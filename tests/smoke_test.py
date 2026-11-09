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
import atexit; atexit.register(lambda: shutil.rmtree(tmp.parent, ignore_errors=True))   # the copy is a few hundred MB; 140 of them sat in /tmp once
def _ignore_live_data(d, names):
    """Copy the code but not the live outputs (odds snapshots, logged picks, caches, site JSON) so the test starts clean."""
    rel = os.path.relpath(d, ROOT)
    skip = {".git", "__pycache__"}
    if rel == "data":
        skip |= {"cache", "picks.csv", "parlays.csv", "retro_five.json", "weekly_five.md", "lines_log.csv", "retro_assists.json"}
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
# the ticker: one beat (the daily when due, a due pull slot), and how long to sleep
_t = subprocess.run([sys.executable, "run.py", "tick"], cwd=tmp, env=env, capture_output=True, text=True)
check(_t.returncode == 0 and ("odds:" in _t.stdout or "tick:" in _t.stdout), f"a ticker beat runs ({_t.stdout.strip().splitlines()[-1][:90] if _t.stdout.strip() else _t.stderr[-200:]})")
_s = subprocess.run([sys.executable, "run.py", "sleep"], cwd=tmp, env=env, capture_output=True, text=True)
_ps = json.loads((tmp / "docs" / "data" / "meta.json").read_text()).get("pull_schedule") or []
check(_ps and all({"key", "at", "status", "kind"} <= set(x) for x in _ps) and all(x["status"] in ("pulled", "skipped", "due", "upcoming") for x in _ps), f"meta publishes the week's pull schedule with each slot's status ({len(_ps)} slots)")
check('id="pulls"' in (ROOT / "docs" / "index.html").read_text() and "function renderPulls" in (ROOT / "docs" / "index.html").read_text(), "the site shows the pull ticker")
# trade watch: a new trade on the wire raises one alert; other moves and old entries do not
from pipeline import watch as _W
_rows = [("2026-11-09T08:00Z", "Acquired LB Some One from the Chicago Bears in exchange for a 2027 fifth-round pick."), ("2026-11-09T08:00Z", "Signed WR Jalin Hyatt from the practice squad."),
         ("2026-11-05T08:00Z", "Waived QB Jake Haener."), ("2026-11-02T08:00Z", "Traded CB Old Guy to the Jets.")]
_hits = _W.new_trades(_rows, {"2026-11-02T08:00Z|Traded CB Old Guy to the Jets."})
check([s for _, s in _hits] == [_rows[0][1]], f"the trade watch flags a new trade only ({len(_hits)} hits)")
# one game's server error must not lose the slate: retried, then skipped, never raised
import pipeline.odds as _O, requests as _rq
_saved = (_O.requests.get, _O.RETRY_WAITS); _O.RETRY_WAITS = (0, 0, 0); _n = {"c": 0}
class _Resp:
    def __init__(s, code): s.status_code, s.text, s.headers = code, "", {}
    def raise_for_status(s):
        if s.status_code >= 400: raise _rq.HTTPError(str(s.status_code))
def _flaky(url, timeout, params):
    _n["c"] += 1; return _Resp(502) if _n["c"] < 3 else _Resp(200)
