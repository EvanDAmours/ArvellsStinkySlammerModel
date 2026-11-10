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
        skip |= {"cache", "picks.csv", "parlays.csv", "retro_five.json", "weekly_five.md", "lines_log.csv", "retro_assists.json", "sleepers.csv", "settled.csv"}
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
FT = {t["key"]: t for t in bt.get("factor_tests", [])}
check(set(FT) >= {"crew", "role", "volume", "pfr", "persnap", "vacancy", "snap"} and all({"in_model", "rows", "helps", "t", "verdict"} <= set(t) for t in FT.values())
      and all(FT[k]["in_model"] == bool(v) for k, v in __import__("json").loads(__import__("json").dumps(bt["design"]["factors"])).items() if k in FT),
      f"the protocol's daily test covers every factor, in the model or out ({sum(t['in_model'] for t in FT.values())} in, {sum(not t['in_model'] for t in FT.values())} out)")
check(FT["crew"]["helps"] is not None and FT["crew"]["helps"] < 0 and not FT["crew"]["in_model"], f"the daily test sees the planted stat crews although the factor is out of the model (deviance {FT['crew']['helps']:+.4f}, t {FT['crew']['t']:+.1f})")
check(FT["role"]["in_model"] and FT["role"]["t"] is not None and FT["role"]["t"] < -1 and P["Factor model"]["mae"] < P["Factor model without next man up"]["mae"], f"next man up earns its place on the rows it moves (t {FT['role']['t']:+.1f})")
check(P["Factor model"]["mae"] <= P["Season average"]["mae"], "factor model at least matches season average")
_fin = bt.get("final", {})
check(len(_fin.get("folds", [])) >= 2 and all(f["final"]["deviance"] > 0 and f["factor"]["deviance"] > 0 for f in _fin["folds"]) and "final_minus_factor" in _fin and isinstance(bt.get("flags"), list)
      and any(r["predictor"].startswith("Final projection") and "deviance" in r for r in bt["predictors"]),
      f"the final projection is scored out of sample, a fold a season, in Poisson deviance ({[(f['season'], round(f['final']['deviance'], 3)) for f in _fin.get('folds', [])]}; flags {bt.get('flags')})")
lb = next((d for d in bt["dispersion"] if d["group"] == "LB"), None)
_s = next((d for d in bt["dispersion"] if d["group"] == "S"), None)
check(lb is not None and _s is not None and 0.6 <= lb["corrected"] <= 1.05 and lb["corrected"] < _s["corrected"], f"linebacker spread fitted tighter than the safeties', as planted (0.75 before the projection's own error: {lb and round(lb['corrected'], 2)} vs {_s and round(_s['corrected'], 2)})")
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
check(all(0 <= b.get("lock", -1) <= 100 and b.get("tier") in ("pick", "lean", "pass") for b in priced) and all(b.get("grade") in ("A", "B", "C") for b in priced if b.get("pick") in ("Over", "Under"))
      and all(b.get("grade") is None for b in priced if b.get("pick") not in ("Over", "Under")), "every priced line has a lock score and a tier; a pick has a grade, a line that is not a pick has none")
check(all("lock_block" in b and "lock_eligible" in b and "in_role_games" in b for b in priced) and not any(b.get("lock_block") and b.get("five") for b in priced),
      f"priced lines carry the lock-eligibility checklist and no blocked line is a lock ({sum(1 for b in priced if b.get('lock_block'))} blocked of {len(priced)})")
check(all(not (b.get("lock_block") and "Over" == b.get("side") and "fading" in str(b.get("why"))) for b in priced) and not any("Over" == b.get("side") and "fading an outlier" in str(b.get("why")) for b in priced),
      "no Over is sold as fading an outlier")
check(any("role-shift" in r["predictor"] for r in bt["predictors"]) and isinstance(bt.get("weak_spots"), list), "backtest reports the role-shift factors and the weak-spot table")
check(all(any(k in r["predictor"] for r in bt["predictors"]) for k in ("per-snap base", "vacancy rule", "indoors (corners)", "outlier damping")), "backtest reports the per-snap, vacancy, dome and outlier-damping pieces")
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
check(any(r["predictor"].startswith("Solo tackles: final projection") for r in bt["predictors"]) and any("solo" in d["group"] for d in bt["dispersion"]) and 0.9 <= bt.get("scale_solo", 0) <= 1.1,
      "solo tackles scored in the backtest with their own dispersion and level")
check(any("without league solo drift" in r["predictor"] for r in bt["predictors"]) and all(0.85 <= (p.get("solo_drift") or 1.0) <= 1.15 for p in proj), "league solo drift applied and reported")
check(all("far_from_line" in b and all(0 < b.get(k, -1) < 1 for k in ("p_claim", "p_low", "p_model", "market_over")) and "edge_low" in b and "mkt_mean" in b for b in priced),
      "priced lines carry the far-from-line flag, the book's fair chance, the model's own chance, the win chance and the cautious chance")
check(all("next man up" in str(b.get("lock_block")) for b in priced if b.get("signal_role")) and not any(b["pick"] == "Under" and "next man up" in str(b.get("lock_block")) and (b.get("share_pred") or 0) < C.PHI_SHARE_SPLIT for b in priced),
      f"the next man up is never lock-eligible, and his Under is not a pick when the model expects him under 60% of the snaps ({sum('next man up' in str(b.get('lock_block')) for b in priced)} lines on such players)")
check(not any(b.get("five") and b.get("side") == "Over" for b in priced) and all("Over side" in str(b.get("lock_block")) for b in priced if b.get("side") == "Over"), "no Over is a lock while Overs are ineligible")
_E = C.ENGINE
_guard = lambda b: b["side"] == "Under" and "next man up" in str(b.get("lock_block"))       # his Under is never a pick when he is expected under 60% of the snaps
check(all((b["edge_low"] >= _E["pick_edge_low"] - 1e-9) == (b["tier"] == "pick") or b.get("status") or b["n_prev"] < C.MIN_GAMES_FOR_PICK or _guard(b) for b in priced)
      and all(b["ev"] >= _E["lean_edge"] - 1e-9 and b["edge_low"] < _E["pick_edge_low"] for b in priced if b["tier"] == "lean")
      and all(b["pick"] in ("Over", "Under") for b in priced if b["tier"] == "pick") and all(b["pick"] == "Pass" for b in priced if b["tier"] != "pick"),
      f"a pick breaks even at the cautious chance; a lean has an edge only at the win chance and is not a pick ({sum(b['tier'] == 'pick' for b in priced)} picks, {sum(b['tier'] == 'lean' for b in priced)} leans)")
