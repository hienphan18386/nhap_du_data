"""Write both mental-health questionnaires through the API.

Each tab is its own dynamic form sharing one tab_id: ADHD is form 1000278 / LoaiId 22,
autism is form 1000283 / LoaiId 23. Answer ids are per-questionnaire and the labels
repeat between sets ("Thỉnh thoảng" is 25 in one and 52 in another), so a single global
label table would silently pick the wrong id -- each tab keeps its own.

The evaluation date is the record's own exam date, never today's.
"""
import json, sys, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, '/Users/hienphantrong/Desktop/Project/AI_PROJECT/NHAP_DATA_LONG')
from app import ksk_workbook as wb
import medapi
from check_tamthan import ADHD, AUTISM, REPORT, read_rows

TABS = {
    "adhd": dict(form_id="1000278", loai=22, code="GiamChuY_6_18Tuoi", table=ADHD,
                 name="Câu hỏi sàng lọc rối loạn giảm chú ý - tăng động "
                      "(áp dụng cho trẻ từ 6 đến 18 tuổi)", key="adhd"),
    "autism": dict(form_id="1000283", loai=23, code="PhoTuKy_6_11Tuoi", table=AUTISM,
                   name="Câu hỏi sàng lọc rối loạn phổ tự kỷ "
                        "(áp dụng cho trẻ từ 6 đến 11 tuổi)", key="autism"),
}


def read_head(form_id, pid, cd):
    """The questionnaire's own header row (ID, NgayDanhGia, NguoiDanhGia, ...)."""
    r = medapi._curl(f"{medapi.BASE}/FormViewer/FormViewerDataByRecord"
                     f"?form_id={form_id}&SessionSiteId=130&record_id={pid}",
                     [{"Varible": "phieukhamId", "Value": str(pid)},
                      {"Varible": "cdId", "Value": str(cd)},
                      {"Varible": "recordid", "Value": str(pid)}])
    rows = (((r or {}).get("result") or {}).get("data") or {}).get("formData") or []
    return rows[0] if rows else {}


def write_tab(tab, r, pid, cd):
    """Fill one questionnaire. Returns (ok, problems)."""
    t = TABS[tab]
    answers = [wb.nfc(a or "") for a in (r.get(t["key"]) or [])]
    rows = read_rows(pid, cd, t["code"], t["form_id"])
    if not rows:
        return False, [f"{tab}: không đọc được bảng câu hỏi"]
    rows = sorted(rows, key=lambda x: int(x.get("stt") or 0))
    problems, out = [], []
    for i, row in enumerate(rows):
        text = answers[i] if i < len(answers) else ""
        val = row.get("GiaTri")
        if text:
            got = t["table"].get(text.lower().strip(" .:;"))
            if got is None:
                problems.append(f"{tab} câu {row.get('stt')}: {text!r} không có trong danh mục")
            else:
                val = str(got)
        out.append({"Id": row["Id"], "Code": row.get("Code"), "stt": row.get("stt"),
                    "NoiDungCauHoi": row.get("NoiDungCauHoi"), "GiaTri": val})

    head = read_head(t["form_id"], pid, cd)
    body = {"ID": head.get("ID"), "CongDanId": int(cd), "LoaiId": t["loai"],
            "NgayDanhGia": head.get("NgayDanhGia"), "NguoiDanhGia": head.get("NguoiDanhGia"),
            "KetQua": head.get("KetQua") or "", "GhiChu": head.get("GhiChu") or "",
            "NhomCauHoiName": t["name"], "DanhGiaTamThan_ChiTiet": out,
            "cdId": int(cd), "phieukhamId": str(pid), "MauKham": "mauphieukskd18",
            "recordid": int(pid),
            "TabOptions": json.dumps({"formId": t["form_id"], "NhomCauHoiCode": t["code"],
                                      "recordId": str(pid)}),
            "AttachmentFile": '{"upload":"","deleted":""}', "formdata_parent": None}
    res = medapi._curl(f"{medapi.BASE}/FormViewer/FormToDataBaseUpdate"
                       f"?form_id={t['form_id']}&tab_id=4166&record_id={pid}", body)
    ok = bool(res.get("success")) and bool((res.get("result") or {}).get("isSucceeded", True))
    return ok, problems