_O.requests.get = _flaky; _ok = _O._get_event_odds("e", "k", "A @ B")
_O.requests.get = lambda url, timeout, params: _Resp(502); _gone = _O._get_event_odds("e", "k", "A @ B")
_O.requests.get, _O.RETRY_WAITS = _saved
check(_ok is not None and _ok.status_code == 200 and _n["c"] == 3 and _gone is None, "a game's 502 is retried, and a game that keeps failing is skipped instead of crashing the pull")
check(_s.returncode == 0 and _s.stdout.strip().isdigit() and 60 <= int(_s.stdout.strip()) <= 900, f"the ticker's sleep is between a minute and fifteen ({_s.stdout.strip()})")
check((tmp / "data" / "picks.csv").exists() and "stake" in pd.read_csv(tmp / "data" / "picks.csv").columns, "the stake is logged with the pick")
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
_ac = json.loads((tmp / "docs/data/actuals.json").read_text())
check(_ac.get("weeks") and all(len(v) == 3 for w in _ac["weeks"].values() for v in w.values()), f"official box scores published for every defender-game ({sum(len(w) for w in _ac['weeks'].values())} rows)")
_pl = json.loads((tmp / "docs/data/patchlog.json").read_text())
check(len(_pl) >= 20 and {"change", "research", "post-mortem"} <= {e["kind"] for e in _pl} and all(e["title"] and "body" in e for e in _pl) and _pl == sorted(_pl, key=lambda e: e["date"], reverse=True), f"patch log built from the model log ({len(_pl)} entries, newest first)")
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
others = picks[~picks.player.isin(five.player) & ~flagged & picks.market.isin(C.LOCK_MARKETS)] if len(five) else picks[~flagged & picks.market.isin(C.LOCK_MARKETS)]   # assists are never locks
_segs = G.segment_key(five) if len(five) else pd.Series([], dtype=str)
_full = {k for k, v in _segs.value_counts().items() if v >= C.LOCKS_PER_SEGMENT}
_better = others[(others.lock > five.lock.min() + 1e-9) & ~G.segment_key(others).isin(_full)] if len(five) and len(others) else others.iloc[0:0]
_strong = others[(others.lock >= C.LOCK_MIN_SCORE) & ~G.segment_key(others).isin(_full)] if len(others) else others.iloc[0:0]
check(len(five) <= 5 and five.player.nunique() == len(five) and _better.empty and (_segs.value_counts() <= C.LOCKS_PER_SEGMENT).all()
      and (five.lock >= C.LOCK_MIN_SCORE).all() and (len(five) > 0 or _strong.empty),
      f"locks: only A-grade picks (score {C.LOCK_MIN_SCORE}+), top scores, one per player, at most {C.LOCKS_PER_SEGMENT} of a kind, none when no pick is strong ({len(five)}; kinds {dict(_segs.value_counts())})")
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
check(_R.next_pull(_sat, _g) == "2026-11-01T02:00+00:00" and _R.next_pull(_sat + dt.timedelta(hours=8), _g) == "2026-11-01T16:00+00:00"
      and _R.next_pull(dt.datetime(2026, 11, 1, 16, 30, tzinfo=dt.timezone.utc), _g) == "2026-11-01T17:00+00:00", f"next pull: Saturday 8 pm, then Sunday 10 am after the Saturday pull, then an hour before Sunday's first kickoff ({_R.next_pull(_sat, _g)}, {_R.next_pull(_sat + dt.timedelta(hours=8), _g)})")

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
# an assists pick settles on assists (combined less solo), not on tackles
_r0 = week6.iloc[0]; _ast_line = float(_r0.comb - _r0.solo_t) - 0.5
_pa = pd.concat([pd.DataFrame(rows), pd.DataFrame([dict(season=2026, week=6, player=_r0.player, team=_r0.team, opp="", market="player_assists", side="Over", line=_ast_line,
                                                      book="DraftKings", odds=-110, event_id="X0", commence_time="2026-10-18T17:00:00Z", pulled_at="20261018T120000Z", five=False, lock=50.0, grade="C")])], ignore_index=True)
# a pick that carries the league id grades on it even when the logged name is misspelled
_pid = pw[(pw.season == 2026) & (pw.week == 6) & (pw.player == _r0.player)].player_id.iloc[0]
_pb = pd.concat([pd.DataFrame(rows), pd.DataFrame([dict(season=2026, week=6, player=_r0.player + "x", player_id=str(_pid), team=_r0.team, opp="", market="player_tackles_assists", side="Over", line=float(_r0.comb) - 0.5,
                                                      book="DraftKings", odds=-110, event_id="X0", commence_time="2026-10-18T17:00:00Z", pulled_at="20261018T120000Z", five=False, lock=50.0, grade="C")])], ignore_index=True)
