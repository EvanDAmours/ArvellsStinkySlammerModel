"""Score the candidate "holes" in the books' lines on the closing lines of finished weeks (MODEL_LOG, open issue 15).

Each candidate was written down on 2026-11-10 from weeks 7 to 9 and is in no rule. This tool applies the same definitions to any
weeks, so weeks 10 on test them out of sample. Everything a candidate uses is known before kickoff: the two closing lines and
the player's games earlier in the season. One line per player and market (the median line across books that quote both sides,
the best price of each side).

  python tools/holes.py                 every week with closing lines and box scores
  python tools/holes.py --weeks 10 11   those weeks only
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C                      # noqa: E402
import run as R                         # noqa: E402
from pipeline import odds as O          # noqa: E402
from pipeline.model import american_to_decimal as dec  # noqa: E402
from pipeline.sources import norm_name  # noqa: E402

PART_TIME, HOT = C.HOLES["part_time"], C.HOLES["hot"]      # the same numbers the card's flags use


def frame(H, season, weeks=None):
    """One row per player and market (solo, combined) with a closing line, a decided result and his numbers before the week."""
    Hg = R.official_solo(H)
    Hs = Hg[Hg.season == season]
    all_weeks = sorted(int(w) for w in Hs[Hs.comb.notna()].week.unique())
    out = []
    for w in (weeks or all_weeks):
        cl = O.closing_lines(season, int(w))
        cur = Hs[Hs.week == w]
        if cl is None or len(cl) == 0 or cur.empty:
            continue
        cl = cl[cl.over_odds.notna() & cl.under_odds.notna()].copy()
        cl["name_key"], cl["kind"] = cl.player.map(norm_name), cl.market.map(C.market_kind)
        cl["od"], cl["ud"] = cl.over_odds.map(dec), cl.under_odds.map(dec)
        g = cl[cl.kind != "assists"].groupby(["name_key", "kind"]).agg(line=("line", "median"), od=("od", "max"), ud=("ud", "max")).reset_index()
        both = g.pivot(index="name_key", columns="kind", values="line")
        g["book_share"] = g.name_key.map((both["solo"] / both["combined"]) if {"solo", "combined"} <= set(both.columns) else pd.Series(dtype=float))
        box = cur.groupby("name_key").agg(comb=("comb", "sum"), solo=("solo_t", "sum"), teams=("team", "nunique")).reset_index()
        pr = Hs[Hs.week < w].sort_values("week")
        f = pr.groupby("name_key").agg(avg_c=("comb", "mean"), avg_s=("solo_t", "mean"), sum_c=("comb", "sum"), sum_s=("solo_t", "sum"), pct=("def_pct", "mean")).reset_index()
        l3 = pr.groupby("name_key").tail(3).groupby("name_key").agg(l3_c=("comb", "mean")).reset_index()
        g = g.merge(box[box.teams == 1], on="name_key").merge(f, on="name_key", how="left").merge(l3, on="name_key", how="left")
        league = g.drop_duplicates("name_key").sum_s.sum() / max(1.0, g.drop_duplicates("name_key").sum_c.sum())
        k = C.SHARE_GAP["k"]
        g["share_gap"] = (g.sum_s.fillna(0) + k * league) / (g.sum_c.fillna(0) + k) - g.book_share
        g["week"] = int(w)
        out.append(g)
    if not out:
        return pd.DataFrame()
    D = pd.concat(out, ignore_index=True)
    D["actual"] = np.where(D.kind == "solo", D.solo, D.comb)
    D = D[D.actual != D.line].copy()
    D["under"] = D.actual < D.line
    D["u_ret"], D["o_ret"] = np.where(D.under, D.ud - 1, -1.0), np.where(~D.under, D.od - 1, -1.0)
    return D


def candidates(D):
    """[(name, the side it bets, the rows it bets, the rows it is compared with)]."""
    s, c = D[D.kind == "solo"], D[D.kind == "combined"]
    gap, part = s.share_gap <= C.SHARE_GAP["flag"], s.pct < PART_TIME
    hot = (c.l3_c - c.avg_c) >= HOT
    return [("Solo Under, the book's solo share too high for him (share gap)", "Under", s[gap], s[~gap]),
            ("Solo Under, a part-time player (under 85% of the snaps)", "Under", s[part], s[~part]),
            ("Solo Under, neither of the two (the rest of the solo board)", "Under", s[~gap & ~part], s[gap | part]),
            ("Combined Over, his last three games half a tackle over his season average", "Over", c[hot], c[~hot])]


def report(D):
    rec = lambda x, side: (int((x.under == (side == "Under")).sum()), int((x.under != (side == "Under")).sum()), float((x.u_ret if side == "Under" else x.o_ret).mean()) if len(x) else float("nan"))
    lines = []
    for name, side, bet, rest in candidates(D):
        w, l, r = rec(bet, side); w2, l2, r2 = rec(rest, side)
        by = " ".join(f"wk{wk} {rec(x, side)[0]}-{rec(x, side)[1]}" for wk, x in bet.groupby("week"))
        lines.append(f"{name}: {w}-{l} ({w / max(1, w + l):.0%}, {r:+.1%} a bet) against {w2}-{l2} ({w2 / max(1, w2 + l2):.0%}) for the other lines of the market | {by}")
    return lines


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=C.SEASON)
    ap.add_argument("--weeks", type=int, nargs="*")
    a = ap.parse_args()
    H = R.load_all()[5]
    D = frame(H, a.season, a.weeks)
    if D.empty:
        sys.exit("no closing lines with box scores for those weeks")
    print(f"{len(D)} decided closing lines, weeks {sorted(int(w) for w in D.week.unique())}; at the best closing price of the side, 1 unit a bet")
    for ln in report(D):
        print("  " + ln)
