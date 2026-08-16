"""
core/diff_utils.py — word diff for the Coherence Pass

Contains:
  - compute_diff(original, edited) -> dict

Pure text helper, no IO, no dependency on other core modules.
Uses only the Python standard library (difflib) — no new dependency.

Imported by: app.py — exclusively in Coherence Mode
(source_lang == target_lang), not in the normal translation path.
"""

from __future__ import annotations

import difflib
import re

_WORD_SPLIT_RE = re.compile(r"(\s+)")


def _tokenize(text: str) -> list[str]:
    """Splits into words + whitespace as separate tokens — whitespace is
    preserved for a readable diff display instead of being lost on join."""
    return [t for t in _WORD_SPLIT_RE.split(text) if t != ""]


def compute_diff(original: str, edited: str) -> dict:
    """Word-level diff between the original and the Coherence Pass result.

    Returns:
        {
          "segments": [{"tag": "equal"|"insert"|"delete", "text": str}, ...],
          "similarity": float,   # difflib.SequenceMatcher ratio, 0..1
        }

    "similarity" also serves as the warning threshold in the frontend (see
    COHERENCE_WARNING_THRESHOLD in translate.js) — no separate fallback/
    drift mechanism like run_s2() has, a deliberate choice: a visible
    notice instead of a silent revert.
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
