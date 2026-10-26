"""End-to-end test on the synthetic league. Run from the repo root:  python tests/smoke_test.py
Copies the repo to a temp folder, runs the daily job, an odds pull and grading, and checks that the
backtest recovers the effects planted in the synthetic data."""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
tmp = Path(tempfile.mkdtemp()) / "repo"
def _ignore_live_data(d, names):
    """Copy the code but not the live outputs (odds snapshots, logged picks, caches, site JSON) so the test starts clean."""
    rel = os.path.relpath(d, ROOT)
    skip = {".git", "__pycache__"}
    if rel == "data":
        skip |= {"cache", "picks.csv", "parlays.csv", "retro_five.json", "weekly_five.md"}
    if rel == os.path.join("data", "odds"):
        skip |= {n for n in names if n.isdigit()}
    if rel == os.path.join("docs", "data"):
        skip |= {n for n in names if n.endswith(".json")}
    return skip
shutil.copytree(ROOT, tmp, ignore=_ignore_live_data)
env = dict(os.environ, TACKLE_FAKE_DATA="1", TACKLE_FAKE_ODDS="1", PYTHONPATH=str(tmp))
fails = []

def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

def run(*args):
    r = subprocess.run([sys.executable, "run.py", *args], cwd=tmp, env=env, capture_output=True, text=True)
    print(r.stdout.strip()); print(r.stderr.strip()[-2000:]) if r.returncode else None
    return r.returncode

check(run("daily") == 0, "daily job runs")
meta = json.loads((tmp / "docs/data/meta.json").read_text())
proj = json.loads((tmp / "docs/data/projections.json").read_text())
bt = json.loads((tmp / "docs/data/backtest.json").read_text())
check(meta["week"] == 7, f"upcoming week detected ({meta['week']})")
check(meta["formula_check_ok"], f"tackle formula self-check matched official totals ({meta['tackle_formula']})")
check(len(proj) > 300, f"projections built ({len(proj)})")

P = {r["predictor"]: r for r in bt["predictors"]}
check(P["Season average"]["mae"] < P["Last game"]["mae"], "season average beats last game")
check(P["Full model"]["mae"] < P["Full model without stat crew"]["mae"], "stat-crew factor improves accuracy")
check(P["Full model"]["mae"] < P["Full model without role bump"]["mae"], "role bump improves accuracy")
check(P["Full model"]["mae"] <= P["Season average"]["mae"], "full model at least matches season average")
lb = next((d for d in bt["dispersion"] if d["group"] == "LB"), None)
check(lb is not None and 0.6 <= lb["corrected"] <= 1.0, f"linebacker spread recovered near planted 0.75 ({lb and round(lb['corrected'], 2)})")
cal = bt["calibration"]
worst = max(abs(c["predicted"] - c["observed"]) for c in cal if c["n"] > 200)
check(worst < 0.06, f"over-probabilities calibrated (worst bucket off by {worst:.3f})")
check(bt["role"] and bt["role"]["actual_vs_avg_pct"] > 0.2, f"backups with a vacated starter beat their average ({bt['role'] and round(bt['role']['actual_vs_avg_pct'], 2)})")

# stat-crew estimates should track the planted crews
sys.path.insert(0, str(tmp)); os.chdir(tmp)
os.environ["TACKLE_FAKE_DATA"] = "1"
import run as R
from pipeline import model as M
from tests.fake_data import planted_crews
seasons, pw, sched, snaps, inj, H, status = R.load_all()
share, lg = M.crew_factors(H, 2026, 7)
planted = planted_crews()
common = [t for t in share if t in planted and t != "NEUTRAL"]
corr = np.corrcoef([share[t] for t in common], [planted[t] for t in common])[0, 1]
check(corr > 0.8, f"stat-crew rates recovered for every venue (correlation {corr:.2f} over {len(common)} stadiums)")
up = [p for p in proj if p["role_signal"]]
check(len(up) >= 6, f"role signals raised for backups whose starter is listed out ({len(up)})")

