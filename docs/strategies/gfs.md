# GFS strategy: where to find things

- **Rules (the truth):** `gfs_spec.md`
- **Implementation choices where the spec is open:** `gfs_interpretation.md`
- **Parameters:** `config/strategies.yaml` under `gfs`
- **Code:** `src/niftyta/backtest/gfs.py` (signals and simulator), `src/niftyta/pipeline/gfs_run.py` (runner)
- **Run:** `.venv/bin/python scripts/gfs.py RELIANCE`
