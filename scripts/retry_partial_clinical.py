#!/usr/bin/env python3
"""Retry each archived partial KSK record once, with resumable per-record logs."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE = "https://quanlyskcd.medinet.org.vn"
DEFAULT_OUTPUT = (
    ROOT
    / "outputs"
    / "01a00837-8433-7af0-b650-c7d8c10aa93e"
    / "retry_partial"
)
ARCHIVES = [
    ROOT / "outputs" / "01a00837-8433-7af0-b650-c7d8c10aa93e" / "clinical_results_001_100.json",
    ROOT / "outputs" / "01a00837-8433-7af0-b650-c7d8c10aa93e" / "clinical_results_101_270.json",
    ROOT / "outputs" / "01a00837-8433-7af0-b650-c7d8c10aa93e" / "clinical_results_271_361.json",
    ROOT / "outputs" / "01a00837-8433-7af0-b650-c7d8c10aa93e" / "clinical_results_362_363.json",
]


def load_partial_queue(results_dir: Path | None = None) -> list[dict]:
    records: dict[int, dict] = {}
    paths = sorted(results_dir.glob("TT*.json")) if results_dir else ARCHIVES
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        for record in data.get("partial", []):
            records[int(record["stt"])] = record
    return [records[key] for key in sorted(records)]


def result_status(path: Path) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "invalid_result"
    for status in ("done", "partial", "not_found", "search_failed", "no_exam_date", "failed"):
        if data.get(status):
            return status
    return "empty_result"


def write_manifest(output_dir: Path, queue: list[dict]) -> None:
    attempts = []
    for record in queue:
        result_path = output_dir / f"TT{int(record['stt']):03d}_{record['cccd']}.json"
        attempts.append(
            {
                "stt": record["stt"],
                "cccd": record["cccd"],
                "name": record["name"],
                "attempted": result_path.exists(),
                "status": result_status(result_path) if result_path.exists() else "pending",
                "result_file": str(result_path),
            }
        )
    manifest = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "total": len(queue),
        "attempted": sum(item["attempted"] for item in attempts),
        "pending": sum(not item["attempted"] for item in attempts),
        "statuses": {
            status: sum(item["status"] == status for item in attempts)
            for status in sorted({item["status"] for item in attempts})
        },
        "attempts": attempts,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def direct_record_url(record: dict) -> str | None:
    ids = record.get("ids") or {}
    phieu = ids.get("phieukhamId")
    cd = ids.get("cdId")
    if not phieu or not cd:
        return None
    return (
        f"{SITE}/nav_group/kskdk_thongtinkhamduoi18/app/main/dynamicform/viewer/"
        f"KSKD18_ThongTinKham/{phieu}?cdId={cd}&phieukhamId={phieu}"
        "&MauKham=mauphieukskd18"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--from", dest="exam_from", default="01/07/2026")
    parser.add_argument("--to", dest="exam_to", default="16/08/2026")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--queue-results-dir",
        type=Path,
        default=None,
        help="Build the retry queue from partial results in TT*.json files in this directory.",
    )
    parser.add_argument(
        "--only-stt",
        type=int,
        action="append",
        default=None,
        help="Retry only this STT; may be supplied more than once.",
    )
    args = parser.parse_args()

    queue = load_partial_queue(args.queue_results_dir)
    if args.only_stt:
        selected = set(args.only_stt)
        queue = [record for record in queue if int(record["stt"]) in selected]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_manifest(args.output_dir, queue)
    print(f"Có {len(queue)} hồ sơ partial cần chạy lại.", flush=True)

    for index, record in enumerate(queue, 1):
        stt = int(record["stt"])
        cccd = str(record["cccd"])
        result_path = args.output_dir / f"TT{stt:03d}_{cccd}.json"
        log_path = args.output_dir / f"TT{stt:03d}_{cccd}.log"
        if result_path.exists():
            print(f"[{index}/{len(queue)}] TT{stt} đã thử trước đó -> bỏ qua", flush=True)
            continue

        print(
            f"\n[{index}/{len(queue)}] Chạy lại TT{stt} {record['name']} ({cccd})",
            flush=True,
        )
        command = [
            sys.executable,
            "-u",
            "-m",
            "app.clinical",
            "--file",
            str(Path(args.file).expanduser().resolve()),
            "--from",
            args.exam_from,
            "--to",
            args.exam_to,
            "--only-cccd",
            cccd,
        ]
        record_url = direct_record_url(record)
        if record_url:
            command.extend(["--record-url", record_url])
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            assert process.stdout is not None
            for line in process.stdout:
                print(line, end="", flush=True)
                log.write(line)
                log.flush()
            return_code = process.wait()

        live_result = ROOT / "clinical_results.json"
        if live_result.exists():
            shutil.copy2(live_result, result_path)
        else:
            result_path.write_text(
                json.dumps(
                    {"failed": [{**record, "problems": ["không có clinical_results.json"]}]},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        print(f"TT{stt}: exit={return_code}, status={result_status(result_path)}", flush=True)
        write_manifest(args.output_dir, queue)

    write_manifest(args.output_dir, queue)
    print("\nĐã thử lại toàn bộ hàng đợi partial.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
