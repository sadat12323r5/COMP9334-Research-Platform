"""
evaluate_prediction.py — Statistically validate a predicted response-time
distribution against a measured trace.

You predict the response-time distribution at some target arrival rate (using
DES, queueing formulas, ML — your choice), THEN run the real sweep at that rate
once, and use this script to score how close your prediction was.

Inputs:
  --observed   A trace CSV collected by sweep.py (uses its response_ms column,
               status 2xx rows only).
  --predicted  A CSV holding your predicted response times in ms: either a
               single unnamed column of numbers, or any CSV with a column named
               response_ms or sim_response_ms.

Metrics reported:
  * KS distance — the maximum vertical gap between the two empirical CDFs
    (0 = identical distributions, 1 = no overlap).
  * Mean, p50, p90, p95, p99 of both distributions and the relative error of
    each predicted percentile.

Usage:
  python3 scripts/evaluate_prediction.py \
      --observed traces/python_dsp_1c/python_dsp_75rps_run01.csv \
      --predicted my_prediction.csv
"""
import argparse
import csv
import math


def read_observed(path):
    vals = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not str(row.get("status_code", "")).startswith("2"):
                continue
            try:
                v = float(row["response_ms"])
                if math.isfinite(v):
                    vals.append(v)
            except (KeyError, ValueError):
                pass
    if not vals:
        raise SystemExit(f"No 2xx response_ms rows found in {path}")
    return sorted(vals)


def read_predicted(path):
    vals = []
    with open(path, newline="", encoding="utf-8") as f:
        sample = f.read(4096)
        f.seek(0)
        has_header = any(c.isalpha() for c in sample.split("\n")[0])
        if has_header:
            for row in csv.DictReader(f):
                for col in ("response_ms", "sim_response_ms"):
                    if col in row:
                        try:
                            v = float(row[col])
                            if math.isfinite(v):
                                vals.append(v)
                        except ValueError:
                            pass
                        break
        else:
            for line in f:
                for tok in line.strip().split(","):
                    if tok:
                        try:
                            v = float(tok)
                            if math.isfinite(v):
                                vals.append(v)
                        except ValueError:
                            pass
    if not vals:
        raise SystemExit(
            f"No numeric predictions found in {path} "
            "(expected a response_ms/sim_response_ms column or plain numbers)")
    return sorted(vals)


def ks_distance(a, b):
    """KS distance between two sorted samples, and the x where it occurs."""
    pts = sorted(set(a) | set(b))
    i = j = 0
    n, m = len(a), len(b)
    d, at = 0.0, 0.0
    for x in pts:
        while i < n and a[i] <= x:
            i += 1
        while j < m and b[j] <= x:
            j += 1
        gap = abs(i / n - j / m)
        if gap > d:
            d, at = gap, x
    return d, at


def pct(sv, p):
    idx = p / 100 * (len(sv) - 1)
    lo, hi = int(math.floor(idx)), int(math.ceil(idx))
    return sv[lo] if lo == hi else sv[lo] * (1 - (idx - lo)) + sv[hi] * (idx - lo)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--observed", required=True)
    ap.add_argument("--predicted", required=True)
    args = ap.parse_args()

    obs = read_observed(args.observed)
    pred = read_predicted(args.predicted)

    d, at = ks_distance(obs, pred)
    print(f"n_observed={len(obs)}  n_predicted={len(pred)}")
    print(f"\nKS distance = {d:.4f}   (largest CDF gap at ~{at:.3f} ms)")
    print(f"\n{'metric':>8} {'observed':>12} {'predicted':>12} {'rel.err':>9}")
    rows = [("mean", sum(obs) / len(obs), sum(pred) / len(pred))]
    for p in (50, 90, 95, 99):
        rows.append((f"p{p}", pct(obs, p), pct(pred, p)))
    for name, o, s in rows:
        rel = (s - o) / o if o else float("nan")
        print(f"{name:>8} {o:>12.3f} {s:>12.3f} {rel:>+8.1%}")
    print("\nInterpretation guide: KS < 0.05 excellent | 0.05-0.15 good | "
          "0.15-0.30 moderate | > 0.30 poor.\n"
          "Also check WHERE the gap is: a gap in the tail means your model "
          "misses tail latency even if KS looks acceptable.")


if __name__ == "__main__":
    main()
