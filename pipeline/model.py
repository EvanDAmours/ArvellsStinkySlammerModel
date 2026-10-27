"""Projection model and bet pricing.

What the model does (each piece was tested walk-forward before it was kept):
  1. Season-to-date tackles per game, shrunk lightly toward last season's rate (or a position prior).
  2. A small point-spread tilt: underdog defenses stay on the field longer.
  3. Stat-crew factor for the stadium: crews that split tackles into assists raise combined
     tackles and cut solos. Every venue's rate is measured from the data itself.
  4. A role bump for a backup when a regular at his position group is out.
  5. A count distribution tighter than Poisson for linebackers (measured), used to price lines.
"""
import math

import numpy as np
import pandas as pd

import config as C

TEAM_NAMES = {
    "ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens", "BUF": "Buffalo Bills",
    "CAR": "Carolina Panthers", "CHI": "Chicago Bears", "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns",
    "DAL": "Dallas Cowboys", "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
    "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars", "KC": "Kansas City Chiefs",
    "LV": "Las Vegas Raiders", "LAC": "Los Angeles Chargers", "LA": "Los Angeles Rams", "LAR": "Los Angeles Rams",
    "MIA": "Miami Dolphins", "MIN": "Minnesota Vikings", "NE": "New England Patriots", "NO": "New Orleans Saints",
    "NYG": "New York Giants", "NYJ": "New York Jets", "PHI": "Philadelphia Eagles", "PIT": "Pittsburgh Steelers",
    "SF": "San Francisco 49ers", "SEA": "Seattle Seahawks", "TB": "Tampa Bay Buccaneers", "TEN": "Tennessee Titans",
    "WAS": "Washington Commanders",
}
OUT_STATUSES = {"out", "doubtful", "ir", "injured reserve", "pup", "suspended"}


# ---------------------------------------------------------------- distribution
def p_over(mu, phi, line):
    """P(X > line) for a count with mean mu and variance phi*mu."""
    if mu is None or not np.isfinite(mu) or mu <= 0:
        return float("nan")
    k0 = int(math.floor(line))
    if phi < 0.98:                         # tighter than Poisson: binomial
        n = max(math.ceil(mu / (1 - phi)), math.ceil(mu) + 1)
        p = mu / n
        pmf = (1 - p) ** n
        cdf = pmf
        for k in range(1, k0 + 1):
            pmf *= (n - k + 1) / k * (p / (1 - p))
            cdf += pmf
    elif phi > 1.02:                       # looser than Poisson: negative binomial
        r, q = mu / (phi - 1), 1 - 1 / phi
        pmf = (1 / phi) ** r
        cdf = pmf
        for k in range(1, k0 + 1):
            pmf *= (k - 1 + r) / k * q
            cdf += pmf
    else:                                  # Poisson
        pmf = math.exp(-mu)
        cdf = pmf
        for k in range(1, k0 + 1):
            pmf *= mu / k
            cdf += pmf
    return min(1.0, max(0.0, 1 - cdf))


def fair_line(mu, phi):
    lines = [x + 0.5 for x in range(0, 25)]
    return min(lines, key=lambda L: abs(p_over(mu, phi, L) - 0.5))


def american_to_decimal(a):
    a = float(a)
    return 1 + a / 100 if a > 0 else 1 + 100 / abs(a)


# ---------------------------------------------------------------- assembling history
def team_games(sched):
    base = ["game_id", "season", "week", "gameday", "gametime", "home_score", "location", "spread_line", "total_line"]
    sched = sched.copy()
    for c in ("home_rest", "away_rest"):
        if c not in sched.columns:
            sched[c] = 7
    h = sched[base + ["home_team", "away_team", "home_rest"]].rename(columns={"home_team": "team", "away_team": "opp_team", "home_rest": "rest"}).assign(is_home=True)
    a = sched[base + ["home_team", "away_team", "away_rest"]].rename(columns={"away_team": "team", "home_team": "opp_team", "away_rest": "rest"}).assign(is_home=False)
    tg = pd.concat([h, a], ignore_index=True)
    neutral = tg.location.str.lower().str.startswith("neutral")
    tg["venue"] = np.where(neutral, "NEUTRAL", np.where(tg.is_home, tg.team, tg.opp_team))
    # underdog-positive spread for the DEFENSE's team (nflverse: positive spread_line = home favored)
    tg["spread_dog"] = np.where(tg.is_home, -tg.spread_line, tg.spread_line)
    tg["final"] = tg.home_score.notna()
    return tg


