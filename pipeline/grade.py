"""Log picks when they are made, then grade them against official box scores and the closing line."""
from pathlib import Path
import json

import numpy as np
import pandas as pd

import config as C
from pipeline import odds as O
from pipeline.model import american_to_decimal, implied_mean, p_over
from pipeline.sources import norm_name

PICKS = Path("data/picks.csv")
KEY = ["season", "week", "player", "market", "side", "line", "book"]


def size_stakes(bets):
    """Size the slate as one book (config.STAKE, config.ENGINE['rho']). Every pick arrives with its own stake: a quarter of
    Kelly at the cautious chance. Here, per bet (one per player, market and side, taken at the line and book where its own
    stake is largest, so the caps hold whichever of his lines is bet): (1) the picks of one kind (side x market) on one
    slate day rise and fall together, so each stake is divided by 1 + (N - 1) x rho for the N of them; (2) at most
    game_cap units on one game, kind_cap on one kind a slate day and slate_cap on a slate day, the stakes concerned scaled
    down together; (3) nothing falls under the minimum. Every other row of the same bet (another book, another line) is
    scaled by the same factor. `stake_raw` keeps each row's stake before sizing and `slate_n` the N."""
    if bets is None or len(bets) == 0 or "stake" not in bets.columns or "event_id" not in bets.columns:
        return bets
    b = bets.copy()
    c, rho = C.STAKE, C.ENGINE["rho"]
    live = b.pick.isin(["Over", "Under"]) & b.stake.notna()
    b["stake_raw"] = b.stake
    b["slate_n"] = np.nan
    if not live.any():
        return b
    d = b[live].copy()
    d["_e"] = pd.to_numeric(d["edge_low"], errors="coerce").fillna(0.0) if "edge_low" in d.columns else 0.0
    main = d.sort_values(["stake", "_e"], ascending=False).drop_duplicates(["player", "market", "side"])
    slate = slate_of(main.commence_time) if "commence_time" in main.columns else pd.Series("", index=main.index)
    kind = main.side.astype(str) + " " + main.market.map(C.market_kind).astype(str)
    n_kind = main.groupby([slate, kind]).player.transform("size").astype(float)
    st = main.stake.astype(float) / (1 + (n_kind - 1) * rho)
    for keys, cap in ((main.event_id.astype(str), c["game_cap"]), ([slate, kind], c["kind_cap"]), (slate, c["slate_cap"])):
        tot = st.groupby(keys).transform("sum")
        st = st * (cap / tot).clip(upper=1.0)
    st = st.clip(lower=c["min"])
    factor = dict(zip(zip(main.player, main.market, main.side), (st / main.stake.astype(float)).clip(upper=1.0)))
    by_n = dict(zip(zip(main.player, main.market, main.side), n_kind))
    keys_live = [k_ for k_, l_ in zip(zip(b.player, b.market, b.side), live) if l_]
    b.loc[live, "stake"] = np.maximum(c["min"], b.loc[live, "stake_raw"].astype(float).values * np.array([factor.get(k_, 1.0) for k_ in keys_live]))
    b.loc[live, "slate_n"] = [by_n.get(k_) for k_ in keys_live]
    return b


cap_stakes = size_stakes      # old name


def hit_interval(wins, losses, weeks=1):
    """A 95% interval for a hit rate with the week as the unit (MODEL_LOG A3: the picks of one week share a shock, so a
    record is worth fewer bets than it counts): a Wilson interval on the effective count n / (1 + (n / weeks - 1) x rho).
    Returns (low, high), or (None, None) with no decided bet."""
    n = int(wins) + int(losses)
    if n <= 0:
        return None, None
    per_week = n / max(1, int(weeks))
    n_eff = n / (1 + max(0.0, per_week - 1) * C.ENGINE["rho"])
    ph, z = wins / n, 1.96
    den = 1 + z * z / n_eff
    mid, half = (ph + z * z / (2 * n_eff)) / den, z * np.sqrt(ph * (1 - ph) / n_eff + z * z / (4 * n_eff * n_eff)) / den
    return float(max(0.0, mid - half)), float(min(1.0, mid + half))


def _weeks_of(part):
    """Distinct season-weeks among a frame's decided picks."""
    if part is None or len(part) == 0 or "week" not in part.columns:
        return 1
    return max(1, int(part[["season", "week"]].drop_duplicates().shape[0]) if "season" in part.columns else int(part.week.nunique()))


def log_picks(bets, season, week, pulled_at):
    if bets is None or bets.empty or "pick" not in bets:
        return 0
    best = bets.best_price.fillna(False).astype(bool) if "best_price" in bets.columns else pd.Series(True, index=bets.index)
    new = bets[bets.pick.isin(["Over", "Under"]) & best].copy()
    if "commence_time" in new.columns:            # never log a pick on a game that has kicked off (31 week-7 rows were)
        new = new[pd.to_datetime(new.commence_time, utc=True, errors="coerce") > O._utcnow()]
    if new.empty:
        return 0
    new = new.assign(season=season, week=week, pulled_at=pulled_at, side=new.pick,
                     odds=np.where(new.pick == "Over", new.over_odds, new.under_odds))
    cols = KEY + ["player_id", "team", "opp", "group", "odds", "proj", "proj_model", "mkt_line", "mkt_mean", "model_over", "model_over_own", "market_over", "ev", "why", "p_claim", "p_low", "p_model", "claim_ev", "edge_low", "tier", "segment", "segment_adj", "stake", "stake_raw", "slate_n",
                  "lock", "grade", "consistency", "cons_hits", "cons_n", "payout", "uncertain", "new_role", "reduced_role", "absence", "new_team",
                  "in_role_games", "lock_block", "lock_eligible", "press_pg", "fp_comb", "fp_solo", "fp_rel", "phi", "event_id", "commence_time", "pulled_at"]
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
            # market_over is NOT refreshed: it is the no-vig price when we bet, which closing-line value measures from
            for c in ["lock", "grade", "consistency", "cons_hits", "cons_n", "ev", "proj", "proj_model", "mkt_line", "mkt_mean", "model_over", "model_over_own", "why",
                      "p_claim", "p_low", "p_model", "claim_ev", "edge_low", "tier", "segment", "stake", "stake_raw", "slate_n", "lock_block", "lock_eligible", "payout", "phi"]:
                if c in fresh.columns:
                    both.loc[i, c] = fresh.loc[k, c]
    # a logged pick the current board no longer makes (any book, any line) keeps its old grade but can no longer be a
    # lock or a parlay leg (audit 2026-11-09: a pick turned Pass kept its A and its lock)
    still = set(zip(new.player, new.market, new.side))
    if "lock_block" in both.columns:
        for i in open_:
            if (both.loc[i, "player"], both.loc[i, "market"], both.loc[i, "side"]) not in still:
                lb = "" if pd.isna(both.loc[i, "lock_block"]) else str(both.loc[i, "lock_block"])
                if "not a pick at the last pull" not in lb:
                    both.loc[i, "lock_block"] = (lb + ", " if lb else "") + "not a pick at the last pull"
                both.loc[i, "lock_eligible"] = False
                if "five" in both.columns:
                    both.loc[i, "five"] = False
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
            cand = cand[cand.lock.notna() & (cand.lock >= C.LOCK_MIN_SCORE) & cand.market.isin(C.LOCK_MARKETS)]
            if "grade" in cand.columns:       # the claimed-edge gate and the solo-only rule demote the grade, not the score
                cand = cand[cand.grade.astype(str) == "A"]
            cand = cand[~lock_blocked(cand)]
            cand = cand.drop_duplicates("player")
            # no more than LOCKS_PER_SEGMENT of the same kind of pick a day, counting the ones already kept
            seg_count = {}
            for k_ in segment_key(kept).tolist():
                seg_count[k_] = seg_count.get(k_, 0) + 1
            chosen = []
            for i, k_ in zip(cand.index, segment_key(cand).tolist()):
                if len(chosen) >= slots:
                    break
                if seg_count.get(k_, 0) >= C.LOCKS_PER_SEGMENT:
                    continue
                seg_count[k_] = seg_count.get(k_, 0) + 1
                chosen.append(i)
            P.loc[chosen, "five"] = True
    return P


def segment_key(df):
    """The kind of pick, for the per-kind caps: the pricer's segment when it has one, else side x market."""
    if df is None or len(df) == 0:
        return pd.Series([], dtype=str)
    mk = df.market.map(C.market_kind).astype(str)
    base = df.side.astype(str) + " " + mk
    if "segment" in df.columns:
        seg = df.segment.fillna("").astype(str)
        return pd.Series(np.where(seg.str.strip() != "", seg, base), index=df.index)
    return pd.Series(base, index=df.index)


mark_weekly_five = mark_locks   # old name


# ---------------------------------------------------------------- parlays
PARLAYS = Path("data/parlays.csv")
LEG_COLS = ["season", "week", "slate", "parlay_id", "leg", "player", "jersey", "team", "opp", "market", "side", "line", "book", "odds", "link", "sid",
            "p_side", "mkt_side", "lock", "grade", "event_id", "commence_time", "n_legs", "combined_decimal", "combined_prob", "corr_ratio", "same_game", "product_decimal", "units", "chosen_at"]


def american(dec):
    return int(round((dec - 1) * 100)) if dec >= 2 else int(round(-100 / (dec - 1)))