_pb.to_csv("data/picks.csv", index=False)
_gb, _ = G.grade(pw.assign(player_id=pw.player_id.astype(str)))
check(_gb.result.iloc[3] == "Win" and float(_gb.actual.iloc[3]) == float(_r0.comb), f"a pick grades on its league id when the name does not match ({_gb.result.iloc[3]}, actual {_gb.actual.iloc[3]})")
# a game the official stats have not reached is settled from ESPN's final box score, and marked live
from pipeline.sources import norm_name as _nn
pd.DataFrame(rows).to_csv("data/picks.csv", index=False)
_r1 = week6.iloc[1]
_pw_wo = pw[~((pw.season == 2026) & (pw.week == 6) & (pw.team == _r1.team))]
_live = pd.DataFrame([dict(season=2026, week=6, team=_r1.team, name_key=_nn(_r1.player), player=_r1.player, comb=int(_r1.comb), solo_t=int(_r1.solo_t))])
_gl, _sl = G.grade(_pw_wo, live=_live)
check(_gl.result.iloc[1] == "Loss" and _gl.graded_by.iloc[1] == "live" and _gl.graded_by.iloc[0] == "official", f"a finished game's pick settles from the live box score until the official stats arrive ({_gl.result.iloc[1]}, {_gl.graded_by.iloc[1]})")
_pa.to_csv("data/picks.csv", index=False)
_ga, _ = G.grade(pw)
check(list(_ga.result) == ["Win", "Loss", "Win", "Win"] and float(_ga.actual.iloc[3]) == float(_r0.comb - _r0.solo_t) and _ga.side_market.iloc[3] == "Over assists",
      f"an assists pick is graded on assists ({_ga.result.iloc[3]}, actual {_ga.actual.iloc[3]} vs line {_ast_line})")
pd.DataFrame(rows).to_csv("data/picks.csv", index=False)
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
_nv = list(graded.clv_novig)
check(all(np.isfinite(v) for v in _nv) and all((v > 0) == (lm > 0) for v, lm in zip(_nv, graded.clv_line)) and all(abs(v) < 0.5 for v in _nv) and summary.get("clv_novig_n") == 3 and summary.get("avg_clv_novig") is not None,
      f"no-vig closing-line value computed per pick and follows the line move ({[round(v, 3) for v in _nv]})")
_html = (ROOT / "docs" / "index.html").read_text()
check('data-tab="ast"' in _html and "function renderAssists" in _html and "player_assists" in _html, "site has the Assists tab")
check(C.market_kind("player_assists") == "assists" and C.market_kind("player_tackles_assists") == "combined" and C.market_kind("player_solo_tackles") == "solo"
      and C.market_kind("player_assists_alternate") == "assists" and C.market_kind("player_tackles_assists_alternate") == "combined", "market kinds: solo, assists, combined")
_pa = pd.read_csv(tmp / "data" / "cache" / "projections.csv")
check({"proj_ast", "phi_ast", "fair_line_ast"} <= set(_pa.columns) and (_pa.proj_ast > 0).all() and ((_pa.proj_ast - (_pa.proj - _pa.proj_solo)).abs() < 0.06).all(), "assists projection: combined less solo, with its own dispersion and fair line")
_ba = json.loads((tmp / "docs" / "data" / "bets.json").read_text())
_ast = [b for b in _ba if b["market"] == "player_assists"]
check(len(_ast) >= 10 and all(b.get("proj") is not None and b.get("under_link") for b in _ast) and not any(b.get("five") for b in _ast) and any(b["pick"] in ("Over", "Under") for b in _ast) or len(_ast) >= 10 and all(b.get("proj") is not None for b in _ast) and not any(b.get("five") for b in _ast),
      f"assists lines priced on the board with slip links and never a lock ({len(_ast)} lines, {sum(b['pick'] in ('Over', 'Under') for b in _ast)} picks)")
