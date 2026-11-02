"""End-to-end test on the synthetic league. Run from the repo root:  python tests/smoke_test.py
Copies the repo to a temp folder, runs the daily job, an odds pull and grading, and checks that the
backtest recovers the effects planted in the synthetic data."""
import datetime as dt
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
check(any("boosted corrector" in r["predictor"] for r in bt["predictors"]), "boosted corrector scored walk-forward in the backtest")
check(all(p.get("proj_gbm") is None or p["proj_gbm"] > 0 for p in proj) and any(p.get("proj_gbm") for p in proj), "projections carry the corrector's own number")
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
import config as C
from pipeline import grade as G
from pipeline import model as M
from tests.fake_data import planted_crews
seasons, pw, sched, snaps, inj, H, status, vol = R.load_all()
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
check(all("lock_block" in b and "lock_eligible" in b and "in_role_games" in b for b in priced) and not any(b.get("lock_block") and b.get("five") for b in priced),
      f"priced lines carry the lock-eligibility checklist and no blocked line is a lock ({sum(1 for b in priced if b.get('lock_block'))} blocked of {len(priced)})")
check(all(not (b.get("lock_block") and "Over" == b.get("side") and "fading" in str(b.get("why"))) for b in priced) and not any("Over" == b.get("side") and "fading an outlier" in str(b.get("why")) for b in priced),
      "no Over is sold as fading an outlier")
check(any("role-shift" in r["predictor"] for r in bt["predictors"]) and isinstance(bt.get("weak_spots"), list), "backtest reports the role-shift factors and the weak-spot table")
check(all(any(k in r["predictor"] for r in bt["predictors"]) for k in ("per-snap base", "vacancy rule", "dome corners", "outlier damping")), "backtest reports the per-snap, vacancy, dome and outlier-damping pieces")
check(any(p.get("group") == "DL" and p.get("press_pg") is not None for p in proj) and all(p.get("press_pg") is None for p in proj if p.get("group") != "DL")
      and not any("pressure" in r["predictor"] for r in bt["predictors"]), "lineman pressure profile carried for the card, DL only, with no model row (rejected in round 5)")
check(all("fp_comb" in p and "fp_rel_comb" in p for p in proj) and meta.get("fantasypros_rows") == 0 and "espn_injury_rows" in meta, "outside consensus and outside injury feed wired through (empty on synthetic data)")
sys.path.insert(0, str(tmp))
from pipeline import sources as _S
_payload = {"injuries": [{"injuries": [
    {"status": "Suspension", "athlete": {"displayName": "C.J. Gardner-Johnson", "team": {"abbreviation": "BUF"}, "position": {"abbreviation": "S"}}, "details": {"returnDate": "2026-11-09"}},
    {"status": "Injured Reserve", "athlete": {"displayName": "Some Player Jr.", "team": {"abbreviation": "WSH"}}},
    {"status": "Active", "athlete": {"displayName": "Mack Wilson Sr.", "team": {"abbreviation": "ARI"}}},
    {"status": "Questionable", "athlete": {"displayName": "Max Melton", "team": {"abbreviation": "LAR"}}}]}]}
_e = _S.parse_espn_injuries(_payload, 2026, 8)
check(list(_e.status) == ["suspended", "injured reserve", "questionable"] and list(_e.team) == ["BUF", "WAS", "LA"], "ESPN injury feed parsed: statuses mapped, Active dropped, team codes translated")
_lg = pd.DataFrame(dict(season=[2026, 2026], week=[8, 8], team=["LA", "BUF"], name_key=["maxmelton", "cjgardnerjohnson"], player_id=["00-1", "00-2"], status=["Out", ""], practice=["DNP", "Full"]))
_m = _S.merge_injury_sources(_lg, _e).set_index(["team", "name_key"])
check(_m.loc[("LA", "maxmelton"), "status"] == "Out" and _m.loc[("BUF", "cjgardnerjohnson"), "status"] == "suspended" and _m.loc[("BUF", "cjgardnerjohnson"), "practice"] == "Full"
      and _m.loc[("BUF", "cjgardnerjohnson"), "player_id"] == "00-2" and ("WAS", "someplayer") in _m.index, "injury sources merged: more severe status wins, league practice status and ids kept, outside-only listings added")
