"""Fill only the ADHD questionnaire, through the form, for a whole workbook.

The API can write the other four sections but not this one: FormToDataBaseUpdate
accepts the request and answers "Lưu dữ liệu thành công" while the answers stay empty,
because they live in a child table those endpoints do not touch. So this tab keeps
going through the page, and only this tab -- running the full clinical flow for a
section that is already correct would cost hours for nothing.

Each student is filled, saved, then the page is reloaded and read back: a save here
gives no signal of its own, and the questionnaire's rows stream in after the form
paints, so an unverified "saved" means very little.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

sys.path.insert(0, str(Path(__file__).resolve().parent / "medinet_api"))

from app import ksk_workbook as wb
from app.clinical import ClinicalFiller, FORM_TAM_THAN
from app.importer import AppleScriptImporter
import medapi


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--file", required=True)
    p.add_argument("--from", dest="exam_from", default="01/07/2026")
    p.add_argument("--to", dest="exam_to", default="31/08/2026")
    p.add_argument("--start-at", type=int, default=1, help="bắt đầu từ hồ sơ thứ N")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--only-stt", type=int, action="append")
    p.add_argument("--out", default="adhd_ui_results.json")
    p.add_argument("--verify-here", action="store_true",
                   help="Nạp lại trang đối chiếu ngay sau mỗi em. Mặc định KHÔNG, vì "
                        "đối chiếu qua API ở cuối vừa nhanh hơn nhiều vừa độc lập hơn.")
    return p.parse_args()


def lookup(cccd, tries=2):
    """Record ids and exam date, renewing the session when it has expired."""
    for attempt in range(tries):
        try:
            return medapi.find_record(cccd)
        except medapi.Unauthorized:
            print("      phiên hết hạn -- đang lấy lại token...", flush=True)
            if not medapi.refresh_token():
                return None
    return None


def save(rows, path):
    Path(path).write_text(json.dumps(rows, ensure_ascii=False, indent=1))


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

    driver = AppleScriptImporter(dry_run=False, age_group="M2")
    filler = ClinicalFiller(driver, args.exam_from, args.exam_to, dry_run=False)
    out, started = [], time.time()

    for i, r in enumerate(records, 1):
        stt = int(r["stt"])
        answers = [a for a in (r.get("adhd") or [])]
        wanted = len([a for a in answers if wb.nfc(a)])
        head = f"[{i}/{len(records)}] TT{stt} {r['name']}"
        if not wanted:
            out.append({"stt": stt, "status": "khong_co_du_lieu"})
            print(f"{head}: file không có câu trả lời -- bỏ qua", flush=True)
            save(out, args.out)
            continue

        t0 = time.time()
        # Look the record up through the standalone client, not ClinicalFiller's
        # api_lookup: that one reads whatever token the page happened to leak and
        # returns None once it expires, so a run turns into a wall of "KHÔNG TÌM THẤY"
        # and writes off students who are plainly there. This client raises on an
        # expired session and can go and fetch a fresh token.
        ids = lookup(r["cccd"])
        if not ids:
            out.append({"stt": stt, "name": r["name"], "status": "tra_that_bai"})
            print(f"{head}: KHÔNG TRA ĐƯỢC HỒ SƠ -- cần chạy lại", flush=True)
            save(out, args.out)
            continue
        exam = ids.get("exam")
        if not exam:
            out.append({"stt": stt, "name": r["name"], "status": "khong_co_ngay_kham"})
            print(f"{head}: hồ sơ chưa có ngày khám -- bỏ qua", flush=True)
            save(out, args.out)
            continue

        url = filler.section_url(FORM_TAM_THAN, ids, 1)
        if not filler.goto(url, "DanhGiaTamThan_ChiTiet"):
            out.append({"stt": stt, "name": r["name"], "status": "khong_mo_duoc"})
            print(f"{head}: không mở được form", flush=True)
            save(out, args.out)
            continue

        problems = filler.fill_tam_than(r, answers, exam) or []
        ok, messages = filler.save("Lưu")

        # Reading it back here costs about half the time per student and is itself a
        # source of false failures -- a reload that does not come back reports a save
        # that worked as broken, and leaves the grid in a state the next student has to
        # recover from. The same check runs over every student through the API
        # afterwards in minutes, and being separate from the write makes it stronger
        # evidence, not weaker. Kept behind a flag for when one student is being chased.
        left = []
        if args.verify_here:
            if filler.goto(url, "DanhGiaTamThan_ChiTiet"):
                left = filler.verify_tam_than(answers, exam) or []
            else:
                left = ["không mở lại được để đối chiếu"]
        if not ok:
            left.append("báo lỗi khi lưu: " + "; ".join(messages))

        status = "khop" if not left else "con_sai"   # "khop" here = đã lưu, chưa đối chiếu
        out.append({"stt": stt, "name": r["name"], "cccd": r["cccd"],
                    "exam": exam, "problems": problems, "sai": left,
                    "status": status, "seconds": round(time.time() - t0, 1)})
        print(f"{head}: {'OK ' if status == 'khop' else 'SAI'} "
              f"({time.time() - t0:.0f}s)" + ("  -> " + "; ".join(left[:2]) if left else ""),
              flush=True)
        save(out, args.out)

    done = sum(1 for x in out if x.get("status") == "khop")
    print(f"\n===== {len(out)} hồ sơ trong {(time.time()-started)/60:.0f} phút "
          f"| khớp: {done} | còn sai: {sum(1 for x in out if x.get('status')=='con_sai')}",
          flush=True)


if __name__ == "__main__":
    main()
