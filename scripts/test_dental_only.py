#!/usr/bin/env python3
"""Test ONLY the dental chart (teeth) section for one student.

Opens a student's clinical form, navigates to the lam sang section,
dumps the iframe DOM to understand what tooth elements are available,
then tries to fill teeth and reports results.

Usage:
    python3 scripts/test_dental_only.py --cccd 079319026177 \
        --file "TH Xom Chieu_MAU AI NHAP LIEU  KSK.xlsx" \
        --from 01/07/2026 --to 16/08/2026

    # With record URL (skips search):
    python3 scripts/test_dental_only.py --cccd 079319026177 \
        --file "TH Xom Chieu_MAU AI NHAP LIEU  KSK.xlsx" \
        --from 01/07/2026 --to 16/08/2026 \
        --record-url "https://quanlyskcd.medinet.org.vn/..."

    # Dry-run (don't actually save):
    python3 scripts/test_dental_only.py --cccd 079319026177 \
        --file "..." --dry-run

    # Dump only (just inspect DOM, don't try filling):
    python3 scripts/test_dental_only.py --cccd 079319026177 \
        --file "..." --dump-only
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import ksk_workbook as wb
from app.clinical import (
    ClinicalImporter, FORM_LAM_SANG, SITE, NAV,
    medinet_tooth_condition,
)
from app.importer import js_string


def main():
    ap = argparse.ArgumentParser(description="Test dental chart for one student")
    ap.add_argument("--file", required=True, help="Path to KSK Excel file")
    ap.add_argument("--cccd", required=True, help="Student CCCD to test")
    ap.add_argument("--from", dest="exam_from", default="01/01/2020")
    ap.add_argument("--to", dest="exam_to", default="31/12/2030")
    ap.add_argument("--record-url", help="Direct URL to the student's record")
    ap.add_argument("--dry-run", action="store_true", help="Don't save changes")
    ap.add_argument("--dump-only", action="store_true", help="Just dump iframe DOM, don't fill")
    args = ap.parse_args()

    # Read workbook
    records = wb.read_ksk(str(Path(args.file).expanduser().resolve()))
    print(f"Doc {len(records)} ho so tu {Path(args.file).name}")

    # Find student
    r = None
    for rec in records:
        if rec.get("cccd") == args.cccd:
            r = rec
            break
    if not r:
        print(f"Khong tim thay CCCD {args.cccd} trong file!")
        sys.exit(1)

    stt = r.get("stt", "?")
    name = r.get("ho_ten", "?")
    print(f"\nTT{stt} {name} ({args.cccd})")
    print(f"  Tinh trang rang: {r.get('tinh_trang_rang', '(trong)')}")
    print(f"  Cac rang sau:    {r.get('cac_rang_sau', '(trong)')}")

    condition = medinet_tooth_condition(r.get("tinh_trang_rang", ""))
    teeth = wb.tooth_numbers(r.get("cac_rang_sau", ""))
    print(f"  -> condition: {condition!r}")
    print(f"  -> teeth:     {teeth}")

    if not teeth:
        print("\nKhong co rang nao can dien. Xong!")
        sys.exit(0)

    # Create importer
    imp = ClinicalImporter(
        file_path=str(Path(args.file).expanduser().resolve()),
        exam_from=args.exam_from,
        exam_to=args.exam_to,
        dry_run=args.dry_run,
    )

    # Find the record on Medinet
    if args.record_url:
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(args.record_url)
        qs = parse_qs(parsed.query)
        path_parts = parsed.path.rstrip("/").split("/")
        phieukham_id = path_parts[-1] if path_parts else ""
        cd_id = qs.get("cdId", [""])[0]
        ids = {"phieukhamId": phieukham_id, "cdId": cd_id}
        print(f"\n  Mo thang theo URL: {ids}")
    else:
        print(f"\n  Tim ho so tren Medinet...")
        found = imp.find_student(args.cccd)
        if not found:
            print("  Khong tim thay ho so!")
            sys.exit(1)
        ids = found
        print(f"  Tim thay: {ids}")

    # Navigate to Lam Sang form
    url = imp.section_url(FORM_LAM_SANG, ids, None)
    print(f"\n  Mo form Kham lam sang...")
    if not imp.goto(url, "TuanHoan_ChuaPhatHienBatThuong"):
        print("  FAIL: Khong mo duoc form!")
        sys.exit(1)
    print("  OK: Form da mo")

    # Wait for iframe to load
    time.sleep(3)

    # DUMP: Examine the iframe DOM
    print("\n" + "=" * 60)
    print("KHAO SAT IFRAME BIEU DO RANG")
    print("=" * 60)

    iframe_info = imp.js("""
        (function(){
            var frame = document.querySelector('iframe[src*="ksk_kham_rang_m2"]');
            if (!frame) return JSON.stringify({error: 'no-iframe', iframes: Array.from(document.querySelectorAll('iframe')).map(function(f){ return f.src; })});
            var doc = null;
            try { doc = frame.contentDocument; } catch (e) { return JSON.stringify({error: 'inaccessible', msg: e.message}); }
            if (!doc) return JSON.stringify({error: 'no-doc'});

            var selects = Array.from(doc.querySelectorAll('select.tooth-select'));
            var toothData = selects.map(function(s){
                var opt = s.options[s.selectedIndex];
                return {
                    tooth: s.getAttribute('data-tooth'),
                    value: s.value,
                    text: opt ? opt.textContent.trim() : '',
                    optionCount: s.options.length
                };
            });

            // Also check for other tooth-like elements
            var otherInputs = Array.from(doc.querySelectorAll('[data-tooth]'));
            var allToothNums = otherInputs.map(function(e){
                return {tag: e.tagName, tooth: e.getAttribute('data-tooth'), cls: e.className};
            });

            return JSON.stringify({
                ok: true,
                selectCount: selects.length,
                allDataToothCount: otherInputs.length,
                bodyHTML_length: doc.body ? doc.body.innerHTML.length : 0,
                toothNumbers: toothData.map(function(t){ return t.tooth; }),
                toothData: toothData,
                allDataTooth: allToothNums.slice(0, 20),
                bodySnippet: doc.body ? doc.body.innerHTML.substring(0, 800) : ''
            });
        })()
    """)

    try:
        info = json.loads(iframe_info) if isinstance(iframe_info, str) else iframe_info
    except (json.JSONDecodeError, TypeError):
        info = {"raw": str(iframe_info)}

    print(json.dumps(info, indent=2, ensure_ascii=False))

    if info.get("error"):
        print(f"\nFAIL: Iframe loi: {info['error']}")
        print("  Cho 30s roi thu lai...")
        time.sleep(30)
        iframe_info2 = imp.js("""
            (function(){
                var frame = document.querySelector('iframe[src*="ksk_kham_rang_m2"]');
                if (!frame) return JSON.stringify({error: 'still-no-iframe'});
                var doc = null;
                try { doc = frame.contentDocument; } catch(e) { return JSON.stringify({error: 'still-inaccessible'}); }
                if (!doc) return JSON.stringify({error: 'still-no-doc'});
                var selects = doc.querySelectorAll('select.tooth-select');
                return JSON.stringify({selectCount: selects.length, bodyLen: doc.body ? doc.body.innerHTML.length : 0});
            })()
        """)
        print(f"  Sau 30s: {iframe_info2}")

    # Check which teeth we need exist in iframe
    if info.get("ok"):
        available = set(info.get("toothNumbers", []))
        print(f"\nRang co trong iframe: {sorted(available)} ({len(available)} rang)")
        print(f"Rang can dien:        {teeth}")
        missing = [t for t in teeth if t not in available]
        present = [t for t in teeth if t in available]
        print(f"   Co san: {present}")
        print(f"   Thieu:  {missing}")

        if missing:
            print(f"\n!!!  {len(missing)} rang khong ton tai trong bieu do Medinet!")
            print("   Co the rang sua da thay -> Medinet khong tao select cho rang do.")

    if args.dump_only:
        print("\n[dump-only] Xong khao sat, khong dien.")
        sys.exit(0)

    # Try filling teeth
    print("\n" + "=" * 60)
    print("THU DIEN BIEU DO RANG")
    print("=" * 60)

    problems = imp.fill_teeth(r)
    if problems:
        print(f"\nVan de ({len(problems)}):")
        for p in problems:
            print(f"   - {p}")
    else:
        print("\nOK: Dien het rang thanh cong!")

    # Save
    if not args.dry_run and not problems:
        print("\nLuu...")
        ok, messages = imp.save("Luu thay doi")
        if ok:
            print("   OK: Da luu!")
        else:
            print(f"   FAIL: Luu that bai: {'; '.join(messages)}")
    elif args.dry_run:
        print("\n[dry-run] Khong luu.")

    # Verify
    if not args.dump_only and info.get("ok"):
        print("\nVerify...")
        verify_problems = imp.verify_teeth(r)
        if verify_problems:
            print(f"   Van de: {verify_problems}")
        else:
            print("   OK: Verify OK!")


if __name__ == "__main__":
    main()
