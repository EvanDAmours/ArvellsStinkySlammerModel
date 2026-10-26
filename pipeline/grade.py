"""Log picks when they are made, then grade them against official box scores and the closing line."""
from pathlib import Path

import numpy as np
import pandas as pd

import config as C
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
    both = mark_locks(both, season, week)
    PICKS.parent.mkdir(parents=True, exist_ok=True)
    both.to_csv(PICKS, index=False)
    return len(both) - len(old)


FIVE = 5
EDMONTON = "America/Edmonton"


def slate_of(commence_time):
    """Kickoff date in Edmonton time: the slate a game belongs to."""
    t = pd.to_datetime(commence_time, utc=True, errors="coerce")
    if isinstance(t, pd.Series):
        return t.dt.tz_convert(EDMONTON).dt.strftime("%Y-%m-%d").where(t.notna(), "")
    return "" if pd.isna(t) else t.tz_convert(EDMONTON).strftime("%Y-%m-%d")


def games_by_slate(season, week, extra=None):
    """Distinct games kicking off on each slate day, from every snapshot of the week (plus any frame given)."""
    frames = [O.load_snapshots(season, week)]
    if extra is not None and len(extra) and "event_id" in extra:
        frames.append(extra)
    frames = [f[["event_id", "commence_time"]] for f in frames if f is not None and len(f) and "commence_time" in f]
    if not frames:
        return {}
    d = pd.concat(frames, ignore_index=True).drop_duplicates("event_id")
    d["slate"] = slate_of(d.commence_time)
    return d.groupby("slate").event_id.nunique().to_dict()


def locks_for(n_games):
    return C.LOCKS_PER_SLATE["single"] if n_games <= 1 else C.LOCKS_PER_SLATE["multi"]


def mark_locks(P, season, week, now=None):
    """Flag each slate day's locks: the highest lock-score picks (one per player), 3 on a one-game day and 5 on a
    multi-game day. A pick whose game has started keeps its place; the remaining places are re-chosen among games
    still to come at every pull. The flag column is `five` for historical reasons."""
    now = now or O._utcnow()
    P = P.copy()
    if "five" not in P.columns:
        P["five"] = False
    P["five"] = P.five.fillna(False).astype(bool)
    P["slate"] = slate_of(P.commence_time)
    wk = (P.season == season) & (P.week == week)
    start = pd.to_datetime(P.commence_time, utc=True, errors="coerce")
    games = games_by_slate(season, week, P[wk])
    for slate in sorted(P[wk].slate.unique()):
        day = wk & (P.slate == slate)
        started = day & start.notna() & (start <= now)
        open_ = day & ~started
        kept = P[started & P.five]
        P.loc[open_, "five"] = False
        slots = max(0, locks_for(games.get(slate, 1)) - kept.player.nunique())
        if slots and "lock" in P.columns:
            cand = P[open_ & ~P.player.isin(set(kept.player))].sort_values("lock", ascending=False)
            cand = cand[cand.lock.notna()].drop_duplicates("player").head(slots)
            P.loc[cand.index, "five"] = True
    return P


mark_weekly_five = mark_locks   # old name


# ---------------------------------------------------------------- parlays
PARLAYS = Path("data/parlays.csv")
LEG_COLS = ["season", "week", "slate", "parlay_id", "leg", "player", "team", "opp", "market", "side", "line", "book", "odds",
            "p_side", "lock", "grade", "event_id", "commence_time", "n_legs", "combined_decimal", "combined_prob", "units", "chosen_at"]


def american(dec):
    return int(round((dec - 1) * 100)) if dec >= 2 else int(round(-100 / (dec - 1)))


def choose_parlay(bets, slate):
    """The parlay with the best chance of hitting on one slate day: the highest blended probabilities on the board,
    one per player, never a side the model dislikes. Returns leg rows with parlay-level fields, or None."""
    if bets is None or len(bets) == 0 or "ev" not in bets:
        return None
    b = bets[(bets.slate == slate) & bets.proj.notna() & bets.ev.notna() & (bets.ev >= 0)].copy()
    if b.empty:
        return None
    b["p_side"] = np.where(b.side == "Over", b.model_over, 1 - b.model_over)
    b["dec"] = b.payout + 1
    b = b.sort_values(["p_side", "ev"], ascending=False).drop_duplicates("player")
    lo, hi = C.PARLAY_LEGS
    legs = b[b.p_side >= C.PARLAY_MIN_PROB].head(hi)
    if len(legs) < lo:
        legs = b[b.p_side >= C.PARLAY_FALLBACK_PROB].head(lo)
    if len(legs) < lo:
        return None   # not enough confident legs on this slate yet: no parlay rather than a bad one
    dec, prob = float(legs.dec.prod()), float(legs.p_side.prod())
    edge = dec - 1
    kelly = (prob * edge - (1 - prob)) / edge if edge > 0 else 0.0
    units = float(np.clip(round(C.PARLAY_KELLY_FRACTION * kelly, 1), *C.PARLAY_UNITS)) if kelly > 0 else C.PARLAY_UNITS[0]
    out = legs.assign(leg=range(1, len(legs) + 1), n_legs=len(legs), combined_decimal=dec, combined_prob=prob, units=units)
    return out


