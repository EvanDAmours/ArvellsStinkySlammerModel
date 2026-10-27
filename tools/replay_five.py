"""Replay a finished week under the CURRENT pricing and lock rules, using only what was known at each line pull.

For every odds snapshot of the week, in time order: price the lines then on the board (games not yet kicked off),
log the picks the way the live job does (first price kept), and re-choose the weekly five among open games.
Then grade everything against the official box scores. The result goes to data/retro_five.json and is shown on
the site under the locks record as the projected record "had the current rules been running".

Known look-ahead (small, stated): the week's injury report is the final one, and the dispersion estimate (phi)
comes from a backtest that includes the replayed week.

  python tools/replay_five.py --week 7
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C                      # noqa: E402
import run as R                         # noqa: E402
from pipeline import grade as G         # noqa: E402
from pipeline import model as M         # noqa: E402
from pipeline import odds as O          # noqa: E402
from pipeline import sources as S       # noqa: E402

OUT = Path("data/retro_five.json")


def lines_as_of(snaps, t):
    s = snaps[snaps.pulled_at <= t].sort_values("pulled_at")
    s = s.drop_duplicates(["event_id", "book", "market", "player", "line"], keep="last")
    start = pd.to_datetime(s.commence_time, utc=True, errors="coerce")
    now = pd.Timestamp(dt.datetime.strptime(t, "%Y%m%dT%H%M%SZ"), tz="UTC")
    return s[start.isna() | (start > now)], now


def replay(season, week):
    seasons, pw, sched, snaps_df, inj, H, status, src = R.load_all()
    state = json.load(open("data/cache/model_state.json"))
    P = M.finalize_projections(M.upcoming_rows(H, sched, inj, season, week, vol=src["vol"], dc=src["dc"], pbp_starters=src["pbp"]["starters"]),
                               state["phi"], scale=state.get("scale", 1.0))
    P = R.attach_game_logs(P, H, season, week)
    snaps = O.load_snapshots(season, week)
    if snaps.empty:
        sys.exit(f"No odds snapshots for {season} week {week}")
    snaps["pulled_at"] = snaps.pulled_at.astype(str)
    picks, parlays = pd.DataFrame(), pd.DataFrame(columns=G.LEG_COLS)
    all_games = snaps.drop_duplicates("event_id").assign(slate=G.slate_of(snaps.drop_duplicates("event_id").commence_time),
                                                         start=pd.to_datetime(snaps.drop_duplicates("event_id").commence_time, utc=True))
    for t in sorted(snaps.pulled_at.unique()):
        lines, now = lines_as_of(snaps, t)
        bets = M.price_lines(lines, P)
        if bets.empty or "pick" not in bets:
            continue
        # recommended parlay per slate day, re-chosen until the day's first kickoff
        bets["slate"] = G.slate_of(bets.commence_time)
        for slate in sorted(x for x in bets.slate.unique() if x):
            if ((all_games.slate == slate) & (all_games.start <= now)).any():
                continue
            legs = G.choose_parlay(bets, slate)
            if legs is None:
                continue
            legs = legs.assign(season=season, week=week, slate=slate, parlay_id=f"{season}-wk{week:02d}-{slate}", chosen_at=t,
                               odds=np.where(legs.side == "Over", legs.over_odds, legs.under_odds))
            legs = legs[[c for c in G.LEG_COLS if c in legs.columns]]
            parlays = pd.concat([parlays[parlays.slate != slate], legs], ignore_index=True)
        new = bets[bets.pick.isin(["Over", "Under"]) & bets.best_price.fillna(False)].copy()
        if new.empty:
            continue
        new = new.assign(season=season, week=week, pulled_at=t, side=new.pick,
                         odds=np.where(new.pick == "Over", new.over_odds, new.under_odds))
        cols = G.KEY + ["team", "opp", "odds", "proj", "proj_model", "mkt_line", "model_over", "market_over", "ev", "why",
                        "lock", "grade", "consistency", "cons_hits", "cons_n", "payout", "event_id", "commence_time", "pulled_at"]
        new = new[[c for c in cols if c in new.columns]]
        picks = pd.concat([picks, new], ignore_index=True).drop_duplicates(G.KEY, keep="first")
        picks = G.mark_locks(picks, season, week, now=now)
        print(f"{t}: {len(lines)} lines on the board, {len(picks)} picks logged, locks = "
              + ", ".join(f"{r.player} {r.side} {r.line:g}" for r in picks[picks.five].itertuples()))
    # grade against box scores
    picks["name_key"] = picks.player.map(S.norm_name)
    stats = pw[(pw.season == season) & (pw.week == week)].groupby("name_key").agg(comb=("comb", "sum"), solo=("solo_t", "sum"))
    picks = picks.join(stats, on="name_key")
    picks["actual"] = np.where(picks.market.str.contains("solo"), picks.solo, picks.comb)
    done = picks.actual.notna()
    win = np.where(picks.side == "Over", picks.actual > picks.line, picks.actual < picks.line)
    picks["result"] = np.where(~done, "Pending", np.where(picks.actual == picks.line, "Push", np.where(win, "Win", "Loss")))
    dec = picks.odds.map(lambda a: M.american_to_decimal(a) if pd.notna(a) else np.nan)
    picks["units"] = np.where(picks.result == "Win", dec - 1, np.where(picks.result == "Loss", -1.0, 0.0))
    picks = picks.sort_values(["five", "lock"], ascending=[False, False])

    def rec(d):
        g = d[d.result.isin(["Win", "Loss", "Push"])]
        return dict(n=int(len(d)), wins=int((g.result == "Win").sum()), losses=int((g.result == "Loss").sum()),
                    pushes=int((g.result == "Push").sum()), pending=int((d.result == "Pending").sum()),
                    units=float(g.units.sum()), hit=float((g.result == "Win").sum() / max(1, (g.result != "Push").sum())) if len(g) else None)
    five = picks[picks.five]
    stats = pw[(pw.season == season) & (pw.week == week)].groupby(["season", "week", "name_key"]).agg(comb=("comb", "sum"), solo=("solo_t", "sum")).reset_index()
    PQ = G.grade_parlay_legs(parlays, stats) if len(parlays) else pd.DataFrame()
    entry = dict(season=season, week=week, replayed_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
                 rules=dict(line_weight=C.LINE_WEIGHT, pick_bar=C.PICK_BAR, signal_bar=C.SIGNAL_BAR, lock_weights=C.LOCK_WEIGHTS, grade_bars=C.GRADE_BARS),
                 five=rec(five), plays=rec(picks),
                 parlays=[] if PQ.empty else json.loads(PQ.to_json(orient="records")),
                 picks=[dict(player=r.player, team=r.team, opp=r.opp, market=r.market, side=r.side, line=float(r.line), odds=float(r.odds),
                             book=r.book, lock=float(r.lock), grade=r.grade, proj=float(r.proj), actual=None if pd.isna(r.actual) else float(r.actual),
                             result=r.result, units=float(r.units), commence_time=r.commence_time) for r in five.itertuples()])
    out = json.loads(OUT.read_text()) if OUT.exists() else dict(weeks=[])
    out["weeks"] = [w for w in out["weeks"] if not (w["season"] == season and w["week"] == week)] + [entry]
    out["weeks"].sort(key=lambda w: (w["season"], w["week"]))
    out["note"] = ("Replayed under the current rules using only what was known at each line pull. Weeks without odds "
                   "snapshots cannot be replayed: line pulling started in week 7 of 2026, and historical lines need a paid Odds API plan.")
    OUT.write_text(json.dumps(out, indent=1))
    f, p = entry["five"], entry["plays"]
    print(f"\nweek {week} replay: five {f['wins']}-{f['losses']} ({f['pending']} pending, {f['units']:+.2f}u); "
          f"all plays {p['wins']}-{p['losses']} of {p['n']} ({p['units']:+.2f}u)")
    for r in five.itertuples():
        print(f"  {r.grade} {r.lock:4.0f}  {r.player:22}{r.side:6}{r.line:>4} {r.market[7:]:17}{int(r.odds):>5} {r.book:13} actual {r.actual!s:>5} {r.result}")
    for q in entry["parlays"]:
        print(f"  parlay {q['slate']}: {q['n_legs']} legs {q['combined_american']:+d}, chance {q['combined_prob']:.0%}, stake {q['units']:.1f}u -> {q['result']} ({q['units_won']:+.2f}u)")
        for l in q["legs"]:
            print(f"      {l['player']} {l['side']} {l['line']:g} {l['market'][7:]} {l['odds']:+.0f} {l['book']}  p {l['p_side']:.2f}  actual {l['actual']}  {l['result']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=C.SEASON)
    ap.add_argument("--week", type=int, required=True)
    a = ap.parse_args()
    replay(a.season, a.week)