# a board where nothing can be priced (one-sided prices only, a player the model does not carry) still yields every column
_Pm = pd.read_csv(tmp / "data" / "cache" / "projections.csv")
_bare = M.price_lines(pd.DataFrame([dict(player=_Pm.player.iloc[0], book="Bally Bet", market="player_tackles_assists", line=5.5, over_odds=-110, under_odds=np.nan, event_id="Z1", commence_time="2099-01-01T18:00:00Z"),
                                    dict(player="Nobody Atall", book="DraftKings", market="player_solo_tackles", line=2.5, over_odds=-110, under_odds=-110, event_id="Z1", commence_time="2099-01-01T18:00:00Z")]), _Pm)
check(len(_bare) == 2 and {"ev", "best_price", "tier", "stake", "lock", "grade", "sleeper"} <= set(_bare.columns) and not _bare.best_price.any() and set(_bare.pick) == {"Pass", "No projection"}
      and G.size_stakes(_bare) is not None and "one-sided" in " ".join(_bare.why.astype(str)).lower(),
      "a board with nothing to price (a one-sided price with no two-way book on the line, an unknown player) is passed without a pick and without breaking the log")
_od = lambda b: b["over_odds"] if b["side"] == "Over" else b["under_odds"]
_tol = 4e-4                                               # the site's JSON keeps four decimals
check(all(abs(b["ev"] - (b["p_claim"] * M.american_to_decimal(_od(b)) - 1)) < _tol and abs(b["edge_low"] - (b["p_low"] * M.american_to_decimal(_od(b)) - 1)) < _tol
          and min(b["p_model"], b["mkt_side"]) - _tol <= b["p_low"] <= max(b["p_model"], b["mkt_side"]) + _tol and (b["p_low"] - b["mkt_side"]) * (b["p_claim"] - b["p_low"]) >= -_tol for b in priced),
      "the win chance sits between the book's fair chance and the model's own, the cautious chance nearer the book; both returns follow from the price")
check(all(b.get("mkt_mean") is not None and min(b["proj_model"], b["mkt_mean"]) - 0.06 <= b["proj"] <= max(b["proj_model"], b["mkt_mean"]) + 0.06 for b in priced), "the priced number sits between the model's number and the one the book's price implies")
check(any(b.get("cons_n", 0) > 0 for b in priced), "consistency (games cleared) computed from game logs")
check(all(str(b.get("over_link", "")).startswith("https://") and str(b.get("under_link", "")).startswith("https://") for b in priced), "priced lines carry the book's bet-slip links for both sides")
picks = pd.read_csv(tmp / "data/picks.csv") if (tmp / "data/picks.csv").exists() else pd.DataFrame()
check(len(picks) >= 1, f"picks logged ({len(picks)})")
check(picks.drop_duplicates(["player", "market", "side", "line"]).shape[0] == len(picks), "one logged pick per player/line (best price only)")
check({"lock", "grade", "consistency", "payout"} <= set(picks.columns) and picks.grade.isin(["A", "B", "C"]).all(), "logged picks carry their grade, lock score, consistency and payout")
five = picks[picks.five.fillna(False).astype(bool)] if "five" in picks.columns else pd.DataFrame()
flagged = G.lock_blocked(picks)               # never locks, whatever their score
_isA = picks.grade.astype(str) == "A"                                                         # only an A can be a lock: the cautious edge, the model's own chance, the checklist
others = picks[~picks.player.isin(five.player) & ~flagged & _isA & picks.market.isin(C.LOCK_MARKETS)] if len(five) else picks[~flagged & _isA & picks.market.isin(C.LOCK_MARKETS)]   # assists are never locks
_segs = G.segment_key(five) if len(five) else pd.Series([], dtype=str)
_full = {k for k, v in _segs.value_counts().items() if v >= C.LOCKS_PER_SEGMENT}
_better = others[(others.lock > five.lock.min() + 1e-9) & ~G.segment_key(others).isin(_full)] if len(five) and len(others) else others.iloc[0:0]
_strong = others[(others.lock >= C.LOCK_MIN_SCORE) & ~G.segment_key(others).isin(_full)] if len(others) else others.iloc[0:0]
check(len(five) <= 5 and five.player.nunique() == len(five) and _better.empty and (_segs.value_counts() <= C.LOCKS_PER_SEGMENT).all()
      and (five.lock >= C.LOCK_MIN_SCORE).all() and (len(five) > 0 or _strong.empty),
      f"locks: only A-grade picks (the model's own chance {C.LOCK_MIN_SCORE:.0f}+), highest first, one per player, at most {C.LOCKS_PER_SEGMENT} of a kind, none when no pick is strong ({len(five)}; kinds {dict(_segs.value_counts())})")
check(sum(1 for b in bets if b.get("five")) == len(five), "locks marked on the board")
parlays = pd.read_csv(tmp / "data/parlays.csv") if (tmp / "data/parlays.csv").exists() else pd.DataFrame()
check(len(parlays) >= 2 and parlays.parlay_id.nunique() >= 1 and parlays.groupby("parlay_id").size().between(2, 4).all(), f"recommended parlay built ({parlays.parlay_id.nunique() if len(parlays) else 0} parlay, {len(parlays)} legs)")
check(len(parlays) and parlays.player.nunique() == len(parlays) and parlays.units.between(0.1, 1.0).all(), "parlay legs are distinct players with a stake between 0.1 and 1 unit")
check(all(b["edge_low"] >= _E["b_edge_low"] - 1e-9 and b["p_model"] >= _E["a_model"] - 1e-9 and not b.get("lock_block") and b["market"] in C.A_GRADE_MARKETS for b in priced if b.get("grade") == "A")
      and all(b["edge_low"] >= _E["b_edge_low"] - 1e-9 for b in priced if b.get("grade") == "B") and all(b["edge_low"] < _E["b_edge_low"] for b in priced if b.get("grade") == "C")
      and (five.market.isin(C.A_GRADE_MARKETS).all() if len(five) else True),
      f"an A has a cautious edge of 2%+, a model chance of 70%+, a clear checklist and a market that can carry one; a B the edge; a C is a pick short of it ({dict(pd.Series([b.get('grade') for b in priced if b.get('grade')]).value_counts())})")
