"""The line log: the model's read of every player-market with a line, kept at each pull (data/lines_log.csv, the newest pull
of a week wins). It is what lets any rule be scored after the fact without having been live: the scoreboard against the
market (pipeline/evaluate.py) is built from it, and a candidate rule is tested on it in the shadow before it is adopted.

Until 2026-11-09 this module also estimated a per-market blend of the model's number with the posted line (and a level
correction for each); the pricing engine replaced that (config.ENGINE; MODEL_LOG, decision register).
"""
from pathlib import Path

import numpy as np
import pandas as pd

LOG = Path("data/lines_log.csv")
LOG_COLS = ["season", "week", "player", "player_id", "team", "market", "proj_model", "phi", "exp_opps", "share_pred", "pulled_at", "line", "book", "side", "odds",
            "market_over", "model_over_own", "p_claim", "p_low", "p_model", "claim_ev", "edge_low", "tier", "grade", "pick", "lock", "lock_block"]


def log_model_numbers(bets, season, week, stamp):
    """Keep the model's latest read for every player-market with a line this week (one row each: his highest lock score
    among his lines and books; the newest pull wins)."""
    if bets is None or len(bets) == 0 or "proj_model" not in bets.columns:
        return 0
    new = bets[bets.proj_model.notna()].drop_duplicates(["player", "market"]).copy()
    new = new.assign(season=season, week=week, pulled_at=stamp)
    if "side" in new.columns and "over_odds" in new.columns:
        new["odds"] = np.where(new.side == "Over", new.over_odds, new.under_odds)
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