check(run("odds") == 0, "odds pull, pricing and pick logging run")
bets = json.loads((tmp / "docs/data/bets.json").read_text())
check(len(bets) > 50 and all(b["model_over"] is None or 0 <= b["model_over"] <= 1 for b in bets), f"lines priced ({len(bets)})")
priced = [b for b in bets if b.get("proj") is not None]
check(all(b.get("grade") in ("A", "B", "C") and 0 <= b.get("lock", -1) <= 100 for b in priced), "every priced line has a confidence grade and lock score")
check(all(b.get("mkt_line") is not None and abs(b["proj"] - b["proj_model"]) <= abs(b["mkt_line"] - b["proj_model"]) + 1e-9 for b in priced), "pricing mean sits between the model and the market line")
check(any(b.get("cons_n", 0) > 0 for b in priced), "consistency (games cleared) computed from game logs")
picks = pd.read_csv(tmp / "data/picks.csv") if (tmp / "data/picks.csv").exists() else pd.DataFrame()
check(len(picks) >= 1, f"picks logged ({len(picks)})")
check(picks.drop_duplicates(["player", "market", "side", "line"]).shape[0] == len(picks), "one logged pick per player/line (best price only)")
check({"lock", "grade", "consistency", "payout"} <= set(picks.columns) and picks.grade.isin(["A", "B", "C"]).all(), "logged picks carry their grade, lock score, consistency and payout")
five = picks[picks.five.fillna(False).astype(bool)] if "five" in picks.columns else pd.DataFrame()
others = picks[~picks.player.isin(five.player)] if len(five) else picks
check(1 <= len(five) <= 5 and five.player.nunique() == len(five) and (others.empty or five.lock.min() >= others.lock.max() - 1e-9), f"weekly five flagged: top lock scores, one per player ({len(five)})")
check(sum(1 for b in bets if b.get("five")) == len(five), "locks marked on the board")
parlays = pd.read_csv(tmp / "data/parlays.csv") if (tmp / "data/parlays.csv").exists() else pd.DataFrame()
check(len(parlays) >= 2 and parlays.parlay_id.nunique() >= 1 and parlays.groupby("parlay_id").size().between(2, 4).all(), f"recommended parlay built ({parlays.parlay_id.nunique() if len(parlays) else 0} parlay, {len(parlays)} legs)")
check(len(parlays) and parlays.player.nunique() == len(parlays) and parlays.units.between(0.1, 1.0).all(), "parlay legs are distinct players with a stake between 0.1 and 1 unit")
pj = json.loads((tmp / "docs/data/parlays.json").read_text())
check(len(pj) >= 1 and pj[0]["n_legs"] == len(pj[0]["legs"]) and sum(1 for b in bets if b.get("parlay")) == len(parlays), "parlay written for the site and marked on the board")

# grading: fake picks on finished week-6 games with a closing snapshot
from pipeline import grade as G
week6 = pw[(pw.season == 2026) & (pw.week == 6)].sort_values("comb", ascending=False).head(3)
rows, snap = [], []
for i, r in enumerate(week6.itertuples()):
    side = "Over" if i % 2 == 0 else "Under"
    rows.append(dict(season=2026, week=6, player=r.player, market="player_tackles_assists", side=side, line=r.comb - 0.5,
                     book="DraftKings", odds=-110, event_id=f"X{i}", commence_time="2026-10-18T17:00:00Z", pulled_at="20261018T120000Z"))
    snap.append(dict(event_id=f"X{i}", commence_time="2026-10-18T17:00:00Z", book="DraftKings", market="player_tackles_assists",
                     player=r.player, line=r.comb + 0.5, over_odds=-110, under_odds=-110, pulled_at="20261018T165500Z"))