# Rule 0 (CLAUDE.md): a pick is never graded, ranked or chosen by whether the book agrees with it. At a fixed model chance and a
# fixed margin, moving the book's fair chance toward the model's must never raise the cautious edge (what chooses a pick) or the
# grade; the lock score (what ranks) is the model's own chance and does not see the book at all. (The stake is not part of the
# rule: sized by Kelly, it can rise a hair as an absurd long shot's price shortens, because the bet gets less volatile.)
_rank = {None: 0, "C": 1, "B": 2, "A": 3}; _viol = 0
for _pm100 in range(51, 99):
    _pm, _prev = _pm100 / 100, None
    for _pk100 in range(5, _pm100 + 1):
        _pk = _pk100 / 100; _dec = 1 / (_pk * 1.0476)
        _pl = M.engine_chance(_pm, _pk, _E["beta_low"]); _el = _pl * _dec - 1
        _cur = (_el, _rank[M.engine_grade(_el, _pm, False, "player_solo_tackles")])
        _viol += _prev is not None and (_cur[0] > _prev[0] + 1e-12 or _cur[1] > _prev[1])
        _prev = _cur
check(_viol == 0 and abs(M.engine_chance(0.7, 0.5, 0.0) - 0.5) < 1e-12 and abs(M.engine_chance(0.7, 0.5, 1.0) - 0.7) < 1e-9 and abs(M.fair_over(-110, -110) - 0.5) < 1e-12
      and abs(M.fair_over(-130, 110) - (130 / 230) / (130 / 230 + 100 / 210)) < 1e-12 and np.isnan(M.fair_over(-110, None))
      and M.engine_grade(-0.001, 0.9, False) is None and M.engine_grade(0.03, 0.9, True) == "B" and M.engine_grade(0.03, 0.9, False, "player_assists") == "B",
      "more agreement from the book never improves a pick's cautious edge or its grade; zero disagreement is the book's fair chance; a blocked or trial-market pick tops out at B")
# trades: a regular who played his team's last game shows on another team in the weekly roster before week 7
_done = H[(H.season == 2026) & (H.week < 7)]
_tlast = _done.groupby("team").week.max().to_dict()
_reg = _done[(_done.week == _done.team.map(_tlast)) & (_done.def_pct >= 0.9) & (_done.group == "LB")].iloc[0]
_F0 = M.upcoming_rows(H, sched, inj, 2026, 7, vol=vol["vol"], dc=vol["dc"], pbp_starters=vol["pbp"]["starters"])
_other = sorted(set(_F0.team) - {_reg.team})[0]
_F1 = M.upcoming_rows(H, sched, inj, 2026, 7, vol=vol["vol"], dc=vol["dc"], pbp_starters=vol["pbp"]["starters"], roster={str(_reg.player_id): (_other, 7)})
_me = _F1[_F1.player_id == _reg.player_id]
_mates = _F1[(_F1.team == _reg.team) & (_F1.group == "LB") & (_F1.player_id != _reg.player_id)]
check(len(_me) == 1 and _me.team.iloc[0] == _other and bool(_me.team_changed.iloc[0])
      and _mates.vacancy.all() and _mates[_mates.pct_prev.fillna(0) < 0.75].role_signal.all() and len(_mates[_mates.pct_prev.fillna(0) < 0.75])
      and _mates.gone_regulars.str.contains(f"traded to {_other}").all(),
      f"a trade in the weekly roster moves the player, flags his old group's vacancy and next man up, and names him on their cards ({_reg.player} {_reg.team} -> {_other})")
_T6 = H[(H.season == 2026) & (H.n_prev >= 2)].head(400)
_pa = {}
_m0, _m1 = M.project_frame(_T6)[1], M.project_frame(_T6, parts=_pa)[1]
check(np.allclose(_m0.values, _m1.values, equal_nan=True) and {"base", "volume", "crew", "tilt", "damp", "solo_share"} <= set(_pa),
      "recording the projection's pieces leaves the projection unchanged")
check(all(str(b.get("logic", "")).startswith("How the model built") for b in priced)
      and all(abs(e) >= 0.03 for b in priced for _, e in (b.get("logic_chips") or [])),
      f"every priced line shows how the model built its number; the card's factor row lists the 3%+ movers ({sum(1 for b in priced if b.get('logic_chips'))} with movers)")
_sl = [b for b in priced if b.get("sleeper")]
_lo, _hi = C.SLEEPER["comb_over"]
check(all((b["sleeper"] == "Over" and C.market_kind(b["market"]) == "combined" and _lo <= b["proj_model"] - b["line"] < _hi) or
          (b["sleeper"] == "Under" and C.market_kind(b["market"]) == "solo" and b["proj_model"] - b["line"] <= C.SLEEPER["solo_under"]
           and b.get("sleeper_med") is not None and b["sleeper_med"] >= b["line"] + C.SLEEPER["solo_hist"] - 1e-9) for b in _sl)
      and all(b.get("sleeper_ev") is not None and (C.SLEEPER["min_ev"] is None or b["sleeper_ev"] >= C.SLEEPER["min_ev"] - 1e-9) for b in _sl),
      f"sleepers follow the rule: combined Overs {_lo} to {_hi} over the line, solo Unders 0.5+ under it with his median within a tackle ({len(_sl)} on the board)")
check(all(b.get("sleeper_grade") in ("A", "B", "C") and 0 < (b.get("sleeper_p") or 0) < 1 and f"Grade {b['sleeper_grade']}" in str(b.get("sleeper_note")) for b in _sl)
      and not any(b["sleeper"] == "Over" and b.get("sleeper_grade") == "A" for b in _sl)
      and all(b.get("sleeper_grade") == "C" or ("steady role" in str(b.get("sleeper_note"))) for b in _sl)
      and all((b.get("sleeper_grade") != "A") or b["sleeper_p"] >= C.SLEEPER["a_model"] - 1e-9 or (b.get("exp_opps") or 99) < C.SLEEPER["a_opps"] for b in _sl),
      f"every sleeper carries a grade, the model's own chance and a summary; combined Overs never an A; an A has a 70%+ chance or a low-volume game ({dict(pd.Series([b.get('sleeper_grade') for b in _sl]).value_counts()) if _sl else {}})")
