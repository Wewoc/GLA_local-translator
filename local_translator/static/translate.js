// ── translate.js — Übersetzungslogik ────────────────────────────────────────
//
// Besitzt: translate, translateNow, stopTranslation, handleTranslateBtn,
//          deeplFinal, libreFinal, mymemoryFinal, laraFinal
//
// Liest globalen State: config, isTranslating, abortController
// Schreibt globalen State: isTranslating, abortController,
//                          currentTranslation, mindsetDetected
//
// Ruft auf: updateLaraUsage, updateVramStatus (engines.js)
//           showToast, renderDiffHTML (ui.js)
//
// Kohärenz-Modus (source_lang === target_lang): kein Block mehr — das
// Backend läuft dann Prompt B statt Übersetzung (siehe app.py, engines/
// ollama.py). Response kann zusätzlich "diff" + "similarity" enthalten
// (core/diff_utils.py) — wird statt Klartext gerendert, mit Warnhinweis
// bei niedriger Ähnlichkeit (siehe COHERENCE_WARNING_THRESHOLD unten).
//
// HTML-onclick-Abhängigkeiten (müssen global verfügbar sein):
//   handleTranslateBtn, deeplFinal, libreFinal, mymemoryFinal, laraFinal

const CHUNK_LIMITS = { ollama: 6000, deepl: 4900, mymemory: 480 };
const COHERENCE_WARNING_THRESHOLD = 0.6;   // difflib-Ratio — darunter: sichtbarer Warnhinweis