def prepare(pw, sched, snaps):
    """One row per defender-game with game context, snaps, and zero-tackle games filled in."""
    tg = team_games(sched)
    pw = pw.copy()
    # add games a defender played (per snap counts) without recording a tackle, so averages aren't inflated
    if len(snaps):
        # names that are ambiguous within a team-week can't be matched safely: drop them rather than duplicate rows
        snaps = snaps.drop_duplicates(["season", "week", "team", "name_key"], keep=False)
        dup_names = pw.duplicated(["season", "week", "team", "name_key"], keep=False)
        sn = snaps[snaps.def_snaps >= 10]
        ids = pw.drop_duplicates(["season", "team", "name_key"])[["season", "team", "name_key", "player_id", "player", "group"]]
        have = pw[["season", "week", "team", "name_key"]].drop_duplicates()
        miss = sn.merge(have, on=["season", "week", "team", "name_key"], how="left", indicator=True)
        miss = miss[miss._merge == "left_only"].drop(columns=["_merge"]).merge(ids, on=["season", "team", "name_key"], how="inner")
        if len(miss):
            for c in ["comb", "solo_t", "solo", "ast", "with_ast"]:
                miss[c] = 0
            pw = pd.concat([pw, miss[[c for c in pw.columns if c in miss.columns]]], ignore_index=True)
        pw = pw.merge(snaps[["season", "week", "team", "name_key", "def_pct", "def_snaps"]], on=["season", "week", "team", "name_key"], how="left")
        pw.loc[pw.index.isin(dup_names[dup_names].index), ["def_pct", "def_snaps"]] = np.nan
    else:
        pw["def_pct"], pw["def_snaps"] = np.nan, np.nan
    keep = ["season", "week", "team", "game_id", "venue", "spread_dog", "is_home", "opp_team", "gameday", "gametime", "final", "rest"]
    pw = pw.drop_duplicates(["player_id", "season", "week"], keep="first")
    H = pw.merge(tg[keep].drop_duplicates(["season", "week", "team"]), on=["season", "week", "team"], how="inner")
    H["ast_t"] = H.comb - H.solo_t
    # each game's stat crew, estimated only from games before it; then remove it so averages are crew-neutral
    H = attach_crews(H, H)
    H["comb_adj"] = H.comb / H.crew_comb
    H["solo_adj"] = H.solo_t / H.crew_solo
    return H.sort_values(["player_id", "season", "week"]).reset_index(drop=True)


# ---------------------------------------------------------------- tackle opportunities (volume)
def volume_table(vol):
    """Per team-game, the prior-games means (this season, shifted) and last season's mean of opportunities faced
    by the defence and generated by the offence."""
    if vol is None or len(vol) == 0:
        return None
    v = vol.sort_values(["season", "week"]).copy()
    for col in [c for c in ("faced", "gen", "faced_runs", "gen_runs", "faced_comps", "gen_comps") if c in v.columns]:
        g = v.groupby(["team", "season"], sort=False)[col]
        v[f"{col}_prev"] = g.transform(lambda x: x.shift(1).expanding().mean())
        v[f"{col}_n"] = g.cumcount()
        ps = v.groupby(["team", "season"])[col].mean().reset_index()
        ps["season"] += 1
        v = v.merge(ps.rename(columns={col: f"{col}_ps"}), on=["team", "season"], how="left")
    v.attrs["league"] = float(vol.faced.mean())
    return v


def _shrink(x, n, prior, m):
    x = x.fillna(prior)
    n = n.fillna(0)
    return (x * n + prior * m) / (n + m)


def expected_stat(frame, V, stat=""):
    """Expected value of a faced/generated stat for each row's game (opportunities, run plays, completions): the
    defence's faced average and the opponent's generated average, each shrunk toward last season (or the league)."""
    f, g = ("faced" + ("_" + stat if stat else ""), "gen" + ("_" + stat if stat else ""))
    if f + "_prev" not in V.columns:
        return np.full(len(frame), np.nan)
    lg = float(V[f].mean()) if stat else V.attrs.get("league", 50.0)
    m = C.VOLUME["pseudo_games"]
    d = frame[["season", "week", "team", "opp_team"]].merge(V[["season", "week", "team", f + "_prev", f + "_n", f + "_ps"]], on=["season", "week", "team"], how="left")
    d = d.merge(V[["season", "week", "team", g + "_prev", g + "_n", g + "_ps"]].rename(columns={"team": "opp_team"}), on=["season", "week", "opp_team"], how="left")
    return ((_shrink(d[f + "_prev"], d[f + "_n"], d[f + "_ps"].fillna(lg), m) + _shrink(d[g + "_prev"], d[g + "_n"], d[g + "_ps"].fillna(lg), m)) / 2).values


def expected_opps(frame, V):
    return expected_stat(frame, V, "")


def attach_volume(H, vol):
    """Add each game's opportunities faced (opps) and the pre-game expectation (exp_opps) to defender rows."""
    V = volume_table(vol)
    H = H.copy()
    if V is None:
        H["opps"], H["exp_opps"] = np.nan, np.nan
        return H
    H = H.merge(V[["season", "week", "team", "faced"]].rename(columns={"faced": "opps"}), on=["season", "week", "team"], how="left")
    H["exp_opps"] = expected_opps(H, V)
    H["exp_runs"], H["exp_comps"] = expected_stat(H, V, "runs"), expected_stat(H, V, "comps")
    return H


def attach_extras(H, pbp=None, pfr=None, dc=None):
    """Per-game run/pass tackle credits, PFR targets and missed tackles, and depth-chart status on defender rows."""
    H = H.copy()
    if pbp is not None and len(pbp["players"]):
        H = H.merge(pbp["players"], on=["season", "week", "player_id"], how="left")
        H = H.merge(pbp["teams"], on=["season", "week", "team"], how="left")
        H[["run_tk", "pass_tk"]] = H[["run_tk", "pass_tk"]].fillna(0)      # no credit row means no tackle credits, not unknown
    for c in ("run_tk", "pass_tk", "runs_faced", "comps_faced"):
        if c not in H.columns:
            H[c] = np.nan
    if pfr is not None and len(pfr):
        H = H.merge(pfr, on=["season", "week", "team", "name_key"], how="left")
    for c in ("targets", "missed", "pfr_comb"):
        if c not in H.columns:
            H[c] = np.nan
    H["dc_starter"] = np.nan
    if dc is not None and len(dc):
        from pipeline.sources import starters_for
        flags = {}
        for (sn, wk, tm, gd), idx in H.groupby(["season", "week", "team", "gameday"]).groups.items():
            st = starters_for(dc, sn, wk, tm, gd)
            if st is not None:
                flags.update({i: (H.at[i, "player_id"] in st) for i in idx})
        H["dc_starter"] = pd.Series(flags, dtype="float")
    return H


