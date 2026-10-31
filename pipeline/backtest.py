"""Walk-forward backtest: every past game predicted using only what was known before it.

Reports, for each season and overall:
  - accuracy of competing predictors (season average, shrinkage levels, last game, blends, the full model,
    and the full model with each piece removed), so every piece must keep earning its place;
  - the measured spread of tackle counts (variance / mean) by position group;
  - calibration of over-probabilities across lines around each projection;
  - what follows an outlier game (regression to the mean).
"""
import math

import numpy as np
import pandas as pd

import config as C
from pipeline import model as M


def build_test_rows(H, seasons, min_prev=2, min_week=3):
    # crew columns already hold this game's crew, estimated from earlier games only (see model.prepare)
    return H[H.season.isin(seasons) & (H.n_prev >= min_prev) & (H.week >= min_week) & H.comb.notna()].copy()


def _metrics(actual, pred):
    pred = pd.Series(pred).fillna(pd.Series(actual).mean())   # an undefined prediction is scored, not dropped
    a, p = np.asarray(actual, dtype=float), np.asarray(pred, dtype=float)
    e = a - p
    # level-matched miss: the predictor scaled to zero bias first, so a piece cannot look better by shifting the level
    scale = a.sum() / p.sum() if p.sum() > 0 else 1.0
    return dict(n=int(len(e)), mae=float(np.mean(np.abs(e))), mae_cal=float(np.mean(np.abs(a - p * scale))), rmse=float(np.sqrt(np.mean(e ** 2))), bias=float(np.mean(e)))


