# COMP9334 Research Platform — Capacity Prediction for Containerised Servers

## The Research Question

> **Given a measured trace of real requests to a containerised server, can you
> accurately predict what the response-time distribution will look like at a
> higher load — without running the server at that load?**

Capacity planners face this question constantly: traffic will double next
month — will the p99 latency still meet the SLO, or do we need more replicas?
Running the production system at double load just to find out is expensive and
risky. This platform lets you attack the question scientifically: real servers,
real measurements, and your own predictive model, validated statistically
against ground truth that you collect yourself.

## Learning Outcomes

By completing the exercises on this platform you will learn to:

1. **Set up an experimental capacity-planning platform** — containerised
   servers, an open-loop Poisson load generator, and per-request measurement
   of queueing and service times.
2. **Process measurements to obtain the parameters for discrete event
   simulation** — extract arrival processes, service-time distributions, and
   utilisation from raw traces.
3. **Build a discrete event simulation (DES) for different servers** — from a
   single-worker FIFO queue to multi-worker systems.
4. **Use the simulation for prediction** — forecast the response-time
   distribution at loads you have not measured, then validate the forecast
   against a real measurement using statistical distance metrics.

You are encouraged to go beyond DES: analytical queueing formulas, bootstrap
methods, and machine-learning approaches are all valid — the platform only
fixes the *question* and the *validation standard*, not the method.

## Repository Layout

Pick the folder matching your operating system. Each is self-contained: the
same seven servers, the same load generators, the same scripts — only the
setup instructions differ.

```
COMP9334-Research-Platform/
├── linux/       Docker Engine on native Linux
├── windows/     Docker Desktop on Windows (WSL2 backend)
├── mac/         Docker Desktop on macOS (Intel & Apple Silicon)
└── docs/        Research brief, queueing primer, trace format reference
```

Inside each platform folder:

```
├── docker-compose.yml    All server definitions with CPU pinning
├── servers/              Seven server implementations (5 languages)
├── scripts/              Load generators + sweep/smoke-test/evaluation tools
├── data/live_logs/       Live CSV logs written by the running containers
└── traces/               Your collected experiment traces land here
```

## The Servers Under Test

All servers expose an HTTP endpoint and log **every request** to a CSV with
nanosecond arrival timestamps and a decomposition of response time into
queueing and service components. The DSP servers run an identical CPU-bound
pipeline (AES-256 decrypt → 64-tap FIR filter → AES-256 encrypt), so
differences you measure come from the *runtime and architecture*, not the
workload.

| Service (compose name) | Port | Language / architecture |
|---|---|---|
| `app` | 8080 | Go — single goroutine FIFO queue, synthetic lognormal work |
| `apache` | 8082 | PHP/Apache — messaging app with a shared file store |
| `apache-dsp` | 8083 | PHP/Apache — DSP pipeline, prefork worker processes |
| `node-dsp` | 8084 | Node.js — single event loop, DSP pipeline |
| `python-dsp` | 8085 | Python/Gunicorn — one worker process, DSP pipeline |
| `java-dsp` | 8086 | Java — fixed thread pool, DSP pipeline |
| `go-sqlite` | 8087 | Go — SQLite-backed I/O-bound service |
| `node-dsp-mc` | 8088 | Node.js cluster — 3 processes on 3 cores |
| `python-dsp-mc` | 8089 | Gunicorn — 3 workers on 3 cores |
| `java-dsp-mc` | 8090 | Java — 3-thread pool on 3 cores |
| `go-sqlite-mc` | 8091 | Go + SQLite WAL — 3 workers on 3 cores |

Run **one server at a time**: they are pinned to the same CPU cores on purpose
so that experiments are comparable — running two at once makes them contend.

## Quickstart (5 minutes)

```bash
cd linux/          # or windows/ or mac/ — see that folder's README first
docker compose up -d --build python-dsp
python3 scripts/smoke_test.py --server python_dsp
python3 scripts/sweep.py --server python_dsp --rates 10 25 --duration 30
head -3 traces/python_dsp_1c/python_dsp_10rps_run01.csv
```

You now have real measured traces. Read `docs/RESEARCH_BRIEF.md` for the full
exercise, `docs/QUEUEING_PRIMER.md` for the theory you need, and
`docs/TRACE_FORMAT.md` for the exact meaning of every CSV column.

## The Rules of the Game

1. **Calibrate low, predict high.** Build your model only from traces
   collected at *low* arrival rates. Predict the response-time distribution at
   a *higher* rate. Only then measure the higher rate and score yourself with
   `scripts/evaluate_prediction.py`.
2. **Validate statistically.** Report the KS distance between predicted and
   observed CDFs, plus percentile errors (p50/p95/p99). One number on one run
   is not evidence — repeat runs and report variability.
3. **Explain failures.** The most interesting result is not a good KS — it is
   understanding *why* a model breaks for a particular server. When your
   prediction fails, investigate the architecture before blaming the data.

## Requirements

- Docker (Engine or Desktop) and Docker Compose v2
- Python 3.10+ with: `requests`, `cryptography` (for load generation);
  `numpy`, `scipy`, `matplotlib`, `pandas` recommended for analysis
