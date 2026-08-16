"""
filter_terminology.py — Post-filter for already-built terminology lists

Three independent passes — runnable individually or combined:

  Pass 1 — Blocklist (default, always active)
    Removes fragments, everyday words, uppercase-letter artifacts.

  Pass 2 — Ollama filter (--filter)
    Ollama judges: "Is this a genuine domain-specific term for this domain?"
    Recommended: mistral or qwen2.5:7b

  Pass 3 — Validation (--validate)
    aya-expanse judges: "Is the DE->EN translation correct?"
    Checks translation quality of the pairs, not just whether it's a domain term.
    Recommended: aya-expanse:latest (multilingual, knows DE/EN terminology)

A backup is created before every write (terminology/{mindset}/backup/).

Usage:
  python filter_terminology.py --dir ../terminology
  python filter_terminology.py --dir ../terminology --dry-run
  python filter_terminology.py --dir ../terminology --filter --model mistral
  python filter_terminology.py --dir ../terminology --validate --model aya-expanse:latest
  python filter_terminology.py --dir ../terminology --filter --validate --model aya-expanse:latest
  python filter_terminology.py --dir ../terminology --mindset technical legal
"""

import argparse
import json
import re
import shutil
import sys
import time
import urllib.request
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────
#
# Stricter blocklist compared to build_terminology.py:
#
#   r"^\w{1,4}$"          too short (1-4 characters)
#                         catches: ping, ring, fore, sire, rent, thin, time, task
#
#   r"^\d+"               starts with a digit
#
#   r"^\(.*\)$"           entirely in parentheses
#
#   r"^[A-ZÄÖÜ]{2,}$"    uppercase only (NICHT, ODER, REICH, LARGE, FAST, MODE)
#                         exception: ACRONYM_ALLOWLIST
#
#   r"^[a-z]{1,5}$"       short lowercase fragments from IATE parsing
#                         catches: adit, cant, fore, quire, fines, mounts
#
#   r"^[A-Z][a-z]{1,4}$"  short capitalized words (Here, More, Other, Excel)
#
#   r"^(ja|nein|...)$"    everyday words
BLOCKLIST_PATTERNS = [
    r"^\w{1,4}$",
    r"^\d+",
    r"^\(.*\)$",
    r"^[A-ZÄÖÜ]{2,}$",
    r"^[a-z]{1,5}$",
    r"^[A-Z][a-z]{1,4}$",
    r"^(ja|nein|ok|ok\.|gut|neu|alt|gross|klein|alle|jede[rs]?|bzw|usw|etc|ggf|inkl|exkl|ca|max|min)$",
    r"^(Eiche|Sonde|Frist|Sache|Spiel|Dauer|Dichte|Boden|Welle|Stein|Kraft)$",
]

# Acronyms kept despite being uppercase
ACRONYM_ALLOWLIST = {
    "VRAM", "API", "CPU", "GPU", "RAM", "ROM", "SQL", "XML", "JSON", "HTTP",
    "HTTPS", "FTP", "SSH", "TCP", "UDP", "DNS", "URL", "URI", "HTML", "CSS",
    "REST", "SOAP", "PDF", "CSV", "ZIP", "VPN", "LAN", "WAN", "SSD", "HDD",
    "BIOS", "UEFI", "USB", "PCIe", "HDMI", "RGB", "LED", "LCD", "OLED",
}

ALL_MINDSETS = ["general", "technical", "legal", "medical",
                "editorial", "academic", "marketing", "political"]

# ── Ollama Helper Function ────────────────────────────────────────────────────

def _ollama_call(prompt: str, model: str, host: str, timeout: int = 120) -> str:
    """Runs a single Ollama call. Returns the response text."""
    payload = json.dumps({
        "model": model, "prompt": prompt, "stream": False
    }).encode()
    req = urllib.request.Request(
        f"{host}/api/generate", data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read()).get("response", "").strip()


def _parse_number_list(response: str, batch_len: int) -> set:
    """Parses a comma-separated number list from an Ollama response."""
    indices = set()
    if response.lower() == "none":
        return indices
    for p in response.split(","):
        p = p.strip()
        if p.isdigit():
            idx = int(p) - 1
            if 0 <= idx < batch_len:
                indices.add(idx)
    return indices

