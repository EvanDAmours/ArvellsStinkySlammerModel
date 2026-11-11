"""Look for built-in bias: every stored line of the replayed seasons against what the player did, and the replayed picks.

Measures only; it changes nothing. Input is the folder `tools/season_test.py --season S --out DIR` writes for each
season (lines_S.csv, picks_S.csv), all in one DIR. Run it in a scratch copy, like the replay:

  python tools/bias_audit.py --dir /tmp/x --seasons 2024 2025 2026 [--history H.pkl]

What it prints: (1) the model's number against the result for players who had a line, by market, season and position;
(2) every Under on the board against the book's fair chance, no pick rule at all; (3) said chance against what happened,
for the model alone and for the engine; (4) the Under by how much of the game the player played; (5) the book's solo
share, the model's and the result, and how many solo lines are flagged, by season; (6) the picks by size of edge and by
side and position; (7) whether picks win and lose together.

Solo is graded on the official count (solo plus tackle with assist), the one the books settle on: the first pass of
2026-11-11 used the plain solo column and overstated every solo Under by about five points.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C                      # noqa: E402

KIND = {"player_tackles_assists": "combined", "player_solo_tackles": "solo", "player_assists": "assists"}
LINE = ["season", "week", "player_id", "kind", "book", "line"]


def frame(d, seasons, history=None):
    """Every stored line with the player's result, his playing time and the price."""
    if history:
        H = pd.read_pickle(history)
    else:
        import run as R
        H = R.load_all()[5]
    H = H[H.season_type.eq("REG")].copy()
    H["solo"] = H.solo_off.fillna(H.solo) if "solo_off" in H.columns else H.solo
    L = pd.concat([pd.read_csv(Path(d) / f"lines_{s}.csv") for s in seasons], ignore_index=True)
    h = H[["season", "week", "player_id", "solo", "ast", "comb", "def_pct", "pct_prev", "group"]].drop_duplicates(["season", "week", "player_id"])
    D = L.merge(h, on=["season", "week", "player_id"], how="left")
    D["kind"] = D.market.map(KIND)
    D["actual"] = np.where(D.kind == "solo", D.solo, np.where(D.kind == "assists", D.ast, D.comb))
    D = D[D.actual.notna()].copy()
    D["over_hit"] = (D.actual > D.line).astype(float)
    D["win"] = np.where(D.side == "Over", D.actual > D.line, D.actual < D.line).astype(float)
    D["dec"] = np.where(D.odds > 0, 1 + D.odds / 100, 1 + 100 / D.odds.abs())
    D["units"] = np.where(D.win == 1, D.dec - 1, -1.0)
    return D, H


def said_hit(g, col, hit, bins):
    t = g.groupby(pd.cut(g[col], bins), observed=True).agg(n=(hit, "size"), said=(col, "mean"), hit=(hit, "mean"))
    t["gap"] = t.hit - t.said
    return t.round(3).to_string()