def volume_prior_for_week(vol, season, week):
    """The same expectation for games not yet played: a per-team frame of prior means this season and last."""
    V = volume_table(vol)
    if V is None:
        return None
    rows = []
    lg = V.attrs.get("league", 50.0)
    for team in sorted(set(V.team)):
        cur = V[(V.season == season) & (V.team == team) & (V.week < week)]
        prev = V[(V.season == season - 1) & (V.team == team)]
        rows.append(dict(team=team, faced_prev=cur.faced.mean() if len(cur) else np.nan, faced_n=len(cur),
                         faced_ps=prev.faced.mean() if len(prev) else lg, gen_prev=cur.gen.mean() if len(cur) else np.nan,
                         gen_n=len(cur), gen_ps=prev.gen.mean() if len(prev) else lg))
    out = pd.DataFrame(rows)
    out.attrs["league"] = lg
    return out


def add_history_features(H):
    H = H.sort_values(["player_id", "season", "week"]).copy()
    g = H.groupby(["player_id", "season"], sort=False)
    H["n_prev"] = g.cumcount()
    H["pct_last3"] = g.def_pct.transform(lambda x: x.shift(1).rolling(C.SNAP_TREND["games"], min_periods=1).mean())
    if "opps" in H.columns:
        H["opps_prev_mean"] = g.opps.transform(lambda x: x.shift(1).expanding().mean())
    else:
        H["opps_prev_mean"] = np.nan
    for c in ("run_tk", "pass_tk", "runs_faced", "comps_faced", "targets", "missed", "pfr_comb"):
        H[c + "_prev"] = g[c].transform(lambda x: x.shift(1).expanding().sum()) if c in H.columns else np.nan
    if "dc_starter" in H.columns:
        prev = g.dc_starter.shift(1)
        H["promoted"] = (H.dc_starter == 1) & (prev == 0)
        H["demoted"] = (H.dc_starter == 0) & (prev == 1)
    else:
        H["promoted"], H["demoted"] = False, False
    H["comb_prev_raw"] = g.comb.cumsum() - H.comb
    H["comb_prev"] = g.comb_adj.cumsum() - H.comb_adj
    H["solo_prev"] = g.solo_adj.cumsum() - H.solo_adj
    H["last"] = g.comb.shift(1)
    H["last2"] = g.comb.transform(lambda x: x.shift(1).rolling(2).mean())
    H["pct_prev"] = g.def_pct.transform(lambda x: x.shift(1).expanding().mean())
    H["pct_last"] = g.def_pct.shift(1)
    ps = H.groupby(["player_id", "season"]).agg(ps_games=("comb", "size"), ps_avg=("comb_adj", "mean"),
                                                 ps_avg_raw=("comb", "mean")).reset_index()
    ps["season"] += 1
    return H.merge(ps, on=["player_id", "season"], how="left")


# ---------------------------------------------------------------- stat crews
def crew_factors(H, season, week):
    """Each venue's solo share, measured from last season plus this season before `week`, shrunk to league."""
    prev = H[H.season == season - 1]
    cur = H[(H.season == season) & (H.week < week)]
    pool = pd.concat([prev, cur])
    if pool.empty:
        return {}, 0.56
    lg_s = pool.solo_t.sum() / max(1.0, pool.comb.sum())
    by = pool.groupby("venue").agg(S=("solo_t", "sum"), T=("comb", "sum"))
    m = C.CREW_PSEUDO_TACKLES
    share = ((by.S + m * lg_s) / (by["T"] + m)).to_dict()
    return share, lg_s


def crew_multipliers(share, lg_s):
    a = (1 - share) / (1 + share)
    a_lg = (1 - lg_s) / (1 + lg_s)
    return (1 + a) / (1 + a_lg), (1 - a) / (1 - a_lg)


def attach_crews(df, H, season_col="season", week_col="week"):
    out = []
    for (s, w), part in df.groupby([season_col, week_col]):
        share, lg = crew_factors(H, s, w)
        sh = part.venue.map(share).fillna(lg)
        comb_m, solo_m = crew_multipliers(sh, lg)
        part = part.assign(crew_share=sh.values, crew_comb=comb_m.values, crew_solo=solo_m.values)
        part.loc[part.venue == "NEUTRAL", ["crew_comb", "crew_solo"]] = 1.0
        out.append(part)
    return pd.concat(out) if out else df.assign(crew_share=np.nan, crew_comb=1.0, crew_solo=1.0)


# ---------------------------------------------------------------- role changes
def role_signals_backtest(H):
    """Flag a backup when a teammate at his position group played 75%+ of snaps last game but is absent this week.
    (Inactive lists are public 90 minutes before kickoff, so this is information a bettor has in time.)"""
    H = H.copy()
    nz = lambda x: x if x == x and x is not None else 0.0  # NaN-safe
    present = H.groupby(["season", "team", "week"]).player_id.apply(set).to_dict()
    pct = {(r.season, r.team, r.week, r.player_id): nz(r.def_pct) for r in H.itertuples()}
    group = dict(zip(H.player_id, H.group))
    team_weeks = H.groupby(["season", "team"]).week.apply(lambda x: sorted(set(x))).to_dict()
    vacated = set()
    for (s, t), weeks in team_weeks.items():
        for i in range(1, len(weeks)):
            w, wp = weeks[i], weeks[i - 1]
            for pid in present.get((s, t, wp), set()) - present.get((s, t, w), set()):
                if pct.get((s, t, wp, pid), 0) >= 0.75:
                    vacated.add((s, t, w, group.get(pid)))
    H["role_signal"] = [((s, t, w, g) in vacated) and nz(pp) < 0.75
                        for s, t, w, g, pp in zip(H.season, H.team, H.week, H.group, H.pct_prev)]
    return H