_slc = pd.read_csv(tmp / "data/sleepers.csv") if (tmp / "data/sleepers.csv").exists() else pd.DataFrame()
check((len(_slc) > 0) == (len(_sl) > 0) and (len(_slc) == 0 or _slc.duplicated(["season", "week", "player", "market", "side"]).sum() == 0), f"sleepers logged once per player, market and side ({len(_slc)} rows)")
if len(_slc):
    _rowp = pw[(pw.season == 2026) & (pw.week == 6)].sort_values("comb", ascending=False).iloc[0]
    pd.DataFrame([dict(season=2026, week=6, player=_rowp.player, market="player_tackles_assists", side="Over", line=float(_rowp.comb) - 0.5, odds=100,
                       book="DraftKings", commence_time="2026-10-18T17:00:00Z")]).to_csv(G.SLEEPERS, index=False)
    _gs, _ss = G.grade_sleepers(pw)
    check(list(_gs.result) == ["Win"] and _ss["all"]["wins"] == 1 and abs(_ss["all"]["units"] - 1.0) < 1e-9 and "by_grade" in _ss, f"a sleeper grades on the box score, with a record by grade ({list(_gs.result)})")
    check({"sleeper_grade", "sleeper_p", "sleeper_note"} <= set(_slc.columns) and _slc.sleeper_grade.isin(["A", "B", "C"]).all(), "logged sleepers keep their grade, chance and summary")
    _slc.to_csv(G.SLEEPERS, index=False)
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
G.SETTLED.unlink(missing_ok=True)
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
G.SETTLED.unlink(missing_ok=True)                 # a fresh settlement store: this scenario grades the same picks from another source
_r1 = week6.iloc[1]
_pw_wo = pw[~((pw.season == 2026) & (pw.week == 6) & (pw.team == _r1.team))]
_live = pd.DataFrame([dict(season=2026, week=6, team=_r1.team, name_key=_nn(_r1.player), player=_r1.player, comb=int(_r1.comb), solo_t=int(_r1.solo_t))])
_gl, _sl = G.grade(_pw_wo, live=_live)
check(_gl.result.iloc[1] == "Loss" and _gl.graded_by.iloc[1] == "live" and _gl.graded_by.iloc[0] == "official", f"a finished game's pick settles from the live box score when the game ends ({_gl.result.iloc[1]}, {_gl.graded_by.iloc[1]})")
# a bet settles once: the official stats arrive later with a different count for that player; the record does not move
_pw_fix = pw.copy(); _mrow = (_pw_fix.season == 2026) & (_pw_fix.week == 6) & (_pw_fix.team == _r1.team) & (_pw_fix.player == _r1.player)
_pw_fix.loc[_mrow, "comb"] = _pw_fix.loc[_mrow, "comb"] + 2
_gf, _sf = G.grade(_pw_fix)
check(_gf.result.iloc[1] == "Loss" and float(_gf.actual.iloc[1]) == float(_r1.comb) and _gf.graded_by.iloc[1] == "live" and bool(_gf.corrected.iloc[1]) and _sf["stat_corrections"] == 1 and G.SETTLED.exists(),
      f"a bet settles once: a later stat correction is counted and shown, never applied ({_gf.result.iloc[1]}, kept {float(_gf.actual.iloc[1]):g} against a corrected {float(_r1.comb) + 2:g})")
G.SETTLED.unlink(missing_ok=True)
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
check(summary["by_grade"] and summary["by_grade"][0]["grade"] == "A" and all({"hit", "hit_lo", "hit_hi", "pushes", "pending", "staked", "stake"} <= set(g) for g in summary["by_grade"])
      and summary["five"]["hit_lo"] is not None and summary["five"]["hit_lo"] < summary["five"]["hit"] < summary["five"]["hit_hi"] and "hit_lo" in summary["by_side"][0],
      f"records carry hit rate, its likely range, pushes, pending and staked units ({[(g['grade'], g['wins'], g['losses']) for g in summary['by_grade']]})")
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
check({"engine", "stake", "factors", "frozen_until", "corrector_weight"} <= set(_mt.get("grading", {})) and _mt["grading"]["engine"]["beta"] == C.ENGINE["beta"] and "odds_budget" in _mt and isinstance(_mt.get("protocol_flags"), list),
      "meta carries the engine's settings, the factor set, the freeze date, the odds-credit budget and the protocol's flags")
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
_bets_once = {}                                             # one bet per player, market and side: the caps hold for his largest stake among his lines and books
for b in _pk:
    _k3 = (b["player"], b["market"], b["side"])
    if _k3 not in _bets_once or b["stake"] > _bets_once[_k3]["stake"]: _bets_once[_k3] = b
_byg, _bys, _byk = {}, {}, {}
for b in _bets_once.values():
    _sl8 = G.slate_of(b["commence_time"]); _kd = b["side"] + " " + C.market_kind(b["market"])
    _byg[b["event_id"]] = _byg.get(b["event_id"], 0) + b["stake"]; _bys[_sl8] = _bys.get(_sl8, 0) + b["stake"]; _byk[(_sl8, _kd)] = _byk.get((_sl8, _kd), 0) + b["stake"]
_slack = C.STAKE["min"] * len(_bets_once)                   # the floor of 0.1u a pick can lift a capped total a little
check(_byg and max(_byg.values()) <= C.STAKE["game_cap"] + _slack and max(_bys.values()) <= C.STAKE["slate_cap"] + _slack and max(_byk.values()) <= C.STAKE["kind_cap"] + _slack
      and all(b.get("stake_raw") is not None and b["stake"] <= b["stake_raw"] + 1e-9 and (b.get("slate_n") or 0) >= 1 for b in _pk),
      f"the slate is sized as one book: caps per game, per kind and per slate day (most on a game {max(_byg.values()) if _byg else 0:.2f}u, a kind {max(_byk.values()) if _byk else 0:.2f}u, a day {max(_bys.values()) if _bys else 0:.2f}u over {len(_bets_once)} bets)")
_one = pd.DataFrame([dict(player=f"P{i}", market="player_solo_tackles", side="Under", pick="Under", stake=2.0, edge_low=0.03, event_id=f"G{i // 2}", commence_time="2099-01-03T18:00:00Z", best_price=True) for i in range(12)])
_sz = G.size_stakes(_one)
check(abs(_sz.stake.sum() - C.STAKE["kind_cap"]) < 1e-6 and _sz.groupby("event_id").stake.sum().max() <= C.STAKE["game_cap"] + 1e-9 and (_sz.slate_n == 12).all() and (_sz.stake_raw == 2.0).all()
      and abs(G.size_stakes(_one.head(1)).stake.iloc[0] - 2.0) < 1e-9,
      f"twelve like picks on one slate are divided for their number and held to the cap for one kind ({_sz.stake.sum():.2f}u in all); a lone pick keeps its stake")
