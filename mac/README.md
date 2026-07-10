# Platform Setup — macOS (Docker Desktop, Intel & Apple Silicon)

## 1. Install prerequisites

1. Install **Docker Desktop for Mac** (Apple Silicon and Intel builds both
   work; all base images used here are multi-architecture).
2. Python 3.10+ (preinstalled `python3` is fine, or use Homebrew).
3. In Docker Desktop → Settings → Resources, give Docker at least **4 CPUs**
   and 4 GB RAM — the multi-core servers pin to 3 cores inside the VM.

## 2. Install Python dependencies

```bash
python3 -m pip install requests cryptography numpy scipy matplotlib pandas
```

## 3. Start a server and verify

From this `mac/` folder:

```bash
docker compose up -d --build python-dsp
python3 scripts/smoke_test.py --server python_dsp
```

## 4. Collect traces

```bash
python3 scripts/sweep.py --server python_dsp --rates 10 25 50
```

Traces land in `traces/`. See `../docs/RESEARCH_BRIEF.md` for the exercise.

## macOS-specific notes

- **Containers run inside a VM** on macOS. CPU pinning (`cpuset`) applies to
  the VM's virtual cores, not physical ones, and the hypervisor adds
  scheduling noise. Absolute timings will differ from native Linux; your
  modelling and validation methodology is unaffected — calibrate and validate
  on the same machine and report the platform.
- **Apple Silicon**: images build natively for arm64. If a build pulls an
  x86 image and warns about emulation, expect that server to run slower
  under Rosetta/QEMU — prefer another server or note it in your report.
- **Bind-mount performance**: Docker Desktop file sharing (VirtioFS) is fast
  enough for the CSV logging here, but keep the repo on the local disk, not
  a network share.
