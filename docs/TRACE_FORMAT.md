# Trace Format Reference

`scripts/sweep.py` collects TWO CSVs per (server, rate, run) — the same
experiment measured from two independent vantage points:

```
traces/<server_folder>/<tag>_<rate>rps_run<NN>.csv          server-side (internal)
traces/<server_folder>/<tag>_<rate>rps_run<NN>_client.csv   client-side (external)
traces/<server_folder>/<tag>_<rate>rps_run<NN>_meta.json    run metadata
```

Run numbers auto-increment; existing traces are never overwritten.

## Client-side trace (external measurement)

Written by the load generator (`--client-log`): one row per request as the
CLIENT observed it, treating the server as a black box.

| Column | Meaning |
|---|---|
| `send_unix_ns` | When the client sent the request (Unix epoch ns) |
| `client_response_ms` | Send until the complete response was received |
| `status_code` | HTTP status (0 = no response / transport error) |
| `ok` | 1 if the request succeeded |
| `error` / `method` | Error text (dsp/sqlite) or HTTP method (apache) |

`client_response_ms` includes everything the server-side `response_ms`
includes PLUS connection setup, network transit, kernel accept-queue wait,
and client-side scheduling delays. It is always ≥ the server-side value for
the same request, and it is the only view a real user of the service has.
See `LAB_GUIDE.md` Lab 2 for the comparison exercise.

## Server-side trace (internal measurement)

Written by the server itself, with timestamps taken inside the process.

### Columns common to all servers

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
