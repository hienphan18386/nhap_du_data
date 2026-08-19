#!/usr/bin/env python3
"""Fill ONLY the dental chart for partial records.

Goes straight to FORM_LAM_SANG via stored IDs, fills only teeth, saves.
No search needed - uses IDs from manifest or previous result files.

Usage:
    # Test on one:
    python3 scripts/retry_teeth_only.py \
        --file "TH Xom Chieu_MAU AI NHAP LIEU  KSK.xlsx" \
        --from 01/07/2026 --to 16/08/2026 \
        --manifest outputs/.../manifest.json \
        --only-cccd 083319009511

    # Run all partial:
    python3 scripts/retry_teeth_only.py \
        --file "TH Xom Chieu_MAU AI NHAP LIEU  KSK.xlsx" \
        --from 01/07/2026 --to 16/08/2026 \
        --manifest outputs/.../manifest.json
"""
from __future__ import annotations

import argparse
import json
import glob
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import ksk_workbook as wb
from app.clinical import (
    ClinicalFiller, FORM_LAM_SANG,
    medinet_tooth_condition,
)
from app.importer import AppleScriptImporter


def collect_ids_from_output_dir(out_dir: Path, pattern: str = "*.json") -> dict:
    """Scan result JSON files for stored record IDs."""
    ids_map = {}  # cccd -> ids
    for jf in sorted(out_dir.glob(pattern)):
        if jf.name == "manifest.json":
            continue
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue
        for bucket in ("done", "partial", "failed", "not_found", "error"):
            for rec in data.get(bucket, []):
                cccd = rec.get("cccd", "")
                ids = rec.get("ids")
                if cccd and ids and ids.get("phieukhamId"):
                    ids_map[cccd] = ids
    return ids_map


def main():
    ap = argparse.ArgumentParser(description="Fill ONLY teeth")
    ap.add_argument("--file", required=True)
    ap.add_argument("--from", dest="exam_from", default="01/07/2026")
    ap.add_argument("--to", dest="exam_to", default="16/08/2026")
    ap.add_argument("--cccd-file", help="File with one CCCD per line")
    ap.add_argument("--only-cccd", help="Test one CCCD")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # Build CCCD set
    cccd_set = set()
    if args.only_cccd:
        cccd_set.add(args.only_cccd)
    elif args.cccd_file:
        for line in Path(args.cccd_file).read_text().splitlines():
            line = line.strip()
            if line:
                cccd_set.add(line)
    else:
        print("Phai chi dinh --only-cccd hoac --cccd-file")
        sys.exit(1)

    # Collect IDs from ALL result files
    ids_map = {}
    out_base = Path("outputs")
    for d in sorted(out_base.rglob("*.json")):
        if d.name == "manifest.json":
            continue
        try:
            data = json.loads(d.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        for bucket in ("done", "partial", "failed", "not_found", "error"):
            items = data.get(bucket, [])
            if isinstance(items, list):
                for rec in items:
                    if isinstance(rec, dict):
                        cccd = rec.get("cccd", "")
                        ids = rec.get("ids")
                        if cccd and ids and ids.get("phieukhamId"):
                            ids_map[cccd] = ids
    # Also root-level
    for jf in Path(".").glob("clinical_results*.json"):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        for bucket in ("done", "partial", "failed", "not_found", "error"):
            items = data.get(bucket, [])
            if isinstance(items, list):
                for rec in items:
                    if isinstance(rec, dict):
                        cccd = rec.get("cccd", "")
                        ids = rec.get("ids")
                        if cccd and ids and ids.get("phieukhamId"):
                            ids_map[cccd] = ids
    print(f"Tim thay IDs cho {len(ids_map)} ho so")

    # Read workbook
    xlsx = str(Path(args.file).expanduser().resolve())
    records = wb.load_records(xlsx)
    print(f"Doc {len(records)} ho so tu {Path(args.file).name}")

    # Filter: need teeth + in CCCD set + have IDs
    queue = []
    for r in records:
        cccd = r.get("cccd", "")
        if cccd not in cccd_set:
            continue
        teeth = wb.tooth_numbers(r.get("cac_rang_sau", ""))
        cond = medinet_tooth_condition(r.get("tinh_trang_rang", ""))
        if not teeth or not cond or cond.lower() in ("binh thuong", "bình thường"):
            continue
        ids = ids_map.get(cccd)
        if not ids:
            print(f"  SKIP TT{r.get('stt','?')} {r.get('ho_ten','?')} ({cccd}): khong co IDs")
            continue
        queue.append((r, ids))

    print(f"\nCo {len(queue)} ho so can nhap rang.\n")
    if not queue:
        return

    # Create driver + filler
    driver = AppleScriptImporter()
    filler = ClinicalFiller(driver, args.exam_from, args.exam_to, args.dry_run)

    done_count = 0
    still_partial = 0
    failed_count = 0

    for i, (r, ids) in enumerate(queue):
        cccd = r["cccd"]
        stt = r.get("stt", "?")
        name = r.get("ho_ten", "?")
        teeth = wb.tooth_numbers(r.get("cac_rang_sau", ""))
        cond = medinet_tooth_condition(r.get("tinh_trang_rang", ""))
        t0 = time.time()

        print(f"[{i+1}/{len(queue)}] TT{stt} {name} ({cccd}) - {len(teeth)} rang ({cond})")

        # Go straight to FORM_LAM_SANG using stored IDs
        url = filler.section_url(FORM_LAM_SANG, ids, None)
        if not filler.goto(url, "TuanHoan_ChuaPhatHienBatThuong"):
            print(f"  FAIL: khong mo duoc form lam sang!")
            failed_count += 1
            continue

        filler._current_ids = ids

        # Fill teeth & RHM diagnosis
        problems = filler.fill_teeth(r)
        if r.get("rhm_benh"):
            problems += filler.fill_diagnosis(r["rhm_benh"], "RHM_ChuaPhatHienBatThuong",
                                              "RHM_ChanDoanSoBo_ICD", "răng-hàm-mặt")
        for p in problems:
            print(f"  ! {p}")

        # Save
        ok, messages = filler.save("Lưu thay đổi")
        if not ok:
            print(f"  Luu LOI: {'; '.join(messages)}")
            failed_count += 1
        elif problems:
            still_partial += 1
        else:
            elapsed = time.time() - t0
            print(f"  OK! ({elapsed:.0f}s)")
            done_count += 1

    # Save final results
    results_file = Path("outputs/01a00837-8433-7af0-b650-c7d8c10aa93e/retry_teeth_final_results.json")
    results_file.parent.mkdir(parents=True, exist_ok=True)
    results_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total": len(queue),
        "done": done_count,
        "partial": still_partial,
        "failed": failed_count
    }
    results_file.write_text(json.dumps(results_data, indent=2, ensure_ascii=False))
    print(f"\nDa luu ket qua vao {results_file}")

    print(f"\n{'='*60}")
    print(f"Tong: {len(queue)}")
    print(f"  Done:    {done_count}")
    print(f"  Partial: {still_partial}")
    print(f"  Failed:  {failed_count}")


if __name__ == "__main__":
    main()