def choose_parlay(bets, slate):
    """The recommended parlay for one slate day: legs that are picks in their own right (the cautious edge at or above
    zero), lock-eligible, one per player, the model's own chance highest first. Returns leg rows with parlay-level
    fields, or None: a slate without two such legs gets no parlay rather than a thin one."""
    if bets is None or len(bets) == 0 or "ev" not in bets:
        return None
    b = bets[(bets.slate == slate) & bets.proj.notna() & bets.pick.isin(["Over", "Under"]) & bets.market.isin(C.PARLAY_MARKETS)].copy()
    b = b[~lock_blocked(b)]
    if b.empty:
        return None
    b["p_side"] = pd.to_numeric(b["p_claim"], errors="coerce")           # the engine's win chance of the leg
    b["_own"] = pd.to_numeric(b["p_model"], errors="coerce") if "p_model" in b.columns else b["p_side"]   # the model's own chance: what ranks a leg
    b["dec"] = b.payout + 1
    b = b[b.p_side.notna() & b.dec.notna()].sort_values(["_own", "ev"], ascending=False).drop_duplicates("player")
    b["_seg"] = segment_key(b)
    lo, hi = C.PARLAY_LEGS

    def take(pool, n):          # best legs, at most PARLAY_LEGS_PER_SEGMENT of a kind
        out, cnt = [], {}
        for i, k_ in zip(pool.index, pool._seg.tolist()):
            if len(out) >= n:
                break
            if cnt.get(k_, 0) >= C.PARLAY_LEGS_PER_SEGMENT:
                continue
            cnt[k_] = cnt.get(k_, 0) + 1; out.append(i)
        return pool.loc[out]
    legs = take(b[b._own >= C.PARLAY_MIN_PROB], hi)
    if len(legs) < lo:
        legs = take(b[b._own >= C.PARLAY_FALLBACK_PROB], lo)
    if len(legs) < lo:
        return None   # not enough legs that are picks on this slate yet: no parlay rather than a bad one
    product, prob = float(legs.dec.prod()), float(legs.p_side.prod())
    # legs on one defence share the plays it faces: the joint chance is not the product (model.parlay_corr_ratio)
    from pipeline.model import parlay_corr_ratio
    corr = parlay_corr_ratio([dict(mu=r.proj, phi=getattr(r, "phi", None), exp_opps=getattr(r, "exp_opps", None), line=r.line, side=r.side, event_id=getattr(r, "event_id", None), team=getattr(r, "team", None)) for r in legs.itertuples()])
    prob = float(min(0.99, prob * corr))
    # two legs in one game: the book prices a same-game parlay itself, under the product of the legs when they rise and
    # fall together. The price recorded is the product divided by our own correlation ratio: an estimate, flagged as one
    # (until 2026-11-09 the product itself was logged, a price no book pays)
    same_game = bool(legs.event_id.astype(str).duplicated().any()) if "event_id" in legs.columns else False
    dec = product / max(1.0, corr) if same_game else product
    edge = dec - 1
    kelly = (prob * edge - (1 - prob)) / edge if edge > 0 else 0.0
    units = float(np.clip(round(C.PARLAY_KELLY_FRACTION * kelly, 1), *C.PARLAY_UNITS)) if kelly > 0 else C.PARLAY_UNITS[0]
    out = legs.drop(columns=["_seg", "_own"]).assign(leg=range(1, len(legs) + 1), n_legs=len(legs), combined_decimal=dec, product_decimal=product, combined_prob=prob, corr_ratio=corr, same_game=same_game, units=units)
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
                           odds=np.where(legs.side == "Over", legs.over_odds, legs.under_odds),
                           link=np.where(legs.side == "Over", legs.get("over_link", pd.Series(None, index=legs.index)), legs.get("under_link", pd.Series(None, index=legs.index))),
                           sid=np.where(legs.side == "Over", legs.get("over_sid", pd.Series(None, index=legs.index)), legs.get("under_sid", pd.Series(None, index=legs.index))))
        legs = legs[[c for c in LEG_COLS if c in legs.columns]]
        old = pd.concat([old, legs], ignore_index=True)
    PARLAYS.parent.mkdir(parents=True, exist_ok=True)
    old.to_csv(PARLAYS, index=False)
    return old


def grade_parlay_legs(L, stats):
    """Leg results from box-score rows (season, week, team, name_key, comb, solo_t), then one row per parlay. A leg whose
    team's game is in the books but whose player has no row did not play: void, priced out of the parlay as books do."""
    L = L.copy()
    L["name_key"] = L.player.map(norm_name)
    L = _merge_stats(L, _with_ast(stats), "")
    L["actual"] = _actual_for(L)
    done = L.actual.notna()
    teams_done = set(zip(stats.season, stats.week, stats.team)) if "team" in stats.columns else set()
    gone = np.array([(not d) and ((s_, w_, t_) in teams_done) for d, s_, w_, t_ in zip(done, L.season, L.week, L.get("team", pd.Series([None] * len(L))))], dtype=bool)
    win = np.where(L.side == "Over", L.actual > L.line, L.actual < L.line)
    L["result"] = np.where(~done, np.where(gone, "Void", "Pending"), np.where(L.actual == L.line, "Push", np.where(win, "Win", "Loss")))
    L["dec"] = L.odds.map(lambda a: american_to_decimal(a) if pd.notna(a) else np.nan)
    rows = []
    for pid, legs in L.groupby("parlay_id", sort=False):
        res = legs.result
        result = "Loss" if (res == "Loss").any() else "Pending" if (res == "Pending").any() else "Win"
        live = legs[~legs.result.isin(["Push", "Void"])]
        eff_dec = float(live.dec.prod()) if len(live) else 1.0
        units = float(legs.units.iloc[0])
        won = units * (eff_dec - 1) if result == "Win" else -units if result == "Loss" else 0.0
        first = legs.iloc[0]
        rows.append(dict(parlay_id=pid, season=int(first.season), week=int(first.week), slate=first.slate, n_legs=int(len(legs)),
                         combined_decimal=float(first.combined_decimal), combined_american=american(float(first.combined_decimal)),
                         combined_prob=float(first.combined_prob), corr_ratio=None if pd.isna(getattr(first, "corr_ratio", np.nan)) else float(first.corr_ratio),
                         same_game=bool(getattr(first, "same_game", False)) if pd.notna(getattr(first, "same_game", np.nan)) else bool(legs.event_id.astype(str).duplicated().any()),
                         units=units, chosen_at=first.chosen_at, result=result, units_won=won,
                         legs=[dict(player=r.player, team=r.team, opp=r.opp, market=r.market, side=r.side, line=float(r.line), book=r.book,
                                    odds=None if pd.isna(r.odds) else float(r.odds), p_side=float(r.p_side),
                                    mkt_side=None if pd.isna(getattr(r, "mkt_side", np.nan)) else float(r.mkt_side), lock=None if pd.isna(r.lock) else float(r.lock),
                                    grade=r.grade, actual=None if pd.isna(r.actual) else float(r.actual), result=r.result,
                                    commence_time=r.commence_time) for r in legs.itertuples()]))
    return pd.DataFrame(rows)


def grade_parlays(pw_comb, live=None):
    pw_comb = _with_ast(pw_comb)
    if live is not None and len(live):        # ESPN finals for games the official stats do not cover yet
        have = set(zip(pw_comb.season, pw_comb.week, pw_comb.name_key))
        extra = _with_ast(live)[[k not in have for k in zip(live.season, live.week, live.name_key)]]
        pw_comb = pd.concat([pw_comb, extra[[c for c in extra.columns if c in pw_comb.columns or c in ("comb", "solo_t", "ast_t")]]], ignore_index=True)
    if not PARLAYS.exists():
        return pd.DataFrame(), {}
    L = pd.read_csv(PARLAYS)
    if L.empty:
        return pd.DataFrame(), {}
    P = grade_parlay_legs(L, pw_comb)
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


def _with_ast(pw_comb):
    """The player-week table with an assists column (combined less solo), for grading the assists market."""
    if pw_comb is None or len(pw_comb) == 0 or "ast_t" in pw_comb.columns:
        return pw_comb
    return pw_comb.assign(ast_t=pw_comb.comb - pw_comb.solo_t)


def _actual_for(df):
    """The box-score number each row's market settles on: solo, assists or combined."""
    kind = df.market.map(C.market_kind)
    ast = df["ast"] if "ast" in df.columns else df["comb"] - df["solo"]
    return pd.Series(np.select([kind == "solo", kind == "assists"], [df["solo"], ast], df["comb"]), index=df.index)


def _no_vig_side(over, under, side):
    if pd.isna(over) or pd.isna(under):
        return np.nan
    po, pu = 1 / american_to_decimal(over), 1 / american_to_decimal(under)
    return (po if side == "Over" else pu) / (po + pu)


def _market_mean(p_over_close, line, phi):
    """The mean of a count with dispersion phi whose chance of clearing `line` is the closing no-vig over price: the
    market's own expectation, read off its closing number (model.implied_mean)."""
    return implied_mean(p_over_close, phi, line)