_fp = _S.parse_fantasypros('x "rows":[{"id":1,"player":{"name":"Jack Campbell","team":"DET"},"def_tackle":7.3,"def_assist":4.1},{"id":2,"player":{"name":"Devin Lloyd","team":"JAC"},"def_tackle":6.0,"def_assist":3.0}] y')
check(len(_fp) == 2 and abs(float(_fp.fp_comb.iloc[0]) - 11.4) < 1e-9 and _fp.team.iloc[1] == "JAX", "FantasyPros consensus rows parsed with team codes translated")
check(any(p.get("share_pred") is not None and p.get("tsnaps_exp") for p in proj) and all(0 <= (p.get("share_pred") or 0) <= 1 for p in proj), "projections carry an expected snap share and team snaps")
check(any(":low" in k or "under 60%" in str(d.get("group", "")) for d in bt["dispersion"] for k in [d.get("group", "")]), "dispersion estimated separately for low expected snap share")
check(meta.get("freshness", {}).get("stats_through_week") is not None, "data freshness (stats and snaps through week) reported")
check(any(r["predictor"].startswith("Solo tackles: full model") for r in bt["predictors"]) and any("solo" in d["group"] for d in bt["dispersion"]) and 0.9 <= bt.get("scale_solo", 0) <= 1.1,
      "solo tackles scored in the backtest with their own dispersion and level")
check(any("without league solo drift" in r["predictor"] for r in bt["predictors"]) and all(0.85 <= (p.get("solo_drift") or 1.0) <= 1.15 for p in proj), "league solo drift applied and reported")
check(all("far_from_line" in b and "p_claim" in b and "segment_adj" in b for b in priced), "priced lines carry the far-from-line flag, the claimed chance and the segment correction")
check(not any(b.get("five") and b.get("side") == "Over" for b in priced) and all("Over side" in str(b.get("lock_block")) for b in priced if b.get("side") == "Over"), "no Over is a lock while Overs are ineligible")
check(all(b.get("ev", 0) >= 0.10 - 1e-9 or "fading" in str(b.get("why")) or "role" in str(b.get("why")) for b in priced if b.get("pick") == "Over"), "an Over pick clears the higher Over bar unless a signal backs it")
check(all(b.get("mkt_line") is not None and abs(b["proj"] - b["proj_model"]) <= abs(b["mkt_line"] - b["proj_model"]) + 1e-9 for b in priced), "pricing mean sits between the model and the market line")
check(any(b.get("cons_n", 0) > 0 for b in priced), "consistency (games cleared) computed from game logs")
check(all((b.get("p_claim") or 0) >= 0.55 - 1e-9 and (b.get("ev") or 0) >= 0.06 - 1e-9 for b in priced if b.get("pick") in ("Over", "Under")), "every pick clears the claimed-chance floor and the full return bar")
check(all(str(b.get("over_link", "")).startswith("https://") and str(b.get("under_link", "")).startswith("https://") for b in priced), "priced lines carry the book's bet-slip links for both sides")
picks = pd.read_csv(tmp / "data/picks.csv") if (tmp / "data/picks.csv").exists() else pd.DataFrame()
check(len(picks) >= 1, f"picks logged ({len(picks)})")
check(picks.drop_duplicates(["player", "market", "side", "line"]).shape[0] == len(picks), "one logged pick per player/line (best price only)")
check({"lock", "grade", "consistency", "payout"} <= set(picks.columns) and picks.grade.isin(["A", "B", "C"]).all(), "logged picks carry their grade, lock score, consistency and payout")
five = picks[picks.five.fillna(False).astype(bool)] if "five" in picks.columns else pd.DataFrame()
flagged = G.lock_blocked(picks)               # never locks, whatever their score
others = picks[~picks.player.isin(five.player) & ~flagged] if len(five) else picks
_segs = G.segment_key(five) if len(five) else pd.Series([], dtype=str)
_full = {k for k, v in _segs.value_counts().items() if v >= C.LOCKS_PER_SEGMENT}
_better = others[(others.lock > five.lock.min() + 1e-9) & ~G.segment_key(others).isin(_full)] if len(five) and len(others) else others.iloc[0:0]
check(1 <= len(five) <= 5 and five.player.nunique() == len(five) and _better.empty and (_segs.value_counts() <= C.LOCKS_PER_SEGMENT).all(),
      f"weekly five flagged: top lock scores, one per player, at most {C.LOCKS_PER_SEGMENT} of a kind ({len(five)}; kinds {dict(_segs.value_counts())})")
