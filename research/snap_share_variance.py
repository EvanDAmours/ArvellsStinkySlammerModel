"""Item 6: snap-share variance in the dispersion. Fit on 2023-2025, judge tail calibration on 2026 by expected-share bucket."""
import sys, json, pickle, numpy as np, pandas as pd
sys.path.insert(0, "/home/user/ArvellsStinkySlammerModel")
import config as C
from pipeline import model as M, backtest as B
from pipeline.model import p_over
R_ = "/tmp/claude-0/-home-user-ArvellsStinkySlammerModel/9774aa0d-3733-5c2c-b44f-73ecd122b6e0/scratchpad/res"
H = pd.read_parquet(f"{R_}/H.parquet"); aux = pickle.load(open(f"{R_}/aux.pkl", "rb")); seasons = aux["seasons"]
T = B.build_test_rows(H, seasons); T = T.assign(mu=M.project_frame(T)[1].values)
T["share"] = M.share_pred(T).fillna(T.pct_prev).fillna(1.0).clip(0.01, 1.0); T = T[T.mu > 0.3].copy()
T["bucket"] = pd.cut(T.share, [0, .4, .6, .8, 1.01], labels=["<40%", "40-60%", "60-80%", "80%+"])
fit, test = T[T.season < 2026], T[T.season == 2026]
# the share residual by bucket (how wrong the expected share is), on the fit seasons
res = fit.assign(r=fit.def_pct - fit.share).groupby("bucket", observed=True).r.std()
print("sd of actual share around expected, by bucket:", res.round(3).to_dict())
# dispersion estimates on the fit seasons: (a) two bins per group (current), (b) four buckets per group, (c) continuous
def phi_of(part):
    noise = part.mu / (part.n_prev + 1)
    return float(np.clip(np.mean(((part.comb - part.mu) ** 2 - noise) / part.mu), 0.5, 2.2))
two, four, cont = {}, {}, {}
for g, part in fit.groupby("group"):
    two[g] = phi_of(part[part.share >= 0.6]); two[g + ":low"] = phi_of(part[part.share < 0.6])
    for b, pb in part.groupby("bucket", observed=True):
        if len(pb) >= 60: four[(g, b)] = phi_of(pb)
    # continuous: phi = a + b * mu * cv^2, cv = sd_share_bucket / share; least squares on per-row (resid^2 - noise)/mu
    x = (part.mu * (part.bucket.map(res).astype(float) / part.share.clip(lower=0.05)) ** 2).values
    y = (((part.comb - part.mu) ** 2 - part.mu / (part.n_prev + 1)) / part.mu).values
    ok = np.isfinite(x) & np.isfinite(y); x, y = x[ok], y[ok]
    A = np.column_stack([np.ones(len(x)), x]); coef = np.linalg.lstsq(A, y, rcond=None)[0]
    cont[g] = (float(coef[0]), float(coef[1]))
print("continuous fits (a, b per group):", {g: (round(a, 2), round(b, 2)) for g, (a, b) in cont.items()})
rng = np.random.default_rng(5)
def pit(d, phis):
    out = []
    for r, ph in zip(d.itertuples(), phis):
        k = int(r.comb); lo = (1 - p_over(r.mu, ph, k - 0.5)) if k > 0 else 0.0; hi = 1 - p_over(r.mu, ph, k + 0.5)
        out.append(lo + rng.random() * (hi - lo))
    return np.asarray(out)
test = test.sample(min(9000, len(test)), random_state=2)
ph_two = [two.get(g + ":low", two.get(g, 1.0)) if s < 0.6 else two.get(g, 1.0) for g, s in zip(test.group, test.share)]
ph_four = [four.get((g, b), two.get(g, 1.0)) for g, b in zip(test.group, test.bucket)]
ph_cont = [float(np.clip(cont[g][0] + cont[g][1] * m * (res[b] / max(s, 0.05)) ** 2, 0.5, 2.5)) for g, b, m, s in zip(test.group, test.bucket, test.mu, test.share)]
u2, u4, uc = pit(test, ph_two), pit(test, ph_four), pit(test, ph_cont)
def row(u, name):
    return f"{name:10s} tails {np.mean(u < .05):.3f}/{np.mean(u > .95):.3f} flat {np.abs(np.histogram(u, 10, (0, 1))[0] / len(u) - .1).sum():.3f}"
print("2026, all:", row(u2, "two-bin"), "|", row(u4, "four-bin"), "|", row(uc, "continuous"))
for b in ["<40%", "40-60%", "60-80%", "80%+"]:
    i = (test.bucket == b).values
    print(f"  {b:6s} n={i.sum():5d}  two-bin {np.mean(u2[i] < .05):.3f}/{np.mean(u2[i] > .95):.3f}  four-bin {np.mean(u4[i] < .05):.3f}/{np.mean(u4[i] > .95):.3f}  continuous {np.mean(uc[i] < .05):.3f}/{np.mean(uc[i] > .95):.3f}")
