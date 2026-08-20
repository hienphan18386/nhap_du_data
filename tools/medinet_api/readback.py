"""Print what Medinet stores next to what the workbook says, in words.

The field-by-field check shares its interpretation with the builder, so it can only
catch data that failed to travel -- not data that was understood wrongly. A history of
"Không" was written as "Có" and the check called it correct. Words, read by a person,
are what catch that.
"""
import sys, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, '/Users/hienphantrong/Desktop/Project/AI_PROJECT/NHAP_DATA_LONG')
from app import ksk_workbook as wb
import medapi, build_tiensu as bt

LABEL = {264: "Có", 265: "Không", 5154: "Bình thường", 5155: "Không bình thường",
         102: "Đã tiêm", 103: "Chưa tiêm", 104: "Không nhớ rõ",
         5172: "Bình thường, hẹn khám định kỳ", 5173: "Có yếu tố nguy cơ, cần theo dõi"}
# Reverse map for display only. Aliases (H62.6 -> H52.6's id) must not win the label,
# or a correctly stored code is shown under the wrong name.
_ALIAS = set(__import__('json').loads(
    __import__('pathlib').Path('icd_alias_note.json').read_text()))
ICD = {}
for _c, _i in sorted(__import__('json').loads(
        __import__('pathlib').Path('icd_map.json').read_text()).items()):
    if _i not in ICD or _c not in _ALIAS:
        ICD[_i] = _c


def lab(v):
    if v is None or v == "":
        return "(trống)"
    try:
        n = int(v)
    except (TypeError, ValueError):
        return str(v)
    return LABEL.get(n) or ICD.get(n) or str(v)


FILE = '/Users/hienphantrong/Desktop/Project/AI_PROJECT/NHAP_DATA_LONG/data/TH Bạch Đằng_MAU AI NHAP LIEU  KSK .xlsx'
recs = {int(r['stt']): r for r in wb.load_records(FILE)}
for stt in [int(x) for x in sys.argv[1:]]:
    r = recs[stt]
    who = medapi.find_record(r['cccd'])
    pid, cd = who['phieukhamId'], who['cdId']
    ts = medapi.read_form(1000103, pid, cd)
    ls = medapi.read('lam_sang', pid, cd)
    kl = medapi.read('ket_luan', pid, cd)
    vac = bt.read_vaccines(pid, cd)
    print(f"\n===== TT{stt} {r['name']} =====")
    rows = [
        ("Sản khoa",        r.get('ts_san_khoa'),   lab(ts.get('TS_BanThan_SanKhoa'))),
        ("Tiền sử bệnh",    r.get('ts_benh_tat'),   lab(ts.get('TS_BanThan_MacBenh'))),
        ("Đang điều trị",   r.get('ts_dang_dieu_tri'), ts.get('TS_BanThan_DangDieuTriBenh')),
        ("Tiêm chủng",      r.get('ts_tiem_chung'),
         f"{len([v for v in vac if v.get('TinhTrangTiemId')==102])}/{len(vac)} dòng 'Đã tiêm'"),
        ("Chiều cao",       r.get('chieu_cao'),     ts.get('TheLuc_ChieuCao')),
        ("Cân nặng",        r.get('can_nang'),      ts.get('TheLuc_CanNang')),
        ("Mạch",            r.get('mach'),          ts.get('TheLuc_Mach')),
        ("Huyết áp TT/TTr", f"{r.get('huyet_ap_tt')}/{r.get('huyet_ap_ttr')}",
         f"{ts.get('TheLuc_HuyetApTamThu')}/{ts.get('TheLuc_HuyetApTamTruong')}"),
        ("Nhịp thở",        r.get('nhip_tho'),      ts.get('NhipTho')),
        ("Mắt (chẩn đoán)", r.get('mat_benh'),      lab(ls.get('Mat_ChanDoanSoBo_ICD'))),
        ("TMH (chẩn đoán)", r.get('tmh_benh'),      lab(ls.get('TMH_ChanDoanSoBo_ICD'))),
        ("RHM (chẩn đoán)", r.get('rhm_benh'),      lab(ls.get('RHM_ChanDoanSoBo_ICD'))),
        ("Kết luận",        "(suy từ chẩn đoán)",   lab(kl.get('DeNghi'))),
        ("Đề nghị ghi rõ",  r.get('de_nghi'),       kl.get('KetLuan_DeNghi')),
    ]
    for name, excel, stored in rows:
        print(f"  {name:18s} excel={str(excel)[:38]:38s} | medinet={str(stored)[:44]}")
