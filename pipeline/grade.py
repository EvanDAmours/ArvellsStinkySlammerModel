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
                  "lock", "grade", "consistency", "cons_hits", "cons_n", "payout", "uncertain", "new_role", "reduced_role", "absence", "new_team",
                  "in_role_games", "lock_block", "lock_eligible", "event_id", "commence_time", "pulled_at"]
    new = new[[c for c in cols if c in new.columns]]
    old = pd.read_csv(PICKS) if PICKS.exists() else pd.DataFrame(columns=cols)
    both = pd.concat([old, new], ignore_index=True).drop_duplicates(KEY, keep="first")  # keep the first price we took
    # a pick whose game has not started gets its score, grade and evidence refreshed from the current board
    # (the price we took stays, for closing-line value); the current formula and the latest game logs apply
    start = pd.to_datetime(both.commence_time, utc=True, errors="coerce")
    open_ = both.index[(both.season == season) & (both.week == week) & (start > O._utcnow())]
    fresh = new.set_index(KEY)
    for i in open_:
        k = tuple(both.loc[i, KEY])
        if k in fresh.index:
            for c in ["lock", "grade", "consistency", "cons_hits", "cons_n", "ev", "proj", "proj_model", "mkt_line", "model_over", "market_over", "why"]:
                if c in fresh.columns:
                    both.loc[i, c] = fresh.loc[k, c]
    # a logged pick whose player has vanished from a board that still lists his game (ruled out, inactive, line
    # pulled) can no longer be a lock or a parlay leg: it will void or it is dead money
    board = bets[bets.proj.notna()] if "proj" in bets.columns else bets
    if "event_id" in board.columns and "lock_block" in both.columns:
        events_on_board = set(board.event_id.dropna().astype(str))
        players_on_board = set(zip(board.event_id.astype(str), board.player))
        for i in open_:
            ev, pl = str(both.loc[i, "event_id"]), both.loc[i, "player"]
            if ev in events_on_board and (ev, pl) not in players_on_board:
                lb = "" if pd.isna(both.loc[i, "lock_block"]) else str(both.loc[i, "lock_block"])
                if "off the board" not in lb:
                    both.loc[i, "lock_block"] = (lb + ", " if lb else "") + "off the board"
                    both.loc[i, "lock_eligible"] = False
                    both.loc[i, "five"] = False
    both = mark_locks(both, season, week)
    PICKS.parent.mkdir(parents=True, exist_ok=True)
    both.to_csv(PICKS, index=False)
    return len(both) - len(old)


FIVE = 5
EDMONTON = "America/Edmonton"
try:                                                   # Alberta Time: UTC-6 all year from 2026-11-01; guard against stale zone data
    import datetime as _dt
    from zoneinfo import ZoneInfo as _ZI
    if _dt.datetime(2026, 11, 2, 12, 0, tzinfo=_ZI(EDMONTON)).utcoffset() != _dt.timedelta(hours=-6):
        EDMONTON = _dt.timezone(_dt.timedelta(hours=-6), "Alberta")
except Exception:  # noqa: BLE001
    pass


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
            cand = cand[cand.lock.notna() & (cand.lock >= C.LOCK_MIN_SCORE)]
            cand = cand[~lock_blocked(cand)]
            cand = cand.drop_duplicates("player").head(slots)
            P.loc[cand.index, "five"] = True
    return P


mark_weekly_five = mark_locks   # old name


# ---------------------------------------------------------------- parlays
PARLAYS = Path("data/parlays.csv")
LEG_COLS = ["season", "week", "slate", "parlay_id", "leg", "player", "team", "opp", "market", "side", "line", "book", "odds",
            "p_side", "mkt_side", "lock", "grade", "event_id", "commence_time", "n_legs", "combined_decimal", "combined_prob", "units", "chosen_at"]


def american(dec):
    return int(round((dec - 1) * 100)) if dec >= 2 else int(round(-100 / (dec - 1)))


