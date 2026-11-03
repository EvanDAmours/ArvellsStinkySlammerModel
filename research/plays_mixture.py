"""Item 5: plays-faced mixture vs the single count distribution. Tail calibration (PIT coverage) on the backtest
frame, Brier/log-loss at the posted consensus lines of weeks 7 and 8. Same mean in both; only the shape differs."""
import sys, json, pickle, math, numpy as np, pandas as pd
sys.path.insert(0, "/home/user/ArvellsStinkySlammerModel")
import config as C
from pipeline import model as M, backtest as B
from pipeline.model import p_over
R_ = "/tmp/claude-0/-home-user-ArvellsStinkySlammerModel/9774aa0d-3733-5c2c-b44f-73ecd122b6e0/scratchpad/res"
H = pd.read_parquet(f"{R_}/H.parquet"); aux = pickle.load(open(f"{R_}/aux.pkl", "rb")); seasons = aux["seasons"]
phi_by = json.load(open(f"{R_}/state8.json"))["phi"]
T = B.build_test_rows(H, seasons)
base, mu, mu_solo = M.project_frame(T); T = T.assign(mu=mu.values * 1.0)
share = M.share_pred(T).fillna(T.pct_prev).fillna(1.0)
T["phi"] = [phi_by.get(f"{g}:low", phi_by.get(g, 1.0)) if s < C.PHI_SHARE_SPLIT else phi_by.get(g, 1.0) for g, s in zip(T.group, share)]
T = T[T.exp_opps.notna() & T.opps.notna() & (T.mu > 0.3)].copy()
sd_plays = float((T.drop_duplicates(["season", "week", "team"]).opps - T.drop_duplicates(["season", "week", "team"]).exp_opps).std())
print("rows", len(T), "sd of plays faced around expectation", round(sd_plays, 2))
# Gauss-Hermite nodes for a normal mixture over plays
GH_X, GH_W = np.polynomial.hermite_e.hermegauss(9); GH_W = GH_W / GH_W.sum()
def cdf_single(mu, phi, k):           # P(X <= k)
    return 1 - p_over(mu, phi, k + 0.5)
def cdf_mix(mu, phi_tot, k, eo, sd=sd_plays, floor=0.55):
    cv2 = (sd / eo) ** 2
    phi_w = max(floor, phi_tot - mu * cv2)          # within-game dispersion once the plays draw is taken out
    tot = 0.0
    for x, w in zip(GH_X, GH_W):
        plays = max(0.3 * eo, eo + sd * x)
        tot += w * (1 - p_over(mu * plays / eo, phi_w, k + 0.5))
    return tot
# PIT coverage: how often the actual falls in each tail, by both shapes (randomised PIT for counts)
rng = np.random.default_rng(1)
def pit(cdf):
    out = []
    for r in T.itertuples():
        a = int(r.comb); lo = cdf(r.mu, r.phi, a - 1) if a > 0 else 0.0; hi = cdf(r.mu, r.phi, a)
        out.append(lo + rng.random() * (hi - lo))
    return np.array(out)
def pit_mix():
    out = []
    for r in T.itertuples():
        a = int(r.comb); lo = cdf_mix(r.mu, r.phi, a - 1, r.exp_opps) if a > 0 else 0.0; hi = cdf_mix(r.mu, r.phi, a, r.exp_opps)
        out.append(lo + rng.random() * (hi - lo))
    return np.array(out)
sub = T.sample(min(12000, len(T)), random_state=3); T = sub
u1 = pit(cdf_single); u2 = pit_mix()
def report(u, name):
    bins = np.histogram(u, bins=10, range=(0, 1))[0] / len(u)
    print(f"{name:8s} PIT deciles " + " ".join(f"{b:.3f}" for b in bins) + f"  | below 5%: {np.mean(u < .05):.3f} above 95%: {np.mean(u > .95):.3f}  (ideal 0.050)  flatness {np.abs(bins - 0.1).sum():.3f}")
report(u1, "single"); report(u2, "mixture")
for grp in ("LB", "S", "CB", "DL"):
    i = (T.group == grp).values
    print(f"  {grp}: single tails {np.mean(u1[i] < .05):.3f}/{np.mean(u1[i] > .95):.3f}  mixture {np.mean(u2[i] < .05):.3f}/{np.mean(u2[i] > .95):.3f}  n={i.sum()}")
# Brier / log-loss at posted consensus lines, weeks 7-8 (combined and solo)
L = pd.read_parquet(f"{R_}/lines78.parquet"); L = L[L.actual.notna() & L.model.notna() & L.exp_opps.notna() & (L.kind != "assists") & (L.over_odds.fillna(0) != 0) & (L.under_odds.fillna(0) != 0)].copy()
def scores(name, pfun):
    p = np.array([pfun(r) for r in L.itertuples()]); y = (L.actual.values > L.line.values).astype(float); push = L.actual.values == L.line.values
    p, y = p[~push], y[~push]
    print(f"{name:28s} n={len(y)} Brier {np.mean((p - y) ** 2):.4f}  log-loss {-np.mean(y * np.log(np.clip(p, 1e-6, 1)) + (1 - y) * np.log(np.clip(1 - p, 1e-6, 1))):.4f}")
blend = lambda r: 0.4 * r.model + 0.6 * r.line
scores("single, blended mean", lambda r: p_over(blend(r), r.phi_use, r.line))
scores("mixture, blended mean", lambda r: 1 - cdf_mix(blend(r), r.phi_use, math.floor(r.line), r.exp_opps))
scores("single, model mean", lambda r: p_over(r.model, r.phi_use, r.line))
scores("mixture, model mean", lambda r: 1 - cdf_mix(r.model, r.phi_use, math.floor(r.line), r.exp_opps))
# the market's own no-vig probability as the benchmark
from pipeline.model import american_to_decimal as dec
def mkt(r):
    po, pu = 1 / dec(r.over_odds), 1 / dec(r.under_odds); return po / (po + pu)
scores("market no-vig", mkt)
