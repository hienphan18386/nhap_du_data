"""Wait for the detached Chrome run, then perform the independent full API readback."""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--wait-pid", type=int, required=True)
    p.add_argument("--file", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--log", required=True)
    args = p.parse_args()
    while alive(args.wait_pid):
        time.sleep(30)

    root = Path(__file__).resolve().parent.parent
    command = [sys.executable, str(root / "tools" / "medinet_api" / "import_all.py"),
               "--file", args.file, "--mode", "verify", "--out", args.out]
    with Path(args.log).open("a") as log:
        log.write("Chrome đã kết thúc; bắt đầu đọc ngược API toàn bộ.\n")
        log.flush()
        code = subprocess.call(command, cwd=str(root), stdout=log, stderr=subprocess.STDOUT)
        log.write(f"Đọc ngược kết thúc với mã {code}.\n")


if __name__ == "__main__":
    main()