# ---------------------------------------------------------------- projections
def snap_trend_factor(F):
    """Recent snap share vs season share, damped: rises ** power_up, drops ** power_down."""
    t = C.SNAP_TREND
    ok = F.pct_prev.notna() & (F.pct_prev > t["min_share"]) & F.get("pct_last3", pd.Series(np.nan, index=F.index)).notna()
    ratio = (F.pct_last3 / F.pct_prev).where(ok, 1.0).clip(*t["cap"])
    power = np.where(ratio >= 1, t["power_up"], t["power_down"])
    return pd.Series(np.power(ratio.values, power), index=F.index)


def volume_factor(F):
    """Expected opportunities this game vs the ones the player has faced, damped and capped."""
    v = C.VOLUME
    if "exp_opps" not in F or "opps_prev_mean" not in F:
        return pd.Series(1.0, index=F.index)
    ratio = (F.exp_opps / F.opps_prev_mean).where(F.exp_opps.notna() & F.opps_prev_mean.notna() & (F.opps_prev_mean > 0), 1.0)
    return (ratio ** v["power"]).clip(*v["cap"])


def depth_factor(F):
    d = C.DEPTH
    dem = F["demoted"].fillna(False).astype(bool) if "demoted" in F else pd.Series(False, index=F.index)
    pro = F["promoted"].fillna(False).astype(bool) if "promoted" in F else pd.Series(False, index=F.index)
    return pd.Series(np.where(dem, d["demoted"], np.where(pro, d["promoted"], 1.0)), index=F.index)


def pfr_factor(F):
    """Coverage usage (targets per game, DBs only) and missed-tackle rate, both from PFR, vs typical."""
    c = C.PFR
    n = F.n_prev.astype(float).clip(lower=1)
    out = pd.Series(1.0, index=F.index)
    if "targets_prev" in F:
        db = F.group.isin(["CB", "S"]) & F.targets_prev.notna()
        rate = (F.targets_prev / n).where(db)
        typical = float(rate[db].mean()) if db.any() else np.nan
        if typical and typical > 0:
            tgt = (1 + c["target_slope"] * (rate / typical - 1)).clip(*c["target_cap"]).where(db, 1.0)
            out = out * tgt.fillna(1.0)
    if "missed_prev" in F and "pfr_comb_prev" in F:
        tot = (F.pfr_comb_prev.fillna(0) + F.missed_prev.fillna(0))
        rate = (F.missed_prev / tot.clip(lower=1)).where(tot >= 5)
        miss = (1 + c["miss_slope"] * (rate - c["miss_base"])).clip(*c["miss_cap"]).fillna(1.0)
        out = out * miss
    return out.fillna(1.0)


def mix_factor(F):
    """Opponent run/pass mix this game vs what the player has faced, through his own run- and pass-tackle rates."""
    c = C.MIX
    need = ["run_tk_prev", "pass_tk_prev", "runs_faced_prev", "comps_faced_prev", "exp_runs", "exp_comps"]
    if any(col not in F for col in need):
        return pd.Series(1.0, index=F.index)
    ok = (F.runs_faced_prev > 0) & (F.comps_faced_prev > 0) & F.exp_runs.notna() & F.exp_comps.notna()
    n = F.n_prev.astype(float).clip(lower=1)
    run_rate, pass_rate = F.run_tk_prev / F.runs_faced_prev.clip(lower=1), F.pass_tk_prev / F.comps_faced_prev.clip(lower=1)
    split = run_rate * F.exp_runs + pass_rate * F.exp_comps
    neutral = run_rate * (F.runs_faced_prev / n) + pass_rate * (F.comps_faced_prev / n)
    ratio = (split / neutral.clip(lower=0.1)).where(ok, 1.0).clip(*c["cap"]) ** c["power"]
    return (1 + c["weight"] * (ratio - 1)).fillna(1.0)


def injury_factor(F):
    """Listed questionable (and expected to play) or limited in practice: a few percent under his average."""
    c = C.INJURY
    status = F["status"].fillna("").astype(str).str.lower() if "status" in F else pd.Series("", index=F.index)
    practice = F["practice"].fillna("").astype(str).str.lower() if "practice" in F else pd.Series("", index=F.index)
    f = np.where(status == "questionable", c["questionable"], 1.0) * np.where(practice.str.startswith("limited"), c["limited_practice"], 1.0)
    return pd.Series(f, index=F.index)


def attach_injury_status(H, inj):
    """Each defender-game's own report status and practice status that week (for the backtest of the injury factor)."""
    H = H.copy()
    if inj is None or len(inj) == 0:
        H["status"], H["practice"] = "", ""
        return H
    cols = ["season", "week", "team", "name_key", "status"] + (["practice"] if "practice" in inj.columns else [])
    i = inj.drop_duplicates(["season", "week", "team", "name_key"])[cols]
    H = H.merge(i, on=["season", "week", "team", "name_key"], how="left")
    H["status"] = H.status.fillna("")
    H["practice"] = H["practice"].fillna("") if "practice" in H.columns else ""
    return H


