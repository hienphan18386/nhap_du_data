"""Fill ADHD and autism questionnaires through Medinet's real Chrome form.

The dynamic-form API is not safe for these child rows: it can report success while
clearing every answer. This runner therefore uses the same visible form controls as a
human operator, then leaves exact readback to tools/medinet_api/import_all.py verify.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "medinet_api"))

from app import ksk_workbook as wb
from app.clinical import ClinicalFiller, FORM_TAM_THAN
from app.importer import AppleScriptImporter
from import_all import resolve_record


TAB_SPECS = {
    "adhd": (1, "adhd"),
    "autism": (2, "autism"),
}


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--file", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--tabs", choices=("both", "adhd", "autism"), default="both")
    p.add_argument("--from", dest="exam_from", default="01/07/2026")
    p.add_argument("--to", dest="exam_to", default="31/08/2026")
    p.add_argument("--start-at", type=int, default=1)
    p.add_argument("--limit", type=int)
    p.add_argument("--only-stt", type=int, action="append")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--verify-here", action="store_true")
    p.add_argument("--record-map",
                   help="Preflight JSON containing verified phieukhamId/cdId/exam by STT")
    p.add_argument("--tab-marker",
                   help="Use a pre-marked Chrome tab so independent workers do not collide")
    return p.parse_args()


def atomic_save(rows, path):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    temporary.replace(target)


def selected_tabs(option):
    return list(TAB_SPECS) if option == "both" else [option]


def main():
    args = parse_args()
    records = sorted(wb.load_records(args.file), key=lambda r: int(r["stt"]))
    if args.only_stt:
        keep = set(args.only_stt)
        records = [r for r in records if int(r["stt"]) in keep]
    else:
        records = records[args.start_at - 1:]
        if args.limit:
            records = records[:args.limit]

    output = Path(args.out)
    previous = json.loads(output.read_text()) if args.resume and output.exists() else []
    record_map = {}
    if args.record_map:
        mapped_rows = json.loads(Path(args.record_map).read_text())
        record_map = {int(x["stt"]): x for x in mapped_rows}
    completed = {int(x["stt"]) for x in previous if x.get("status") == "khop"}
    results = list(previous)
    tabs = selected_tabs(args.tabs)
    driver = AppleScriptImporter(dry_run=False, age_group="M2")
    if args.tab_marker:
        driver._tab_marker = args.tab_marker
    filler = ClinicalFiller(driver, args.exam_from, args.exam_to, dry_run=False)
    started = time.time()

    for index, record in enumerate(records, 1):
        stt = int(record["stt"])
        if stt in completed:
            continue
        t0 = time.time()
        mapped = record_map.get(stt)
        if mapped and mapped.get("phieukhamId") and mapped.get("cdId") and mapped.get("exam"):
            who = {"phieukhamId": str(mapped["phieukhamId"]),
                   "cdId": str(mapped["cdId"]), "exam": mapped["exam"]}
            lookup_error = None
        elif mapped:
            who, lookup_error = None, mapped.get("status") or "khong_tim_thay"
        else:
            who, lookup_error = resolve_record(record)
        row = {"stt": stt, "tabs": {}, "problems": []}
        if lookup_error:
            row["status"] = lookup_error
        else:
            exam = who.get("exam")
            for tab in tabs:
                sub_tab, source_key = TAB_SPECS[tab]
                answers = [a for a in (record.get(source_key) or [])]
                wanted = len([a for a in answers if wb.nfc(a)])
                tab_problems = []
                if not wanted:
                    tab_problems.append("file không có câu trả lời")
                else:
                    url = filler.section_url(FORM_TAM_THAN, who, sub_tab)
                    if not filler.goto(url, "DanhGiaTamThan_ChiTiet", timeout_s=120):
                        tab_problems.append("không mở được biểu mẫu")
                    else:
                        tab_problems += filler.fill_tam_than(record, answers, exam) or []
                        ok, messages = filler.save("Lưu")
                        if not ok:
                            tab_problems.append("lưu thất bại: " + "; ".join(messages))
                        if args.verify_here:
                            if filler.goto(url, "DanhGiaTamThan_ChiTiet", timeout_s=120):
                                tab_problems += filler.verify_tam_than(answers, exam) or []
                            else:
                                tab_problems.append("không mở lại được để đối chiếu")
                row["tabs"][tab] = "khop" if not tab_problems else "con_sai"
                row["problems"] += [f"[{tab}] {x}" for x in tab_problems]
            row["status"] = "khop" if not row["problems"] else "con_sai"

        row["seconds"] = round(time.time() - t0, 1)
        results = [x for x in results if int(x["stt"]) != stt] + [row]
        results.sort(key=lambda x: int(x["stt"]))
        atomic_save(results, output)
        first = f" -> {row['problems'][0]}" if row.get("problems") else ""
        print(f"[{index}/{len(records)}] TT{stt}: {row['status']} ({row['seconds']:.0f}s){first}",
              flush=True)

    counts = {}
    for row in results:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    print(f"\n===== UI tâm thần: {len(results)} hồ sơ | {counts} | "
          f"{(time.time() - started) / 60:.1f} phút", flush=True)


if __name__ == "__main__":
    main()