def no_vig_clv(odds, side, line, close_line, close_over, close_under, phi=1.0):
    """Closing-line value as bettors quote it: the no-vig (fair) closing chance of our side minus the chance implied
    by the price we took (vig included). Positive means the market closed on our side of our price. When the
    close is on a different line, the closing price is carried to our line through the market's own mean (the
    mean that reproduces the closing no-vig chance at the closing line, with the group's dispersion), so a line
    that moved our way counts as value and one that moved against us as its loss."""
    if pd.isna(odds) or pd.isna(close_line) or pd.isna(close_over) or pd.isna(close_under):
        return np.nan
    taken = 1 / american_to_decimal(odds)
    nv_over = _no_vig_side(close_over, close_under, "Over")
    if close_line != line:
        nv_over = p_over(_market_mean(nv_over, close_line, phi), phi, line)
    fair = nv_over if side == "Over" else 1 - nv_over
    return float(fair - taken)


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


SEGMENTS = Path("data/cache/segments.json")


def segment_calibration(P):
    """How the model's claims have resolved for picks like each other: side x market x position, then coarser.
    delta = hit rate minus claimed chance; the pricer applies n/(n+k) of it to the next pick in the segment."""
    c = C.SEGMENT_CAL
    if P is None or len(P) == 0 or "result" not in P.columns:
        return {}, []
    g = P[P.result.isin(["Win", "Loss"])].copy()
    if g.empty:
        return {}, []
    if "group" not in g.columns or g.group.isna().all():
        try:
            pr = pd.read_csv(Path("data/cache/projections.csv"))[["player", "group"]].drop_duplicates("player")
            g = g.drop(columns=[c_ for c_ in ("group",) if c_ in g.columns]).merge(pr, on="player", how="left")
        except (OSError, ValueError):
            g["group"] = ""
    g["group"] = g.group.fillna("").astype(str)
    g["mk"] = g.market.map(C.market_kind)
    mo = pd.to_numeric(g["model_over"], errors="coerce") if "model_over" in g.columns else pd.Series(np.nan, index=g.index)
    p_side = pd.Series(np.where(g.side == "Over", mo, 1 - mo), index=g.index)
    claimed = pd.to_numeric(g["p_claim"], errors="coerce") if "p_claim" in g.columns else pd.Series(np.nan, index=g.index)
    # measured against the claim BEFORE the correction it already carried: p_claim includes the segment adjustment, and
    # the pricer applies the new one to the uncorrected claim, so measuring against p_claim erased a working correction
    if "segment_adj" in g.columns:
        claimed = claimed - pd.to_numeric(g["segment_adj"], errors="coerce").fillna(0.0)
    g["claimed"] = claimed.fillna(0.5 + C.CLAIM_SHRINK * (p_side - 0.5)).fillna(0.5)
    g["hit"] = (g.result == "Win").astype(float)
    # recent weeks weigh more: a pick's weight halves every `half_life_weeks`, so a book that re-prices a market shows
    # in the correction within a couple of weeks instead of after it has been outvoted by the old record
    stamp = pd.to_numeric(g.season, errors="coerce").fillna(0) * 100 + pd.to_numeric(g.week, errors="coerce").fillna(0)
    age = (stamp.max() - stamp).clip(lower=0)
    g["w"] = 0.5 ** (age / float(c.get("half_life_weeks", 3)))
    segs, rows = {}, []
    for keys in (["side", "mk", "group"], ["side", "mk"], ["side"]):
        for vals, part in g.groupby(keys):
            vals = (vals,) if not isinstance(vals, tuple) else vals
            if "group" in keys and vals[-1] == "":        # position unknown: counts in the coarser segments only
                continue
            key = " ".join(str(v) for v in vals if v != "")
            n = int(len(part)); n_eff = float(part.w.sum())
            hit = float((part.hit * part.w).sum() / n_eff); cl = float((part.claimed * part.w).sum() / n_eff)
            w = n_eff / (n_eff + c["k"]); adj = float(np.clip(w * (hit - cl), -c["cap"], c["cap"]))
            segs[key] = dict(n=n, n_eff=n_eff, hit=hit, claimed=cl, delta=hit - cl, adj=adj, wins=int(part.hit.sum()), losses=int(n - part.hit.sum()), units=float(part.units.sum()),
                             hit_raw=float(part.hit.mean()), claimed_raw=float(part.claimed.mean()))
            rows.append(dict(segment=key, level=len(keys), **segs[key]))
    rows.sort(key=lambda r: (r["level"], -r["n"]))
    return segs, rows


def market_watch(pw_comb):
    """How the whole board resolved, week by week and market by market: every closing line (consensus across books)
    against the box score, with the market's own no-vig chance of the over. Shows where the market itself is off."""
    pw_comb = _with_ast(pw_comb)
    out = []
    weeks = sorted({(int(s), int(w)) for s, w in zip(pw_comb.season, pw_comb.week)}) if len(pw_comb) else []
    for s_, w_ in weeks:
        cl = O.closing_lines(s_, w_)
        if cl is None or len(cl) == 0:
            continue
        cl = cl.copy(); cl["name_key"] = cl.player.map(norm_name)
        dec_o = cl.over_odds.map(lambda a: american_to_decimal(a) if pd.notna(a) else np.nan); dec_u = cl.under_odds.map(lambda a: american_to_decimal(a) if pd.notna(a) else np.nan)
        cl["p_over"] = np.where(dec_o.notna() & dec_u.notna(), (1 / dec_o) / (1 / dec_o + 1 / dec_u), np.nan)
        agg = cl.groupby(["event_id", "name_key", "market"]).agg(line=("line", "median"), p_over=("p_over", "mean")).reset_index()
        st = pw_comb[(pw_comb.season == s_) & (pw_comb.week == w_)].groupby("name_key").agg(comb=("comb", "sum"), solo=("solo_t", "sum"), ast=("ast_t", "sum"))
        agg = agg.join(st, on="name_key"); agg["actual"] = _actual_for(agg)
        agg = agg[agg.actual.notna() & (agg.actual != agg.line)]
        if agg.empty:
            continue
        agg["mk"] = agg.market.map(C.market_kind); agg["over"] = (agg.actual > agg.line).astype(float)
        for mk, part in agg.groupby("mk"):
            out.append(dict(season=s_, week=w_, market=mk, lines=int(len(part)), over_rate=float(part.over.mean()), market_p_over=float(part.p_over.mean()) if part.p_over.notna().any() else None))
    return out


