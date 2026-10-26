# Working on this repository

1. Read `MODEL_LOG.md` first. It records every change, the evidence behind it, what was tried and rejected, and
   the pitfalls already hit. Do not repeat an experiment listed as rejected without new evidence.
2. Follow the validation protocol in `MODEL_LOG.md` before pushing any change to the model, pricing, bars, grade
   weights, schedule or data sources: smoke test, offline re-pricing of the latest graded week, backtest check.
3. Append an entry to `MODEL_LOG.md` for every change: date, what, why, evidence, revert condition. Add any new
   pitfall to its list. A change that is not in the log did not happen.
4. After each graded week, add a post-mortem to `MODEL_LOG.md`: record, calibration (claimed vs hit), results by
   market, side, signal and grade, and what changed because of it.
5. `python tests/smoke_test.py` must pass before every push. `TACKLE_FAKE_DATA=1 TACKLE_FAKE_ODDS=1` run the
   pipeline on synthetic data.
6. Secrets: `ODDS_API_KEY` and `PARLAY_API_KEY` are GitHub Actions secrets. Never print or commit their values.
7. Schedules are in UTC in `.github/workflows/*.yml`; the user is in Edmonton (Mountain time).
