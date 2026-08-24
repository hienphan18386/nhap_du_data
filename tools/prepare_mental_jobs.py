"""Prepare a local, resumable browser job queue from the audited workbook."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import ksk_workbook as wb


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--file", required=True)
    p.add_argument("--preflight", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    source = {int(r["stt"]): r for r in wb.load_records(args.file)}
    preflight = json.loads(Path(args.preflight).read_text())
    jobs = []
    for item in preflight:
        if item.get("status") != "san_sang":
            continue
        stt = int(item["stt"])
        record = source[stt]
        jobs.append({"stt": stt, "phieukhamId": item["phieukhamId"],
                     "cdId": item["cdId"], "exam": item["exam"],
                     "adhd": record.get("adhd") or [],
                     "autism": record.get("autism") or []})
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(jobs, ensure_ascii=False))
    print(f"{len(jobs)} công việc")


if __name__ == "__main__":
    main()