check(abs(M.kelly_stake(0.553, 1.909) - min(C.STAKE["max"], max(C.STAKE["min"], C.STAKE["kelly_fraction"] * ((0.553 * 0.909 - 0.447) / 0.909) * 100))) < 1e-9 and M.kelly_stake(0.45, 1.909) is None
      and abs(M.kelly_stake(1 / 1.909, 1.909) - C.STAKE["min"]) < 1e-9, "the stake is a quarter of Kelly at the cautious chance: the minimum when it only breaks even there, none below")
_lo, _hi = G.hit_interval(10, 4, 3); _lo2, _hi2 = G.hit_interval(100, 40, 3); _lo3, _hi3 = G.hit_interval(100, 40, 140)
check(_lo < 10 / 14 < _hi and _hi - _lo > 0.35 and (_hi2 - _lo2) > (_hi3 - _lo3) and G.hit_interval(0, 0) == (None, None),
      f"a record's likely range is wide on few bets and wider when the bets share weeks (10-4: {_lo:.0%} to {_hi:.0%})")
from pipeline import backtest as _BT
_rng = np.random.default_rng(5); _mu = _rng.uniform(2, 9, 6000)
_nb = _rng.negative_binomial(_mu / 0.4, 1 / 1.4); _po = _rng.poisson(_mu)
check(abs(_BT.fit_phi(_nb, _mu) - 1.4) < 0.08 and abs(_BT.fit_phi(_po, _mu) - 1.0) < 0.08, f"the spread is recovered by maximum likelihood ({_BT.fit_phi(_nb, _mu):.2f} for a planted 1.40, {_BT.fit_phi(_po, _mu):.2f} for a Poisson)")
_dv = _BT.deviance(np.array([0, 3, 5]), np.array([1.0, 3.0, 4.0]))
check(abs(_dv[0] - 2.0) < 1e-9 and abs(_dv[1]) < 1e-12 and _dv[2] > 0 and _BT.paired(np.array([-1.0, -1.0, -1.0, -1.0]), np.array([1, 2, 3, 4]))[0] == -1.0, "Poisson deviance and the week-clustered paired test compute")
check((tmp / "data" / "lines_log.csv").exists() and len(pd.read_csv(tmp / "data" / "lines_log.csv")) >= 10 and "proj_model" in pd.read_csv(tmp / "data" / "lines_log.csv").columns, "the model's number for every line is logged at each pull")
_pcsv = pd.read_csv(tmp / "data" / "cache" / "projections.csv")
_fx = [c for c in _pcsv.columns if c.startswith("fx_")]
check(len(_fx) >= 12 and {"fx_role", "fx_volume", "fx_snaps", "fx_tilt"} <= set(_fx) and _pcsv[_fx].abs().max().max() < 1.0 and (_pcsv.fx_volume.abs() > 0.005).any()
      and (_pcsv[_pcsv.role_signal.astype(str) == "True"].fx_role > 0.01).mean() > 0.8 and (_pcsv[_pcsv.role_signal.astype(str) != "True"].fx_role.abs() < 1e-9).all(),
      f"every signal's effect on the final projection is measured by rebuilding it without the signal; next man up lifts the backups it fires for and no one else ({len(_fx)} signals)")
# the scoreboard on a synthetic graded week: a model that knows the answer must beat a book that prices every line a coin flip
from pipeline import linelog as _LL, evaluate as _EV
_wk = pw[(pw.season == 2026) & (pw.week == 6)].drop_duplicates("name_key").head(60).reset_index(drop=True)
_half = np.arange(len(_wk)) % 2 == 0
_lg = pd.DataFrame(dict(season=2026, week=6, player=_wk.player.values, player_id=_wk.player_id.astype(str).values, team=_wk.team.values, market="player_tackles_assists", proj_model=_wk.comb.values.astype(float) + 0.2, phi=1.0, exp_opps=50.0, share_pred=0.8, pulled_at="t"))
_snap = pd.DataFrame(dict(event_id="B1", commence_time="2026-10-18T17:00:00Z", book="DraftKings", market="player_tackles_assists", player=_wk.player.values, line=np.where(_half, _wk.comb.values - 1.5, _wk.comb.values + 1.5), over_odds=-110, under_odds=-110, pulled_at="20261018T165500Z"))
_old_log = _LL.LOG; _LL.LOG = tmp / "data" / "lines_log_test.csv"; _lg.to_csv(_LL.LOG, index=False)
_snapdir = Path("data/odds/2026/wk06"); _snapdir.mkdir(parents=True, exist_ok=True); _snap.to_csv(_snapdir / "20261018T165500Z.csv", index=False)
_cf = _EV.closing_frame(pw, 2026, weeks=[6]); _sb = _EV.scoreboard(_cf); _LL.LOG = _old_log
check(len(_cf) >= 30 and _sb and _sb["lines"] >= 30 and _sb["log_loss"]["engine"] < _sb["log_loss"]["market"] and abs(_sb["log_loss"]["market"] - np.log(2)) < 1e-6 and _sb["engine_minus_market"] > 0
      and _sb["se"] is None and _sb["t"] is None and len(_sb["by_week"]) == 1 and len(_sb["tiers"]) == 4 and _sb["tiers"][0]["lines"] > 0 and _sb["tiers"][0]["hit"] > 0.9 and _sb["calibration"],
      f"the scoreboard scores the engine against the book's fair close on every line, and says nothing about sureness from a single week (market {_sb.get('log_loss', {}).get('market')}, engine {_sb.get('log_loss', {}).get('engine')})")
check({"p_low", "p_model", "edge_low", "tier", "market_over"} <= set(pd.read_csv(tmp / "data" / "lines_log.csv").columns), "the line log keeps the engine's read of every line, picked or not, so a rule can be scored later without having been live")
# in-sample and out-of-sample are kept apart: a week before the engine's first week is never called a test of it
_sb_live = _EV.scoreboard(_cf, live_week=6)
check(_sb["since"] is None and _sb["live_week"] == C.ENGINE_LIVE["week"] and all(r["since"] is None for r in _sb["shadow"]) and [w["state"] for w in _sb["watches"]] == ["running", "running"] and _sb["watches"][0]["n"] == 0
      and _sb_live["since"]["lines"] == _sb_live["lines"] and abs(_sb_live["since"]["engine_minus_market"] - _sb_live["engine_minus_market"]) < 1e-12 and _sb_live["since"]["t"] is None
      and all(r["since"]["lines"] == _sb_live["lines"] for r in _sb_live["shadow"]) and _sb_live["watches"][0]["n"] == 1 and _sb_live["watches"][0]["state"] == "running",
      "the scoreboard reports the weeks since the engine apart from the weeks its weight was chosen on, and reads no verdict before the weeks are in")
