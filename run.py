"""Entry point.

  python run.py daily            refresh stats, rerun backtest and projections, grade picks, rebuild the site data
  python run.py odds [--hours N] pull tackle lines (needs ODDS_API_KEY), price them, log picks, rebuild the site data
  python run.py odds --auto      run only if this is a scheduled pull slot (Edmonton time) or an international game is
                                 12 h or 1 h from kickoff; the job runs every half hour and this decides what, if anything, to pull
"""
import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

from zoneinfo import ZoneInfo

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
EDMONTON = ZoneInfo("America/Edmonton")
EASTERN = ZoneInfo("America/New_York")

# Scheduled pull slots, Edmonton local time (minutes after midnight) by weekday (Mon=0), and which games each covers.
# The job runs every half hour; a run that is not within 14 minutes of a slot does nothing.
PULL_SLOTS = {
    3: [(9 * 60, "thu_fri"), (14 * 60, "thu_fri"), (17 * 60 + 30, "thu_fri")],   # Thursday: Thursday and Friday games
    4: [(18 * 60, "sat")],                                                        # Friday evening: Saturday games, if any
    5: [(9 * 60, "sat_sun"), (18 * 60, "sun")],                                   # Saturday: Saturday and Sunday games, then Sunday
    0: [(9 * 60, "mon"), (17 * 60 + 30, "mon")],                                  # Monday: the Monday game
}
INTL_WINDOWS_H = (12, 1)           # international games are pulled this many hours before kickoff
SERVED = CACHE / "pull_slots.json"  # slots already served, so a late run still pulls once and an on-time run doesn't pull twice


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


def week_games(sched, season, week):
    """This week's games with kickoff in UTC and an international flag (nflverse marks overseas games as neutral site)."""
    g = sched[(sched.season == season) & (sched.week == week)]
    out = []
    for r in g.itertuples():
        try:
            kick = dt.datetime.strptime(f"{r.gameday} {r.gametime}", "%Y-%m-%d %H:%M").replace(tzinfo=EASTERN)
        except ValueError:
            continue
        out.append(dict(game_id=r.game_id, home=r.home_team, away=r.away_team, kickoff=kick.astimezone(dt.timezone.utc).isoformat(),
                        edmonton=kick.astimezone(EDMONTON).strftime("%a %Y-%m-%d %H:%M"), international=str(r.location).lower().startswith("neutral")))
    return out


def auto_plan(now=None, games=None, served=None):
    """What a scheduled run should pull right now: a dict of pull() keyword arguments (with a `key` naming the slot
    it serves), or None to do nothing. GitHub's cron drifts by up to half an hour, so a slot is served by the first
    run after its time, once; `served` is the set of keys already served (persisted in data/cache/pull_slots.json)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    served = set(served or [])
    local = now.astimezone(EDMONTON)
    today = local.date()
    d = lambda n: str(today + dt.timedelta(days=n))
    due = []
    for slot, what in PULL_SLOTS.get(local.weekday(), []):
        key = f"{today} {slot // 60:02d}:{slot % 60:02d}"
        if local.hour * 60 + local.minute >= slot and key not in served:
            days = {"thu_fri": [d(0), d(1)], "sat": [d(1)], "sat_sun": [d(0), d(1)], "sun": [d(1)], "mon": [d(0)]}[what]
            due.append((slot, dict(days=days, key=key, reason=f"{local.strftime('%A')} {slot // 60:02d}:{slot % 60:02d} slot (run at {local.strftime('%H:%M')}): games on {days}")))
    if due:
        due.sort()
        plan = due[-1][1]                       # the latest slot that is due; earlier unserved ones today are stale
        plan["also_served"] = [p["key"] for _, p in due[:-1]]
        return plan
    # international games: once in the hour starting 12 h before kickoff, once in the hour starting 1 h before
    for g in games or []:
        if not g.get("international"):
            continue
        kick = dt.datetime.fromisoformat(g["kickoff"])
        ahead_h = (kick - now).total_seconds() / 3600
        for h in INTL_WINDOWS_H:
            key = f"{g['game_id']} {h}h"
            if 0 < ahead_h <= h and key not in served:
                return dict(teams=(g["home"], g["away"]), key=key, reason=f"international game {g['away']} at {g['home']} is {ahead_h:.1f} h from kickoff ({h} h window)")
    return None


def load_served():
    try:
        return set(json.loads(SERVED.read_text()))
    except (OSError, ValueError):
        return set()


def mark_served(keys):
    served = load_served() | set(keys)
    cutoff = str(dt.date.today() - dt.timedelta(days=10))
    served = {k for k in served if k[:10] >= cutoff or not k[:4].isdigit()}   # keep slot keys for ten days; game keys stay
    SERVED.parent.mkdir(parents=True, exist_ok=True)
    SERVED.write_text(json.dumps(sorted(served), indent=1))


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
    vol = S.load_team_volume(seasons)
    pbp, pfr, dc = S.load_pbp_tackles(seasons), S.load_pfr_def(seasons), S.load_depth_charts(seasons)
    if len(pbp["teams"]):
        t = pbp["teams"].rename(columns={"runs_faced": "faced_runs", "comps_faced": "faced_comps"})
        vol = vol.merge(t, on=["season", "week", "team"], how="left")
        vol = vol.merge(t.rename(columns={"team": "opp_team", "faced_runs": "gen_runs", "faced_comps": "gen_comps"}), on=["season", "week", "opp_team"], how="left")
    H = M.add_history_features(M.attach_extras(M.attach_volume(M.prepare(pw, sched, snaps), vol), pbp, pfr, dc))
    H = M.role_signals_backtest(H)
    status = dict(stats_source=used, tackle_formula=formula, formula_check_ok=ok, formula_check=report,
                  snaps_rows=int(len(snaps)), injury_rows=int(len(inj)), volume_rows=int(len(vol)),
                  pbp_rows=int(len(pbp["players"])), pfr_rows=int(len(pfr)), depth_chart_rows=int(len(dc)))
    return seasons, pw, sched, snaps, inj, H, status, dict(vol=vol, pbp=pbp, pfr=pfr, dc=dc)


def mark_five(bets, season, week):
    """Flag the board's rows that are this week's five."""
    if bets is None or len(bets) == 0 or "side" not in bets:
        return bets
    keys = G.weekly_five_keys(season, week)
    bets = bets.copy()
    bets["five"] = [(r.player, r.market, r.side, float(r.line), r.book) in keys for r in bets.itertuples()]
    pk = set()
    if G.PARLAYS.exists():
        L = pd.read_csv(G.PARLAYS)
        L = L[(L.season == season) & (L.week == week)]
        pk = {(r.player, r.market, r.side, float(r.line), r.book) for r in L.itertuples()}
    bets["parlay"] = [(r.player, r.market, r.side, float(r.line), r.book) in pk for r in bets.itertuples()]
    return bets


def attach_game_logs(P, H, season, week):
    """This season's game-by-game tackles for every projected player, so the pricer can say how often he cleared a line."""
    if P is None or len(P) == 0:
        return P
    done = H[(H.season == season) & (H.week < week)].sort_values("week")
    comb = done.groupby("player_id").comb.apply(lambda x: "|".join(str(int(v)) for v in x))
    solo = done.groupby("player_id").solo_t.apply(lambda x: "|".join(str(int(v)) for v in x))
    P = P.copy()
    P["log_comb"] = P.player_id.map(comb).fillna("")
    P["log_solo"] = P.player_id.map(solo).fillna("")
    return P


