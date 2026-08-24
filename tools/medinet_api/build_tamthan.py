"""Write both mental-health questionnaires through the API.

Each tab is its own dynamic form sharing one tab_id: ADHD is form 1000278 / LoaiId 22,
autism is form 1000283 / LoaiId 23. Answer ids are per-questionnaire and the labels
repeat between sets ("Thỉnh thoảng" is 25 in one and 52 in another), so a single global
label table would silently pick the wrong id -- each tab keeps its own.

The evaluation date is the record's own exam date, never today's.
"""
import datetime as dt
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


def api_date(value):
    """Keep the form's original slash-date representation."""
    if value in (None, ""):
        return value
    if isinstance(value, (dt.date, dt.datetime)):
        parsed = value.date() if isinstance(value, dt.datetime) else value
        return parsed.strftime("%d/%m/%Y")
    text = str(value).strip()
    try:
        dt.datetime.strptime(text, "%d/%m/%Y")
        return text
    except ValueError:
        pass
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).date().strftime("%d/%m/%Y")
    except ValueError:
        return text


def read_head(form_id, code, pid, cd):
    """The questionnaire's own header row (ID, NgayDanhGia, NguoiDanhGia, ...).

    TabOptions is required: without it the form viewer answers with a blank template
    -- ID null and NgayDanhGia set to now -- and posting that back makes the backend
    fail with "Object reference not set to an instance of an object." It also means a
    save would carry today's date instead of the record's own exam date.
    """
    r = medapi._curl(f"{medapi.BASE}/FormViewer/FormViewerDataByRecord"
                     f"?form_id={form_id}&SessionSiteId=130&record_id={pid}",
                     [{"Varible": "phieukhamId", "Value": str(pid)},
                      {"Varible": "cdId", "Value": str(cd)},
                      {"Varible": "recordid", "Value": str(pid)},
                      {"Varible": "MauKham", "Value": "mauphieukskd18"},
                      {"Varible": "TabOptions", "Value": json.dumps(
                          {"formId": form_id, "NhomCauHoiCode": code, "recordId": str(pid)})}])
    rows = (((r or {}).get("result") or {}).get("data") or {}).get("formData") or []
    return rows[0] if rows else {}


def write_tab(tab, r, pid, cd, exam_date=None):
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
        # `Id` is the question id; uppercase `ID` is the persisted detail-row id.
        # Medinet distinguishes an omitted ID (insert) from ID=null (clears detail),
        # so only existing detail rows may include the uppercase key.
        detail = {"Id": row["Id"], "Code": row.get("Code"), "stt": row.get("stt"),
                  "NoiDungCauHoi": row.get("NoiDungCauHoi"), "GiaTri": val}
        if row.get("ID") is not None:
            detail["ID"] = row["ID"]
        out.append(detail)

    head = read_head(t["form_id"], t["code"], pid, cd)
    body = {"ID": head.get("ID"), "CongDanId": int(cd), "LoaiId": t["loai"],
            # A new questionnaire header may default to today's date. The record lookup
            # is the authority for the examination date, so the generic runner passes it
            # explicitly; older callers keep the stored header date for compatibility.
            "NgayDanhGia": api_date(exam_date or head.get("NgayDanhGia")),
            "NguoiDanhGia": head.get("NguoiDanhGia"),
            "KetQua": head.get("KetQua") or "", "GhiChu": head.get("GhiChu") or "",
            # Types are load-bearing here: the backend wants the detail rows as a JSON
            # *string*, the ids as strings, and formdata_parent as the literal "null".
            # Sending a list, an int, or a real null makes it answer "Object reference
            # not set to an instance of an object."
            "NhomCauHoiName": t["name"],
            "DanhGiaTamThan_ChiTiet": json.dumps(out, ensure_ascii=False),
            "cdId": str(cd), "phieukhamId": str(pid), "MauKham": "mauphieukskd18",
            "recordid": str(pid),
            "TabOptions": json.dumps({"formId": t["form_id"], "NhomCauHoiCode": t["code"],
                                      "recordId": str(pid)}),
            "AttachmentFile": '{"upload":"","deleted":""}', "formdata_parent": "null"}
    res = medapi._curl(f"{medapi.BASE}/FormViewer/FormToDataBaseUpdate"
                       f"?form_id={t['form_id']}&tab_id=4166&record_id={pid}"
                       f"&SessionSiteId=130", body)
    result = res.get("result") or {}
    ok = bool(res.get("success")) and bool(result.get("isSucceeded"))
    if not ok:
        problems.append(f"{tab}: máy chủ từ chối -- {result.get('message')}")
    return ok, problems