async function translate(engine = 'ollama') {
  const text = document.getElementById('srcText').value.trim();
  if (!text || isTranslating) return;

  const src = document.getElementById('srcLang').value;
  const tgt = document.getElementById('tgtLang').value;
  // Kohärenz-Modus: src === tgt ist erlaubt (Prompt B im Backend übernimmt
  // dann statt Übersetzung ein einsprachiges Lektorat) — kein Block mehr.
  const coherenceMode = src === tgt;

  // Mindset-Detect — erster Schritt, sobald eine Übersetzung tatsächlich
  // startet (egal ob per Button, Enter oder Debounce-Timeout ausgelöst).
  // Läuft nur einmal pro Übersetzungslauf (mindsetDetected-Flag), Reset
  // passiert im finally-Block unten nach Abschluss.
  if (!mindsetDetected) {
    try {
      const mindsetModel = document.getElementById('mindsetModelSelect')?.value || '';
      const res  = await fetch('/mindset/detect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, mindset_model: mindsetModel })
      });
      const data = await res.json();
      const sel  = document.getElementById('mindsetSelect');
      if (data.mindset && sel) {
        sel.value = data.mindset;
        const aiLabel = document.getElementById('mindsetAiLabel');
        if (aiLabel) aiLabel.textContent = `AI: ${data.mindset}`;
      }
    } catch {
      // Mindset-Detect ist ein "Nice-to-have" - schlägt es fehl, läuft die
      // Übersetzung trotzdem mit dem aktuell gewählten Mindset weiter.
    }
    mindsetDetected = true;
  }

  const limit        = CHUNK_LIMITS[engine];
  const needsChunking = limit && text.length > limit;

  isTranslating    = true;
  abortController  = new AbortController();
  const results    = [];
  let minSimilarity = null;
  const out        = document.getElementById('tgtOutput');
  out.textContent  = 'Translating …';
  out.className    = 'output-area loading';
  const warnEl = document.getElementById('coherenceWarning');
  if (warnEl) warnEl.style.display = 'none';

  const translateBtn       = document.getElementById('translateBtn');
  translateBtn.textContent = '■ Stop';
  translateBtn.onclick     = stopTranslation;
  document.getElementById('mindsetSelect').disabled = true;

  try {
    if (needsChunking) {
      // ── Chunks vorbereiten ────────────────────────────────────────────────
      const prepRes  = await fetch('/translate/chunks/prepare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, engine })
      });
      const prepData = await prepRes.json();
      if (!prepRes.ok) throw new Error(prepData.detail || 'Error');

      const { chunks, total } = prepData;
      let context = '';

      // Modelle vor Start entladen
      await fetch('/ollama/unload', { method: 'POST' }).catch(() => {});

      // Chunk-Tabelle aufbauen
      out.className = 'output-area';
      out.innerHTML = '';
      const table   = document.createElement('table');
      table.className = 'chunk-table';
      chunks.forEach((chunk, i) => {
        const tr     = document.createElement('tr');
        const tdRight = document.createElement('td');
        tdRight.className = 'chunk-right';
        tdRight.id        = `chunk-right-${i}`;
        tdRight.innerHTML = '<span class="chunk-placeholder">…</span>';
        tr.appendChild(tdRight);
        table.appendChild(tr);
      });
      out.appendChild(table);

      // ── Chunk-Loop ────────────────────────────────────────────────────────
      for (let i = 0; i < chunks.length; i++) {
        const s2sel = document.getElementById('s2ModelSelect').value;
        document.getElementById('engineBadge').innerHTML =
          `translating… (${i + 1} / ${total}) <span class="badge-pulse"></span>`;

        const res = await fetch('/translate/chunk', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          signal: abortController.signal,
          body: JSON.stringify({
            text:        chunks[i],
            source_lang: src,
            target_lang: tgt,
            engine,
            context,
            mindset:     document.getElementById('mindsetSelect').value,
            s2_model:    s2sel,
            chunk_index: i,
          })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Error');

        results.push(data.translation);
        // letzter Absatz als Kontext für nächsten Chunk
        const paras = data.translation.split('\n\n');
        context = paras[paras.length - 1].slice(-300);

        const cell = document.getElementById(`chunk-right-${i}`);
        if (cell) {
          if (data.diff) {
            cell.innerHTML = renderDiffHTML(data.diff);
            if (typeof data.similarity === 'number') {
              minSimilarity = minSimilarity === null
                ? data.similarity
                : Math.min(minSimilarity, data.similarity);
            }
          } else {
            cell.textContent = data.translation;
          }
        }
        document.getElementById('engineBadge').innerHTML =
          `translating… (${i + 1} / ${total} ✓) <span class="badge-pulse"></span>`;
      }

      currentTranslation = results.join('\n\n');

    } else {
      // ── Normaler Pfad — kein Chunking ─────────────────────────────────────
      await fetch('/ollama/unload', { method: 'POST' }).catch(() => {});
      const res = await fetch('/translate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, source_lang: src, target_lang: tgt, engine,
                             s2_model: document.getElementById('s2ModelSelect').value })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Error');
      currentTranslation = data.translation;

      // Chunk-Tabelle darf nicht überschrieben werden — dieser Zweig läuft
      // nur, wenn needsChunking von vornherein false war (siehe MAINTENANCE).
      if (data.diff) {
        out.innerHTML = renderDiffHTML(data.diff);
        out.className = 'output-area';
        if (typeof data.similarity === 'number') minSimilarity = data.similarity;
      } else {
        out.textContent = currentTranslation;
        out.className   = 'output-area';
      }
    }

    if (warnEl && coherenceMode && minSimilarity !== null && minSimilarity < COHERENCE_WARNING_THRESHOLD) {
      warnEl.textContent =
        `⚠ Auffällig große Abweichung vom Original erkannt (Ähnlichkeit ${(minSimilarity * 100).toFixed(0)}%) — bitte sorgfältig prüfen.`;
      warnEl.style.display = '';
    }

    document.getElementById('tgtCount').textContent =
      `${currentTranslation.length.toLocaleString('en')} chars`;
    if (engine === 'lara') updateLaraUsage();
    document.getElementById('engineBadge').textContent = coherenceMode ? 'coherence pass' : `via ${engine}`;

  } catch (err) {
    if (err.name === 'AbortError') {
      out.textContent = results.length
        ? results.join('\n\n') + '\n\n[aborted]'
        : '[aborted]';
      out.className = 'output-area';
    } else {
      out.textContent = `⚠ ${err.message}`;
      out.className   = 'output-area';
      showToast(err.message, 'err');
    }
  } finally {
    isTranslating   = false;
    abortController = null;
    mindsetDetected = false;

    const btn       = document.getElementById('translateBtn');
    btn.textContent = '▶ Translate';
    btn.onclick     = translateNow;

    const mindsetSel     = document.getElementById('mindsetSelect');
    mindsetSel.disabled  = false;
    mindsetSel.value     = config.default_mindset || 'general';
    // AI-Label bleibt stehen — wird erst bei clearAll() oder der nächsten
    // erfolgreichen Detection (translate(), Anfang) überschrieben.

    if (engine === 'ollama') {
      fetch('/ollama/unload', { method: 'POST' })
        .then(() => updateVramStatus())
        .catch(() => {});
    }
  }
}

function translateNow()  { translate('ollama'); }
function deeplFinal()    { translate('deepl'); }
function libreFinal()    { translate('libretranslate'); }
function mymemoryFinal() { translate('mymemory'); }
function laraFinal()     { translate('lara'); }

function stopTranslation() {
  if (abortController) abortController.abort();
}

function handleTranslateBtn() {
  if (isTranslating) stopTranslation();
  else translateNow();
}
