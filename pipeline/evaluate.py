"""The scoreboard: is the engine beating the book's own fair price?

A win-loss record cannot answer that this season (MODEL_LOG A5: a true 5% edge needs about 34 weeks to show at two
standard errors). The chance the engine gives every line can: it is scored against what happened, next to the chance
the book's closing price gives the same line, on EVERY line the model had a number for, picked or not.

  closing_frame   one row per player and market of every graded week: the consensus closing line, the fair chance of
                  the Over at it, the best closing price of each side, the model's logged number and spread, the box score
  scoreboard      log-loss of the market, the model alone and the engine, by week and in all, the engine's margin over
                  the market with weeks as the unit, calibration of the engine's chance, and what each tier (pick, lean,
                  no pick) would have returned at the closing prices. `since`: the same on the weeks from the engine's
                  first week on (config.ENGINE_LIVE), the only ones its weight was not chosen on. `shadow`: the
                  candidates of config.SHADOW scored on the same lines against the engine, never used for a pick

The closing price is the last pull before kickoff (about an hour out), not the true close.
"""
import math

import numpy as np
import pandas as pd

import config as C
from pipeline import linelog as LL
from pipeline import odds as O
from pipeline.model import american_to_decimal, engine_betas, engine_chance, fair_over, p_over
from pipeline.sources import norm_name


def closing_frame(pw_comb, season, weeks=None):
    """pw_comb: player-week rows with name_key, team, season, week, comb, solo_t (the official box scores). Only weeks with
    logged numbers, two-way closing lines and box scores count. Empty frame when nothing is graded yet."""
    cols = ["week", "kind", "line", "p_mkt", "over_dec", "under_dec", "proj_model", "phi", "actual", "books", "level"]
    if not LL.LOG.exists():
        return pd.DataFrame(columns=cols)
    log = pd.read_csv(LL.LOG)
    log = log[log.season == season]
    if log.empty:
        return pd.DataFrame(columns=cols)
    log["name_key"] = log.player.map(norm_name)
    log["kind"] = log.market.map(C.market_kind)
    rows = []
    for wk in sorted(log.week.unique()):
        if weeks is not None and wk not in weeks:
            continue
        cl = O.closing_lines(season, int(wk))
        st = pw_comb[(pw_comb.season == season) & (pw_comb.week == wk)]
        if cl is None or len(cl) == 0 or st.empty:
            continue
        cl = cl[cl.over_odds.notna() & cl.under_odds.notna()].copy()      # two-way prices only: a one-sided price holds an unknown vig
        if cl.empty:
            continue
        cl["name_key"] = cl.player.map(norm_name); cl["kind"] = cl.market.map(C.market_kind)
        cl["p_nv"] = [fair_over(o, u) for o, u in zip(cl.over_odds, cl.under_odds)]
        cl["od"], cl["ud"] = cl.over_odds.map(american_to_decimal), cl.under_odds.map(american_to_decimal)
        keys = ["event_id", "name_key", "kind"]
        cons = cl.groupby(keys).agg(line=("line", "median")).reset_index()
        at = cl.merge(cons, on=keys, suffixes=("", "_c"))
        at = at[at.line == at.line_c]                                     # the books posting the consensus line
        cons = cons.join(at.groupby(keys).agg(p_mkt=("p_nv", "mean"), over_dec=("od", "max"), under_dec=("ud", "max"), books=("p_nv", "size")), on=keys)
        m = log[log.week == wk].drop_duplicates(["name_key", "kind", "team"] if "team" in log.columns else ["name_key", "kind"])
        m = m.assign(level=pd.to_numeric(m["level"], errors="coerce").fillna(1.0) if "level" in m.columns else 1.0)     # the lined-player level the number was priced with
        m = m[[c for c in ("name_key", "kind", "team", "proj_model", "phi", "level") if c in m.columns]]
        cons = cons.merge(m, on=["name_key", "kind"], how="inner")
        # box scores by name AND team: two players can share a name key (the Byron Youngs, the Byron Murphys)
        if "team" in cons.columns and "team" in st.columns:
            box = st.groupby(["name_key", "team"]).agg(comb=("comb", "sum"), solo=("solo_t", "sum")).reset_index()
            cons = cons.merge(box, on=["name_key", "team"], how="left")
        else:
            cons = cons.join(st.groupby("name_key").agg(comb=("comb", "sum"), solo=("solo_t", "sum")), on="name_key")
        cons = cons[cons.comb.notna()]
        cons["actual"] = np.where(cons.kind == "solo", cons.solo, np.where(cons.kind == "assists", cons.comb - cons.solo, cons.comb))
        cons["week"] = int(wk)
        rows.append(cons[cols])
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=cols)


