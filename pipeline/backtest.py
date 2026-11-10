"""Walk-forward backtest: every past game predicted using only what was known before it.

What it certifies is the number the board prices with (the factor model blended with the corrector), not the factor model
alone: the corrector is trained on earlier seasons only and scored on the next (one fold per season after the first).
Reports, for each season and overall:
  - accuracy of competing predictors (season average, shrinkage levels, last game, the factor model, the final projection);
  - the protocol's test of every factor, each morning: Poisson deviance on the rows the factor moves, both variants at the
    same level, paired, with season-weeks as the unit (`factor_tests`). A factor that is in must not hurt; one that is out
    can earn its way back. Nothing is switched automatically: a flag is a prompt to run the full test (MODEL_LOG);
  - the spread of tackle counts (variance / mean) by position, share of snaps and market, fitted by maximum likelihood
    around the out-of-sample final projection, the one the pricer uses;
  - calibration of over-probabilities and the shape of the distribution around that same projection;
  - where the season log stops describing a player (weak spots), and what follows an outlier game.
"""
import math

import numpy as np
import pandas as pd

import config as C
from pipeline import model as M

try:
    from scipy.special import gammaln as _gammaln
except ImportError:                                  # scipy ships with scikit-learn; this keeps the module importable without it
    _gammaln = np.vectorize(math.lgamma)

FACTOR_NAMES = {"tilt": "spread tilt", "crew": "stat crew", "role": "next man up", "snap": "snap trend", "volume": "opponent volume", "depth": "depth chart",
                "pfr": "coverage targets and missed tackles", "mix": "run/pass mix", "rest": "bye", "injury": "injury report", "role_shift": "role-shift factors",
                "persnap": "per-snap base", "vacancy": "vacancy rule", "dome": "indoors (corners)", "outlier_damp": "outlier damping"}


def build_test_rows(H, seasons, min_prev=2, min_week=3):
    # crew columns already hold this game's crew, estimated from earlier games only (see model.prepare)
    return H[H.season.isin(seasons) & (H.n_prev >= min_prev) & (H.week >= min_week) & H.comb.notna()].copy()


def deviance(actual, pred):
    """Poisson deviance per row: the proper score for a mean (the absolute miss rewards the median instead)."""
    y, m = np.asarray(actual, dtype=float), np.clip(np.asarray(pred, dtype=float), 0.05, None)
    return 2 * (np.where(y > 0, y * np.log(np.where(y > 0, y, 1) / m), 0.0) - (y - m))


def paired(diff, weeks):
    """Mean of a per-row difference and its t with season-weeks as the unit: (mean, t, clusters). t is None with fewer
    than three weeks. The picks of one week share a shock, so rows are not independent (MODEL_LOG A3)."""
    s = pd.DataFrame(dict(v=np.asarray(diff, dtype=float), g=np.asarray(weeks))).groupby("g").v.agg(["sum", "size"])
    if len(s) == 0 or s["size"].sum() == 0:
        return float("nan"), None, 0
    m = float(s["sum"].sum() / s["size"].sum())
    if len(s) < 3:
        return m, None, int(len(s))
    se = float(math.sqrt(((s["sum"] - m * s["size"]) ** 2).sum()) / s["size"].sum() * math.sqrt(len(s) / (len(s) - 1)))
    return m, (m / se if se > 0 else None), int(len(s))


def _metrics(actual, pred):
    pred = pd.Series(pred).fillna(pd.Series(actual).mean())   # an undefined prediction is scored, not dropped
    a, p = np.asarray(actual, dtype=float), np.asarray(pred, dtype=float)
    e = a - p
    # level-matched miss: the predictor scaled to zero bias first, so a piece cannot look better by shifting the level
    scale = a.sum() / p.sum() if p.sum() > 0 else 1.0
    return dict(n=int(len(e)), mae=float(np.mean(np.abs(e))), mae_cal=float(np.mean(np.abs(a - p * scale))), rmse=float(np.sqrt(np.mean(e ** 2))), bias=float(np.mean(e)),
                deviance=float(np.mean(deviance(a, p))))