def luck_check(P, pw_comb):
    """Luck or skill, week by week: for each segment of graded picks (side, then side x market, then side x market x
    position), the picks' hit rate against the share of EVERY closing line in that segment that resolved the same
    way (the market's base rate that week). lift = hit - base: what our choice of lines added on top of the way the
    whole market went. A week where the whole board went under is not a week the model saw coming."""
    pw_comb = _with_ast(pw_comb)
    if P is None or len(P) == 0 or "result" not in P.columns:
        return []
    g = P[P.result.isin(["Win", "Loss"])].copy()
    if g.empty:
        return []
    if "group" not in g.columns or g.group.isna().any():
        try:
            pr = pd.read_csv(Path("data/cache/projections.csv"))[["player", "group"]].drop_duplicates("player").set_index("player").group
            g["group"] = g.get("group", pd.Series(index=g.index, dtype=object)).fillna(g.player.map(pr))
        except (OSError, KeyError, ValueError):
            g["group"] = g.get("group", "")
    g["mk"] = g.market.map(C.market_kind); g["hit"] = (g.result == "Win").astype(float)
    mo = pd.to_numeric(g["model_over"], errors="coerce") if "model_over" in g.columns else pd.Series(np.nan, index=g.index)
    shrunk = 0.5 + C.CLAIM_SHRINK * (pd.Series(np.where(g.side == "Under", 1 - mo, mo), index=g.index) - 0.5)
    g["claimed"] = pd.to_numeric(g["p_claim"], errors="coerce").fillna(shrunk) if "p_claim" in g.columns else shrunk   # the claim, not the pricer's probability
    if "clv_pos" in g.columns:
        g["clv_pos"] = pd.to_numeric(g.clv_pos.map(lambda v: {True: 1.0, False: 0.0, "True": 1.0, "False": 0.0}.get(v, v)), errors="coerce").astype(float)
        # beat the close among closes that moved: a line and price that held is not a loss to the close
        mv = (pd.to_numeric(g.get("clv_line"), errors="coerce").fillna(0) != 0) | (pd.to_numeric(g.get("clv_prob"), errors="coerce").abs() > 0.005)
        g.loc[~mv.fillna(False).astype(bool), "clv_pos"] = np.nan
    out = []
    for (sn, wk), gw in g.groupby(["season", "week"]):
        cl = O.closing_lines(int(sn), int(wk))
        if cl is None or len(cl) == 0:
            continue
        cl = cl.copy(); cl["name_key"] = cl.player.map(norm_name)
        agg = cl.groupby(["event_id", "name_key", "market"]).agg(line=("line", "median")).reset_index()
        st = pw_comb[(pw_comb.season == sn) & (pw_comb.week == wk)].groupby("name_key").agg(comb=("comb", "sum"), solo=("solo_t", "sum"), ast=("ast_t", "sum"))
        agg = agg.join(st, on="name_key"); agg["actual"] = _actual_for(agg)
        agg = agg[agg.actual.notna() & (agg.actual != agg.line)].copy()
        if agg.empty:
            continue
        agg["mk"] = agg.market.map(C.market_kind); agg["under"] = (agg.actual < agg.line).astype(float)
        if "group" in pw_comb.columns:
            agg["group"] = agg.name_key.map(pw_comb[(pw_comb.season == sn) & (pw_comb.week == wk)].drop_duplicates("name_key").set_index("name_key").group)
        else:
            agg["group"] = agg.name_key.map(gw.drop_duplicates("name_key").set_index("name_key").group)
        for keys in (["side"], ["side", "mk"], ["side", "mk", "group"]):
            for k, part in gw.groupby(keys):
                k = (k,) if not isinstance(k, tuple) else k; sel = dict(zip(keys, k))
                m = agg
                for kk, v in sel.items():
                    if kk != "side":
                        m = m[m[kk] == v]
                if len(m) < 3 or len(part) < 1:
                    continue
                if "mk" not in sel and part.mk.nunique() > 1:
                    # a side-only row: the board's base weighted to the picks' own market mix (solo and combined boards
                    # differed by 15-18 points in weeks 7-8; pooling them credited the market mix as lift)
                    mix = part.mk.value_counts(normalize=True)
                    bases = {k_: float(m[m.mk == k_].under.mean()) for k_ in mix.index if (m.mk == k_).sum() >= 3}
                    u = sum(mix[k_] * v for k_, v in bases.items()) / max(sum(mix[k_] for k_ in bases), 1e-9) if bases else float(m.under.mean())
                else:
                    u = float(m.under.mean())
                base = u if sel["side"] == "Under" else 1 - u
                hit, claimed = float(part.hit.mean()), (float(part.claimed.mean()) if part.claimed.notna().any() else None)
                beat = float(part.clv_pos.dropna().mean()) if "clv_pos" in part and part.clv_pos.notna().any() else None
                lift = hit - base
                verdict = ("we picked badly" if lift < -0.05 else "we picked well" if lift > 0.05 else
                           "the market went our way" if hit >= 0.5 else "nothing added")
                if len(part) < 8:
                    verdict += " (few picks)"
                out.append(dict(season=int(sn), week=int(wk), level=len(keys), segment=" ".join(str(v) for v in k if v), side=sel["side"],
                                picks=int(len(part)), wins=int(part.hit.sum()), hit=hit, claimed=claimed, market_lines=int(len(m)), market_base=base,
                                lift=lift, beat_close=beat, verdict=verdict))
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
        lo, hi = hit_interval(int((part.result == "Win").sum()), int((part.result == "Loss").sum()), _weeks_of(part[part.result != "Push"]))
        out.append(dict(key=v, bets=int(len(part)), wins=int((part.result == "Win").sum()), losses=int((part.result == "Loss").sum()),
                        pushes=int((part.result == "Push").sum()), pending=int((allp.result == "Pending").sum()),
                        units=float(part.units.sum()) if len(part) else 0.0, roi=float(part.units.mean()) if len(part) else None,
                        hit=float((part.result == "Win").sum() / decided) if decided else None, hit_lo=lo, hit_hi=hi))
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
        lo, hi = hit_interval(int((part.result == "Win").sum()), int((part.result == "Loss").sum()), _weeks_of(part[part.result != "Push"]))
        cl = pd.to_numeric(part[part.result != "Push"].p_claim, errors="coerce").dropna() if "p_claim" in part.columns else pd.Series(dtype=float)
        out.append(dict(grade=gr, bets=int(len(part)), wins=int((part.result == "Win").sum()), losses=int((part.result == "Loss").sum()),
                        pushes=int((part.result == "Push").sum()), pending=int((allp.result == "Pending").sum()),
                        units=float(part.units.sum()) if len(part) else 0.0, roi=float(part.units.mean()) if len(part) else None,
                        hit=float((part.result == "Win").sum() / decided) if decided else None, hit_lo=lo, hit_hi=hi,
                        claimed=float(cl.mean()) if len(cl) else None,
                        stake=stake, staked=float(part.units.sum() * stake) if len(part) else 0.0))
    return out


def engine_era(Pc):
    """The record of the weeks the current rules chose (config.ENGINE_LIVE on), by itself. The picks before it were made
    under other rules and say nothing about these, and the rules themselves were chosen on those weeks; the decision
    register's revert conditions are read here. Pc: the counted picks, graded. Always returns the same keys."""
    s0, w0 = C.ENGINE_LIVE["season"], C.ENGINE_LIVE["week"]
    E = Pc[(Pc.season > s0) | ((Pc.season == s0) & (Pc.week >= w0))] if Pc is not None and len(Pc) and "result" in Pc.columns else pd.DataFrame(columns=["season", "week", "result", "units"])
    num = lambda d, c: pd.to_numeric(d[c], errors="coerce") if c in d.columns else pd.Series(np.nan, index=d.index)

    def rec(d):
        g = d[d.result.isin(["Win", "Loss", "Push"])]
        dcd = g[g.result != "Push"]
        w, l = int((g.result == "Win").sum()), int((g.result == "Loss").sum())
        lo, hi = hit_interval(w, l, _weeks_of(dcd))
        st = num(g, "stake").fillna(0.0)
        said, own = num(dcd, "p_claim").dropna(), num(dcd, "p_model").dropna()
        return dict(bets=int(len(g)), wins=w, losses=l, pushes=int((g.result == "Push").sum()), pending=int((d.result == "Pending").sum()),
                    units=float(g.units.sum()) if len(g) else 0.0, staked=float(st.sum()), units_at_stake=float((g.units * st).sum()) if len(g) else 0.0,
                    hit=(w / (w + l) if w + l else None), hit_lo=lo, hit_hi=hi,
                    claimed=float(said.mean()) if len(said) else None, model_said=float(own.mean()) if len(own) else None)

    def buckets(col, edges):
        d = E[E.result.isin(["Win", "Loss"])]
        p = num(d, col)
        out = []
        for lo_, hi_ in zip(edges[:-1], edges[1:]):
            part = d[(p >= lo_) & (p < hi_)]
            if len(part):
                w = int((part.result == "Win").sum())
                lo, hi = hit_interval(w, len(part) - w, _weeks_of(part))
                out.append(dict(bucket=f"{lo_:.0%} to {hi_:.0%}", bets=int(len(part)), said=float(num(part, col).mean()), hit=w / len(part), hit_lo=lo, hit_hi=hi))
        return out

    def watch(rule, name, what, part, of=None, bar=None):
        """A condition of the decision register: how far along it is and where it stands. `running` until `of` decided picks."""
        part = part[part.result.isin(["Win", "Loss"])]
        if of and "commence_time" in part.columns:
            part = part.assign(_t=pd.to_datetime(part.commence_time, utc=True, errors="coerce")).sort_values("_t").head(of)
        r = rec(part)
        n = r["wins"] + r["losses"]
        if (of and n < of) or r["hit"] is None:
            state = "running"
        elif bar is None:
            state = "read it now"
        elif of:                                   # a condition with a count: read on the hit rate once the count is in
            state = "holds" if r["hit"] >= bar else "fails"
        else:                                      # a standing target: only when the likely range is clear of it
            state = "holds" if r["hit_lo"] >= bar else "fails" if r["hit_hi"] < bar else "running"
        return dict(rule=rule, name=name, what=what, n=n, of=of, unit="picks", bar=bar, wins=r["wins"], losses=r["losses"], hit=r["hit"], hit_lo=r["hit_lo"], hit_hi=r["hit_hi"],
                    claimed=r["claimed"], model_said=r["model_said"], state=state, note=None)

    grade = E.grade.fillna("").astype(str) if "grade" in E.columns else pd.Series("", index=E.index)
    kind = E.market.map(C.market_kind) if "market" in E.columns else pd.Series("", index=E.index)
    side = E.side.fillna("").astype(str) if "side" in E.columns else pd.Series("", index=E.index)
    five = E.five.fillna(False).astype(bool) if "five" in E.columns else pd.Series(False, index=E.index)
    out = dict(since=dict(season=int(s0), week=int(w0)), **rec(E))
    out["by_grade"] = record_by_grade(E)
    out["by_side_market"] = record_by(E.assign(side_market=side + " " + kind), "side_market", ["Over combined", "Over solo", "Over assists", "Under combined", "Under solo", "Under assists"]) if len(E) else []
    out["by_group"] = record_by(E, "group", ["DL", "LB", "S", "CB"]) if len(E) else []
    out["by_week"] = [dict(season=int(sn), week=int(wk), **rec(part)) for (sn, wk), part in E.groupby(["season", "week"])] if len(E) else []
    out["calibration"] = buckets("p_claim", [0.0, 0.5, 0.55, 0.6, 0.65, 0.7, 1.01])            # the win chance against what happened
    out["model_calibration"] = buckets("p_model", [0.0, 0.55, 0.6, 0.65, 0.7, 0.8, 1.01])      # the model's own chance (the lock score, the A bar)
    out["locks"] = rec(E[five])
    a_bar = C.ENGINE["a_model"]
    own, el = num(E, "p_model"), num(E, "edge_low")
    old_a = (own >= a_bar) & (el >= C.ENGINE["b_edge_low"])         # what an A was until 2026-11-09: sure on the model's own chance
    flagged = E["why"].astype(str).str.contains("solo share:", regex=False) if "why" in E.columns else pd.Series(False, index=E.index)
    solo_under = (kind == "solo") & (side == "Under")
    out["watches"] = [
        watch("E4", "A picks", "An A is a pick that is also a sleeper on the same side. Read at 30 graded: it stays only if these hit 60% or better and beat the B and C picks.", E[grade == "A"], of=30, bar=0.60),
        watch("E4", "The A rule it replaced", f"Picks with a cautious edge of 2%+ and a model chance of {a_bar:.0%}+, whatever their grade now. Counted beside the new A, so the two rules can be told apart.", E[old_a], of=30),
        watch("E5", "Combined A picks", "A picks and locks go back to solo only if these hit under 55% over their first 20.", E[(grade == "A") & (kind == "combined")], of=20, bar=0.55),
        watch("E6", "Over picks", "Re-read at 40. The candidate is to show Overs as leans only.", E[side == "Over"], of=40),
        watch("E5", "Locks", "The target is 70% over the season.", E[five], bar=0.70),
        # the book-share flag (config.HOLES, open issue 15): the card's "solo share:" clause, in no grade until it is read here
        watch("H1", "Solo Under picks on a flagged line", f"The book's solo line is {C.HOLES['book_share']:.0%} or more of its own combined line. Replayed on weeks 4 to 9 these went 63-25 and the unflagged ones 48-54. Read after week 13: at 58% or better here and ahead of the unflagged, the flag becomes an input to the A grade.", E[solo_under & flagged], of=30, bar=0.58),
        watch("H1", "Solo Under picks on an unflagged line", "The other half of the same test.", E[solo_under & ~flagged], of=30),
        watch("H1", "Solo Over picks on a flagged line", "Replayed on weeks 4 to 9: 3-10. Read at 15: under 45%, the Over is no pick on a flagged line.", E[(kind == "solo") & (side == "Over") & flagged], of=15),
    ]
    return out


