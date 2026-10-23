"""Entry point.

  python run.py daily            refresh stats, rerun backtest and projections, grade picks, rebuild the site data
  python run.py odds [--hours N] pull tackle lines (needs ODDS_API_KEY), price them, log picks, rebuild the site data
  python run.py odds --auto      choose the pull window from the day and time (used by the scheduled job)
"""
import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import config as C
from pipeline import backtest as B
from pipeline import grade as G
from pipeline import model as M
from pipeline import odds as O
from pipeline import sources as S

SITE = Path("docs/data")
CACHE = Path("data/cache")


def _json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    def clean(o):
        if isinstance(o, dict):
            return {k: clean(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [clean(v) for v in o]
        if isinstance(o, (np.floating, float)):
            return None if not np.isfinite(o) else round(float(o), 4)
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.bool_,)):
            return bool(o)
        return o
    path.write_text(json.dumps(clean(obj), indent=1, default=str))


def records(df, cols=None):
    if df is None or len(df) == 0:
        return []
    d = df[cols] if cols else df
    return json.loads(d.to_json(orient="records", date_format="iso"))


def upcoming_week(sched, season):
    s = sched[sched.season == season]
    open_weeks = s[s.home_score.isna()].week
    return int(open_weeks.min()) if len(open_weeks) else int(s.week.max()) + 1


def load_all():
    seasons = sorted(set(C.HISTORY_SEASONS + [C.SEASON]))
    pw, used = S.load_player_week(seasons)
    checks = json.loads(Path("data/known_checks.json").read_text())
    formula, ok, report = S.choose_tackle_formula(pw, checks)
    pw = S.apply_tackle_formula(pw, formula)
    sched = S.load_schedule(seasons)
    snaps = S.load_snaps(seasons)
    inj = S.load_injuries([C.SEASON])
    H = M.add_history_features(M.prepare(pw, sched, snaps))
    H = M.role_signals_backtest(H)
    status = dict(stats_source=used, tackle_formula=formula, formula_check_ok=ok, formula_check=report,
                  snaps_rows=int(len(snaps)), injury_rows=int(len(inj)))
    return seasons, pw, sched, snaps, inj, H, status


def cmd_daily():
    seasons, pw, sched, snaps, inj, H, status = load_all()
    week = upcoming_week(sched, C.SEASON)
    bt, phi, k = B.run_backtest(H, seasons)
    F = M.upcoming_rows(H, sched, inj, C.SEASON, week)
    P = M.finalize_projections(F, phi, k=k)
    CACHE.mkdir(parents=True, exist_ok=True)
    if len(P):
        P.to_csv(CACHE / "projections.csv", index=False)
    json.dump(dict(phi=phi, k=k, week=week), open(CACHE / "model_state.json", "w"))
    graded, summary = G.grade(pw)
    lines = O.latest_lines(C.SEASON, week)
    bets = M.price_lines(lines, P) if len(lines) else pd.DataFrame()
    write_site(P, bets, bt, graded, summary, week, status, lines_pulled=None if lines.empty else str(lines.pulled_at.max()))
    print(f"daily: week {week}, {len(P)} projections, {len(bets)} priced lines, backtest on {bt.get('games', 0)} games")


def cmd_odds(hours=None, auto=False):
    key = os.environ.get("ODDS_API_KEY") or ("fake" if os.environ.get("TACKLE_FAKE_ODDS") else None)
    if not key:
        sys.exit("ODDS_API_KEY is not set. Add it as a GitHub Actions secret (see README).")
    if not (CACHE / "projections.csv").exists():
        cmd_daily()
    P = pd.read_csv(CACHE / "projections.csv")
    state = json.load(open(CACHE / "model_state.json"))
    week = int(state["week"])
    if auto:
        now = dt.datetime.now(dt.timezone.utc)
        # full slate Friday and early Sunday; otherwise only games starting in the next few hours
        hours = None if (now.weekday() == 4 or (now.weekday() == 6 and now.hour < 14)) else 4
    rows, remaining = O.pull(key, hours_ahead=hours)
    O.save_snapshot(rows, C.SEASON, week)
    lines = O.latest_lines(C.SEASON, week)
    bets = M.price_lines(lines, P)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    n_new = G.log_picks(bets, C.SEASON, week, stamp)
    meta_path = SITE / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    meta.update(odds_credits_remaining=remaining, lines_pulled=stamp, lines_count=int(len(lines)))
    _json(meta_path, meta)
    _json(SITE / "bets.json", records(bets))
    print(f"odds: {len(rows)} prices pulled, {len(lines)} current lines, {n_new} new picks logged, credits left {remaining}")


def write_site(P, bets, bt, graded, summary, week, status, lines_pulled):
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
    meta = dict(generated_at=now, season=C.SEASON, week=week, lines_pulled=lines_pulled, **status,
                bars=dict(pick=C.PICK_BAR, signal=C.SIGNAL_BAR))
    old = SITE / "meta.json"
    if old.exists():
        prev = json.loads(old.read_text())
        meta.setdefault("odds_credits_remaining", prev.get("odds_credits_remaining"))
    _json(SITE / "meta.json", meta)
    cols = ["player", "team", "opp_team", "group", "status", "n_prev", "season_avg", "last", "base", "proj", "proj_solo",
            "fair_line", "fair_line_solo", "crew_comb", "crew_solo", "spread_dog", "role_signal", "venue", "gameday", "gametime", "phi"]
    _json(SITE / "projections.json", records(P, [c for c in cols if c in P.columns]) if len(P) else [])
    _json(SITE / "bets.json", records(bets))
    _json(SITE / "backtest.json", bt)
    _json(SITE / "results.json", dict(summary=summary, picks=records(graded)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["daily", "odds"])
    ap.add_argument("--hours", type=float, default=None)
    ap.add_argument("--auto", action="store_true")
    a = ap.parse_args()
    cmd_daily() if a.cmd == "daily" else cmd_odds(a.hours, a.auto)
