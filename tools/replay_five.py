"""Replay a finished week under the CURRENT projection, engine and lock rules, using only what was known at each line pull.

The week's projections are rebuilt with today's code from games finished before the week (the corrector, the spread
and the level are refitted on those games only). Then every odds snapshot of the week is fed, in time order, through
the same functions the live job runs, with the clock set to the snapshot's time: the board is each game's latest
pull, picks are logged and refreshed, locks and the parlay re-chosen, sleepers logged. Everything is then graded by
the live grader against the official box scores (one bet per player, market and side; late and phantom rows void).
The result goes to data/retro_five.json and is shown on the site as the record "had the current rules been running".

Known look-ahead (small, stated): the week's injury report is the final one, and the history features of the frame
were built once with every game loaded (each row still only sees games before it).

  python tools/replay_five.py --week 7
  python tools/replay_five.py --week 9 --markets player_assists --out data/retro_assists.json --all-picks
"""
import argparse
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C                      # noqa: E402
import run as R                         # noqa: E402
from pipeline import backtest as B      # noqa: E402
from pipeline import grade as G         # noqa: E402
from pipeline import linelog as LL      # noqa: E402
from pipeline import model as M         # noqa: E402
from pipeline import odds as O          # noqa: E402
from pipeline import sources as S       # noqa: E402

OUT = Path("data/retro_five.json")
STAT_COLS = ["season", "week", "team", "name_key", "player_id", "group", "comb", "solo_t"]


def board_as_of(snaps, t):
    """The board at time t: each game's latest pull at or before t (as odds.latest_lines reads it), games not yet started."""
    s = snaps[snaps.pulled_at <= t]
    if s.empty:
        return s
    s = s[s.pulled_at == s.groupby("event_id").pulled_at.transform("max")]
    s = s.drop_duplicates(["event_id", "book", "market", "player", "line"], keep="last")
    now = pd.Timestamp(dt.datetime.strptime(t, "%Y%m%dT%H%M%SZ"), tz="UTC")
    start = pd.to_datetime(s.commence_time, utc=True, errors="coerce")
    return s[start.isna() | (start > now)]


def projections_as_of(season, week, loaded=None):
    """This week's projections from today's code and the games finished before the week. Returns (P, H, pw)."""
    seasons, pw, sched, snaps_df, inj, H, status, src = loaded or R.load_all()
    prior = H[(H.season < season) | ((H.season == season) & (H.week < week))]
    _, phi, _, scale, gbm = B.run_backtest(prior, seasons)
    cur = prior[prior.season == season]
    if "with_ast" in cur.columns and cur.solo.sum() > 0:
        phi["__solo_official__"] = float(1 + cur.with_ast.sum() / cur.solo.sum())
    try:
        roster = S.roster_teams(season, week)
    except Exception:  # noqa: BLE001
        roster = None
    F = M.upcoming_rows(H, sched, inj, season, week, vol=src["vol"], dc=src["dc"], pbp_starters=src["pbp"]["starters"], roster=roster)
    P = R.attach_game_logs(M.finalize_projections(F, phi, scale=scale, gbm=gbm), H, season, week)
    P["lined_level"] = R.lined_level_now(H, week)       # from the live line log's earlier weeks only
    for c in ("jersey", "espn_id", "fp_comb", "fp_solo", "fp_rel_comb", "fp_rel_solo"):
        if c not in P.columns:
            P[c] = np.nan
    return P, H, pw