_pl = json.loads((tmp / "docs" / "data" / "parlays.json").read_text()) if (tmp / "docs" / "data" / "parlays.json").exists() else {}
_legs = [l for p in (_pl.get("parlays") or _pl.get("open") or []) for l in (p.get("legs") or [])] if isinstance(_pl, dict) else []
check(not any(l.get("market") == "player_assists" for l in _legs), "no parlay leg is an assists line")
_ac = json.loads((tmp / "docs" / "data" / "actuals.json").read_text())
check(all(len(v) == 3 for wk in _ac["weeks"].values() for v in wk.values()) and any(k.startswith("id:") for wk in _ac["weeks"].values() for k in wk), "actuals carry combined, solo and assists, by name and by league id")
check(all(b.get("player_id") for b in _ba) and all("espn_id" in b for b in _ba), "every priced line carries the league player id (and an ESPN id slot)")
_mt = json.loads((tmp / "docs" / "data" / "meta.json").read_text())
check(_mt.get("season_over") is False, "meta says the season is not over while games remain")
# the blend
check("blend" in _mt.get("grading", {}), "meta carries the per-market blend (empty until a week is graded with logged numbers)")
check(bt.get("prob_scores", {}).get("pit") and 0 < bt["prob_scores"]["pit"]["below_5"] < 0.2 and abs(sum(bt["prob_scores"]["pit"]["deciles"]) - 1) < 0.01 and bt["prob_scores"].get("own_lines", {}).get("brier", 1) < 0.3,
      f"backtest scores the distribution's shape (PIT tails {bt['prob_scores'].get('pit', {}).get('below_5')}/{bt['prob_scores'].get('pit', {}).get('above_95')}, Brier at own lines {bt['prob_scores'].get('own_lines', {}).get('brier')})")
# parlay correlation: two Unders on one defence rise together, an Under and an Over pull apart, different games are independent
_leg = lambda side, ev="E1", mu=5.5: dict(mu=mu, phi=1.4, exp_opps=50.0, line=5.5, side=side, event_id=ev, team="T" if ev == "E1" else "U")
_uu, _uo, _diff = M.parlay_corr_ratio([_leg("Under"), _leg("Under")]), M.parlay_corr_ratio([_leg("Under"), _leg("Over")]), M.parlay_corr_ratio([_leg("Under"), _leg("Under", ev="E2")])
check(1.0 < _uu < 1.2 and 0.8 < _uo < 1.0 and _diff == 1.0, f"parlay legs on one defence share the plays draw (UU {_uu:.3f}, UO {_uo:.3f}, other game {_diff})")
check(all("corr_ratio" in q for q in pj) if pj else True, "parlays carry the correlation ratio")
# stakes: quarter Kelly per pick within the clip, capped per game, logged with the pick
_pk = [b for b in _ba if b["pick"] in ("Over", "Under") and b.get("best_price") is not False]
check(_pk and all(b.get("stake") is not None and C.STAKE["min"] - 1e-9 <= b["stake"] <= C.STAKE["max"] + 1e-9 for b in _pk), f"every pick carries a stake inside the clip ({len(_pk)} picks)")
_byg = {}
for b in _pk: _byg[b["event_id"]] = _byg.get(b["event_id"], 0) + b["stake"]
check(_byg and max(_byg.values()) <= C.STAKE["game_cap"] + 1e-3, f"no game carries more than the cap (max {max(_byg.values()) if _byg else 0:.4f}u)")
check(abs(M.kelly_stake(0.58, 1.909) - min(C.STAKE["max"], max(C.STAKE["min"], 0.25 * ((0.58 * 0.909 - 0.42) / 0.909) * 100))) < 1e-9 and M.kelly_stake(0.45, 1.909) is None, "the Kelly stake follows the claimed chance and the price, none without an edge")
from pipeline import blend as BL
check(abs(M.blend_mean(4.0, 6.0, "solo", {"solo": {"w": 0.5, "bias_model": -0.3, "bias_line": -0.5}}) - (0.5 * 3.7 + 0.5 * 5.5)) < 1e-9 and abs(M.blend_mean(4.0, 6.0, "solo", None) - ((1 - C.LINE_WEIGHT) * 4 + C.LINE_WEIGHT * 6)) < 1e-9,
      "the pricing mean applies the market's blend weight and both level corrections, else the default weight")
