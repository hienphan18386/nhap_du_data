"""Check the ADHD questionnaire of every student against the workbook. Read-only.

The UI run's "OK" only means the save button was pressed and Medinet did not complain.
This is the evidence: the answers are read back from the server and compared, one
question at a time, with the answer table that belongs to this questionnaire -- labels
repeat between question sets, so a shared table would match the wrong id.
"""
import argparse, json, sys, time, warnings, pathlib
warnings.filterwarnings('ignore')
sys.path.insert(0, '/Users/hienphantrong/Desktop/Project/AI_PROJECT/NHAP_DATA_LONG')
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from app import ksk_workbook as wb
import medapi
from check_tamthan import read_rows, ADHD

DEFAULT_FILE = \
    '/Users/hienphantrong/Desktop/Project/AI_PROJECT/NHAP_DATA_LONG/data/THCS Tang Bat Ho_AI nhap lieu KQ kham.xlsx'


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('file', nargs='?', default=DEFAULT_FILE)
    p.add_argument('--only-stt-from',
                   help='JSON array containing the STT values that should be checked')
    p.add_argument('--only-stt', type=int, action='append',
                   help='Check one STT; repeat the option to check more than one')
    p.add_argument('--out', default='outputs/tangbatho/verify_adhd.json')
    return p.parse_args()


def guarded(fn, *a):
    for _ in range(2):
        try:
            return fn(*a)
        except medapi.Unauthorized:
            print("   phiên hết hạn -- lấy lại token...", flush=True)
            if not medapi.refresh_token():
                raise SystemExit("KHÔNG LẤY LẠI ĐƯỢC TOKEN -- dừng, không ghi nhận sai")
    return None


args = parse_args()
records = sorted(wb.load_records(args.file), key=lambda r: int(r['stt']))
if args.only_stt_from or args.only_stt:
    selected = set(args.only_stt or [])
    if args.only_stt_from:
        selected.update(int(row['stt']) for row in json.loads(
            pathlib.Path(args.only_stt_from).read_text()))
    records = [r for r in records if int(r['stt']) in selected]
    found = {int(r['stt']) for r in records}
    missing = sorted(selected - found)
    if missing:
        raise SystemExit(f'Không tìm thấy STT trong workbook: {missing}')
bad, t0 = [], time.time()
for i, r in enumerate(records, 1):
    answers = [wb.nfc(a or "") for a in (r.get('adhd') or [])]
    wanted = [a for a in answers if a]
    if not wanted:
        continue
    who = guarded(medapi.find_record, r['cccd'])
    if not who:
        bad.append({"stt": int(r['stt']), "name": r['name'], "sai": ["không tra được hồ sơ"]})
        continue
    pid, cd = who['phieukhamId'], who['cdId']
    rows = sorted(guarded(read_rows, pid, cd, "GiamChuY_6_18Tuoi", "1000278") or [],
                  key=lambda x: int(x.get('stt') or 0))
    sai = []
    if not rows:
        sai.append("không đọc được bảng câu hỏi")
    for k, row in enumerate(rows):
        text = answers[k] if k < len(answers) else ""
        if not text:
            continue
        want = ADHD.get(text.lower().strip(" .:;"))
        if want is None:
            sai.append(f"câu {row.get('stt')}: Excel ghi {text!r} không có trong danh mục")
        elif str(row.get('GiaTri') or '') != str(want):
            sai.append(f"câu {row.get('stt')}: lưu {row.get('GiaTri')}, cần {want} ({text})")
    if sai:
        bad.append({"stt": int(r['stt']), "name": r['name'], "cccd": r['cccd'], "sai": sai})
        print(f"  SAI TT{r['stt']} {r['name'][:24]}: {len(sai)} câu -> {sai[0][:60]}", flush=True)
    if i % 100 == 0:
        print(f"  ...đã kiểm {i}/{len(records)} | sai đến giờ: {len(bad)}", flush=True)

print(f"\n===== ADHD: {len(records)} em trong {(time.time()-t0)/60:.0f} phút")
print(f"      khớp hoàn toàn : {len(records)-len(bad)}")
print(f"      còn sai        : {len(bad)}")
pathlib.Path(args.out).write_text(
    json.dumps(bad, ensure_ascii=False, indent=1))
