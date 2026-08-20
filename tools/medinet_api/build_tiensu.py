"""Tiền sử bản thân: history answers, the vaccination schedule, and khám thể lực.

The vaccination table is a child report, not a form field: it is read through report
1002141 and written back inside KSKD18_TiemChung_Json. Writing it as data is what
removes the 38 individual radio clicks the UI needed -- and with them the pass that
kept timing out and leaving doses unset.
"""
import json, sys, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, '/Users/hienphantrong/Desktop/Project/AI_PROJECT/NHAP_DATA_LONG')
from app import ksk_workbook as wb
# Reuse the project's own reading of a workbook answer instead of restating it here.
# A second implementation drifted immediately: is_no_finding() is for clinical cells
# ("Chưa phát hiện bất thường") and answers False to a plain "Không", so a history of
# "Không" was written as "Có" -- and the check, sharing the same mistake, called it
# correct. Interpretation lives in one place.
from app.clinical import is_no, medinet_san_khoa, NOTE_PREFIX
import medapi

VAC_REPORT = 1002141
VAC_STATUS = {"đã tiêm": 102, "chưa tiêm": 103, "không nhớ rõ": 104}
SAN_KHOA = {"bình thường": 5154, "không bình thường": 5155}
CO_KHONG = {"có": 264, "không": 265}
MEASURES = (("TheLuc_ChieuCao", "chieu_cao"), ("TheLuc_CanNang", "can_nang"),
            ("TheLuc_Mach", "mach"), ("TheLuc_HuyetApTamThu", "huyet_ap_tt"),
            ("TheLuc_HuyetApTamTruong", "huyet_ap_ttr"), ("NhipTho", "nhip_tho"))


def num(v):
    if v is None or str(v).strip() == "":
        return None
    try:
        f = float(str(v).strip().replace(",", "."))
    except ValueError:
        return None
    return int(f) if f == int(f) else f


def read_vaccines(pid, cd):
    r = medapi._curl(f"{medapi.BASE}/DRViewer/PostData?id={VAC_REPORT}&SessionSiteId=130",
                     [{"Varible": "ReportId", "Value": VAC_REPORT},
                      {"Varible": "recordid", "Value": int(pid)},
                      {"Varible": "MauKham", "Value": "mauphieukskd18"},
                      {"Varible": "phieukhamId", "Value": str(pid)},
                      {"Varible": "cdId", "Value": str(cd)}])
    res = r.get("result")
    return res if isinstance(res, list) else (res or {}).get("data") or []


def vac_id(r):
    t = wb.nfc(r.get("ts_tiem_chung") or "").lower()
    return VAC_STATUS.get(t)


def build(r, current, vaccines):
    out = dict(current)
    problems = []

    sk = medinet_san_khoa(r.get("ts_san_khoa"))
    if sk:
        if sk.lower() in SAN_KHOA:
            out["TS_BanThan_SanKhoa"] = SAN_KHOA[sk.lower()]
        else:
            problems.append(f"sản khoa {sk!r} không có trong danh mục")

    bt = wb.nfc(r.get("ts_benh_tat") or "")
    if bt:
        # Anything that is not a negative answer counts as "Có"; the wording itself has
        # no box on this form, so it is reported rather than dropped silently.
        out["TS_BanThan_MacBenh"] = CO_KHONG["không"] if is_no(bt) else CO_KHONG["có"]
        if not is_no(bt) and bt.lower() not in ("có", "co"):
            problems.append(note_only_yes_no(bt))

    dt = wb.nfc(r.get("ts_dang_dieu_tri") or "")
    if dt:
        out["TS_BanThan_DangDieuTriBenh"] = dt

    for field, key in MEASURES:
        v = num(r.get(key))
        if v is not None:
            out[field] = v

    vid = vac_id(r)
    if wb.nfc(r.get("ts_tiem_chung") or "") and vid is None:
        problems.append(f"tiêm chủng {r.get('ts_tiem_chung')!r} không có trong danh mục")
    elif vid is not None:
        rows = [dict(x) for x in vaccines]
        for x in rows:
            x["TinhTrangTiemId"] = vid
        out["KSKD18_TiemChung_Json"] = json.dumps(rows, ensure_ascii=False)
    return out, problems


def note_only_yes_no(text):
    return NOTE_PREFIX + (f"tiền sử bệnh ghi {text!r} -- form chỉ có Có/Không nên đã chọn "
                          f"'Có'; phần chữ này không có ô để nhập")


def check(r, stored, vaccines):
    bad = []
    sk = (medinet_san_khoa(r.get("ts_san_khoa")) or "").lower()
    if sk in SAN_KHOA and int(stored.get("TS_BanThan_SanKhoa") or 0) != SAN_KHOA[sk]:
        bad.append(f"sản khoa: lưu {stored.get('TS_BanThan_SanKhoa')}, cần {SAN_KHOA[sk]}")

    bt = wb.nfc(r.get("ts_benh_tat") or "")
    if bt:
        want = CO_KHONG["không"] if is_no(bt) else CO_KHONG["có"]
        if int(stored.get("TS_BanThan_MacBenh") or 0) != want:
            bad.append(f"tiền sử bệnh: lưu {stored.get('TS_BanThan_MacBenh')}, cần {want}")

    dt = wb.nfc(r.get("ts_dang_dieu_tri") or "")
    if dt and wb.nfc(stored.get("TS_BanThan_DangDieuTriBenh") or "").lower() != dt.lower():
        bad.append(f"đang điều trị: lưu {stored.get('TS_BanThan_DangDieuTriBenh')!r}, cần {dt!r}")

    for field, key in MEASURES:
        w = num(r.get(key))
        if w is None:
            continue
        g = num(stored.get(field))
        if g != w:
            bad.append(f"{field}: lưu {g!r}, cần {w!r}")

    vid = vac_id(r)
    if vid is not None:
        wrong = [x for x in vaccines if x.get("TinhTrangTiemId") != vid]
        if wrong:
            bad.append(f"tiêm chủng: {len(wrong)}/{len(vaccines)} dòng chưa đúng")
    return bad
