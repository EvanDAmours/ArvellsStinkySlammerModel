"""Replay a whole season (or some of its weeks) under the CURRENT rules and report what they would have done.

For each week: tools/replay_five.py rebuilds the projection from the games before that week and prices every stored odds
snapshot through the live functions; the picks are graded on the box scores. Then, over the weeks together: the record
by grade, kind and stretch, the units at the stakes, the engine against the book's fair closing price (the scoreboard),
and the candidate holes of tools/holes.py. Past seasons' lines come from `python run.py history --season` (data/odds).

Run it in a scratch copy of the repo, never in the working tree (it loads and caches the stats feeds), and one
pipeline process at a time:

  python tools/season_test.py --season 2025                    every week with stored lines
  python tools/season_test.py --season 2026 --weeks 4 5 6 --out /tmp/x     picks and lines kept as CSV under /tmp/x

Known look-ahead, as in the replay: the week's injury report is the final one. The projection's constants were tuned on
2023 to 2026, so an earlier season is out of sample for the pricing rules, not for those constants. An earlier season's
level for lined players is 1 (the line log is this season's).
"""
import argparse
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C                      # noqa: E402
import run as R                         # noqa: E402
from pipeline import evaluate as EV     # noqa: E402
from pipeline import linelog as LL      # noqa: E402
from pipeline import odds as O          # noqa: E402
from tools import holes as HO           # noqa: E402
from tools import replay_five as RF     # noqa: E402

KIND = {"player_tackles_assists": "combined", "player_solo_tackles": "solo", "player_assists": "assists"}


def rec(x):
    if not len(x):
        return "-"
    return f"{int(x.win.sum())}-{int((~x.win).sum())} ({x.win.mean():.0%}, {x.flat.mean():+.0%} a bet; {x.st.sum():+.1f}u on {x.stake.sum():.0f} staked)"