def _logpmf(y, mu, phi):
    """Log-probability of counts y under the pricer's distribution (model.p_over): binomial under 0.98, Poisson near 1,
    negative binomial above 1.02, with mean mu and variance phi x mu."""
    y, mu = np.asarray(y, dtype=float), np.clip(np.asarray(mu, dtype=float), 0.05, None)
    if phi < 0.98:
        n = np.maximum(np.ceil(mu / (1 - phi)), np.ceil(mu) + 1)
        p = mu / n
        lp = _gammaln(n + 1) - _gammaln(y + 1) - _gammaln(np.maximum(n - y, 0) + 1) + y * np.log(p) + np.maximum(n - y, 0) * np.log1p(-p)
        return np.where(y <= n, lp, -20.0)
    if phi > 1.02:
        r = mu / (phi - 1)
        return _gammaln(y + r) - _gammaln(r) - _gammaln(y + 1) - r * math.log(phi) + y * math.log(1 - 1 / phi)
    return y * np.log(mu) - mu - _gammaln(y + 1)


def fit_phi(y, mu, lo=0.5, hi=2.5):
    """The variance / mean ratio that makes the observed counts most likely around the projections given (two passes of
    a grid). Fitted around the projection the pricer uses, so the projection's own error is in the spread, as it must be."""
    y, mu = np.asarray(y, dtype=float), np.asarray(mu, dtype=float)
    best, step = None, 0.05
    grid = np.arange(lo, hi + 1e-9, step)
    for _ in range(2):
        ll = [float(_logpmf(y, mu, float(ph)).sum()) for ph in grid]
        best = float(grid[int(np.argmax(ll))])
        grid = np.arange(max(lo, best - step), min(hi, best + step) + 1e-9, step / 10)
    return best


def walk_forward_final(T, mu_scaled, min_train=2000, min_test=200):
    """The corrector's out-of-sample number for every test row: trained on the seasons before the row's season, one fold a
    season. NaN for the first season (nothing to train on) and for a fold too small to fit. Returns (gbm, X)."""
    X = M.gbm_features(T, mu_scaled)
    gb = np.full(len(T), np.nan)
    for S in sorted(T.season.unique())[1:]:
        tr, te = (T.season < S).values, (T.season == S).values
        if tr.sum() <= min_train or te.sum() <= min_test:
            continue
        fold = M.fit_gbm(X[tr], T.comb[tr])
        if fold is not None:
            gb[te] = fold(X[te])
    return gb, X


def factor_tests(T, base_mu, weeks, share=None):
    """The protocol's test of each factor on the factor model: with against without, each scaled to the same level, on the
    rows the factor moves, in Poisson deviance, paired, season-weeks as the unit. `helps` is negative when the factor
    lowers the deviance; `helps_regulars` is the same on the regulars among those rows (the players who get lines).
    Verdicts, from the regulars when the factor moves 200 or more of them, else from every row: a factor in the model
    'earns its place' at t <= -1, is 'neutral' between, and 'hurts' at t >= +2; one that is out is a 'candidate' at
    t <= -2. A verdict here prompts the full test on the final projection (walk-forward with the corrector retrained,
    judged on regulars); it never switches a factor by itself."""
    y = T.comb.values.astype(float)
    regular = (np.asarray(share, dtype=float) >= C.REGULAR_SHARE) if share is not None else np.zeros(len(T), dtype=bool)
    lvl = lambda mu: mu * (y.sum() / max(1e-9, float(np.nansum(mu))))
    base_raw = np.asarray(base_mu, dtype=float)
    base = lvl(base_raw)
    out = []
    for key, name in FACTOR_NAMES.items():
        on = bool(C.FACTORS.get(key, True))
        other_raw = M.project_frame(T, **{"use_" + key: not on})[1].values.astype(float)
        other = lvl(other_raw)
        with_, without = (base, other) if on else (other, base)
        # the rows the factor itself moves (before the two variants are brought to the same level)
        moved = np.isfinite(base_raw) & np.isfinite(other_raw) & (np.abs(base_raw / np.clip(other_raw, 1e-9, None) - 1) > 1e-6)
        if moved.sum() < 30:
            out.append(dict(factor=name, key=key, in_model=on, rows=int(moved.sum()), helps=None, t=None, verdict="too few rows"))
            continue
        dall = deviance(y, with_) - deviance(y, without)
        m, t, k = paired(dall[moved], weeks[moved])
        mr = moved & regular
        m_r, t_r, _ = paired(dall[mr], weeks[mr]) if mr.sum() >= 200 else (None, None, 0)
        bias_with, bias_without = float(np.mean((y - with_)[moved])), float(np.mean((y - without)[moved]))
        tj = t_r if t_r is not None else t                    # judged on the regulars it moves when there are enough of them
        if tj is None:
            verdict = "too few weeks"
        elif on:
            verdict = "earns its place" if tj <= -1 else "hurts" if tj >= 2 else "neutral"
        else:
            verdict = "candidate" if tj <= -2 else "out"
        out.append(dict(factor=name, key=key, in_model=on, rows=int(moved.sum()), helps=m, t=t, weeks=k, rows_regulars=int(mr.sum()), helps_regulars=m_r, t_regulars=t_r,
                        bias_with=bias_with, bias_without=bias_without, verdict=verdict))
    return out