# ── Pass 1: Blocklist ─────────────────────────────────────────────────────────

def is_trivial(term: str) -> bool:
    if term.strip() in ACRONYM_ALLOWLIST:
        return False
    for pattern in BLOCKLIST_PATTERNS:
        if re.match(pattern, term.strip(), re.IGNORECASE):
            return True
    return False


def filter_pair(de_term: str, en_term: str) -> bool:
    if is_trivial(de_term) or is_trivial(en_term):
        return True
    if de_term.lower() == en_term.lower():
        return True
    return False

# ── Pass 2: Ollama Domain-Term Filter ────────────────────────────────────────

def ollama_filter_batch(
    pairs: list[tuple],
    mindset: str,
    model: str,
    host: str,
    batch_size: int = 30,
) -> list[tuple]:
    """
    Pass 2 — domain-term filter.
    Question: "Is this a genuine domain-specific term for this domain?"
    """
    CONTEXT = {
        "general":   "general-purpose reference",
        "technical": "software and IT documentation",
        "legal":     "contracts and legislation",
        "medical":   "clinical and research texts",
        "editorial": "journalism and prose",
        "academic":  "scholarly publications",
        "marketing": "advertising and business",
        "political": "policy and government",
    }
    context = CONTEXT.get(mindset, "professional documents")

    # ── Load checkpoint ───────────────────────────────────────────────────────
    checkpoint_path = Path(__file__).resolve().parent / f".filter2_checkpoint_{mindset}.json"
    start_batch = 0
    kept, skipped = [], 0

    if checkpoint_path.exists():
        try:
            cp = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            if cp.get("model") == model and cp.get("total_pairs") == len(pairs):
                start_batch = cp["completed_batches"]
                kept_codes  = set(cp["kept_codes"])
                kept        = [p for p in pairs if p[0] in kept_codes]
                skipped     = cp["skipped"]
                print(f"    Resuming from batch {start_batch + 1} ({len(kept)} already kept)")
            else:
                print(f"    Checkpoint outdated — starting over")
                checkpoint_path.unlink()
        except Exception:
            print(f"    Checkpoint unreadable — starting over")
            checkpoint_path.unlink()

    print(f"    Pass 2 domain-term filter [{mindset}]: {len(pairs)} pairs ...")
    total = (len(pairs) + batch_size - 1) // batch_size

    for i in range(start_batch * batch_size, len(pairs), batch_size):
        batch = pairs[i: i + batch_size]
        bn = i // batch_size + 1
        numbered = "\n".join(
            f"{j+1}. DE: {de} | EN: {en}"
            for j, (_, de, en) in enumerate(batch)
        )
        prompt = (
            f"Terminology filter for {context} documents.\n"
            "Return ONLY numbers of genuine domain-specific terms. "
            "Remove: everyday words, generic adjectives, word fragments, "
            "abbreviations of common words, proper nouns unrelated to the domain.\n"
            "Format: comma-separated numbers. Example: 1,3,5\n"
            "If none qualify: none\n\n"
            + numbered
        )
        try:
            rt = _ollama_call(prompt, model, host)
            indices = _parse_number_list(rt, len(batch))
            for idx in sorted(indices):
                kept.append(batch[idx])
            skipped += len(batch) - len(indices)
            print(f"      Batch {bn}/{total}: {len(indices)} kept, "
                  f"{len(batch)-len(indices)} filtered")
            checkpoint_path.write_text(json.dumps({
                "mindset": mindset, "model": model,
                "total_pairs": len(pairs), "completed_batches": bn,
                "kept_codes": [p[0] for p in kept], "skipped": skipped,
            }, ensure_ascii=False), encoding="utf-8")
            time.sleep(0.1)
        except Exception as ex:
            print(f"      [WARN] Batch {bn}: {ex} — kept unchanged")
            kept.extend(batch)

    if checkpoint_path.exists():
        checkpoint_path.unlink()
    print(f"    -> {len(kept)} kept, {skipped} filtered")
    return kept

# ── Pass 3: Translation Validation ───────────────────────────────────────────

