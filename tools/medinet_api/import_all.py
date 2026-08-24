"""Safe end-to-end Medinet API importer for one clinical KSK workbook.

The write order is fixed: Tiền sử -> Tâm thần -> Khám lâm sàng -> Kết luận. Every
record is read back only after all writes, so cross-section side effects are caught.
"""
import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys
import time
import unicodedata
import uuid
import warnings

warnings.filterwarnings("ignore")
ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app import ksk_workbook as wb
import build_ketluan as bk
import build_lamsang as bl
import build_tamthan as bm
import build_tiensu as bt
import check_tamthan as ct
import medapi


def normalized_date(value):
    """Return a date for the Medinet ISO timestamp or workbook dd/mm/yyyy value."""
    if value in (None, ""):
        return None
    if isinstance(value, (dt.date, dt.datetime)):
        return value.date() if isinstance(value, dt.datetime) else value
    text = str(value).strip()
    for parser in (
        lambda x: dt.datetime.fromisoformat(x.replace("Z", "+00:00")).date(),
        lambda x: dt.datetime.strptime(x, "%d/%m/%Y").date(),
        lambda x: dt.datetime.strptime(x, "%Y-%m-%d").date(),
    ):
        try:
            return parser(text)
        except ValueError:
            pass
    return None


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--file", required=True)
    p.add_argument("--mode", choices=("preflight", "import", "verify"), required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--only-stt", type=int, action="append")
    p.add_argument("--start-at", type=int, default=1)
    p.add_argument("--limit", type=int)
    p.add_argument("--resume", action="store_true",
                   help="Skip STTs already marked khop in the output JSON")
    p.add_argument("--skip-mental", action="store_true",
                   help="Do not write or verify ADHD/autism (use the browser UI flow instead)")
    return p.parse_args()


def fold(value):
    text = unicodedata.normalize("NFKD", wb.nfc(value)).lower()
    return " ".join("".join(ch for ch in text if not unicodedata.combining(ch)).split())


def guarded(fn, *args, **kwargs):
    for _ in range(2):
        try:
            return fn(*args, **kwargs)
        except medapi.Unauthorized:
            print("      phiên hết hạn -- đang lấy lại token...", flush=True)
            if not medapi.refresh_token():
                raise SystemExit("KHÔNG LẤY LẠI ĐƯỢC TOKEN -- dừng để tránh ghi nhận sai")
    raise SystemExit("XÁC THỰC MEDINET THẤT BẠI HAI LẦN -- dừng")


def atomic_save(rows, path):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    temp.replace(path)


def source_audit(file_path):
    process = subprocess.run(
        [sys.executable, str(HERE / "audit_source.py"), file_path],
        capture_output=True, text=True)
    try:
        report = json.loads(process.stdout)
    except json.JSONDecodeError:
        raise SystemExit("Không đọc được kết quả kiểm tra file nguồn")
    if process.returncode or report.get("errors"):
        raise SystemExit(f"File nguồn còn {report.get('errors')} lỗi -- dừng trước khi gọi API")
    return report


def select_records(file_path, only_stt, start_at, limit):
    records = sorted(wb.load_records(file_path), key=lambda r: int(r["stt"]))
    if only_stt:
        wanted = set(only_stt)
        records = [r for r in records if int(r["stt"]) in wanted]
        found = {int(r["stt"]) for r in records}
        if found != wanted:
            raise SystemExit(f"Không tìm thấy STT: {sorted(wanted - found)}")
    else:
        records = records[start_at - 1:]
        if limit:
            records = records[:limit]
    return records


def resolve_record(r):
    candidates = guarded(medapi.find_records, r["cccd"])
    exact = [x for x in candidates if fold(x.get("name")) == fold(r.get("name"))]
    if not candidates:
        return None, "khong_tim_thay"
    if len(exact) != 1:
        return None, "ten_khong_khop" if not exact else "nhieu_ho_so_trung"
    if not exact[0].get("exam"):
        return None, "thieu_ngay_kham"
    return exact[0], None


def scaffold(guid_field, pid, cd, include_recordid=False):
    out = {guid_field: str(uuid.uuid4()), "phieukhamId": pid, "cdId": cd,
           "MauKham": "mauphieukskd18", "AttachmentFile": '{"upload":"","deleted":""}',
           "nav_selected_items": "{}", "labelactioncode": "SAVE", "formdata_parent": "null"}
    if include_recordid:
        out["recordid"] = pid
    return out


def mental_tabs(r):
    tabs = ["adhd"]
    if r.get("autism_available"):
        tabs.append("autism")
    return tabs


def preflight_one(r):
    who, error = resolve_record(r)
    if error:
        return {"stt": int(r["stt"]), "status": error}
    pid, cd = who["phieukhamId"], who["cdId"]
    problems = []
    expected = {"adhd": 18, "autism": 10}
    for tab in mental_tabs(r):
        cfg = bm.TABS[tab]
        rows = guarded(ct.read_rows, pid, cd, cfg["code"], cfg["form_id"])
        if len(rows) != expected[tab]:
            problems.append(f"{tab}: Medinet có {len(rows)} câu, cần {expected[tab]}")
    return {"stt": int(r["stt"]), "phieukhamId": pid, "cdId": cd,
            "exam": who.get("exam"), "problems": problems,
            "status": "san_sang" if not problems else "form_khong_khop"}


def verify_one(r, who, include_mental=True):
    pid, cd = who["phieukhamId"], who["cdId"]
    problems, warnings_out = [], []
    ts = guarded(medapi.read_form, 1000103, pid, cd)
    vaccines = guarded(bt.read_vaccines, pid, cd)
    ls = guarded(medapi.read, "lam_sang", pid, cd)
    kl = guarded(medapi.read, "ket_luan", pid, cd)
    problems += [f"[Tiền sử] {x}" for x in bt.check(r, ts, vaccines)]
    problems += [f"[Khám lâm sàng] {x}" for x in bl.check(r, ls)]
    problems += [f"[Kết luận] {x}" for x in bk.check(r, kl)]

    for tab in (mental_tabs(r) if include_mental else ()):
        cfg = bm.TABS[tab]
        answers = [wb.nfc(x or "") for x in (r.get(cfg["key"]) or [])]
        rows = guarded(ct.read_rows, pid, cd, cfg["code"], cfg["form_id"])
        head = guarded(bm.read_head, cfg["form_id"], cfg["code"], pid, cd)
        if not head.get("ID"):
            problems.append(f"[Tâm thần/{tab}] chưa có phiếu đánh giá đã lưu")
        wanted_date = normalized_date(who.get("exam"))
        stored_date = normalized_date(head.get("NgayDanhGia"))
        if stored_date != wanted_date:
            problems.append(
                f"[Tâm thần/{tab}] ngày đánh giá lưu {head.get('NgayDanhGia')!r}, "
                f"cần {who.get('exam')!r}")
        rows = sorted(rows, key=lambda x: int(x.get("stt") or 0))
        if len(rows) != len(answers):
            problems.append(f"[Tâm thần/{tab}] Medinet có {len(rows)} câu, Excel có {len(answers)}")
            continue
        for index, row in enumerate(rows):
            answer = answers[index]
            wanted = cfg["table"].get(answer.lower().strip(" .:;"))
            if wanted is None or str(row.get("GiaTri") or "") != str(wanted):
                problems.append(
                    f"[Tâm thần/{tab}] câu {row.get('stt')}: lưu {row.get('GiaTri')}, cần {wanted}")

    other = wb.nfc(r.get("kham_lam_sang_khac") or "")
    if other:
        ls_form = guarded(medapi.read_form, 1000104, pid, cd)
        if "KhamLamSangKhac" in ls_form:
            got = wb.nfc(ls_form.get("KhamLamSangKhac") or "")
            if fold(got) != fold(other):
                problems.append(f"[Khám lâm sàng] mục khác lưu {got!r}, cần {other!r}")
        else:
            warnings_out.append("Không có trường đọc ngược KhamLamSangKhac trong API")
    return problems, warnings_out


def import_one(r, who, include_mental=True):
    pid, cd, exam = who["phieukhamId"], who["cdId"], who["exam"]
    writes, build_problems = {}, []

    current_ts = guarded(medapi.read_form, 1000103, pid, cd)
    vaccines = guarded(bt.read_vaccines, pid, cd)
    values, notes = bt.build(r, current_ts, vaccines)
    blocking = [x for x in notes if not x.startswith("ghi chú:")]
    build_problems += blocking
    values.update(scaffold("KSKD18_TTHC_TienSu_guid", pid, cd, include_recordid=True))
    writes["tien_su"] = guarded(medapi.write, "tien_su", pid, cd, values)

    for tab in (mental_tabs(r) if include_mental else ()):
        ok, problems = guarded(bm.write_tab, tab, r, pid, cd, exam)
        writes[tab] = {"ok": ok}
        build_problems += problems

    current_ls = guarded(medapi.read, "lam_sang", pid, cd)
    values, problems = bl.build(r, current_ls)
    build_problems += problems
    values.update(scaffold("KSKD18_ThongTinKham_guid", pid, cd))
    writes["lam_sang"] = guarded(medapi.write, "lam_sang", pid, cd, values)

    # Read Kết luận only after Khám lâm sàng has been stored so Medinet has already
    # recomputed the read-only diagnosis summary that drives the recommendation.
    current_kl = guarded(medapi.read, "ket_luan", pid, cd)
    values, problems = bk.build(r, current_kl)
    build_problems += problems
    values.update(scaffold("KSKD18_KetLuanKham_guid", pid, cd))
    writes["ket_luan"] = guarded(medapi.write, "ket_luan", pid, cd, values)

    write_failures = [name for name, verdict in writes.items() if not verdict.get("ok")]
    stored_problems, warnings_out = verify_one(r, who, include_mental=include_mental)
    all_problems = build_problems + [f"API từ chối mục {x}" for x in write_failures] + stored_problems
    return writes, all_problems, warnings_out


def main():
    args = parse_args()
    audit = source_audit(args.file)
    records = select_records(args.file, args.only_stt, args.start_at, args.limit)
    output_path = pathlib.Path(args.out)
    previous = []
    if args.resume and output_path.exists():
        previous = json.loads(output_path.read_text())
    completed = {int(x["stt"]) for x in previous if x.get("status") in ("khop", "san_sang")}
    results = list(previous)
    started = time.time()

    for index, r in enumerate(records, 1):
        stt = int(r["stt"])
        if stt in completed:
            continue
        t0 = time.time()
        if args.mode == "preflight":
            row = preflight_one(r)
        else:
            who, error = resolve_record(r)
            if error:
                row = {"stt": stt, "status": error}
            elif args.mode == "verify":
                problems, warnings_out = verify_one(r, who, include_mental=not args.skip_mental)
                row = {"stt": stt, "exam": who.get("exam"), "problems": problems,
                       "warnings": warnings_out, "status": "khop" if not problems else "con_sai"}
            else:
                writes, problems, warnings_out = import_one(
                    r, who, include_mental=not args.skip_mental)
                row = {"stt": stt, "exam": who.get("exam"), "writes": writes,
                       "problems": problems, "warnings": warnings_out,
                       "status": "khop" if not problems else "con_sai"}
        row["seconds"] = round(time.time() - t0, 2)
        results = [x for x in results if int(x["stt"]) != stt] + [row]
        results.sort(key=lambda x: int(x["stt"]))
        atomic_save(results, output_path)
        print(f"[{index}/{len(records)}] TT{stt}: {row['status']} ({row['seconds']:.1f}s)"
              + (f" -> {row.get('problems', [''])[0]}" if row.get("problems") else ""),
              flush=True)

    counts = {}
    for row in results:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    print(f"\n===== {args.mode}: {len(results)} hồ sơ | {counts} | "
          f"{(time.time() - started) / 60:.1f} phút | nguồn {audit['records']} hồ sơ")


if __name__ == "__main__":
    main()
