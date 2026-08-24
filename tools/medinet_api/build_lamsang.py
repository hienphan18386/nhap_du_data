"""Turn one workbook row into the Khám lâm sàng field set, and check it back.

Read-modify-write: start from what Medinet currently stores so untouched fields keep
their values, overlay only what the workbook says, and never invent a value.
"""
import json, sys, pathlib
sys.path.insert(0, '/Users/hienphantrong/Desktop/Project/AI_PROJECT/NHAP_DATA_LONG')
from app import ksk_workbook as wb
from app.clinical import NHI_KHOA, medinet_tooth_condition
import medapi

TOOTH_STATUS = {"bình thường": 191, "sâu": 192, "trám sâu lại": 193, "trám tốt": 194,
                "mất do sâu": 195, "mất lý do khác": 196, "bít hố rãnh": 197,
                "trụ, cầu,implant": 198, "chưa mọc": 220, "không ghi nhận": 221}


def num(v):
    """Excel number -> API number. The API takes real numbers; the comma is a UI thing."""
    if v is None or str(v).strip() == "":
        return None
    s = str(v).strip().replace(",", ".")
    try:
        f = float(s)
    except ValueError:
        return None
    return int(f) if f == int(f) else f


def block(r, key, cb_field, icd_field, out, problems):
    """One clinical block: normal tick, or ICD codes."""
    text = wb.nfc(r.get(key) or "")
    if not text:
        return
    if wb.is_no_finding(text):
        out[cb_field] = True
        out[icd_field] = None
        return
    codes = wb.icd_codes(text)
    if not codes:
        problems.append(f"{key}: không đọc được mã ICD trong {text!r}")
        return
    ids = []
    for c in codes:
        i = medapi.icd_id(c)
        if i is None:
            problems.append(f"{key}: chưa có id cho mã {c}")
        else:
            ids.append(str(i))
    if ids:
        out[cb_field] = False
        out[icd_field] = ",".join(ids)


def build(r, current):
    out = dict(current)
    problems = []
    for key, cb, icd in NHI_KHOA:
        block(r, key, cb, icd, out, problems)
    block(r, "mat_benh", "Mat_ChuaPhatHienBatThuong", "Mat_ChanDoanSoBo_ICD", out, problems)
    block(r, "tmh_benh", "TMH_ChuaPhatHienBatThuong", "TMH_ChanDoanSoBo_ICD", out, problems)
    block(r, "rhm_benh", "RHM_ChuaPhatHienBatThuong", "RHM_ChanDoanSoBo_ICD", out, problems)

    for field, key in (("Mat_KhongKinh_MP", "mat_khong_kinh_mp"),
                       ("Mat_KhongKinh_MT", "mat_khong_kinh_mt"),
                       ("Mat_CoKinh_MP", "mat_co_kinh_mp"),
                       ("Mat_CoKinh_MT", "mat_co_kinh_mt")):
        v = wb.vision_score(r.get(key))
        if v is not None:
            out[field] = num(v)
    for field, key in (("TMH_TaiTrai_NoiThuong", "tai_trai_noi_thuong"),
                       ("TMH_TaiTrai_NoiTham", "tai_trai_noi_tham"),
                       ("TMH_TaiPhai_NoiThuong", "tai_phai_noi_thuong"),
                       ("TMH_TaiPhai_NoiTham", "tai_phai_noi_tham")):
        v = num(r.get(key))
        if v is not None:
            out[field] = v

    # Free text "Khám lâm sàng khác". The Get store does not return this field, so it
    # cannot be read back through the API -- it is written exactly as the UI writes it
    # (raw workbook text) and has to be confirmed in the page itself.
    khac = wb.nfc(r.get("kham_lam_sang_khac") or "")
    if khac:
        out["KhamLamSangKhac"] = khac

    # Teeth: the stored value is a list of {toothNumber, statusId, statusName}. Only the
    # teeth the workbook names are touched; every other tooth keeps what Medinet holds.
    cond = medinet_tooth_condition(r.get("tinh_trang_rang"))
    teeth = wb.tooth_numbers(r.get("cac_rang_sau"))
    if cond and teeth and cond.lower() not in ("bình thường", "binh thuong"):
        sid = TOOTH_STATUS.get(cond.lower())
        if sid is None:
            problems.append(f"tình trạng răng {cond!r} không có mã")
        else:
            try:
                chart = json.loads(current.get("KhamRangJSON") or "[]")
            except ValueError:
                chart = []
            by = {int(t["toothNumber"]): t for t in chart if isinstance(t, dict)}
            for t in teeth:
                n = int(t)
                if n in by:
                    by[n]["statusId"] = sid
                    by[n]["statusName"] = cond
                else:
                    # The stored chart holds only the teeth Medinet has a record for --
                    # TT7's had 23 of 32 -- so a tooth the workbook names may simply not
                    # be there yet. Adding it is what clicking that tooth in the chart
                    # does; refusing would drop a real finding.
                    by[n] = {"toothNumber": n, "statusId": sid, "statusName": cond}
            out["KhamRangJSON"] = json.dumps(
                sorted(by.values(), key=lambda x: int(x["toothNumber"])), ensure_ascii=False)
    return out, problems


