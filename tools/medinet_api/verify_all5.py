"""Check all five sections of every record at once. Read-only.

Checking one section at a time is what let a whole run go wrong unnoticed: saving Tiền
sử resets two booleans owned by Khám lâm sàng, and a per-section check never looks at
the section it just damaged. Everything is written first, then everything is read.
"""
import json, sys, time, warnings, pathlib
warnings.filterwarnings('ignore')
sys.path.insert(0, '/Users/hienphantrong/Desktop/Project/AI_PROJECT/NHAP_DATA_LONG')
from app import ksk_workbook as wb
import medapi, build_lamsang as bl, build_ketluan as bk, build_tiensu as bt, check_tamthan as ct

FILE = '/Users/hienphantrong/Desktop/Project/AI_PROJECT/NHAP_DATA_LONG/data/TH Bạch Đằng_MAU AI NHAP LIEU  KSK .xlsx'

def guarded(fn, *a):
    try:
        return fn(*a)
    except medapi.Unauthorized:
        print("   token het han -- lay lai...", flush=True)
        if not medapi.refresh_token():
            raise SystemExit("KHONG LAY LAI DUOC TOKEN -- dung lai")
        return fn(*a)

recs = sorted(wb.load_records(FILE), key=lambda r: int(r['stt']))
bad, t0 = [], time.time()
for i, r in enumerate(recs, 1):
    who = guarded(medapi.find_record, r['cccd'])
    if not who:
        bad.append({"stt": int(r['stt']), "name": r['name'], "sai": ["khong tim thay ho so"]})
        continue
    pid, cd = who['phieukhamId'], who['cdId']
    sai = []
    sai += [f"[Tiền sử] {x}" for x in bt.check(
        r, guarded(medapi.read_form, 1000103, pid, cd), guarded(bt.read_vaccines, pid, cd))]
    sai += [f"[Khám lâm sàng] {x}" for x in bl.check(r, guarded(medapi.read, 'lam_sang', pid, cd))]
    sai += [f"[Kết luận] {x}" for x in bk.check(r, guarded(medapi.read, 'ket_luan', pid, cd))]
    sai += [f"[Tâm thần] {x}" for x in guarded(ct.check, r, pid, cd)]
    if sai:
        bad.append({"stt": int(r['stt']), "name": r['name'], "sai": sai})
        print(f"  SAI TT{r['stt']} {r['name'][:22]}: {len(sai)} cho -> {sai[0][:74]}", flush=True)
    if i % 30 == 0:
        print(f"  ...da kiem {i}/{len(recs)} | sai den gio: {len(bad)}", flush=True)
print(f"\n===== DOI CHIEU CA 5 MUC: {len(recs)} em trong {time.time()-t0:.0f}s")
print(f"      khop hoan toan voi Excel : {len(recs)-len(bad)}")
print(f"      con sai                  : {len(bad)}")
pathlib.Path('verify_all5.json').write_text(json.dumps(bad, ensure_ascii=False, indent=1))