def pair_corr(g, key):
    """Correlation of results between two picks of the same cluster."""
    r = g.win - g.win.mean()
    n = g.groupby(key).size()
    s = r.groupby(g[key]).sum()
    pairs = (n ** 2).sum() - n.sum()
    return float(((s ** 2).sum() - (r ** 2).sum()) / pairs / g.win.var(ddof=0)) if pairs else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--seasons", type=int, nargs="+", required=True)
    ap.add_argument("--history", default=None, help="a pickled history frame; default: load it as the pipeline does")
    a = ap.parse_args()
    D, H = frame(a.dir, a.seasons, a.history)
    one = D.drop_duplicates(["season", "week", "player_id", "kind"]).assign(err=lambda x: x.actual - x.proj_model)
    agg = dict(n=("err", "size"), proj=("proj_model", "mean"), actual=("actual", "mean"), err=("err", "mean"), se=("err", lambda x: x.std() / np.sqrt(len(x))))
    print("== 1. The model's number against the result, players with a line (err = result minus the model)")
    print(one.groupby(["kind", "season"]).agg(**agg).round(3).to_string())
    print(one[one.season >= max(a.seasons) - 1].groupby(["kind", "group"]).agg(**agg).round(3).to_string())

    U = D.drop_duplicates(LINE).assign(under_hit=lambda x: 1 - x.over_hit, fair_under=lambda x: 1 - x.market_over, model_under=lambda x: 1 - x.model_over_own)
    print("\n== 2. Every line once: the Under against the book's fair chance, no pick rule")
    print(U.groupby(["kind", "season"]).agg(lines=("under_hit", "size"), under_hit=("under_hit", "mean"), book_fair=("fair_under", "mean"), model_alone=("model_under", "mean")).round(3).to_string())

    print("\n== 3. Said chance of the Under against what happened")
    for kd, g in U.groupby("kind"):
        print(f" -- {kd}: the model alone\n{said_hit(g, 'model_under', 'under_hit', [0, .4, .5, .6, .7, 1])}")
    for (kd, sd), g in D.groupby(["kind", "side"]):
        print(f" -- {kd} {sd}: the engine's win chance, rows as stored\n{said_hit(g, 'p_claim', 'win', [0, .5, .55, .6, .65, .7, 1])}")

    print("\n== 4. The Under by the share of defensive snaps the player played")
    print(U.groupby(["kind", pd.cut(U.def_pct, [0, .5, .7, .85, .95, 1.01])], observed=True).agg(n=("under_hit", "size"), under_hit=("under_hit", "mean")).round(3).unstack(0).to_string())
    x = D.drop_duplicates(["season", "week", "player_id"])
    print(x.groupby("season").agg(expected=("pct_prev", "mean"), played=("def_pct", "mean")).round(3).to_string())

    print("\n== 5. Solo share of combined: the league, then the book's, the model's and the result for players with both lines")
    lg = H.groupby("season").agg(solo=("solo", "sum"), comb=("comb", "sum"))
    print((lg.solo / lg.comb).round(4).to_dict())
    S = one[one.kind == "solo"].merge(one[one.kind == "combined"][["season", "week", "player_id", "line", "proj_model"]], on=["season", "week", "player_id"], suffixes=("", "_c"))
    S["hole"] = S.line / S.line_c >= C.HOLES["book_share"]
    t = S.groupby("season").agg(n=("solo", "size"), book=("line", "sum"), bookc=("line_c", "sum"), m=("proj_model", "sum"), mc=("proj_model_c", "sum"), solo=("solo", "sum"), comb=("comb", "sum"), flagged=("hole", "mean"))
    print(t.assign(book_share=t.book / t.bookc, model_share=t.m / t.mc, actual_share=t.solo / t.comb)[["n", "book_share", "model_share", "actual_share", "flagged"]].round(3).to_string())
    Su = U[U.kind == "solo"].merge(U[U.kind == "combined"].groupby(["season", "week", "player_id"]).line.mean().rename("line_c").reset_index(), on=["season", "week", "player_id"], how="left")
    Su = Su.merge(D[(D.kind == "solo") & (D.side == "Under")][LINE + ["dec"]].rename(columns={"dec": "dec_under"}), on=LINE, how="left")
    Su["hole"] = Su.line / Su.line_c >= C.HOLES["book_share"]
    t = Su.groupby(["season", "hole"]).agg(lines=("under_hit", "size"), under_hit=("under_hit", "mean"), line=("line", "mean"), actual=("actual", "mean"), dec=("dec_under", "mean"))
    print(t.assign(breakeven=1 / t.dec).drop(columns="dec").round(3).to_string())

    P = pd.concat([pd.read_csv(Path(a.dir) / f"picks_{s}.csv", low_memory=False) for s in a.seasons], ignore_index=True)
    P = P[P.result.isin(["Win", "Loss"]) & (P.tier == "pick")].copy()
    P["win"] = (P.result == "Win").astype(float)
    P["kind"] = P.market.map(KIND)
    rec = lambda g: pd.Series(dict(n=len(g), w=int(g.win.sum()), l=int(len(g) - g.win.sum()), hit=round(g.win.mean(), 3), said=round(g.p_claim.mean(), 3), per_bet=round(g.units.mean(), 3)))
    print(f"\n== 6. The picks ({len(P)}): by size of the cautious edge, by the model's own chance, by side and position")
    print(P.groupby(pd.cut(P.edge_low, [-1, .01, .02, .04, .07, 1]), observed=True).apply(rec).to_string())
    print(P.groupby(pd.cut(P.p_model, [0, .6, .65, .7, .75, .8, 1]), observed=True).apply(rec).to_string())
    print(P.groupby(["kind", "side"]).apply(rec).to_string())
    print(P.groupby(["group", "side"]).apply(rec).to_string())
    print(f" locks: {rec(P[P.five.fillna(False).astype(bool)]).to_dict()} | all A: {rec(P[P.grade == 'A']).to_dict()}")

    print("\n== 7. Do picks win and lose together?")
    P["tg"] = P.season.astype(str) + "|" + P.week.astype(str) + "|" + P.team.astype(str)
    print(f" two picks on the same team in the same game: correlation {pair_corr(P, 'tg'):+.3f}; in the same game, either team: {pair_corr(P, 'event_id'):+.3f}")
    x = P[P.side == "Under"].pivot_table(index=["season", "week", "player"], columns="kind", values="win", aggfunc="first")
    if {"solo", "combined"} <= set(x.columns):
        x = x.dropna(subset=["solo", "combined"])
        print(f" solo Under and combined Under on the same player: {len(x)} pairs, same result in {(x.solo == x.combined).mean():.0%}, correlation {x.solo.corr(x.combined):+.2f}")
    w = P.groupby(["season", "week"]).agg(n=("win", "size"), hit=("win", "mean"), said=("p_claim", "mean"), v=("p_claim", lambda p: (p * (1 - p)).sum()))
    z = (w.hit - w.said) * w.n / np.sqrt(w.v)
    print(f" weeks: {len(w)}; the spread of weekly results is {z.std():.2f} times what independent picks at the said chances give")
    d = P.groupby(["season", "week", "player", "kind", "side"]).size()
    print(f" the same bet at more than one book: {int((d > 1).sum())} of {len(d)}")


if __name__ == "__main__":
    main()
