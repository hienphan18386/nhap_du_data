"""Detach the post-import verification monitor."""
import argparse
import json
import subprocess
import sys
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--wait-pid", type=int, required=True)
    p.add_argument("--file", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--log", required=True)
    p.add_argument("--pid-file", required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parent.parent
    command = [sys.executable, str(root / "tools" / "verify_when_mental_done.py"),
               "--wait-pid", str(args.wait_pid), "--file", args.file,
               "--out", args.out, "--log", args.log]
    process = subprocess.Popen(command, cwd=str(root), stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               start_new_session=True)
    Path(args.pid_file).write_text(str(process.pid))
    print(json.dumps({"pid": process.pid, "waiting_for": args.wait_pid}))


if __name__ == "__main__":
    main()