def choose_parlay(bets, slate):
    """The parlay with the best chance of hitting on one slate day: the highest blended probabilities on the board,
    one per player, never a side the model dislikes. Returns leg rows with parlay-level fields, or None."""
    if bets is None or len(bets) == 0 or "ev" not in bets:
        return None
    b = bets[(bets.slate == slate) & bets.proj.notna() & bets.ev.notna() & (bets.ev >= 0)].copy()
    b = b[~lock_blocked(b)]
    if b.empty:
        return None
    from pipeline.model import claimed_prob
    b["p_side"] = [claimed_prob(x) for x in np.where(b.side == "Over", b.model_over, 1 - b.model_over)]   # the claimed, shrunk chance
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
        old = old[~((old.season == season) & (old.week == week) & (old.slate == slate))]   # open slate: re-chosen from scratch
        legs = choose_parlay(bets, slate)
        if legs is None:
            continue   # the board no longer supports a parlay for this slate: none is shown
        legs = legs.assign(season=season, week=week, slate=slate, parlay_id=f"{season}-wk{week:02d}-{slate}", chosen_at=stamp,
                           odds=np.where(legs.side == "Over", legs.over_odds, legs.under_odds))
        legs = legs[[c for c in LEG_COLS if c in legs.columns]]
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
                                    odds=None if pd.isna(r.odds) else float(r.odds), p_side=float(r.p_side),
                                    mkt_side=None if pd.isna(getattr(r, "mkt_side", np.nan)) else float(r.mkt_side), lock=None if pd.isna(r.lock) else float(r.lock),
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


def lock_blocked(df):
    """Rows that can never be a lock or a parlay leg: the pricer's checklist (`lock_block`), or, for rows priced before
    it existed, the questionable and new-role flags."""
    if df is None or len(df) == 0:
        return pd.Series(False, index=getattr(df, "index", None))
    if "lock_block" in df.columns:
        return df.lock_block.fillna("").astype(str).str.strip().str.len() > 0
    out = pd.Series(False, index=df.index)
    for col in ("uncertain", "new_role"):
        if col in df.columns:
            out |= df[col].map(lambda v: str(v).lower() == "true")
    return out


def record_by(P, col, order=None):
    """Record per value of `col` (side, market): graded picks, with pending counted alongside."""
    if P is None or len(P) == 0 or col not in P.columns or "result" not in P.columns:
        return []
    labels = P[col].fillna("").astype(str)
    out = []
    for v in (order or sorted(labels.unique())):
        allp = P[labels == v]
        if allp.empty:
            continue
        part = allp[allp.result.isin(["Win", "Loss", "Push"])]
        decided = int((part.result != "Push").sum())
        out.append(dict(key=v, bets=int(len(part)), wins=int((part.result == "Win").sum()), losses=int((part.result == "Loss").sum()),
                        pushes=int((part.result == "Push").sum()), pending=int((allp.result == "Pending").sum()),
                        units=float(part.units.sum()) if len(part) else 0.0, roi=float(part.units.mean()) if len(part) else None,
                        hit=float((part.result == "Win").sum() / decided) if decided else None))
    return out


