"""Item 8: stake sizing on the graded picks: grade units vs flat vs quarter Kelly with caps."""
import sys, numpy as np, pandas as pd
sys.path.insert(0, '/home/user/ArvellsStinkySlammerModel')
import config as C
G = pd.read_csv("/tmp/claude-0/-home-user-ArvellsStinkySlammerModel/9774aa0d-3733-5c2c-b44f-73ecd122b6e0/scratchpad/graded.csv")
G = G[G.result.isin(["Win", "Loss", "Push"])].copy()
G["p_raw"] = np.where(G.side == "Over", G.model_over, 1 - G.model_over)
G["claim"] = pd.to_numeric(G.p_claim, errors="coerce").fillna(0.5 + C.CLAIM_SHRINK * (G.p_raw - 0.5))
from pipeline.model import american_to_decimal
G["dec"] = G.odds.map(american_to_decimal); G["b"] = G.dec - 1
G["win"] = (G.result == "Win").astype(float); G["loss"] = (G.result == "Loss").astype(float)
G["grade_u"] = G.grade.map(C.GRADE_UNITS).fillna(0.25)
f = (G.claim * G.b - (1 - G.claim)) / G.b
BANK = 100.0   # a bankroll of 100 units: the stake is a quarter of the Kelly fraction of it
G["kelly_u"] = (0.25 * f * BANK).clip(0.25, 3.0).where(f > 0, 0.25)
def cap_by_game(st, cap=4.0):
    tot = st.groupby(G.event_id).transform("sum"); return st * np.minimum(1.0, cap / tot.clip(lower=1e-9))
G["kelly_cap"] = cap_by_game(G.kelly_u)
G["flat"] = 1.0
def evaluate(col):
    st = G[col] * (G.grade_u.sum() / G[col].sum()); profit = st * G.units   # every scheme scaled to the same total staked as the grade ladder
    daily = profit.groupby(G.commence_time.str[:10]).sum()
    return dict(staked=float(st.sum()), profit=float(profit.sum()), roi=float(profit.sum() / st.sum()), worst_day=float(daily.min()), best_day=float(daily.max()), sd_day=float(daily.std()),
                max_game=float(st.groupby(G.event_id).sum().max()))
for col in ("flat", "grade_u", "kelly_u", "kelly_cap"):
    r = evaluate(col); print(f"{col:10s} staked {r['staked']:6.1f}u profit {r['profit']:+6.1f}u return {r['roi']:+.1%}  worst day {r['worst_day']:+.1f} best {r['best_day']:+.1f} sd/day {r['sd_day']:.1f}  max on one game {r['max_game']:.1f}u")
for wk in (7, 8):
    d = G[G.week == wk]
    for col in ("grade_u", "kelly_cap"):
        st = d[col] * (G.grade_u.sum() / G[col].sum()); pr = st * d.units; print(f"  week {wk} {col:9s} staked {st.sum():5.1f} profit {pr.sum():+5.1f} return {pr.sum() / st.sum():+.1%}")
print("quarter-Kelly stake (bankroll 100u) by grade:", G.groupby("grade").kelly_cap.mean().round(2).to_dict(), " by claim bucket:", G.groupby(pd.cut(G.claim, [0, .55, .6, .65, 1])).kelly_cap.mean().round(2).to_dict())