def check(r, stored):
    """Compare what Medinet now holds against the workbook. Returns mismatches."""
    bad = []

    def want_icd(key):
        text = wb.nfc(r.get(key) or "")
        if not text:
            return None
        if wb.is_no_finding(text):
            return "NORMAL"
        return sorted(str(medapi.icd_id(c)) for c in wb.icd_codes(text) if medapi.icd_id(c))

    for key, cb, icd in list(NHI_KHOA) + [
            ("mat_benh", "Mat_ChuaPhatHienBatThuong", "Mat_ChanDoanSoBo_ICD"),
            ("tmh_benh", "TMH_ChuaPhatHienBatThuong", "TMH_ChanDoanSoBo_ICD"),
            ("rhm_benh", "RHM_ChuaPhatHienBatThuong", "RHM_ChanDoanSoBo_ICD")]:
        w = want_icd(key)
        if w is None:
            continue
        if w == "NORMAL":
            if not stored.get(cb):
                bad.append(f"{key}: chưa tích 'chưa phát hiện bất thường'")
        else:
            got = sorted(str(x) for x in str(stored.get(icd) or "").split(",") if x.strip())
            if got != w:
                bad.append(f"{key}: ICD lưu {got or 'trống'}, cần {w}")

    for field, key in (("Mat_KhongKinh_MP", "mat_khong_kinh_mp"),
                       ("Mat_KhongKinh_MT", "mat_khong_kinh_mt"),
                       ("Mat_CoKinh_MP", "mat_co_kinh_mp"),
                       ("Mat_CoKinh_MT", "mat_co_kinh_mt"),
                       ("TMH_TaiTrai_NoiThuong", "tai_trai_noi_thuong"),
                       ("TMH_TaiTrai_NoiTham", "tai_trai_noi_tham"),
                       ("TMH_TaiPhai_NoiThuong", "tai_phai_noi_thuong"),
                       ("TMH_TaiPhai_NoiTham", "tai_phai_noi_tham")):
        w = num(wb.vision_score(r.get(key)) if field.startswith("Mat_") else r.get(key))
        if w is None:
            continue
        g = num(stored.get(field))
        if g != w:
            bad.append(f"{field}: lưu {g!r}, cần {w!r}")

    cond = medinet_tooth_condition(r.get("tinh_trang_rang"))
    teeth = wb.tooth_numbers(r.get("cac_rang_sau"))
    if cond and teeth and cond.lower() not in ("bình thường", "binh thuong"):
        try:
            chart = json.loads(stored.get("KhamRangJSON") or "[]")
        except ValueError:
            chart = []
        by = {int(t["toothNumber"]): t for t in chart if isinstance(t, dict)}
        for t in teeth:
            got = (by.get(int(t)) or {}).get("statusName")
            if wb.nfc(got or "").lower() != cond.lower():
                bad.append(f"răng {t}: lưu {got!r}, cần {cond!r}")
    return bad