def ollama_validate_batch(
    pairs: list[tuple],
    mindset: str,
    model: str,
    host: str,
    batch_size: int = 20,
) -> list[tuple]:
    """
    Pass 3 — translation quality.
    Question: "Is the DE->EN translation correct and natural?"

    Smaller batches (20 instead of 30) because the task is harder
    and aya-expanse has to judge both languages at once.
    """
    DOMAIN = {
        "general":   "general professional",
        "technical": "software, IT, and engineering",
        "legal":     "legal and regulatory",
        "medical":   "medical and clinical",
        "editorial": "journalism and publishing",
        "academic":  "academic and scientific",
        "marketing": "business and marketing",
        "political": "political and governmental",
    }
    domain = DOMAIN.get(mindset, "professional")

    # ── Load checkpoint ───────────────────────────────────────────────────────
    checkpoint_path = Path(__file__).resolve().parent / f".filter3_checkpoint_{mindset}.json"
    start_batch = 0
    kept, rejected = [], 0

    if checkpoint_path.exists():
        try:
            cp = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            if cp.get("model") == model and cp.get("total_pairs") == len(pairs):
                start_batch = cp["completed_batches"]
                kept_codes  = set(cp["kept_codes"])
                kept        = [p for p in pairs if p[0] in kept_codes]
                rejected    = cp["rejected"]
                print(f"    Resuming from batch {start_batch + 1} ({len(kept)} already kept)")
            else:
                print(f"    Checkpoint outdated — starting over")
                checkpoint_path.unlink()
        except Exception:
            print(f"    Checkpoint unreadable — starting over")
            checkpoint_path.unlink()

    print(f"    Pass 3 translation validation [{mindset}]: {len(pairs)} pairs ...")
    total = (len(pairs) + batch_size - 1) // batch_size

    for i in range(start_batch * batch_size, len(pairs), batch_size):
        batch = pairs[i: i + batch_size]
        bn = i // batch_size + 1
        numbered = "\n".join(
            f"{j+1}. DE: {de} → EN: {en}"
            for j, (_, de, en) in enumerate(batch)
        )
        prompt = (
            f"You are a bilingual DE/EN terminology validator for {domain} texts.\n"
            "Below are German-English term pairs.\n"
            "Return ONLY the numbers of pairs where the English term is a correct, "
            "natural, and domain-appropriate translation of the German term.\n"
            "Reject if: wrong meaning, outdated usage, nonsensical, or the EN term "
            "is unrelated to the DE term.\n"
            "Format: comma-separated numbers only. Example: 1,3,5\n"
            "If none are correct: none\n\n"
            + numbered
        )
        try:
            rt = _ollama_call(prompt, model, host, timeout=180)
            indices = _parse_number_list(rt, len(batch))
            for idx in sorted(indices):
                kept.append(batch[idx])
            rejected += len(batch) - len(indices)
            print(f"      Batch {bn}/{total}: {len(indices)} kept, "
                  f"{len(batch)-len(indices)} rejected")
            checkpoint_path.write_text(json.dumps({
                "mindset": mindset, "model": model,
                "total_pairs": len(pairs), "completed_batches": bn,
                "kept_codes": [p[0] for p in kept], "rejected": rejected,
            }, ensure_ascii=False), encoding="utf-8")
            time.sleep(0.1)
        except Exception as ex:
            print(f"      [WARN] Batch {bn}: {ex} — kept unchanged")
            kept.extend(batch)

    if checkpoint_path.exists():
        checkpoint_path.unlink()
    print(f"    -> {len(kept)} kept, {rejected} rejected")
    return kept

# ── Main Function Per Mindset ─────────────────────────────────────────────────

