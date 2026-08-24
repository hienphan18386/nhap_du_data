"""Read-only validation for a clinical KSK workbook before API import."""
import argparse
import collections
import json
import pathlib
import sys
import warnings

warnings.filterwarnings("ignore")
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app import ksk_workbook as wb
from app.clinical import medinet_san_khoa, medinet_tooth_condition
import build_lamsang as bl
import build_tiensu as bt
from check_tamthan import ADHD, AUTISM
import medapi


def args_parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("file")
    p.add_argument("--out")
    return p.parse_args()


def present(value):
    return wb.nfc(value or "") != ""


def issue(items, level, record, field, message):
    items.append({"level": level, "row": record.get("row"),
                  "stt": record.get("stt"), "field": field, "message": message})


def main():
    args = args_parser()
    records = sorted(wb.load_records(args.file), key=lambda r: int(r["stt"]))
    issues = []

    stt_counts = collections.Counter(int(r["stt"]) for r in records)
    cccd_counts = collections.Counter(r["cccd"] for r in records)
    expected_stt = list(range(1, len(records) + 1))
    actual_stt = [int(r["stt"]) for r in records]

    if actual_stt != expected_stt:
        issues.append({"level": "error", "field": "stt",
                       "message": "STT không liên tục từ 1 đến số hồ sơ"})
    for r in records:
        stt = int(r["stt"])
        if stt_counts[stt] > 1:
            issue(issues, "error", r, "stt", f"STT {stt} bị lặp")
        if cccd_counts[r["cccd"]] > 1:
            issue(issues, "error", r, "cccd", "CCCD bị lặp trong file")
        if not (r["cccd"].isdigit() and len(r["cccd"]) == 12):
            issue(issues, "error", r, "cccd", "CCCD không đủ đúng 12 chữ số")
        if not present(r.get("name")):
            issue(issues, "error", r, "name", "Họ tên trống")

        for tab, key, table, wanted_len in (
                ("ADHD", "adhd", ADHD, 18),
                ("Phổ tự kỷ", "autism", AUTISM, 10)):
            answers = [wb.nfc(x or "") for x in (r.get(key) or [])]
            if key == "autism" and not r.get("autism_available"):
                continue
            if len(answers) != wanted_len or any(not x for x in answers):
                issue(issues, "error", r, key,
                      f"{tab} phải có đủ {wanted_len} câu trả lời")
            for pos, answer in enumerate(answers, 1):
                if answer and answer.lower().strip(" .:;") not in table:
                    issue(issues, "error", r, key,
                          f"{tab} câu {pos}: {answer!r} không có trong danh mục API")

        sk = medinet_san_khoa(r.get("ts_san_khoa"))
        if present(r.get("ts_san_khoa")) and (not sk or sk.lower() not in bt.SAN_KHOA):
            issue(issues, "error", r, "ts_san_khoa",
                  f"Giá trị {r.get('ts_san_khoa')!r} không có trong danh mục")
        if present(r.get("ts_tiem_chung")) and bt.vac_id(r) is None:
            issue(issues, "error", r, "ts_tiem_chung",
                  f"Giá trị {r.get('ts_tiem_chung')!r} không có trong danh mục")

        for field, key in bt.MEASURES:
            value = r.get(key)
            if present(value) and bt.num(value) is None:
                issue(issues, "error", r, key, f"Không đọc được số {value!r}")

        _, clinical_problems = bl.build(r, {})
        for message in clinical_problems:
            issue(issues, "error", r, "kham_lam_sang", message)

        condition = medinet_tooth_condition(r.get("tinh_trang_rang"))
        teeth = wb.tooth_numbers(r.get("cac_rang_sau"))
        if teeth and (not condition or condition.lower() not in bl.TOOTH_STATUS):
            issue(issues, "error", r, "tinh_trang_rang",
                  f"Có răng {teeth} nhưng tình trạng {condition!r} chưa có mã API")

        for key in ("tuan_hoan", "ho_hap", "tieu_hoa", "than_tiet_nieu",
                    "than_kinh", "tam_than", "mat_benh", "tmh_benh", "rhm_benh"):
            text = wb.nfc(r.get(key) or "")
            if text and not wb.is_no_finding(text):
                codes = wb.icd_codes(text)
                if not codes:
                    issue(issues, "error", r, key,
                          f"Không đọc được mã ICD trong {text!r}")
                for code in codes:
                    if medapi.icd_id(code) is None:
                        issue(issues, "error", r, key, f"Chưa có id API cho ICD {code}")

    answer_counts = {
        "adhd": collections.Counter(
            wb.nfc(x or "") for r in records for x in (r.get("adhd") or [])),
        "autism": collections.Counter(
            wb.nfc(x or "") for r in records for x in (r.get("autism") or [])),
    }
    summary = {
        "file": str(pathlib.Path(args.file).resolve()),
        "records": len(records),
        "stt_min": min(actual_stt) if actual_stt else None,
        "stt_max": max(actual_stt) if actual_stt else None,
        "autism_available": all(r.get("autism_available") for r in records),
        "answer_counts": {k: dict(v) for k, v in answer_counts.items()},
        "errors": sum(x["level"] == "error" for x in issues),
        "warnings": sum(x["level"] == "warning" for x in issues),
        "issues": issues,
    }
    rendered = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.out:
        pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(args.out).write_text(rendered)
    print(rendered)
    raise SystemExit(1 if summary["errors"] else 0)


if __name__ == "__main__":
    main()