def cmd_daily():
    seasons, pw, sched, snaps, inj, H, status, src = load_all()
    week = upcoming_week(sched, C.SEASON)
    bt, phi, k, scale = B.run_backtest(H, seasons)
    F = M.upcoming_rows(H, sched, inj, C.SEASON, week, vol=src["vol"], dc=src["dc"], pbp_starters=src["pbp"]["starters"])
    P = M.finalize_projections(F, phi, scale=scale)
    P = attach_game_logs(P, H, C.SEASON, week)
    CACHE.mkdir(parents=True, exist_ok=True)
    if len(P):
        P.to_csv(CACHE / "projections.csv", index=False)
    json.dump(dict(phi=phi, k=k, scale=scale, week=week), open(CACHE / "model_state.json", "w"))
    games = week_games(sched, C.SEASON, week)
    json.dump(games, open(CACHE / "games.json", "w"), indent=1)
    status["international_games"] = [f"{g['away']} at {g['home']}, {g['edmonton']} Edmonton" for g in games if g["international"]]
    graded, summary = G.grade(pw)
    parlays, psum = G.grade_parlays(pw)
    summary["parlays"] = psum
    G.write_five_log(graded, summary, Path("data/weekly_five.md"), parlays)
    lines = O.upcoming_only(O.latest_lines(C.SEASON, week))
    bets = M.price_lines(lines, P) if len(lines) else pd.DataFrame()
    bets = mark_five(bets, C.SEASON, week)
    write_site(P, bets, bt, graded, summary, week, status, lines_pulled=None if lines.empty else str(lines.pulled_at.max()), parlays=parlays)
    write_parlays(C.SEASON, week)
    print(f"daily: week {week}, {len(P)} projections, {len(bets)} priced lines, backtest on {bt.get('games', 0)} games")


