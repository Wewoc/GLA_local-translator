// ── ui.js — UI-Hilfsfunktionen ──────────────────────────────────────────────
//
// Besitzt: showToast, clearAll, copyTranslation, exportMD, openExportDir,
//          updateCharCount, swapLangs, updatePipelineGray, isCoherenceMode,
//          updateCoherenceUI, renderDiffHTML
//
// Liest globalen State: config, currentTranslation
// Schreibt globalen State: currentTranslation, mindsetDetected (nur clearAll)
// Ruft auf: checkLibre() aus engines.js (swapLangs, updateCoherenceUI — ok,
//           da Click-/Change-Event); updateCharCount (updateCoherenceUI)

function showToast(msg, type = '') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = `toast show ${type}`;
  setTimeout(() => t.className = 'toast', 3000);
}

function clearAll() {
  document.getElementById('srcText').value = '';
  document.getElementById('tgtOutput').innerHTML =
    '<span class="placeholder-text">Translation appears here …</span>';
  document.getElementById('engineBadge').textContent = '';
  currentTranslation = '';
  mindsetDetected = false;
  const aiLabel = document.getElementById('mindsetAiLabel');
  if (aiLabel) aiLabel.textContent = '';
  ['srcCount', 'tgtCount'].forEach(id =>
    document.getElementById(id).textContent = '0 chars');
  const warnEl = document.getElementById('coherenceWarning');
  if (warnEl) warnEl.style.display = 'none';
}

function copyTranslation() {
  if (!currentTranslation) { showToast('No translation available', 'err'); return; }
  navigator.clipboard.writeText(currentTranslation)
    .then(() => showToast('✓ Copied to clipboard', 'ok'))
    .catch(() => showToast('Copy failed', 'err'));
}

async function exportMD() {
  const src = document.getElementById('srcText').value.trim();
  if (!src)               { showToast('No text to export', 'err'); return; }
  if (!currentTranslation){ showToast('No translation yet', 'err'); return; }
  try {
    const res = await fetch('/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source_text: src,
        target_text: currentTranslation,
        source_lang: document.getElementById('srcLang').value,
        target_lang: document.getElementById('tgtLang').value,
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail);
    showToast(`✓ Exported to ${data.export_dir}`, 'ok');
  } catch (err) {
    showToast(err.message, 'err');
  }
}

async function openExportDir() {
  try {
    const r = await fetch('/export/open');
    if (!r.ok) {
      const d = await r.json();
      showToast(d.detail || 'Could not open folder', 'err');
    }
  } catch {
    showToast('Could not open folder', 'err');
  }
}

function updateCharCount(taId, countId) {
  const len = document.getElementById(taId).value.length;
  document.getElementById(countId).textContent = `${len.toLocaleString('en')} chars`;
  const btn = document.getElementById('mymemoryBtn');
  if (btn && !btn.dataset.forceDisabled) {
    btn.disabled = !config.mymemory_available;
    if (len > 500) {
      btn.textContent = '★ MyMemory (chunked)';
      btn.title = 'Text will be split into 500-char chunks';
    } else {
      btn.textContent = '★ MyMemory - max. 500 characters';
      btn.title = 'Final pass via MyMemory';
    }
  }
}

function swapLangs() {
  const s = document.getElementById('srcLang');
  const t = document.getElementById('tgtLang');
  [s.value, t.value] = [t.value, s.value];
  if (config.libretranslate_available) checkLibre();
}

function updatePipelineGray() {
  const s1   = document.getElementById('modelSelect').value;
  const s2   = document.getElementById('s2ModelSelect').value;
  const used = new Set([s1, s2].filter(Boolean));
  ['s2ModelSelect'].forEach(id => {
    document.getElementById(id).querySelectorAll('option').forEach(opt => {
      if (!opt.value) return;
      const inUse = used.has(opt.value) && opt.value !== s2;
      opt.textContent = inUse ? `${opt.value} ✓` : opt.value;
    });
  });
}

// ── Kohärenz-Modus — Status + Diff-Rendering ────────────────────────────────
//
// Aktiv, wenn source_lang === target_lang: Backend läuft dann Prompt B
// (einsprachiges Lektorat) statt Übersetzung, siehe engines/ollama.py
// run_coherence_pass(). S2 und externe Engines ergeben in diesem Fall
// keinen Sinn und werden hier gesperrt.

function isCoherenceMode() {
  return document.getElementById('srcLang').value === document.getElementById('tgtLang').value;
}

function updateCoherenceUI() {
  const active = isCoherenceMode();

  const s2sel = document.getElementById('s2ModelSelect');
  if (s2sel) {
    s2sel.disabled = active;
    if (active) s2sel.value = '';
  }

  const deeplBtn = document.getElementById('deeplBtn');
  if (deeplBtn) deeplBtn.disabled = active ? true : !config.deepl_available;

  const laraBtn = document.getElementById('laraBtn');
  if (laraBtn) laraBtn.disabled = active ? true : !config.lara_available;

  // MyMemory/LibreTranslate haben eigene reaktive Status-Funktionen —
  // im Kohärenz-Modus nur hart sperren, beim Verlassen deren eigene Logik
  // erneut aufrufen statt sie hier zu duplizieren (Single Owner).
  const mmBtn = document.getElementById('mymemoryBtn');
  if (mmBtn) {
    if (active) mmBtn.disabled = true;
    else updateCharCount('srcText', 'srcCount');
  }

  const libreBtn = document.getElementById('libreBtn');
  if (libreBtn) {
    if (active) libreBtn.disabled = true;
    else if (config.libretranslate_available) checkLibre();
  }

  const label = document.getElementById('coherenceLabel');
  if (label) label.style.display = active ? '' : 'none';

  if (!active) {
    const warnEl = document.getElementById('coherenceWarning');
    if (warnEl) warnEl.style.display = 'none';
  }
}

function renderDiffHTML(segments) {
  const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  return segments.map(seg => {
    const text = esc(seg.text);
    if (seg.tag === 'insert') return `<ins class="diff-insert">${text}</ins>`;
    if (seg.tag === 'delete') return `<del class="diff-delete">${text}</del>`;
    return text;
  }).join('');
}