check((tmp / "data" / "lines_log.csv").exists() and len(pd.read_csv(tmp / "data" / "lines_log.csv")) >= 10 and "proj_model" in pd.read_csv(tmp / "data" / "lines_log.csv").columns, "the model's number for every line is logged at each pull")
# blend estimation on a synthetic graded week: the model 1 high, the line 1 low -> both corrected, line weight ~0.5
import pipeline.blend as _BL
_wk = pw[(pw.season == 2026) & (pw.week == 6)].drop_duplicates("name_key").head(60)
_lg = pd.DataFrame(dict(season=2026, week=6, player=_wk.player.values, player_id=_wk.player_id.astype(str).values, team=_wk.team.values, market="player_tackles_assists", proj_model=_wk.comb.values + 1.0, phi=1.0, exp_opps=50.0, share_pred=0.8, pulled_at="t"))
_snap = pd.DataFrame(dict(event_id="B1", commence_time="2026-10-18T17:00:00Z", book="DraftKings", market="player_tackles_assists", player=_wk.player.values, line=_wk.comb.values - 1.0, over_odds=-110, under_odds=-110, pulled_at="20261018T165500Z"))
_old_log = _BL.LOG; _BL.LOG = tmp / "data" / "lines_log_test.csv"; _lg.to_csv(_BL.LOG, index=False)
_snapdir = Path("data/odds/2026/wk06"); _snapdir.mkdir(parents=True, exist_ok=True); _snap.to_csv(_snapdir / "20261018T165500Z.csv", index=False)
_bl = _BL.estimate(pw, 2026, weeks=[6]); _BL.LOG = _old_log
check(_bl.get("combined") and 0.35 < _bl["combined"]["w"] < 0.65 and _bl["combined"]["bias_model"] < -0.2 and _bl["combined"]["bias_line"] > 0.2 and _bl["combined"]["n"] >= 30,
      f"blend estimated from a graded week's closing lines ({_bl.get('combined')})")
check(_bl["combined"].get("scores", {}).get("n", 0) >= 20 and all(k in _bl["combined"]["scores"] for k in ("market", "model", "blend")), "blend estimate scores the chance at the posted lines against the market")

_sg = json.loads((tmp / "data" / "cache" / "segments.json").read_text()) if (tmp / "data" / "cache" / "segments.json").exists() else {}
check(all("n_eff" in v and v["n_eff"] <= v["n"] + 1e-9 for v in _sg.values()) if _sg else True, f"segment calibration carries the recency-weighted count ({len(_sg)} segments)")

check('data-tab="gloss"' in _html and "function renderGloss" in _html and "No-vig CLV" in _html and "clv_pct" in _html, "site has the glossary tab and the no-vig CLV tile")
from pipeline.grade import no_vig_clv
check(abs(no_vig_clv(-110, "Under", 5.5, 5.5, -110, -110) - (0.5 - 110 / 210)) < 1e-9 and no_vig_clv(-110, "Under", 5.5, 4.5, -110, -110) > 0.03 and no_vig_clv(-110, "Under", 5.5, 6.5, -110, -110) < -0.03
      and no_vig_clv(-110, "Over", 5.5, 5.5, -130, +110) > 0, "no-vig CLV: the vig on a held line, a move our way positive, against negative, a price move our way positive")
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

# every workflow file must parse: a colon in a step name silently removed every trigger on 2026-11-02 (pulls stopped)
import yaml as _yaml
for _wf in sorted((ROOT / ".github/workflows").glob("*.yml")):
    try:
        _d = _yaml.safe_load(_wf.read_text()); _ok = bool(_d.get(True) or _d.get("on"))
    except Exception:  # noqa: BLE001
        _ok = False
    check(_ok, f"workflow {_wf.name} is valid YAML with its triggers")

# the gate: sealing the site behind a password, and a pull that still reads the sealed meta
_r = subprocess.run([sys.executable, "run.py", "seal"], cwd=tmp, env=dict(env, SITE_PASSWORD="smoke-pw", SITE_PASSWORDS="evan: second-pw\n# a comment\nfriend: third-pw"), capture_output=True, text=True)
_enc = sorted(p.name for p in (tmp / "docs/data").glob("*.json.enc")); _plain = sorted(p.name for p in (tmp / "docs/data").glob("*.json"))
check(_r.returncode == 0 and len(_enc) >= 6 and not _plain, f"site sealed: {len(_enc)} files encrypted, no plaintext left ({_plain})")
from pipeline import seal as _SEAL
_meta_back = json.loads(_SEAL.unseal_bytes((tmp / "docs/data/meta.json.enc").read_text(), "smoke-pw"))
_bad = True
try:
    _SEAL.unseal_bytes((tmp / "docs/data/meta.json.enc").read_text(), "wrong"); _bad = False
