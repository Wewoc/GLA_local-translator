"""
apply_checkpoint.py — Applies an existing checkpoint directly to the JSON files.

Reads:  .filter3_checkpoint_{mindset}.json
Writes: terminology/{mindset}/de.json + en.json (filtered)
A backup is created beforehand.

Call (from the Terminologie-Engine folder):
  python apply_checkpoint.py --mindset technical --dir ..\terminology
"""

import argparse
import json
import shutil
import time
from pathlib import Path

def apply(mindset: str, terminology_dir: Path, script_dir: Path) -> None:
    checkpoint_path = script_dir / f".filter3_checkpoint_{mindset}.json"

    if not checkpoint_path.exists():
        print(f"[ERROR] Checkpoint not found: {checkpoint_path}")
        return

    cp = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    kept_codes = set(cp["kept_codes"])
    completed  = cp["completed_batches"]
    total      = cp["total_pairs"]

    print(f"[{mindset}] Checkpoint loaded:")
    print(f"  Completed batches:      {completed}")
    print(f"  Total pairs:            {total}")
    print(f"  Kept (kept_codes):      {len(kept_codes)}")

    de_path = terminology_dir / mindset / "de.json"
    en_path = terminology_dir / mindset / "en.json"

    if not de_path.exists() or not en_path.exists():
        print(f"[ERROR] JSON files not found: {de_path}")
        return

    de_data = json.loads(de_path.read_text(encoding="utf-8"))
    en_data = json.loads(en_path.read_text(encoding="utf-8"))

    print(f"  Entries before filter:  {len(de_data)}")

    # Backup
    backup_dir = terminology_dir / mindset / "backup"
    backup_dir.mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    shutil.copy2(de_path, backup_dir / f"de_{ts}.json")
    shutil.copy2(en_path, backup_dir / f"en_{ts}.json")
    print(f"  Backup created in backup/")

    # Filter — keep only kept_codes
    new_de = {code: term for code, term in de_data.items() if code in kept_codes}
    new_en = {code: term for code, term in en_data.items() if code in kept_codes}

    de_path.write_text(json.dumps(new_de, ensure_ascii=False, indent=2), encoding="utf-8")
    en_path.write_text(json.dumps(new_en, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"  Entries after filter:   {len(new_de)} (−{len(de_data) - len(new_de)})")
    print(f"  Note: checkpoint contained {completed} of {(total + 19) // 20} batches")

    if completed < (total + 19) // 20:
        remaining = (total + 19) // 20 - completed
        print(f"  WARNING: {remaining} batches were not validated — ")
        print(f"  these entries are missing from kept_codes and were removed.")
        print(f"  Recommendation: catch up on the remaining batches with validate.bat.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mindset", required=True)
    parser.add_argument("--dir", type=Path, required=True)
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    apply(args.mindset, args.dir.resolve(), script_dir)
