# How to create your own Mindset / Terminology Extension

LocalTranslate protects domain-specific vocabulary from being mistranslated,
simplified, or dropped by the LLM — the mechanism is called a **Mindset**.
The built-in mindsets (general, technical, legal, medical, editorial,
academic, marketing, political) are built from the Microsoft Terminology
Collection and IATE. But the mechanism itself doesn't care where the terms
come from. You can protect **any** vocabulary this way — company product
names, internal abbreviations, RPG lore terms, a niche technical field —
without touching a large terminology database at all.

This guide covers two levels:

- **Part A** — add terms to an *existing* mindset (a few minutes, no new
  files beyond one JSON)
- **Part B** — build a *new*, standalone mindset from scratch (e.g. one
  named `rpg` or `company`)

Start with Part A if you're not sure which one you need — it's the lower
effort and the same mechanism underneath.

---

## How the protection actually works (short version)

Before a chunk of text is sent to the LLM, `TermEngine.protect()` replaces
every known source-language term with a stable code (`§Txxxxxxxx§`). The LLM
never sees the original word — it can't mistranslate, simplify, or forget
something it never received. After translation, `TermEngine.restore()` swaps
the codes back using the target-language list.

Everything below is about how those lists get populated.

---

## Part A — Add terms to an existing mindset

Use this when a few specific words are missing from a mindset you already
use (e.g. `technical` doesn't know a newer AI term, or `general` doesn't
know your company's product name).

### 1. Find or create the custom file

```
local_translator/terminology/<mindset>/custom_de.json
local_translator/terminology/<mindset>/custom_en.json
```

Example: to extend the `technical` mindset, create (or edit)

```
local_translator/terminology/technical/custom_de.json
local_translator/terminology/technical/custom_en.json
```

These files are loaded automatically at runtime and merged into the main
`de.json` / `en.json` for that mindset. If a code exists in both, the
custom entry wins.

**Important:** `custom_*.json` is never touched by the build pipeline
(`build_terminology.py`). Rebuilding the main lists from MTC/IATE will not
overwrite or delete your manual entries — that's the whole point of keeping
them in a separate file.

### 2. Pick a code and add the entry

Format is identical to the main lists — `{"§Txxxxxxxx§": "term"}`. The
8-hex-character code just needs to be unique within the mindset; the exact
value doesn't matter functionally as long as `custom_de.json` and
`custom_en.json` use the *same* code for the same term pair.

Easiest way to get a valid-looking code: reuse the hash scheme from the
build pipeline (`md5(f"{mindset}:{de_term.lower()}")[:8]`), or just make one
up — e.g. `§Tcustom01§` doesn't work (must be exactly 8 hex chars,
`0-9a-f`), but `§Tc0570001§` does.

`custom_de.json`:
```json
{
  "§Tc0570001§": "Retrieval-Augmented Generation"
}
```

`custom_en.json`:
```json
{
  "§Tc0570001§": "Retrieval-Augmented Generation"
}
```

