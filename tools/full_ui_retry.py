"""Retry selected records through every visible Medinet clinical form."""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "medinet_api"))

from app import ksk_workbook as wb
from app.clinical import ClinicalFiller
from app.importer import AppleScriptImporter
from import_all import resolve_record


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--file", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--only-stt", type=int, action="append", required=True)
    p.add_argument("--from", dest="exam_from", default="01/07/2026")
    p.add_argument("--to", dest="exam_to", default="31/08/2026")
    args = p.parse_args()

    keep = set(args.only_stt)
    records = [r for r in wb.load_records(args.file) if int(r["stt"]) in keep]
    records.sort(key=lambda r: int(r["stt"]))
    filler = ClinicalFiller(AppleScriptImporter(dry_run=False, age_group="M2"),
                            args.exam_from, args.exam_to, dry_run=False)
    results = []
    for index, record in enumerate(records, 1):
        stt, started = int(record["stt"]), time.time()
        who, error = resolve_record(record)
        if error:
            row = {"stt": stt, "status": error, "problems": []}
        else:
            result = {"sections": {}, "problems": []}
            filler.fill_sections(record, who, who["exam"], result)
            row = {"stt": stt, "status": result.get("status"),
                   "sections": result.get("sections"), "problems": result.get("problems")}
        row["seconds"] = round(time.time() - started, 1)
        results.append(row)
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(results, ensure_ascii=False, indent=2))
        print(f"[{index}/{len(records)}] TT{stt}: {row['status']} ({row['seconds']:.0f}s)",
              flush=True)


if __name__ == "__main__":
    main()