def report(P, season):
    """P: the counted, decided picks of the replayed weeks."""
    P = P.assign(win=P.result == "Win", flat=P.units, st=P.units * P.stake, kind=P.market.map(KIND))
    weeks = sorted(P.week.unique())
    half = weeks[len(weeks) // 2] if len(weeks) > 3 else None
    P["stretch"] = "all" if half is None else np.where(P.week < half, f"weeks {weeks[0]}-{half - 1}", f"weeks {half}-{weeks[-1]}")
    stretches = list(dict.fromkeys(P.sort_values("week").stretch))
    line = lambda x: " | ".join(f"{s}: {rec(x[x.stretch == s])}" for s in stretches) + (f" | all: {rec(x)}" if len(stretches) > 1 else "")
    print(f"\n{season}, weeks {weeks[0]} to {weeks[-1]}: every pick  {line(P)}")
    for g, x in P.groupby("grade"):
        print(f"  grade {g}  {line(x)}  ({len(x) / len(weeks):.1f} a week)")
    print(f"  locks    {line(P[P.five.fillna(False).astype(bool)])}")
    for (k, sd), x in P.groupby(["kind", "side"]):
        print(f"  {k} {sd}: {rec(x)}")
    flag = P.why.astype(str).str.contains("the book's solo line is", regex=False)
    su = (P.kind == "solo") & (P.side == "Under")
    print(f"  solo Under on a flagged line: {rec(P[su & flag])} | unflagged: {rec(P[su & ~flag])}")
    w = P.groupby("week").agg(flat=("flat", "sum"), st=("st", "sum"), stake=("stake", "sum"))
    print(f"  weeks: a profit at one unit a bet in {int((w.flat > 0).sum())} of {len(w)}, at the stakes in {int((w.st > 0).sum())}; "
          f"worst week {w.st.min():+.1f}u, best {w.st.max():+.1f}u; {w.stake.mean():.1f}u staked a week")
    for b, x in P.groupby("book"):
        print(f"  at {b}: {rec(x)}")


def summary(P, season):
    """The same replay as a small record for the site (data/replay_seasons.json): the season's picks under the current
    rules, by grade and by week. P: the counted, decided picks."""
    P = P.assign(win=P.result == "Win", st=P.units * P.stake)
    def r(x):
        n = len(x)
        return dict(bets=int(n), wins=int(x.win.sum()), losses=int(n - x.win.sum()), hit=float(x.win.mean()) if n else None, units=float(x.units.sum()),
                    staked=float(x.stake.sum()), units_at_stake=float(x.st.sum()))
    weeks = sorted(int(w) for w in P.week.unique())
    by_week = []
    for w, x in P.groupby("week"):
        by_week.append(dict(week=int(w), **r(x), by_grade={g: dict(wins=int(y.win.sum()), losses=int((~y.win).sum()), units=float(y.units.sum())) for g, y in x.groupby("grade")}))
    wk = P.groupby("week").st.sum()
    return dict(season=int(season), weeks=weeks, plays=r(P), by_grade=[dict(grade=g, **r(x)) for g, x in P.groupby("grade")],
                locks=r(P[P.five.fillna(False).astype(bool)]), by_week=by_week, weeks_up_at_stakes=int((wk > 0).sum()), worst_week=float(wk.min()), best_week=float(wk.max()))


def save_summary(path, entry):
    """Put a season's record into the site's file, replacing that season's earlier one."""
    import json
    path = Path(path)
    data = json.loads(path.read_text()) if path.exists() else dict(seasons=[])
    data["seasons"] = sorted([e for e in data.get("seasons", []) if e.get("season") != entry["season"]] + [entry], key=lambda e: e["season"])
    data["note"] = ("Each season's stored lines replayed under the current rules: the projection rebuilt from the games before each week, the picks made by the "
                    "live functions and graded on the box scores. One snapshot a week for 2024, 2025 and weeks 4 to 6 of 2026 (an hour before kickoff), the "
                    "final injury report, and the best price across the books on the feed. The rules were chosen on 2025 and 2026; 2024 was not used.")
    path.write_text(json.dumps(data, indent=1))


def scoreboard(lines, H, season):
    """The engine against the book's fair closing price on the replayed weeks' lines."""
    if lines is None or not len(lines):
        return
    log = lines.sort_values("pulled_at").drop_duplicates(["season", "week", "player", "team", "market"], keep="last")
    tmp = Path(tempfile.mkdtemp()) / "lines_log.csv"
    log.to_csv(tmp, index=False)
    saved, season_saved = LL.LOG, C.SEASON
    try:
        LL.LOG, C.SEASON = tmp, season
        Hg = R.official_solo(H)
        sb = EV.scoreboard(EV.closing_frame(Hg[["season", "week", "team", "name_key", "comb", "solo_t"]], season), live_week=1)
    finally:
        LL.LOG, C.SEASON = saved, season_saved
    s = (sb or {}).get("since")
    if not s:
        print("\nscoreboard: too few decided lines")
        return None
    print(f"\nthe engine against the book, {s['lines']} decided closing lines: log-loss book {s['log_loss']['market']:.4f}, model alone {s['log_loss']['model']:.4f}, "
          f"engine {s['log_loss']['engine']:.4f}; engine better by {s['engine_minus_market']:+.4f} (t {s['t'] or 0:+.1f}), in "
          f"{sum(b['engine_minus_market'] > 0 for b in sb['by_week'])} of {len(sb['by_week'])} weeks")
    for k, v in s["by_kind"].items():
        print(f"  {k}: {v['lines']} lines, engine better by {v['engine_minus_market']:+.4f} (give or take {2 * (v['se'] or 0):.4f})")
    for r in sb["shadow"]:
        q = r["since"]
        print(f"  in the shadow, {r['name']}: {q['vs_engine']:+.4f} against the engine (t {q['t'] or 0:+.1f})")
    return dict(lines=int(s["lines"]), engine_minus_market=float(s["engine_minus_market"]), t=None if s["t"] is None else float(s["t"]),
                weeks=int(len(sb["by_week"])), weeks_better=int(sum(b["engine_minus_market"] > 0 for b in sb["by_week"])))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=C.SEASON)
    ap.add_argument("--weeks", type=int, nargs="*")
    ap.add_argument("--out", default="", help="keep the picks and the lines of the replay as CSV in this folder")
    ap.add_argument("--json", default="", help="write the season's record for the site into this file (data/replay_seasons.json)")
    a = ap.parse_args()
    weeks = a.weeks or sorted(int(p.name[2:]) for p in (O.ODDS_DIR / str(a.season)).glob("wk*") if p.name[2:].isdigit())
    if not weeks:
        sys.exit(f"no stored lines for {a.season}")
    if a.season != C.SEASON:
        R.lined_level_now = lambda H, week: 1.0          # the line log holds this season only
    loaded = R.load_all()
    picks, lines = [], []
    scratch = Path(tempfile.mkdtemp()) / "retro.json"
    for wk in weeks:
        try:
            _, graded, _, ll_ = RF.replay(a.season, wk, loaded=loaded, out=scratch, keep_all=True)
        except SystemExit as e:
            print(f"week {wk}: {e}")
            continue
        if len(graded):
            picks.append(graded)
        if ll_ is not None and len(ll_):
            lines.append(ll_)
    P = pd.concat(picks, ignore_index=True) if picks else pd.DataFrame()
    L = pd.concat(lines, ignore_index=True) if lines else pd.DataFrame()
    if a.out:
        Path(a.out).mkdir(parents=True, exist_ok=True)
        P.to_csv(Path(a.out) / f"picks_{a.season}.csv", index=False)
        L.to_csv(Path(a.out) / f"lines_{a.season}.csv", index=False)
    if len(P) and "counted" in P.columns:
        D = P[P.counted.fillna(False).astype(bool) & P.result.isin(["Win", "Loss"])]
        if len(D):
            report(D, a.season)
    else:
        D = pd.DataFrame()
    sb_ = scoreboard(L, loaded[5], a.season)
    if a.json and len(D):
        save_summary(a.json, dict(summary(D, a.season), against_the_book=sb_))
    D2 = HO.frame(loaded[5], a.season, weeks)
    if len(D2):
        print(f"\nthe holes, {len(D2)} decided closing lines (tools/holes.py):")
        for ln in HO.report(D2):
            print("  " + ln)