def _phantom(P):
    """True for a pick whose (book, market, player, line) was not on its game's board when it was logged: the game's
    latest pull at or before the pick's stamp is the board it was priced from."""
    out = np.zeros(len(P), dtype=bool)
    for (s_, w_), idx in P.groupby(["season", "week"]).groups.items():
        snaps = O.load_snapshots(int(s_), int(w_))
        if snaps is None or len(snaps) == 0 or "pulled_at" not in snaps.columns:
            continue
        snaps = snaps.assign(pulled_at=snaps.pulled_at.astype(str), event_id=snaps.event_id.astype(str))
        stamps = snaps.groupby("event_id").pulled_at.apply(lambda x: sorted(set(x))).to_dict()
        have = set(zip(snaps.event_id, snaps.pulled_at, snaps.book, snaps.market, snaps.player, snaps.line.astype(float)))
        for i in idx:
            r = P.loc[i]
            ev, t = str(r.get("event_id")), str(r.get("pulled_at"))
            prior = [x for x in stamps.get(ev, []) if x <= t]
            if not prior:
                continue                                  # no snapshot to judge by: leave it
            out[P.index.get_loc(i)] = (ev, prior[-1], r.book, r.market, r.player, float(r.line)) not in have
    return out


SETTLED = Path("data/settled.csv")
SETTLED_COLS = KEY + ["actual", "graded_by", "settled_at"]


def _freeze_settlement(P):
    """A bet settles once. The first box score that grades a pick (ESPN's final when the game ends, else the official
    stats) is written to data/settled.csv and used from then on: a book pays on the count at the final whistle and does
    not reopen a bet for a later stat correction, so the record must not move either. A later official number that
    differs is counted (`corrected`), never applied; the model itself always trains on the official stats. To undo a
    wrong settlement, delete its row from the file. Returns the frame with `actual` and `graded_by` as settled."""
    import datetime as dt
    norm = lambda r: (int(r[0]), int(r[1]), str(r[2]), str(r[3]), str(r[4]), round(float(r[5]), 2), str(r[6]))
    try:
        old = pd.read_csv(SETTLED) if SETTLED.exists() else pd.DataFrame(columns=SETTLED_COLS)
    except (OSError, ValueError):
        old = pd.DataFrame(columns=SETTLED_COLS)
    store = {norm(r[:7]): (float(r[7]), r[8]) for r in old[SETTLED_COLS[:9]].itertuples(index=False)} if len(old) else {}
    P = P.copy()
    P["corrected"] = False
    new, stamp = [], dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for i, r in zip(P.index, P[KEY].itertuples(index=False)):
        try:
            k_ = norm(r)
        except (TypeError, ValueError):
            continue
        a = P.at[i, "actual"]
        if k_ in store:
            kept, by = store[k_]
            if pd.notna(a) and float(a) != kept:
                P.at[i, "corrected"] = True
            P.at[i, "actual"], P.at[i, "graded_by"] = kept, by
        elif pd.notna(a):
            store[k_] = (float(a), P.at[i, "graded_by"])
            new.append(dict(zip(KEY, r), actual=float(a), graded_by=P.at[i, "graded_by"], settled_at=stamp))
    if new:
        try:
            SETTLED.parent.mkdir(parents=True, exist_ok=True)
            pd.concat([old, pd.DataFrame(new)], ignore_index=True)[SETTLED_COLS].to_csv(SETTLED, index=False)
        except OSError:
            pass
    return P


def _merge_stats(P, pw, suffix=""):
    """Box-score totals onto picks by season, week, TEAM and name: two players can share a name key (week 7: the Byron
    Murphys of MIN and SEA, the Byron Youngs of LA and PHI were summed). A pick without a team match falls back to the
    name alone only when one player has that name that week. Adds comb/solo/ast + suffix."""
    keyN = ["season", "week", "name_key"]
    agg = dict(comb=("comb", "sum"), solo=("solo_t", "sum"), ast=("ast_t", "sum"))
    out = {k: k + suffix for k in ("comb", "solo", "ast")}
    if "team" in pw.columns and "team" in P.columns:
        byT = pw.groupby(keyN + ["team"]).agg(**agg).reset_index().rename(columns=out)
        P = P.merge(byT, on=keyN + ["team"], how="left")
        byN = pw.groupby(keyN).agg(**agg, _teams=("team", "nunique")).reset_index()
        byN = byN[byN._teams == 1].drop(columns="_teams").rename(columns={k: v + "_n" for k, v in out.items()})
        P = P.merge(byN, on=keyN, how="left")
        for k, v in out.items():
            P[v] = P[v].where(P[v].notna(), P[v + "_n"])
        return P.drop(columns=[v + "_n" for v in out.values()])
    return P.merge(pw.groupby(keyN).agg(**agg).reset_index().rename(columns=out), on=keyN, how="left")