def filter_mindset(
    mindset_dir: Path,
    mindset: str,
    use_filter: bool,
    use_validate: bool,
    ollama_model: str,
    ollama_host: str,
    dry_run: bool,
) -> dict:
    de_path = mindset_dir / "de.json"
    en_path = mindset_dir / "en.json"

    if not de_path.exists() or not en_path.exists():
        print(f"  [{mindset}] SKIP — de.json or en.json missing")
        return {}

    de_data = json.loads(de_path.read_text(encoding="utf-8"))
    en_data = json.loads(en_path.read_text(encoding="utf-8"))

    if not de_data:
        print(f"  [{mindset}] SKIP — empty")
        return {}

    print(f"  [{mindset}] {len(de_data)} entries")

    # ── Pass 1: Blocklist ─────────────────────────────────────────────────────
    pairs_in = [(code, de_data[code], en_data.get(code, ""))
                for code in de_data if code in en_data]
    pairs_ok = [(code, de, en) for code, de, en in pairs_in
                if not filter_pair(de, en)]
    removed_blocklist = len(pairs_in) - len(pairs_ok)
    print(f"    Pass 1 blocklist: {removed_blocklist} removed, {len(pairs_ok)} remaining")

    # ── Pass 2: Domain-term filter ────────────────────────────────────────────
    if use_filter and pairs_ok:
        pairs_ok = ollama_filter_batch(
            pairs_ok, mindset, ollama_model, ollama_host
        )

    # ── Pass 3: Translation validation ────────────────────────────────────────
    if use_validate and pairs_ok:
        pairs_ok = ollama_validate_batch(
            pairs_ok, mindset, ollama_model, ollama_host
        )

    # ── Backup + Write ────────────────────────────────────────────────────────
    total_removed = len(pairs_in) - len(pairs_ok)

    if dry_run:
        print(f"    DRY RUN — would remove {total_removed} entries "
              f"({len(pairs_ok)} remaining)")
        return {"before": len(pairs_in), "after": len(pairs_ok), "removed": total_removed}

    backup_dir = mindset_dir / "backup"
    backup_dir.mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    shutil.copy2(de_path, backup_dir / f"de_{ts}.json")
    shutil.copy2(en_path, backup_dir / f"en_{ts}.json")

    new_de = {code: de for code, de, _ in pairs_ok}
    new_en = {code: en for code, _, en in pairs_ok}

    de_path.write_text(json.dumps(new_de, ensure_ascii=False, indent=2), encoding="utf-8")
    en_path.write_text(json.dumps(new_en, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"    -> {len(new_de)} entries written "
          f"({total_removed} removed, backup in backup/)")

    return {"before": len(pairs_in), "after": len(new_de), "removed": total_removed}

# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Post-filter for already-built terminology lists (3 passes)"
    )
    parser.add_argument("--dir",      type=Path, required=True,
                        help="Path to the terminology folder")
    parser.add_argument("--mindset",  nargs="*", default=ALL_MINDSETS,
                        help="Filter mindsets (default: all)")
    parser.add_argument("--filter",   action="store_true",
                        help="Enable pass 2: Ollama domain-term filter")
    parser.add_argument("--validate", action="store_true",
                        help="Enable pass 3: translation validation via aya-expanse")
    parser.add_argument("--model",    default="aya-expanse:latest",
                        help="Ollama model (default: aya-expanse:latest)")
    parser.add_argument("--host",     default="http://localhost:11434",
                        help="Ollama host")
    parser.add_argument("--dry-run",  action="store_true",
                        help="Only show what would be removed, write nothing")
    args = parser.parse_args()

    if not args.dir.exists():
        print(f"[ERROR] Folder not found: {args.dir}")
        sys.exit(1)

    print()
    print("  filter_terminology — post-filter")
    passes = ["Pass 1: Blocklist"]
    if args.filter:   passes.append("Pass 2: Domain-term filter")
    if args.validate: passes.append("Pass 3: Translation validation")
    print(f"  Active passes: {' + '.join(passes)}")
    if args.validate or args.filter:
        print(f"  Model: {args.model}")
    if args.dry_run:
        print("  DRY RUN — no files will be changed")
    print()

    total_stats = {}
    for mindset in args.mindset:
        mindset_dir = args.dir / mindset
        stats = filter_mindset(
            mindset_dir=mindset_dir,
            mindset=mindset,
            use_filter=args.filter,
            use_validate=args.validate,
            ollama_model=args.model,
            ollama_host=args.host,
            dry_run=args.dry_run,
        )
        if stats:
            total_stats[mindset] = stats
        print()

    if total_stats:
        print("  Summary:")
        total_before  = sum(s["before"]  for s in total_stats.values())
        total_after   = sum(s["after"]   for s in total_stats.values())
        total_removed = total_before - total_after
        for mindset, s in total_stats.items():
            print(f"    {mindset:12} {s['before']:>6} -> {s['after']:>6} (-{s['removed']})")
        print(f"    {'TOTAL':12} {total_before:>6} -> {total_after:>6} (-{total_removed})")
    print()


if __name__ == "__main__":
    main()