def _ll(p, y):
    p = np.clip(np.asarray(p, dtype=float), 1e-4, 1 - 1e-4)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def _cluster(v, g):
    """Mean of v and its standard error with the groups g (weeks) as the unit; se None with fewer than two groups."""
    s = pd.DataFrame(dict(v=np.asarray(v, dtype=float), g=np.asarray(g))).groupby("g").v.agg(["sum", "size"])
    m = float(s["sum"].sum() / s["size"].sum())
    if len(s) < 2:
        return m, None
    return m, float(math.sqrt(((s["sum"] - m * s["size"]) ** 2).sum()) / s["size"].sum() * math.sqrt(len(s) / (len(s) - 1)))


def lined_level(frame, week, kinds=None, shrink=None, clip=None):
    """{kind: factor} for `week`: actual over projected on the season's lined games before it, on the model's number before
    any level (proj_model / level), shrunk n / (n + shrink) and clipped. 1.0 for a kind with no earlier lined game."""
    cfg = C.LINED_LEVEL
    kinds, shrink, clip = kinds or cfg["kinds"], cfg["shrink"] if shrink is None else shrink, clip or cfg["clip"]
    out = {k_: 1.0 for k_ in kinds}
    if frame is None or len(frame) == 0:
        return out
    v = frame[frame.proj_model.notna() & frame.actual.notna() & (frame.week < week)]
    lv = pd.to_numeric(v["level"], errors="coerce").fillna(1.0) if "level" in v.columns else pd.Series(1.0, index=v.index)
    raw = v.proj_model / lv.clip(lower=0.5)
    for k_ in kinds:
        sel = (v.kind == k_).values
        if sel.sum() and raw[sel].sum() > 0:
            r = 1 + (v.actual[sel].sum() - raw[sel].sum()) / raw[sel].sum() * sel.sum() / (sel.sum() + shrink)
            out[k_] = float(np.clip(r, *clip))
    return out


SHADOW_NAMES = (("beta_by_kind", "The flat weight of 0.5 in both markets (the rule until 2026-11-09)"),
                ("centred", "The combined gap centred on the week's own mean"),
                ("lined_level", "The level for lined players on solo lines too"))


def _shadow(v, e):
    """The Over's chance on every row of v under each candidate of config.SHADOW. v holds every line with a market chance
    and a model number, pushes included: a rule that runs before kickoff cannot know which lines will push."""
    s = C.SHADOW
    logit, sig = (lambda p: np.log(p / (1 - p))), (lambda z: 1 / (1 + np.exp(-z)))
    pk = np.clip(v.p_mkt.values.astype(float), 1e-4, 1 - 1e-4)
    pm = np.clip([p_over(m, ph, l) for m, ph, l in zip(v.proj_model, v.phi, v.line)], 0.02, 0.98)
    gap = logit(pm) - logit(pk)
    eng = np.array([engine_betas(k_)[0] for k_ in v.kind], dtype=float)
    out = {}
    beta = np.array([s["beta_by_kind"].get(k_, e["beta"]) for k_ in v.kind], dtype=float)
    out["beta_by_kind"] = sig(logit(pk) + beta * gap)
    centre = pd.Series(gap).groupby([v.week.values, v.kind.values]).transform("mean").values
    centre = np.where(v.kind.isin(s["centre_kinds"]).values, centre, 0.0)
    out["centred"] = sig(logit(pk) + eng * (gap - centre))
    ratio = np.ones(len(v))
    for w in sorted(set(v.week)):
        lv = lined_level(v, w, kinds=s["level_kinds"], shrink=s["level_shrink"])
        for k_, r in lv.items():
            ratio[((v.week == w) & (v.kind == k_)).values] = r
    pm_l = np.clip([p_over(m * r, ph, l) for m, r, ph, l in zip(v.proj_model, ratio, v.phi, v.line)], 0.02, 0.98)
    out["lined_level"] = sig(logit(pk) + eng * (logit(pm_l) - logit(pk)))
    return out


