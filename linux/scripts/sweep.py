"""
sweep.py — Run Poisson load sweeps against one server and collect traces.

For each requested rate it:
  1. Truncates the server's live CSV log and pre-writes the correct header
     (most servers write their header only once per process start, so after a
     truncation the header would otherwise be lost).
  2. Runs the matching Poisson load generator for --duration seconds, with
     client-side logging enabled.
  3. Saves TWO traces per run plus a metadata JSON:
       traces/<server>/<tag>_<rate>rps_runNN.csv         (server-side, internal)
       traces/<server>/<tag>_<rate>rps_runNN_client.csv  (client-side, external)
     The server trace is written by timestamps inside the server; the client
     trace is the load generator's own view (send time -> full response
     received). Comparing the two is part of the lab exercises.

Run numbers auto-increment, so re-running the same command adds new trials and
never overwrites existing traces.

Run only ONE server at a time: the containers are pinned to the same CPU cores
on purpose, and concurrent servers would contend with each other.

Usage (from the platform folder, e.g. linux/):
  python3 scripts/sweep.py --server python_dsp
  python3 scripts/sweep.py --server apache_dsp --rates 10 25 50
  python3 scripts/sweep.py --server go --rates 100 200 --duration 60 --trials 3
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)                      # platform folder (linux/ etc.)
LOGS = os.path.join(BASE, "data", "live_logs")
TRACES = os.path.join(BASE, "traces")

AES_KEY = ("0102030405060708090a0b0c0d0e0f10"
           "1112131415161718191a1b1c1d1e1f20")

# CSV headers each server writes (only once per process start). We pre-write
# them after truncating the shared live log so every collected trace parses.
H_DSP_PY = ("arrival_unix_ns,service_ms,queue_ms,response_ms,status_code,"
            "route,method,pid,body_parse_ms,decrypt_ms,unpack_ms,fir_ms,"
            "pack_ms,encrypt_ms")
H_DSP_NODE = ("arrival_unix_ns,service_ms,queue_ms,response_ms,status_code,"
              "route,method,pid,body_read_ms,body_parse_ms,decrypt_ms,"
              "unpack_ms,fir_ms,pack_ms,encrypt_ms")
H_DSP_JAVA = ("arrival_unix_ns,service_ms,queue_ms,response_ms,status_code,"
              "route,method,pid,worker_id,body_read_ms,body_parse_ms,"
              "decrypt_ms,unpack_ms,fir_ms,pack_ms,encrypt_ms")
H_DSP_PHP = ("arrival_unix_ns,service_ms,queue_ms,response_ms,status_code,"
             "route,method,pid,parse_ms,decrypt_ms,unpack_ms,kernel_ms,"
             "fir_ms,pack_ms,encrypt_ms")
H_GO = ("id,trace_id,arrival_unix_ns,service_start_unix_ns,"
        "service_end_unix_ns,response_end_unix_ns,queue_ms,service_ms,"
        "response_ms,status_code,bytes_written,route,method,pid,worker_id,"
        "service_target_ms,work_ms,write_response_ms")
H_SQLITE = ("arrival_unix_ns,service_ms,queue_ms,response_ms,status_code,"
            "route,method,pid,worker_id,body_parse_ms,insert_ms,select_ms,"
            "db_ms,write_response_ms")

# key: (compose service, trace folder, file tag, live csv, url, load kind,
#       header, suggested rates)
SERVERS = {
    "go":            ("app",           "go_1c",         "go",
                      "requests.csv",              "http://localhost:8080",
                      "go",     H_GO,       [50, 100, 200, 400]),
    "apache_msg":    ("apache",        "apache_msg_1c", "apache_msg",
                      "apache_requests.csv",       "http://localhost:8082",
                      "apache", None,      [10, 25, 50]),
    "apache_dsp":    ("apache-dsp",    "apache_dsp_1c", "apache_dsp",
                      "dsp_aes_requests.csv",      "http://localhost:8083/process",
                      "dsp",    H_DSP_PHP,  [10, 25, 50, 75, 100]),
    "node_dsp":      ("node-dsp",      "node_dsp_1c",   "node_dsp",
                      "node_dsp_requests.csv",     "http://localhost:8084/process",
                      "dsp",    H_DSP_NODE, [200, 400, 800, 1200, 1600]),
    "python_dsp":    ("python-dsp",    "python_dsp_1c", "python_dsp",
                      "python_dsp_requests.csv",   "http://localhost:8085/process",
                      "dsp",    H_DSP_PY,   [10, 25, 50, 75]),
    "java_dsp":      ("java-dsp",      "java_dsp_1c",   "java_dsp",
                      "java_dsp_requests.csv",     "http://localhost:8086/process",
                      "dsp",    H_DSP_JAVA, [100, 200, 400, 600]),
    "go_sqlite":     ("go-sqlite",     "go_sqlite_1c",  "go_sqlite",
                      "go_sqlite_requests.csv",    "http://localhost:8087/process",
                      "sqlite", H_SQLITE,   [100, 200, 400, 600]),
    "node_dsp_mc":   ("node-dsp-mc",   "node_dsp_3c",   "node_dsp_mc",
                      "node_dsp_mc_requests.csv",  "http://localhost:8088/process",
                      "dsp",    H_DSP_NODE, [200, 400, 800, 1600, 2400]),
    "python_dsp_mc": ("python-dsp-mc", "python_dsp_3c", "python_dsp_mc",
                      "python_dsp_mc_requests.csv","http://localhost:8089/process",
                      "dsp",    H_DSP_PY,   [25, 50, 100, 150, 200, 250, 300]),
    "java_dsp_mc":   ("java-dsp-mc",   "java_dsp_3c",   "java_dsp_mc",
                      "java_dsp_mc_requests.csv",  "http://localhost:8090/process",
                      "dsp",    H_DSP_JAVA, [100, 200, 400, 600, 800]),
    "go_sqlite_mc":  ("go-sqlite-mc",  "go_sqlite_3c",  "go_sqlite_mc",
                      "go_sqlite_mc_requests.csv", "http://localhost:8091/process",
                      "sqlite", H_SQLITE,   [50, 100, 200, 400, 800]),
}


def next_run(out_dir, tag):
    if not os.path.isdir(out_dir):
        return 1
    pat = re.compile(rf"^{re.escape(tag)}_\d+rps_run(\d+)\.csv$")
    runs = [int(m.group(1)) for f in os.listdir(out_dir) if (m := pat.match(f))]
    return max(runs, default=0) + 1


def reset_live_csv(path, header):
    """Truncate the live log, pre-write the header, and make sure the container
    process (which may run as a different uid, e.g. Apache's www-data) can
    append to it."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        if header:
            f.write(header + "\n")
    os.chmod(path, 0o666)


def load_cmd(kind, url, rate, duration, seed, client_log=""):
    py = sys.executable
    if kind == "dsp":
        cmd = [py, os.path.join(HERE, "dsp_aes_load.py"), "--url", url,
               "--rate", str(rate), "--duration", str(duration),
               "--aes-key", AES_KEY, "--seed", str(seed)]
    elif kind == "apache":
        cmd = [py, os.path.join(HERE, "apache_load.py"), "--base-url", url,
               "--rate", str(rate), "--duration", str(duration),
               "--seed", str(seed)]
    elif kind == "sqlite":
        cmd = [py, os.path.join(HERE, "sqlite_load.py"), "--url", url,
               "--rate", str(rate), "--duration", str(duration),
               "--seed", str(seed)]
    else:
        # "go": plain GETs against the root route.
        cmd = [py, os.path.join(HERE, "poisson_load_generator.py"), "--url", url + "/",
               "--rate", str(rate), "--duration", str(duration),
               "--seed", str(seed)]
    if client_log:
        cmd += ["--client-log", client_log]
    return cmd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", required=True, choices=sorted(SERVERS))
    ap.add_argument("--rates", nargs="*", type=int, default=None)
    ap.add_argument("--duration", type=int, default=90)
    ap.add_argument("--trials", type=int, default=1)
    ap.add_argument("--seed-base", type=int, default=42)
    args = ap.parse_args()

    svc, folder, tag, live_name, url, kind, header, def_rates = SERVERS[args.server]
    live_csv = os.path.join(LOGS, live_name)
    out_dir = os.path.join(TRACES, folder)
    os.makedirs(out_dir, exist_ok=True)
    rates = args.rates or def_rates
    run0 = next_run(out_dir, tag)

    print(f"server={args.server} service={svc} rates={rates} "
          f"duration={args.duration}s trials={args.trials} first_run={run0:02d}")
    print("Make sure the container is up, e.g.: "
          f"docker compose up -d --build {svc}\n")

    for t in range(args.trials):
        run = run0 + t
        for rate in rates:
            dest = os.path.join(out_dir, f"{tag}_{rate}rps_run{run:02d}.csv")
            client_dest = os.path.join(out_dir, f"{tag}_{rate}rps_run{run:02d}_client.csv")
            print(f"=== {args.server} {rate} rps run{run:02d} ===")
            reset_live_csv(live_csv, header)
            time.sleep(0.5)
            seed = args.seed_base + run - 1
            started = datetime.now(timezone.utc).isoformat()
            cmd = load_cmd(kind, url, rate, args.duration, seed,
                           client_log=client_dest)
            try:
                subprocess.run(cmd, timeout=args.duration + 60)
            except subprocess.TimeoutExpired:
                print("  [WARN] load generator timed out")
            time.sleep(2)
            if os.path.getsize(live_csv) > 200:
                shutil.copy2(live_csv, dest)
                rows = sum(1 for _ in open(dest)) - 1
                meta = {"server": args.server, "rate_rps": rate,
                        "duration_s": args.duration, "seed": seed, "run": run,
                        "url": url, "started_at_utc": started, "rows": rows,
                        "completed_at_utc": datetime.now(timezone.utc).isoformat()}
                with open(dest.replace(".csv", "_meta.json"), "w") as f:
                    json.dump(meta, f, indent=2)
                print(f"  saved {rows} rows -> {os.path.relpath(dest, BASE)}")
            else:
                print(f"  [WARN] no rows captured in {live_csv} — "
                      "is the container running and writing to data/live_logs/?")


if __name__ == "__main__":
    main()