def rest_factor(F):
    r = C.REST
    return pd.Series(np.where(F.get("rest", pd.Series(7, index=F.index)).fillna(7) >= r["bye_days"], r["bye"], 1.0), index=F.index)


def project_frame(F, k=None, use_tilt=True, use_crew=True, use_role=True, use_snap=True, use_volume=True, use_depth=True, use_pfr=True, use_mix=True, use_rest=True, use_injury=True):
    k = F.group.map(C.SHRINK_GAMES_BY_GROUP).fillna(C.SHRINK_GAMES) if k is None else k
    if use_crew:
        prev, ps = F.comb_prev, F.ps_avg
    else:
        prev, ps = F.comb_prev_raw, F.ps_avg_raw
    prior = np.where(F.ps_games.fillna(0) >= 4, ps, F.group.map(C.POS_PRIOR).fillna(4.0))
    n = F.n_prev.astype(float)
    base = np.where(n + k > 0, (prev + k * prior) / np.maximum(n + k, 1e-9), prior)
    tilt = 1 + np.clip(C.SPREAD_TILT * F.spread_dog.fillna(0), -C.SPREAD_TILT_CAP, C.SPREAD_TILT_CAP) if use_tilt else 1.0
    crew_c = F.crew_comb.fillna(1.0) if use_crew and "crew_comb" in F else 1.0
    crew_s = F.crew_solo.fillna(1.0) if use_crew and "crew_solo" in F else 1.0
    role = np.where(F.get("role_signal", False) == True, C.ROLE_BUMP, 1.0) if use_role else 1.0  # noqa: E712
    snap = snap_trend_factor(F).values if use_snap else 1.0
    volume = volume_factor(F).values if use_volume else 1.0
    extra = 1.0
    if use_depth:
        extra = extra * depth_factor(F).values
    if use_pfr:
        extra = extra * pfr_factor(F).values
    if use_mix:
        extra = extra * mix_factor(F).values
    if use_rest:
        extra = extra * rest_factor(F).values
    if use_injury:
        extra = extra * injury_factor(F).values
    solo_share = (F.solo_prev + 8 * F.group.map(C.POS_SOLO_SHARE).fillna(0.6)) / (F.comb_prev + 8)
    mu = base * tilt * crew_c * role * snap * volume * extra
    mu_solo = base * tilt * solo_share * crew_s * role * snap * volume * extra
    return pd.Series(base, index=F.index), pd.Series(mu, index=F.index), pd.Series(mu_solo, index=F.index)