def run_backtest(H, seasons):
    T = build_test_rows(H, seasons)
    if T.empty:
        return {"error": "No games to test yet."}, {g: v for g, v in C.DEFAULT_PHI.items()}, C.SHRINK_GAMES, 1.0, None
    a = T.comb.astype(float)
    preds = {"Season average": T.comb_prev_raw / T.n_prev}
    for k in [1, 2, 4]:
        preds[f"Season average shrunk {k} game{'s' if k > 1 else ''} toward last season"] = M.project_frame(T, k=k, use_tilt=False, use_crew=False, use_role=False)[0]
    preds["Last game"] = T["last"]
    preds["80% season average, 20% last game"] = 0.8 * (T.comb_prev_raw / T.n_prev) + 0.2 * T["last"]
    preds["Average of last two games"] = T.last2
    # choose shrinkage by MAE, then evaluate the full model and ablations with it
    shrink_opts = {0: preds["Season average"], **{k: preds[f"Season average shrunk {k} game{'s' if k > 1 else ''} toward last season"] for k in [1, 2, 4]}}
    best_k = min(shrink_opts, key=lambda k: float(np.nanmean(np.abs(a - shrink_opts[k]))))
    preds["Full model"] = M.project_frame(T)[1]
    preds["Full model with one shrink for every position"] = M.project_frame(T, k=best_k)[1]
    preds["Full model without stat crew"] = M.project_frame(T, use_crew=False)[1]
    preds["Full model without spread tilt"] = M.project_frame(T, use_tilt=False)[1]
    preds["Full model without role bump"] = M.project_frame(T, use_role=False)[1]
    preds["Full model without snap trend"] = M.project_frame(T, use_snap=False)[1]
    preds["Full model without opportunity volume"] = M.project_frame(T, use_volume=False)[1]
    preds["Full model without depth chart"] = M.project_frame(T, use_depth=False)[1]
    preds["Full model without PFR targets and missed tackles"] = M.project_frame(T, use_pfr=False)[1]
    preds["Full model without run/pass mix"] = M.project_frame(T, use_mix=False)[1]
    preds["Full model without rest days"] = M.project_frame(T, use_rest=False)[1]
    preds["Full model without injury report"] = M.project_frame(T, use_injury=False)[1]
    preds["Full model without role-shift factors"] = M.project_frame(T, use_role_shift=False)[1]
    preds["Full model without per-snap base"] = M.project_frame(T, use_persnap=False)[1]
    preds["Full model without vacancy rule"] = M.project_frame(T, use_vacancy=False)[1]
    preds["Full model without dome corners"] = M.project_frame(T, use_dome=False)[1]

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
        for name in ["Season average", "Full model", "Last game"]:
            p = preds[name][idx]
            ok = p.notna()
            m = _metrics(a[idx][ok], p[ok])
            m.update(season=int(s), predictor=name)
            by_season.append(m)

    # measured spread by group: (miss^2 - noise of the average) / mean
    full = preds["Full model"]
    full_solo = M.project_frame(T)[2]
    phi_by_group, phi_rows = {}, []
    Tm = T.assign(mu=full, mu_solo=full_solo, _share=M.share_pred(T).fillna(T.pct_prev).fillna(1.0))
    for g, part in Tm.groupby("group"):
        for stat, col, mucol, floor in (("", "comb", "mu", 0.5), ("|solo", "solo_t", "mu_solo", 0.3)):
            pt = part[part[mucol] > floor]
            if len(pt) < 60:
                continue
            for label, sub in (("", pt), (":low", pt[pt._share < C.PHI_SHARE_SPLIT])):
                if len(sub) < 60:
                    continue
                noise = sub[mucol] / (sub.n_prev + best_k)
                raw = float(np.mean((sub[col] - sub[mucol]) ** 2 / sub[mucol]))
                corr = float(np.mean(((sub[col] - sub[mucol]) ** 2 - noise) / sub[mucol]))
                key = g + label + stat
                phi_by_group[key] = float(np.clip(corr, 0.5, 2.2))
                phi_rows.append(dict(group=g + (" (expected share under 60%)" if label else "") + (" solo" if stat else ""), n=int(len(sub)), raw=raw, corrected=corr, used=phi_by_group[key]))
    # solo tackles: level calibration and an error row of their own (half the lines are solo markets)
    ok_s = full_solo.notna()
    phi_by_group["__scale_solo__"] = float(np.clip(T.solo_t[ok_s].sum() / max(1e-9, float(full_solo[ok_s].sum())), 0.9, 1.1))
    for g, part in T[ok_s].assign(_ms=full_solo[ok_s]).groupby("group"):
        if len(part) >= 300:
            phi_by_group[f"{g}|solo_scale"] = float(np.clip(part.solo_t.sum() / max(1e-9, float(part._ms.sum())), 0.9, 1.1))
    solo_rows = [dict(predictor="Solo tackles: full model (solo share of the projection)", **_metrics(T.solo_t, full_solo)),
                 dict(predictor="Solo tackles: full model without league solo drift", **_metrics(T.solo_t, M.project_frame(T, use_solo_drift=False)[2])),
                 dict(predictor="Solo tackles: season average", **_metrics(T.solo_t, T.solo_prev / T.n_prev.clip(lower=1) * T.crew_solo.fillna(1.0)))]
    for g, v in C.DEFAULT_PHI.items():
        phi_by_group.setdefault(g, v)

    # calibration of over-probabilities at lines around each projection
    cal = []
    sample = T.assign(mu=full).dropna(subset=["mu"])
    sample = sample[sample.mu > 0.5]
    if len(sample) > 4000:
        sample = sample.sample(4000, random_state=7)
    for r in sample.itertuples():
        phi = phi_by_group.get(r.group, 1.0)
        for d in (-1.5, -0.5, 0.5, 1.5):
            line = math.floor(r.mu) + 0.5 + d
            if line < 0.5:
                continue
            cal.append((M.p_over(r.mu, phi, line), 1.0 if r.comb > line else 0.0))
    cal_rows = []
    if cal:
        c = pd.DataFrame(cal, columns=["p", "hit"])
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

    # role bump subset: did backups with a vacated regular beat their average?
    rs = T[T.get("role_signal", False) == True]  # noqa: E712
    role = None
    if len(rs):
        avg = rs.comb_prev_raw / rs.n_prev
        role = dict(n=int(len(rs)), actual_vs_avg=float((rs.comb - avg).mean()),
                    actual_vs_avg_pct=float((rs.comb.sum() / avg.sum()) - 1))

    scale = float(np.clip(T.comb.sum() / max(1e-9, float(np.nansum(full))), 0.9, 1.1))   # level calibration of the full model
    # where the season log stops describing a player: each situation reported on its own, with and without its factor
    fl = M.role_shift_flags(T)
    no_nr = np.asarray(preds["Full model without per-snap base"], dtype=float)
    no_rs = np.asarray(preds["Full model without role-shift factors"], dtype=float)
    weak_spots = []
    vac = M.vacancy_rule(T).values
    no_vac = np.asarray(preds["Full model without vacancy rule"], dtype=float)
    if vac.any():
        weak_spots.append(dict(situation="Vacancy: a regular at his group out or gone, his share jumped", n=int(vac.sum()),
                               actual_vs_model=float(T.comb[vac].sum() / max(1e-9, np.nansum(full[vac])) - 1),
                               actual_vs_model_without=float(T.comb[vac].sum() / max(1e-9, np.nansum(no_vac[vac])) - 1),
                               mae=float(np.nanmean(np.abs(T.comb[vac] - full[vac])))))
    for key, label, without in (("new_role", "New role: part-timer who just played a starter's snaps", no_nr),
                                ("reduced_role", "Reduced role: last game's snaps well below his season share", no_rs),
                                ("absence", "Back after 3+ weeks out", no_rs), ("missed_game", "Back after one missed game (no bye)", no_rs),
                                ("new_team", "First game for a new team", no_rs)):
        sel = fl[key].values
        if sel.any():
            weak_spots.append(dict(situation=label, n=int(sel.sum()), actual_vs_model=float(T.comb[sel].sum() / max(1e-9, np.nansum(full[sel])) - 1),
                                   actual_vs_model_without=float(T.comb[sel].sum() / max(1e-9, np.nansum(without[sel])) - 1),
                                   mae=float(np.nanmean(np.abs(T.comb[sel] - full[sel])))))
    new_role = next((w for w in weak_spots if w["situation"].startswith("New role")), None)
    # second model, reported honestly: trained on all seasons but the latest, scored on the latest; then trained on everything for live use
    gbm_rows, gbm_live = [], None
    last = max(seasons)
    X = M.gbm_features(T, full * scale)
    if (T.season < last).sum() > 2000 and (T.season == last).sum() > 200:
        fold = M.fit_gbm(X[T.season < last], T.comb[T.season < last])
        if fold is not None:
            sel = (T.season == last).values
            fm, gm = _metrics(T.comb[sel], (full * scale)[sel]), _metrics(T.comb[sel], M.blend_gbm((full * scale)[sel], fold(X[sel])))
            gbm_rows = [dict(predictor=f"Full model, {last} fold", **fm), dict(predictor=f"{int(C.GBM['weight'] * 100)}% boosted corrector blend, {last} fold (trained on earlier seasons)", **gm)]
    gbm_live = M.fit_gbm(X, T.comb)
    result = dict(seasons=[int(s) for s in seasons], games=int(len(T)), best_shrink_games=int(best_k), scale=scale,
                  predictors=table + gbm_rows + solo_rows, by_season=by_season, dispersion=phi_rows, calibration=cal_rows, scale_solo=phi_by_group["__scale_solo__"],
                  scale_solo_by_group={k.split("|")[0]: v for k, v in phi_by_group.items() if k.endswith("|solo_scale")},
                  regression=reg, role=role, new_role=new_role, weak_spots=weak_spots)
    return result, phi_by_group, best_k, scale, gbm_live
