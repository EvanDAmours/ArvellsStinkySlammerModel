"""Entry point.

  python run.py daily            refresh stats, rerun backtest and projections, grade picks, rebuild the site data
  python run.py odds [--hours N] pull tackle lines (needs ODDS_API_KEY), price them, log picks, rebuild the site data
  python run.py odds --auto      run only if this is a scheduled pull slot (Edmonton time) or an international game is
                                 12 h or 1 h from kickoff; the job runs every half hour and this decides what, if anything, to pull
"""
import argparse
import datetime as dt
import json
import math
import os
import sys
from pathlib import Path

from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import config as C
from pipeline import backtest as B
from pipeline import evaluate as EV
from pipeline import linelog as LL
from pipeline import live_grade as LG
from pipeline import seal as SEAL
from pipeline import patchlog as PATCH
from pipeline import grade as G
from pipeline import model as M
from pipeline import odds as O
from pipeline import sources as S

SITE = Path("docs/data")
CACHE = Path("data/cache")
EDMONTON = ZoneInfo("America/Edmonton")
EASTERN = ZoneInfo("America/New_York")
# Alberta stays on UTC-6 all year from 2026-11-01 ("Alberta Time", tzdata 2026e). A runner with older zone data
# would fall back to UTC-7 that night and run every fixed slot an hour early in real Alberta time; guard against it.
if dt.datetime(2026, 11, 2, 12, 0, tzinfo=EDMONTON).utcoffset() != dt.timedelta(hours=-6):
    EDMONTON = dt.timezone(dt.timedelta(hours=-6), "Alberta")

# Scheduled pull slots, Edmonton local time (minutes after midnight) by weekday (Mon=0), and which games each covers.
# The job runs every quarter hour; each slot is served once by the first run after its time. A pull costs 3 credits
# per game (0 when no line is up). Trimmed on 2026-11-03 to stay inside one free 500-credit key a month (about 105
# credits a week): the Saturday hourly pulls went (68 credits in week 8 for lines that mostly sit until Sunday), the
# Friday pulls went, and Thursday, Sunday and Monday keep a morning look, a midday look and a pre-kickoff look.
def _hourly(start, end, what, step=60):
    return [(m, what) for m in range(start * 60, end * 60 + 1, step)]
# Fixed looks. Every game, on any weekday, also gets a pull an hour before its kickoff from the schedule (see
# kickoff_slots): that is what makes a Friday, Saturday or holiday game safe without a slot for its weekday.
PULL_SLOTS = {
    3: [(9 * 60, "thu_fri"), (13 * 60, "thu_fri")],   # Thursday 9 am and 1 pm: Thursday and Friday games (the pre-kickoff pull follows from the schedule)
    4: [],                                            # Friday: pre-kickoff pulls only, when there is a Friday game
    5: [(20 * 60, "sat_sun")],                        # Saturday 8 pm: Saturday and Sunday games, the whole slate once it is posted
    6: [(10 * 60, "today")],                          # Sunday 10 am: the slate with the inactives known (ties with the pre-kickoff pull on a normal week, so one pull)
    0: [(9 * 60, "mon"), (13 * 60, "mon")],           # Monday 9 am and 1 pm: the Monday game
}
# An early look at the whole week (Thursday to Monday), on the dates in config.OPENER_DATES only: a trial of how far
# the first posted lines sit from the closing ones (owner's request, 2026-11-10).
OPENER_SLOT = (10 * 60, "week")                   # Wednesday 10 am Edmonton


def slots_on(day):
    """The fixed slots of an Edmonton date: PULL_SLOTS for its weekday, plus the early look on a trial date."""
    extra = [OPENER_SLOT] if str(day) in getattr(C, "OPENER_DATES", ()) else []
    return list(PULL_SLOTS.get(day.weekday(), [])) + extra


INTL_WINDOWS_H = (12,)             # international games (early-morning kickoffs) also get a pull this many hours before kickoff; the hour-before pull comes from the schedule
PRE_KICK_MIN = 60                  # every game: one pull this many minutes before its kickoff (Edmonton time), covering every game that day not yet started
PRE_KICK_CLUSTER_MIN = 30          # kickoffs within this many minutes of each other share one pre-kickoff pull


def kickoff_slots(games, day):
    """(slot minutes, key) of the pre-kickoff pulls on `day` (an Edmonton date): one per cluster of kickoffs."""
    kicks = []
    for g in games or []:
        try:
            k = dt.datetime.fromisoformat(g["kickoff"]).astimezone(EDMONTON)
        except (KeyError, ValueError, TypeError):
            continue
        if k.date() == day:
            kicks.append(k)
    out, start = [], None
    for k in sorted(kicks):
        if start is None or (k - start).total_seconds() > PRE_KICK_CLUSTER_MIN * 60:
            start = k
            slot = start.hour * 60 + start.minute - PRE_KICK_MIN
            out.append((slot, f"{day} prekick-{max(slot, 0) // 60:02d}:{max(slot, 0) % 60:02d}"))
    return out
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
    for slot, what in slots_on(today):
        key = f"{today} {slot // 60:02d}:{slot % 60:02d}"
        if local.hour * 60 + local.minute >= slot and key not in served:
            days = {"week": [d(n) for n in range(1, 6)], "thu_fri": [d(0), d(1)], "sat": [d(1)], "sat_sun": [d(0), d(1)], "fri_weekend": [d(1), d(2)], "sun": [d(1)], "mon": [d(0)], "today": [d(0)]}[what]
            due.append((slot, dict(days=days, key=key, reason=f"{local.strftime('%A')} {slot // 60:02d}:{slot % 60:02d} slot (run at {local.strftime('%H:%M')}): games on {days}")))
    # every game day: one pull an hour before each cluster of kickoffs, from the schedule, covering every game that day
    # not yet started (a run that comes late because GitHub stalled still serves it; started games are simply skipped)
    for slot, key in kickoff_slots(games, today):
        if local.hour * 60 + local.minute >= slot and key not in served:
            due.append((slot, dict(days=[d(0)], key=key, reason=f"pre-kickoff slot {key.split()[-1][8:]} (run at {local.strftime('%H:%M')}): games on {d(0)}")))
    if due:
        due.sort(key=lambda x: x[0])            # by slot time only (two plans can share a time: the fixed 10 am and a pre-kickoff slot)
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


