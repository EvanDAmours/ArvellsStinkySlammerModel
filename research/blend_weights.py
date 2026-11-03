"""Item 1: per-market line blend weight and line bias from closing-line errors, weeks 7 and 8 separately."""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "/home/user/ArvellsStinkySlammerModel")
L = pd.read_parquet("/tmp/claude-0/-home-user-ArvellsStinkySlammerModel/9774aa0d-3733-5c2c-b44f-73ecd122b6e0/scratchpad/res/lines78.parquet")
L = L[L.actual.notna() & L.model.notna()].copy()
print("lines with actual and model:", len(L), L.groupby(["week", "kind"]).size().to_dict())
rows = []
for (wk, kind), d in L.groupby(["week", "kind"]):
    a, m, l = d.actual.values, d.model.values, d.line.values
    mse_m, mse_l = np.mean((a - m) ** 2), np.mean((a - l) ** 2)
    bias_m, bias_l = np.mean(a - m), np.mean(a - l)
    # inverse-variance weight on the line (unbiased errors) and with the line de-biased
    w_iv = mse_m / (mse_m + mse_l)
    mse_l_db = np.mean((a - (l + bias_l)) ** 2)
    w_iv_db = mse_m / (mse_m + mse_l_db)
    # least squares a ~ b_m m + b_l l + c
    X = np.column_stack([m, l, np.ones(len(a))]); b = np.linalg.lstsq(X, a, rcond=None)[0]
    for w in (0.0, 0.4, 0.6, 0.8, 1.0):
        pass
    best = min(((w, np.mean((a - ((1 - w) * m + w * l)) ** 2)) for w in np.arange(0, 1.01, 0.05)), key=lambda x: x[1])
    best_db = min(((w, np.mean((a - ((1 - w) * m + w * (l + bias_l))) ** 2)) for w in np.arange(0, 1.01, 0.05)), key=lambda x: x[1])
    rows.append(dict(week=wk, kind=kind, n=len(d), mse_model=mse_m, mse_line=mse_l, bias_model=bias_m, bias_line=bias_l, w_iv=w_iv, w_iv_debiased=w_iv_db,
                     ls_model=b[0], ls_line=b[1], ls_c=b[2], best_w=best[0], best_mse=best[1], best_w_db=best_db[0], best_mse_db=best_db[1], mse_at_0p6=np.mean((a - (0.4 * m + 0.6 * l)) ** 2)))
R = pd.DataFrame(rows); pd.set_option("display.width", 250)
print(R.round(3).to_string(index=False))
# cross-check walk-forward: weights fitted on week 7, applied to week 8 (and the reverse)
for fit, test in ((7, 8), (8, 7)):
    for kind in ("combined", "solo"):
        f = R[(R.week == fit) & (R.kind == kind)].iloc[0]; d = L[(L.week == test) & (L.kind == kind)]
        a, m, l = d.actual.values, d.model.values, d.line.values
        cur = np.mean((a - (0.4 * m + 0.6 * l)) ** 2)
        new = np.mean((a - ((1 - f.w_iv_debiased) * m + f.w_iv_debiased * (l + f.bias_line))) ** 2)
        new_w = np.mean((a - ((1 - f.w_iv) * m + f.w_iv * l)) ** 2)
        print(f"fit wk{fit} -> test wk{test} {kind:9s} n={len(d):3d}  mse current(0.6, no bias) {cur:.3f}  | iv weight {f.w_iv:.2f} no bias {new_w:.3f}  | iv weight {f.w_iv_debiased:.2f} + bias {f.bias_line:+.2f}: {new:.3f}")