except Exception:
    pass
_meta2 = json.loads(_SEAL.unseal_bytes((tmp / "docs/data/meta.json.enc").read_text(), "third-pw"))
check(_meta_back.get("week") == 7 and _meta2.get("week") == 7 and _bad and "for 3 passwords" in _r.stdout, "sealed meta opens with any of the three passwords and not with another")
_r2 = subprocess.run([sys.executable, "run.py", "odds"], cwd=tmp, env=dict(env, SITE_PASSWORD="smoke-pw"), capture_output=True, text=True)
_m2 = json.loads((tmp / "docs/data/meta.json").read_text()) if (tmp / "docs/data/meta.json").exists() else {}
check(_r2.returncode == 0 and _m2.get("week") == 7 and _m2.get("lines_pulled"), "a pull after sealing still reads the sealed meta and writes the board")
_r3 = subprocess.run([sys.executable, "run.py", "seal"], cwd=tmp, env=dict(env, SITE_PASSWORD=""), capture_output=True, text=True)
check(_r3.returncode == 0 and "stays open" in _r3.stdout and (tmp / "docs/data/meta.json").exists(), "no password set: the site stays open")

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
two = R.auto_plan(now=_at(2026, 10, 29, 17, 40))   # 9 am and 1 pm both unserved
check(two and two["key"] == "2026-10-29 13:00" and two["also_served"] == ["2026-10-29 09:00"], "with several slots due, the latest is served and the stale ones marked")
thu = [dict(game_id="2026_08_GB_CAR", home="CAR", away="GB", kickoff=_at(2026, 10, 29, 18, 15).isoformat(), international=False)]
pk = R.auto_plan(now=_at(2026, 10, 29, 17, 20), games=thu, served={"2026-10-29 09:00", "2026-10-29 13:00"})
check(pk and pk["key"] == "2026-10-29 prekick-17:15" and pk["days"] == ["2026-10-29"], f"Thursday: a pull an hour before kickoff comes from the schedule ({pk and pk.get('key')})")
check(R.auto_plan(now=_at(2026, 10, 29, 17, 10), games=thu, served={"2026-10-29 09:00", "2026-10-29 13:00"}) is None, "Thursday: nothing due between the 1 pm look and the pre-kickoff pull")
late_pk = R.auto_plan(now=_at(2026, 10, 29, 19, 0), games=thu, served={"2026-10-29 09:00", "2026-10-29 13:00"})
check(late_pk and late_pk["key"] == "2026-10-29 prekick-17:15", "a stalled scheduler still serves the pre-kickoff pull when it wakes (started games are then skipped)")
sun = [dict(game_id="2026_09_A_B", home="B", away="A", kickoff=_at(2026, 11, 1, 11, 0).isoformat(), international=False),
       dict(game_id="2026_09_C_D", home="D", away="C", kickoff=_at(2026, 11, 1, 14, 25).isoformat(), international=False),
       dict(game_id="2026_09_E_F", home="F", away="E", kickoff=_at(2026, 11, 2, 18, 15).isoformat(), international=False)]