def cmd_odds(hours=None, auto=False):
    keys = {name: os.environ[name] for name in C.ODDS_KEY_ENV if os.environ.get(name)}
    if not keys and os.environ.get("TACKLE_FAKE_ODDS"):
        keys = {"ODDS_API_KEY": "fake"}
    if not keys:
        sys.exit(f"None of {C.ODDS_KEY_ENV} is set. Add at least one as a GitHub Actions secret (see README).")
    if not (CACHE / "projections.csv").exists():
        cmd_daily()
    P = pd.read_csv(CACHE / "projections.csv")
    state = json.load(open(CACHE / "model_state.json"))
    week = int(state["week"])
    pull_kw = dict(hours_ahead=hours)
    if auto:
        games = json.load(open(CACHE / "games.json")) if (CACHE / "games.json").exists() else []
        plan = auto_plan(games=games, served=load_served())
        if plan is None:
            print("odds: no pull slot due and no international game in a pull window; nothing to do")
            return
        print(f"odds: {plan.pop('reason')}")
        mark_served([plan.pop("key")] + plan.pop("also_served", []))
        if "teams" in plan:
            home, away = plan.pop("teams")
            names = {M.TEAM_NAMES.get(home), M.TEAM_NAMES.get(away)}
            ev = O.list_events(next(iter(keys.values())))
            plan["event_ids"] = [e["id"] for e in ev if e.get("home_team") in names or e.get("away_team") in names]
        pull_kw = plan
    rows, credits = O.pull(keys, **pull_kw)
    numeric = [c for c in credits.values() if isinstance(c, (int, float))]
    remaining = int(sum(numeric)) if numeric else next(iter(credits.values()), None)
    O.save_snapshot(rows, C.SEASON, week)
    lines = O.upcoming_only(O.latest_lines(C.SEASON, week))
    bets = M.price_lines(lines, P)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    n_new = G.log_picks(bets, C.SEASON, week, stamp)
    G.build_parlays(bets, C.SEASON, week, stamp)
    bets = mark_five(bets, C.SEASON, week)
    write_parlays(C.SEASON, week)
    meta_path = SITE / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    meta.update(odds_credits_remaining=remaining, odds_credits_by_key=credits, lines_pulled=stamp, lines_count=int(len(lines)))
    _json(meta_path, meta)
    _json(SITE / "bets.json", records(bets))
    print(f"odds: {len(rows)} prices pulled, {len(lines)} current lines, {n_new} new picks logged, credits left {remaining}")


def write_parlays(season, week):
    """This week's recommended parlays for the Plays tab, with whether each is still open or already placed."""
    out = []
    if G.PARLAYS.exists():
        L = pd.read_csv(G.PARLAYS)
        L = L[(L.season == season) & (L.week == week)]
        now = dt.datetime.now(dt.timezone.utc)
        for pid, legs in L.groupby("parlay_id", sort=False):
            first = legs.iloc[0]
            start = pd.to_datetime(legs.commence_time, utc=True, errors="coerce")
            out.append(dict(parlay_id=pid, slate=first.slate, n_legs=int(len(legs)), combined_decimal=float(first.combined_decimal),
                            combined_american=G.american(float(first.combined_decimal)), combined_prob=float(first.combined_prob),
                            units=float(first.units), chosen_at=first.chosen_at, placed=bool((start <= now).any()),
                            first_kickoff=None if start.isna().all() else start.min().isoformat(),
                            legs=records(legs[[c for c in ["leg", "player", "team", "opp", "market", "side", "line", "book", "odds", "p_side", "mkt_side", "lock", "grade", "commence_time"] if c in legs.columns]])))
    _json(SITE / "parlays.json", out)


def write_site(P, bets, bt, graded, summary, week, status, lines_pulled, parlays=None):
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
    meta = dict(generated_at=now, season=C.SEASON, week=week, lines_pulled=lines_pulled, **status,
                bars=dict(pick=C.PICK_BAR, signal=C.SIGNAL_BAR),
                grading=dict(bars=C.GRADE_BARS, units=C.GRADE_UNITS, weights=C.LOCK_WEIGHTS, ev_full=C.LOCK_EV_FULL,
                             model_full=C.LOCK_MODEL_FULL, locks=C.LOCKS_PER_SLATE, line_weight=C.LINE_WEIGHT))
    old = SITE / "meta.json"
    if old.exists():
        prev = json.loads(old.read_text())
        meta.setdefault("odds_credits_remaining", prev.get("odds_credits_remaining"))
        meta.setdefault("odds_credits_by_key", prev.get("odds_credits_by_key"))
    _json(SITE / "meta.json", meta)
    cols = ["player", "team", "opp_team", "group", "status", "n_prev", "season_avg", "last", "base", "proj", "proj_solo",
            "fair_line", "fair_line_solo", "crew_comb", "crew_solo", "spread_dog", "role_signal", "venue", "gameday", "gametime", "phi",
            "dc_status", "opp_qb_out", "opp_rb_out", "rest", "pct_last3", "pct_prev"]
    _json(SITE / "projections.json", records(P, [c for c in cols if c in P.columns]) if len(P) else [])
    _json(SITE / "bets.json", records(bets))
    _json(SITE / "backtest.json", bt)
    retro = Path("data/retro_five.json")
    _json(SITE / "results.json", dict(summary=summary, picks=records(graded), parlays=records(parlays) if parlays is not None and len(parlays) else [],
                                      retro=json.loads(retro.read_text()) if retro.exists() else None))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["daily", "odds"])
    ap.add_argument("--hours", type=float, default=None)
    ap.add_argument("--auto", action="store_true")
    a = ap.parse_args()
    cmd_daily() if a.cmd == "daily" else cmd_odds(a.hours, a.auto)