rows[0].update(five=True, lock=80.0, grade="A"); rows[1].update(five=True, lock=75.0, grade="A"); rows[2].update(five=False)
pd.DataFrame(rows).to_csv("data/picks.csv", index=False)
(Path("data/odds/2026/wk06")).mkdir(parents=True, exist_ok=True)
pd.DataFrame(snap).to_csv("data/odds/2026/wk06/20261018T165500Z.csv", index=False)
graded, summary = G.grade(pw)
check(list(graded.result) == ["Win", "Loss", "Win"], f"picks graded correctly ({list(graded.result)})")
check(abs(summary["units"] - (2 * (100 / 110) - 1)) < 1e-6, f"units computed ({summary['units']:.3f})")
check(list(graded.clv_line) == [1.0, -1.0, 1.0], f"closing line value computed ({list(graded.clv_line)})")
f5 = summary["five"]
check(f5["wins"] == 1 and f5["losses"] == 1 and len(f5["weeks"]) == 1 and f5["weeks"][0]["running_wins"] == 1, f"weekly five tally ({f5['wins']}-{f5['losses']}, {len(f5['weeks'])} week)")
# a fake two-leg parlay on the same finished games: both legs cashed
legs = []
for i, r in enumerate(week6.head(2).itertuples()):
    side = "Over" if i % 2 == 0 else "Under"
    legs.append(dict(season=2026, week=6, slate="2026-10-18", parlay_id="2026-wk06-2026-10-18", leg=i + 1, player=r.player, team=r.team, opp="", market="player_tackles_assists",
                     side=side, line=r.comb - 0.5 if side == "Over" else r.comb + 0.5, book="DraftKings", odds=-110, p_side=0.65, lock=75.0, grade="A",
                     event_id=f"X{i}", commence_time="2026-10-18T17:00:00Z", n_legs=2, combined_decimal=(1 + 100 / 110) ** 2, combined_prob=0.65 ** 2, units=0.3, chosen_at="20261018T120000Z"))
pd.DataFrame(legs).to_csv("data/parlays.csv", index=False)
pq, psum = G.grade_parlays(pw)
check(len(pq) == 1 and pq.result.iloc[0] == "Win" and abs(pq.units_won.iloc[0] - 0.3 * ((1 + 100 / 110) ** 2 - 1)) < 1e-6 and psum["wins"] == 1, f"parlay graded ({pq.result.iloc[0] if len(pq) else 'none'}, {pq.units_won.iloc[0] if len(pq) else 0:+.3f}u)")
summary["parlays"] = psum
G.write_five_log(graded, summary, tmp / "data/weekly_five.md", pq)
log = (tmp / "data/weekly_five.md").read_text()
check("Locks record: 1-1" in log and "| 2026 wk 6 | 2 | 1-1 |" in log and "Parlays record: 1-0" in log, "locks and parlays log written with records, week line and parlay line")

# scheduled pull slots and international windows, in Edmonton time
import datetime as _dt
from zoneinfo import ZoneInfo as _Z
_ed = _Z("America/Edmonton")
def _at(y, m, d, hh, mm):
    return _dt.datetime(y, m, d, hh, mm, tzinfo=_ed).astimezone(_dt.timezone.utc)
plan = R.auto_plan(now=_at(2026, 10, 29, 9, 4))     # Thursday 9:04 am
check(plan and plan.get("days") == ["2026-10-29", "2026-10-30"], f"Thursday 9 am slot covers Thursday and Friday games ({plan and plan.get('days')})")
check(R.auto_plan(now=_at(2026, 10, 29, 11, 0)) is None, "Thursday 11 am is not a pull slot")
check(R.auto_plan(now=_at(2026, 11, 1, 9, 0)) is None, "Sunday 9 am is not a pull slot (none specified)")
plan = R.auto_plan(now=_at(2026, 11, 7, 18, 2))      # Saturday 6:02 pm, after the clock change
check(plan and plan.get("days") == ["2026-11-08"], f"Saturday 6 pm slot covers Sunday games in standard time ({plan and plan.get('days')})")
plan = R.auto_plan(now=_at(2026, 11, 9, 17, 30))     # Monday 5:30 pm
check(plan and plan.get("days") == ["2026-11-09"], "Monday 5:30 pm slot covers the Monday game")
intl = [dict(home="PIT", away="NO", kickoff=_at(2026, 10, 25, 7, 30).isoformat(), international=True)]
check(R.auto_plan(now=_at(2026, 10, 24, 19, 30), games=intl).get("teams") == ("PIT", "NO"), "international game pulled 12 h before kickoff")
check(R.auto_plan(now=_at(2026, 10, 25, 6, 30), games=intl).get("teams") == ("PIT", "NO"), "international game pulled 1 h before kickoff")
check(R.auto_plan(now=_at(2026, 10, 25, 5, 0), games=intl) is None, "no pull between the international windows")
games = json.loads((tmp / "data/cache/games.json").read_text())
check(len(games) > 10 and all({"home", "away", "kickoff", "international"} <= set(g) for g in games), f"this week's games written with kickoff and international flag ({len(games)})")

print("\nALL CHECKS PASSED" if not fails else f"\n{len(fails)} CHECK(S) FAILED")
sys.exit(1 if fails else 0)
