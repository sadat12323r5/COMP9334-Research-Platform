# Platform Setup — Linux (native Docker Engine)

Native Linux is the reference platform: containers run directly on the host
kernel with real cgroup CPU pinning, so timing measurements have the least
virtualisation noise.

## 1. Install Docker Engine + Compose

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"   # then log out and back in
```

## 2. Install Python dependencies

```bash
python3 -m pip install --user requests cryptography numpy scipy matplotlib pandas
```

(On Ubuntu 23.10+ add `--break-system-packages`, or use a venv.)

## 3. Start a server and verify

```bash
docker compose up -d --build python-dsp
python3 scripts/smoke_test.py --server python_dsp
```

## 4. Collect traces

```bash
python3 scripts/sweep.py --server python_dsp --rates 10 25 50
```

Traces land in `traces/`. See `../docs/RESEARCH_BRIEF.md` for the exercise.

## Linux-specific notes

- **File permissions**: some containers write the trace log as a non-root
  user (e.g. Apache's `www-data`, uid 33). The scripts set the live log
  world-writable automatically; if you create `data/live_logs` files by hand
  and a server logs nothing, check permissions first.
- **CPU pinning is real here**: `cpuset: "0"` in docker-compose.yml pins a
  container to physical core 0. Keep heavy processes (browsers, IDE
  indexing, the load generator itself if you can) off the pinned cores while
  measuring — they would contend with the server and contaminate service
  times.
- **One server at a time**, as everywhere: the single-core services all pin
  to core 0 by design.