def upcoming_rows(H, sched, injuries, season, week, vol=None, dc=None, pbp_starters=None):
    """Feature rows for every active defender whose team plays in `week`: anyone with a game in the last four
    weeks, plus anyone listed as a starter on the current depth chart (a starter back from injury)."""
    tg = team_games(sched)
    games = tg[(tg.season == season) & (tg.week == week)]
    done = H[(H.season == season) & (H.week < week)]
    if done.empty:
        return pd.DataFrame()
    recent = done[done.week >= week - 4]
    active = recent.drop_duplicates("player_id")[["player_id"]]
    starters = {}
    if dc is not None and len(dc):
        from pipeline.sources import starters_for
        for r in games.itertuples():
            st = starters_for(dc, season, week, r.team, r.gameday)
            if st:
                starters[r.team] = st
    if starters:
        listed = {pid for ids in starters.values() for pid in ids}
        back = done[done.player_id.isin(listed) & ~done.player_id.isin(active.player_id)].drop_duplicates("player_id")[["player_id"]]
        active = pd.concat([active, back], ignore_index=True)
    sums = {c: (c, "sum") for c in ("run_tk", "pass_tk", "runs_faced", "comps_faced", "targets", "missed", "pfr_comb") if c in done.columns}
    agg = done.groupby("player_id").agg(
        player=("player", "last"), name_key=("name_key", "last"), team=("team", "last"), group=("group", "last"),
        n_prev=("comb", "size"), comb_prev=("comb_adj", "sum"), comb_prev_raw=("comb", "sum"),
        solo_prev=("solo_adj", "sum"), pct_prev=("def_pct", "mean"), **sums).reset_index()
    agg = agg.rename(columns={c: c + "_prev" for c in sums})
    last_dc = done.sort_values("week").groupby("player_id").dc_starter.last() if "dc_starter" in done.columns else None
    lasts = done.sort_values("week").groupby("player_id").agg(last=("comb", "last"), pct_last=("def_pct", "last"))
    last2 = done.sort_values("week").groupby("player_id").comb.apply(lambda x: x.tail(2).mean() if len(x) >= 2 else np.nan).rename("last2")
    pct_last3 = done.sort_values("week").groupby("player_id").def_pct.apply(lambda x: x.tail(C.SNAP_TREND["games"]).mean()).rename("pct_last3")
    opps_prev = (done.groupby("player_id").opps.mean().rename("opps_prev_mean") if "opps" in done.columns
                 else pd.Series(dtype=float, name="opps_prev_mean"))
    F = agg.merge(active, on="player_id").join(lasts, on="player_id").join(last2, on="player_id").join(pct_last3, on="player_id").join(opps_prev, on="player_id")
    ps = H[H.season == season - 1].groupby("player_id").agg(ps_games=("comb", "size"), ps_avg=("comb_adj", "mean"),
                                                            ps_avg_raw=("comb", "mean"))
    F = F.join(ps, on="player_id")
    F = F.merge(games[["team", "game_id", "venue", "spread_dog", "is_home", "opp_team", "gameday", "gametime", "final", "rest"]], on="team", how="inner")
    F["season"], F["week"] = season, week
    F = attach_crews(F, H)
    V = volume_table(vol) if vol is not None else None
    if V is not None and len(V):
        Fv = F.assign(season=season, week=week)
        Vw = V[V.season == season]
        # a synthetic row per team for this week: prior means over played games, last season's mean as the prior
        rows = []
        for team in sorted(set(V.team)):
            cur, prev = Vw[(Vw.team == team) & (Vw.week < week)], V[(V.season == season - 1) & (V.team == team)]
            r = dict(season=season, week=week, team=team)
            for col in [c for c in ("faced", "gen", "faced_runs", "gen_runs", "faced_comps", "gen_comps") if c in V.columns]:
                r[col + "_prev"] = cur[col].mean() if len(cur) else np.nan
                r[col + "_n"] = len(cur)
                r[col + "_ps"] = prev[col].mean() if len(prev) else np.nan
            rows.append(r)
        Vt = pd.DataFrame(rows)
        for col in [c for c in ("faced", "gen", "faced_runs", "gen_runs", "faced_comps", "gen_comps") if c in V.columns]:
            Vt[col] = np.nan
        Vt.attrs["league"] = V.attrs.get("league", 50.0)
        for c in [c for c in ("faced", "faced_runs", "faced_comps") if c in V.columns]:
            Vt[c] = V[c].mean()   # league level for the shrink target when there is no last season
        F["exp_opps"] = expected_stat(Fv, Vt, "")
        F["exp_runs"], F["exp_comps"] = expected_stat(Fv, Vt, "runs"), expected_stat(Fv, Vt, "comps")
    else:
        F["exp_opps"], F["exp_runs"], F["exp_comps"] = np.nan, np.nan, np.nan
    # depth chart: starter now vs his last game; the opponent's starting QB / RB listed out
    F["dc_starter"] = [((pid in starters[t]) if t in starters else np.nan) for pid, t in zip(F.player_id, F.team)]
    prev_dc = F.player_id.map(last_dc) if last_dc is not None else pd.Series(np.nan, index=F.index)
    F["promoted"] = (F.dc_starter == 1) & (prev_dc == 0)
    F["demoted"] = (F.dc_starter == 0) & (prev_dc == 1)
    F["dc_status"] = np.where(F.promoted, "promoted", np.where(F.demoted, "demoted", np.where(F.dc_starter == 1, "starter", "")))
    inj_w = injuries[(injuries.season == season) & (injuries.week == week)] if len(injuries) else injuries
    out_ids = set(inj_w[inj_w.status.str.lower().isin(["out", "doubtful"])].player_id.astype(str)) if len(inj_w) and "player_id" in inj_w else set()
    F["opp_qb_out"], F["opp_rb_out"] = False, False
    if pbp_starters is not None and len(pbp_starters):
        latest = pbp_starters[pbp_starters.season == season].sort_values("week").groupby("team").last()
        F["opp_qb_out"] = [str(latest.qb1.get(o, "")) in out_ids for o in F.opp_team]
        F["opp_rb_out"] = [str(latest.rb1.get(o, "")) in out_ids for o in F.opp_team]
    # injuries for this week: own status, and role signal when a regular at his position group is out
    inj = injuries[(injuries.season == season) & (injuries.week == week)] if len(injuries) else injuries
    status = {(r.team, r.name_key): r.status for r in inj.itertuples()} if len(inj) else {}
    practice = {(r.team, r.name_key): getattr(r, "practice", "") for r in inj.itertuples()} if len(inj) else {}
    F["status"] = [status.get((t, n), "") for t, n in zip(F.team, F.name_key)]
    F["practice"] = [practice.get((t, n), "") for t, n in zip(F.team, F.name_key)]
    out_keys = {(t, n) for (t, n), s in status.items() if str(s).lower() in OUT_STATUSES}
    regs = F[(F.pct_prev >= 0.75) & (F.n_prev >= 2)]
    vacated = {(r.team, r.group) for r in regs.itertuples() if (r.team, r.name_key) in out_keys}
    F["role_signal"] = [((t, g) in vacated) and not (p >= 0.75) and (t, n) not in out_keys
                        for t, g, p, n in zip(F.team, F.group, F.pct_prev.fillna(0), F.name_key)]
    return F


def finalize_projections(F, phi_by_group, k=None, scale=1.0, gbm=None):
    """scale: the backtest's level calibration (actual / predicted), applied to the projected means.
    gbm: the trained corrector's predict function; its blend moves the combined projection and the solo one in step."""
    if F.empty:
        return F
    base, mu, mu_solo = project_frame(F, k=k)
    mu, mu_solo = mu * scale, mu_solo * scale
    if gbm is not None:
        g = gbm(gbm_features(F, mu))
        blended = pd.Series(blend_gbm(mu, g), index=F.index)
        ratio = (blended / mu.clip(lower=1e-6)).clip(0.5, 2.0)
        F = F.assign(proj_factor=mu.values, proj_gbm=np.asarray(g))
        mu, mu_solo = blended, mu_solo * ratio
    F = F.assign(base=base.values, proj=mu.values, proj_solo=mu_solo.values)
    F["phi"] = F.group.map(phi_by_group).fillna(1.0)
    F.loc[F.venue == "NEUTRAL", "phi"] = F.phi + 0.15
    F["fair_line"] = [fair_line(m, p) for m, p in zip(F.proj, F.phi)]
    F["fair_line_solo"] = [fair_line(m, p) for m, p in zip(F.proj_solo, F.phi)]
    F["season_avg"] = F.comb_prev_raw / F.n_prev.clip(lower=1)
    return F


