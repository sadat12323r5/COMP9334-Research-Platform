# COMP9334 Research Platform — Capacity Prediction for Containerised Servers

> **Given a measured trace of real requests to a containerised server, can you
> accurately predict what the response-time distribution will look like at a
> higher load — without running the server at that load?**

Capacity planners face this question constantly: traffic will double next
month — will the p99 latency still meet the SLO, or do we need more replicas?
Running the production system at double load just to find out is expensive and
risky. This platform lets you attack the question scientifically: real servers,
real measurements, and your own predictive model, validated statistically
against ground truth that you collect yourself.

**Contents:**
[Learning Outcomes](#learning-outcomes) ·
[Repository Layout](#repository-layout) ·
[The Servers](#the-servers-under-test) ·
[Quickstart](#quickstart-5-minutes) ·
[Guided Labs](#the-guided-labs) ·
[The Research Exercise](#the-research-exercise) ·
[Queueing Primer](#queueing-primer) ·
[Trace Format](#trace-format-reference) ·
[Troubleshooting](#troubleshooting)

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

Pick the folder matching your operating system. Each is self-contained — the
same seven servers, load generators, and scripts — and has a short README with
OS-specific setup steps.

```
COMP9334-Research-Platform/
├── linux/       Docker Engine on native Linux
├── windows/     Docker Desktop on Windows (WSL2 backend)
└── mac/         Docker Desktop on macOS (Intel & Apple Silicon)
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

You now have real measured traces — two per run, in fact: a **server-side**
trace (timestamps written inside the server) and a **client-side** trace (the
load generator's external view of the same requests). Comparing them is one of
the first exercises. Now start the guided labs below.

**Requirements**: Docker (Engine or Desktop) with Compose v2; Python 3.10+
with `requests`, `cryptography` (load generation) and `numpy`, `scipy`,
`matplotlib`, `pandas` recommended for analysis.

---

# The Guided Labs

Work through these in order. Each lab ends with a **checkpoint**: a validation
you must pass before moving on. If a checkpoint fails, something is wrong with
your setup or your understanding — fix it now, because every later result
builds on it.

Commands are written for Linux/macOS (`python3`, `/`). On Windows use `python`
and `\`. Always run from your platform folder (`linux/`, `windows/`, `mac/`).

## Lab 0 — Setup and smoke test

```bash
docker compose up -d --build python-dsp
python3 scripts/smoke_test.py --server python_dsp
```

**Expected output** (numbers will vary, structure must not):

```
smoke test: python_dsp (compose service 'python-dsp') at http://localhost:8085/process
...
[OK] NN trace rows captured in data/live_logs/python_dsp_requests.csv
```

> **Checkpoint 0** — the smoke test prints `[OK]`. If it prints `[FAIL]`, work
> through its checklist (container running? port free? `data/live_logs/`
> writable?) before continuing.

## Lab 1 — Understand the load generator

The generators in `scripts/` are **open-loop Poisson** sources: they draw
exponential inter-arrival times with mean 1/rate and send each request at its
scheduled instant *whether or not earlier responses have returned*. This
matches the arrival assumptions of the queueing models you will build. (A
closed-loop tool — one that waits for a response before sending the next
request — would throttle itself exactly when the system gets interesting.
Understand this difference; it is a classic measurement mistake.)

Run one directly and read every line of its output:

```bash
python3 scripts/dsp_aes_load.py --url http://localhost:8085/process \
    --rate 20 --duration 30 --seed 1
```

**Expected output:**

```
Building signal pool: 200 packets x 1024 samples (seed=1) ...
Warmup (5 s) -> http://localhost:8085/process
Load test: rate=20.0 rps, duration=30.0 s, verify=False

--- Results ---
sent=~600  ok=~600  err=0  achieved_rps=~20  elapsed=30.0s
client latency (ms):  p50=...  p95=...  p99=...  max=...
```

Things to note:

- **Warmup**: the first 5 seconds are a gentle warm-up. Its requests DO appear
  in the server's trace — decide explicitly whether to trim them in analysis.
- **sent vs ok vs err**: at low rate on a healthy server, `err` must be 0.
- **achieved_rps**: the rate actually delivered. The generator is a real
  program on a real machine; at high rates it may not keep up (see Lab 3).
- **seed**: fixes the arrival sequence — the same seed reproduces the same
  arrival times. Use different seeds for repeat trials, and record them.

> **Checkpoint 1** — at `--rate 20`, `achieved_rps` is within 5% of 20 and
> `err=0`. Compute the expected number of requests (rate × duration ≈ 600)
> and confirm `sent` is close to it.

## Lab 2 — Two measurement systems: server-side vs client-side

There are two independent ways to measure the same experiment, and this
platform gives you both:

1. **Internal (server-side)**: every server timestamps each request as it
   processes it and appends a row to its CSV in `data/live_logs/` — arrival
   time, queueing time, service time, response time, per-stage timings.
2. **External (client-side)**: the load generator records, for every request,
   when it sent it and how long until the complete response came back
   (`--client-log`). This treats the server as a black box — the only thing a
   real user of the system could ever observe.

`sweep.py` captures **both** automatically:

```bash
python3 scripts/sweep.py --server python_dsp --rates 20 --duration 60
```

This produces, in `traces/python_dsp_1c/`:

```
python_dsp_20rps_run01.csv          <- server-side trace
python_dsp_20rps_run01_client.csv   <- client-side trace
python_dsp_20rps_run01_meta.json    <- rate, seed, duration, timestamps
```

Now compare them. Compute, for each trace, the mean and p50/p95/p99 of the
response time (server: `response_ms` with `status_code` 2xx; client:
`client_response_ms` with `ok=1`).

What you should find, and must be able to explain:

- **Row counts differ slightly** — the server trace includes the warm-up
  requests; the client trace covers only the measured window.
- **Client ≥ server, always, per percentile.** The client sees everything the
  server sees *plus* TCP connection handling, network transit, and time spent
  scheduled-out inside the client itself. On localhost this gap can still be
  large — tens of milliseconds — because the generator opens a fresh
  connection per request. The gap is not "error"; it is a different system
  boundary.
- The two views can *disagree about saturation*: near overload, a server's own
  trace may look calm while client latency explodes, because requests are
  piling up in the kernel accept queue **before** the server ever timestamps
  them. The server cannot see a queue that forms in front of it.

> **Checkpoint 2** — produce a table: {mean, p50, p95, p99} × {server trace,
> client trace}. Verify (a) client ≥ server for every entry, and (b) within
> the server trace, `queue_ms + service_ms ≈ response_ms` for every row
> (spot-check 10 rows). Write two sentences: what does each measurement
> system see that the other cannot?

When you model this system, you must choose which boundary you are modelling.
Both choices are defensible; mixing them silently is not.

## Lab 3 — Find the saturation point (and never trust ours)

A single-worker server that takes E[S] milliseconds per request can complete
at most ~1000/E[S] requests per second. Beyond that the system is **unstable**:
the queue grows without bound, latency explodes, and no steady-state
measurement means anything. Running experiments there is pointless — you must
know where the cliff is.

**Procedure** (use the `go` server — its behaviour is the cleanest):

```bash
docker compose up -d --build app        # the Go server, port 8080
python3 scripts/sweep.py --server go --rates 50 --duration 30
```

1. From the 50 rps server trace, estimate E[S] = mean of `service_ms`.
2. Predict capacity: λ_max ≈ 1000 / E[S] (single worker).
3. Sweep upward — e.g. `--rates 100 200 400` then approach your predicted
   λ_max — watching for the three saturation signatures:
   - `achieved_rps` falls below ~90% of the target rate, or
   - errors/timeouts appear, or
   - p99 response time is an order of magnitude above its low-rate value
     and grows with every rate step.
4. Record your measured saturation rate and compare with the prediction.

**Indicative values from our reference machine** (6-core laptop, native Linux,
servers pinned to 1 core). *Yours will differ — that is the point of this lab.
Docker Desktop on Windows/macOS typically saturates 2–10× earlier.*

| Server | E[S] at low rate | Indicative saturation |
|---|---|---|
| `go` | ~2.0 ms | ~450–500 rps |
| `apache_msg` | ~2.0 ms | ~400–500 rps |
| `apache_dsp` | ~1.2 ms | ~400–450 rps |
| `python_dsp` | ~3.2 ms | ~300 rps theoretical — **but see warning** |
| `go_sqlite` | ~3.4 ms | ~250–300 rps |
| `node_dsp`, `java_dsp` | < 0.5 ms | beyond the generator's reach |
| 3-core variants | as 1c | up to ~3× the 1c figure |

**⚠ The generator saturates too.** A single Python load-generator process on a
typical laptop cannot deliver much more than ~100–200 rps of the heavier DSP
payloads. If `achieved_rps` plateaus **and** the server trace shows no
queueing (`queue_ms` still ≈ 0), the bottleneck is your *client*, not the
server — you have measured nothing about the server's limit. Check for this
explicitly before declaring saturation. (Workarounds: run several generator
processes in parallel with different seeds, or accept the client ceiling and
study a slower server.)

> **Checkpoint 3** — for the `go` server: report E[S], predicted λ_max,
> measured saturation rate, and whether they agree within ~±25%. State which
> of the three saturation signatures you observed, and show one piece of
> evidence that it was the *server* (not the generator) that saturated.
> Then compute utilisation ρ = λ·E[S]/1000 for each rate you ran, and confirm
> the misbehaviour starts as ρ approaches 1.

If prediction and measurement *disagree* badly for some other server, do not
assume you made a mistake — investigate. Capacity formulas embed assumptions
(one worker, service time independent of load); a server that breaks the
formula is breaking an assumption, and finding out which one is exactly the
research question this platform exists to explore.

## Lab 4 — Calibration sweeps: collect the data you will model from

Pick your server. Choose 3–4 rates that keep ρ comfortably below ~0.5 (use
your Lab 3 numbers), and collect **at least 3 repeat trials** per rate:

```bash
python3 scripts/sweep.py --server python_dsp --rates 10 25 50 --duration 90 --trials 3
```

Then validate the dataset with the two **operational laws** — identities that
hold for ANY stable queueing system, whatever the distributions:

- **Utilisation law**: ρ = λ · E[S]. λ here is the *achieved* rate — compute
  it from the trace itself (number of arrivals ÷ span of `arrival_unix_ns`),
  never from the target you asked for.
- **Little's law**: E[N] = λ · E[R], where E[R] is mean response time and
  E[N] is the mean number of requests in the system. Estimate E[N] from the
  trace directly: sum of all `response_ms` ÷ span of the trace in ms.

> **Checkpoint 4** — for every (rate, trial): a table of achieved λ, E[S], ρ,
> E[R], and Little's-law E[N]. Verify (a) achieved λ within 5% of target,
> (b) ρ < 0.6 everywhere, (c) run-to-run variation of p95 at the same rate is
> small compared to the differences *between* rates (if it is not, you cannot
> attribute anything to load — collect more trials), and (d) Little's law
> holds within ~10% when cross-checked against a direct estimate.

## Lab 5 — Predict, then validate

1. Using **only** your Lab 4 low-rate traces, build a model of the server (see
   [The Research Exercise](#the-research-exercise) for method options).
2. Choose a target rate meaningfully above your calibration rates (but below
   the Lab 3 saturation point — predictions about an unstable system are
   untestable). Produce a **predicted sample of response times** and save it
   as a one-column CSV in ms.
3. Only after the prediction is frozen, measure reality:
   ```bash
   python3 scripts/sweep.py --server python_dsp --rates 75 --duration 90 --trials 3
   ```
4. Score yourself:
   ```bash
   python3 scripts/evaluate_prediction.py \
       --observed traces/python_dsp_1c/python_dsp_75rps_run04.csv \
       --predicted my_prediction.csv
   ```

Two honest-practice rules. First, decide **before** measuring what "close
enough" means (a KS threshold, a p95/p99 relative-error budget) — moving the
goalposts after seeing the answer is self-deception, not validation. Second,
score against *each* repeat trial: if your model-vs-reality KS is within the
trial-to-trial KS spread, your model is as good as the measurement noise
allows anyone to be.

> **Checkpoint 5** — a validation table: KS and p95/p99 relative error for
> your prediction against each of ≥3 trials at the target rate, alongside the
> trial-vs-trial values. One paragraph: where is your model weakest (bulk or
> tail?), and which assumption do you suspect?

A prediction that fails Checkpoint 5 with a *diagnosed cause* is worth more
than one that passes silently. The servers on this platform are chosen so
that simple models work beautifully on some and fail interestingly on others
— which is which, and why, is yours to discover.

---

# The Research Exercise

The labs give you the measurement skills; this is the research question, in
four stages matching the learning outcomes.

## Which servers should you model?

You are **not** expected to model all eleven configurations. But the zoo is
not arbitrary: each configuration rewards a different modelling idea. The
architecture column below — together with your own measurements and the
server's source code, which you are encouraged to read — should suggest what
kind of model to try. Whether your first candidate survives contact with the
data is the research question.

| Config | Architecture | Worth asking yourself |
|---|---|---|
| `go` | 1 goroutine, FIFO channel | the simplest case there is — and it logs the service time it *intended* next to the one it delivered, so a simulation can be checked piece by piece |
| `python_dsp` | 1 sync worker, 1 core | how far does the simplest textbook model take you, if you fit the service distribution from data instead of assuming one? |
| `python_dsp_mc` | 3 workers on 3 cores, one shared socket | three workers — but is it one queue or three? what would each imply for waiting times? |
| `node_dsp` | 1 event loop | an event loop serves one thing at a time — is that the same thing as a FIFO queue? |
| `node_dsp_mc` | 3-process cluster behind one port | how do requests get distributed among the processes, and does it matter? (the `pid` column knows) |
| `java_dsp` | 4 threads on **1** core | what does "number of servers" even mean when there are more workers than cores? |
| `java_dsp_mc` | 3 threads on 3 cores | look closely at the start of a run — is the server the same server all the way through? |
| `apache_dsp` | many worker processes on 1 core | when several processes share one core, what happens to the time each individual request takes? |
| `apache_msg` | Apache + a shared file store, GET/POST mix | two kinds of requests share one server — do they deserve the same treatment in a model? |
| `go_sqlite` | worker + SQLite database | a request can wait in more than one place here — where does the queue really form? |
| `go_sqlite_mc` | 3 workers + a database that serialises writes | three workers, but only one may write at a time — what is limiting whom? |

The intended scope is **two servers**:

1. **Core (everyone): `python_dsp`.** Everyone modelling the same core server
   makes results comparable and mistakes easy to diagnose. Build the full
   Stage 2–4 pipeline here first; a working pipeline on an easy server is
   worth more than a broken one on a hard server. (The `go` server from
   Lab 3 is its synthetic cousin — the ideal sanity check for your first
   simulation.)
2. **Challenge (choose one from the table).** Run your pipeline from the core
   server unchanged first, watch where its predictions fail, and let the
   failure — plus the question in the table — point you to a better model.
   Explaining *why* the simple model broke is worth as much as the fix.

Ambitious pairs or groups covering several rows of the table end up with a
comparative study of when each kind of model is the right one — which is
exactly what a capacity planner needs to know.

**Stage 1 — Platform and measurement** = Labs 0–4 above.

**Stage 2 — Parameter extraction.** From your low-rate traces, characterise:
the **arrival process** (are inter-arrival times exponential? plot them), the
**service-time distribution** (histogram; try fitting lognormal, gamma,
Weibull; check the fit, don't assume it), and the **number of parallel
workers** `c` the architecture provides (read the server's source and its
docker-compose entry).

**Stage 3 — Build a predictor.** Options, roughly in order of effort:

- **Analytical queueing formulas** (M/M/1, M/G/1 mean-value results) — fast,
  but only predict means/moments, not full distributions.
- **Discrete event simulation** — simulate arrivals, a queue, and `c` workers;
  draw service times from your fitted distribution (or resample the empirical
  one). Predicts the *full* distribution; the centrepiece method here.
- **Statistical / ML approaches** — regression on summary statistics,
  bootstrap extrapolation. Useful as comparison baselines — but beware:
  a model trained only on low-rate data has never seen the nonlinear latency
  growth near saturation, and most ML regressors cannot extrapolate beyond
  their training range. Test this rather than assuming it.

Whatever you choose, calibrate **only** on low-rate data.

**Stage 4 — Predict, then validate** = Lab 5 above.

### Questions worth investigating

1. How far above your calibration rates can you predict before accuracy
   collapses? Where is the server's saturation point, and what happens to
   your model's validity there?
2. Does the same modelling approach work equally well for all servers?
   Compare a CPU-bound server against the SQLite-backed one, or a
   single-worker against a multi-worker variant.
3. Do the model's *assumptions* survive contact with the data? For example:
   is the service-time distribution actually independent of the arrival rate?
   Is a multi-worker server really one shared queue? Design an experiment
   that tests the assumption directly rather than guessing.
4. When your predictions fail, can you localise the cause — wrong service
   distribution, wrong queueing structure, or a measurement/runtime artefact
   (warm-up, garbage collection, caching)?

### Deliverables (suggested)

- Your collected traces and the exact commands used to produce them.
- Your predictor's code and a description of its assumptions.
- A validation report: predicted vs observed CDF plots, KS distances,
  percentile errors, and repeat-run variability at each target rate.
- A discussion: where the model works, where it fails, and *why*.

---

# Queueing Primer

The minimum theory needed here; any COMP9334 textbook covers it in depth.

**Request timing decomposition.** Every request passes through two phases,
both measured by the servers:

```
|--- queue_ms ---|--- service_ms ---|
|-------------- response_ms --------|
```

At low load, `queue_ms ≈ 0` and response ≈ service. As load grows, waiting
time comes to dominate. Predicting that growth is the whole game.

**Kendall notation M/G/c** — *arrival process / service distribution / number
of servers*. **M** ("Markovian") arrivals = a Poisson process (what the load
generators produce). **G** ("General") service = an arbitrary distribution you
estimate from data. **c** = parallel workers; a single-worker server is M/G/1.

**Utilisation.** `rho = lambda × E[S] / c` — the fraction of capacity in use
(λ in req/s, E[S] in seconds). As ρ → 1 waiting grows without bound; above 1
the system is unstable and has no steady state. Compute ρ before interpreting
any measurement.

**Operational laws** (distribution-free sanity checks): the utilisation law
`U = X × E[S]` and Little's law `E[N] = X × E[R]` hold in any stable system.
Use them to validate your measurement pipeline before trusting any model
built on it (Lab 4).

**Comparing distributions.** The **empirical CDF** at x is the fraction of
requests with response time ≤ x; overlaying predicted and observed CDFs shows
exactly where they disagree. The **Kolmogorov–Smirnov (KS) distance** is the
largest vertical gap between two CDFs — 0 = identical, 1 = disjoint,
unit-free. It is the primary score in `evaluate_prediction.py`. Know its blind
spot: KS is usually maximised near the middle of the distribution, so also
inspect p95/p99 errors when tail latency is what you care about.

**DES in one paragraph.** A discrete event simulation keeps a virtual clock
and processes events (arrivals, service completions) in time order: for each
arriving request, draw or replay a service time, assign it to a free worker or
queue it, record when it finishes. The output is a synthetic trace of response
times — directly comparable to a measured trace. Its power: arrivals and
service times can come from *your data* rather than closed-form assumptions.
Its risk: the simulation quietly encodes structural assumptions (one shared
queue, service independent of load, FIFO order) that the real server may not
satisfy.

---

# Trace Format Reference

`scripts/sweep.py` collects TWO CSVs per (server, rate, run) — the same
experiment measured from two vantage points — plus metadata:

```
traces/<server_folder>/<tag>_<rate>rps_run<NN>.csv          server-side (internal)
traces/<server_folder>/<tag>_<rate>rps_run<NN>_client.csv   client-side (external)
traces/<server_folder>/<tag>_<rate>rps_run<NN>_meta.json    rate, seed, duration
```

Run numbers auto-increment; existing traces are never overwritten.

### Server-side trace (internal)

| Column | Meaning |
|---|---|
| `arrival_unix_ns` | Request arrival timestamp, Unix epoch nanoseconds |
| `service_ms` | Active processing time (ms) |
| `queue_ms` | Waiting time before processing began (ms) |
| `response_ms` | `queue_ms + service_ms` — what the server delivered |
| `status_code` | HTTP status; **filter to 2xx rows for analysis** |
| `route`, `method`, `pid` | Request routing / process metadata |

Sort by `arrival_unix_ns` before analysis; concurrent writers can interleave
rows slightly out of order. Per-server extras: the DSP servers log per-stage
timings (`decrypt_ms`, `fir_ms`, `encrypt_ms`, …) whose sum approximates
`service_ms`; the Go server logs `service_target_ms` (the *intended* service
demand) next to the wall-clock `service_ms` — comparing them is instructive;
the SQLite servers log `insert_ms`, `select_ms`, `db_ms`.

### Client-side trace (external)

Written by the load generator (`--client-log`; sweep.py passes it
automatically): one row per request as the CLIENT observed it.

| Column | Meaning |
|---|---|
| `send_unix_ns` | When the client sent the request (Unix epoch ns) |
| `client_response_ms` | Send until the complete response was received |
| `status_code` | HTTP status (0 = no response / transport error) |
| `ok` | 1 if the request succeeded |
| `error` / `method` | Error text (dsp/sqlite) or HTTP method (apache) |

`client_response_ms` includes everything `response_ms` includes PLUS
connection setup, network transit, kernel accept-queue wait, and client-side
scheduling. It is always ≥ the server-side value for the same request, and it
is the only view a real user of the service has (Lab 2).

### Gotchas

1. **Status filtering**: overloaded servers return 503 rows with zeroed
   timings — keep them for throughput/loss accounting, exclude them from
   response-time distributions.
2. **Header repair**: servers write their CSV header only once per process
   start. `sweep.py` handles this automatically; if you collect traces by
   hand and the first line is data, copy the header string from
   `scripts/sweep.py`.
3. **Clock basis**: server-side timestamps exclude client-side and network
   overhead — that is what the client trace is for.

---

# Troubleshooting

| Symptom | Likely cause |
|---|---|
| `[FAIL] no trace rows` in smoke test | container not running, wrong port, or `data/live_logs/` not writable by the container user — `chmod 666` the live CSV |
| `achieved_rps` far below target, server `queue_ms ≈ 0` | client-side ceiling — your generator, not the server, is the bottleneck (Lab 3 warning) |
| errors like `Connection refused` | server not up on that port — `docker compose ps` |
| massive p99 at modest rates on Windows/macOS | Docker Desktop virtualisation overhead — recalibrate everything on your own machine, compare nothing across machines |
| first line of a hand-collected CSV is data, not a header | you truncated the live log yourself; use `sweep.py`, or copy the header string from `scripts/sweep.py` |
