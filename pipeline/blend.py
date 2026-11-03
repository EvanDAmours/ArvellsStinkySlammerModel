"""The pricing blend per market: how much of the pricing mean comes from the consensus line, and the level
correction each side needs, estimated from the closing lines of graded weeks.

The model's number for every line is logged at each pull (`log_model_numbers`, data/lines_log.csv, latest per
player-market-week). After a week is graded, every consensus closing line is compared with the box score and with
the model's logged number: the line's weight is the inverse-variance weight mse_model / (mse_model + mse_line), and
each side's level correction is its mean error, all shrunk by n / (n + k) toward the defaults (config.BLEND).
Weeks 7-8 of 2026: the solo line ran 0.3-0.5 high and the model 0.2-0.4 high; the combined line a tenth low.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

import config as C
from pipeline import odds as O
from pipeline.sources import norm_name

LOG = Path("data/lines_log.csv")
LOG_COLS = ["season", "week", "player", "player_id", "team", "market", "proj_model", "phi", "exp_opps", "share_pred", "pulled_at"]
CACHE = Path("data/cache/blend.json")


def log_model_numbers(bets, season, week, stamp):
    """Keep the model's latest number for every player-market with a line this week (one row each, the newest
    pull wins), so the blend can be estimated once the week is graded."""
    if bets is None or len(bets) == 0 or "proj_model" not in bets.columns:
        return 0
    new = bets[bets.proj_model.notna()].drop_duplicates(["player", "market"]).copy()
    new = new.assign(season=season, week=week, pulled_at=stamp)
    for c in LOG_COLS:
        if c not in new.columns:
            new[c] = np.nan
    new = new[LOG_COLS]
    old = pd.read_csv(LOG) if LOG.exists() else pd.DataFrame(columns=LOG_COLS)
    key = ["season", "week", "player", "market"]
    out = pd.concat([old, new], ignore_index=True).drop_duplicates(key, keep="last")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(LOG, index=False)
    return int(len(new))


def _actual(kind, comb, solo):
    return np.where(kind == "solo", solo, np.where(kind == "assists", comb - solo, comb))


def estimate(pw_comb, season, weeks=None):
    """Per market kind: dict(w, bias_line, bias_model, n, mse_model, mse_line, w_raw). pw_comb: player-week rows with
    name_key, season, week, comb, solo_t (official box scores). Only weeks with logged numbers, closing lines and
    box scores count. Empty dict when nothing is graded yet."""
    if not LOG.exists():
        return {}
    log = pd.read_csv(LOG)
    log = log[log.season == season]
    if log.empty:
        return {}
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
        cl = cl.copy(); cl["name_key"] = cl.player.map(norm_name); cl["kind"] = cl.market.map(C.market_kind)
        cons = cl.groupby(["event_id", "name_key", "kind"]).line.median().reset_index()
        box = st.groupby("name_key").agg(comb=("comb", "sum"), solo=("solo_t", "sum"))
        cons = cons.join(box, on="name_key")
        cons = cons[cons.comb.notna()]
        m = log[log.week == wk].drop_duplicates(["name_key", "kind"])[["name_key", "kind", "proj_model"]]
        cons = cons.merge(m, on=["name_key", "kind"], how="inner")
        cons["actual"] = _actual(cons.kind.values, cons.comb.values, cons.solo.values)
        rows.append(cons[["kind", "line", "proj_model", "actual"]])
    if not rows:
        return {}
    d = pd.concat(rows, ignore_index=True)
    c, out = C.BLEND, {}
    for kind, part in d.groupby("kind"):
        n = int(len(part))
        if n < c["min_lines"]:
            continue
        a, mo, li = part.actual.values.astype(float), part.proj_model.values.astype(float), part.line.values.astype(float)
        mse_m, mse_l = float(np.mean((a - mo) ** 2)), float(np.mean((a - li) ** 2))
        w_raw = mse_m / max(1e-9, mse_m + mse_l)
        sh = n / (n + c["k"])
        out[kind] = dict(w=float(C.LINE_WEIGHT + sh * (w_raw - C.LINE_WEIGHT)), w_raw=float(w_raw),
                         bias_line=float(np.clip(sh * np.mean(a - li), -c["max_bias"], c["max_bias"])),
                         bias_model=float(np.clip(sh * np.mean(a - mo), -c["max_bias"], c["max_bias"])),
                         n=n, mse_model=mse_m, mse_line=mse_l, weeks=sorted(int(w) for w in log.week.unique()))
    return out


def save(blend):
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(blend, indent=1))


def load():
    try:
        return json.loads(CACHE.read_text())
    except (OSError, ValueError):
        return None