# ---------------------------------------------------------------- pricing posted lines
def _log(row, col):
    """Game log stored on a projection row: a list, or a '|'-joined string from projections.csv."""
    v = row.get(col) if hasattr(row, "get") else None
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return []
    if isinstance(v, str):
        return [float(x) for x in v.split("|") if x not in ("", "nan")]
    return list(v)


def lock_score(ev, p_side, consistency, n_games, signal):
    """0-100 confidence in a pick from the model's own evidence only: expected return at the price, the model's
    probability for the side, how often the player cleared the line this season, games of data, and whether a
    role-change or outlier-fade signal backs the pick. Weights in config.LOCK_WEIGHTS; tested on the Track record tab."""
    w = C.LOCK_WEIGHTS
    ev_part = float(np.clip(ev / C.LOCK_EV_FULL, 0, 1))
    model_part = float(np.clip((p_side - 0.5) / (C.LOCK_MODEL_FULL - 0.5), 0, 1))
    cons_part = 0.5 if consistency is None or np.isnan(consistency) else float(consistency)
    n_part = float(np.clip(n_games / 6.0, 0, 1))
    score = 100 * (w["ev"] * ev_part + w["model"] * model_part + w["consistency"] * cons_part + w["sample"] * n_part + w["signal"] * (1.0 if signal else 0.0))
    return float(np.clip(score, 0, 100))


def grade_of(score):
    return "A" if score >= C.GRADE_BARS["A"] else "B" if score >= C.GRADE_BARS["B"] else "C"


def price_lines(lines, P):
    """Evaluate every posted line against the projection; return one row per line with EV, pick and confidence grade."""
    if lines is None or len(lines) == 0 or P is None or len(P) == 0:
        return pd.DataFrame()
    from pipeline.sources import norm_name
    L = lines.copy()
    L["name_key"] = L.player.map(norm_name)
    L["mkt_line"] = L.groupby(["player", "market"]).line.transform("median")   # consensus line across books
    P = P.copy()
    P["team_name"] = P.team.map(TEAM_NAMES)
    rows = []
    for r in L.itertuples():
        cand = P[P.name_key == r.name_key]
        if len(cand) > 1:
            cand2 = cand[cand.team_name.isin([getattr(r, "home_team", None), getattr(r, "away_team", None)])]
            cand = cand2 if len(cand2) else cand
        solo = "solo" in str(r.market)
        base = dict(player=r.player, book=r.book, market=r.market, line=float(r.line), over_odds=r.over_odds,
                    under_odds=r.under_odds, commence_time=getattr(r, "commence_time", ""), event_id=getattr(r, "event_id", ""))
        if cand.empty:
            rows.append({**base, "pick": "No projection", "why": "Player not in the model (no defensive snaps logged)"})
            continue
        p = cand.iloc[0]
        mu_model = p.proj_solo if solo else p.proj
        mu = (1 - C.LINE_WEIGHT) * mu_model + C.LINE_WEIGHT * float(r.mkt_line)
        po_model = p_over(mu, p.phi, float(r.line))
        has_u = pd.notna(r.under_odds)
        d_o = american_to_decimal(r.over_odds) if pd.notna(r.over_odds) else None
        d_u = american_to_decimal(r.under_odds) if has_u else None
        if d_o and d_u:
            mkt = (1 / d_o) / (1 / d_o + 1 / d_u)
        elif d_o:
            mkt = 1 / d_o
        else:
            mkt = 1 - 1 / d_u
        po = mkt + C.PROB_SHRINK * (po_model - mkt)
        ev_o = po * (d_o - 1) - (1 - po) if d_o else -9
        ev_u = (1 - po) * (d_u - 1) - po if d_u else -9
        side, ev = ("Over", ev_o) if ev_o >= ev_u else ("Under", ev_u)
        log = _log(p, "log_solo" if solo else "log_comb")
        hits = [(x > r.line) if side == "Over" else (x < r.line) for x in log]
        consistency = float(np.mean(hits)) if hits else float("nan")
        mkt_side = mkt if side == "Over" else 1 - mkt
        dec = d_o if side == "Over" else d_u
        gap = (p["last"] - p.base) if pd.notna(p["last"]) else 0.0
        fade = abs(gap) >= C.FADE_GAP and ((side == "Under" and gap > 0) or (side == "Over" and gap < 0))
        role = bool(p.role_signal) and side == "Over"
        flagged = str(p.status).lower() in OUT_STATUSES
        uncertain = str(p.status).lower() == "questionable"
        thin = p.n_prev < C.MIN_GAMES_FOR_PICK and not role
        bar = C.SIGNAL_BAR if (fade or role) else C.PICK_BAR
        pick = side if (ev >= bar and not flagged and not thin) else "Pass"
        p_side = po if side == "Over" else 1 - po
        lock = lock_score(ev, p_side, consistency, int(p.n_prev), fade or role)
        if flagged:
            why = f"His own status is {p.status or 'uncertain'}: wait for the final report"
        elif thin:
            why = f"Only {int(p.n_prev)} games of data"
        elif ev < bar:
            why = f"Best side returns {ev:+.0%}; needs {bar:.0%}"
        else:
            why = f"{side} returns {ev:+.0%}" + (", backed by a role change" if role else ", fading an outlier last game" if fade else ", price gap only")
            if uncertain:
                why += "; listed questionable: priced 8% under his average, not a lock, voids if he sits"
        rows.append({**base, "team": p.team, "opp": p.opp_team, "group": p.group, "proj": float(mu), "proj_model": float(mu_model),
                     "mkt_line": float(r.mkt_line), "phi": float(p.phi), "model_over": po, "market_over": mkt, "ev": ev, "side": side,
                     "pick": pick, "why": why, "signal_fade": bool(fade), "signal_role": role, "status": p.status,
                     "season_avg": float(p.season_avg), "last": None if pd.isna(p["last"]) else float(p["last"]),
                     "n_prev": int(p.n_prev), "consistency": consistency, "cons_hits": int(sum(hits)), "cons_n": len(hits),
                     "mkt_side": float(mkt_side), "payout": None if dec is None else float(dec - 1),
                     "international": str(p.get("venue", "")) == "NEUTRAL", "depth": p.get("dc_status", ""), "uncertain": bool(uncertain),
                     "opp_qb_out": bool(p.get("opp_qb_out", False)), "opp_rb_out": bool(p.get("opp_rb_out", False)),
                     "rest": None if pd.isna(p.get("rest", np.nan)) else int(p.get("rest")),
                     "lock": lock, "grade": grade_of(lock)})
    out = pd.DataFrame(rows)
    if "ev" in out:
        out = out.sort_values("ev", ascending=False, na_position="last")
        # line shopping: mark the best book for each player / market / side / line
        out["best_price"] = ~out.duplicated(["player", "market", "side", "line"]) & out.ev.notna()
        out = out.sort_values(["lock", "ev"], ascending=[False, False], na_position="last")
    return out