def record_by_grade(P):
    """Record per confidence grade (A, B, C, then any picks logged before grades existed), graded picks only, with
    pending counted alongside. `staked` is the units won at the suggested stake for the grade (GRADE_UNITS)."""
    if P is None or len(P) == 0 or "grade" not in P.columns or "result" not in P.columns:
        return []
    labels = P.grade.fillna("ungraded").replace("", "ungraded").astype(str)
    out = []
    for gr in ["A", "B", "C"] + sorted(set(labels.unique()) - {"A", "B", "C"}):
        allp = P[labels == gr]
        if allp.empty:
            continue
        part = allp[allp.result.isin(["Win", "Loss", "Push"])]
        stake = float(C.GRADE_UNITS.get(gr, 0.0))
        decided = int((part.result != "Push").sum())
        out.append(dict(grade=gr, bets=int(len(part)), wins=int((part.result == "Win").sum()), losses=int((part.result == "Loss").sum()),
                        pushes=int((part.result == "Push").sum()), pending=int((allp.result == "Pending").sum()),
                        units=float(part.units.sum()) if len(part) else 0.0, roi=float(part.units.mean()) if len(part) else None,
                        hit=float((part.result == "Win").sum() / decided) if decided else None,
                        stake=stake, staked=float(part.units.sum() * stake) if len(part) else 0.0))
    return out


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
    # a game that is in the books (the team has stat rows) but the player has none: he did not play, the bet is void
    if "team" in pw_comb.columns and "team" in P.columns:
        teams_done = set(zip(pw_comb.season, pw_comb.week, pw_comb.team))
        game_done = [((s, w, t) in teams_done) or ((s, w, o) in teams_done) for s, w, t, o in zip(P.season, P.week, P.team, P.get("opp", P.team))]
        P["void"] = np.asarray(game_done) & P.actual.isna().values
    else:
        P["void"] = False
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
            prob_gain = np.nan
            if c.line == r.line:
                # same line: did the no-vig price move our way? compare the closing no-vig chance of our side with the
                # no-vig chance when we bet (logged as market_over), falling back to our implied price
                mo = getattr(r, "market_over", np.nan)
                open_side = (mo if r.side == "Over" else 1 - mo) if pd.notna(mo) else 1 / american_to_decimal(r.odds)
                prob_gain = _no_vig_side(c.over_odds, c.under_odds, r.side) - open_side
            clv.append((r.Index, line_move, prob_gain))
    for idx, lm, pg in clv:
        P.loc[idx, "clv_line"] = lm
        P.loc[idx, "clv_prob"] = pg
    # closing-line value: the line moved our way, or the line held and the no-vig price moved our way (0.5 pt tolerance)
    moved = P.clv_line.notna() & ((P.clv_line != 0) | (P.clv_prob.abs() > 0.005))
    P["clv_pos"] = np.where(P.clv_line.notna(), (P.clv_line > 0) | ((P.clv_line == 0) & (P.clv_prob > 0.005)), False)
    P["clv_pos"] = P.clv_pos.astype(bool)
    done = P.actual.notna()
    win = np.where(P.side == "Over", P.actual > P.line, P.actual < P.line)
    push = P.actual == P.line
    P["result"] = np.where(~done, np.where(P.void, "Void", "Pending"), np.where(push, "Push", np.where(win, "Win", "Loss")))
    dec = P.odds.map(lambda a: american_to_decimal(a) if pd.notna(a) else np.nan)
    P["units"] = np.where(P.result == "Win", dec - 1, np.where(P.result == "Loss", -1.0, 0.0))
    g = P[P.result.isin(["Win", "Loss", "Push"])]
    by_grade = record_by_grade(P)
    five = g[g.five.fillna(False).astype(bool)] if "five" in g.columns else g.iloc[0:0]
    five_all = P[P.five.fillna(False).astype(bool)] if "five" in P.columns else P.iloc[0:0]
    weeks, cw, cl = [], 0, 0
    for (sn, wk), part in five_all.groupby(["season", "week"]):
        w, l, pu = int((part.result == "Win").sum()), int((part.result == "Loss").sum()), int((part.result == "Push").sum())
        cw, cl = cw + w, cl + l
        weeks.append(dict(season=int(sn), week=int(wk), picks=int(len(part)), wins=w, losses=l, pushes=pu,
                          pending=int((part.result == "Pending").sum()), units=float(part.units.sum()),
                          running_wins=cw, running_losses=cl))
    P["side_market"] = P.side.fillna("") + " " + np.where(P.market.str.contains("solo"), "solo", "combined")
    summary = dict(by_grade=by_grade, by_side=record_by(P, "side", ["Over", "Under"]),
                   by_side_market=record_by(P, "side_market", ["Over combined", "Over solo", "Under combined", "Under solo"]),
                   five=dict(bets=int(len(five)), wins=int((five.result == "Win").sum()), losses=int((five.result == "Loss").sum()),
                             pushes=int((five.result == "Push").sum()), units=float(five.units.sum()) if len(five) else 0.0,
                             hit=float((five.result == "Win").sum() / max(1, (five.result != "Push").sum())) if len(five) else None,
                             pending=int((five_all.result == "Pending").sum()), weeks=weeks),bets=int(len(g)), wins=int((g.result == "Win").sum()), losses=int((g.result == "Loss").sum()),
                   pushes=int((g.result == "Push").sum()), units=float(g.units.sum()) if len(g) else 0.0,
                   roi=float(g.units.sum() / len(g)) if len(g) else None,
                   avg_clv_line=float(P.clv_line.mean()) if P.clv_line.notna().any() else None,
                   avg_clv_prob=float(P.clv_prob.mean()) if P.clv_prob.notna().any() else None,
                   beat_close_share=float(P.clv_pos[moved].mean()) if moved.any() else None,
                   close_moved=int(moved.sum()), close_known=int(P.clv_line.notna().sum()),
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
