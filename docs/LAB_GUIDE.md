# Lab Guide — Guided Measurement and Prediction Exercises

Work through these labs in order. Each lab ends with a **checkpoint**: a
validation you must pass before moving on. If a checkpoint fails, something is
wrong with your setup or your understanding — fix it now, because every later
result builds on it.

Commands are written for Linux/macOS (`python3`, `/`). On Windows use `python`
and `\`. Always run from your platform folder (`linux/`, `windows/`, `mac/`).

---

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

---

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

---

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

---

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

---

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

---

## Lab 5 — Predict, then validate

This is the research exercise (`RESEARCH_BRIEF.md` has the full statement):

1. Using **only** your Lab 4 low-rate traces, build a model of the server —
   DES driven by resampled service times, an analytical M/G/1 formula, a
   statistical extrapolation, anything you can defend.
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

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `[FAIL] no trace rows` in smoke test | container not running, wrong port, or `data/live_logs/` not writable by the container user — `chmod 666` the live CSV |
| `achieved_rps` far below target, server `queue_ms ≈ 0` | client-side ceiling — your generator, not the server, is the bottleneck (Lab 3 warning) |
| errors like `Connection refused` | server not up on that port — `docker compose ps` |
| massive p99 at modest rates on Windows/macOS | Docker Desktop virtualisation overhead — recalibrate everything on your own machine, compare nothing across machines |
| first line of a hand-collected CSV is data, not a header | you truncated the live log yourself; `sweep.py` re-writes headers automatically — use it, or copy the header string from `scripts/sweep.py` |