def grade(pw_comb, live=None):
    """pw_comb: player-week rows with name_key, season, week, comb, solo_t (official formula applied).
    live: ESPN final box-score rows (pipeline/live_grade.py) for games the official stats do not cover yet; they
    settle a pick only where the official stats have nothing, and only for a player listed in that box score."""
    pw_comb = _with_ast(pw_comb)
    if not PICKS.exists():
        return pd.DataFrame(), {}
    P = pd.read_csv(PICKS)
    if P.empty:
        return P, {}
    P["name_key"] = P.player.map(norm_name)
    P = _merge_stats(P, pw_comb, "")
    # picks logged with the league player id (since 2026-11-03) grade on it, so a duplicate name or a book's spelling
    # cannot grade the wrong man; the name match stays for older picks
    if "player_id" in P.columns and "player_id" in pw_comb.columns and P.player_id.notna().any():
        sid = pw_comb[pw_comb.player_id.notna()].assign(player_id=lambda d: d.player_id.astype(str)).groupby(["season", "week", "player_id"]).agg(
            comb_id=("comb", "sum"), solo_id=("solo_t", "sum"), ast_id=("ast_t", "sum")).reset_index()
        P["player_id"] = P.player_id.where(P.player_id.notna(), None).astype(object)
        P = P.merge(sid, on=["season", "week", "player_id"], how="left")
        for c in ("comb", "solo", "ast"):
            P[c] = P[f"{c}_id"].where(P[f"{c}_id"].notna(), P[c])
        P = P.drop(columns=["comb_id", "solo_id", "ast_id"])
    P["actual"] = _actual_for(P)
    P["graded_by"] = np.where(P.actual.notna(), "official", None)
    if live is not None and len(live):
        P = _merge_stats(P, _with_ast(live), "_l")
        fill = P.actual.isna() & P.comb_l.notna()
        for c in ("comb", "solo", "ast"):
            P.loc[fill, c] = P.loc[fill, f"{c}_l"]
        P.loc[fill, "actual"] = _actual_for(P[fill])
        P.loc[fill, "graded_by"] = "live"
        P = P.drop(columns=["comb_l", "solo_l", "ast_l"])
    P = _freeze_settlement(P)          # a bet settles once, on the first box score that grades it
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
                clv.append((r.Index, np.nan, np.nan, np.nan))
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
            phi = getattr(r, "phi", np.nan)                # the pricer's own spread for this market, when the pick logged it
            phi = float(phi) if pd.notna(phi) else C.DEFAULT_PHI.get(str(getattr(r, "group", "")), 1.0)
            clv.append((r.Index, line_move, prob_gain, no_vig_clv(r.odds, r.side, r.line, c.line, c.over_odds, c.under_odds, phi)))
    for idx, lm, pg, nv in clv:
        P.loc[idx, "clv_line"] = lm
        P.loc[idx, "clv_prob"] = pg
        P.loc[idx, "clv_novig"] = nv
    for col in ("clv_line", "clv_prob", "clv_novig"):
        if col not in P.columns:
            P[col] = np.nan
    # closing-line value: the line moved our way, or the line held and the no-vig price moved our way (0.5 pt tolerance)
    moved = P.clv_line.notna() & ((P.clv_line != 0) | (P.clv_prob.abs() > 0.005))
    P["clv_pos"] = np.where(P.clv_line.notna(), (P.clv_line > 0) | ((P.clv_line == 0) & (P.clv_prob > 0.005)), False)
    P["clv_pos"] = P.clv_pos.astype(bool)
    done = P.actual.notna()
    win = np.where(P.side == "Over", P.actual > P.line, P.actual < P.line)
    push = P.actual == P.line
    P["result"] = np.where(~done, np.where(P.void, "Void", "Pending"), np.where(push, "Push", np.where(win, "Win", "Loss")))
    # a pick logged at or after its kickoff was never a pre-game pick (31 week-7 rows, from a pull before the board
    # dropped started games): void, out of every record
    t_pick = pd.to_datetime(P.pulled_at.astype(str), format="%Y%m%dT%H%M%SZ", utc=True, errors="coerce")
    late = (t_pick >= pd.to_datetime(P.commence_time, utc=True, errors="coerce")).fillna(False).values
    P.loc[late, "result"] = "Void"
    P["late"] = late
    # a pick logged on a line its game's board was not offering at that moment (the old latest_lines kept every line ever
    # seen; 21 rows, 4 A grades, a lock among them) was never a bet anyone could place: void, out of every record
    P["phantom"] = _phantom(P)
    P.loc[P.phantom.values, "result"] = "Void"
    late = late | P.phantom.values
    dec = P.odds.map(lambda a: american_to_decimal(a) if pd.notna(a) else np.nan)
    P["units"] = np.where(P.result == "Win", dec - 1, np.where(P.result == "Loss", -1.0, 0.0))
    # one bet per player, market and side: the same pick logged at two books or two lines is one bet in every record and
    # in the calibration (617 graded rows were 422 bets). The row kept: the lock if there is one, else the first logged.
    order = P.assign(_five=(P.five.fillna(False).astype(bool) if "five" in P.columns else False), _t=t_pick).sort_values(["_five", "_t"], ascending=[False, True])
    keep_idx = order[~order.late].drop_duplicates(["season", "week", "player", "market", "side"]).index
    P["counted"] = P.index.isin(keep_idx)
    Pc = P[P.counted]
    g = Pc[Pc.result.isin(["Win", "Loss", "Push"])]
    by_grade = record_by_grade(Pc)
    five = g[g.five.fillna(False).astype(bool)] if "five" in g.columns else g.iloc[0:0]
    five_all = Pc[Pc.five.fillna(False).astype(bool)] if "five" in Pc.columns else Pc.iloc[0:0]
    weeks, cw, cl = [], 0, 0
    for (sn, wk), part in five_all.groupby(["season", "week"]):
        w, l, pu = int((part.result == "Win").sum()), int((part.result == "Loss").sum()), int((part.result == "Push").sum())
        cw, cl = cw + w, cl + l
        weeks.append(dict(season=int(sn), week=int(wk), picks=int(len(part)), wins=w, losses=l, pushes=pu,
                          pending=int((part.result == "Pending").sum()), units=float(part.units.sum()),
                          running_wins=cw, running_losses=cl))
    P["side_market"] = P.side.fillna("") + " " + P.market.map(C.market_kind)
    Pc = P[P.counted]
    segs, seg_rows = segment_calibration(Pc)
    try:
        SEGMENTS.parent.mkdir(parents=True, exist_ok=True)
        SEGMENTS.write_text(json.dumps(segs, indent=1))
    except OSError:
        pass
    try:
        watch = market_watch(pw_comb)
    except Exception:  # noqa: BLE001
        watch = []
    try:
        luck = luck_check(Pc, pw_comb)
    except Exception as e:  # noqa: BLE001
        print(f"grade: luck check skipped ({type(e).__name__}: {e})"); luck = []
    mvc = moved[P.counted.values] if hasattr(moved, "values") else moved
    summary = dict(by_grade=by_grade, by_side=record_by(Pc, "side", ["Over", "Under"]), segments=seg_rows, market_watch=watch, luck=luck,
                   by_side_market=record_by(Pc, "side_market", ["Over combined", "Over solo", "Over assists", "Under combined", "Under solo", "Under assists"]),
                   rows_logged=int(len(P)), bets_counted=int(P.counted.sum()), late_voided=int(P.late.sum()),
                   stat_corrections=int(P.corrected.sum()) if "corrected" in P.columns else 0,
                   hit_lo=hit_interval(int((g.result == "Win").sum()), int((g.result == "Loss").sum()), _weeks_of(g[g.result != "Push"]))[0],
                   hit_hi=hit_interval(int((g.result == "Win").sum()), int((g.result == "Loss").sum()), _weeks_of(g[g.result != "Push"]))[1],
                   clv_novig_se=_cluster_se(Pc[Pc.clv_novig.notna()], "clv_novig"),
                   five=dict(bets=int(len(five)), wins=int((five.result == "Win").sum()), losses=int((five.result == "Loss").sum()),
                             hit_lo=hit_interval(int((five.result == "Win").sum()), int((five.result == "Loss").sum()), _weeks_of(five[five.result != "Push"]))[0],
                             hit_hi=hit_interval(int((five.result == "Win").sum()), int((five.result == "Loss").sum()), _weeks_of(five[five.result != "Push"]))[1],
                             pushes=int((five.result == "Push").sum()), units=float(five.units.sum()) if len(five) else 0.0,
                             hit=float((five.result == "Win").sum() / max(1, (five.result != "Push").sum())) if len(five) else None,
                             pending=int((five_all.result == "Pending").sum()), weeks=weeks),bets=int(len(g)), wins=int((g.result == "Win").sum()), losses=int((g.result == "Loss").sum()),
                   pushes=int((g.result == "Push").sum()), units=float(g.units.sum()) if len(g) else 0.0,
                   roi=float(g.units.sum() / len(g)) if len(g) else None,
                   avg_clv_line=float(Pc.clv_line.mean()) if Pc.clv_line.notna().any() else None,
                   avg_clv_prob=float(Pc.clv_prob.mean()) if Pc.clv_prob.notna().any() else None,
                   avg_clv_novig=float(Pc.clv_novig.mean()) if Pc.clv_novig.notna().any() else None,
                   clv_novig_n=int(Pc.clv_novig.notna().sum()), clv_held=int((Pc.clv_line == 0).sum()),
                   beat_close_share=float(Pc.clv_pos[mvc].mean()) if mvc.any() else None,
                   close_moved=int(mvc.sum()), close_known=int(Pc.clv_line.notna().sum()),
                   pending=int((Pc.result == "Pending").sum()))
    try:
        summary["era"] = engine_era(Pc)        # the weeks the current rules chose, by themselves
    except Exception as e:  # noqa: BLE001
        print(f"grade: the engine-era record was skipped ({type(e).__name__}: {e})"); summary["era"] = None
    return P.drop(columns=["name_key"]), summary


def _cluster_se(d, col):
    """Standard error of a mean with season-weeks as the unit (None with fewer than two weeks)."""
    if d is None or len(d) == 0 or col not in d.columns:
        return None
    grp = d.groupby(["season", "week"])[col].agg(["sum", "size"])
    if len(grp) < 2:
        return None
    m = grp["sum"].sum() / grp["size"].sum()
    return float(np.sqrt(((grp["sum"] - m * grp["size"]) ** 2).sum()) / grp["size"].sum() * np.sqrt(len(grp) / (len(grp) - 1)))