def next_pull(now=None, games=None):
    """When the next scheduled line pull is due (UTC ISO), from the fixed slots and Sunday's pre-kickoff slot."""
    now = now or dt.datetime.now(dt.timezone.utc)
    local = now.astimezone(EDMONTON)
    for n in range(8):
        day = local.date() + dt.timedelta(days=n)
        slots = [m for m, _ in slots_on(day)] + [m for m, _ in kickoff_slots(games, day)]
        for m in sorted(slots):
            t = dt.datetime.combine(day, dt.time(m // 60, m % 60), tzinfo=EDMONTON)
            if t > local:
                return t.astimezone(dt.timezone.utc).isoformat(timespec="minutes")
    return None


def load_served():
    try:
        return set(json.loads(SERVED.read_text()))
    except (OSError, ValueError):
        return set()


PULL_LOG = CACHE / "pull_log.json"    # slot key -> what happened: {"pulled": UTC stamp, "games": n} or {"skipped": UTC stamp}


def log_pull(key, pulled=None, skipped=(), games=None, saved=False):
    """Record what each slot did, for the site's pull ticker: the slot pulled (with its time), was folded into a
    later one (a stale slot when a run came late), or was left out to save odds credits (`saved`)."""
    try:
        logd = json.loads(PULL_LOG.read_text())
    except (OSError, ValueError):
        logd = {}
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    if key:
        logd[key] = dict(saved=now) if saved else dict(pulled=pulled or now, games=games)
    for k in skipped:
        logd.setdefault(k, dict(skipped=now))
    cutoff = str(dt.date.today() - dt.timedelta(days=10))
    logd = {k: v for k, v in logd.items() if k[:10] >= cutoff or not k[:4].isdigit()}
    PULL_LOG.parent.mkdir(parents=True, exist_ok=True)
    PULL_LOG.write_text(json.dumps(logd, indent=1, sort_keys=True))


def pull_schedule(now=None, games=None, days=7):
    """Every scheduled pull from today through the next `days` days (Edmonton time), with what happened to each:
    [{key, day, at (UTC ISO), kind: fixed|prekick, status: pulled|skipped|due|upcoming, pulled_at}]. 'due' means its
    time has passed and no run has served it yet; the site shows it as late after a grace period."""
    now = now or dt.datetime.now(dt.timezone.utc)
    local = now.astimezone(EDMONTON)
    served = load_served()
    try:
        logd = json.loads(PULL_LOG.read_text())
    except (OSError, ValueError):
        logd = {}
    out = []
    for n in range(days + 1):
        day = local.date() + dt.timedelta(days=n)
        slots = [(m, f"{day} {m // 60:02d}:{m % 60:02d}", "fixed") for m, _ in slots_on(day)]
        slots += [(m, k, "prekick") for m, k in kickoff_slots(games, day)]
        for m, key, kind in sorted(slots):
            at = dt.datetime.combine(day, dt.time(max(m, 0) // 60, max(m, 0) % 60), tzinfo=EDMONTON).astimezone(dt.timezone.utc)
            rec = logd.get(key, {})
            if "pulled" in rec:
                status = "pulled"
            elif "saved" in rec:
                status = "saved"                       # left out to keep credits for the pre-kickoff pulls
            elif "skipped" in rec or key in served:
                status = "skipped"
            elif at <= now:
                status = "due"
            else:
                status = "upcoming"
            out.append(dict(key=key, day=str(day), at=at.isoformat(timespec="minutes"), kind=kind, status=status,
                            pulled_at=rec.get("pulled"), games=rec.get("games")))
    # a fixed look and a pre-kickoff pull at the same minute are one pull: keep the one that ran
    seen, uniq = {}, []
    for s in out:
        prev = seen.get(s["at"])
        if prev is None:
            seen[s["at"]] = s; uniq.append(s)
        elif s["status"] == "pulled" and prev["status"] != "pulled":
            uniq[uniq.index(prev)] = s; seen[s["at"]] = s
    return uniq


def mark_served(keys):
    served = load_served() | set(keys)
    cutoff = str(dt.date.today() - dt.timedelta(days=10))
    served = {k for k in served if k[:10] >= cutoff or not k[:4].isdigit()}   # keep slot keys for ten days; game keys stay
    SERVED.parent.mkdir(parents=True, exist_ok=True)
    SERVED.write_text(json.dumps(sorted(served), indent=1))


# ---------------------------------------------------------------- the odds-credit budget (config.ODDS_BASE_MARKETS, ODDS_RESET_DAY)
# A pull costs one credit per market per game. What is worth most per credit is kept longest:
#   prekick  the pull an hour before a game's kickoff (inactives known; it is also the closing price everything is scored against)
#   early    the 9 am and 1 pm looks on a Thursday or Monday (a game or two each, a couple of credits)
#   sat      Saturday night's look at the whole Sunday slate
#   look     any other look (Sunday 10 am, an hour before the pre-kickoff pull; an international game's 12-hour look)
# then pulling the whole day again at each pre-kickoff pull rather than only the games about to kick off, then the assists market.
KICKOFFS = CACHE / "kickoffs.json"      # kickoff (UTC) of every game left this season, written by the daily
PULL_CLASS = {"prekick": 0, "early": 1, "sat": 2, "look": 3}
BUDGET_LEVELS = {3: "every scheduled pull, all three markets", 2: "every scheduled pull, without the assists trial market",
                 1: "two markets; one pre-kickoff pull a game, the Thursday and Monday looks and Saturday night's look",
                 0: "two markets; one pre-kickoff pull a game and the Thursday and Monday looks", -1: "two markets; one pre-kickoff pull a game and nothing else"}


def credit_reset(now):
    """The next time the key's credits reset (UTC)."""
    d = C.ODDS_RESET_DAY
    this = dt.datetime(now.year, now.month, d, tzinfo=dt.timezone.utc)
    if this > now:
        return this
    y, m = (now.year + 1, 1) if now.month == 12 else (now.year, now.month + 1)
    return dt.datetime(y, m, d, tzinfo=dt.timezone.utc)


def scheduled_pulls(now, kickoffs, until):
    """Every scheduled pull on the days from now to `until`: (at UTC, kind, games it covers pulling the whole day, games
    about to kick off, key). kind: a key of PULL_CLASS."""
    ks = sorted(dt.datetime.fromisoformat(k) for k in kickoffs or [])
    games = [dict(kickoff=k.isoformat()) for k in ks]
    out, day, end = [], now.astimezone(EDMONTON).date(), until.astimezone(EDMONTON).date()
    win = dt.timedelta(minutes=PRE_KICK_MIN + PRE_KICK_CLUSTER_MIN + 5)
    while day <= end:
        at_of = lambda m: dt.datetime.combine(day, dt.time(max(m, 0) // 60, max(m, 0) % 60), tzinfo=EDMONTON).astimezone(dt.timezone.utc)
        on = lambda dates, after: sum(1 for k in ks if k.astimezone(EDMONTON).date() in dates and k > after)
        d = lambda n: day + dt.timedelta(days=n)
        seen = set()
        for m, key in kickoff_slots(games, day):
            at = at_of(m); seen.add(m)
            out.append((at, "prekick", on({day}, at), sum(1 for k in ks if at < k <= at + win), key))
        for m, what in slots_on(day):
            if m in seen:
                continue                                  # the same minute as a pre-kickoff pull: one pull
            at = at_of(m)
            dates = {"week": {d(n) for n in range(1, 6)}, "thu_fri": {d(0), d(1)}, "sat": {d(1)}, "sat_sun": {d(0), d(1)}, "fri_weekend": {d(1), d(2)}, "sun": {d(1)}, "mon": {d(0)}, "today": {d(0)}}[what]
            n = on(dates, at)
            out.append((at, "sat" if what == "sat_sun" else "early" if what in ("thu_fri", "mon", "week") else "look", n, n, f"{day} {m // 60:02d}:{m % 60:02d}"))
        day += dt.timedelta(days=1)
    return sorted(p_ for p_ in out if p_[0] < until)


def level_cost(pulls, level):
    """Credits the listed pulls cost at a service level, every game assumed to have lines up (an empty response is free)."""
    nm = len(C.ODDS_MARKETS) if level == 3 else len(C.ODDS_BASE_MARKETS)
    keep = {3: 3, 2: 3, 1: 2, 0: 1, -1: 0}[level]         # the least protected class of pull this level still runs
    return sum(nm * ((n_day if level >= 2 else n_cluster) if kind == "prekick" else n_day) for _, kind, n_day, n_cluster, _ in pulls if PULL_CLASS[kind] <= keep)


def credit_budget(now=None, credits=None, kickoffs=None, served=(), current=None):
    """What the credits left can pay for until they reset. credits: the total left across keys (None: unknown, nothing is
    held back). Returns dict(level, label, spare, reset, costs, pulls, short): `level` is the richest schedule the whole
    remaining month can afford (BUDGET_LEVELS); `short` is how many credits the barest schedule (one pre-kickoff pull a
    game) lacks, 0 when it is covered. `govern` decides each pull from the same list."""
    now = now or dt.datetime.now(dt.timezone.utc)
    reset = credit_reset(now)
    if kickoffs is None:
        try:
            kickoffs = json.loads(KICKOFFS.read_text())
        except (OSError, ValueError):
            kickoffs = None
    if credits is None or kickoffs is None:
        return dict(level=3, label=BUDGET_LEVELS[3], spare=None, reset=reset.isoformat(timespec="minutes"), costs={}, pulls=[], short=0, known=False)
    served = set(served or ())
    pulls = [p_ for p_ in scheduled_pulls(now, kickoffs, reset) if (p_[0] > now or p_[4] == current) and (p_[4] not in served or p_[4] == current)]
    spare = float(credits) - C.MIN_CREDITS_LEFT
    costs = {lv: level_cost(pulls, lv) for lv in (3, 2, 1, 0, -1)}
    level = next((lv for lv in (3, 2, 1, 0, -1) if costs[lv] <= spare), -1)
    return dict(level=level, label=BUDGET_LEVELS[level], spare=spare, reset=reset.isoformat(timespec="minutes"), costs={str(k): v for k, v in costs.items()},
                pulls=pulls, short=max(0, int(math.ceil(costs[-1] - spare))), known=True)


def govern(plan_key, budget):
    """What this pull may do: dict(run, markets, cluster, kind, why). A pre-kickoff pull always runs. A look runs when,
    after paying for it, the credits still cover every later pull of a more protected class in its barest form (so this
    Saturday's look can run even when the month cannot afford every Saturday's). The whole day is pulled again at a
    pre-kickoff pull, and the assists market is asked for, only when the whole remaining schedule is affordable that way.
    A pull not on the schedule (an international game's 12-hour look) counts as a look."""
    base, full = list(C.ODDS_BASE_MARKETS), list(C.ODDS_MARKETS)
    if not budget.get("known"):
        return dict(run=True, markets=full, cluster=False, kind="prekick" if plan_key and "prekick" in str(plan_key) else "look", why="")
    pulls, spare = budget.get("pulls", []), budget["spare"]
    me = next((p_ for p_ in pulls if p_[4] == plan_key), None)
    kind = me[1] if me else ("prekick" if plan_key and "prekick" in str(plan_key) else "look")
    later = [p_ for p_ in pulls if p_[4] != plan_key]
    n_day, n_cluster = (me[2], me[3]) if me else (1, 1)
    barest = lambda cls: sum(len(base) * (p_[3] if p_[1] == "prekick" else p_[2]) for p_ in later if PULL_CLASS[p_[1]] < cls)
    everything = lambda nm: sum(nm * p_[2] for p_ in later)
    all_day = spare - len(base) * n_day >= everything(len(base))
    all_full = spare - len(full) * n_day >= everything(len(full))
    if kind == "prekick":
        return dict(run=True, markets=full if all_full else base, cluster=not all_day, kind=kind, why="")
    run_it = spare - len(base) * n_day >= barest(PULL_CLASS[kind])
    why = "" if run_it else f"left out to keep odds credits for the pulls that matter more ({spare:.0f} to spend before {budget['reset'][:10]}; this look would cost about {len(base) * n_day})"
    return dict(run=run_it, markets=full if all_full else base, cluster=False, kind=kind, why=why)


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
    inj = S.load_injuries(seasons)
    week_ahead = upcoming_week(sched, C.SEASON)
    espn = S.load_espn_injuries(C.SEASON, week_ahead)        # suspensions and IR stays the league report never carries
    inj = S.merge_injury_sources(inj, espn)
    roster_out = S.load_roster_out(C.SEASON, week_ahead)     # reserve lists neither feed always carries (Edmunds, week 9)
    inj = S.merge_injury_sources(inj, roster_out)
    vol = S.load_team_volume(seasons)
    pbp, pfr, dc = S.load_pbp_tackles(seasons), S.load_pfr_def(seasons), S.load_depth_charts(seasons)
    if len(pbp["teams"]):
        t = pbp["teams"].rename(columns={"runs_faced": "faced_runs", "comps_faced": "faced_comps"})
        vol = vol.merge(t, on=["season", "week", "team"], how="left")
        vol = vol.merge(t.rename(columns={"team": "opp_team", "faced_runs": "gen_runs", "faced_comps": "gen_comps"}), on=["season", "week", "opp_team"], how="left")
    H = M.add_history_features(M.attach_extras(M.attach_volume(M.prepare(pw, sched, snaps), vol), pbp, pfr, dc))
    H = M.attach_injury_status(H, inj)
    H = M.role_signals_backtest(H)
    cur_stats = pw[(pw.season == C.SEASON)]
    cur_snaps = snaps[(snaps.season == C.SEASON)] if len(snaps) else snaps
    freshness = dict(stats_through_week=int(cur_stats.week.max()) if len(cur_stats) else None,
                     snaps_through_week=int(cur_snaps.week.max()) if len(cur_snaps) else None)
    freshness["snaps_lag"] = bool(freshness["stats_through_week"] and freshness["snaps_through_week"] and freshness["snaps_through_week"] < freshness["stats_through_week"])
    status = dict(stats_source=used, tackle_formula=formula, formula_check_ok=ok, formula_check=report, freshness=freshness,
                  snaps_rows=int(len(snaps)), injury_rows=int(len(inj)), espn_injury_rows=int(len(espn)), roster_out_rows=int(len(roster_out)), volume_rows=int(len(vol)),
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
    pct = done.groupby("player_id").def_pct.apply(lambda x: "|".join(f"{v:.2f}" for v in x.fillna(0)))
    ast = done.groupby("player_id").apply(lambda d: "|".join(str(int(v)) for v in (d.comb - d.solo_t)), include_groups=False)
    P["log_comb"] = P.player_id.map(comb).fillna("")
    P["log_solo"] = P.player_id.map(solo).fillna("")
    P["log_ast"] = P.player_id.map(ast).fillna("")
    P["log_pct"] = P.player_id.map(pct).fillna("")      # snap share per game, so consistency can count in-role games only
    return P


def attach_consensus(P, season, week):
    """Outside expert-consensus tackle projections (FantasyPros, the top players at each position) beside the model's
    number: shown as a cross-check, logged with each pick, never used to price or choose. The week's rows are kept
    under data/consensus so the cross-check can be validated against results later."""
    if P is None or len(P) == 0:
        return P, 0
    fp = S.load_fantasypros(week)
    P = P.copy()
    for c in ("fp_comb", "fp_solo", "fp_ast", "fp_rel_comb", "fp_rel_solo"):
        P[c] = np.nan
    if fp.empty:
        return P, 0
    out = Path("data/consensus")
    out.mkdir(parents=True, exist_ok=True)
    fp.assign(season=season, week=week, pulled_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")).to_csv(out / f"fantasypros_{season}_w{int(week):02d}.csv", index=False)
    m = P[["team", "name_key"]].merge(fp, on=["team", "name_key"], how="left")
    for c in ("fp_comb", "fp_solo", "fp_ast"):
        P[c] = m[c].values
    # their numbers are not box-score tackles (on 2026-10-31 they ran 24% above the matched players' season averages,
    # a mix of sites' tackle definitions), so the usable signal is relative: how far the consensus sits above or
    # below its usual relation to this model for a player
    for c, base in (("fp_comb", "proj"), ("fp_solo", "proj_solo")):
        ratio = P[c] / P[base].where(P[base] > 0)
        typical = float(ratio.median()) if ratio.notna().sum() >= 5 else np.nan
        P[c.replace("fp_", "fp_rel_")] = (ratio / typical - 1) if typical and typical > 0 else np.nan
    return P, int(len(fp))


def daily_is_fresh(hours=8):
    """True when the last daily run succeeded within `hours` (data/cache/last_run.txt, written by the workflow)."""
    try:
        outcome, stamp = (CACHE / "last_run.txt").read_text().split()[:2]
        done = dt.datetime.strptime(stamp, "%Y-%m-%dT%H:%MZ").replace(tzinfo=dt.timezone.utc)
    except (OSError, ValueError):
        return False
    return outcome == "success" and (dt.datetime.now(dt.timezone.utc) - done).total_seconds() < hours * 3600


DAILY_AT_MIN = 4 * 60 + 15      # Edmonton minutes after midnight: the ticker runs the daily once a day after this


def _last_run():
    """(outcome, UTC datetime) of the last daily run from data/cache/last_run.txt, or (None, None)."""
    try:
        outcome, stamp = (CACHE / "last_run.txt").read_text().split()[:2]
        return outcome, dt.datetime.strptime(stamp, "%Y-%m-%dT%H:%MZ").replace(tzinfo=dt.timezone.utc)
    except (OSError, ValueError):
        return None, None


def mark_run(outcome):
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / "last_run.txt").write_text(f"{outcome} {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%MZ')}\n")


def daily_due(now=None):
    """The daily is due once per Edmonton day after DAILY_AT_MIN: no successful run yet on today's local date."""
    now = now or dt.datetime.now(dt.timezone.utc)
    local = now.astimezone(EDMONTON)
    if local.hour * 60 + local.minute < DAILY_AT_MIN:
        return False
    outcome, when = _last_run()
    return not (outcome == "success" and when is not None and when.astimezone(EDMONTON).date() >= local.date())


LIVE_DONE = CACHE / "live_graded.json"     # ESPN events already settled live


def official_solo(H):
    """The history frame with solo_t set to the official solo count (nflverse solo + tackle with assist), the one the
    books and ESPN's live box scores settle on. The model itself trains on solo alone, the stable series."""
    if "solo_off" not in H.columns:
        return H
    Hg = H.copy()
    Hg["solo_t"] = Hg.solo_off.fillna(Hg.solo_t)
    return Hg


def lined_level_now(H, week):
    """The combined level for this week's lined players (config.LINED_LEVEL), 1.0 when it cannot be worked out."""
    try:
        Hg = official_solo(H)
        lv = EV.lined_level(EV.closing_frame(Hg[["season", "week", "team", "name_key", "comb", "solo_t"]], C.SEASON), week)
        print(f"daily: level for lined players this week: {lv}")
        return float(lv.get("combined", 1.0))
    except Exception as e:  # noqa: BLE001
        print(f"daily: lined-player level skipped ({type(e).__name__}: {e})")
        return 1.0


def scoreboard(Hg):
    """The engine against the market's fair closing price on every line the model had a number for (pipeline/evaluate.py)."""
    try:
        return EV.scoreboard(EV.closing_frame(Hg[["season", "week", "team", "name_key", "comb", "solo_t"]], C.SEASON))
    except Exception as e:  # noqa: BLE001    (a report must never stop the grading)
        print(f"scoreboard skipped ({type(e).__name__}: {e})")
        return {}


def _live_rows(week=None):
    """ESPN final box-score rows for this week's finished games (empty on synthetic data or failure)."""
    if os.environ.get("TACKLE_FAKE_DATA") or not G.PICKS.exists():
        return pd.DataFrame()
    try:
        week = week or int(json.load(open(CACHE / "model_state.json"))["week"])
        picks = pd.read_csv(G.PICKS)
        # this week and last: the first daily of a new week must still settle last week's Monday night game until the
        # official stats arrive (audit 2026-11-09)
        parts = [LG.finals(picks, C.SEASON, w)[0] for w in sorted({week - 1, week}) if w >= 1]
        parts = [p_ for p_ in parts if p_ is not None and len(p_)]
        return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    except Exception as e:  # noqa: BLE001
        print(f"live grade: ESPN finals not read ({type(e).__name__}: {e})")
        return pd.DataFrame()


def cmd_live_grade(force=False):
    """Settle the picks of every game that has ended, from ESPN's final box score, without waiting for the daily:
    regrade, rewrite results.json and the weekly log. Runs on a ticker beat only when a new game has finished."""
    if os.environ.get("TACKLE_FAKE_DATA") or not G.PICKS.exists() or not (CACHE / "model_state.json").exists():
        return
    week = int(json.load(open(CACHE / "model_state.json"))["week"])
    try:
        picks_now = pd.read_csv(G.PICKS)
        live, events = pd.DataFrame(), []
        for w in sorted({week - 1, week}):             # last week's Monday night game settles after the rollover too
            if w < 1:
                continue
            lv, ev = LG.finals(picks_now, C.SEASON, w)
            if lv is not None and len(lv):
                live = pd.concat([live, lv], ignore_index=True)
            events += list(ev)
    except Exception as e:  # noqa: BLE001
        print(f"live grade: ESPN not reached ({type(e).__name__}); next beat retries")
        return
    try:
        done = set(json.loads(LIVE_DONE.read_text()))
    except (OSError, ValueError):
        done = set()
    new = [e for e in events if e not in done]
    if not new and not force:
        return
    print(f"live grade: {len(new)} game(s) just ended; settling their picks from ESPN's final box score", flush=True)
    seasons = [C.SEASON]
    pw, _ = S.load_player_week(seasons)
    formula, _, _ = S.choose_tackle_formula(pw, json.loads(Path("data/known_checks.json").read_text()))
    pw = S.apply_tackle_formula(pw, formula)
    H = M.prepare(pw, S.load_schedule(seasons), S.load_snaps(seasons))      # zero-tackle games from snap counts, as the daily grades
    Hg = official_solo(H)
    graded, summary = G.grade(Hg[["season", "week", "team", "name_key", "player_id", "group", "comb", "solo_t"]], live=live)
    summary["live_graded"] = int((graded.get("graded_by") == "live").sum()) if len(graded) else 0
    parlays, psum = G.grade_parlays(Hg[["season", "week", "team", "name_key", "player_id", "group", "comb", "solo_t"]], live=live)   # H: zero-tackle games too, so a leg can settle
    summary["parlays"] = psum
    sleepers, summary["sleepers"] = G.grade_sleepers(Hg[["season", "week", "team", "name_key", "player_id", "group", "comb", "solo_t"]], live=live)
    summary["scoreboard"] = scoreboard(Hg)
    G.write_five_log(graded, summary, Path("data/weekly_five.md"), parlays)
    retro = Path("data/retro_five.json")
    _json(SITE / "results.json", dict(summary=summary, picks=records(graded), parlays=records(parlays) if parlays is not None and len(parlays) else [],
                                      sleepers=records(sleepers) if len(sleepers) else [], retro=json.loads(retro.read_text()) if retro.exists() else None))
    LIVE_DONE.write_text(json.dumps(sorted(done | set(events))))
    print(f"live grade: {summary['live_graded']} pick(s) settled live; {summary.get('pending', 0)} still pending", flush=True)


def cmd_tick():
    """One beat of the pipeline ticker (.github/workflows/ticker.yml): the daily once a day after 4:15 am Edmonton,
    then any pull slot that is due. GitHub starts scheduled jobs late and skips many; a ticker that runs for hours
    and beats every few minutes serves every slot a few minutes after its time whatever the scheduler does."""
    outcome, when = _last_run()
    recent_failure = outcome == "failure" and when is not None and (dt.datetime.now(dt.timezone.utc) - when).total_seconds() < 1800
    if daily_due() and not recent_failure:
        print("tick: the daily is due", flush=True)
        try:
            cmd_daily()
            mark_run("success")
        except Exception as e:  # noqa: BLE001
            # a failed daily (a feed outage, a data-shape error) must not take the pulls and the live grade down with it:
            # they run on the cached projections, and the daily is retried at most every 30 minutes (audit 2026-11-09)
            mark_run("failure")
            import traceback
            print(f"tick: the daily FAILED ({type(e).__name__}: {e}); pulls and live grading carry on with the cached projections")
            traceback.print_exc()
    elif daily_due():
        print("tick: the daily failed in the last 30 minutes; retrying later", flush=True)
    try:
        cmd_live_grade()           # a game just ended: settle its picks now, not at tomorrow's daily
    except Exception as e:  # noqa: BLE001
        print(f"tick: live grade skipped ({type(e).__name__}: {e})")
    if any(os.environ.get(k) for k in C.ODDS_KEY_ENV) or os.environ.get("TACKLE_FAKE_ODDS"):
        cmd_odds(auto=True)
    else:
        print("tick: no odds key in the environment; pulls skipped")


def cmd_keys():
    """Check every Odds API key without spending a credit (the events call is free): set or not, accepted or rejected,
    credits left. Prints names and counts only, never a key."""
    keys = {name: os.environ.get(name, "") for name in C.ODDS_KEY_ENV}
    left = O.credits_left({n: k for n, k in keys.items() if k})
    for name in C.ODDS_KEY_ENV:
        if not keys[name]:
            print(f"keys: {name}: not set (no secret of this name reaches the job)")
        elif left.get(name) is None:
            print(f"keys: {name}: set, but the Odds API could not be reached or gave no count")
        elif left[name] == 0.0:
            print(f"keys: {name}: REJECTED by the Odds API, or out of credits")
        else:
            print(f"keys: {name}: works, {left[name]:.0f} credits left")
    known = [v for v in left.values() if v]
    print(f"keys: {len(known)} working key(s), {sum(known):.0f} credits in all")


def cmd_sleep(now=None):
    """Seconds the ticker should sleep: until the next pull slot or the next daily, between 60 and 900."""
    now = now or dt.datetime.now(dt.timezone.utc)
    games = json.load(open(CACHE / "games.json")) if (CACHE / "games.json").exists() else []
    if auto_plan(now=now, games=games, served=load_served()) is not None or daily_due(now):
        return 120            # something is due and was not done (a failed beat): try again in two minutes
    due = []
    nxt = next_pull(now=now, games=games)
    if nxt:
        due.append(dt.datetime.fromisoformat(nxt))
    local = now.astimezone(EDMONTON)
    d = local.date() if local.hour * 60 + local.minute < DAILY_AT_MIN else local.date() + dt.timedelta(days=1)
    due.append(dt.datetime.combine(d, dt.time(DAILY_AT_MIN // 60, DAILY_AT_MIN % 60), tzinfo=EDMONTON).astimezone(dt.timezone.utc))
    secs = min((t - now).total_seconds() for t in due)
    return int(max(60, min(900, secs + 15)))


def cmd_daily(auto=False):
    if auto and daily_is_fresh():
        print("daily: a run already succeeded in the last 8 hours; nothing to do (fallback schedule)")
        return
    seasons, pw, sched, snaps, inj, H, status, src = load_all()
    week = upcoming_week(sched, C.SEASON)
    bt, phi, k, scale, gbm = B.run_backtest(H, seasons)
    Hg = official_solo(H)                       # grading, the blend and My board settle on the official solo count
    cur = H[H.season == C.SEASON]
    if "with_ast" in cur.columns and cur.solo.sum() > 0:
        phi["__solo_official__"] = float(1 + cur.with_ast.sum() / cur.solo.sum())     # this season's rate of tackles made with an assist
        status["solo_official_factor"] = phi["__solo_official__"]
    games = week_games(sched, C.SEASON, week)
    status["protocol_flags"] = bt.get("flags", [])       # a factor that fails its daily test, or one that is out and passes: a prompt to run the full test
    if status["protocol_flags"]:
        print("daily: PROTOCOL FLAGS: " + "; ".join(status["protocol_flags"]))
    try:                                                 # every kickoff left this season, for the odds-credit budget
        left = [g_["kickoff"] for w_ in sorted(set(sched[sched.season == C.SEASON].week)) if w_ >= week for g_ in week_games(sched, C.SEASON, int(w_))]
        CACHE.mkdir(parents=True, exist_ok=True)
        KICKOFFS.write_text(json.dumps(sorted(left)))
    except Exception as e:  # noqa: BLE001
        print(f"daily: kickoff list not written ({type(e).__name__}: {e})")
    status["season_over"] = not games           # every game of the season (playoffs included) is in the books: grade, keep the record, project nothing
    if games:
        F = M.upcoming_rows(H, sched, inj, C.SEASON, week, vol=src["vol"], dc=src["dc"], pbp_starters=src["pbp"]["starters"],
                            roster=S.roster_teams(C.SEASON, week))      # trades: the weekly roster moves a player before the depth chart does
        P = M.finalize_projections(F, phi, scale=scale, gbm=gbm)
        P = attach_game_logs(P, H, C.SEASON, week)
        P, status["fantasypros_rows"] = attach_consensus(P, C.SEASON, week)
        P["lined_level"] = lined_level_now(H, week)       # the level for players who get lines, from the season's earlier lined games
    else:
        print(f"daily: no game left on the {C.SEASON} schedule (week {week}); the season is over, so the record is graded and nothing is projected")
        P, status["fantasypros_rows"] = pd.DataFrame(), 0
    jerseys = S.load_jerseys(C.SEASON) if len(P) else {}
    espn_ids = S.load_espn_ids() if len(P) else {}
    P["jersey"] = P.player_id.astype(str).map(jerseys) if len(P) else None
    P["espn_id"] = P.player_id.astype(str).map(espn_ids) if len(P) else None
    CACHE.mkdir(parents=True, exist_ok=True)
    if len(P):
        P.to_csv(CACHE / "projections.csv", index=False)
    json.dump(dict(phi=phi, k=k, scale=scale, week=week), open(CACHE / "model_state.json", "w"))
    json.dump(games, open(CACHE / "games.json", "w"), indent=1)
    status["international_games"] = [f"{g['away']} at {g['home']}, {g['edmonton']} Edmonton" for g in games if g["international"]]
    live = _live_rows()
    graded, summary = G.grade(Hg[["season", "week", "team", "name_key", "player_id", "group", "comb", "solo_t"]], live=live)
    summary["live_graded"] = int((graded.get("graded_by") == "live").sum()) if len(graded) else 0
    summary["scoreboard"] = sb = scoreboard(Hg)          # the engine against the market's fair close, on the official count
    if sb:
        print(f"daily: against the market on {sb['lines']} closing lines: log-loss market {sb['log_loss']['market']:.4f}, model {sb['log_loss']['model']:.4f}, engine {sb['log_loss']['engine']:.4f}"
              + (f" (engine better by {sb['engine_minus_market']:+.4f}, t {sb['t']:+.1f} over {len(sb['weeks'])} weeks)" if sb.get("t") is not None else ""))
    # the official box score for every defender-game this season, so the owner's own board can grade any bet (not only the model's picks)
    hs = Hg[(Hg.season == C.SEASON) & Hg.comb.notna()]
    actuals = {}
    for r in hs.itertuples():
        actuals.setdefault(str(int(r.week)), {})[f"{r.team}|{r.name_key}"] = [int(r.comb), int(r.solo_t), int(r.comb - r.solo_t)]   # combined, solo, assists
        actuals[str(int(r.week))][f"id:{r.player_id}"] = actuals[str(int(r.week))][f"{r.team}|{r.name_key}"]                    # the same row by league id, for bets that carry one
    _json(SITE / "actuals.json", dict(season=C.SEASON, weeks=actuals))   # H has zero-tackle games from snap counts, so "played, no tackles" is not "did not play"
    parlays, psum = G.grade_parlays(Hg[["season", "week", "team", "name_key", "player_id", "group", "comb", "solo_t"]], live=live)   # H: zero-tackle games too, so a leg can settle
    summary["parlays"] = psum
    G.write_five_log(graded, summary, Path("data/weekly_five.md"), parlays)
    lines = O.upcoming_only(O.latest_lines(C.SEASON, week))
    bets = G.size_stakes(M.price_lines(lines, P)) if len(lines) else pd.DataFrame()
    if len(bets):
        _stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        LL.log_model_numbers(bets, C.SEASON, week, _stamp)
        # the morning re-price is what the board shows until the next pull: log new picks and refresh open ones with
        # it, so a grade seen on the site is the grade the record keeps (2026-11-05: an A shown all morning was never logged)
        G.log_picks(bets, C.SEASON, week, _stamp)
        G.log_sleepers(bets, C.SEASON, week, _stamp)
    sleepers, summary["sleepers"] = G.grade_sleepers(Hg[["season", "week", "team", "name_key", "player_id", "group", "comb", "solo_t"]], live=live)
    bets = mark_five(bets, C.SEASON, week)
    write_site(P, bets, bt, graded, summary, week, status, lines_pulled=None if lines.empty else str(lines.pulled_at.max()), parlays=parlays, sleepers=sleepers)
    write_week_lines(P, C.SEASON, week)
    write_parlays(C.SEASON, week)
    print(f"daily: week {week}, {len(P)} projections, {len(bets)} priced lines, backtest on {bt.get('games', 0)} games")


def refresh_injury_status(P, week):
    """The projections are built each morning; a pull hours later must price with the report as it stands now.
    A player ruled out since the morning becomes a pass, a new questionable listing drops out of the locks."""
    try:
        inj = S.load_injuries([C.SEASON])
    except Exception as e:  # noqa: BLE001
        print(f"odds: injury refresh skipped ({e})")
        return P
    inj = inj[(inj.season == C.SEASON) & (inj.week == week)] if len(inj) else inj
    if inj.empty:
        # the league report did not load (every source failed): keep the morning's statuses rather than clear them all
        print("odds: injury refresh skipped (the league report came back empty); the morning's statuses stand")
        return P
    espn, roster = S.load_espn_injuries(C.SEASON, week), S.load_roster_out(C.SEASON, week)
    inj = S.merge_injury_sources(S.merge_injury_sources(inj, espn), roster)
    if inj.empty or "name_key" not in P.columns:
        return P
    status = {(r.team, r.name_key): str(r.status) for r in inj.itertuples()}
    practice = {(r.team, r.name_key): str(getattr(r, "practice", "")) for r in inj.itertuples()}
    before = P.status.fillna("").astype(str) if "status" in P.columns else pd.Series("", index=P.index)
    P = P.copy()
    reserve = {"injured reserve", "ir", "pup", "suspended"}
    outside_failed = len(espn) == 0 or len(roster) == 0
    P["status"] = [status.get((t, n), "") or (old if outside_failed and str(old).lower() in reserve else "")      # a reserve-list status only
                   for t, n, old in zip(P.team, P.name_key, before)]                                                  # the outside feeds carry survives their failure
    P["practice"] = [practice.get((t, n), "") for t, n in zip(P.team, P.name_key)]
    changed = int((before.str.lower() != P.status.fillna("").astype(str).str.lower()).sum())
    print(f"odds: injury report refreshed for week {week}: {len(inj)} listings, {changed} projection statuses changed since the morning run")
    return P


ROLE_NEWS = CACHE / "role_news.json"


def role_news(before, after, now=None, min_share=0.3):
    """Players whose availability changed since the projections were built: ruled out (or doubtful, or to a reserve list)
    since, or cleared since, expected to play at least `min_share` of the snaps, on a team that has not kicked off.
    [(team, player, old status, new status)]. A change like this moves his teammates' snaps, which a status refresh
    alone does not: the projections have to be rebuilt."""
    if before is None or after is None or len(before) == 0 or "status" not in after.columns:
        return []
    now = now or dt.datetime.now(dt.timezone.utc)
    try:
        games = json.load(open(CACHE / "games.json"))
        started = {t for g in games for t in (g["home"], g["away"]) if dt.datetime.fromisoformat(g["kickoff"]) <= now}
    except (OSError, ValueError, KeyError):
        started = set()
    out_ = lambda v: str(v).strip().lower() in M.OUT_STATUSES
    old = before.status.fillna("").astype(str) if "status" in before.columns else pd.Series("", index=before.index)
    share = pd.to_numeric(after.get("share_pred"), errors="coerce").fillna(0.0) if "share_pred" in after.columns else pd.Series(1.0, index=after.index)
    news = []
    for i in after.index:
        o, n = old.get(i, ""), str(after.at[i, "status"] if pd.notna(after.at[i, "status"]) else "")
        if out_(o) != out_(n) and share.get(i, 0.0) >= min_share and after.at[i, "team"] not in started:
            news.append((str(after.at[i, "team"]), str(after.at[i, "player"]), o, n))
    return news


def reproject_on_news(P0, P, week):
    """Rebuild the projections before a pull prices anything when a player who was expected to play is now out (or the
    reverse): the next man up and the shares of everyone at his position change with it. Each piece of news triggers one
    rebuild (data/cache/role_news.json); a rebuild that fails leaves the morning's projections in place."""
    news = role_news(P0, P)
    try:
        seen = set(map(tuple, json.loads(ROLE_NEWS.read_text()).get(str(week), [])))
    except (OSError, ValueError, AttributeError):
        seen = set()
    fresh = [n for n in news if (n[0], n[1], n[3]) not in seen]
    if not fresh:
        return P
    print("odds: availability changed since the projections were built: " + "; ".join(f"{pl} ({t}) {o or 'active'} -> {n or 'active'}" for t, pl, o, n in fresh)
          + ". Rebuilding the projections before pricing.", flush=True)
    try:
        ROLE_NEWS.write_text(json.dumps({str(week): sorted(seen | {(n[0], n[1], n[3]) for n in fresh})}))
        cmd_daily()
        return refresh_injury_status(pd.read_csv(CACHE / "projections.csv"), week)
    except Exception as e:  # noqa: BLE001
        print(f"odds: the rebuild failed ({type(e).__name__}: {e}); pricing with the morning's projections and the refreshed statuses")
        return P


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
    # the credit budget: the richest schedule the credits left this month can pay for decides what this pull asks for
    left = O.credits_left(keys)
    known = [c for c in left.values() if isinstance(c, (int, float))]
    budget = credit_budget(credits=sum(known) if known and all(c is not None for c in left.values()) else None, served=load_served(), current=plan.get("key") if auto else None)
    rule = govern(plan.get("key") if auto else None, budget)
    if not auto:
        rule.update(run=True, cluster=False)            # a pull by hand always runs, whole window; only the markets follow the budget
    if budget.get("known"):
        print(f"odds: credit budget level {budget['level']} ({budget['label']}): {budget['spare']:.0f} credits to spend before {budget['reset'][:10]}, "
              f"the full schedule would cost {budget['costs'].get('3')}, the barest {budget['costs'].get('-1')}" + (f"; SHORT by {budget['short']}" if budget["short"] else ""))
    if auto and not rule["run"]:
        pulled_key, skipped_keys = plan.pop("key"), plan.pop("also_served", [])
        mark_served([pulled_key] + skipped_keys)
        log_pull(pulled_key, skipped=skipped_keys, saved=True)
        print(f"odds: {pulled_key} {rule['why']}")
        _budget_to_meta(budget)
        return
    P = reproject_on_news(P, refresh_injury_status(P, week), week)   # only when a pull is happening: the report as it stands now, and new projections if it moved a role
    if auto:
        pulled_key, skipped_keys = plan.pop("key"), plan.pop("also_served", [])
        mark_served([pulled_key] + skipped_keys)
        if "teams" in plan:
            home, away = plan.pop("teams")
            names = {M.TEAM_NAMES.get(home), M.TEAM_NAMES.get(away)}
            ev = O.list_events(next(iter(keys.values())))
            plan["event_ids"] = [e["id"] for e in ev if e.get("home_team") in names or e.get("away_team") in names]
        pull_kw = plan
        if rule["cluster"] and "days" in pull_kw:       # a tight budget: only the games about to kick off, not the whole day again
            pull_kw = dict(hours_ahead=(PRE_KICK_MIN + PRE_KICK_CLUSTER_MIN + 10) / 60)
    rows, credits = O.pull(keys, markets=rule["markets"], **pull_kw)
    numeric = [c for c in credits.values() if isinstance(c, (int, float))]
    remaining = int(sum(numeric)) if numeric else next(iter(credits.values()), None)
    O.save_snapshot(rows, C.SEASON, week)
    if auto:
        log_pull(pulled_key, skipped=skipped_keys, games=len({r.get("event_id") for r in rows}) if rows else 0)
    lines = O.upcoming_only(O.latest_lines(C.SEASON, week))
    bets = G.size_stakes(M.price_lines(lines, P))
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    LL.log_model_numbers(bets, C.SEASON, week, stamp)
    n_new = G.log_picks(bets, C.SEASON, week, stamp)
    G.log_sleepers(bets, C.SEASON, week, stamp)
    G.build_parlays(bets, C.SEASON, week, stamp)
    bets = mark_five(bets, C.SEASON, week)
    write_parlays(C.SEASON, week)
    meta_path = SITE / "meta.json"
    meta = SEAL.read_json(meta_path) or {}          # the previous meta may be sealed (SITE_PASSWORD) or plain
    games = json.load(open(CACHE / "games.json")) if (CACHE / "games.json").exists() else []
    after = credit_budget(credits=remaining if isinstance(remaining, (int, float)) else None, served=load_served())
    meta.update(odds_credits_remaining=remaining, odds_credits_by_key=credits, lines_pulled=stamp, lines_count=int(len(lines)), next_pull=next_pull(games=games),
                pull_schedule=pull_schedule(games=games), odds_budget=_budget_public(after), odds_markets=rule["markets"])
    _json(meta_path, meta)
    _json(SITE / "bets.json", records(bets))
    write_week_lines(P, C.SEASON, week)
    print(f"odds: {len(rows)} prices pulled, {len(lines)} current lines, {n_new} new picks logged, credits left {remaining}")


def _budget_public(budget):
    """The budget as the site shows it (no pull list)."""
    return {k: v for k, v in budget.items() if k != "pulls"} | dict(pulls_left=len(budget.get("pulls", [])))


def _budget_to_meta(budget):
    """Refresh the budget and the pull schedule on the site after a look was left out to save credits."""
    meta_path = SITE / "meta.json"
    meta = SEAL.read_json(meta_path) or {}
    games = json.load(open(CACHE / "games.json")) if (CACHE / "games.json").exists() else []
    meta.update(odds_budget=_budget_public(budget), next_pull=next_pull(games=games), pull_schedule=pull_schedule(games=games))
    _json(meta_path, meta)


def cmd_history(weeks, markets):
    """Fetch a finished week's lines for extra markets from the historical endpoint (10 credits a game per market)
    and store them as snapshots, so the replay can price and grade them as if they had been pulled live."""
    key = os.environ.get("ODDS_API_KEY")
    if not key:
        sys.exit("ODDS_API_KEY is not set")
    if not weeks:
        sys.exit("history: give --weeks, e.g. --weeks 7,8")
    for wk in weeks:
        print(f"history: season {C.SEASON} week {wk}, markets {markets}")
        rows, left = O.pull_historical(key, C.SEASON, wk, markets)
        path = O.save_snapshot(rows, C.SEASON, wk)
        print(f"history: week {wk}: {len(rows)} prices saved to {path}, credits left {left}")


WEEK_LINE_COLS = ["player", "player_id", "espn_id", "jersey", "team", "opp", "group", "market", "line", "book", "over_odds", "under_odds", "over_link", "under_link", "side", "pick", "tier", "status", "proj", "proj_model", "model_over", "market_over", "p_claim", "p_low", "p_model", "ev", "edge_low", "grade", "lock", "commence_time", "event_id", "rundown"]


def write_week_lines(P, season, week):
    """Every line pulled this week at its last price, started games included, priced the same way as the board:
    the My board tab lets a bet be added from here after its game has kicked off or the book has pulled the line."""
    lines = O.all_lines(season, week)        # every line seen this week (a line since moved or pulled can still be on a bettor's slip)
    if lines is None or len(lines) == 0 or P is None or len(P) == 0:
        _json(SITE / "lines_week.json", [])
        return
    bets = G.size_stakes(M.price_lines(lines, P))
    _json(SITE / "lines_week.json", records(bets[[c for c in WEEK_LINE_COLS if c in bets.columns]]) if len(bets) else [])


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
            sg = getattr(first, "same_game", np.nan)
            out.append(dict(parlay_id=pid, slate=first.slate, n_legs=int(len(legs)), combined_decimal=float(first.combined_decimal),
                            same_game=bool(sg) if pd.notna(sg) else bool(legs.event_id.astype(str).duplicated().any()),
                            product_decimal=None if pd.isna(getattr(first, "product_decimal", np.nan)) else float(first.product_decimal),
                            combined_american=G.american(float(first.combined_decimal)), combined_prob=float(first.combined_prob), corr_ratio=None if pd.isna(getattr(first, "corr_ratio", np.nan)) else float(first.corr_ratio),
                            units=float(first.units), chosen_at=first.chosen_at, placed=bool((start <= now).any()),
                            finished=bool(start.notna().all() and (start + dt.timedelta(hours=4, minutes=30) <= now).all()),   # every leg's game is over: it belongs to the Track record tab, not the board
                            first_kickoff=None if start.isna().all() else start.min().isoformat(),
                            legs=records(legs[[c for c in ["leg", "player", "jersey", "team", "opp", "market", "side", "line", "book", "odds", "link", "sid", "p_side", "mkt_side", "lock", "grade", "commence_time"] if c in legs.columns]])))
    _json(SITE / "parlays.json", out)


def write_site(P, bets, bt, graded, summary, week, status, lines_pulled, parlays=None, sleepers=None):
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
    games = json.load(open(CACHE / "games.json")) if (CACHE / "games.json").exists() else []
    meta = dict(generated_at=now, season=C.SEASON, week=week, lines_pulled=lines_pulled, next_pull=next_pull(games=games), pull_schedule=pull_schedule(games=games), **status,
                grading=dict(engine=C.ENGINE, bars=C.GRADE_BARS, units=C.GRADE_UNITS, locks=C.LOCKS_PER_SLATE, lock_min=C.LOCK_MIN_SCORE, clv=C.CLV_BARS, clv_pct=C.CLV_PCT_BARS,
                             stake=C.STAKE, frozen_until=C.FROZEN_UNTIL, corrector_weight=C.GBM["weight"], factors=C.FACTORS,
                             parlay=dict(min_model=C.PARLAY_MIN_PROB, fallback=C.PARLAY_FALLBACK_PROB, legs=list(C.PARLAY_LEGS))))
    prev = SEAL.read_json(SITE / "meta.json")
    if prev:
        meta.setdefault("odds_credits_remaining", prev.get("odds_credits_remaining"))
        meta.setdefault("odds_credits_by_key", prev.get("odds_credits_by_key"))
        meta.setdefault("odds_markets", prev.get("odds_markets"))
    left = prev.get("odds_credits_remaining") if prev else None      # the budget as of the last pull's credits, re-read against today's schedule
    meta["odds_budget"] = _budget_public(credit_budget(credits=left if isinstance(left, (int, float)) else None, served=load_served()))
    _json(SITE / "meta.json", meta)
    cols = ["player", "team", "opp_team", "group", "status", "n_prev", "season_avg", "last", "base", "proj", "proj_solo",
            "fair_line", "fair_line_solo", "crew_comb", "crew_solo", "spread_dog", "role_signal", "venue", "gameday", "gametime", "phi", "phi_solo",
            "dc_status", "opp_qb_out", "opp_rb_out", "rest", "pct_last3", "pct_prev", "pct_last", "gap_weeks", "team_changed", "new_role", "reduced_role",
            "absence", "missed_game", "new_team", "snap_jump", "vacancy", "vacancy_rule", "share_pred", "rate_clean", "tsnaps_exp", "allowed_rel", "roof", "solo_drift", "proj_factor", "proj_gbm",
            "player_id", "log_comb", "log_solo", "log_ast", "proj_ast", "phi_ast", "fair_line_ast", "press_pg", "fp_comb", "fp_solo", "fp_rel_comb", "fp_rel_solo", "jersey", "espn_id"]
    _json(SITE / "projections.json", records(P, [c for c in cols if c in P.columns]) if len(P) else [])
    _json(SITE / "bets.json", records(bets))
    _json(SITE / "backtest.json", bt)
    try:
        _json(SITE / "patchlog.json", PATCH.build("MODEL_LOG.md"))     # every calibration, evaluation and change, from the log
    except Exception as e:  # noqa: BLE001
        print(f"patch log skipped ({type(e).__name__}: {e})")
    retro = Path("data/retro_five.json")
    retro_ast = Path("data/retro_assists.json")
    if retro_ast.exists():
        meta["retro_assists"] = json.loads(retro_ast.read_text())
    _json(SITE / "results.json", dict(summary=summary, picks=records(graded), parlays=records(parlays) if parlays is not None and len(parlays) else [],
                                      sleepers=records(sleepers) if sleepers is not None and len(sleepers) else [],
                                      retro=json.loads(retro.read_text()) if retro.exists() else None))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["daily", "odds", "seal", "history", "tick", "sleep", "watch", "live-grade", "keys"])
    ap.add_argument("--test", action="store_true", help="watch: raise one test alert")
    ap.add_argument("--hours", type=float, default=None)
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--weeks", default="", help="history: comma-separated finished weeks to fetch, e.g. 7,8")
    ap.add_argument("--markets", default=C.ASSIST_MARKET, help="history: comma-separated market keys")
    a = ap.parse_args()
    if a.cmd == "seal":
        SEAL.cmd_seal(SITE)
    else:
        if a.cmd == "history":
            cmd_history([int(w) for w in a.weeks.split(",") if w.strip()], [m for m in a.markets.split(",") if m.strip()])
        elif a.cmd == "keys":
            cmd_keys()
        elif a.cmd == "tick":
            cmd_tick()
        elif a.cmd == "live-grade":
            cmd_live_grade(force=True)
        elif a.cmd == "watch":
            from pipeline import watch as W
            W.run(test=a.test)
        elif a.cmd == "sleep":
            print(cmd_sleep())
        else:
            cmd_daily(a.auto) if a.cmd == "daily" else cmd_odds(a.hours, a.auto)
