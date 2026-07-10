"""
smoke_test.py — Verify a server container is up and its trace logging works
before you invest in a full sweep.

Sends ~5 seconds of light load with the matching generator, then checks that
rows appeared in the server's live CSV log.

Usage (from the platform folder):
  docker compose up -d --build python-dsp
  python3 scripts/smoke_test.py --server python_dsp
"""
import argparse
import os
import subprocess
import sys
import time

from sweep import SERVERS, LOGS, load_cmd, reset_live_csv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", required=True, choices=sorted(SERVERS))
    args = ap.parse_args()

    svc, folder, tag, live_name, url, kind, header, _ = SERVERS[args.server]
    live_csv = os.path.join(LOGS, live_name)

    print(f"smoke test: {args.server} (compose service '{svc}') at {url}")
    reset_live_csv(live_csv, header)
    cmd = load_cmd(kind, url, rate=5, duration=5, seed=1)
    try:
        subprocess.run(cmd, timeout=45)
    except subprocess.TimeoutExpired:
        print("[FAIL] load generator hung — is the container running?")
        sys.exit(1)
    time.sleep(1)

    with open(live_csv, encoding="utf-8", errors="replace") as f:
        lines = f.read().strip().splitlines()
    n_rows = max(0, len(lines) - 1) if header else len(lines)
    if n_rows > 0:
        print(f"[OK] {n_rows} trace rows captured in data/live_logs/{live_name}")
        print(f"     first data line: {lines[1 if header else 0][:120]}")
        sys.exit(0)
    print(f"[FAIL] no trace rows in {live_csv}.")
    print("       Checklist: container up? (docker compose ps)  "
          "correct port free?  data/live_logs/ writable by the container?")
    sys.exit(1)


if __name__ == "__main__":
    main()