def build_parlays(bets, season, week, stamp, now=None):
    """Re-choose the recommended parlay for every slate day whose first game has not kicked off, and keep the
    rest as they were placed. One parlay per slate day, saved to data/parlays.csv."""
    now = now or O._utcnow()
    old = pd.read_csv(PARLAYS) if PARLAYS.exists() else pd.DataFrame(columns=LEG_COLS)
    if bets is None or len(bets) == 0 or "side" not in bets:
        return old
    bets = bets.copy()
    bets["slate"] = slate_of(bets.commence_time)
    snaps = O.load_snapshots(season, week)
    if len(snaps):
        snaps = snaps.assign(slate=slate_of(snaps.commence_time), start=pd.to_datetime(snaps.commence_time, utc=True, errors="coerce"))
    for slate in sorted(s for s in bets.slate.unique() if s):
        if len(snaps) and ((snaps.slate == slate) & (snaps.start <= now)).any():
            continue   # a game on this slate has started: the parlay was placed and stays as it was
        legs = choose_parlay(bets, slate)
        if legs is None:
            continue
        legs = legs.assign(season=season, week=week, slate=slate, parlay_id=f"{season}-wk{week:02d}-{slate}", chosen_at=stamp,
                           odds=np.where(legs.side == "Over", legs.over_odds, legs.under_odds))
        legs = legs[[c for c in LEG_COLS if c in legs.columns]]
        old = old[~((old.season == season) & (old.week == week) & (old.slate == slate))]
        old = pd.concat([old, legs], ignore_index=True)
    PARLAYS.parent.mkdir(parents=True, exist_ok=True)
    old.to_csv(PARLAYS, index=False)
    return old


def grade_parlay_legs(L, stats):
    """Leg results from box-score stats (name_key, season, week -> comb, solo), then one row per parlay."""
    L = L.copy()
    L["name_key"] = L.player.map(norm_name)
    L = L.merge(stats, on=["season", "week", "name_key"], how="left")
    L["actual"] = np.where(L.market.str.contains("solo"), L.solo, L.comb)
    done = L.actual.notna()
    win = np.where(L.side == "Over", L.actual > L.line, L.actual < L.line)
    L["result"] = np.where(~done, "Pending", np.where(L.actual == L.line, "Push", np.where(win, "Win", "Loss")))
    L["dec"] = L.odds.map(lambda a: american_to_decimal(a) if pd.notna(a) else np.nan)
    rows = []
    for pid, legs in L.groupby("parlay_id", sort=False):
        res = legs.result
        result = "Loss" if (res == "Loss").any() else "Pending" if (res == "Pending").any() else "Win"
        live = legs[legs.result != "Push"]
        eff_dec = float(live.dec.prod()) if len(live) else 1.0
        units = float(legs.units.iloc[0])
        won = units * (eff_dec - 1) if result == "Win" else -units if result == "Loss" else 0.0
        first = legs.iloc[0]
        rows.append(dict(parlay_id=pid, season=int(first.season), week=int(first.week), slate=first.slate, n_legs=int(len(legs)),
                         combined_decimal=float(first.combined_decimal), combined_american=american(float(first.combined_decimal)),
                         combined_prob=float(first.combined_prob), units=units, chosen_at=first.chosen_at, result=result, units_won=won,
                         legs=[dict(player=r.player, team=r.team, opp=r.opp, market=r.market, side=r.side, line=float(r.line), book=r.book,
                                    odds=None if pd.isna(r.odds) else float(r.odds), p_side=float(r.p_side), lock=None if pd.isna(r.lock) else float(r.lock),
                                    grade=r.grade, actual=None if pd.isna(r.actual) else float(r.actual), result=r.result,
                                    commence_time=r.commence_time) for r in legs.itertuples()]))
    return pd.DataFrame(rows)


