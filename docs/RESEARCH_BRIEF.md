# Research Brief — Predicting Response Times at Unmeasured Loads

## Objective

Using only measurements taken at **low** arrival rates, predict the full
response-time distribution of a chosen server at a **higher** arrival rate,
then validate the prediction against a real measurement at that rate.

This mirrors the four learning outcomes of the platform: build the
experimental setup, extract model parameters from measurements, build a
simulation (or another predictive model), and use it for prediction.

## Suggested Workflow

### Stage 1 — Platform setup and measurement (Learning Outcome 1)

Work through `LAB_GUIDE.md` (Labs 0–4) — it walks this stage step by step
with validation checkpoints, including the two measurement systems
(server-side vs client-side traces) and finding your machine's saturation
points. In summary:

1. Pick one server to start with (`python_dsp` is a friendly first choice).
2. Start it, smoke-test it, and run a sweep at several low rates, e.g.:
   ```bash
   python3 scripts/sweep.py --server python_dsp --rates 10 25 50
   ```
3. Open a trace CSV and understand every column (`docs/TRACE_FORMAT.md`).
   Verify basic sanity: does achieved throughput match the target rate? Do
   `queue_ms + service_ms ≈ response_ms`?
4. Verify the operational laws on your data — these are distribution-free
   identities that must hold in any stable system:
   - Utilisation law: `rho = lambda × E[S]`
   - Little's law: `E[N] = lambda × E[R]`
   If they do not hold, find the measurement problem before modelling.

### Stage 2 — Parameter extraction (Learning Outcome 2)

From your low-rate traces, characterise:
- the **arrival process** (are inter-arrival times exponential? plot them),
- the **service-time distribution** (histogram; try fitting standard families
  such as lognormal, gamma, Weibull; check the fit, don't assume it),
- the **number of parallel workers** the architecture provides (read the
  server's source and docker-compose entry — this is `c` in queueing terms).

### Stage 3 — Build a predictor (Learning Outcome 3)

Build a model that maps *(arrival rate, your extracted parameters)* to a
predicted response-time distribution. Options, roughly in order of effort:

- **Analytical queueing formulas** (e.g. M/M/1, M/G/1 mean-value results) —
  fast, but only predict means/moments, not full distributions.
- **Discrete event simulation** — simulate arrivals, a queue, and `c` workers;
  draw service times from your fitted distribution (or resample the empirical
  one). This predicts the *full* distribution and is the centrepiece method
  of this platform.
- **Statistical / ML approaches** — e.g. regression on summary statistics
  across rates, bootstrap extrapolation. Useful as comparison baselines.

Whatever you choose, the model must be calibrated **only** on low-rate data.

### Stage 4 — Predict, then validate (Learning Outcome 4)

1. Choose a target rate meaningfully above your calibration rates.
2. Produce a predicted sample of response times (a CSV of numbers in ms).
3. Only now run the real sweep at the target rate.
4. Score the prediction:
   ```bash
   python3 scripts/evaluate_prediction.py \
       --observed traces/<server>/<trace at target rate>.csv \
       --predicted my_prediction.csv
   ```
5. Repeat the measurement at least 3 times. Is the run-to-run KS variation
   smaller than your model-vs-reality KS? If not, you cannot distinguish model
   error from noise.

## Questions Worth Investigating

These get progressively harder; strong projects go beyond the first two.

1. How far above your calibration rates can you predict before accuracy
   collapses? Where is the server's saturation point, and what happens to
   your model's validity there?
2. Does the same modelling approach work equally well for all servers? Compare
   a CPU-bound server against the SQLite-backed one, or a single-worker
   against a multi-worker variant.
3. Do the model's *assumptions* survive contact with the data? For example:
   is the service-time distribution actually independent of the arrival rate?
   Is a multi-worker server really one shared queue? Design an experiment that
   tests the assumption directly rather than guessing.
4. When your predictions fail, can you localise the cause — wrong service
   distribution, wrong queueing structure, or a measurement/runtime artefact
   (warm-up, garbage collection, caching)?

## Deliverables (suggested)

- Your collected traces and the exact commands used to produce them.
- Your predictor's code and a description of its assumptions.
- A validation report: predicted vs observed CDF plots, KS distances,
  percentile errors, and repeat-run variability at each target rate.
- A discussion: where the model works, where it fails, and *why*.

## Practical Pitfalls (read before your first full sweep)

- **Warm-up**: JIT compilation (Java) and interpreter/module loading (Python)
  make the first requests slower. Decide explicitly whether to discard a
  warm-up window, and say so in your report.
- **Achieved vs target rate**: the generator reports achieved rps; at high
  rates a single client machine may not keep up. Always use the achieved rate
  in your analysis.
- **Stability**: if the arrival rate exceeds the service capacity
  (utilisation ≥ 1), the queue grows without bound and no steady-state
  prediction is meaningful. Check utilisation at every rate.
- **One server at a time**: containers share pinned CPU cores by design.
- **Open-loop vs closed-loop**: the generators here are open-loop (they do not
  wait for responses before sending the next request). This matches the
  Poisson assumptions of most queueing models — do not replace them with a
  closed-loop tool without understanding the difference.