# ---------------------------------------------------------------- second model: gradient-boosted corrector
GBM_FEATURES = ["log_mu", "n_prev", "snap", "pct_prev", "vol", "spread", "tgt", "miss", "demoted", "promoted", "starter", "q", "limited",
                "rest", "week", "last", "avg", "ps_avg", "crew", "grp", "is_home", "exp_runs", "exp_comps", "run_tk_rate", "pass_tk_rate"]


def gbm_features(F, mu):
    """The feature frame for the corrector: the factor model's projection plus the raw signals behind it."""
    n = F.n_prev.astype(float).clip(lower=1)
    col = lambda c, d=np.nan: F[c] if c in F else pd.Series(d, index=F.index)
    status = col("status", "").fillna("").astype(str).str.lower(); practice = col("practice", "").fillna("").astype(str).str.lower()
    X = pd.DataFrame({
        "log_mu": np.log(pd.Series(np.asarray(mu, dtype=float), index=F.index).clip(lower=0.05)),
        "n_prev": F.n_prev.astype(float),
        "snap": (col("pct_last3") / col("pct_prev").clip(lower=0.05)).fillna(1.0).clip(0.3, 3.0),
        "pct_prev": col("pct_prev").fillna(0),
        "vol": (col("exp_opps") / col("opps_prev_mean")).fillna(1.0).clip(0.6, 1.6),
        "spread": col("spread_dog").fillna(0),
        "tgt": (col("targets_prev") / n).fillna(0),
        "miss": (col("missed_prev") / (col("pfr_comb_prev").fillna(0) + col("missed_prev").fillna(0)).clip(lower=1)).fillna(0.1),
        "demoted": col("demoted", False).fillna(False).astype(float), "promoted": col("promoted", False).fillna(False).astype(float),
        "starter": col("dc_starter").astype(float).fillna(0.5),
        "q": (status == "questionable").astype(float), "limited": practice.str.startswith("limited").astype(float),
        "rest": col("rest").fillna(7), "week": F.week.astype(float), "last": col("last").fillna(0),
        "avg": (F.comb_prev_raw / n), "ps_avg": col("ps_avg").fillna(-1), "crew": col("crew_comb").fillna(1.0),
        "grp": F.group.map({"LB": 0, "S": 1, "CB": 2, "DL": 3}).fillna(4), "is_home": col("is_home", False).fillna(False).astype(float),
        "exp_runs": col("exp_runs").fillna(26), "exp_comps": col("exp_comps").fillna(21),
        "run_tk_rate": (col("run_tk_prev") / col("runs_faced_prev").clip(lower=1)).fillna(0),
        "pass_tk_rate": (col("pass_tk_prev") / col("comps_faced_prev").clip(lower=1)).fillna(0),
    })
    return X[GBM_FEATURES].astype(float)


def fit_gbm(X, y):
    """Train the corrector (a few seeds averaged). Returns a predict function, or None if scikit-learn is missing."""
    try:
        from sklearn.ensemble import HistGradientBoostingRegressor
    except ImportError:
        return None
    c = C.GBM
    models = []
    for seed in c["seeds"]:
        m = HistGradientBoostingRegressor(loss="poisson", max_iter=c["max_iter"], learning_rate=c["learning_rate"], max_leaf_nodes=c["max_leaf_nodes"],
                                          min_samples_leaf=c["min_samples_leaf"], l2_regularization=c["l2"], random_state=seed)
        m.fit(X, y)
        models.append(m)
    return lambda Xn: np.mean([m.predict(Xn) for m in models], axis=0)


def blend_gbm(mu, gbm_pred):
    w = C.GBM["weight"]
    return (1 - w) * np.asarray(mu, dtype=float) + w * np.clip(np.asarray(gbm_pred, dtype=float), 0.05, None)
