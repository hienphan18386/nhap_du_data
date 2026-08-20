"""Tiền sử bản thân for every student, each one read back and compared."""
import json, sys, time, uuid, warnings, pathlib
warnings.filterwarnings('ignore')
sys.path.insert(0, '/Users/hienphantrong/Desktop/Project/AI_PROJECT/NHAP_DATA_LONG')
from app import ksk_workbook as wb
import medapi, build_tiensu as bt

FILE = '/Users/hienphantrong/Desktop/Project/AI_PROJECT/NHAP_DATA_LONG/data/TH Bạch Đằng_MAU AI NHAP LIEU  KSK .xlsx'
OUT = pathlib.Path('tiensu_results.json')

def guarded(fn, *a):
    try:
        return fn(*a)
    except medapi.Unauthorized:
        print("      token het han -- lay lai...", flush=True)
        if not medapi.refresh_token():
            raise SystemExit("KHONG LAY LAI DUOC TOKEN -- dung lai")
        return fn(*a)

recs = sorted(wb.load_records(FILE), key=lambda r: int(r['stt']))
only = {int(x) for x in sys.argv[1:]} or None
res, t0 = [], time.time()
for i, r in enumerate(recs, 1):
    stt = int(r['stt'])
    if only and stt not in only:
        continue
    who = guarded(medapi.find_record, r['cccd'])
    if not who:
        res.append({"stt": stt, "status": "khong_tim_thay"})
        print(f"[{i}/{len(recs)}] TT{stt}: KHONG TIM THAY", flush=True); continue
    pid, cd = who['phieukhamId'], who['cdId']
    cur = guarded(medapi.read_form, 1000103, pid, cd)
    vac = guarded(bt.read_vaccines, pid, cd)
    truoc = bt.check(r, cur, vac)
    vals, probs = bt.build(r, cur, vac)
    vals.update({"KSKD18_TTHC_TienSu_guid": str(uuid.uuid4()), "phieukhamId": pid,
                 "cdId": cd, "MauKham": "mauphieukskd18", "recordid": pid,
                 "AttachmentFile": '{"upload":"","deleted":""}', "nav_selected_items": "{}",
                 "labelactioncode": "SAVE", "formdata_parent": "null"})
    w = guarded(medapi.write, 'tien_su', pid, cd, vals)
    cur2 = guarded(medapi.read_form, 1000103, pid, cd)
    vac2 = guarded(bt.read_vaccines, pid, cd)
    sau = bt.check(r, cur2, vac2) + [p for p in probs if not p.startswith('ghi chú:')]
    res.append({"stt": stt, "name": r['name'], "sai_truoc": truoc, "sai_sau": sau,
                "status": "khop" if not sau else "con_sai"})
    print(f"[{i}/{len(recs)}] {'OK ' if not sau else 'SAI'} TT{stt} {r['name'][:22]:22s} "
          f"truoc={len(truoc)} sau={len(sau)}" + ("  -> " + "; ".join(sau[:2]) if sau else ""),
          flush=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))
print(f"\n===== {len(res)} em trong {time.time()-t0:.0f}s | khop: "
      f"{sum(1 for x in res if x['status']=='khop')} | con sai: "
      f"{sum(1 for x in res if x['status']=='con_sai')}")