def run_backtest(H, seasons):
    T = build_test_rows(H, seasons)
    if T.empty:
        return {"error": "No games to test yet."}, {g: v for g, v in C.DEFAULT_PHI.items()}, C.SHRINK_GAMES, 1.0, None
    a = T.comb.astype(float)
    y = a.values
    weeks = (T.season * 100 + T.week).values
    preds = {"Season average": T.comb_prev_raw / T.n_prev}
    for k in [1, 2, 4]:
        preds[f"Season average shrunk {k} game{'s' if k > 1 else ''} toward last season"] = M.project_frame(T, k=k, use_tilt=False, use_crew=False, use_role=False)[0]
    preds["Last game"] = T["last"]
    preds["80% season average, 20% last game"] = 0.8 * (T.comb_prev_raw / T.n_prev) + 0.2 * T["last"]
    preds["Average of last two games"] = T.last2
    shrink_opts = {0: preds["Season average"], **{k: preds[f"Season average shrunk {k} game{'s' if k > 1 else ''} toward last season"] for k in [1, 2, 4]}}
    best_k = min(shrink_opts, key=lambda k: float(np.nanmean(np.abs(a - shrink_opts[k]))))
    base, full, full_solo = M.project_frame(T)                      # the factor model as it runs (config.FACTORS)
    preds["Factor model"] = full
    preds["Factor model with one shrink for every position"] = M.project_frame(T, k=best_k)[1]
    for key, name in FACTOR_NAMES.items():                           # each factor flipped: out of the model, or added to it
        on = bool(C.FACTORS.get(key, True))
        preds[f"Factor model without {name}" if on else f"Factor model with {name} added"] = M.project_frame(T, **{"use_" + key: not on})[1]

    scale = float(np.clip(T.comb.sum() / max(1e-9, float(np.nansum(full))), 0.9, 1.1))   # level calibration of the factor model
    mu_f = (full * scale).values.astype(float)
    # the final projection, out of sample: the corrector trained on earlier seasons only
    gb, X = walk_forward_final(T, full * scale)
    has = np.isfinite(gb)
    w = C.GBM["weight"]
    final = np.where(has, M.blend_gbm(mu_f, np.where(has, gb, mu_f)), mu_f)
    preds["Final projection (out of sample where the corrector has an earlier season to learn from)"] = pd.Series(final, index=T.index)

    table = []
    for name, p in preds.items():
        ok = p.notna()
        m = _metrics(a[ok], p[ok])
        m["predictor"] = name
        m["beats_last_game"] = int((np.abs(a[ok] - p[ok]) < np.abs(a[ok] - T["last"][ok])).sum())
        table.append(m)
    table.sort(key=lambda r: r["mae"])

    by_season = []
    for s in sorted(T.season.unique()):
        idx = T.season == s
        for name in ["Season average", "Factor model", "Last game"]:
            p = preds[name][idx]
            ok = p.notna()
            m = _metrics(a[idx][ok], p[ok])
            m.update(season=int(s), predictor=name)
            by_season.append(m)

    share = M.share_pred(T).fillna(T.pct_prev).fillna(1.0).values
    tests = factor_tests(T, full.values.astype(float), weeks, share)

    # the corrector, fold by fold, and the test that the final projection beats the factor model it is built on
    gbm_rows, final_block = [], dict(weight=w, folds=[])
    for S in sorted(T.season[has].unique()):
        sel = has & (T.season == S).values
        fm, gm = _metrics(y[sel], mu_f[sel]), _metrics(y[sel], final[sel])
        gbm_rows += [dict(predictor=f"Factor model, {int(S)} fold", **fm), dict(predictor=f"{int(w * 100)}% boosted corrector blend, {int(S)} fold (trained on earlier seasons)", **gm)]
        final_block["folds"].append(dict(season=int(S), n=int(sel.sum()), factor=fm, final=gm))
    if has.any():
        d_ = deviance(y, final) - deviance(y, mu_f)
        m_all, t_all, k_all = paired(d_[has], weeks[has])
        st = has & (share >= C.REGULAR_SHARE)                 # the regulars: the players the books post lines on
        m_st, t_st, _ = paired(d_[st], weeks[st]) if st.sum() >= 30 else (None, None, 0)
        final_block.update(n=int(has.sum()), weeks=k_all, final_minus_factor=m_all, t=t_all, starters_n=int(st.sum()), starters_final_minus_factor=m_st, starters_t=t_st,
                           bias=float(np.mean((y - final)[has])), starters_bias=float(np.mean((y - final)[st])) if st.any() else None, regular_share=C.REGULAR_SHARE,
                           starters_by_season=[dict(season=int(S), n=int((st & (T.season == S).values).sum()), bias=float(np.mean((y - final)[st & (T.season == S).values])),
                                                    deviance=float(np.mean(deviance(y, final)[st & (T.season == S).values]))) for S in sorted(T.season[st].unique())])

    # the spread, fitted by maximum likelihood around the projection the pricer uses. Rows with an out-of-sample corrector
    # when there are enough of them; else every row around the factor model (a first season, or the synthetic league)
    use = has if has.sum() >= 2000 else np.ones(len(T), dtype=bool)
    ratio = np.clip(final / np.clip(mu_f, 1e-6, None), 0.5, 2.0)
    solo_raw = full_solo.values.astype(float) * ratio              # the solo projection moves in step with the combined one
    ok_s = np.isfinite(solo_raw) & use
    phi_by_group, phi_rows = {}, []
    phi_by_group["__scale_solo__"] = float(np.clip(T.solo_t.values[ok_s].sum() / max(1e-9, float(solo_raw[ok_s].sum())), 0.9, 1.1))
    solo_scale = pd.Series(phi_by_group["__scale_solo__"], index=T.index)
    for g, idx in T.groupby("group").groups.items():
        sel = ok_s & T.index.isin(idx)
        if sel.sum() >= 300:
            phi_by_group[f"{g}|solo_scale"] = float(np.clip(T.solo_t.values[sel].sum() / max(1e-9, float(solo_raw[sel].sum())), 0.9, 1.1))
            solo_scale[idx] = phi_by_group[f"{g}|solo_scale"]
    mu_solo = solo_raw * solo_scale.values
    Tm = T.assign(mu=final, mu_solo=mu_solo, mu_ast=np.clip(final - mu_solo, 0.05, None), xshare=share, xuse=use)
    if "ast_t" not in Tm.columns:
        Tm["ast_t"] = Tm.comb - Tm.solo_t
    for g, part in Tm[Tm.xuse].groupby("group"):
        for stat, col, mucol, floor in (("", "comb", "mu", 0.5), ("|solo", "solo_t", "mu_solo", 0.3), ("|ast", "ast_t", "mu_ast", 0.3)):
            pt = part[part[mucol] > floor]
            if len(pt) < 60:
                continue
            # the base key is the regular's class (expected share at or above the split); ":low" the part-timer's
            for label, sub in (("", pt[pt.xshare >= C.PHI_SHARE_SPLIT]), (":low", pt[pt.xshare < C.PHI_SHARE_SPLIT])):
                if len(sub) < 60:
                    sub = pt if not label else sub
                if len(sub) < 60:
                    continue
                ml = fit_phi(sub[col].values, sub[mucol].values)
                raw = float(np.mean((sub[col] - sub[mucol]) ** 2 / sub[mucol]))
                key = g + label + stat
                phi_by_group[key] = float(np.clip(ml, 0.5, 2.2))
                phi_rows.append(dict(group=g + (" (expected share under 60%)" if label else "") + (" solo" if stat == "|solo" else " assists" if stat == "|ast" else ""), n=int(len(sub)), raw=raw, corrected=ml, used=phi_by_group[key]))
    for g, v in C.DEFAULT_PHI.items():
        phi_by_group.setdefault(g, v)
    # a new role: how much wider his count runs than his class's, fitted the same way (config.NEW_ROLE holds the fallback)
    fl = M.role_shift_flags(T)
    nr = fl["new_role"].values & use
    if nr.sum() >= 150:
        grp_phi = lambda stat: np.array([phi_by_group.get(f"{g}{':low' if s_ < C.PHI_SHARE_SPLIT else ''}{stat}", phi_by_group.get(g + stat, phi_by_group.get(g, 1.0))) for g, s_ in zip(T.group.values[nr], share[nr])])
        for key, col, mu_, stat in (("__new_role_bump__", "comb", final, ""), ("__new_role_bump_solo__", "solo_t", mu_solo, "|solo")):
            ph0 = grp_phi(stat); yy, mm = T[col].values[nr].astype(float), mu_[nr]
            best_b, best_ll = 0.0, -np.inf
            for b_ in np.arange(0.0, 1.0001, 0.05):
                ll = sum(float(_logpmf(yy[ph0 == v], mm[ph0 == v], float(v + b_)).sum()) for v in set(ph0))
                if ll > best_ll:
                    best_b, best_ll = float(b_), ll
            phi_by_group[key] = best_b
    phi_by_group["__pfr_typical__"] = M.pfr_typical(T)       # the live week's coverage factor is centred on this, not on its own roster

    ast_t = T.comb - T.solo_t
    solo_rows = [dict(predictor="Assists: final projection (combined less solo)", **_metrics(ast_t[use], (final - mu_solo)[use])),
                 dict(predictor="Assists: season average", **_metrics(ast_t, (T.comb_prev - T.solo_prev) / T.n_prev.clip(lower=1))),
                 dict(predictor="Solo tackles: final projection (solo share of the projection)", **_metrics(T.solo_t[use], mu_solo[use])),
                 dict(predictor="Solo tackles: factor model without league solo drift", **_metrics(T.solo_t, M.project_frame(T, use_solo_drift=False)[2] * solo_scale.values)),
                 dict(predictor="Solo tackles: factor model", **_metrics(T.solo_t, full_solo.values * solo_scale.values)),
                 dict(predictor="Solo tackles: season average", **_metrics(T.solo_t, T.solo_prev / T.n_prev.clip(lower=1) * T.crew_solo.fillna(1.0)))]

    # calibration of over-probabilities and the shape of the distribution, around the final projection with the fitted
    # spread, on the players who get lines (expected at 60%+ of the snaps)
    def phi_for(g, s_):
        return phi_by_group.get(f"{g}:low", phi_by_group.get(g, 1.0)) if s_ < C.PHI_SHARE_SPLIT else phi_by_group.get(g, 1.0)
    sample = Tm[Tm.xuse & (Tm.mu > 0.5) & (Tm.xshare >= C.PHI_SHARE_SPLIT)]
    if len(sample) < 500:
        sample = Tm[Tm.xuse & (Tm.mu > 0.5)]
    if len(sample) > 6000:
        sample = sample.sample(6000, random_state=7)
    cal = []
    for r in sample.itertuples():
        phi = phi_for(r.group, r.xshare)
        for d in (-1.5, -0.5, 0.5, 1.5):
            line = math.floor(r.mu) + 0.5 + d
            if line < 0.5:
                continue
            cal.append((M.p_over(r.mu, phi, line), 1.0 if r.comb > line else 0.0))
    cal_rows, prob_scores = [], {}
    if cal:
        c = pd.DataFrame(cal, columns=["p", "hit"])
        prob_scores["own_lines"] = dict(n=int(len(c)), brier=float(np.mean((c.p - c.hit) ** 2)), log_loss=float(-np.mean(c.hit * np.log(c.p.clip(1e-6, 1)) + (1 - c.hit) * np.log((1 - c.p).clip(1e-6, 1)))),
                                        brier_coin=0.25)
    # probability integral transform: where the actuals fall in the model's own distribution (randomised for counts);
    # a calibrated shape puts 5% of them below its 5th percentile and 5% above its 95th, and fills the deciles evenly
    rng = np.random.default_rng(11)
    pit = []
    for r in sample.itertuples():
        phi = phi_for(r.group, r.xshare)
        k = int(r.comb); lo = (1 - M.p_over(r.mu, phi, k - 0.5)) if k > 0 else 0.0; hi = 1 - M.p_over(r.mu, phi, k + 0.5)
        pit.append(lo + rng.random() * (hi - lo))
    if pit:
        u = np.asarray(pit, dtype=float); u = u[np.isfinite(u)]
        prob_scores["pit"] = dict(n=int(len(u)), below_5=float(np.mean(u < 0.05)), above_95=float(np.mean(u > 0.95)),
                                  deciles=[float(x) for x in np.histogram(u, bins=10, range=(0, 1))[0] / len(u)])
        c["bin"] = pd.cut(c.p, [0, .2, .35, .45, .55, .65, .8, 1.0], include_lowest=True)
        for b, part in c.groupby("bin", observed=True):
            cal_rows.append(dict(bucket=str(b), n=int(len(part)), predicted=float(part.p.mean()), observed=float(part.hit.mean())))

    # regression to the mean after outlier games
    T2 = T.assign(avg=T.comb_prev_raw / T.n_prev)
    reg = []
    for label, mask in [("After a game 4+ above his average", T2["last"] - T2.avg >= 4),
                        ("After a game 3+ below his average", T2["last"] - T2.avg <= -3)]:
        part = T2[mask]
        if len(part):
            reg.append(dict(situation=label, n=int(len(part)), vs_avg=float((part.comb - part.avg).mean()),
                            vs_last=float((part.comb - part["last"]).mean())))

    # next man up: did backups with a vacated regular beat their average?
    rs = T[T.get("role_signal", False) == True]  # noqa: E712
    role = None
    if len(rs):
        avg = rs.comb_prev_raw / rs.n_prev
        role = dict(n=int(len(rs)), actual_vs_avg=float((rs.comb - avg).mean()),
                    actual_vs_avg_pct=float((rs.comb.sum() / avg.sum()) - 1))

    # where the season log stops describing a player: each situation's level against the final projection (out of sample)
    # and against the factor model alone
    weak_spots = []
    status = T.status.fillna("").astype(str).str.lower().values if "status" in T.columns else np.array([""] * len(T))
    spots = [("Next man up: a backup whose regular is out", T.get("role_signal", pd.Series(False, index=T.index)).fillna(False).astype(bool).values),
             ("Vacancy: a regular at his group out or gone, his share jumped", M.vacancy_rule(T).values),
             ("New role: part-timer who just played a starter's snaps", fl["new_role"].values),
             ("Reduced role: last game's snaps well below his season share", fl["reduced_role"].values),
             ("Back after 3+ weeks out", fl["absence"].values), ("Back after one missed game (no bye)", fl["missed_game"].values),
             ("First game for a new team", fl["new_team"].values), ("Listed questionable", status == "questionable"),
             ("Off a bye", (pd.to_numeric(T.get("rest", pd.Series(7, index=T.index)), errors="coerce").fillna(7) >= C.REST["bye_days"]).values),
             ("Regulars (expected at 80%+ of the snaps)", share >= 0.8), ("Part-timers (expected under 30%)", share < 0.3)]
    for label, sel in spots:
        sel = np.asarray(sel, dtype=bool) & use
        if sel.sum() >= 30:
            weak_spots.append(dict(situation=label, n=int(sel.sum()), actual_vs_model=float(y[sel].sum() / max(1e-9, final[sel].sum()) - 1),
                                   actual_vs_model_without=float(y[sel].sum() / max(1e-9, np.nansum(mu_f[sel])) - 1),
                                   bias=float(np.mean((y - final)[sel])), mae=float(np.mean(np.abs(y - final)[sel]))))
    new_role = next((w_ for w_ in weak_spots if w_["situation"].startswith("New role")), None)

    # what the protocol asks to be looked at (never an automatic change)
    flags = [f"{t_['factor']}: in the model and it {t_['verdict']} (t {t_['t']:+.1f} on {t_['rows']} rows)" for t_ in tests if t_["in_model"] and t_["verdict"] == "hurts"]
    flags += [f"{t_['factor']}: out of the model and a candidate again (t {t_['t']:+.1f} on {t_['rows']} rows)" for t_ in tests if not t_["in_model"] and t_["verdict"] == "candidate"]
    if final_block.get("starters_t") is not None and final_block["starters_t"] > 0:
        flags.append(f"for regulars the final projection does not beat the factor model out of sample (t {final_block['starters_t']:+.1f})")

    gbm_live = M.fit_gbm(X, T.comb)
    result = dict(seasons=[int(s) for s in seasons], games=int(len(T)), best_shrink_games=int(best_k), scale=scale,
                  predictors=table + gbm_rows + solo_rows, by_season=by_season, dispersion=phi_rows, calibration=cal_rows, prob_scores=prob_scores, scale_solo=phi_by_group["__scale_solo__"],
                  scale_solo_by_group={k.split("|")[0]: v for k, v in phi_by_group.items() if k.endswith("|solo_scale")},
                  regression=reg, role=role, new_role=new_role, weak_spots=weak_spots, factor_tests=tests, final=final_block, flags=flags,
                  design=dict(factors={k: bool(v) for k, v in C.FACTORS.items()}, corrector_weight=w, new_role_bump=phi_by_group.get("__new_role_bump__"), new_role_bump_solo=phi_by_group.get("__new_role_bump_solo__")))
    return result, phi_by_group, best_k, scale, gbm_live
