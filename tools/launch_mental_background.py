"""Launch the resumable single-tab mental-health UI run as a detached process."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--file", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--log", required=True)
    p.add_argument("--pid-file", required=True)
    p.add_argument("--start-at", type=int, default=1)
    p.add_argument("--record-map")
    args = p.parse_args()
    pid_path = Path(args.pid_file)
    if pid_path.exists():
        try:
            old_pid = int(pid_path.read_text().strip())
        except ValueError:
            old_pid = 0
        if old_pid and alive(old_pid):
            raise SystemExit(f"Tiến trình {old_pid} vẫn đang chạy")

    root = Path(__file__).resolve().parent.parent
    command = [sys.executable, str(root / "tools" / "mental_ui.py"),
               "--file", args.file, "--out", args.out,
               "--start-at", str(args.start_at), "--resume", "--verify-here"]
    if args.record_map:
        command += ["--record-map", args.record_map]
    log_path = Path(args.log)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("a")
    process = subprocess.Popen(command, cwd=str(root), stdin=subprocess.DEVNULL,
                               stdout=log, stderr=subprocess.STDOUT,
                               start_new_session=True)
    pid_path.write_text(str(process.pid))
    print(json.dumps({"pid": process.pid, "log": str(log_path), "out": args.out}))


if __name__ == "__main__":
    main()
