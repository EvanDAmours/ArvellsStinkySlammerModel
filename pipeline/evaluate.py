"""The scoreboard: is the engine beating the book's own fair price?

A win-loss record cannot answer that this season (MODEL_LOG A5: a true 5% edge needs about 34 weeks to show at two
standard errors). The chance the engine gives every line can: it is scored against what happened, next to the chance
the book's closing price gives the same line, on EVERY line the model had a number for, picked or not.

  closing_frame   one row per player and market of every graded week: the consensus closing line, the fair chance of
                  the Over at it, the best closing price of each side, the model's logged number and spread, the box score
  scoreboard      log-loss of the market, the model alone and the engine, by week and in all, the engine's margin over
                  the market with weeks as the unit, calibration of the engine's chance, and what each tier (pick, lean,
                  no pick) would have returned at the closing prices

The closing price is the last pull before kickoff (about an hour out), not the true close.
"""
import math

import numpy as np
import pandas as pd

import config as C
from pipeline import linelog as LL
from pipeline import odds as O
from pipeline.model import american_to_decimal, engine_chance, fair_over, p_over
from pipeline.sources import norm_name


def closing_frame(pw_comb, season, weeks=None):
    """pw_comb: player-week rows with name_key, team, season, week, comb, solo_t (the official box scores). Only weeks with
    logged numbers, two-way closing lines and box scores count. Empty frame when nothing is graded yet."""
    cols = ["week", "kind", "line", "p_mkt", "over_dec", "under_dec", "proj_model", "phi", "actual", "books"]
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
        m = m[[c for c in ("name_key", "kind", "team", "proj_model", "phi") if c in m.columns]]
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


def scoreboard(frame, min_lines=20):
    """The engine against the market on a closing frame. {} with fewer than `min_lines` decided lines."""
    from pipeline.grade import hit_interval
    if frame is None or len(frame) == 0:
        return {}
    d = frame[(frame.actual != frame.line) & frame.phi.notna() & frame.p_mkt.notna() & frame.proj_model.notna()].copy()
    if len(d) < min_lines:
        return {}
    e = C.ENGINE
    y = (d.actual.values > d.line.values).astype(float)
    p_model = np.clip([p_over(m, ph, l) for m, ph, l in zip(d.proj_model, d.phi, d.line)], 0.02, 0.98)
    p_mkt = d.p_mkt.values.astype(float)
    p_eng = np.array([engine_chance(a, b, e["beta"]) for a, b in zip(p_model, p_mkt)])
    p_low = np.array([engine_chance(a, b, e["beta_low"]) for a, b in zip(p_model, p_mkt)])
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
                beta=e["beta"], beta_low=e["beta_low"])