check(sum(1 for b in bets if b.get("five")) == len(five), "locks marked on the board")
parlays = pd.read_csv(tmp / "data/parlays.csv") if (tmp / "data/parlays.csv").exists() else pd.DataFrame()
check(len(parlays) >= 2 and parlays.parlay_id.nunique() >= 1 and parlays.groupby("parlay_id").size().between(2, 4).all(), f"recommended parlay built ({parlays.parlay_id.nunique() if len(parlays) else 0} parlay, {len(parlays)} legs)")
check(len(parlays) and parlays.player.nunique() == len(parlays) and parlays.units.between(0.1, 1.0).all(), "parlay legs are distinct players with a stake between 0.1 and 1 unit")
pj = json.loads((tmp / "docs/data/parlays.json").read_text())
check(all(l["market"] == "player_tackles_assists" for q in pj for l in q["legs"]), "parlay legs are combined-tackle lines only")
check(len(pj) >= 1 and pj[0]["n_legs"] == len(pj[0]["legs"]) and sum(1 for b in bets if b.get("parlay")) == len(parlays), "parlay written for the site and marked on the board")
_wl = json.loads((tmp / "docs/data/lines_week.json").read_text())
check(len(_wl) >= len(bets) and all({"player", "market", "line", "book", "commence_time"} <= set(r) for r in _wl), f"every line pulled this week written for My board ({len(_wl)} lines)")
check(all(q.get("finished") is False for q in pj) and json.loads((tmp / "docs/data/meta.json").read_text()).get("next_pull"), "open parlays flagged as not finished and the next pull time published")
sys.path.insert(0, str(tmp))
import run as _R
_sat = dt.datetime(2026, 10, 31, 20, 0, tzinfo=dt.timezone.utc)      # Saturday 2 pm Edmonton
_g = [dict(kickoff="2026-11-01T18:00:00+00:00")]                      # Sunday noon Edmonton
check(_R.next_pull(_sat, _g) == "2026-10-31T21:00+00:00" and _R.next_pull(_sat + dt.timedelta(hours=8), _g) == "2026-11-01T13:00+00:00"
      and _R.next_pull(dt.datetime(2026, 11, 1, 16, 30, tzinfo=dt.timezone.utc), _g) == "2026-11-01T17:00+00:00", "next pull: Saturday 3 pm, then Sunday 7 am after the last Saturday pull, then an hour before Sunday's first kickoff")

# grading: fake picks on finished week-6 games with a closing snapshot
from pipeline import grade as G
week6 = pw[(pw.season == 2026) & (pw.week == 6)].sort_values("comb", ascending=False).head(3)
rows, snap = [], []
for i, r in enumerate(week6.itertuples()):
    side = "Over" if i % 2 == 0 else "Under"
    rows.append(dict(season=2026, week=6, player=r.player, team=r.team, opp="", market="player_tackles_assists", side=side, line=r.comb - 0.5,
                     book="DraftKings", odds=-110, event_id=f"X{i}", commence_time="2026-10-18T17:00:00Z", pulled_at="20261018T120000Z"))
    snap.append(dict(event_id=f"X{i}", commence_time="2026-10-18T17:00:00Z", book="DraftKings", market="player_tackles_assists",
                     player=r.player, line=r.comb + 0.5, over_odds=-110, under_odds=-110, pulled_at="20261018T165500Z"))
rows[0].update(five=True, lock=80.0, grade="A"); rows[1].update(five=True, lock=75.0, grade="A"); rows[2].update(five=False)
pd.DataFrame(rows).to_csv("data/picks.csv", index=False)
(Path("data/odds/2026/wk06")).mkdir(parents=True, exist_ok=True)
pd.DataFrame(snap).to_csv("data/odds/2026/wk06/20261018T165500Z.csv", index=False)
graded, summary = G.grade(pw)
check(list(graded.result) == ["Win", "Loss", "Win"], f"picks graded correctly ({list(graded.result)})")
# a pick on a player with no stat row in a game that is in the books is void, not pending; a game not yet played stays pending
_v = pd.read_csv(G.PICKS); _v = pd.concat([_v, _v.iloc[[0]].assign(player="Nobody Atall", event_id="void_test")], ignore_index=True); _v.to_csv(G.PICKS, index=False)
_gv, _ = G.grade(pw)
check("Void" in set(_gv.result) and int((_gv.result == "Void").sum()) == 1, f"a bet on a player who did not play in a finished game is void ({_gv.result.tolist()})")
check(summary.get("by_side") and {x["key"] for x in summary["by_side"]} <= {"Over", "Under"} and all({"hit", "units", "pending"} <= set(x) for x in summary["by_side"]) and len(summary.get("by_side_market", [])) >= 1,
      f"record by side and by side-market carried ({[(x['key'], x['wins'], x['losses']) for x in summary['by_side']]})")
