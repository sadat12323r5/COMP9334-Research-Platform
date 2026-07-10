# Trace Format Reference

`scripts/sweep.py` collects one CSV per (server, rate, run):

```
traces/<server_folder>/<tag>_<rate>rps_run<NN>.csv
traces/<server_folder>/<tag>_<rate>rps_run<NN>_meta.json
```

Run numbers auto-increment; existing traces are never overwritten.

## Columns common to all servers

| Column | Meaning |
|---|---|
| `arrival_unix_ns` | Request arrival timestamp, Unix epoch nanoseconds |
| `service_ms` | Active processing time (ms) |
| `queue_ms` | Waiting time before processing began (ms) |
| `response_ms` | `queue_ms + service_ms` (ms) — what the client saw |
| `status_code` | HTTP status; **filter to 2xx rows for analysis** |
| `route`, `method`, `pid` | Request routing / process metadata |

Sort by `arrival_unix_ns` before analysis; concurrent writers can interleave
rows slightly out of order.

## Per-server extras

- **DSP servers** (apache-dsp, node-dsp, python-dsp, java-dsp) additionally
  log per-stage timings of the pipeline (e.g. `decrypt_ms`, `fir_ms`,
  `encrypt_ms`; exact set varies slightly per runtime). Their sum
  approximates `service_ms`. Use these to localise *where* time changes.
- **Go server** (`app`) uses an extended schema starting `id,trace_id,...`
  and includes `service_target_ms` — the service demand the server *intended*
  (sampled from its configured distribution) as opposed to the wall-clock
  `service_ms` it actually took. Comparing the two is instructive.
- **SQLite servers** log `insert_ms`, `select_ms`, `db_ms` — the database
  portion of service time.

## Gotchas

1. **Status filtering**: overloaded servers return 503 rows with zeroed
   timings. Keep them for throughput/loss accounting, exclude them from
   response-time distributions.
2. **Header repair**: most servers write the CSV header only once per process
   start. `sweep.py` handles this automatically; if you collect traces by
   hand and the first line is data rather than a header, consult
   `scripts/sweep.py` for the correct header string per server.
3. **Clock basis**: all timestamps are taken server-side, so client-side
   network overhead is excluded. The load generators report client-side
   latency separately in their console output.