(Term stays identical here because it's an established loanword — that's
fine, DE and EN entries don't have to differ.)

### 3. Verify it's active

Two ways:

- **UI**: the terminology indicator in the statusbar shows term count for
  the active mindset/language pair. It should go up by however many terms
  you added.
- **`/terminology/status` endpoint**: returns `src_terms` / `tgt_terms`
  counts directly — compare before/after.

To confirm the *protection* itself is firing (not just that the term is
loaded), translate a short sentence containing the term with a weak/small
model and check the source pane in dev tools or logs for the `§Txxxxxxxx§`
placeholder appearing mid-pipeline — or just check that the term survives
translation unchanged/correctly translated even with a model that would
otherwise mangle it.

That's it — no restart-free hot reload though: the engine caches loaded
lists per process, so **restart the LocalTranslate server** after editing
`custom_*.json` for the change to take effect.

---

## Part B — Build a new, standalone mindset

Use this for a whole new domain that doesn't fit any existing mindset well
— a company wording set, an RPG setting, a technical subfield with its own
established vocabulary.

A mindset has two independent parts. Both are needed for the mindset to be
useful, but they're registered separately:

1. **Prompt behavior** — tone, style rules, veto list → `pipeline/mindsets.json`
2. **Protected vocabulary** — the term lists → `terminology/<name>/`

### 1. Register the mindset in `pipeline/mindsets.json`

Add a new top-level key. No code change needed — `app.py`, the `/mindsets`
endpoint, and `detect_mindset()`'s auto-classification prompt all read this
file dynamically at runtime (`MINDSETS.keys()`), so a new entry here is
automatically:

- selectable in the UI dropdown
- a valid target for the mindset auto-detection classifier
- usable in `/translate/chunk` requests

Structure, using a `company` example:

```json
"company": {
  "label": "Company",
  "rst_mode": "hard_precision",
  "anchor": "You are a translator handling internal documents for a specific company, preserving established internal terminology and product naming.",
  "mam": "Do not mix source and target language. Translate completely — no untranslated fragments from the source language unless on the veto list. Keep product names, internal project codenames, and department abbreviations unchanged unless a target-language equivalent is explicitly defined below.",
  "veto": ["Acme Suite", "Project Falcon", "QA-Team"],
  "p0": "Output only the translation. No introductory sentences. No explanations. Do not repeat the source text. Do not comment on the translation."
}
```

Field meaning (see existing mindsets for more examples):

| Field | Purpose |
|---|---|
| `label` | Shown in the UI dropdown |
| `rst_mode` | `balanced` / `hard_precision` / `soft` — coarse style dial used elsewhere in the pipeline |
| `anchor` | One-sentence role framing at the top of every S1 prompt for this mindset |
| `mam` | The actual behavior rules — "Must Always/Must Never" instructions |
| `veto` | Prompt-level hint: terms to leave untranslated. This is a **soft** signal (the LLM can still ignore it) — it's a complement to the term-list protection below, not a replacement |
| `p0` | Output-format instruction, usually identical across mindsets |

**On the veto list vs. the terminology folder below:** the veto list is a
prompt hint, the terminology folder is a hard mechanical replacement. For
anything that must never be mistranslated (not just "should ideally stay
untranslated"), put it in the term list (step 2), not just in `veto`.

### 2. Create the terminology folder

```
local_translator/terminology/company/de.json
local_translator/terminology/company/en.json
```

Same format as any other mindset — you're not required to run the MTC/IATE
build pipeline at all for a from-scratch mindset. You can write these files
by hand from the start:

```json
{
  "§Tc0aa0001§": "Projektname Falcon",
  "§Tc0aa0002§": "Qualitätssicherungsteam"
}
```

```json
{
  "§Tc0aa0001§": "Project Falcon",
  "§Tc0aa0002§": "QA Team"
}
```

There's no minimum size — even 5–10 entries are enough to see the
protection work on the terms that matter most to you. Grow the list over
time as you notice more terms getting mangled.

If you later want richer coverage than you can realistically hand-write
(e.g. full RPG lore with hundreds of names), you can still use the build
pipeline (`Terminologie-Engine/build_terminology.py`) as a *starting point*
by feeding it a source file in TBX or the expected CSV format — but for
most from-scratch use cases, hand-written lists are the more realistic
path, since MTC/IATE won't contain company- or setting-specific vocabulary
anyway.

### 3. Optional: `custom_de.json` / `custom_en.json` from day one

Nothing stops you from splitting a from-scratch mindset the same way as
Part A — `de.json`/`en.json` for a "core" list, `custom_de.json`/
`custom_en.json` for ongoing additions. For a mindset you're never going to
run the build pipeline on, this split matters less (there's nothing that
would overwrite `de.json` anyway) — it's a convenience for keeping curated
core terms separate from ad-hoc additions, not a requirement.

### 4. Restart and verify

Same as Part A — restart the server, then check `/mindsets` (should list
the new key), select it in the UI, and check `/terminology/status` for
non-zero term counts.

---

## Where this can go

Once a mindset is just "a JSON prompt config + a JSON term list," it
becomes a portable, shareable unit — independent of the codebase itself.
A `company` mindset, an RPG-setting mindset, or a mindset for any other
niche domain can be built once and reused across projects or, in
principle, handed to someone else facing the same translation problem in
the same domain — without either side touching code.

---

## Limits — what this doesn't solve

- **Prompt-level rules (`mam`, `anchor`, `veto`) are not guarantees.** The
  LLM can still ignore style instructions, especially with smaller models.
  Only the term-list protection (`§Txxxxxxxx§`) is mechanically enforced.
- **Term matching is exact-ish, not semantic.** The protection matches the
  literal term (with basic German flexion endings: -e, -s, -es, -en, -n).
  A term written very differently from how it's listed (different
  compound, different case not covered by the flexion list) won't be
  caught.
- **No cross-chunk memory.** Each translation chunk is protected
  independently — this doesn't change with a custom mindset, it's a
  property of the pipeline as a whole (see main `README.md` on chunk-size
  limits).
- **This is not a full glossary/CAT-tool replacement.** It's a targeted
  mechanism against LLM hallucination and drift on the specific terms you
  list — not a general translation-memory or fuzzy-matching system.
