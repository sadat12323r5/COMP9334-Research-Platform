# Platform Setup — Windows (Docker Desktop, WSL2 backend)

## 1. Install prerequisites

1. Install **Docker Desktop for Windows** and enable the **WSL2 backend**
   (Settings → General → "Use the WSL 2 based engine").
2. Install **Python 3.10+** from python.org (tick "Add python.exe to PATH").
3. In Docker Desktop → Settings → Resources, give Docker at least **4 CPUs**
   and 4 GB RAM.

## 2. Install Python dependencies

```powershell
python -m pip install requests cryptography numpy scipy matplotlib pandas
```

## 3. Start a server and verify

From this `windows/` folder in PowerShell:

```powershell
docker compose up -d --build python-dsp
python scripts/smoke_test.py --server python_dsp
```

## 4. Collect traces

```powershell
python scripts/sweep.py --server python_dsp --rates 10 25 50
```

Traces land in `traces\`. See `..\docs\RESEARCH_BRIEF.md` for the exercise.

## Windows-specific notes

- Use `python`, not `python3`, in all commands.
- **Virtualisation overhead**: with the WSL2 backend, containers run inside a
  lightweight VM. Expect *absolute* service times to be slower and noisier
  than on native Linux, and CPU-bound calibration (the Go server's synthetic
  workload) to run below its nominal speed. Your *relative* results and
  modelling conclusions are still valid — just do all your calibration and
  validation on the same machine, and report which platform you used.
- **File sharing**: keep this repository on the Windows filesystem
  (`C:\...`) or entirely inside WSL — mixing the two makes the bind-mounted
  `data/live_logs/` slow.
- If a sweep captures no rows, check Docker Desktop → Containers → logs for
  the service, and confirm the `data/live_logs/` bind mount exists.