def scoreboard(frame, min_lines=20, live_week=None):
    """The engine against the market on a closing frame. {} with fewer than `min_lines` decided lines. live_week: the
    first week the engine chose picks (default config.ENGINE_LIVE for its season, week 1 in a later one)."""
    from pipeline.grade import hit_interval
    if frame is None or len(frame) == 0:
        return {}
    v = frame[frame.phi.notna() & frame.p_mkt.notna() & frame.proj_model.notna()].reset_index(drop=True)
    decided = (v.actual != v.line).values
    d = v[decided].copy()
    if len(d) < min_lines:
        return {}
    e = C.ENGINE
    if live_week is None:
        live_week = C.ENGINE_LIVE["week"] if C.SEASON == C.ENGINE_LIVE["season"] else 1
    y = (d.actual.values > d.line.values).astype(float)
    p_model = np.clip([p_over(m, ph, l) for m, ph, l in zip(d.proj_model, d.phi, d.line)], 0.02, 0.98)
    p_mkt = d.p_mkt.values.astype(float)
    p_eng = np.array([engine_chance(a, b, engine_betas(k_)[0]) for a, b, k_ in zip(p_model, p_mkt, d.kind)])
    p_low = np.array([engine_chance(a, b, engine_betas(k_)[1]) for a, b, k_ in zip(p_model, p_mkt, d.kind)])
    wk = d.week.values
    ll = dict(market=_ll(p_mkt, y), model=_ll(p_model, y), engine=_ll(p_eng, y))
    diff = ll["market"] - ll["engine"]                       # positive: the engine's chance was the better forecast
    mean, se = _cluster(diff, wk)
    by_week = [dict(week=int(w), lines=int((wk == w).sum()), market=float(ll["market"][wk == w].mean()), model=float(ll["model"][wk == w].mean()),
                    engine=float(ll["engine"][wk == w].mean()), engine_minus_market=float(diff[wk == w].mean())) for w in sorted(set(wk))]
    by_kind = {}
    for k_ in sorted(set(d.kind)):
        sel = (d.kind == k_).values
        m_, s_ = _cluster(diff[sel], wk[sel])
        by_kind[k_] = dict(lines=int(sel.sum()), engine_minus_market=m_, se=s_)
    # the weeks the engine's weight was not chosen on, by themselves
    live, since = wk >= live_week, None
    if live.any():
        m_, s_ = _cluster(diff[live], wk[live])
        kinds = {}
        for k_ in sorted(set(d.kind[live])):
            sel = live & (d.kind == k_).values
            mk_, sk_ = _cluster(diff[sel], wk[sel])
            kinds[k_] = dict(lines=int(sel.sum()), engine_minus_market=mk_, se=sk_)
        since = dict(from_week=int(live_week), lines=int(live.sum()), weeks=[int(w) for w in sorted(set(wk[live]))],
                     log_loss={k_: float(a[live].mean()) for k_, a in ll.items()}, engine_minus_market=m_, se=s_, t=(m_ / s_ if s_ else None), by_kind=kinds)
    # the candidates in the shadow, on the same lines against the engine (positive: the candidate was the better forecast)
    shadow, sh = [], _shadow(v, e)
    for key, name in SHADOW_NAMES:
        l_ = _ll(sh[key][decided], y)
        gain = ll["engine"] - l_
        m_, s_ = _cluster(gain, wk)
        row = dict(key=key, name=name, log_loss=float(l_.mean()), vs_engine=m_, se=s_, t=(m_ / s_ if s_ else None),
                   by_week=[dict(week=int(w), vs_engine=float(gain[wk == w].mean())) for w in sorted(set(wk))], since=None)
        if live.any():
            mo, so = _cluster(gain[live], wk[live])
            row["since"] = dict(lines=int(live.sum()), weeks=int(len(set(wk[live]))), vs_engine=mo, se=so, t=(mo / so if so else None))
        shadow.append(row)
    # the two conditions of the decision register that are read here, on the weeks since the engine only
    need = max(1, int(C.ENGINE_LIVE.get("read_after_week", live_week)) - int(live_week) + 1) if C.SEASON == C.ENGINE_LIVE["season"] else 4
    n_wk, t_ = (len(since["weeks"]), since["t"]) if since else (0, None)
    note = None if not since else f"margin {since['engine_minus_market']:+.4f}" + ("" if since["se"] is None else f", give or take {2 * since['se']:.4f}")
    row = lambda rule, name, what, state: dict(rule=rule, name=name, what=what, n=n_wk, of=need, unit="weeks", bar=None, wins=None, losses=None, hit=None, hit_lo=None,
                                               hit_hi=None, claimed=None, model_said=None, state=state, note=note)
    watches = [row("E2", f"The engine's weight ({engine_betas('solo')[0]:g} solo, {engine_betas('combined')[0]:g} combined)", f"Moved toward the book if the engine's margin over the book since week {live_week} is negative by more than twice its give or take, read after week {int(live_week) + need - 1}; raised only by the same test.",
                   "running" if n_wk < need or t_ is None else "fails" if t_ <= -2 else "holds")]
    if C.STAKE.get("mode") != "grade":          # the Kelly stake's own condition; stakes by grade are counted with the picks (grade.engine_era, S3)
        watches.append(row("S1", "Stakes on the cautious chance", "Sized on the win chance instead once the engine's margin over the book is positive by more than twice its give or take.",
                   "running" if n_wk < need or t_ is None else "met" if t_ >= 2 else "not met"))
    # the engine's side on every line at the best closing price, and what each tier did
    od, ud = d.over_dec.values.astype(float), d.under_dec.values.astype(float)
    over = (p_eng * od - 1) > ((1 - p_eng) * ud - 1)
    dec = np.where(over, od, ud)
    p_side, pl_side = np.where(over, p_eng, 1 - p_eng), np.where(over, p_low, 1 - p_low)
    win = np.where(over, y == 1, y == 0).astype(float)
    ret = np.where(win == 1, dec - 1, -1.0)
    ev, edge_low = p_side * dec - 1, pl_side * dec - 1
    tiers = []
    for name, sel in (("Picks, B or better", edge_low >= e["b_edge_low"]),                                   # a cautious edge of 2%+
                      ("Picks, C", (edge_low >= e["pick_edge_low"]) & (edge_low < e["b_edge_low"])),            # a cautious edge under 2%
                      ("Leans (not staked)", (edge_low < e["pick_edge_low"]) & (ev >= e["lean_edge"])),      # an edge only at the win chance
                      ("No pick", (edge_low < e["pick_edge_low"]) & (ev < e["lean_edge"]))):
        n = int(sel.sum())
        if not n:
            tiers.append(dict(tier=name, lines=0)); continue
        w = int(win[sel].sum()); lo, hi = hit_interval(w, n - w, len(set(wk[sel])))
        tiers.append(dict(tier=name, lines=n, wins=w, losses=n - w, hit=w / n, hit_lo=lo, hit_hi=hi, chance=float(p_side[sel].mean()), ret=float(ret[sel].mean())))
    cal = []
    cut = pd.cut(pd.Series(p_side), [0, .45, .5, .55, .6, .65, 1.0])
    for b_, idx in pd.Series(range(len(d))).groupby(cut.values, observed=True):
        i = idx.values
        cal.append(dict(bucket=str(b_), lines=int(len(i)), said=float(p_side[i].mean()), hit=float(win[i].mean())))
    return dict(lines=int(len(d)), weeks=[int(w) for w in sorted(set(wk))],
                log_loss=dict(market=float(ll["market"].mean()), model=float(ll["model"].mean()), engine=float(ll["engine"].mean())),
                engine_minus_market=mean, se=se, t=(mean / se if se else None), by_week=by_week, by_kind=by_kind, tiers=tiers, calibration=cal,
                beta=e["beta"], beta_low=e["beta_low"], live_week=int(live_week), since=since, shadow=shadow, watches=watches)
