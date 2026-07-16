# Platform Setup — Windows (Docker Desktop, WSL2 backend)

## 1. Install prerequisites

1. Install **Docker Desktop for Windows** and enable the **WSL2 backend**
   (Settings → General → "Use the WSL 2 based engine").
2. Install **Python 3.10+** from python.org (tick "Add python.exe to PATH").
3. In Docker Desktop → Settings → Resources, give Docker at least **4 CPUs**
   and 4 GB RAM.

## 2. Install Python dependencies

```powershell
python -m pip install requests cryptography numpy scipy matplotlib pandas
```

## 3. Start a server and verify

From this `windows/` folder in PowerShell:

```powershell
docker compose up -d --build python-dsp
python scripts/smoke_test.py --server python_dsp
```

## 4. Collect traces

```powershell
python scripts/sweep.py --server python_dsp --rates 10 25 50
```

Traces land in `traces\`. See the root `README.md` for the guided labs and the research exercise.

## Windows-specific notes

- Use `python`, not `python3`, in all commands.
- **Virtualisation overhead**: with the WSL2 backend, containers run inside a
  lightweight VM. Expect *absolute* service times to be slower and noisier
  than on native Linux, and CPU-bound calibration (the Go server's synthetic
  workload) to run below its nominal speed. Your *relative* results and
  modelling conclusions are still valid — just do all your calibration and
  validation on the same machine, and report which platform you used.
- **File sharing**: keep this repository on the Windows filesystem
  (`C:\...`) or entirely inside WSL — mixing the two makes the bind-mounted
  `data/live_logs/` slow.
- If a sweep captures no rows, check Docker Desktop → Containers → logs for
  the service, and confirm the `data/live_logs/` bind mount exists.

---

## Windows platform investigation (Lab 4 extension)

On native Linux, `body_parse_ms` (the time the server spends reading the
HTTP request body) is a constant ~0.1 ms at every load level. On Windows
with the WSL2 backend you will observe something different — and explaining
it is a worthwhile exercise in understanding what your measurement tool
actually measures.

### What you will see

Run calibration sweeps at two rates far apart, e.g. 10 rps and 50 rps:

```powershell
python scripts/sweep.py --server python_dsp --rates 10 50 --duration 90
```

Then inspect the per-stage columns in the server-side traces:

```powershell
python -c "
import csv, statistics, os
base = r'traces\python_dsp_1c'
for rate in [10, 50]:
    import glob
    files = sorted(glob.glob(os.path.join(base, f'python_dsp_{rate}rps_run*.csv')))
    bp = []
    for f in files[-1:]:
        for row in csv.DictReader(open(f)):
            if str(row.get('status_code','')).startswith('2'):
                bp.append(float(row['body_parse_ms']))
    print(f'{rate} rps  body_parse p50={sorted(bp)[len(bp)//2]:.2f}ms  service p50 ~ stable')
"
```

You should find `body_parse_ms` is roughly **15–20 ms at 10 rps** and
**< 0.1 ms at 50 rps** — a 100–200× difference for the same server doing
the same work.

### Why this happens

The load generator opens a **new TCP connection for every request**. On
WSL2, each new connection must cross the Windows → WSL2 virtual network
boundary: TCP handshake, virtual NIC, then the body travels the same path.
At **low rates** the server is idle for most of the inter-arrival interval
(~90 ms idle at 10 rps). When the next request arrives, its body is still
in transit when Gunicorn calls the Flask handler — Flask must wait for it,
and that wait shows up as `body_parse_ms`. At **high rates** the server is
nearly continuously busy. New request bodies arrive while a previous request
is still being processed and pile up in the OS receive buffer; by the time
the server reads the next one, the data is already there.

The key insight: `body_parse_ms` here is a property of the *platform*
(virtualised network latency × connection-setup pattern), not a property of
the *server*. It is rate-dependent in a way that has nothing to do with the
DSP pipeline.

### Consequences for Lab 4 and Lab 5

**Lab 4:** you will notice that `response_ms` (= `body_parse_ms` +
`service_ms`) is *higher at low rates than at high rates* — Checkpoint 4c
will show p95 going *down* as rate increases instead of up. This is the
platform artefact above, not a queueing effect. Verify by checking that
`service_ms` is stable across rates (it should be ~3.3 ms for python_dsp
regardless of load). For your DES calibration, use `service_ms` as the
service demand, not `response_ms`.

**Lab 5:** because WSL2 scheduling introduces occasional multi-millisecond
pauses, the server-side tail (p99) is heavier than a simple DES can
predict. A KS distance of **0.15–0.30** ("moderate") is a realistic best
result on this platform, not a sign of a broken model. Score your
prediction against the trial-to-trial KS first — if your model KS is
within 2–3× the trial-to-trial KS, the model is capturing most of what is
capturable.

### Optional: eliminate the artefact with persistent connections

The artefact is caused by per-request connection setup. You can remove it
by editing `scripts/dsp_aes_load.py` to reuse a `requests.Session()`:

Find the section that sends each request and replace the bare
`requests.post(...)` call with `session.post(...)` where `session` is a
`requests.Session()` created once before the load loop. With persistent
connections, `body_parse_ms` drops to < 0.5 ms at all rates on WSL2 —
the calibration data becomes stationary, Lab 5 KS improves, and your
results will be much closer to the Linux reference numbers.

Compare the two versions and note the difference in `body_parse_ms`,
`response_ms`, and your Lab 5 KS score. This comparison is itself a
small experiment in how measurement infrastructure affects conclusions.
