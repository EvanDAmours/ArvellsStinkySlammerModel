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
    both = mark_weekly_five(both, season, week)
    PICKS.parent.mkdir(parents=True, exist_ok=True)
    both.to_csv(PICKS, index=False)
    return len(both) - len(old)


FIVE = 5


def mark_weekly_five(P, season, week, now=None):
    """Flag this week's five highest lock-score picks (one per player). A pick whose game has started keeps its
    place; the remaining places are re-chosen among games still to come at every pull."""
    now = now or O._utcnow()
    P = P.copy()
    if "five" not in P.columns:
        P["five"] = False
    P["five"] = P.five.fillna(False).astype(bool)
    wk = (P.season == season) & (P.week == week)
    start = pd.to_datetime(P.commence_time, utc=True, errors="coerce")
    started = wk & start.notna() & (start <= now)
    open_ = wk & ~started
    kept = P[started & P.five]
    P.loc[open_, "five"] = False
    slots = max(0, FIVE - kept.player.nunique())
    if slots and "lock" in P.columns:
        cand = P[open_ & ~P.player.isin(set(kept.player))].sort_values("lock", ascending=False)
        cand = cand[cand.lock.notna()].drop_duplicates("player").head(slots)
        P.loc[cand.index, "five"] = True
    return P


def weekly_five_keys(season, week):
    """(player, market, side, line, book) of this week's five, for marking the board."""
    if not PICKS.exists():
        return set()
    P = pd.read_csv(PICKS)
    if "five" not in P.columns:
        return set()
    P = P[(P.season == season) & (P.week == week) & P.five.fillna(False).astype(bool)]
    return {(r.player, r.market, r.side, float(r.line), r.book) for r in P.itertuples()}


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
    five = g[g.five.fillna(False).astype(bool)] if "five" in g.columns else g.iloc[0:0]
    five_all = P[P.five.fillna(False).astype(bool)] if "five" in P.columns else P.iloc[0:0]
    weeks, cw, cl = [], 0, 0
    for (sn, wk), part in five_all.groupby(["season", "week"]):
        w, l, pu = int((part.result == "Win").sum()), int((part.result == "Loss").sum()), int((part.result == "Push").sum())
        cw, cl = cw + w, cl + l
        weeks.append(dict(season=int(sn), week=int(wk), picks=int(len(part)), wins=w, losses=l, pushes=pu,
                          pending=int((part.result == "Pending").sum()), units=float(part.units.sum()),
                          running_wins=cw, running_losses=cl))
    summary = dict(by_grade=by_grade,
                   five=dict(bets=int(len(five)), wins=int((five.result == "Win").sum()), losses=int((five.result == "Loss").sum()),
                             pushes=int((five.result == "Push").sum()), units=float(five.units.sum()) if len(five) else 0.0,
                             hit=float((five.result == "Win").sum() / max(1, (five.result != "Push").sum())) if len(five) else None,
                             pending=int((five_all.result == "Pending").sum()), weeks=weeks),bets=int(len(g)), wins=int((g.result == "Win").sum()), losses=int((g.result == "Loss").sum()),
                   pushes=int((g.result == "Push").sum()), units=float(g.units.sum()) if len(g) else 0.0,
                   roi=float(g.units.sum() / len(g)) if len(g) else None,
                   avg_clv_line=float(P.clv_line.mean()) if P.clv_line.notna().any() else None,
                   beat_close_share=float((P.clv_line > 0).mean()) if P.clv_line.notna().any() else None,
                   pending=int((P.result == "Pending").sum()))
    return P.drop(columns=["name_key"]), summary


def write_five_log(P, summary, path):
    """Rewrite the running tally of the weekly five as a markdown file: the record to date, a line per week, and
    every pick with its result. Regenerated by the daily job from data/picks.csv, so it is never edited by hand."""
    import datetime as dt
    f = (summary or {}).get("five") or {}
    weeks = f.get("weeks") or []
    lines = ["# Weekly five: running tally", "",
             "The five highest-confidence picks of each week, named before kickoff and tracked here. Target: 70% hits.",
             f"Generated {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC by the daily job. Do not edit by hand.", ""]
    if not weeks:
        lines.append("No weekly five graded yet.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n")
        return
    hit = f.get("hit")
    lines += [f"**Record: {f.get('wins', 0)}-{f.get('losses', 0)}" + (f"-{f['pushes']}" if f.get("pushes") else "") +
              (f" ({hit:.0%})" if hit is not None else "") + f", {f.get('units', 0):+.2f} units, {f.get('pending', 0)} pending.**", "",
              "| Week | Picks | Record | Units | Running record |", "| --- | --- | --- | --- | --- |"]
    for w in weeks:
        rec = f"{w['wins']}-{w['losses']}" + (f"-{w['pushes']}" if w["pushes"] else "") + (f" ({w['pending']} pending)" if w["pending"] else "")
        lines.append(f"| {w['season']} wk {w['week']} | {w['picks']} | {rec} | {w['units']:+.2f} | {w['running_wins']}-{w['running_losses']} |")
    five = P[P.five.fillna(False).astype(bool)] if "five" in P.columns else P.iloc[0:0]
    for (sn, wk), part in five.groupby(["season", "week"]):
        lines += ["", f"## {sn} week {wk}", "", "| Pick | Price | Book | Grade | Lock | Actual | Result |", "| --- | --- | --- | --- | --- | --- | --- |"]
        for r in part.sort_values("lock", ascending=False).itertuples():
            market = "solo" if "solo" in str(r.market) else "tackles + assists"
            price = ("+" if r.odds > 0 else "") + str(int(r.odds)) if pd.notna(r.odds) else ""
            actual = "" if pd.isna(r.actual) else str(int(r.actual))
            lock = "" if pd.isna(getattr(r, "lock", np.nan)) else str(int(round(r.lock)))
            lines.append(f"| {r.player} {r.side} {r.line:g} {market} | {price} | {r.book} | {getattr(r, 'grade', '')} | {lock} | {actual} | {r.result} |")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
