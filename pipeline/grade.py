"""Log picks when they are made, then grade them against official box scores and the closing line."""
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline import odds as O
from pipeline.model import american_to_decimal
from pipeline.sources import norm_name

PICKS = Path("data/picks.csv")
KEY = ["season", "week", "player", "market", "side", "line", "book"]


def log_picks(bets, season, week, pulled_at):
    if bets is None or bets.empty or "pick" not in bets:
        return 0
    new = bets[bets.pick.isin(["Over", "Under"]) & bets.best_price.fillna(False)].copy()
    if new.empty:
        return 0
    new = new.assign(season=season, week=week, pulled_at=pulled_at, side=new.pick,
                     odds=np.where(new.pick == "Over", new.over_odds, new.under_odds))
    cols = KEY + ["team", "opp", "odds", "proj", "proj_model", "mkt_line", "model_over", "market_over", "ev", "why",
                  "lock", "grade", "consistency", "cons_hits", "cons_n", "payout", "event_id", "commence_time", "pulled_at"]
    new = new[[c for c in cols if c in new.columns]]
    old = pd.read_csv(PICKS) if PICKS.exists() else pd.DataFrame(columns=cols)
    both = pd.concat([old, new], ignore_index=True).drop_duplicates(KEY, keep="first")  # keep the first price we took
    PICKS.parent.mkdir(parents=True, exist_ok=True)
    both.to_csv(PICKS, index=False)
    return len(both) - len(old)


def _no_vig_side(over, under, side):
    if pd.isna(over) or pd.isna(under):
        return np.nan
    po, pu = 1 / american_to_decimal(over), 1 / american_to_decimal(under)
    return (po if side == "Over" else pu) / (po + pu)


def grade(pw_comb):
    """pw_comb: player-week rows with name_key, season, week, comb, solo_t (official formula applied)."""
    if not PICKS.exists():
        return pd.DataFrame(), {}
    P = pd.read_csv(PICKS)
    if P.empty:
        return P, {}
    P["name_key"] = P.player.map(norm_name)
    stats = pw_comb.groupby(["season", "week", "name_key"]).agg(comb=("comb", "sum"), solo=("solo_t", "sum")).reset_index()
    P = P.merge(stats, on=["season", "week", "name_key"], how="left")
    P["actual"] = np.where(P.market.str.contains("solo"), P.solo, P.comb)
    # closing line value: compare our price with the last price before kickoff at the same book
    clv = []
    for (s, w), part in P.groupby(["season", "week"]):
        cl = O.closing_lines(int(s), int(w))
        for r in part.itertuples():
            c = cl[(cl.book == r.book) & (cl.market == r.market) & (cl.player == r.player)] if len(cl) else cl
            if c is None or len(c) == 0:
                clv.append((r.Index, np.nan, np.nan))
                continue
            c = c.iloc[0]
            line_move = (c.line - r.line) if r.side == "Over" else (r.line - c.line)   # positive = we beat the close
            prob_gain = _no_vig_side(c.over_odds, c.under_odds, r.side) - (1 / american_to_decimal(r.odds)) if c.line == r.line else np.nan
            clv.append((r.Index, line_move, prob_gain))
    for idx, lm, pg in clv:
        P.loc[idx, "clv_line"] = lm
        P.loc[idx, "clv_prob"] = pg
    done = P.actual.notna()
    win = np.where(P.side == "Over", P.actual > P.line, P.actual < P.line)
    push = P.actual == P.line
    P["result"] = np.where(~done, "Pending", np.where(push, "Push", np.where(win, "Win", "Loss")))
    dec = P.odds.map(lambda a: american_to_decimal(a) if pd.notna(a) else np.nan)
    P["units"] = np.where(P.result == "Win", dec - 1, np.where(P.result == "Loss", -1.0, 0.0))
    g = P[P.result.isin(["Win", "Loss", "Push"])]
    by_grade = []
    if "grade" in P.columns:
        for gr, part in g.groupby(P.grade.fillna("ungraded")):
            by_grade.append(dict(grade=gr, bets=int(len(part)), wins=int((part.result == "Win").sum()),
                                 losses=int((part.result == "Loss").sum()), units=float(part.units.sum()),
                                 roi=float(part.units.mean()) if len(part) else None))
    summary = dict(by_grade=by_grade,bets=int(len(g)), wins=int((g.result == "Win").sum()), losses=int((g.result == "Loss").sum()),
                   pushes=int((g.result == "Push").sum()), units=float(g.units.sum()) if len(g) else 0.0,
                   roi=float(g.units.sum() / len(g)) if len(g) else None,
                   avg_clv_line=float(P.clv_line.mean()) if P.clv_line.notna().any() else None,
                   beat_close_share=float((P.clv_line > 0).mean()) if P.clv_line.notna().any() else None,
                   pending=int((P.result == "Pending").sum()))
    return P.drop(columns=["name_key"]), summary
