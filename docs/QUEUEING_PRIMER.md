# Queueing Primer — the Theory You Need

This is the minimum background to work on the platform. Any COMP9334 textbook
covers these topics in depth; this page fixes the notation used here.

## Request timing decomposition

Every request passes through two phases, both measured by the servers:

```
|--- queue_ms ---|--- service_ms ---|
|-------------- response_ms --------|
```

- **service_ms** — time the server actively processes the request.
- **queue_ms** — time spent waiting before processing starts.
- **response_ms = queue_ms + service_ms** — what the client experiences.

At low load, `queue_ms ≈ 0` and response ≈ service. As load grows, waiting
time comes to dominate. Predicting that growth is the whole game.

## Kendall notation: M/G/c

A queueing system is described as *arrival process / service distribution /
number of servers*:

- **M** ("Markovian") arrivals — a Poisson process: independent, exponential
  inter-arrival times. The platform's load generators produce exactly this.
- **G** ("General") service — service times follow some arbitrary
  distribution; you estimate it from data.
- **c** — the number of parallel workers. A single-worker server is M/G/1.

## Utilisation

```
rho = lambda × E[S] / c
```

with `lambda` the arrival rate (req/s), `E[S]` the mean service time (s), and
`c` the worker count. `rho` is the fraction of capacity in use. As `rho → 1`
waiting times grow without bound; above 1 the system is unstable and has no
steady state. Always compute `rho` before interpreting any measurement.

## Operational laws (distribution-free sanity checks)

These identities hold in any stable system, whatever the distributions:

- **Utilisation law**: `U = X × E[S]` (X = throughput)
- **Little's law**: `E[N] = X × E[R]` (N = number in system, R = response time)

Use them to validate your measurement pipeline before trusting any model
built on it.

## Comparing distributions: CDF and KS distance

The **empirical CDF** at value x is the fraction of requests with response
time ≤ x. Overlaying the predicted and observed CDFs shows exactly where they
disagree.

The **Kolmogorov–Smirnov (KS) distance** is the largest vertical gap between
two CDFs:

```
KS = max over x of | F_observed(x) − F_predicted(x) |
```

It ranges from 0 (identical) to 1 (disjoint), is unit-free, and is the primary
score used by `scripts/evaluate_prediction.py`. Note its blind spot: KS is
usually maximised near the middle of the distribution, so also inspect tail
percentiles (p95/p99) when tail latency is what you care about.

## Discrete event simulation in one paragraph

A DES for a queueing system keeps a virtual clock and processes events
(arrivals, service completions) in time order. For each arriving request:
draw or replay a service time, assign the request to a free worker or place it
in the queue, and record when it finishes. The output is a synthetic trace of
response times — directly comparable to a measured trace. The power of DES is
that arrival times and service times can come from *your data* rather than
from closed-form assumptions; the risk is that the simulation quietly encodes
structural assumptions (one shared queue, service independent of load, FIFO
order) that the real server may not satisfy.