check(isinstance(summary.get("segments"), list) and isinstance(summary.get("market_watch"), list) and G.SEGMENTS.exists(), f"segment calibration and market watch computed ({len(summary.get('segments', []))} segments, {len(summary.get('market_watch', []))} watch rows)")
check(summary["by_grade"] and summary["by_grade"][0]["grade"] == "A" and all({"hit", "pushes", "pending", "staked", "stake"} <= set(g) for g in summary["by_grade"]),
      f"record by grade carries hit rate, pushes, pending and staked units ({[(g['grade'], g['wins'], g['losses']) for g in summary['by_grade']]})")
check(abs(summary["units"] - (2 * (100 / 110) - 1)) < 1e-6, f"units computed ({summary['units']:.3f})")
check(list(graded.clv_line) == [1.0, -1.0, 1.0], f"closing line value computed ({list(graded.clv_line)})")
check(summary["close_moved"] == 3 and abs(summary["beat_close_share"] - 2 / 3) < 1e-9, f"beat-the-close share counts only moved lines ({summary['beat_close_share']:.3f} of {summary['close_moved']})")
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
check(isinstance(summary.get("luck"), list) and all({"hit", "market_base", "lift", "verdict"} <= set(r) for r in summary["luck"]) and "Luck or skill" in (tmp / "data/weekly_five.md").read_text(), f"luck check computed against the whole market ({len(summary.get('luck') or [])} rows) and written to the weekly log")
check("Locks record: 1-1" in log and "| 2026 wk 6 | 2 | 1-1 |" in log and "Parlays record: 1-0" in log, "locks and parlays log written with records, week line and parlay line")

# scheduled pull slots and international windows, in Edmonton time
import datetime as _dt
from zoneinfo import ZoneInfo as _Z
_ed = _Z("America/Edmonton")
def _at(y, m, d, hh, mm):
    return _dt.datetime(y, m, d, hh, mm, tzinfo=_ed).astimezone(_dt.timezone.utc)
plan = R.auto_plan(now=_at(2026, 10, 29, 9, 4))     # Thursday 9:04 am
check(plan and plan.get("days") == ["2026-10-29", "2026-10-30"] and plan["key"] == "2026-10-29 09:00", f"Thursday 9 am slot covers Thursday and Friday games ({plan and plan.get('days')})")
late = R.auto_plan(now=_at(2026, 10, 29, 9, 27))     # a run 27 minutes late still serves the slot
check(late and late["key"] == "2026-10-29 09:00", "a late run still serves an unserved slot")
check(R.auto_plan(now=_at(2026, 10, 29, 9, 27), served={"2026-10-29 09:00"}) is None, "a served slot is not pulled twice")
check(R.auto_plan(now=_at(2026, 10, 29, 8, 50)) is None, "nothing is due before the first slot of the day")
two = R.auto_plan(now=_at(2026, 10, 29, 17, 40), served={"2026-10-29 09:00"})   # 10 am through 5:30 pm all unserved
check(two and two["key"] == "2026-10-29 17:30" and "2026-10-29 14:00" in two["also_served"] and len(two["also_served"]) == 8, "with several slots due, the latest is served and the stale ones marked")
sun = [dict(game_id="2026_09_A_B", home="B", away="A", kickoff=_at(2026, 11, 1, 11, 0).isoformat(), international=False),
       dict(game_id="2026_09_C_D", home="D", away="C", kickoff=_at(2026, 11, 1, 14, 25).isoformat(), international=False),
       dict(game_id="2026_09_E_F", home="F", away="E", kickoff=_at(2026, 11, 2, 18, 15).isoformat(), international=False)]
