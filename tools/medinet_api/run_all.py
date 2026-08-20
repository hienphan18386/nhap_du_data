"""Fix Khám lâm sàng + Kết luận for every student, then read both back and compare.

ORDER MATTERS: Tiền sử must be written BEFORE this, never after. Saving Tiền sử resets
boolean fields belonging to Khám lâm sàng that its own payload does not carry --
TieuHoa_ChuaPhatHienBatThuong and ThanTietNieu_ChanDoanSoBo both flip to false -- so a
Tiền sử run following this one silently undoes it. Measured on TT198 and confirmed on
a sample of eight: 8/8 had the tiêu hoá tick wiped. The reverse is safe: writing Khám
lâm sàng leaves Tiền sử untouched.

Nothing counts as done because a write returned Success: each record is re-read from
the server afterwards and every field the workbook specifies is compared against it.
"""
import json, sys, time, uuid, warnings, pathlib
warnings.filterwarnings('ignore')
sys.path.insert(0, '/Users/hienphantrong/Desktop/Project/AI_PROJECT/NHAP_DATA_LONG')
from app import ksk_workbook as wb
import medapi, build_lamsang as bl, build_ketluan as bk

FILE = '/Users/hienphantrong/Desktop/Project/AI_PROJECT/NHAP_DATA_LONG/data/TH Bạch Đằng_MAU AI NHAP LIEU  KSK .xlsx'
OUT = pathlib.Path('run_all_results.json')


def scaffold(guid_field, pid, cd):
    return {guid_field: str(uuid.uuid4()), "phieukhamId": pid, "cdId": cd,
            "MauKham": "mauphieukskd18", "AttachmentFile": '{"upload":"","deleted":""}',
            "nav_selected_items": "{}", "labelactioncode": "SAVE", "formdata_parent": "null"}


def guarded(fn, *a, **k):
    """Run one API call, renewing the session once if it has expired.

    An expired token must never be mistaken for an absent record, so a second
    failure stops the whole run instead of marking students "không tìm thấy".
    """
    try:
        return fn(*a, **k)
    except medapi.Unauthorized:
        print("      token het han -- dang lay lai...", flush=True)
        if not medapi.refresh_token():
            raise SystemExit("KHONG LAY LAI DUOC TOKEN -- dung lai, khong ghi nhan sai")
        return fn(*a, **k)


def main():
    recs = sorted(wb.load_records(FILE), key=lambda r: int(r['stt']))
    only = {int(x) for x in sys.argv[1:]} or None
    results, t0 = [], time.time()
    for i, r in enumerate(recs, 1):
        stt = int(r['stt'])
        if only and stt not in only:
            continue
        rec = {"stt": stt, "name": r['name'], "cccd": r['cccd']}
        who = guarded(medapi.find_record, r['cccd'])
        if not who:
            rec["status"] = "khong_tim_thay"
            results.append(rec); print(f"[{i}/{len(recs)}] TT{stt} {r['name']}: KHONG TIM THAY", flush=True)
            OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1)); continue
        pid, cd = who['phieukhamId'], who['cdId']
        rec.update(phieukhamId=pid, cdId=cd, exam=who.get('exam'))

        before_ls = guarded(medapi.read, 'lam_sang', pid, cd)
        before_kl = guarded(medapi.read, 'ket_luan', pid, cd)
        if not before_ls and not before_kl:
            rec["status"] = "doc_khong_duoc"
            results.append(rec); print(f"[{i}/{len(recs)}] TT{stt}: DOC KHONG DUOC", flush=True)
            OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1)); continue
        rec["sai_truoc"] = bl.check(r, before_ls) + bk.check(r, before_kl)

        vals, probs = bl.build(r, before_ls)
        vals.update(scaffold("KSKD18_ThongTinKham_guid", pid, cd))
        w1 = guarded(medapi.write, 'lam_sang', pid, cd, vals)

        vals2, _ = bk.build(r, before_kl)
        vals2.update(scaffold("KSKD18_KetLuanKham_guid", pid, cd))
        w2 = guarded(medapi.write, 'ket_luan', pid, cd, vals2)

        after_ls = guarded(medapi.read, 'lam_sang', pid, cd)
        after_kl = guarded(medapi.read, 'ket_luan', pid, cd)
        sai = bl.check(r, after_ls) + bk.check(r, after_kl) + probs
        rec.update(ghi_lam_sang=w1["ok"], ghi_ket_luan=w2["ok"], sai_sau=sai,
                   status="khop" if not sai else "con_sai")
        results.append(rec)
        mark = "OK " if not sai else "SAI"
        print(f"[{i}/{len(recs)}] {mark} TT{stt} {r['name'][:24]:24s} "
              f"truoc={len(rec['sai_truoc'])} sau={len(sai)}"
              + ("  -> " + "; ".join(sai[:2]) if sai else ""), flush=True)
        OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1))

    done = [x for x in results if x.get("status") == "khop"]
    print(f"\n===== {len(results)} em trong {time.time()-t0:.0f}s | khop: {len(done)} "
          f"| con sai: {sum(1 for x in results if x.get('status')=='con_sai')} "
          f"| khong tim thay: {sum(1 for x in results if x.get('status')=='khong_tim_thay')}")


if __name__ == "__main__":
    main()