# the candidates in the shadow, on lines where each has a known answer
_sv = pd.DataFrame(dict(week=[1, 1, 2, 2, 2, 1], kind=["combined", "combined", "combined", "combined", "solo", "solo"], line=[4.5] * 6, p_mkt=[0.5] * 6, proj_model=[4.0, 6.0, 4.0, 6.0, 4.0, 5.0], phi=[1.2] * 6, actual=[8.0, 12.0, 3.0, 9.0, 2.0, 10.0], level=[1.0] * 6))
_sh = _EV._shadow(_sv, C.ENGINE)
_pm = np.clip([M.p_over(m, 1.2, 4.5) for m in _sv.proj_model], 0.02, 0.98); _lgt = lambda p: np.log(p / (1 - p)); _sgm = lambda z: 1 / (1 + np.exp(-z))
_bc, _bs = M.engine_betas("combined")[0], M.engine_betas("solo")[0]
_ratio_solo = min(C.LINED_LEVEL["clip"][1], 1 + (10.0 - 5.0) / 5.0 * 1 / (1 + C.SHADOW["level_shrink"]))          # week 1's solo line came in at twice its projection
_lv = _EV.lined_level(_sv, 2)
check(abs(_sh["beta_by_kind"][0] - _sgm(C.SHADOW["beta_by_kind"]["combined"] * _lgt(_pm[0]))) < 1e-9 and abs(_sh["beta_by_kind"][4] - _sgm(C.SHADOW["beta_by_kind"]["solo"] * _lgt(_pm[4]))) < 1e-9
      and abs(_sh["centred"][0] + _sh["centred"][1] - 1) < 1e-9 and abs(_sh["centred"][4] - M.engine_chance(_pm[4], 0.5, _bs)) < 1e-9
      and abs(_sh["lined_level"][0] - M.engine_chance(_pm[0], 0.5, _bc)) < 1e-9
      and abs(_sh["lined_level"][4] - M.engine_chance(min(0.98, max(0.02, M.p_over(4.0 * _ratio_solo, 1.2, 4.5))), 0.5, _bs)) < 1e-9 and _sh["lined_level"][4] > M.engine_chance(_pm[4], 0.5, _bs)
      and abs(_lv["combined"] - min(C.LINED_LEVEL["clip"][1], 1 + (20.0 - 10.0) / 10.0 * 2 / (2 + C.LINED_LEVEL["shrink"]))) < 1e-9 and _EV.lined_level(_sv, 1)["combined"] == 1.0
      and abs(_EV.lined_level(_sv.assign(level=1.02, proj_model=_sv.proj_model * 1.02), 2)["combined"] - _lv["combined"]) < 1e-9,
      "the candidates in the shadow compute what they are written down as, and the level for lined players uses earlier lined games only, on the model's number before any level")
# the weight by market, and the grade: an A is a pick the sleeper rule also names; agreement from the book never earns it
check(M.engine_betas("solo") == (0.65, 0.325) and M.engine_betas("combined") == (0.35, 0.175) and M.engine_betas("assists") == (C.ENGINE["beta"], C.ENGINE["beta"] * C.ENGINE["low_ratio"])
      and M.engine_grade(0.001, 0.62, False, "player_solo_tackles", sleeper_match=True) == "A" and M.engine_grade(0.05, 0.9, False, "player_solo_tackles", sleeper_match=False) == "B"
      and M.engine_grade(0.001, 0.9, False, "player_solo_tackles", sleeper_match=False) == "C" and M.engine_grade(0.05, 0.9, True, "player_solo_tackles", sleeper_match=True) == "B"
      and M.engine_grade(-0.01, 0.9, False, "player_solo_tackles", sleeper_match=True) is None and M.engine_grade(0.05, 0.9, False, "player_assists", sleeper_match=True) == "B",
      "the model's disagreement weighs 0.65 on solo lines and 0.35 on combined, and an A is a pick that is also a sleeper with a clear checklist")
# a pull rebuilds the projections when a player expected to play is ruled out (or cleared) since the morning
_rb = pd.DataFrame(dict(team=["AAA", "AAA", "BBB", "AAA"], player=["Starter", "Backup", "Other", "Deep"], status=["", "", "out", ""], share_pred=[0.9, 0.4, 0.8, 0.05]))
_ra = _rb.assign(status=["out", "questionable", "", "out"])
_news = R.role_news(_rb, _ra, now=dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc))
check(sorted(n[1] for n in _news) == ["Other", "Starter"] and R.role_news(_rb, _rb) == [], f"a starter ruled out or cleared since the morning is news that rebuilds the projections; a new questionable tag or a deep reserve is not ({_news})")
# the record of the engine's own weeks: picks before its first week are out, the register's conditions count the right picks
_lv = C.ENGINE_LIVE
_ep = pd.DataFrame(dict(season=_lv["season"], week=[_lv["week"] - 1, _lv["week"], _lv["week"], _lv["week"], _lv["week"] + 1, _lv["week"] + 1], player=list("abcdef"),
                        market=["player_solo_tackles", "player_tackles_assists", "player_tackles_assists", "player_solo_tackles", "player_tackles_assists", "player_solo_tackles"],
                        side=["Under", "Under", "Over", "Under", "Under", "Under"], grade=["A", "A", "C", "B", "A", "C"], result=["Win", "Win", "Loss", "Win", "Loss", "Pending"],
                        units=[0.9, 0.8, -1.0, 1.1, -1.0, 0.0], stake=[1.0, 2.0, 0.1, 0.5, 1.0, 0.3], p_claim=[0.6, 0.62, 0.52, 0.58, 0.61, 0.55], p_model=[0.72, 0.74, 0.55, 0.66, 0.71, 0.6],
                        five=[True, True, False, False, True, False], group=["CB", "LB", "LB", "S", "LB", "DL"], commence_time="2026-11-15T18:00:00Z"))