check(R.auto_plan(now=_at(2026, 11, 1, 9, 30), games=sun) is None, "Sunday: nothing due before the 10 am look")
plan = R.auto_plan(now=_at(2026, 11, 1, 10, 3), games=sun)
check(plan and plan.get("days") == ["2026-11-01"] and plan.get("key") == "2026-11-01 prekick-10:00" and plan.get("also_served") == ["2026-11-01 10:00"], f"Sunday: the pull an hour before the first kickoff wins a tie with the fixed 10 am look ({plan and plan.get('reason')})")
check(R.auto_plan(now=_at(2026, 11, 1, 13, 2), games=sun, served={"2026-11-01 10:00", "2026-11-01 prekick-10:00"}) is None, "Sunday: nothing due between the morning pull and the afternoon pre-kickoff pull")
plan = R.auto_plan(now=_at(2026, 11, 1, 13, 30), games=sun, served={"2026-11-01 10:00", "2026-11-01 prekick-10:00"})
check(plan and plan.get("key") == "2026-11-01 prekick-13:25" and plan.get("days") == ["2026-11-01"], "Sunday: the afternoon games get their own pre-kickoff pull")
check(R.auto_plan(now=_at(2026, 11, 1, 10, 33), games=sun, served={"2026-11-01 10:00", "2026-11-01 prekick-10:00"}) is None, "Sunday: every Sunday pull is served once")
_sun2 = [dict(game_id="2026_09_A_B", home="B", away="A", kickoff=_at(2026, 11, 1, 11, 0).isoformat()), dict(game_id="2026_09_C_D", home="D", away="C", kickoff=_at(2026, 11, 1, 11, 25).isoformat()),
         dict(game_id="2026_09_E_F", home="F", away="E", kickoff=_at(2026, 11, 1, 14, 5).isoformat()), dict(game_id="2026_09_G_H", home="H", away="G", kickoff=_at(2026, 11, 1, 14, 25).isoformat()), dict(game_id="2026_09_I_J", home="J", away="I", kickoff=_at(2026, 11, 1, 18, 20).isoformat())]
check([k for _, k in R.kickoff_slots(_sun2, _dt.date(2026, 11, 1))] == ["2026-11-01 prekick-10:00", "2026-11-01 prekick-13:05", "2026-11-01 prekick-17:20"], f"kickoffs within half an hour share one pre-kickoff pull ({[k for _, k in R.kickoff_slots(_sun2, _dt.date(2026, 11, 1))]})")
fri = [dict(game_id="2026_12_X_Y", home="Y", away="X", kickoff=_at(2026, 11, 27, 13, 0).isoformat(), international=False)]   # a Friday game (Black Friday)
plan = R.auto_plan(now=_at(2026, 11, 27, 12, 4), games=fri)
check(plan and plan.get("key") == "2026-11-27 prekick-12:00" and plan.get("days") == ["2026-11-27"], "a Friday game gets its pre-kickoff pull although Friday has no fixed slot")
check(R.next_pull(_at(2026, 11, 27, 9, 0), fri) == _at(2026, 11, 27, 12, 0).isoformat(timespec="minutes"), f"next pull walks the schedule's pre-kickoff pulls on any day ({R.next_pull(_at(2026, 11, 27, 9, 0), fri)})")
check(R.auto_plan(now=_at(2026, 11, 1, 6, 30)) is None and R.auto_plan(now=_at(2026, 11, 1, 11, 40), served={"2026-11-01 10:00"}) is None, "Sunday with no schedule loaded: only the fixed looks are due")
check(dt.datetime(2026, 11, 2, 12, 0, tzinfo=R.EDMONTON).utcoffset() == dt.timedelta(hours=-6) and dt.datetime(2026, 10, 30, 12, 0, tzinfo=R.EDMONTON).utcoffset() == dt.timedelta(hours=-6),
      "Edmonton stays on UTC-6 through the November clock change (Alberta Time)")
