"""Item 3: team tackle budget normalisation, walk-forward on the backtest frame."""
import sys, pickle, numpy as np, pandas as pd
sys.path.insert(0, "/home/user/ArvellsStinkySlammerModel")
import config as C
from pipeline import model as M, backtest as B
R_ = "/tmp/claude-0/-home-user-ArvellsStinkySlammerModel/9774aa0d-3733-5c2c-b44f-73ecd122b6e0/scratchpad/res"
H = pd.read_parquet(f"{R_}/H.parquet"); aux = pickle.load(open(f"{R_}/aux.pkl", "rb"))
seasons = aux["seasons"]
print("H", H.shape, "has opps/exp_opps:", "opps" in H.columns, "exp_opps" in H.columns)
# projections for every row (walk-forward by construction: features are prior-only)
base, mu, mu_solo = M.project_frame(H)
H = H.assign(mu=mu.values)
# team-game sums: actual team tackles (all rows), projected sum, plays faced, expected plays
tg = H.groupby(["season", "week", "team"]).agg(comb=("comb", "sum"), mu=("mu", "sum"), opps=("opps", "first"), exp_opps=("exp_opps", "first"), crew=("crew_comb", "first"), n=("comb", "size")).reset_index()
tg = tg[tg.opps.notna() & tg.exp_opps.notna()].sort_values(["season", "week"])
tg["tpp"] = tg.comb / tg.opps
# walk-forward league tackles per play: prior seasons and prior weeks only
tg["key"] = tg.season * 100 + tg.week
cum = tg.groupby("key").agg(c=("comb", "sum"), o=("opps", "sum")).sort_index().cumsum().shift(1)
tg["tpp_prev"] = tg.key.map((cum.c / cum.o))
tg["tpp_prev"] = tg.tpp_prev.fillna(tg.tpp.mean())
print("tackles per play: mean %.3f sd %.3f; team-game spread of actual/exp plays sd %.1f" % (tg.tpp.mean(), tg.tpp.std(), (tg.opps - tg.exp_opps).std()))
print("projected team sum vs actual team total: mean ratio %.3f, corr %.3f" % ((tg.mu / tg.comb).mean(), np.corrcoef(tg.mu, tg.comb)[0, 1]))
tg["budget"] = tg.exp_opps * tg.tpp_prev * tg.crew.fillna(1.0)
tg["factor_raw"] = tg.budget / tg.mu
print("raw budget/sum factor: mean %.3f sd %.3f p10 %.3f p90 %.3f" % (tg.factor_raw.mean(), tg.factor_raw.std(), tg.factor_raw.quantile(.1), tg.factor_raw.quantile(.9)))
# does the factor predict the team's actual/projected ratio? (walk-forward signal check)
tg["ratio_actual"] = tg.comb / tg.mu
print("corr(factor_raw, actual/sum) = %.3f  (if ~0 the budget carries no information)" % np.corrcoef(tg.factor_raw, tg.ratio_actual)[0, 1])
T = B.build_test_rows(H, seasons)
T = T.merge(tg[["season", "week", "team", "factor_raw"]], on=["season", "week", "team"], how="left")
a = T.comb.astype(float).values; m = T.mu.values
def mae(p): return float(np.mean(np.abs(a - p)))
print("\nbacktest rows", len(T), " full model mae %.4f" % mae(m))
for clip in ((0.9, 1.1), (0.85, 1.15), (0.8, 1.2), (0.7, 1.3)):
    for power in (0.5, 1.0):
        f = (T.factor_raw.fillna(1.0).clip(*clip) ** power).values
        parts = []
        for s in sorted(T.season.unique()):
            i = (T.season == s).values; parts.append(f"{s}: {np.mean(np.abs(a[i]-m[i])):.4f}->{np.mean(np.abs(a[i]-m[i]*f[i])):.4f}")
        print(f"clip {clip} power {power}: mae {mae(m * f):.4f}  | " + "  ".join(parts))
# partial normalisation: only toward the budget by a weight (shrink the factor toward 1)
for lam in (0.25, 0.5):
    f = (1 + lam * (T.factor_raw.fillna(1.0).clip(0.7, 1.3) - 1)).values
    print(f"shrink {lam}: mae {mae(m * f):.4f}")