def grade_parlays(pw_comb):
    if not PARLAYS.exists():
        return pd.DataFrame(), {}
    L = pd.read_csv(PARLAYS)
    if L.empty:
        return pd.DataFrame(), {}
    stats = pw_comb.groupby(["season", "week", "name_key"]).agg(comb=("comb", "sum"), solo=("solo_t", "sum")).reset_index()
    P = grade_parlay_legs(L, stats)
    g = P[P.result.isin(["Win", "Loss"])]
    summary = dict(parlays=int(len(P)), wins=int((g.result == "Win").sum()), losses=int((g.result == "Loss").sum()),
                   pending=int((P.result == "Pending").sum()), units=float(g.units_won.sum()) if len(g) else 0.0,
                   staked=float(g.units.sum()) if len(g) else 0.0, hit=float((g.result == "Win").mean()) if len(g) else None)
    return P, summary


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


def write_five_log(P, summary, path, parlays=None):
    """Rewrite the running tally of the weekly five as a markdown file: the record to date, a line per week, and
    every pick with its result. Regenerated by the daily job from data/picks.csv, so it is never edited by hand."""
    import datetime as dt
    f = (summary or {}).get("five") or {}
    weeks = f.get("weeks") or []
    lines = ["# Locks and parlays: running tally", "",
             "The locks: the highest-confidence picks of each slate day (3 on a one-game day, 5 on a multi-game day), named "
             "before kickoff and tracked here. Target: 70% hits. Then the recommended parlay for each slate day.",
             f"Generated {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC by the daily job. Do not edit by hand.", ""]
    if not weeks:
        lines.append("No locks graded yet.")
    hit = f.get("hit")
    if weeks:
        lines += [f"**Locks record: {f.get('wins', 0)}-{f.get('losses', 0)}" + (f"-{f['pushes']}" if f.get("pushes") else "") +
                  (f" ({hit:.0%})" if hit is not None else "") + f", {f.get('units', 0):+.2f} units, {f.get('pending', 0)} pending.**", "",
                  "| Week | Picks | Record | Units | Running record |", "| --- | --- | --- | --- | --- |"]
    for w in weeks:
        rec = f"{w['wins']}-{w['losses']}" + (f"-{w['pushes']}" if w["pushes"] else "") + (f" ({w['pending']} pending)" if w["pending"] else "")
        lines.append(f"| {w['season']} wk {w['week']} | {w['picks']} | {rec} | {w['units']:+.2f} | {w['running_wins']}-{w['running_losses']} |")
    five = P[P.five.fillna(False).astype(bool)] if "five" in P.columns else P.iloc[0:0]
    for (sn, wk), part in (five.groupby(["season", "week"]) if len(five) else []):
        lines += ["", f"## {sn} week {wk}", "", "| Pick | Price | Book | Grade | Lock | Actual | Result |", "| --- | --- | --- | --- | --- | --- | --- |"]
        for r in part.sort_values("lock", ascending=False).itertuples():
            market = "solo" if "solo" in str(r.market) else "tackles + assists"
            price = ("+" if r.odds > 0 else "") + str(int(r.odds)) if pd.notna(r.odds) else ""
            actual = "" if pd.isna(r.actual) else str(int(r.actual))
            lock = "" if pd.isna(getattr(r, "lock", np.nan)) else str(int(round(r.lock)))
            lines.append(f"| {r.player} {r.side} {r.line:g} {market} | {price} | {r.book} | {getattr(r, 'grade', '')} | {lock} | {actual} | {r.result} |")
    ps = (summary or {}).get("parlays") or {}
    lines += ["", "## Parlays", ""]
    if parlays is None or len(parlays) == 0:
        lines.append("No parlays yet.")
    else:
        lines += [f"**Parlays record: {ps.get('wins', 0)}-{ps.get('losses', 0)}, {ps.get('units', 0):+.2f} units on {ps.get('staked', 0):.1f} staked, {ps.get('pending', 0)} pending.**", "",
                  "| Slate | Legs | Odds | Model chance | Stake | Result | Units |", "| --- | --- | --- | --- | --- | --- | --- |"]
        for r in parlays.sort_values(["season", "week", "slate"]).itertuples():
            legs = "; ".join(f"{l['player']} {l['side']} {l['line']:g} ({l['result']})" for l in r.legs)
            lines.append(f"| {r.slate} (wk {r.week}) | {legs} | {'+' if r.combined_american > 0 else ''}{r.combined_american} | {r.combined_prob:.0%} | {r.units:.1f}u | {r.result} | {r.units_won:+.2f} |")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
