"""
core/chunking.py — text splitting and language-name helper function

Contains:
  - LANG_NAMES (derived from LANGUAGES)
  - lang_name(code) — used by engines/ollama.py and app.py (export)
  - split_chunks(text, limit)

Imports: core.config (LANGUAGES)
Imported by: engines/ollama.py, app.py
"""

from core.config import LANGUAGES

# ── Language-Name Mapping ─────────────────────────────────────────────────────

LANG_NAMES = {v: k for k, v in LANGUAGES.items()}

def lang_name(code: str) -> str:
    return LANG_NAMES.get(code.upper(), code)

# ── Chunk Logic ───────────────────────────────────────────────────────────────

def split_chunks(text: str, limit: int) -> list[str]:
    """Split text into chunks — merge paragraphs up to the limit, then start a new chunk."""
    if len(text) <= limit:
        return [text]

    # Collect small units (paragraph → line → sentence → hard cut)
    units = []
    for para in text.split("\n\n"):
        if not para.strip():
            continue
        if len(para) <= limit:
            units.append(para)
        else:
            for line in para.split("\n"):
                if not line.strip():
                    continue
                if len(line) <= limit:
                    units.append(line)
                else:
                    for sentence in line.split(". "):
                        if not sentence.strip():
                            continue
                        if len(sentence) <= limit:
                            units.append(sentence)
                        else:
                            for i in range(0, len(sentence), limit):
                                units.append(sentence[i:i+limit])

    # Merge units into chunks until the limit is reached
    chunks = []
    current = ""
    for unit in units:
        separator = "\n\n" if current else ""
        if len(current) + len(separator) + len(unit) <= limit:
            current += separator + unit
        else:
            if current:
                chunks.append(current)
            current = unit
    if current:
        chunks.append(current)

    return chunks