check(R.auto_plan(now=_at(2026, 11, 1, 6, 30), games=sun) is None, "Sunday: nothing due before the 7 am look")
plan = R.auto_plan(now=_at(2026, 11, 1, 8, 4), games=sun, served={"2026-11-01 07:00"})
check(plan and plan.get("days") == ["2026-11-01"] and plan.get("key") == "2026-11-01 08:00", f"Sunday: the 8 am look covers the whole Sunday slate ({plan and plan.get('reason')})")
plan = R.auto_plan(now=_at(2026, 11, 1, 9, 2), games=sun, served={"2026-11-01 07:00", "2026-11-01 08:00"})
check(plan and plan.get("key") == "2026-11-01 09:00" and plan.get("days") == ["2026-11-01"], "Sunday: hourly looks between the 8 am look and the pre-kickoff pull")
plan = R.auto_plan(now=_at(2026, 11, 1, 10, 3), games=sun, served={"2026-11-01 07:00", "2026-11-01 08:00", "2026-11-01 09:00"})
check(plan and plan.get("days") == ["2026-11-01"] and plan.get("key") == "2026-11-01 sunday-1h" and plan.get("also_served") == ["2026-11-01 10:00"], f"Sunday: the pull an hour before the first kickoff wins a tie with the fixed 10 am look ({plan and plan.get('reason')})")
check(R.auto_plan(now=_at(2026, 11, 1, 10, 33), games=sun, served={"2026-11-01 07:00", "2026-11-01 08:00", "2026-11-01 09:00", "2026-11-01 10:00", "2026-11-01 sunday-1h"}) is None, "Sunday: every Sunday pull is served once")
check(R.auto_plan(now=_at(2026, 11, 1, 6, 30)) is None and R.auto_plan(now=_at(2026, 11, 1, 11, 40), served={f"2026-11-01 {h:02d}:00" for h in range(7, 12)}) is None, "Sunday with no schedule loaded: only the fixed hourly looks are due")
check(dt.datetime(2026, 11, 2, 12, 0, tzinfo=R.EDMONTON).utcoffset() == dt.timedelta(hours=-6) and dt.datetime(2026, 10, 30, 12, 0, tzinfo=R.EDMONTON).utcoffset() == dt.timedelta(hours=-6),
      "Edmonton stays on UTC-6 through the November clock change (Alberta Time)")
plan = R.auto_plan(now=_at(2026, 11, 7, 18, 2), served={"2026-11-07 09:00"})      # Saturday 6:02 pm, after the clock change
check(plan and plan.get("days") == ["2026-11-07", "2026-11-08"] and plan["key"] == "2026-11-07 18:00", f"Saturday 6 pm slot covers Saturday and Sunday games in standard time ({plan and plan.get('days')})")
plan = R.auto_plan(now=_at(2026, 11, 6, 14, 5), served={"2026-11-06 12:00"})      # Friday 2:05 pm
check(plan and plan.get("days") == ["2026-11-07", "2026-11-08"] and plan["key"] == "2026-11-06 14:00", "Friday afternoon pulls cover the weekend's games as they post")
plan = R.auto_plan(now=_at(2026, 11, 9, 17, 30), served={"2026-11-09 09:00"})     # Monday 5:30 pm
check(plan and plan.get("days") == ["2026-11-09"], "Monday 5:30 pm slot covers the Monday game")
intl = [dict(game_id="2026_07_NO_PIT", home="PIT", away="NO", kickoff=_at(2026, 10, 25, 7, 30).isoformat(), international=True)]
_satslots = {f"2026-10-24 {h:02d}:00" for h in range(9, 22)}
p12 = R.auto_plan(now=_at(2026, 10, 24, 19, 50), games=intl, served=_satslots)   # Saturday slots already served
check(p12 and p12.get("teams") == ("PIT", "NO") and p12["key"].endswith("12h"), "international game pulled in the 12 h window even when the run is late")
sat = R.auto_plan(now=_at(2026, 10, 24, 19, 50), games=intl, served=_satslots - {"2026-10-24 19:00"})
check(sat and sat["key"] == "2026-10-24 19:00", "a due regular slot takes priority over an international window")
check(R.auto_plan(now=_at(2026, 10, 25, 5, 0), games=intl, served={"2026_07_NO_PIT 12h"}) is None, "no pull between the international windows once the 12 h one is served")
p1 = R.auto_plan(now=_at(2026, 10, 25, 6, 40), games=intl, served={"2026_07_NO_PIT 12h"})
check(p1 and p1["key"].endswith("1h"), "international game pulled in the 1 h window")
games = json.loads((tmp / "data/cache/games.json").read_text())
check(len(games) > 10 and all({"home", "away", "kickoff", "international"} <= set(g) for g in games), f"this week's games written with kickoff and international flag ({len(games)})")

print("\nALL CHECKS PASSED" if not fails else f"\n{len(fails)} CHECK(S) FAILED")
sys.exit(1 if fails else 0)