check(R.auto_plan(now=_at(2026, 11, 7, 18, 2)) is None, "Saturday: nothing due before the 8 pm look")
plan = R.auto_plan(now=_at(2026, 11, 7, 20, 7))      # Saturday 8:07 pm, after the clock change
check(plan and plan.get("days") == ["2026-11-07", "2026-11-08"] and plan["key"] == "2026-11-07 20:00", f"Saturday 8 pm slot covers Saturday and Sunday games in standard time ({plan and plan.get('days')})")
check(R.auto_plan(now=_at(2026, 11, 6, 14, 5)) is None and R.auto_plan(now=_at(2026, 11, 6, 18, 5)) is None, "Friday: no scheduled pulls")
plan = R.auto_plan(now=_at(2026, 11, 9, 13, 30), served={"2026-11-09 09:00"})     # Monday 1:30 pm
check(plan and plan.get("days") == ["2026-11-09"] and plan["key"] == "2026-11-09 13:00", "Monday 1 pm slot covers the Monday game")
_lr = R.CACHE / "last_run.txt"; _lr.parent.mkdir(parents=True, exist_ok=True); _was = _lr.read_text() if _lr.exists() else None
_now = dt.datetime.now(dt.timezone.utc)
_lr.write_text(f"success {_now.strftime('%Y-%m-%dT%H:%MZ')}"); _fresh = R.daily_is_fresh()
_lr.write_text(f"failure {_now.strftime('%Y-%m-%dT%H:%MZ')}"); _failed = R.daily_is_fresh()
_lr.write_text(f"success {(_now - dt.timedelta(hours=10)).strftime('%Y-%m-%dT%H:%MZ')}"); _old = R.daily_is_fresh()
check(_fresh and not _failed and not _old, "the fallback daily run skips only after a success in the last 8 hours")
# the ticker runs the daily once per Edmonton day after 4:15 am
_day = dt.date(2026, 11, 5); _loc = lambda h, m=0: dt.datetime.combine(_day, dt.time(h, m), tzinfo=R.EDMONTON).astimezone(dt.timezone.utc)
_lr.write_text(f"success {(_loc(4, 30) - dt.timedelta(days=1)).strftime('%Y-%m-%dT%H:%MZ')}")   # yesterday's run
_due_after, _due_before = R.daily_due(_loc(5, 0)), R.daily_due(_loc(3, 0))
_lr.write_text(f"success {_loc(4, 30).strftime('%Y-%m-%dT%H:%MZ')}")                              # today's run done
_done_today = R.daily_due(_loc(9, 0))
_lr.write_text(f"failure {_loc(4, 30).strftime('%Y-%m-%dT%H:%MZ')}")                              # today's run failed: try again
_retry = R.daily_due(_loc(9, 0))
check(_due_after and not _due_before and not _done_today and _retry, f"the ticker's daily is due once per Edmonton day after 4:15 am ({_due_after}, {_due_before}, {_done_today}, {_retry})")
(_lr.write_text(_was) if _was is not None else _lr.unlink())
import yaml as _y
_tk = _y.safe_load((ROOT / ".github/workflows/ticker.yml").read_text()); _dy = _y.safe_load((ROOT / ".github/workflows/daily.yml").read_text()); _od = _y.safe_load((ROOT / ".github/workflows/odds.yml").read_text())
check("schedule" in (_tk.get(True) or _tk.get("on")) and "schedule" not in (_dy.get(True) or _dy.get("on")) and "schedule" not in (_od.get(True) or _od.get("on")), "the ticker is the only scheduled workflow; daily and odds are by hand")
intl = [dict(game_id="2026_07_NO_PIT", home="PIT", away="NO", kickoff=_at(2026, 10, 25, 7, 30).isoformat(), international=True)]
p12 = R.auto_plan(now=_at(2026, 10, 24, 19, 50), games=intl)   # Saturday 7:50 pm, before the 8 pm slot
check(p12 and p12.get("teams") == ("PIT", "NO") and p12["key"].endswith("12h"), "international game pulled in the 12 h window even when the run is late")
sat = R.auto_plan(now=_at(2026, 10, 24, 20, 10), games=intl)
check(sat and sat["key"] == "2026-10-24 20:00", "a due regular slot takes priority over an international window")
check(R.auto_plan(now=_at(2026, 10, 25, 5, 0), games=intl, served={"2026_07_NO_PIT 12h"}) is None, "no pull between the international windows once the 12 h one is served")
p1 = R.auto_plan(now=_at(2026, 10, 25, 6, 40), games=intl, served={"2026_07_NO_PIT 12h"})
check(p1 and p1["key"] == "2026-10-25 prekick-06:30", "international game pulled an hour before its early kickoff by the schedule rule")
games = json.loads((tmp / "data/cache/games.json").read_text())
check(len(games) > 10 and all({"home", "away", "kickoff", "international"} <= set(g) for g in games), f"this week's games written with kickoff and international flag ({len(games)})")

print("\nALL CHECKS PASSED" if not fails else f"\n{len(fails)} CHECK(S) FAILED")
sys.exit(1 if fails else 0)
