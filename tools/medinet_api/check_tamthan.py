"""Compare both mental-health questionnaires against the workbook. Read-only.

Answer ids are per-questionnaire and the labels repeat across sets ("Thỉnh thoảng" is
25 in one and 52 in another), so each tab is mapped with its own table. Comparison
ignores case: the form writes "Thỉnh thoảng" where the workbook writes "thỉnh thoảng",
and an exact match silently blanks every such answer.
"""
import json, sys, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, '/Users/hienphantrong/Desktop/Project/AI_PROJECT/NHAP_DATA_LONG')
from app import ksk_workbook as wb
import medapi

REPORT = 1002346
ADHD = {"không có": 51, "thỉnh thoảng": 52, "thường xuyên": 53}
AUTISM = {"hoàn toàn đồng ý": 54, "có chút đồng ý": 55,
          "có chút không đồng ý": 56, "hoàn toàn không đồng ý": 57}
TABS = {"adhd": ("GiamChuY_6_18Tuoi", "1000278", ADHD),
        "autism": ("PhoTuKy_6_11Tuoi", "1000283", AUTISM)}


def read_rows(pid, cd, code, form_id):
    r = medapi._curl(f"{medapi.BASE}/DRViewer/PostData?id={REPORT}&SessionSiteId=130",
                     [{"Varible": "ReportId", "Value": REPORT},
                      {"Varible": "TabOptions", "Value": json.dumps(
                          {"formId": form_id, "NhomCauHoiCode": code, "recordId": str(pid)})},
                      {"Varible": "recordid", "Value": str(pid)},
                      {"Varible": "MauKham", "Value": "mauphieukskd18"},
                      {"Varible": "phieukhamId", "Value": str(pid)},
                      {"Varible": "cdId", "Value": str(cd)}])
    res = r.get("result")
    return res if isinstance(res, list) else (res or {}).get("data") or []


def check(r, pid, cd):
    bad = []
    for tab, key in (("adhd", "adhd"), ("autism", "autism")):
        code, form_id, table = TABS[tab]
        answers = [wb.nfc(a or "") for a in (r.get(key) or [])]
        rows = read_rows(pid, cd, code, form_id)
        if not rows:
            bad.append(f"{tab}: không đọc được bảng câu hỏi")
            continue
        rows = sorted(rows, key=lambda x: int(x.get("stt") or 0))
        if len([a for a in answers if a]) and len(rows) != len(answers):
            bad.append(f"{tab}: Excel có {len(answers)} câu, Medinet có {len(rows)}")
        for i, row in enumerate(rows):
            want_text = answers[i] if i < len(answers) else ""
            if not want_text:
                continue
            want = table.get(want_text.lower().strip(" .:;"))
            if want is None:
                bad.append(f"{tab} câu {row.get('stt')}: Excel ghi {want_text!r} không có trong danh mục")
                continue
            got = row.get("GiaTri")
            if str(got or "") != str(want):
                bad.append(f"{tab} câu {row.get('stt')}: lưu {got}, cần {want} ({want_text})")
    return bad
