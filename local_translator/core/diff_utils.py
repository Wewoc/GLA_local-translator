"""
core/diff_utils.py — Wort-Diff für den Kohärenz-Pass

Besitzt:
  - compute_diff(original, edited) -> dict

Reiner Text-Helfer, kein IO, keine Abhängigkeit auf andere core-Module.
Nutzt nur die Python-Standardbibliothek (difflib) — keine neue Dependency.

Wird importiert von: app.py — ausschließlich im Kohärenz-Modus
(source_lang == target_lang), nicht im normalen Übersetzungspfad.
"""

from __future__ import annotations

import difflib
import re

_WORD_SPLIT_RE = re.compile(r"(\s+)")


def _tokenize(text: str) -> list[str]:
    """Splittet in Wörter + Whitespace als eigene Tokens — Whitespace bleibt
    für eine lesbare Diff-Anzeige erhalten, statt beim Join verloren zu gehen."""
    return [t for t in _WORD_SPLIT_RE.split(text) if t != ""]


def compute_diff(original: str, edited: str) -> dict:
    """Wortweiser Diff zwischen Original und Kohärenz-Pass-Ergebnis.

    Returns:
        {
          "segments": [{"tag": "equal"|"insert"|"delete", "text": str}, ...],
          "similarity": float,   # difflib.SequenceMatcher-Ratio, 0..1
        }

    "similarity" dient zugleich als Warnschwelle im Frontend (siehe
    COHERENCE_WARNING_THRESHOLD in translate.js) — kein separater
    Fallback-/Drift-Mechanismus wie bei run_s2(), bewusst so entschieden:
    sichtbarer Hinweis statt stillem Revert.
    """
    orig_tokens = _tokenize(original)
    edit_tokens = _tokenize(edited)

    matcher = difflib.SequenceMatcher(a=orig_tokens, b=edit_tokens, autojunk=False)
    segments = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            segments.append({"tag": "equal", "text": "".join(orig_tokens[i1:i2])})
        elif tag == "delete":
            segments.append({"tag": "delete", "text": "".join(orig_tokens[i1:i2])})
        elif tag == "insert":
            segments.append({"tag": "insert", "text": "".join(edit_tokens[j1:j2])})
        elif tag == "replace":
            segments.append({"tag": "delete", "text": "".join(orig_tokens[i1:i2])})
            segments.append({"tag": "insert", "text": "".join(edit_tokens[j1:j2])})

    return {"segments": segments, "similarity": matcher.ratio()}
