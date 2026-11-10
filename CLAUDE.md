# Working on this repository

0. The vision at the top of `MODEL_LOG.md` is the test for every change: easier site, timelier updates, or a more
   reliable weekly five. A change that serves none of these does not get pushed. The edge comes from what the
   market has not priced: never grade, rank or choose a pick by whether the book agrees with it.
1. Read `MODEL_LOG.md` first, in full: how the model works now, the evidence rules, the decision register, the
   rejected-experiments register, the open issues and the pitfalls already hit. `MODEL_LOG_ARCHIVE.md` holds the
   history behind it (research rounds, earlier post-mortems and changelog entries): search it before repeating an
   experiment. Do not repeat an experiment listed as rejected without new evidence.
2. Follow the evidence rules and the validation protocol in `MODEL_LOG.md` before pushing any change to the model,
   pricing, bars, stakes, schedule or data sources: smoke test; for a projection change the walk-forward test of
   the final projection, judged on the regulars who get lines; for a pricing rule the scoreboard against the
   market and a replay of the graded weeks; a real daily in a scratch copy. A rule the log marks frozen is not
   changed before its date unless a defect is found.
3. Append an entry to `MODEL_LOG.md` for every change: date, what, why, evidence, revert condition. Update the
   decision register or the rejected register with it, and add any new pitfall to its list. A change that is not
   in the log did not happen.
4. After each graded week, add a post-mortem to `MODEL_LOG.md`: record (with its likely range), calibration
   (claimed vs hit), results by market, side and grade, and what changed because of it. Start from the scoreboard
   against the market and the luck table (Track record tab, `data/weekly_five.md`): a kind of pick is evidence for
   the model only where lift over the whole board and beating the close agree with the record. A record alone
   proves nothing.
5. `python tests/smoke_test.py` must pass before every push. `TACKLE_FAKE_DATA=1 TACKLE_FAKE_ODDS=1` run the
   pipeline on synthetic data.
6. Secrets: `ODDS_API_KEY` and `PARLAY_API_KEY` are GitHub Actions secrets. Never print or commit their values.
7. Schedules are in UTC in `.github/workflows/*.yml`; the user is in Edmonton (UTC-6 all year since 2026-11-01).
8. After every push, read the result of the Test workflow on GitHub: it runs the smoke test on a clean machine
   with only `requirements.txt` installed. A red check is a failed push, whatever the test said locally.