def replay(season, week, markets=None, out=OUT, keep_all=False, loaded=None, P=None, write=True):
    """markets: restrict the replay to these market keys (e.g. the assists market); out: where the entry is written;
    keep_all: list every pick in the entry, not just the locks. Returns (entry, graded picks, sleepers)."""
    if P is None:
        P, H, pw = projections_as_of(season, week, loaded)
    else:
        H = (loaded or R.load_all())[5]
    snaps = O.load_snapshots(season, week)
    if snaps.empty:
        sys.exit(f"No odds snapshots for {season} week {week}")
    snaps["pulled_at"] = snaps.pulled_at.astype(str)
    if markets:
        snaps = snaps[snaps.market.isin(set(markets))]
        if snaps.empty:
            sys.exit(f"No {markets} snapshots for {season} week {week}")
    # the live job's own functions, writing to a scratch folder, with the clock set to each pull
    tmp = Path(tempfile.mkdtemp())
    saved = (G.PICKS, G.PARLAYS, G.SLEEPERS, G.SETTLED, G.SEGMENTS, LL.LOG, O._utcnow)
    G.PICKS, G.PARLAYS, G.SLEEPERS, G.SETTLED, G.SEGMENTS, LL.LOG = tmp / "picks.csv", tmp / "parlays.csv", tmp / "sleepers.csv", tmp / "settled.csv", tmp / "segments.json", tmp / "lines_log.csv"
    try:
        for t in sorted(snaps.pulled_at.unique()):
            now = dt.datetime.strptime(t, "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc)
            O._utcnow = lambda now=now: now
            lines = board_as_of(snaps, t)
            if lines.empty:
                continue
            bets = G.size_stakes(M.price_lines(lines, P))
            if bets.empty or "pick" not in bets:
                continue
            LL.log_model_numbers(bets, season, week, t)
            G.log_picks(bets, season, week, t)
            G.log_sleepers(bets, season, week, t)
            G.build_parlays(bets, season, week, t, now=now)
            pk = pd.read_csv(G.PICKS) if G.PICKS.exists() else pd.DataFrame()
            locks = pk[pk.five.fillna(False).astype(bool)] if len(pk) and "five" in pk.columns else pk.iloc[0:0]
            print(f"{t}: {len(lines)} lines on the board, {int(bets.pick.isin(['Over', 'Under']).sum())} picks, {int((bets.tier == 'lean').sum())} leans; {len(pk)} rows logged; locks = "
                  + ", ".join(f"{r.player} {r.side} {r.line:g}" for r in locks.itertuples()))
        O._utcnow = saved[6]
        Hg = R.official_solo(H)
        stats = Hg[(Hg.season == season) & (Hg.week == week)][STAT_COLS]
        graded, summary = G.grade(stats)
        parlays, _ = G.grade_parlays(stats)
        sleepers, ssum = G.grade_sleepers(stats)
        lines_log = pd.read_csv(LL.LOG) if LL.LOG.exists() else pd.DataFrame()
    finally:
        G.PICKS, G.PARLAYS, G.SLEEPERS, G.SETTLED, G.SEGMENTS, LL.LOG, O._utcnow = saved
    if graded is None or len(graded) == 0:
        print(f"week {week}: the current rules make no pick on any pull")
        graded = pd.DataFrame(columns=["five", "counted", "result", "units", "grade", "lock", "stake"])
    counted = graded[graded.counted.fillna(False).astype(bool)] if "counted" in graded.columns else graded

    def rec(d):
        g = d[d.result.isin(["Win", "Loss", "Push"])]
        w, l = int((g.result == "Win").sum()), int((g.result == "Loss").sum())
        st = pd.to_numeric(g.get("stake"), errors="coerce").fillna(0.0) if "stake" in g.columns else pd.Series(0.0, index=g.index)
        lo, hi = G.hit_interval(w, l, 1)
        return dict(n=int(len(d)), wins=w, losses=l, pushes=int((g.result == "Push").sum()), pending=int((d.result == "Pending").sum()),
                    units=float(g.units.sum()), staked=float(st.sum()), units_at_stake=float((g.units * st).sum()),
                    hit=float(w / max(1, w + l)) if len(g) else None, hit_lo=lo, hit_hi=hi)
    five = counted[counted.five.fillna(False).astype(bool)] if "five" in counted.columns else counted.iloc[0:0]
    entry = dict(season=season, week=week, replayed_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
                 rules=dict(engine=C.ENGINE, stake=C.STAKE, corrector_weight=C.GBM["weight"], factors=C.FACTORS, lock_min=C.LOCK_MIN_SCORE),
                 five=rec(five), plays=rec(counted), by_grade=G.record_by_grade(counted), sleepers=ssum.get("all") if ssum else None,
                 sleepers_by_grade=ssum.get("by_grade") if ssum else None,
                 parlays=[] if parlays is None or len(parlays) == 0 else json.loads(parlays.to_json(orient="records")),
                 picks=[dict(player=r.player, team=r.team, opp=r.opp, market=r.market, side=r.side, line=float(r.line), odds=float(r.odds),
                             book=r.book, lock=float(r.lock), grade=r.grade, proj=float(r.proj), actual=None if pd.isna(r.actual) else float(r.actual),
                             result=r.result, units=float(r.units), commence_time=r.commence_time) for r in five.sort_values("lock", ascending=False).itertuples()])
    if keep_all:
        entry["all_picks"] = [dict(player=r.player, team=r.team, opp=r.opp, group=getattr(r, "group", None), market=r.market, side=r.side, line=float(r.line), odds=float(r.odds),
                                   book=r.book, lock=float(r.lock), grade=r.grade, proj=float(r.proj), model_over=float(r.model_over), market_over=float(r.market_over),
                                   p_claim=None if pd.isna(getattr(r, "p_claim", np.nan)) else float(r.p_claim), lock_eligible=bool(getattr(r, "lock_eligible", True)),
                                   actual=None if pd.isna(r.actual) else float(r.actual), result=r.result, units=float(r.units), commence_time=r.commence_time)
                             for r in counted.sort_values("lock", ascending=False).itertuples()]
    if write:
        OUT_PATH = Path(out)
        data = json.loads(OUT_PATH.read_text()) if OUT_PATH.exists() else dict(weeks=[])
        data["weeks"] = [w for w in data["weeks"] if not (w["season"] == season and w["week"] == week)] + [entry]
        data["weeks"].sort(key=lambda w: (w["season"], w["week"]))
        data["note"] = ("Replayed under the current rules using only what was known at each line pull. Weeks 7 on have every pull of the week; "
                        "weeks 4 to 6 have one, the lines an hour before kickoff, fetched from the feed's history on 2026-11-10. Weeks 1 to 3 "
                        "have no pick: a player needs three games of the season first.")
        OUT_PATH.write_text(json.dumps(data, indent=1))
    f, p = entry["five"], entry["plays"]
    print(f"\nweek {week} replay: locks {f['wins']}-{f['losses']} ({f['pending']} pending, {f['units']:+.2f}u); "
          f"all plays {p['wins']}-{p['losses']} of {p['n']} ({p['units']:+.2f}u at 1 a bet; {p['units_at_stake']:+.2f}u on {p['staked']:.1f}u staked)")
    print("  by grade: " + ", ".join(f"{g['grade']} {g['wins']}-{g['losses']} ({g['units']:+.1f}u)" for g in entry["by_grade"]))
    for r in five.sort_values("lock", ascending=False).itertuples():
        print(f"  {r.grade} {r.lock:4.0f}  {r.player:22}{r.side:6}{r.line:>4} {r.market[7:]:17}{int(r.odds):>5} {r.book:13} actual {r.actual!s:>5} {r.result}")
    for q in entry["parlays"]:
        print(f"  parlay {q['slate']}: {q['n_legs']} legs {q['combined_american']:+d}, chance {q['combined_prob']:.0%}, stake {q['units']:.1f}u -> {q['result']} ({q['units_won']:+.2f}u)")
    return entry, graded, sleepers, lines_log


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=C.SEASON)
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--markets", default="", help="comma-separated market keys to replay (default: every market in the snapshots)")
    ap.add_argument("--out", default=str(OUT), help="where to write the entry (default data/retro_five.json)")
    ap.add_argument("--all-picks", action="store_true", help="list every pick in the entry, not just the locks")
    a = ap.parse_args()
    replay(a.season, a.week, markets=[m for m in a.markets.split(",") if m.strip()] or None, out=a.out, keep_all=a.all_picks)