_era = G.engine_era(_ep); _wt = {w["name"]: w for w in _era["watches"]}; _none = G.engine_era(_ep.iloc[0:1])
check(_era["bets"] == 4 and _era["wins"] == 2 and _era["losses"] == 2 and _era["pending"] == 1 and abs(_era["units"] - (-0.1)) < 1e-9 and abs(_era["units_at_stake"] - (1.6 - 0.1 + 0.55 - 1.0)) < 1e-9 and abs(_era["staked"] - 3.6) < 1e-9
      and len(_era["by_week"]) == 2 and _wt["A picks"]["n"] == 2 and _wt["A picks"]["of"] == 30 and _wt["A picks"]["state"] == "running" and abs(_wt["A picks"]["model_said"] - 0.725) < 1e-9
      and _wt["Combined A picks"]["n"] == 2 and _wt["Over picks"]["n"] == 1 and _wt["Locks"]["wins"] == 1 and _wt["Locks"]["losses"] == 1 and _wt["Locks"]["state"] == "running"
      and _era["locks"]["bets"] == 2 and {g["grade"] for g in _era["by_grade"]} == {"A", "B", "C"} and sum(c["bets"] for c in _era["calibration"]) == 4
      and _none["bets"] == 0 and len(_none["watches"]) == 5 and all(w["state"] == "running" for w in _none["watches"]),
      f"the record since the engine leaves out the weeks before it and counts each condition of the decision register ({_era['wins']}-{_era['losses']}, {len(_era['watches'])} conditions)")
_evd = "\n".join(G._evidence_sections(dict(scoreboard=_sb_live, era=_era, bets=5, wins=3, losses=2, pushes=0, units=0.8, hit_lo=0.2, hit_hi=0.9, by_grade=G.record_by_grade(_ep), by_side_market=[])))
check(all(k in _evd for k in ("## Against the market", "(out of sample)", "### Candidates in the shadow", "## Since the engine", "Conditions of the decision register on trial", "| E2 The engine's weight (0.65 solo, 0.35 combined) |", "| E4 A picks |", "## All plays to date"))
      and "likely range" in _evd and "No graded closing lines yet." in "\n".join(G._evidence_sections({})),
      "the weekly log carries the evidence in plain text: the scoreboard with the weeks since the engine apart, the shadow, the engine's own record, the conditions on trial")
check(all(k in _html for k in ("rec-trial", "Rules on trial", "Candidates in the shadow", "sb.since", "s.era")), "site shows the out-of-sample verdict, the candidates in the shadow and the rules on trial")

_sg = json.loads((tmp / "data" / "cache" / "segments.json").read_text()) if (tmp / "data" / "cache" / "segments.json").exists() else {}
check(all("n_eff" in v and v["n_eff"] <= v["n"] + 1e-9 for v in _sg.values()) if _sg else True, f"segment calibration carries the recency-weighted count ({len(_sg)} segments)")

check('data-tab="gloss"' in _html and "function renderGloss" in _html and "No-vig CLV" in _html and "clv_pct" in _html, "site has the glossary tab and the no-vig CLV tile")
check(all(k in _html for k in ("Against the market", "Cautious edge", "Likely range", "s.scoreboard", "b.factor_tests", "odds_budget", "function whyBox", "ENGINE()")),
      "site explains the engine: the win chance and the cautious edge on every card, the scoreboard against the market, likely ranges, the daily factor tests, the credit budget")
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

# every library the code or this test imports must be in requirements.txt: the runner installs only that file, and a
# library that happens to be on the machine the test is written on hides the gap (cryptography on 2026-11-02; PyYAML from
# 2026-11-03 to 2026-11-09, when this test failed on GitHub on every push and passed everywhere else)
import ast as _pyast
_req = {l.split("==")[0].strip().lower() for l in (ROOT / "requirements.txt").read_text().splitlines() if l.strip() and not l.lstrip().startswith("#")}
_dist_name = {"yaml": "pyyaml", "sklearn": "scikit-learn"}                 # import name -> the name it is installed under
_own = {p.stem for p in ROOT.glob("*.py")} | {p.name for p in ROOT.iterdir() if p.is_dir()}
_libs = set()
for _f in [p for pat in ("*.py", "pipeline/*.py", "tests/*.py", "tools/*.py", "research/*.py") for p in ROOT.glob(pat)]:
    for _n in _pyast.walk(_pyast.parse(_f.read_text())):
        if isinstance(_n, _pyast.Import):
            _libs |= {a.name.split(".")[0] for a in _n.names}
        elif isinstance(_n, _pyast.ImportFrom) and _n.module and not _n.level:
            _libs.add(_n.module.split(".")[0])
_libs -= set(sys.stdlib_module_names) | _own
_unlisted = sorted(m for m in _libs if _dist_name.get(m, m).lower() not in _req)
check(len(_libs) >= 6 and not _unlisted, f"every library the code and this test import is pinned in requirements.txt ({len(_libs)} libraries; unlisted: {', '.join(_unlisted) or 'none'})")

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
_steps = _tk["jobs"]["tick"]["steps"]
check("workflow_dispatch" in (_tk.get(True) or _tk.get("on")) and "gh workflow run ticker.yml" in str(_steps[-1].get("run")) and _steps[-1].get("if") == "always()"
      and _tk["permissions"].get("actions") == "write" and "GH_TOKEN" in _tk["jobs"]["tick"]["env"],
      "a ticker run that ends starts the next one itself (the scheduler dropped 11 hours of runs on 2026-11-09)")
# the odds-credit budget: what is worth most per credit is kept longest
_U = dt.timezone.utc
def _week_of(thu):
    t0 = dt.datetime(thu.year, thu.month, thu.day, tzinfo=_U); iso = lambda d, h, m: (t0 + dt.timedelta(days=d, hours=h, minutes=m)).isoformat()
    return [iso(1, 1, 15)] + [iso(3, 18, 0)] * 9 + [iso(3, 21, 5)] * 2 + [iso(3, 21, 25)] * 2 + [iso(4, 1, 20), iso(5, 1, 15)]