def write_five_log(P, summary, path, parlays=None):
    """Rewrite the running tally of the weekly five as a markdown file: the record to date, a line per week, and
    every pick with its result. Regenerated by the daily job from data/picks.csv, so it is never edited by hand."""
    import datetime as dt
    f = (summary or {}).get("five") or {}
    weeks = f.get("weeks") or []
    luck = [r for r in ((summary or {}).get("luck") or []) if r.get("level") == 1]
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
            market = {"solo": "solo", "assists": "assists"}.get(C.market_kind(r.market), "tackles + assists")
            price = ("+" if r.odds > 0 else "") + str(int(r.odds)) if pd.notna(r.odds) else ""
            actual = "" if pd.isna(r.actual) else str(int(r.actual))
            lock = "" if pd.isna(getattr(r, "lock", np.nan)) else str(int(round(r.lock)))
            lines.append(f"| {r.player} {r.side} {r.line:g} {market} | {price} | {r.book} | {getattr(r, 'grade', '')} | {lock} | {actual} | {r.result} |")
    ps = (summary or {}).get("parlays") or {}
    if luck:
        lines += ["", "## Luck or skill, week by week", "", "All plays by side: our hit rate against the share of every closing line on the board that resolved the same way. Lift is what our choice of lines added; a week the whole board went our way is not a week the model saw coming.", "",
                  "| Week | Side | Picks | Hit | Claimed | Whole market | Lift | Beat the close | Verdict |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for r in luck:
            lines.append(f"| {r['season']} wk {r['week']} | {r['side']} | {r['picks']} | {r['hit']:.0%} | {'' if r.get('claimed') is None else f"{r['claimed']:.0%}"} | {r['market_base']:.0%} of {r['market_lines']} lines | {r['lift']:+.0%} | {'' if r.get('beat_close') is None else f"{r['beat_close']:.0%}"} | {r['verdict']} |")
    lines += ["", "## Parlays", ""]
    if parlays is None or len(parlays) == 0:
        lines.append("No parlays yet.")
    else:
        lines += [f"**Parlays record: {ps.get('wins', 0)}-{ps.get('losses', 0)}, {ps.get('units', 0):+.2f} units on {ps.get('staked', 0):.1f} staked, {ps.get('pending', 0)} pending.**", "",
                  "| Slate | Legs | Odds | Model chance | Stake | Result | Units |", "| --- | --- | --- | --- | --- | --- | --- |"]
        for r in parlays.sort_values(["season", "week", "slate"]).itertuples():
            legs = "; ".join(f"{l['player']} {l['side']} {l['line']:g} ({l['result']})" for l in r.legs)
            lines.append(f"| {r.slate} (wk {r.week}) | {legs} | {'+' if r.combined_american > 0 else ''}{r.combined_american} | {r.combined_prob:.0%} | {r.units:.1f}u | {r.result} | {r.units_won:+.2f} |")
    lines += _evidence_sections(summary or {})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def _evidence_sections(summary):
    """The evidence a post-mortem starts from, in plain text (the site's copy is sealed): the scoreboard against the
    market with the weeks since the engine apart, the candidates in the shadow, the record of the engine's own weeks with
    the decision register's conditions, and the record to date. Every record carries its likely range."""
    pct = lambda x: "" if x is None else f"{x:.0%}"
    rng = lambda lo, hi: "" if lo is None or hi is None else f"{lo:.0%} to {hi:.0%}"
    sgn = lambda x, nd=4: "" if x is None else f"{x:+.{nd}f}"
    rec = lambda r: f"{r.get('wins', 0)}-{r.get('losses', 0)}" + (f"-{r['pushes']}" if r.get("pushes") else "") + (f" ({r['pending']} pending)" if r.get("pending") else "")
    margin = lambda m, se, t: sgn(m) + ("" if se is None else f" (give or take {se:.4f}" + ("" if t is None else f"; t {t:+.1f}") + ")")
    live = C.ENGINE_LIVE
    out = []
    sb = summary.get("scoreboard") or {}
    out += ["", "## Against the market (every logged closing line)", "",
            "The chance each gives the Over on every line the model had a number for, picked or not, scored by log-loss against what happened (lower is better). "
            "The closing price is the last pull before kickoff. The engine's weight was chosen on the weeks before "
            f"{live['season']} week {live['week']}: only the weeks from there on test it.", ""]
    if not sb:
        out.append("No graded closing lines yet.")
    else:
        ll = sb["log_loss"]
        out += ["| Weeks | Lines | Book | Model alone | Engine | Engine better than the book by |", "| --- | --- | --- | --- | --- | --- |"]
        for w in sb.get("by_week") or []:
            out.append(f"| wk {w['week']}{'' if w['week'] >= sb.get('live_week', live['week']) else ' (in-sample)'} | {w['lines']} | {w['market']:.4f} | {w['model']:.4f} | {w['engine']:.4f} | {sgn(w['engine_minus_market'])} |")
        out.append(f"| All weeks | {sb['lines']} | {ll['market']:.4f} | {ll['model']:.4f} | {ll['engine']:.4f} | {margin(sb.get('engine_minus_market'), sb.get('se'), sb.get('t'))} |")
        sn = sb.get("since")
        if sn:
            out.append(f"| **Since week {sn['from_week']} (out of sample)** | {sn['lines']} | {sn['log_loss']['market']:.4f} | {sn['log_loss']['model']:.4f} | {sn['log_loss']['engine']:.4f} | **{margin(sn.get('engine_minus_market'), sn.get('se'), sn.get('t'))}** |")
        else:
            out.append(f"| **Since week {sb.get('live_week', live['week'])} (out of sample)** | 0 | | | | no graded line yet |")
        kinds = sb.get("by_kind") or {}
        if kinds:
            out += ["", "By market, all weeks: " + "; ".join(f"{k} {margin(v.get('engine_minus_market'), v.get('se'), None)} on {v['lines']} lines" for k, v in kinds.items()) + "."]
        if sn and sn.get("by_kind"):
            out += [f"By market, since week {sn['from_week']}: " + "; ".join(f"{k} {margin(v.get('engine_minus_market'), v.get('se'), None)} on {v['lines']} lines" for k, v in sn["by_kind"].items()) + "."]
        tiers = [t for t in sb.get("tiers") or [] if t.get("lines")]
        if tiers:
            out += ["", "The engine's side on every line at the best closing price, by tier (all weeks):", "",
                    "| Tier | Lines | Record | Hit | Likely range | Chance said | Return a bet |", "| --- | --- | --- | --- | --- | --- | --- |"]
            out += [f"| {t['tier']} | {t['lines']} | {t['wins']}-{t['losses']} | {pct(t['hit'])} | {rng(t.get('hit_lo'), t.get('hit_hi'))} | {pct(t.get('chance'))} | {t['ret']:+.1%} |" for t in tiers]
        cal = sb.get("calibration") or []
        if cal:
            out += ["", "Calibration of the engine's chance (its side on every line, all weeks): " + "; ".join(f"said {c['said']:.0%}, hit {c['hit']:.0%} ({c['lines']})" for c in cal) + "."]
        sh = sb.get("shadow") or []
        if sh:
            out += ["", "### Candidates in the shadow", "",
                    f"Scored on the same lines and never used for a pick. Their numbers were fixed on 2026-11-09 (config.SHADOW); each is decided after {C.FROZEN_UNTIL} on the weeks "
                    f"from week {sb.get('live_week', live['week'])} on. Positive: the candidate was a better forecast than the engine.", "",
                    "| Candidate | Log-loss | Against the engine, all weeks (in-sample included) | Since the engine, out of sample |", "| --- | --- | --- | --- |"]
            for r in sh:
                so = r.get("since")
                out.append(f"| {r['name']} | {r['log_loss']:.4f} | {margin(r.get('vs_engine'), r.get('se'), r.get('t'))} | "
                           + (f"{margin(so.get('vs_engine'), so.get('se'), so.get('t'))} on {so['lines']} lines, {so['weeks']} week(s)" if so else "no graded line yet") + " |")
    mw = summary.get("market_watch") or []
    if mw:
        out += ["", "### The whole board, no model", "",
                "Every closing line of the week: how often the Over won, against the chance the book's fair price gave it. A gap here is the level of the whole market that week; no choice of lines explains it, and a side that won because of it was not picked by skill.", "",
                "| Week | Market | Lines | Over won | Book's fair chance of the Over |", "| --- | --- | --- | --- | --- |"]
        out += [f"| {r['season']} wk {r['week']} | {C.market_kind(r['market'])} | {r['lines']} | {pct(r.get('over_rate'))} | {pct(r.get('market_p_over'))} |" for r in mw]
    era = summary.get("era") or {}
    out += ["", f"## Since the engine ({live['season']} week {live['week']} on)", "",
            "The picks the current rules chose, one bet per player, market and side. The decision register's conditions are read on these alone.", ""]
    if not era or not (era.get("bets") or era.get("pending")):
        out.append("No pick graded yet.")
    else:
        out += [f"**Record {rec(era)}" + (f" ({pct(era['hit'])}, likely range {rng(era.get('hit_lo'), era.get('hit_hi'))})" if era.get("hit") is not None else "")
                + f", {era.get('units', 0):+.2f} units at 1 a bet, {era.get('units_at_stake', 0):+.2f} on {era.get('staked', 0):.1f} units at the stakes"
                + (f"; win chance said {pct(era.get('claimed'))}" if era.get("claimed") is not None else "") + ".**",
                f"Locks: {rec(era.get('locks') or {})}" + (f" ({pct(era['locks']['hit'])}, likely range {rng(era['locks'].get('hit_lo'), era['locks'].get('hit_hi'))})" if (era.get("locks") or {}).get("hit") is not None else "") + ".", "",
                "| Week | Record | Hit | Win chance said | Units at 1 a bet | Staked | Units at the stakes |", "| --- | --- | --- | --- | --- | --- | --- |"]
        out += [f"| {w['season']} wk {w['week']} | {rec(w)} | {pct(w['hit'])} | {pct(w.get('claimed'))} | {w['units']:+.2f} | {w['staked']:.1f} | {w['units_at_stake']:+.2f} |" for w in era.get("by_week") or []]
        out += ["", "| Grade | Record | Hit | Likely range | Win chance said | Units at 1 a bet |", "| --- | --- | --- | --- | --- | --- |"]
        out += [f"| {g['grade']} | {rec(g)} | {pct(g['hit'])} | {rng(g.get('hit_lo'), g.get('hit_hi'))} | {pct(g.get('claimed'))} | {g['units']:+.2f} |" for g in era.get("by_grade") or []]
        for title, key in (("Side and market", "by_side_market"), ("Position", "by_group")):
            rows = era.get(key) or []
            if rows:
                out += ["", f"| {title} | Record | Hit | Likely range | Units at 1 a bet |", "| --- | --- | --- | --- | --- |"]
                out += [f"| {r['key']} | {rec(r)} | {pct(r['hit'])} | {rng(r.get('hit_lo'), r.get('hit_hi'))} | {r['units']:+.2f} |" for r in rows]
        for title, key in (("Calibration of the win chance", "calibration"), ("Calibration of the model's own chance (the lock score and the A bar)", "model_calibration")):
            rows = era.get(key) or []
            if rows:
                out += ["", f"{title}: " + "; ".join(f"{c['bucket']}: said {c['said']:.0%}, hit {c['hit']:.0%} of {c['bets']} ({rng(c.get('hit_lo'), c.get('hit_hi'))})" for c in rows) + "."]
    watches = (era.get("watches") or []) + (sb.get("watches") or [])
    if watches:
        out += ["", "Conditions of the decision register on trial:", "", "| Rule | Condition | So far | Record | Hit | Likely range | Model said | State |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        out += [f"| {w['rule']} {w.get('name', '')} | {w['what']} | {w['n']}" + (f" of {w['of']}" if w.get("of") else "") + f" {w.get('unit', 'picks')} | "
                + (f"{w['wins']}-{w['losses']}" if w.get("wins") is not None else "") + f" | {pct(w.get('hit'))} | {rng(w.get('hit_lo'), w.get('hit_hi'))} | {pct(w.get('model_said'))} | {w['state']}" + (f": {w['note']}" if w.get("note") else "") + " |" for w in watches]
    if summary.get("bets") or summary.get("pending"):
        hit = summary["wins"] / max(1, summary["wins"] + summary["losses"]) if summary.get("wins") is not None else None
        se = summary.get("clv_novig_se")
        out += ["", "## All plays to date (every rule set)", "",
                f"**Record {rec(summary)} ({pct(hit)}, likely range {rng(summary.get('hit_lo'), summary.get('hit_hi'))}), {summary.get('units', 0):+.2f} units at 1 a bet.**"
                + ("" if summary.get("avg_clv_novig") is None else f" No-vig closing-line value {summary['avg_clv_novig'] * 100:+.2f} points" + ("" if se is None else f" (give or take {se * 100:.2f})") + f" on {summary.get('clv_novig_n', 0)} bets.")
                + (f" Later stat corrections counted and not applied: {summary['stat_corrections']}." if summary.get("stat_corrections") else ""), "",
                "| Grade | Record | Hit | Likely range | Chance said | Units at 1 a bet |", "| --- | --- | --- | --- | --- | --- |"]
        out += [f"| {g['grade']} | {rec(g)} | {pct(g['hit'])} | {rng(g.get('hit_lo'), g.get('hit_hi'))} | {pct(g.get('claimed'))} | {g['units']:+.2f} |" for g in summary.get("by_grade") or []]
        rows = summary.get("by_side_market") or []
        if rows:
            out += ["", "| Side and market | Record | Hit | Likely range | Units at 1 a bet |", "| --- | --- | --- | --- | --- |"]
            out += [f"| {r['key']} | {rec(r)} | {pct(r['hit'])} | {rng(r.get('hit_lo'), r.get('hit_hi'))} | {r['units']:+.2f} |" for r in rows]
    return out


# ---------------------------------------------------------------- sleepers (config.SLEEPER), tracked on their own record
SLEEPERS = Path("data/sleepers.csv")
SLEEPER_KEY = ["season", "week", "player", "market", "side"]
SLEEPER_COLS = SLEEPER_KEY + ["player_id", "team", "opp", "group", "line", "book", "odds", "proj_model", "gap", "ev", "pick", "grade",
                              "sleeper_grade", "sleeper_p", "sleeper_med", "exp_opps", "sleeper_note", "event_id", "commence_time", "first_seen", "pulled_at"]


def log_sleepers(bets, season, week, pulled_at):
    """Record this pull's sleepers: one row per player, market and side at the best price. Until its game starts a
    sleeper follows the board (latest line and price; dropped if the model and the line have come together while
    the game is still listed); once the game starts it is frozen and graded like a pick. Returns the open count."""
    if bets is None or len(bets) == 0 or "sleeper" not in bets.columns:
        return 0
    b = bets[bets.sleeper.fillna("").astype(str) != ""].copy()
    now = O._utcnow()
    old = pd.read_csv(SLEEPERS) if SLEEPERS.exists() else pd.DataFrame(columns=SLEEPER_COLS)
    seen = old.drop_duplicates(SLEEPER_KEY).set_index(SLEEPER_KEY).first_seen if len(old) else pd.Series(dtype=object)
    if len(old):
        start_old = pd.to_datetime(old.commence_time, utc=True, errors="coerce")
        board_events = set(bets.event_id.dropna().astype(str)) if "event_id" in bets.columns else set()
        stale = (old.season == season) & (old.week == week) & (start_old > now) & old.event_id.astype(str).isin(board_events)
        old = old[~stale]                     # open rows on a listed game are rebuilt from this pull below
    if len(b):
        b["side"] = b.sleeper
        b["odds"] = np.where(b.side == "Over", b.over_odds, b.under_odds)
        b = b[pd.notna(b.odds)]
        b["_lk"] = np.where(b.side == "Over", -b.line, b.line)          # the best line first (lowest for an Over), then the best price
        b = b.sort_values(["_lk", "odds"], ascending=False).drop_duplicates(["player", "market", "side"])
        start = pd.to_datetime(b.commence_time, utc=True, errors="coerce")
        b = b[start > now]
        b = b.assign(season=season, week=week, pulled_at=pulled_at, gap=b.proj_model - b.line, ev=b.sleeper_ev, first_seen=pulled_at)
        new = b[[c for c in SLEEPER_COLS if c in b.columns]]
        new = new.copy()
        new["first_seen"] = [seen.get(tuple(k), pulled_at) for k in new[SLEEPER_KEY].itertuples(index=False)] if len(seen) else pulled_at
        if len(old):
            started = old[(old.season == season) & (old.week == week)].set_index(SLEEPER_KEY).index
            new = new[[tuple(k) not in started for k in new[SLEEPER_KEY].itertuples(index=False)]]
        old = pd.concat([old, new], ignore_index=True)
    SLEEPERS.parent.mkdir(parents=True, exist_ok=True)
    old[[c for c in SLEEPER_COLS if c in old.columns]].to_csv(SLEEPERS, index=False)
    s = old[(old.season == season) & (old.week == week)]
    return int((pd.to_datetime(s.commence_time, utc=True, errors="coerce") > now).sum())


def grade_sleepers(pw_comb, live=None):
    """Sleeper rows with result and units at the logged price, and a record by kind (combined Overs, solo Unders),
    by week and in all."""
    if not SLEEPERS.exists():
        return pd.DataFrame(), {}
    S = pd.read_csv(SLEEPERS)
    if S.empty:
        return S, {}
    pw = _with_ast(pw_comb)
    if live is not None and len(live):
        have = set(zip(pw.season, pw.week, pw.name_key))
        extra = _with_ast(live)[[k not in have for k in zip(live.season, live.week, live.name_key)]]
        pw = pd.concat([pw, extra[[c for c in extra.columns if c in pw.columns]]], ignore_index=True)
    S["name_key"] = S.player.map(norm_name)
    st = pw.groupby(["season", "week", "name_key"]).agg(comb=("comb", "sum"), solo=("solo_t", "sum"), ast=("ast_t", "sum")).reset_index()
    S = S.merge(st, on=["season", "week", "name_key"], how="left")
    if "player_id" in pw.columns and "player_id" in S.columns and S.player_id.notna().any():
        sid = pw[pw.player_id.notna()].assign(player_id=lambda d: d.player_id.astype(str)).groupby(["season", "week", "player_id"]).agg(
            comb_id=("comb", "sum"), solo_id=("solo_t", "sum"), ast_id=("ast_t", "sum")).reset_index()
        S["player_id"] = S.player_id.where(S.player_id.notna(), None).astype(object).map(lambda v: None if v is None else str(v).split(".")[0])
        S = S.merge(sid, on=["season", "week", "player_id"], how="left")
        for c in ("comb", "solo", "ast"):
            S[c] = S[f"{c}_id"].where(S[f"{c}_id"].notna(), S[c])
        S = S.drop(columns=["comb_id", "solo_id", "ast_id"])
    S["actual"] = _actual_for(S)
    done = S.actual.notna()
    win = np.where(S.side == "Over", S.actual > S.line, S.actual < S.line)
    S["result"] = np.where(~done, "Pending", np.where(S.actual == S.line, "Push", np.where(win, "Win", "Loss")))
    dec = S.odds.map(lambda a: american_to_decimal(a) if pd.notna(a) else np.nan)
    S["units"] = np.where(S.result == "Win", dec - 1, np.where(S.result == "Loss", -1.0, 0.0))
    S["kind"] = np.where(S.market.map(C.market_kind) == "solo", "Solo Unders", "Combined Overs")

    def rec(d):
        g = d[d.result.isin(["Win", "Loss"])]
        w = int((g.result == "Win").sum())
        cl = pd.to_numeric(g.sleeper_p, errors="coerce").dropna() if "sleeper_p" in g.columns else pd.Series(dtype=float)
        lo, hi = hit_interval(w, int(len(g) - w), _weeks_of(g))
        return dict(bets=int(len(d)), wins=w, losses=int(len(g) - w), pushes=int((d.result == "Push").sum()), pending=int((d.result == "Pending").sum()),
                    units=float(d.units.sum()), hit=float(w / len(g)) if len(g) else None, hit_lo=lo, hit_hi=hi, model_chance=float(cl.mean()) if len(cl) else None)
    sg = S.sleeper_grade.fillna("ungraded").astype(str) if "sleeper_grade" in S.columns else pd.Series("ungraded", index=S.index)
    summary = dict(all=rec(S), by_kind={k: rec(d) for k, d in S.groupby("kind")}, by_grade={g: rec(d) for g, d in S.groupby(sg)},
                   by_week=[dict(season=int(s), week=int(w), **rec(d)) for (s, w), d in S.groupby(["season", "week"])],
                   review_after=C.SLEEPER["review_after"], review_hit=C.SLEEPER["review_hit"])
    return S.drop(columns=["name_key"]), summary
