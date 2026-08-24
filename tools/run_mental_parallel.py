"""Run six independent Medinet questionnaire workers on pre-marked Chrome tabs."""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


RANGES = [(9, 75), (84, 75), (159, 75), (234, 75), (309, 75), (384, 74)]


def result_count(path):
    try:
        return len(json.loads(path.read_text()))
    except (OSError, ValueError):
        return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--file", required=True)
    p.add_argument("--out-dir", required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parent.parent
    output_dir = Path(args.out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    workers, logs = [], []

    for number, (start, limit) in enumerate(RANGES, 1):
        output = output_dir / f"worker_{number}.json"
        log_path = output_dir / f"worker_{number}.log"
        log = log_path.open("a")
        command = [sys.executable, str(root / "tools" / "mental_ui.py"),
                   "--file", args.file, "--out", str(output),
                   "--start-at", str(start), "--limit", str(limit),
                   "--tab-marker", f"codex-medinet-worker-{number}", "--resume"]
        workers.append(subprocess.Popen(command, cwd=str(root), stdout=log,
                                        stderr=subprocess.STDOUT))
        logs.append(log)

    total_expected = sum(limit for _, limit in RANGES)
    last_count = -1
    try:
        while any(worker.poll() is None for worker in workers):
            count = sum(result_count(output_dir / f"worker_{n}.json") for n in range(1, 7))
            if count != last_count:
                print(f"Tiến độ UI tâm thần: {count}/{total_expected}", flush=True)
                last_count = count
            time.sleep(10)
    except KeyboardInterrupt:
        for worker in workers:
            if worker.poll() is None:
                worker.terminate()
        raise
    finally:
        for log in logs:
            log.close()

    codes = [worker.returncode for worker in workers]
    count = sum(result_count(output_dir / f"worker_{n}.json") for n in range(1, 7))
    print(f"Hoàn tất tiến trình: {count}/{total_expected}; mã thoát {codes}", flush=True)
    if any(code != 0 for code in codes):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