_ks = _week_of(dt.date(2026, 11, 12)) + _week_of(dt.date(2026, 11, 19)) + _week_of(dt.date(2026, 11, 26))
_t0 = dt.datetime(2026, 11, 10, 6, 0, tzinfo=_U)
_rich, _poor, _broke = R.credit_budget(now=_t0, credits=2000, kickoffs=_ks), R.credit_budget(now=_t0, credits=185, kickoffs=_ks), R.credit_budget(now=_t0, credits=60, kickoffs=_ks)
_kinds = {p_[4]: p_[1] for p_ in _rich["pulls"]}
check(_rich["level"] == 3 and _poor["level"] in (0, 1) and _broke["level"] == -1 and _broke["short"] > 0 and _poor["short"] == 0 and R.credit_reset(_t0) == dt.datetime(2026, 12, 1, tzinfo=_U)
      and _kinds["2026-11-12 09:00"] == "early" and _kinds["2026-11-14 20:00"] == "sat" and _kinds["2026-11-15 10:00"] == "look" and _kinds["2026-11-15 prekick-11:00"] == "prekick"
      and R.credit_budget(now=_t0, credits=None, kickoffs=_ks)["level"] == 3,
      f"the credit budget prices the rest of the month at each service level (2000 credits: level {_rich['level']}; 185: {_poor['level']}; 60: {_broke['level']}, short by {_broke['short']})")
_cr, _srv, _ran, _spent = 185.0, set(), {}, {}
for _at_, _kind, _nd, _nc, _key in _poor["pulls"]:
    _g = R.govern(_key, R.credit_budget(now=_at_, credits=_cr, kickoffs=_ks, served=_srv, current=_key))
    _cost = len(_g["markets"]) * (_nc if _g["cluster"] else _nd) if _g["run"] else 0
    _cr -= _cost; _srv.add(_key); _ran.setdefault(_kind, []).append(_g["run"]); _spent[_kind] = _spent.get(_kind, 0) + _cost
_gr = R.govern("2026-11-15 prekick-11:00", _rich)
check(all(_ran["prekick"]) and all(_ran["early"]) and _ran["sat"][0] and not all(_ran["sat"]) and not any(_ran["look"][:2]) and _cr >= C.MIN_CREDITS_LEFT - 1e-9
      and _gr["run"] and not _gr["cluster"] and len(_gr["markets"]) == len(C.ODDS_MARKETS) and R.govern("x 12h", _rich)["run"],
      f"on 185 credits every game keeps its pre-kickoff pull and the Thursday and Monday looks, the first Saturday look runs and later ones wait, and the month ends above the floor ({_cr:.0f} left; spent {_spent})")
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

# ---- audit 2026-11-09: each fix keeps its behaviour
from pipeline import sources as _S, odds as _O
_pw = pd.DataFrame(dict(solo=[2, 1], with_ast=[1, 0], ast=[1, 2]))
_pf = _S.apply_tackle_formula(_pw, "solo+with_ast+ast")
_hg = R.official_solo(_pf.assign(season=2026, week=1, team="X", name_key="p", player_id="1", group="LB"))
check(list(_pf.solo_t) == [2, 1] and list(_pf.solo_off) == [3, 1] and list(_pf.comb) == [4, 3] and list(_hg.solo_t) == [3, 1],
      "the model trains on solo alone (stable across seasons); grading uses the official count, a tackle with an assist as solo")
_lk = pd.DataFrame([dict(season=2026, week=99, player=f"P{i}", team="AAA", group="LB", market="player_solo_tackles", side="Under", line=3.5, book="DK",
                         lock=90 - i, grade=g, lock_block="", commence_time="2099-01-01T18:00:00Z", five=False) for i, g in enumerate(["B", "A"])])
_lk = G.mark_locks(_lk, 2026, 99)
check(not _lk[_lk.grade == "B"].five.any() and _lk[_lk.grade == "A"].five.all(), "a lock must be an A: a 72+ score the claimed-edge gate made a B is never a lock")
_sc = pd.DataFrame([dict(season=2026, week=8, side="Under", market="player_solo_tackles", group="CB", p_claim=0.62, segment_adj=0.08, model_over=0.3,
                         result="Win" if i < 14 else "Loss", units=0.5 if i < 14 else -1.0) for i in range(20)])
_segs, _ = G.segment_calibration(_sc)
check(abs(_segs["Under solo CB"]["claimed"] - 0.54) < 1e-9, "the segment correction is measured against the claim before its own correction")
_od = Path("data/odds/2026/wk98"); _od.mkdir(parents=True, exist_ok=True)
pd.DataFrame([dict(event_id="E1", commence_time="2099-01-01T18:00:00Z", book="DK", market="player_solo_tackles", player="Pat", line=3.5, over_odds=-110, under_odds=-110, pulled_at="20990101T100000Z")]).to_csv(_od / "20990101T100000Z.csv", index=False)
pd.DataFrame([dict(event_id="E1", commence_time="2099-01-01T18:00:00Z", book="DK", market="player_solo_tackles", player="Pat", line=2.5, over_odds=-110, under_odds=-110, pulled_at="20990101T120000Z")]).to_csv(_od / "20990101T120000Z.csv", index=False)
_ll, _al = _O.latest_lines(2026, 98), _O.all_lines(2026, 98)
check(list(_ll.line) == [2.5] and sorted(_al.line) == [2.5, 3.5], "a line the book moved leaves the board (pricing), but My board still finds it")
_st = pd.DataFrame(dict(season=[2026, 2026], week=[7, 7], team=["MIN", "SEA"], name_key=["byronmurphy", "byronmurphy"], comb=[3, 3], solo_t=[2, 1]))
_mp = G._merge_stats(pd.DataFrame(dict(season=[2026], week=[7], team=["MIN"], name_key=["byronmurphy"])), _st.assign(ast_t=_st.comb - _st.solo_t))
check(int(_mp.solo.iloc[0]) == 2 and int(_mp.comb.iloc[0]) == 3, "two players sharing a name are graded apart by team")
check(G.lock_blocked(pd.DataFrame(dict(lock_block=["not a pick at the last pull"]))).all(), "a logged pick the board stopped making is blocked from the locks")
_L2 = pd.DataFrame(dict(player=["Pat"] * 3, market=["player_solo_tackles"] * 3, line=[3.5, 3.5, 25.5], over_odds=[-110, -105, -150], under_odds=[-110, -115, np.nan]))
_two = _L2.over_odds.notna() & _L2.under_odds.notna()
check(float(_L2[_two].line.median()) == 3.5, "the consensus line comes from books quoting both sides (an Over-only 25.5 does not move it)")
print("\nALL CHECKS PASSED" if not fails else f"\n{len(fails)} CHECK(S) FAILED")
sys.exit(1 if fails else 0)
