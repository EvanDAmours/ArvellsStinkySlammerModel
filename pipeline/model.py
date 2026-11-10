"""Projection model and bet pricing.

The projection: a factor model (a per-game and a per-snap base, then the game factors switched on in config.FACTORS) and a
gradient-boosted corrector trained on every finished game, blended (config.GBM). Counts are negative binomial around it.

The pricing engine: for every posted line, the book's fair chance (its two-way price with the vig out) moved by a fraction of
the model's disagreement, in log-odds (config.ENGINE). That one probability gives the return, the pick, the grade and the stake.
MODEL_LOG.md holds the evidence for every piece and what was tried and dropped.
"""
import functools
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
    base = ["game_id", "season", "week", "gameday", "gametime", "home_score", "away_score", "roof", "location", "spread_line", "total_line"]
    sched = sched.copy()
    for c in ("home_rest", "away_rest"):
        if c not in sched.columns:
            sched[c] = 7
    if "away_score" not in sched.columns:
        sched["away_score"] = np.nan
    if "roof" not in sched.columns:
        sched["roof"] = ""
    h = sched[base + ["home_team", "away_team", "home_rest"]].rename(columns={"home_team": "team", "away_team": "opp_team", "home_rest": "rest"}).assign(is_home=True)
    a = sched[base + ["home_team", "away_team", "away_rest"]].rename(columns={"away_team": "team", "home_team": "opp_team", "away_rest": "rest"}).assign(is_home=False)
    tg = pd.concat([h, a], ignore_index=True)
    neutral = tg.location.str.lower().str.startswith("neutral")
    tg["venue"] = np.where(neutral, "NEUTRAL", np.where(tg.is_home, tg.team, tg.opp_team))
    # underdog-positive spread for the DEFENSE's team (nflverse: positive spread_line = home favored)
    tg["spread_dog"] = np.where(tg.is_home, -tg.spread_line, tg.spread_line)
    tg["final"] = tg.home_score.notna()
    tg["margin"] = (pd.to_numeric(tg.home_score, errors="coerce") - pd.to_numeric(tg.away_score, errors="coerce")).abs()
    tg["roof"] = tg.roof.fillna("").astype(str).str.lower()
    # retractable roofs (ATL, IND, ARI, DAL, HOU) are recorded "closed"/"open" only after the game and blank before it:
    # an upcoming game takes its stadium's usual state from played games, as the training rows saw (audit 2026-11-09:
    # the indoor bump for corners was learned on "closed" and never applied live)
    played = tg[tg.final & (tg.roof != "")]
    if len(played):
        usual = played.groupby("venue").roof.agg(lambda x: x.value_counts().index[0])
        blank = (tg.roof == "") & ~tg.final
        tg.loc[blank, "roof"] = tg.loc[blank, "venue"].map(usual).fillna("").values
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
            for c in ["comb", "solo_t", "solo", "ast", "with_ast", "solo_off"]:
                miss[c] = 0
            pw = pd.concat([pw, miss[[c for c in pw.columns if c in miss.columns]]], ignore_index=True)
        pw = pw.merge(snaps[["season", "week", "team", "name_key", "def_pct", "def_snaps"]], on=["season", "week", "team", "name_key"], how="left")
        pw.loc[pw.index.isin(dup_names[dup_names].index), ["def_pct", "def_snaps"]] = np.nan
    else:
        pw["def_pct"], pw["def_snaps"] = np.nan, np.nan
    keep = ["season", "week", "team", "game_id", "venue", "spread_dog", "is_home", "opp_team", "gameday", "gametime", "final", "rest", "margin", "roof"]
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
    for c in ("targets", "missed", "pfr_comb", "press"):
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
    for c in ("run_tk", "pass_tk", "runs_faced", "comps_faced", "targets", "missed", "pfr_comb", "press"):
        H[c + "_prev"] = g[c].transform(lambda x: x.shift(1).expanding().sum()) if c in H.columns else np.nan
    if "dc_starter" in H.columns:
        prev = g.dc_starter.shift(1)
        H["promoted"] = (H.dc_starter == 1) & (prev == 0)
        H["demoted"] = (H.dc_starter == 0) & (prev == 1)
    else:
        H["promoted"], H["demoted"] = False, False
    H["comb_prev_raw"] = g.comb.cumsum() - H.comb
    H["solo_prev_raw"] = g.solo_t.cumsum() - H.solo_t      # the solo share without the stat-crew adjustment (config.FACTORS crew off)
    H["comb_prev"] = g.comb_adj.cumsum() - H.comb_adj
    H["solo_prev"] = g.solo_adj.cumsum() - H.solo_adj
    H["last"] = g.comb.shift(1)
    H["last2"] = g.comb.transform(lambda x: x.shift(1).rolling(2).mean())
    H["pct_prev"] = g.def_pct.transform(lambda x: x.shift(1).expanding().mean())
    H["pct_last"] = g.def_pct.shift(1)
    H["last_week"] = g.week.shift(1)
    H["gap_weeks"] = H.week - H.last_week                      # 1 = played last week; 2 = a bye or a missed game; 3+ = absence
    prev_team = g.team.shift(1)
    H["team_changed"] = (prev_team.notna() & (H.team != prev_team)).astype(bool)
    # per-snap rate from games with real defensive snaps only (special-teams tackles on 0-9 snaps would inflate it)
    real = H.def_snaps.fillna(0) >= C.PERSNAP["min_game_snaps"]
    H["_c_real"] = np.where(real, H.comb, 0.0)
    H["_s_real"] = np.where(real, H.def_snaps.fillna(0), 0.0)
    g = H.groupby(["player_id", "season"], sort=False)
    H["c_real_prev"] = g._c_real.cumsum() - H._c_real
    H["s_real_prev"] = g._s_real.cumsum() - H._s_real
    H["last_margin"] = g.margin.shift(1) if "margin" in H.columns else np.nan
    H = attach_team_snaps(H)
    H = attach_matchup(H)
    H = H.drop(columns=[c for c in ("solo_drift",) if c in H.columns]).merge(solo_drift_table(H), on=["season", "week"], how="left")
    ps = H.groupby(["player_id", "season"]).agg(ps_games=("comb", "size"), ps_avg=("comb_adj", "mean"),
                                                 ps_avg_raw=("comb", "mean"), ps_c=("_c_real", "sum"), ps_s=("_s_real", "sum")).reset_index()
    ps["season"] += 1
    ps["ps_rate"] = (ps.ps_c / ps.ps_s.clip(lower=1)).where(ps.ps_s >= C.PERSNAP["min_prior_snaps"])
    return H.merge(ps.drop(columns=["ps_c", "ps_s"]), on=["player_id", "season"], how="left").drop(columns=["_c_real", "_s_real"])


def solo_drift_table(H):
    """League solo share over the last few weeks relative to the season to date, known before each week: the stat
    crews' solo/assist split drifts within a season, and a player's season-to-date solo share lags it."""
    c = C.SOLO_DRIFT
    if H.empty or "solo_t" not in H.columns:
        return pd.DataFrame(columns=["season", "week", "solo_drift"])
    lw = H.groupby(["season", "week"]).agg(solo=("solo_t", "sum"), comb=("comb", "sum")).reset_index().sort_values(["season", "week"])
    g = lw.groupby("season")
    std = (g.solo.cumsum() - lw.solo) / (g.comb.cumsum() - lw.comb).clip(lower=1)
    rec_s = g.solo.transform(lambda x: x.shift(1).rolling(c["weeks"], min_periods=1).sum())
    rec_c = g.comb.transform(lambda x: x.shift(1).rolling(c["weeks"], min_periods=1).sum())
    lw["solo_drift"] = (rec_s / rec_c.clip(lower=1) / std.replace(0, np.nan)).clip(*c["cap"]).fillna(1.0)
    return lw[["season", "week", "solo_drift"]]


def solo_drift_for(H, season, week):
    """The drift that applies to an upcoming week: last few played weeks of the season over its season to date."""
    c = C.SOLO_DRIFT
    done = H[(H.season == season) & (H.week < week)]
    if done.empty or done.comb.sum() <= 0:
        return 1.0
    lw = done.groupby("week").agg(solo=("solo_t", "sum"), comb=("comb", "sum")).sort_index()
    rec = lw.tail(c["weeks"])
    std = lw.solo.sum() / max(1.0, lw.comb.sum()); recent = rec.solo.sum() / max(1.0, rec.comb.sum())
    return float(np.clip(recent / std if std > 0 else 1.0, *c["cap"]))


def attach_team_snaps(H):
    """Expected defensive snaps for each team-game: the average of the defence's own prior games and the plays the
    opponent's offence has run per game (each team's offence plays = the snaps its opponents' defences played)."""
    if "def_snaps" not in H.columns or H.empty:
        H["tsnaps_exp"] = np.nan
        return H
    tg = H.groupby(["season", "week", "team", "opp_team"]).def_snaps.max().rename("tsnaps").reset_index().sort_values(["season", "week"])
    tg["d_prev"] = tg.groupby(["season", "team"]).tsnaps.transform(lambda x: x.shift(1).expanding().mean())
    off = tg.rename(columns={"team": "opp_team", "opp_team": "team", "tsnaps": "off_plays"})[["season", "week", "team", "off_plays"]].sort_values(["season", "week"])
    off["o_prev"] = off.groupby(["season", "team"]).off_plays.transform(lambda x: x.shift(1).expanding().mean())
    tg = tg.merge(off.rename(columns={"team": "opp_team"})[["season", "week", "opp_team", "o_prev"]], on=["season", "week", "opp_team"], how="left")
    lg = float(tg.tsnaps.mean()) if tg.tsnaps.notna().any() else 65.0
    tg["tsnaps_exp"] = (tg.d_prev.fillna(lg) + tg.o_prev.fillna(lg)) / 2
    return H.drop(columns=[c for c in ("tsnaps_exp",) if c in H.columns]).merge(tg[["season", "week", "team", "tsnaps_exp"]], on=["season", "week", "team"], how="left")


def team_snaps_for(H, season, week):
    """Expected defensive snaps per team for an upcoming week, from this season's played games."""
    done = H[(H.season == season) & (H.week < week)]
    if done.empty or "def_snaps" not in done.columns:
        return {}, 65.0
    tg = done.groupby(["week", "team", "opp_team"]).def_snaps.max().rename("tsnaps").reset_index()
    d = tg.groupby("team").tsnaps.mean()
    o = tg.groupby("opp_team").tsnaps.mean()      # plays each offence ran = snaps its opponents' defences played
    lg = float(tg.tsnaps.mean()) if tg.tsnaps.notna().any() else 65.0
    return dict(defence=d.to_dict(), offence=o.to_dict()), lg


def matchup_rel(prev_mean, n, lg):
    m = C.MATCHUP["pseudo_games"]
    return (prev_mean.fillna(lg) * n.fillna(0) + m * lg) / ((n.fillna(0) + m) * lg)


def attach_matchup(H):
    """Tackles each opponent's offence has allowed to each position group per game (prior games, shrunk to league): 1 = league."""
    if H.empty or "opp_team" not in H.columns:
        H["allowed_rel"] = 1.0
        return H
    t = H.groupby(["season", "week", "opp_team", "group"]).comb.sum().reset_index().sort_values(["season", "week"])
    gg = t.groupby(["season", "opp_team", "group"]).comb
    t["prev_mean"] = gg.transform(lambda x: x.shift(1).expanding().mean())
    t["n"] = gg.cumcount()
    lg = t.groupby("group").comb.mean()
    t["allowed_rel"] = matchup_rel(t.prev_mean, t.n.astype(float), t.group.map(lg))
    return H.drop(columns=[c for c in ("allowed_rel",) if c in H.columns]).merge(t[["season", "week", "opp_team", "group", "allowed_rel"]], on=["season", "week", "opp_team", "group"], how="left")


def matchup_for(H, season, week):
    """(opp_team, group) -> tackles allowed relative to league, from this season's games before `week`."""
    done = H[(H.season == season) & (H.week < week)]
    lg = H.groupby(["season", "week", "opp_team", "group"]).comb.sum().reset_index().groupby("group").comb.mean()
    if done.empty:
        return {}, lg
    t = done.groupby(["week", "opp_team", "group"]).comb.sum().reset_index().groupby(["opp_team", "group"]).comb.agg(["mean", "size"]).reset_index()
    t["allowed_rel"] = matchup_rel(t["mean"], t["size"].astype(float), t.group.map(lg))
    return {(r.opp_team, r.group): float(r.allowed_rel) for r in t.itertuples()}, lg


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
    # vacancy: a regular at the group (75%+ share in his last game for the team) absent this week, within 3 weeks of his
    # last game: the first weeks of an injury or a trade. Persistent, unlike role_signal which fires once.
    # Causal (audit 2026-11-09): each week sees only the regulars' 75%+ games BEFORE it. The old loop used each player's
    # last 75%+ game of the whole season, so an absence he later returned from was never flagged (it knew the future).
    vac = set()
    for (s, t), weeks in team_weeks.items():
        seen = {}                                   # player -> (week of his latest 75%+ game so far, group)
        for w in weeks:
            for pid, (wl, g) in seen.items():
                if wl < w <= wl + C.VACANCY["recent_weeks"] and pid not in present.get((s, t, w), set()):
                    vac.add((s, t, w, g))
            for pid in present.get((s, t, w), set()):
                if pct.get((s, t, w, pid), 0) >= C.VACANCY["regular_share"]:
                    seen[pid] = (w, group.get(pid))
                else:
                    seen.pop(pid, None)             # judged by his latest game, as the live rule reads it
    H["vacancy"] = [((s, t, w, g) in vac) for s, t, w, g in zip(H.season, H.team, H.week, H.group)]
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


def pfr_typical(F):
    """The typical coverage-target rate (targets per game, DBs with PFR rows) of a frame: the backtest stores its own so
    the live week is centred on the training value, not on that week's roster (bench DBs pulled it 17% low)."""
    if "targets_prev" not in F:
        return np.nan
    n = F.n_prev.astype(float).clip(lower=1)
    db = F.group.isin(["CB", "S"]) & F.targets_prev.notna()
    return float((F.targets_prev / n)[db].mean()) if db.any() else np.nan


def pfr_factor(F, typical=None):
    """Coverage usage (targets per game, DBs only) and missed-tackle rate, both from PFR, vs typical (the training
    frame's rate when given)."""
    c = C.PFR
    n = F.n_prev.astype(float).clip(lower=1)
    out = pd.Series(1.0, index=F.index)
    if "targets_prev" in F:
        db = F.group.isin(["CB", "S"]) & F.targets_prev.notna()
        rate = (F.targets_prev / n).where(db)
        typical = typical if typical is not None and typical == typical and typical > 0 else (float(rate[db].mean()) if db.any() else np.nan)
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


def _flag(v):
    """A boolean that may arrive as a string from projections.csv or as NaN from an older row."""
    return v is True or (isinstance(v, (bool, np.bool_)) and bool(v)) or str(v).lower() == "true"


def snap_jump(F):
    """Last game's snap share over the season share before it (1.0 when unknown)."""
    pl = F["pct_last"] if "pct_last" in F else pd.Series(np.nan, index=F.index)
    pp = F["pct_prev"] if "pct_prev" in F else pd.Series(np.nan, index=F.index)
    return (pl / pp.clip(lower=0.05)).where(pl.notna() & pp.notna(), 1.0)


def new_role_flag(F):
    """A part-timer who just played a starter's snaps: his season history does not describe his current role."""
    c = C.NEW_ROLE
    pl = F["pct_last"] if "pct_last" in F else pd.Series(np.nan, index=F.index)
    pp = F["pct_prev"] if "pct_prev" in F else pd.Series(np.nan, index=F.index)
    f = pl.notna() & pp.notna() & (pp < c["max_prev_share"]) & (pl >= c["min_last_share"]) & (snap_jump(F) >= c["min_ratio"])
    return f.fillna(False).astype(bool)


def new_role_factor(F):
    c = C.NEW_ROLE
    return pd.Series(np.where(new_role_flag(F), np.power(snap_jump(F).clip(upper=c["cap"]), c["power"]), 1.0), index=F.index)


def role_shift_flags(F):
    """Situations where the season log stops describing a player, all market-free: a part-timer who just played a
    starter's snaps (new role), a player whose last game's share fell well below his season share (reduced role), a
    player back after missing games (absence / missed game), and a player who changed team mid-season (new team)."""
    c = C.ROLE_SHIFT
    jump = snap_jump(F)
    pl = F["pct_last"] if "pct_last" in F else pd.Series(np.nan, index=F.index)
    gap = pd.to_numeric(F["gap_weeks"], errors="coerce") if "gap_weeks" in F else pd.Series(np.nan, index=F.index)
    rest = pd.to_numeric(F["rest"], errors="coerce") if "rest" in F else pd.Series(np.nan, index=F.index)
    team = F["team_changed"].map(_flag) if "team_changed" in F else pd.Series(False, index=F.index)
    return pd.DataFrame(dict(new_role=new_role_flag(F),
                             reduced_role=(pl.notna() & (jump < c["contraction_ratio"])).fillna(False).astype(bool),
                             absence=(gap.notna() & (gap >= c["absence_weeks"])).fillna(False).astype(bool),
                             missed_game=(gap.notna() & (gap == 2) & (rest.fillna(7) < C.REST["bye_days"])).fillna(False).astype(bool),
                             new_team=team.fillna(False).astype(bool)), index=F.index)


def role_shift_factor(F, part="all"):
    """part: 'share' = the reduced-role piece (belongs with the per-game base), 'availability' = absence / missed game /
    new team (applies to any base), 'all' = both."""
    c = C.ROLE_SHIFT
    fl = role_shift_flags(F)
    f = np.ones(len(F))
    if part in ("share", "all"):
        f = f * np.where(fl.reduced_role, np.power(snap_jump(F).clip(lower=0.2), c["contraction_power"]), 1.0)
    if part in ("availability", "all"):
        f = f * np.where(fl.absence, c["absence_factor"], np.where(fl.missed_game, c["missed_game_factor"], 1.0))
        f = f * np.where(fl.new_team, c["new_team_factor"], 1.0)
    return pd.Series(f, index=F.index)


def _col_or(F, c, d):
    return F[c] if c in F else pd.Series(d, index=F.index)


def share_pred(F):
    """Next-game snap share: (last game, last three, season) weighted by situation (SHARE_MODEL)."""
    c = C.SHARE_MODEL
    last = _col_or(F, "pct_last", np.nan).fillna(_col_or(F, "pct_prev", np.nan))
    l3 = _col_or(F, "pct_last3", np.nan).fillna(_col_or(F, "pct_prev", np.nan))
    season = _col_or(F, "pct_prev", np.nan)
    ok = last.notna() & season.notna()
    jump = snap_jump(F)
    up = jump >= c["up_ratio"]; down = jump < c["down_ratio"]
    backed = _col_or(F, "vacancy", False).map(_flag) | (pd.to_numeric(_col_or(F, "dc_starter", 0), errors="coerce").fillna(0) >= 1)
    blow = pd.to_numeric(_col_or(F, "last_margin", np.nan), errors="coerce").fillna(0) >= c["blowout_margin"]
    seg = np.where(up & backed, "vacancy", np.where(up & blow, "blowout", np.where(up, "up", np.where(down, "down", "steady"))))
    W = np.array([c[k] for k in seg])
    pred = W[:, 0] * last.fillna(0).values + W[:, 1] * l3.fillna(0).values + W[:, 2] * season.fillna(0).values
    return pd.Series(np.where(ok, np.clip(pred, 0.0, 1.0), np.nan), index=F.index)


def persnap_rate(F):
    """Tackles per defensive snap from games with real defensive snaps, shrunk to last season's rate or the position rate."""
    c = C.PERSNAP
    prior = _col_or(F, "ps_rate", np.nan)
    prior = prior.where(prior.notna(), F.group.map(c["group_rate"]).fillna(0.08))
    cp, sp = _col_or(F, "c_real_prev", 0).fillna(0), _col_or(F, "s_real_prev", 0).fillna(0)
    return (cp + c["pseudo_snaps"] * prior) / (sp + c["pseudo_snaps"])


def persnap_base(F, share):
    """Per-snap projection: rate x share x expected team defensive snaps, calibrated."""
    ts = pd.to_numeric(_col_or(F, "tsnaps_exp", np.nan), errors="coerce").fillna(65.0)
    return persnap_rate(F) * share * ts * C.PERSNAP["cal"]


def vacancy_rule(F):
    """A regular at his group is out or gone, his share jumped, and it was not a blowout: his last game is his new role."""
    c = C.VACANCY
    vac = _col_or(F, "vacancy", False).map(_flag)
    blow = pd.to_numeric(_col_or(F, "last_margin", np.nan), errors="coerce").fillna(0) >= C.SHARE_MODEL["blowout_margin"]
    return (vac & (snap_jump(F) >= c["min_jump"]) & ~blow & _col_or(F, "pct_last", np.nan).notna()).fillna(False).astype(bool)


def dome_factor(F):
    roof = _col_or(F, "roof", "").fillna("").astype(str).str.lower()
    return pd.Series(np.where((F.group == "CB") & roof.isin(["dome", "closed"]), C.DOME_CB, 1.0), index=F.index)


def outlier_damp_factor(F, raw=False):
    """After a game far above or below his base, in a settled role, the season average still leans toward that game."""
    c = C.OUTLIER_DAMP
    last = pd.to_numeric(_col_or(F, "last", np.nan), errors="coerce")
    base = _base_for_outliers(F, raw)
    settled = snap_jump(F).between(0.8, 1.25)
    hi = (last - base >= C.FADE_GAP) & settled; lo = (base - last >= C.FADE_GAP) & settled
    return pd.Series(np.where(hi.fillna(False), c["after_high"], np.where(lo.fillna(False), c["after_low"], 1.0)), index=F.index)


def _base_for_outliers(F, raw=False):
    """The shrunk per-game base, recomputed cheaply (same formula as project_frame's base; raw = without the stat-crew adjustment)."""
    k = F.group.map(C.SHRINK_GAMES_BY_GROUP).fillna(C.SHRINK_GAMES)
    prev, ps = (F.comb_prev_raw, F.ps_avg_raw) if raw else (F.comb_prev, F.ps_avg)
    prior = np.where(F.ps_games.fillna(0) >= 4, ps, F.group.map(C.POS_PRIOR).fillna(4.0))
    n = F.n_prev.astype(float)
    return pd.Series(np.where(n + k > 0, (prev + k * prior) / np.maximum(n + k, 1e-9), prior), index=F.index)


def rest_factor(F):
    r = C.REST
    return pd.Series(np.where(F.get("rest", pd.Series(7, index=F.index)).fillna(7) >= r["bye_days"], r["bye"], 1.0), index=F.index)


FACTOR_KEYS = ("tilt", "crew", "role", "snap", "volume", "depth", "pfr", "mix", "rest", "injury", "new_role", "role_shift", "persnap", "vacancy", "dome", "solo_drift", "outlier_damp")


def project_frame(F, k=None, use_tilt=None, use_crew=None, use_role=None, use_snap=None, use_volume=None, use_depth=None, use_pfr=None, use_mix=None, use_rest=None, use_injury=None, use_new_role=None, use_role_shift=None,
                  use_persnap=None, use_vacancy=None, use_dome=None, use_solo_drift=None, use_outlier_damp=None, parts=None, pfr_typ=None):
    """(base, mu, mu_solo) of the factor model. A factor left as None follows config.FACTORS (the model as it runs); the backtest
    passes True or False to test one. `parts`, when a dict, receives every piece of the build per row (the base, the per-snap
    view, each game factor as a multiplier, the solo share); the numbers are the same."""
    on = lambda v, key: bool(C.FACTORS.get(key, True)) if v is None else bool(v)
    use_tilt, use_crew, use_role, use_snap, use_volume, use_depth = on(use_tilt, "tilt"), on(use_crew, "crew"), on(use_role, "role"), on(use_snap, "snap"), on(use_volume, "volume"), on(use_depth, "depth")
    use_pfr, use_mix, use_rest, use_injury, use_new_role, use_role_shift = on(use_pfr, "pfr"), on(use_mix, "mix"), on(use_rest, "rest"), on(use_injury, "injury"), on(use_new_role, "new_role"), on(use_role_shift, "role_shift")
    use_persnap, use_vacancy, use_dome, use_solo_drift, use_outlier_damp = on(use_persnap, "persnap"), on(use_vacancy, "vacancy"), on(use_dome, "dome"), on(use_solo_drift, "solo_drift"), on(use_outlier_damp, "outlier_damp")
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
    xf = {}                                     # each game factor on its own, for `parts`
    if use_depth:
        xf["depth"] = depth_factor(F).values
    if use_pfr:
        xf["pfr"] = pfr_factor(F, pfr_typ).values
    if use_mix:
        xf["mix"] = mix_factor(F).values
    if use_rest:
        xf["rest"] = rest_factor(F).values
    if use_injury:
        xf["injury"] = injury_factor(F).values
    if use_role_shift:
        xf["availability"] = role_shift_factor(F, "availability").values
    if use_dome:
        xf["dome"] = dome_factor(F).values
    if use_outlier_damp:
        xf["damp"] = outlier_damp_factor(F, raw=not use_crew).values
    for v in xf.values():
        extra = extra * v
    # the per-game core: season rate x snap trend x role bump x the share-related corrections
    pg = base * role * snap
    nr = rs = 1.0
    if use_new_role:
        nr = new_role_factor(F).values
        pg = pg * nr
    if use_role_shift:
        rs = role_shift_factor(F, "share").values
        pg = pg * rs
    core = pg
    ps_used, vac_on, core_pre = np.full(len(F), np.nan), np.zeros(len(F), dtype=bool), None
    if use_persnap:
        share = share_pred(F)
        ps = persnap_base(F, share.fillna(_col_or(F, "pct_prev", np.nan)))
        has_rate = (_col_or(F, "s_real_prev", 0).fillna(0) > 0) | _col_or(F, "ps_rate", np.nan).notna()
        ok = ps.notna() & has_rate
        w = C.PERSNAP["weight"]
        core = np.where(ok, (1 - w) * pg + w * ps.values, pg)
        ps_used = np.where(ok, ps.values, np.nan)
    core_pre = core
    if use_vacancy:
        rule = vacancy_rule(F)
        if rule.any():
            ps_last = persnap_base(F, _col_or(F, "pct_last", np.nan).fillna(0))     # his last game's share is his new role
            wv = C.VACANCY["weight"]
            core = np.where(rule, wv * ps_last.values + (1 - wv) * core, core)
            vac_on = np.asarray(rule, dtype=bool)
    m_s = C.SOLO_SHARE_PSEUDO
    s_prev, c_prev = (F.solo_prev, F.comb_prev) if use_crew or "solo_prev_raw" not in F else (F.solo_prev_raw, F.comb_prev_raw)   # crew off: his raw solo share
    solo_share = (s_prev + m_s * F.group.map(C.POS_SOLO_SHARE).fillna(0.6)) / (c_prev + m_s)
    if use_solo_drift:
        solo_share = solo_share * pd.to_numeric(_col_or(F, "solo_drift", 1.0), errors="coerce").fillna(1.0)
    mu = core * tilt * crew_c * volume * extra
    mu_solo = core * tilt * solo_share * crew_s * volume * extra
    if parts is not None:
        full = lambda v: np.broadcast_to(np.asarray(v, dtype=float), (len(F),)).astype(float)
        parts.update(base=full(base), pg=full(pg), persnap=full(ps_used), core_pre=full(core_pre), core=full(core), vacancy_rule=vac_on,
                     role=full(role), snap=full(snap), new_role=full(nr), share_shift=full(rs), tilt=full(tilt), crew=full(crew_c),
                     crew_solo=full(crew_s), volume=full(volume), solo_share=full(solo_share),
                     **{k_: full(v) for k_, v in xf.items()})
    return pd.Series(base, index=F.index), pd.Series(mu, index=F.index), pd.Series(mu_solo, index=F.index)


def upcoming_rows(H, sched, injuries, season, week, vol=None, dc=None, pbp_starters=None, roster=None):
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
    sums = {c: (c, lambda x: x.sum(min_count=1)) for c in ("run_tk", "pass_tk", "runs_faced", "comps_faced", "targets", "missed", "pfr_comb", "press") if c in done.columns}   # no rows -> NaN, not 0 (as the backtest's history reads)
    agg = done.groupby("player_id").agg(
        player=("player", "last"), name_key=("name_key", "last"), team=("team", "last"), group=("group", "last"),
        n_prev=("comb", "size"), comb_prev=("comb_adj", "sum"), comb_prev_raw=("comb", "sum"),
        solo_prev=("solo_adj", "sum"), solo_prev_raw=("solo_t", "sum"), pct_prev=("def_pct", "mean"), **sums).reset_index()
    agg = agg.rename(columns={c: c + "_prev" for c in sums})
    last_dc = done.sort_values("week").groupby("player_id").dc_starter.last() if "dc_starter" in done.columns else None
    lasts = done.sort_values("week").groupby("player_id").agg(last=("comb", "last"), pct_last=("def_pct", "last"), last_week=("week", "last"),
                                                              last_gameday=("gameday", "last"), last_margin=("margin", "last") if "margin" in done.columns else ("comb", "size"))
    # the snap share of his actual last game: groupby "last" skips a missing value and would report an older game's
    # share, hiding the "snap counts missing for his last game" lock block
    lasts["pct_last"] = done.sort_values("week").groupby("player_id").tail(1).set_index("player_id").def_pct.reindex(lasts.index)
    if "margin" not in done.columns:
        lasts["last_margin"] = np.nan
    real = done.def_snaps.fillna(0) >= C.PERSNAP["min_game_snaps"]
    persnap = done.assign(_c=np.where(real, done.comb, 0.0), _s=np.where(real, done.def_snaps.fillna(0), 0.0)).groupby("player_id").agg(c_real_prev=("_c", "sum"), s_real_prev=("_s", "sum"))
    lasts = lasts.join(persnap)
    last2 = done.sort_values("week").groupby("player_id").comb.apply(lambda x: x.tail(2).mean() if len(x) >= 2 else np.nan).rename("last2")
    pct_last3 = done.sort_values("week").groupby("player_id").def_pct.apply(lambda x: x.tail(C.SNAP_TREND["games"]).mean()).rename("pct_last3")
    opps_prev = (done.groupby("player_id").opps.mean().rename("opps_prev_mean") if "opps" in done.columns
                 else pd.Series(dtype=float, name="opps_prev_mean"))
    F = agg.merge(active, on="player_id").join(lasts, on="player_id").join(last2, on="player_id").join(pct_last3, on="player_id").join(opps_prev, on="player_id")
    prev = H[H.season == season - 1]
    preal = prev.def_snaps.fillna(0) >= C.PERSNAP["min_game_snaps"]
    ps = prev.assign(_c=np.where(preal, prev.comb, 0.0), _s=np.where(preal, prev.def_snaps.fillna(0), 0.0)).groupby("player_id").agg(
        ps_games=("comb", "size"), ps_avg=("comb_adj", "mean"), ps_avg_raw=("comb", "mean"), ps_c=("_c", "sum"), ps_s=("_s", "sum"))
    ps["ps_rate"] = (ps.ps_c / ps.ps_s.clip(lower=1)).where(ps.ps_s >= C.PERSNAP["min_prior_snaps"])
    F = F.join(ps.drop(columns=["ps_c", "ps_s"]), on="player_id")
    F["gap_weeks"] = week - pd.to_numeric(F.last_week, errors="coerce")
    # a mid-season team change shows on the depth chart before he plays for the new team: move him and flag him
    F["team_changed"] = False
    F["team_from"] = F.team
    if dc is not None and len(dc) and "date" in dc.columns:
        cur = dc[(dc.season == season) & dc["date"].notna()]
        if len(cur):
            latest = cur.sort_values("date").groupby("player_id").agg(dc_team=("team", "last"), dc_date=("date", "last"))
            F = F.join(latest, on="player_id")
            moved = F.dc_team.notna() & (F.dc_team != F.team) & (F.dc_date.astype(str) > F.last_gameday.astype(str)) & F.dc_team.isin(set(games.team))
            F.loc[moved, "team"] = F.loc[moved, "dc_team"]
            F.loc[moved, "team_changed"] = True
            F = F.drop(columns=["dc_team", "dc_date"])
    # the league's weekly roster: a trade shows there within days (2026-11-09: owner, after DeForest Buckner left IND).
    # Only a roster row newer than his last game moves him; a new team on a bye drops him from this week (he is gone).
    if roster:
        cur = [roster.get(str(pid)) for pid in F.player_id]
        new_t = pd.Series([c[0] if c else None for c in cur], index=F.index)
        new_w = pd.Series([c[1] if c else -1 for c in cur], index=F.index)
        moved_r = new_t.notna() & (new_t != F.team) & (new_w > pd.to_numeric(F.last_week, errors="coerce").fillna(99)) & ~F.team_changed.astype(bool)
        F.loc[moved_r, "team"] = new_t[moved_r]
        F.loc[moved_r, "team_changed"] = True
    moved_info = F.loc[F.team_changed.astype(bool) & (F.team_from != F.team), ["player_id", "team", "team_from", "group", "pct_last", "last_week"]].copy()   # before the games merge drops a player whose new team is on a bye
    F = F.merge(games[["team", "game_id", "venue", "spread_dog", "is_home", "opp_team", "gameday", "gametime", "final", "rest", "margin", "roof"]], on="team", how="inner")
    F["season"], F["week"] = season, week
    ts, lg_snaps = team_snaps_for(H, season, week)
    F["solo_drift"] = solo_drift_for(H, season, week)
    F["tsnaps_exp"] = (F.team.map(ts.get("defence", {})).fillna(lg_snaps) + F.opp_team.map(ts.get("offence", {})).fillna(lg_snaps)) / 2
    mt, _ = matchup_for(H, season, week)
    F["allowed_rel"] = [mt.get((o, g), 1.0) for o, g in zip(F.opp_team, F.group)]
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
    out_ids = set(inj_w[inj_w.status.str.lower().isin(["out", "doubtful"])].player_id.astype(str)) - {"", "nan", "None"} if len(inj_w) and "player_id" in inj_w else set()
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
    team_last_week = done.groupby("team").week.max().to_dict()
    # next man up fires in the first game without the regular (he played the team's last game), as the backtest defines and
    # validated it; weeks 2-4 of an absence are carried by the backup's own last game, share model and vacancy rule
    vacated = {(r.team, r.group) for r in regs.itertuples() if (r.team, r.name_key) in out_keys and r.last_week == team_last_week.get(r.team)}
    # a regular traded away since his old team's last game: the next man up there, exactly as for one ruled out (the
    # backtest's role signal is any regular present last game and gone this one, trades included)
    moved_all = moved_info
    for r in moved_all.itertuples():
        if (r.pct_last if r.pct_last == r.pct_last else 0) >= 0.75 and r.last_week == team_last_week.get(r.team_from):
            vacated.add((r.team_from, r.group))
    moved_to = {r.player_id: r.team for r in moved_all.itertuples()}
    # vacancy (persistent): a regular by his last game's share who is out, has moved, or missed the team's last game,
    # within the last three weeks. Regulars include players no longer in F (gone from the roster) via `done`.
    vc = C.VACANCY
    last_rows = done.sort_values("week").groupby("player_id").tail(1)
    vac, gone_by = set(), {}
    for r in last_rows.itertuples():
        if (r.def_pct if r.def_pct == r.def_pct else 0) < vc["regular_share"] or week - r.week > vc["recent_weeks"]:
            continue
        listed_now = r.team in starters and r.player_id in starters[r.team]
        missed = r.week < team_last_week.get(r.team, r.week) and not listed_now      # missed the last game and not listed back as a starter
        traded = r.player_id in moved_to and moved_to[r.player_id] != r.team
        gone = (r.team, r.name_key) in out_keys or missed or traded
        if gone:
            vac.add((r.team, r.group))
            why = f"traded to {moved_to[r.player_id]}" if traded else str(status.get((r.team, r.name_key)) or "").lower() or "missed the last game"
            gone_by.setdefault((r.team, r.group), []).append(f"{r.player} ({r.def_pct:.0%} of the snaps in his last game; {why})")
    F["vacancy"] = [(t, g) in vac for t, g in zip(F.team, F.group)]
    # who is gone at his position, for the card: the model's context in words (the effects are in the factors)
    F["gone_regulars"] = ["; ".join(x for x in gone_by.get((t, g), []) if not x.startswith(f"{pl} (")) for t, g, pl in zip(F.team, F.group, F.player)]
    F["dc_starter"] = [(1.0 if pid in starters[t] else 0.0) if t in starters else np.nan for t, pid in zip(F.team, F.player_id)]   # no chart: unknown (training saw 0.5)
    F["role_signal"] = [((t, g) in vacated) and not (p >= 0.75) and (t, n) not in out_keys
                        for t, g, p, n in zip(F.team, F.group, F.pct_prev.fillna(0), F.name_key)]
    return F


SIGNALS = {   # signal -> (short label for the card, what it means in football terms). Each is switched to neutral in turn and the FINAL number rebuilt
    "snaps": ("Snap share", "his snap share in his recent games against his season share"),
    "role": ("Next man up", "a regular at his position is out and he is the backup who steps in"),
    "vacancy": ("Teammate out", "a regular at his position group is out or gone"),
    "tilt": ("Spread", "point spread: an underdog's defence faces more plays"),
    "volume": ("Opponent volume", "tackle chances expected this game (opponent carries + completions + sacks) against what he has faced"),
    "mix": ("Run/pass mix", "this opponent's run/pass mix against the mix he has faced"),
    "depth": ("Depth chart", "promoted or demoted on the latest depth chart"),
    "pfr": ("Coverage", "how often he is targeted in coverage and how often he misses tackles"),
    "dome": ("Indoors", "corners run higher indoors"),
    "last": ("Last game", "his last game against his season average"),
    "injury": ("Injury report", "listed questionable or limited in practice"),
    "rest": ("Rest", "days since his team's last game"),
    "crew": ("Stat crew", "how this stadium's stat crew has credited tackles"),
    "matchup": ("Matchup", "tackles this opponent has allowed to his position group"),
    "absence": ("Absence", "weeks since his last game, or a new team"),
}


def _neutral(F, key, typ=None):
    """The feature rows with one signal switched to neutral: as if it said nothing about this game."""
    G = F.copy()
    n = G.n_prev.astype(float).clip(lower=1)
    has = lambda *cols: all(c in G for c in cols)
    if key == "snaps" and has("pct_prev"):
        for c in ("pct_last", "pct_last3"):
            if c in G:
                G[c] = G.pct_prev.where(G.pct_prev.notna(), G[c])
    elif key == "role":
        G["role_signal"] = False
    elif key == "vacancy":
        G["vacancy"] = False
    elif key == "tilt":
        G["spread_dog"] = 0.0
    elif key == "volume" and has("exp_opps", "opps_prev_mean"):
        G["exp_opps"] = G.opps_prev_mean.where(G.opps_prev_mean.notna(), G.exp_opps)
    elif key == "mix" and has("exp_runs", "exp_comps", "runs_faced_prev", "comps_faced_prev"):
        G["exp_runs"] = (G.runs_faced_prev / n).where(G.runs_faced_prev.notna(), G.exp_runs)
        G["exp_comps"] = (G.comps_faced_prev / n).where(G.comps_faced_prev.notna(), G.exp_comps)
    elif key == "depth":
        G["promoted"], G["demoted"] = False, False
    elif key == "pfr":
        if has("targets_prev") and typ is not None and typ == typ and typ > 0:
            db = G.group.isin(["CB", "S"]) & G.targets_prev.notna()
            G.loc[db, "targets_prev"] = typ * n[db]
        if has("missed_prev", "pfr_comb_prev"):
            ok, base = G.missed_prev.notna(), C.PFR["miss_base"]
            G.loc[ok, "missed_prev"] = base / (1 - base) * G.pfr_comb_prev.fillna(0)[ok]
    elif key == "dome":
        G["roof"] = ""
    elif key == "last" and has("last", "comb_prev_raw"):
        G["last"] = (G.comb_prev_raw / n).where(G.n_prev > 0, G["last"])
    elif key == "injury":
        G["status"], G["practice"] = "", ""
    elif key == "rest":
        G["rest"] = 7
    elif key == "crew":
        G["crew_comb"], G["crew_solo"] = 1.0, 1.0
    elif key == "matchup":
        G["allowed_rel"] = 1.0
    elif key == "absence":
        G["gap_weeks"], G["team_changed"] = 1, False
    return G


def signal_effects(F, final, scale, gbm, typ=None):
    """How far each signal moved the final projection: the number rebuilt with that signal neutral (through the factor
    model and the corrector both), as final / rebuilt - 1 per row. This is what the card's Game logic shows: with the
    corrector at 80% of the number, a factor's own multiplier says little about what reached the projection."""
    out = {}
    fin = np.asarray(final, dtype=float)
    for key in SIGNALS:
        G = _neutral(F, key, typ)
        mu = project_frame(G, pfr_typ=typ)[1] * scale
        cf = blend_gbm(mu, gbm(gbm_features(G, mu))) if gbm is not None else np.asarray(mu, dtype=float)
        out[key] = fin / np.clip(np.asarray(cf, dtype=float), 1e-6, None) - 1
    return out


def finalize_projections(F, phi_by_group, k=None, scale=1.0, gbm=None):
    """scale: the backtest's level calibration (actual / predicted), applied to the projected means.
    gbm: the trained corrector's predict function; its blend moves the combined projection and the solo one in step."""
    if F.empty:
        return F
    parts = {}
    typ = phi_by_group.get("__pfr_typical__") if isinstance(phi_by_group, dict) else None
    base, mu, mu_solo = project_frame(F, k=k, parts=parts, pfr_typ=typ)
    mu_raw = mu.copy()
    scale_solo = phi_by_group.get("__scale_solo__", scale) if isinstance(phi_by_group, dict) else scale
    by_grp = F.group.map({g: phi_by_group.get(f"{g}|solo_scale") for g in F.group.unique()}) if isinstance(phi_by_group, dict) else pd.Series(np.nan, index=F.index)
    mu, mu_solo = mu * scale, mu_solo * by_grp.fillna(scale_solo).values     # solo level per position (CB and S run highest)
    # the model trains on nflverse's solo alone (a stable series); the books and the grader settle on the official count,
    # which adds tackles made with an assist: this season's rate of them (run.py stores it; 2.4% of solo in 2026)
    official = float(phi_by_group.get("__solo_official__", 1.0)) if isinstance(phi_by_group, dict) else 1.0
    mu_solo = mu_solo * official
    if gbm is not None:
        g = gbm(gbm_features(F, mu))
        blended = pd.Series(blend_gbm(mu, g), index=F.index)
        ratio = (blended / mu.clip(lower=1e-6)).clip(0.5, 2.0)
        F = F.assign(proj_factor=mu.values, proj_gbm=np.asarray(g))
        mu, mu_solo = blended, mu_solo * ratio
    F = F.assign(base=base.values, proj=mu.values, proj_solo=mu_solo.values)
    # how the number was built, for the card (logic_steps): the pieces of the base (lf_*), and how far each signal moved the
    # final number (fx_*: the projection rebuilt with that signal neutral)
    extra = {"lf_" + k_: v for k_, v in parts.items()}
    extra["lf_scale"] = float(scale) if np.isscalar(scale) else np.asarray(scale, dtype=float)
    extra["lf_scale_solo"] = by_grp.fillna(scale_solo).values
    extra["lf_official"] = official
    extra["lf_gbm"] = (mu.values / np.clip(mu_raw.values * (float(scale) if np.isscalar(scale) else 1.0), 1e-6, None)) if gbm is not None else 1.0
    try:
        extra.update({"fx_" + k_: v for k_, v in signal_effects(F, mu.values, scale, gbm, typ).items()})
    except Exception as e:  # noqa: BLE001    (the card's explanation must never stop the projections)
        print(f"projections: signal effects skipped ({type(e).__name__}: {e})")
    F = pd.concat([F.drop(columns=[c for c in extra if c in F.columns]), pd.DataFrame(extra, index=F.index)], axis=1)      # one join: many single inserts fragment the frame
    F["phi"] = F.group.map(phi_by_group).fillna(1.0)
    F["share_pred"] = share_pred(F).values
    F["rate_clean"] = persnap_rate(F).values
    F["vacancy_rule"] = (vacancy_rule(F) & bool(C.FACTORS.get("vacancy", True))).values
    # a lineman's profile for the card (PFR pressures per game, prior games): no model effect (research round 5 rejected it)
    F["press_pg"] = (pd.to_numeric(_col_or(F, "press_prev", np.nan), errors="coerce") / F.n_prev.astype(float).clip(lower=1)).where(F.group == "DL").values
    low = F.share_pred.fillna(_col_or(F, "pct_prev", 1.0)).fillna(1.0) < C.PHI_SHARE_SPLIT
    low_phi = F.group.map({g: phi_by_group.get(f"{g}:low") for g in F.group.unique()})
    F.loc[low & low_phi.notna(), "phi"] = low_phi[low & low_phi.notna()]
    # solo tackles are less spread than combined ones: their own dispersion
    F["phi_solo"] = F.group.map({g: phi_by_group.get(f"{g}|solo") for g in F.group.unique()})
    low_solo = F.group.map({g: phi_by_group.get(f"{g}:low|solo") for g in F.group.unique()})
    F.loc[low & low_solo.notna(), "phi_solo"] = low_solo[low & low_solo.notna()]
    F["phi_solo"] = F.phi_solo.fillna(F.phi)
    F.loc[F.venue == "NEUTRAL", "phi"] = F.phi + 0.15
    F.loc[F.venue == "NEUTRAL", "phi_solo"] = F.phi_solo + 0.15
    fl = role_shift_flags(F)
    for c_ in fl.columns:
        F[c_] = fl[c_].values
    F["snap_jump"] = snap_jump(F).values
    # a new role spreads his count: the extra spread the backtest measured around the final projection, else the config's
    bump = float(phi_by_group.get("__new_role_bump__", C.NEW_ROLE["phi_bump"])) if isinstance(phi_by_group, dict) else C.NEW_ROLE["phi_bump"]
    bump_solo = float(phi_by_group.get("__new_role_bump_solo__", C.NEW_ROLE.get("phi_bump_solo", 0.25))) if isinstance(phi_by_group, dict) else C.NEW_ROLE.get("phi_bump_solo", 0.25)
    F.loc[F.new_role, "phi"] = F.phi + bump
    F["fair_line"] = [fair_line(m, p) for m, p in zip(F.proj, F.phi)]
    # assists: the combined projection less the solo one; their own dispersion from the backtest when it has one
    F["proj_ast"] = (F.proj - F.proj_solo).clip(lower=0.05)
    F["phi_ast"] = F.group.map({g: phi_by_group.get(f"{g}|ast") for g in F.group.unique()}) if isinstance(phi_by_group, dict) else np.nan
    low_ast = F.group.map({g: phi_by_group.get(f"{g}:low|ast") for g in F.group.unique()}) if isinstance(phi_by_group, dict) else pd.Series(np.nan, index=F.index)
    F.loc[low & low_ast.notna(), "phi_ast"] = low_ast[low & low_ast.notna()]
    F["phi_ast"] = F.phi_ast.fillna(F.phi)
    F.loc[F.venue == "NEUTRAL", "phi_ast"] = F.phi_ast + 0.15
    F.loc[F.new_role, "phi_solo"] = F.phi_solo + bump_solo
    F.loc[F.new_role & F.phi_ast.notna(), "phi_ast"] = F.phi_ast + bump_solo
    F["fair_line_solo"] = [fair_line(m, p) for m, p in zip(F.proj_solo, F.phi_solo)]
    F["fair_line_ast"] = [fair_line(m, p) for m, p in zip(F.proj_ast, F.phi_ast)]
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


def claimed_prob(p_side, adj=0.0):
    """Legacy (picks logged before the engine, through week 9 of 2026, that carry no claimed chance): the old pricer's chance shrunk toward even."""
    return float(np.clip(0.5 + C.CLAIM_SHRINK * (float(p_side) - 0.5) + float(adj), 0.05, 0.95))


# ---- the engine (config.ENGINE): one probability per line
def fair_over(over_odds, under_odds):
    """The book's fair chance of the Over from its own two-way price: each side's implied chance over their sum (the vig
    taken out in proportion). NaN when the book quotes one side only: a one-sided price holds an unknown vig."""
    if over_odds is None or under_odds is None or pd.isna(over_odds) or pd.isna(under_odds):
        return float("nan")
    po, pu = 1 / american_to_decimal(over_odds), 1 / american_to_decimal(under_odds)
    return po / (po + pu)


def _logit(p):
    p = min(max(float(p), 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def engine_chance(p_model, p_fair, beta):
    """The book's fair chance moved by `beta` of the model's disagreement, in log-odds. beta 0 is the book, 1 the model."""
    z = _logit(p_fair) + beta * (_logit(p_model) - _logit(p_fair))
    return 1 / (1 + math.exp(-z))


@functools.lru_cache(maxsize=200000)
def _implied_mean(p_over_target, phi, line):
    lo, hi = 0.05, 40.0
    for _ in range(50):
        mid = (lo + hi) / 2
        if p_over(mid, phi, line) < p_over_target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def implied_mean(p_over_target, phi, line):
    """The mean of a count with spread phi whose chance of clearing `line` is `p_over_target`: a chance read back as a
    number of tackles (the book's own expectation from its fair price, or the engine's from its win chance)."""
    if p_over_target is None or pd.isna(p_over_target) or pd.isna(phi) or pd.isna(line):
        return float("nan")
    return _implied_mean(round(float(np.clip(p_over_target, 1e-4, 1 - 1e-4)), 4), round(float(phi), 3), float(line))


def kelly_fraction(p, dec):
    """The Kelly fraction of a bet with chance p at decimal odds dec (0 when there is no edge)."""
    if dec is None or pd.isna(dec) or dec <= 1 or p is None or pd.isna(p):
        return 0.0
    b = float(dec) - 1
    return max(0.0, (float(p) * b - (1 - float(p))) / b)


def kelly_stake(p_low, dec):
    """Units to stake on a pick before the slate is sized (config.STAKE): a fraction of the Kelly fraction of the
    bankroll AT THE CAUTIOUS CHANCE, clipped; None when the price is missing. A pick that only just survives the cautious
    test gets the minimum. The correlation divisor and the game, kind and slate caps come later (grade.size_stakes)."""
    c = C.STAKE
    if dec is None or pd.isna(dec) or dec <= 1 or p_low is None or pd.isna(p_low) or float(p_low) * float(dec) - 1 < C.ENGINE["pick_edge_low"] - 1e-12:
        return None                                   # no price, or not a pick at the cautious chance
    return float(np.clip(c["kelly_fraction"] * kelly_fraction(p_low, dec) * c["bankroll"], c["min"], c["max"]))


def engine_betas(kind):
    """(weight, cautious weight) of the model's disagreement for a market kind: config.ENGINE["beta_by_kind"], else "beta"."""
    e = C.ENGINE
    b = float((e.get("beta_by_kind") or {}).get(kind, e["beta"]))
    return b, b * float(e.get("low_ratio", e["beta_low"] / e["beta"]))


def engine_grade(edge_low, p_model_side, blocked, market=None, sleeper_match=None):
    """A, B or C for a pick, from numbers that cannot improve when the book agrees more. A (config.ENGINE["a_rule"] ==
    "sleeper"): a pick that is also a sleeper on the same side, the lock checklist clear, a market that can carry an A.
    With the older rule ("model"): a cautious edge of 2%+ and the model's own chance at a_model or more. B: a cautious edge
    of 2%+. C: a pick short of that. None when it is not a pick. sleeper_match None means the caller does not know: the
    older rule is used."""
    e = C.ENGINE
    if edge_low is None or pd.isna(edge_low) or edge_low < e["pick_edge_low"]:
        return None
    can_a = not blocked and (market is None or market in C.A_GRADE_MARKETS)
    if e.get("a_rule") == "sleeper" and sleeper_match is not None:
        if sleeper_match and can_a:
            return "A"
        return "B" if edge_low >= e["b_edge_low"] else "C"
    if edge_low >= e["b_edge_low"]:
        return "A" if p_model_side >= e["a_model"] and can_a else "B"
    return "C"


def grade_of(score):
    """Legacy name: the score bar of an A (the grade itself needs the cautious edge and the checklist: engine_grade)."""
    return "A" if score >= C.LOCK_MIN_SCORE else "B"


def _num(v, d=np.nan):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return d
    return d if np.isnan(v) else v


def rundown(p, line, side, kind, mu_model, eng, pick, why, fl, new_role, in_role_n, log_raw):
    """A templated read-up of one line from the numbers the pricer used: who he is, his recent games, the model's
    read against the book's price, what the book's line implies about his snaps, what decides it, and the context. Every
    sentence is a number restated; nothing here is a view the data does not hold. `kind`: 'solo', 'assists' or 'combined'.
    eng: dict(p_model, fair, p, p_low, ev, edge_low, mkt_mean) for this side."""
    kind = kind if isinstance(kind, str) else ("solo" if kind else "combined")
    solo = kind == "solo"; ast = kind == "assists"
    stat = {"solo": "solo tackles", "assists": "assists"}.get(kind, "tackles + assists")
    n = int(_num(p.get("n_prev"), 0)); grp = str(p.get("group", "")); team = str(p.get("team", ""))
    solo_sum = _num(p.get("solo_prev_raw"), _num(p.get("solo_prev")))
    avg = (solo_sum if solo else (_num(p.get("comb_prev_raw")) - solo_sum) if ast else _num(p.get("comb_prev_raw"))) / max(n, 1) if n else np.nan
    share = _num(p.get("pct_prev")); last_sh = _num(p.get("pct_last")); exp_sh = _num(p.get("share_pred")); rate = _num(p.get("rate_clean"))
    ps_g = int(_num(p.get("ps_games"), 0)); ps_avg = _num(p.get("ps_avg_raw"))
    out = []
    pos = {"CB": "corner", "S": "safety", "LB": "linebacker", "DL": "lineman"}.get(grp, grp)
    who = f"{p.player}, {team} {pos}"
    if n:
        who += f": {avg:.1f} {stat} a game over {n} game{'s' if n != 1 else ''} this season"
        if not np.isnan(share):
            who += f" at {share:.0%} of the defensive snaps"
    if ps_g >= 4 and not np.isnan(ps_avg) and not solo and not ast:
        who += f"; last season {ps_avg:.1f} a game over {ps_g} games"
    out.append(who + ".")
    lp = _log(p, "log_pct"); lg = log_raw or []
    if lg:
        tail = lg[-3:]; sh = [x for x in lp[-3:]] if lp and len(lp) == len(lg) else []
        recent = ", ".join(f"{int(x)}" + (f" on {s:.0%}" if sh and len(sh) == len(tail) else "") for x, s in zip(tail, sh if sh and len(sh) == len(tail) else [np.nan] * len(tail)))
        out.append(f"Last {len(tail)} game{'s' if len(tail) != 1 else ''}: {recent}{' of the snaps' if sh and len(sh) == len(tail) else ''}.")
    if not np.isnan(exp_sh) and not np.isnan(last_sh) and abs(exp_sh - last_sh) >= 0.15:
        out.append(f"Expected at {exp_sh:.0%} of the snaps tonight against {last_sh:.0%} last game.")
    # the model's read against the book's price
    mm = eng.get("mkt_mean")
    out.append(f"The model's own number is {mu_model:.1f}, which gives the {side.lower()} of {line:g} a {eng['p_model']:.0%} chance. The book's price, with its margin taken out, says {eng['fair']:.0%}"
               + (f" (as a number of tackles: {mm:.1f})" if mm is not None and mm == mm else "") + f". Counting the model's disagreement at half its size, the win chance is {eng['p']:.0%}: "
               f"{eng['ev']:+.0%} at this price. Counted at a quarter (the cautious test a pick must pass): {eng['p_low']:.0%}, {eng['edge_low']:+.0%}.")
    # the book's reading: the snap share at which the model's number would meet the line (the per-snap part scales with share)
    if not np.isnan(exp_sh) and exp_sh > 0.05 and mu_model > 0.05 and not np.isnan(rate):
        implied = float(np.clip(exp_sh * line / mu_model, 0.05, 1.0))
        if abs(implied - exp_sh) >= 0.08:
            out.append(f"The book's line sits where the model would put him at about {implied:.0%} of the snaps; the model expects {exp_sh:.0%}. The two sides disagree about his playing time more than his tackle rate.")
        else:
            out.append(f"The line matches the model at about {implied:.0%} of the snaps, close to the {exp_sh:.0%} expected: the disagreement, if any, is about his tackle rate, which is mostly variance.")
    # what decides it: the share of his games that landed on this side
    if lg:
        k = sum((x > line) if side == "Over" else (x < line) for x in lg)
        out.append(f"He landed on the {side.lower()} of {line:g} in {k} of his {len(lg)} games this season.")
    # context
    nud = []
    st = str(p.get("status", "")).lower()
    if st == "questionable":
        nud.append("listed questionable (the bet voids if he sits)")
    gone = str(p.get("gone_regulars") or "").strip()
    if gone and gone.lower() != "nan":
        nud.append(f"gone at his position: {gone}")
    elif _flag(p.get("vacancy", False)):
        nud.append("a regular at his position is out or gone")
    if new_role:
        nud.append("a part-timer who just played a starter's snaps; his history describes someone else")
    if fl.get("reduced_role"):
        nud.append("his last game's share was well below his season share")
    if fl.get("absence") or fl.get("missed_game"):
        nud.append("back from a missed game")
    if fl.get("new_team"):
        nud.append("first game for a new team")
    if _flag(p.get("opp_qb_out", False)):
        nud.append("the opposing starting quarterback is out")
    if _flag(p.get("opp_rb_out", False)):
        nud.append("the opposing lead rusher is out")
    dc = str(p.get("dc_status", ""))
    if dc in ("promoted", "demoted"):
        nud.append(f"{dc} on the latest depth chart")
    roof = str(p.get("roof", "")).lower()
    if grp == "CB" and roof in ("dome", "closed"):
        nud.append("indoors, where corners run higher")
    rest = _num(p.get("rest"))
    if not np.isnan(rest) and rest >= 10:
        nud.append("off a bye")
    fp = _num(p.get("fp_rel_solo") if solo else p.get("fp_rel_comb"))
    if not np.isnan(fp) and abs(fp) >= 0.08:
        nud.append(f"the outside expert consensus sits {fp:+.0%} from its usual relation to this model for him")
    if nud:
        out.append("Also: " + "; ".join(nud) + ".")
    out.append(("Pick: " if pick in ("Over", "Under") else "No pick: ") + why + ".")
    return " ".join(out)


def parlay_corr_ratio(legs):
    """How much a parlay's chance differs from the product of its legs' chances because legs on the same defence
    share the plays it faces. legs: iterable of dicts with mu, phi, exp_opps, line, side, event_id (and team).
    Simulated: one plays draw per game, each leg's count drawn around its mean scaled by that draw, with the
    within-game dispersion (the leg's dispersion less the plays' share of it). Returns the ratio P(all) / prod P,
    clipped (config.PARLAY_CORR); 1.0 when the legs are in different games or anything is missing."""
    c = C.PARLAY_CORR
    legs = [dict(l) for l in legs]
    if len(legs) < 2 or any(l.get(k) is None or pd.isna(l.get(k)) for l in legs for k in ("mu", "phi", "exp_opps", "line", "side")):
        return 1.0
    keys = [(l.get("event_id"), l.get("team")) for l in legs]
    if len(set(keys)) == len(legs):
        return 1.0          # no two legs on one defence
    rng = np.random.default_rng(7)
    n, sd = int(c["sims"]), float(c["sd_plays"])
    plays = {k: None for k in set(keys)}
    hit_all, prod = np.ones(n, dtype=bool), 1.0
    for l, k in zip(legs, keys):
        eo = max(10.0, float(l["exp_opps"]))
        if plays[k] is None:
            plays[k] = np.clip(rng.normal(eo, sd, n), 0.3 * eo, None)
        mu, phi = max(0.05, float(l["mu"])), float(l["phi"])
        phi_w = max(c["phi_floor"], phi - mu * (sd / eo) ** 2)
        m = mu * plays[k] / eo
        if phi_w <= 1.02:
            x = rng.poisson(m)
        else:
            r = m / (phi_w - 1); x = rng.negative_binomial(r, 1 / phi_w)
        h = (x < float(l["line"])) if l["side"] == "Under" else (x > float(l["line"]))
        hit_all &= h; prod *= max(1e-9, float(h.mean()))
    return float(np.clip(hit_all.mean() / prod, *c["clip"]))


def logic_steps(p, kind="combined", min_effect=0.0):
    """How the model built a player's number, from what finalize_projections stored: his base rate and the per-snap view
    (lf_*), then how far each signal moved the FINAL projection (fx_*: the number rebuilt with that signal neutral, through
    the factor model and the corrector both), the two models' own numbers, and the solo share. Returns (steps, text):
    steps are (label, effect as a fraction or None, detail) in order; text is one paragraph. Empty when the row has no pieces."""
    g = lambda c, d=np.nan: _num(p.get(c), d) if hasattr(p, "get") else d
    if np.isnan(g("lf_base")):
        return [], ""
    kind = kind if isinstance(kind, str) else ("solo" if kind else "combined")
    n = int(g("n_prev", 0)); avg = g("comb_prev_raw", np.nan) / max(n, 1) if n else np.nan
    grp = str(p.get("group", "")); steps = []
    prior = f"last season's {g('ps_avg_raw', g('ps_avg')):.1f}" if g("ps_games", 0) >= 4 and not np.isnan(g("ps_avg_raw", g("ps_avg"))) else f"the {grp} average"
    rate_lab = "Season rate" if kind == "combined" else "Season rate (tackles + assists; the solo share comes last)"
    steps.append((rate_lab, None, f"{avg:.1f} a game over {n} games, weighted with {prior}: {g('lf_base'):.1f}" if n else f"no games yet: {prior}"))
    ps = g("lf_persnap")
    if not np.isnan(ps):
        w_ps = C.PERSNAP["weight"]
        steps.append(("Per-snap view", None, f"{g('rate_clean'):.3f} tackles a snap x {g('share_pred'):.0%} of {g('tsnaps_exp'):.0f} expected defensive snaps = {ps:.1f}; blended {1 - w_ps:.0%}/{w_ps:.0%} with the season rate"))
    for k_, (lab, what) in SIGNALS.items():
        v = g("fx_" + k_, 0.0)
        if np.isnan(v) or abs(v) < max(min_effect, 0.005):
            continue
        detail = what
        if k_ == "volume" and not np.isnan(g("exp_opps")) and not np.isnan(g("opps_prev_mean")):
            detail = f"{g('exp_opps'):.0f} tackle chances expected against the {g('opps_prev_mean'):.0f} he has faced a game"
        elif k_ == "snaps" and not np.isnan(g("pct_last")) and not np.isnan(g("pct_prev")):
            detail = f"{g('pct_last'):.0%} of the snaps last game" + (f", {g('pct_last3'):.0%} over his last three," if not np.isnan(g("pct_last3")) else "") + f" against {g('pct_prev'):.0%} this season"
        elif k_ == "tilt" and not np.isnan(g("spread_dog")):
            sd = g("spread_dog"); detail = f"his team is a {abs(sd):g}-point {'underdog' if sd > 0 else 'favourite'}: {'more' if sd > 0 else 'fewer'} plays for his defence"
        elif k_ == "depth" and str(p.get("dc_status") or "") in ("promoted", "demoted"):
            detail = f"{p.get('dc_status')} on the latest depth chart"
        elif k_ == "injury":
            detail = f"listed {str(p.get('status') or p.get('practice') or 'on the report').lower()}"
        elif k_ == "last" and not np.isnan(g("last")) and not np.isnan(avg):
            detail = f"{g('last'):.0f} last game against {avg:.1f} a game this season"
        elif k_ == "rest" and not np.isnan(g("rest")):
            detail = f"{g('rest'):.0f} days since his team's last game"
        elif k_ == "matchup" and not np.isnan(g("allowed_rel")):
            detail = f"this opponent has allowed {g('allowed_rel') - 1:+.0%} against the league to his position group"
        steps.append((lab, float(v), detail))
    pf, pg_ = g("proj_factor"), g("proj_gbm")
    if not np.isnan(pf) and not np.isnan(pg_):
        w = C.GBM["weight"]
        steps.append(("Two models", None, f"the factor model says {pf:.1f}, the boosted model (trained on every defender-game since 2023) {pg_:.1f}; the number is {1 - w:.0%} the first and {w:.0%} the second"))
    if kind == "solo":
        steps.append(("Solo share", None, f"{g('lf_solo_share'):.0%} of his tackles solo (his own, weighted with his position's)"))
        off = g("lf_official", 1.0)
        if not np.isnan(off) and abs(off - 1) >= 0.005:
            steps.append(("Official count", float(off - 1), "the books count a tackle made with an assist as solo; this season's share of them"))
    total = g("proj_solo") if kind == "solo" else g("proj") - g("proj_solo") if kind == "assists" else g("proj")
    unit = {"solo": "solo tackles", "assists": "assists"}.get(kind, "tackles + assists")
    bits = [f"{lab} {e:+.0%}" if e is not None else f"{lab}: {d}" for lab, e, d in steps]
    text = f"How the model built {total:.1f} {unit}: " + "; ".join(bits) + "."
    if any(e is not None and lab != "Official count" for lab, e, _ in steps):
        text += " Each percentage is how far that signal moved the final number: the projection rebuilt without it."
    if kind == "assists":
        text += " Assists are the combined number less the solo one."
    gone = str(p.get("gone_regulars") or "").strip() if hasattr(p, "get") else ""
    if gone and gone.lower() != "nan":
        text += f" Gone at his position (the Teammate out and Next man up effects above already carry it): {gone}."
    if _flag(p.get("team_changed", False)) if hasattr(p, "get") else False:
        text += f" He was traded or moved: first games for {p.get('team')}, never a lock until he settles."
    return steps, text


def sleeper_grade(side, p_model, exp_opps, unsteady):
    """A sleeper's grade from the model's own evidence only (config.SLEEPER): a steady role for A or B; a solo Under is an A
    with a 70%+ model chance or a low-volume game (under 50 expected tackle opportunities); a combined Over is at most a B.
    Returns (grade, reason)."""
    sl = C.SLEEPER
    if unsteady:
        return "C", "role not settled: " + ", ".join(unsteady)
    if side == "Under":
        strong = [t for ok, t in ((p_model >= sl["a_model"], f"the model's own chance is {sl['a_model']:.0%} or more"),
                                  (exp_opps is not None and exp_opps < sl["a_opps"], f"his defence expects fewer than {sl['a_opps']:.0f} tackle opportunities")) if ok]
        if strong:
            return "A", "steady role, and " + " and ".join(strong)
        return "B", f"steady role, but neither a {sl['a_model']:.0%}+ model chance nor a low-volume game"
    if p_model >= sl["b_model_over"]:
        return "B", f"steady role and a {sl['b_model_over']:.0%}+ model chance (combined Overs top out at B until their record earns an A)"
    return "C", f"model chance under {sl['b_model_over']:.0%}"


def sleeper_note(side, kind, mu, line, phi, p_model, log_raw, exp_opps, grade, why, at_price=""):
    """One short paragraph for the site: the model's number against the line, its own chance of the side from its count
    distribution, the player's season against the line, the game's volume, the grade with its reason, and what the
    pricing engine makes of the same line at its price."""
    k_under, k_over = int(math.floor(line)), int(math.floor(line)) + 1
    unit = "solo tackles" if kind == "solo" else "tackles + assists"
    target = f"{k_under} or fewer" if side == "Under" else f"{k_over} or more"
    spread = "Poisson" if abs(phi - 1) < 0.02 else (f"{phi:.2f}x Poisson spread" if phi > 1 else f"tighter than Poisson ({phi:.2f}x)")
    parts = [f"Model {mu:.1f} {unit} against a line of {line:g} ({mu - line:+.1f}).",
             f"The model's own chance of {target}: {p_model:.0%} (its count model, {spread})."]
    if log_raw:
        n_side = sum(1 for x in log_raw if (x <= k_under if side == "Under" else x >= k_over))
        parts.append(f"His season: median {float(np.median(log_raw)):g}, {target} in {n_side} of {len(log_raw)} games.")
    if exp_opps is not None:
        parts.append(f"His defence expects {exp_opps:.0f} tackle opportunities (carries + completions + sacks; league about 50).")
    parts.append(f"Grade {grade}: {why}.")
    if at_price:
        parts.append(at_price)
    return " ".join(parts)


def price_lines(lines, P, segments=None, blend=None):
    """Evaluate every posted line against the projection (the engine, config.ENGINE); return one row per line with the win
    chance, the cautious chance, the returns at this book's price, the pick, the grade and the stake before slate sizing.
    `segments` and `blend` are accepted and ignored: the corrections they carried were retired on 2026-11-09."""
    if lines is None or len(lines) == 0 or P is None or len(P) == 0:
        return pd.DataFrame()
    from pipeline.sources import norm_name
    e_ = C.ENGINE
    L = lines.copy()
    L["name_key"] = L.player.map(norm_name)
    # the consensus line across books, from rows that quote both sides: Bally Bet posts Over-only rows, sometimes far off
    # (2026-10-31: Jordyn Brooks 25.5 against DraftKings' 8.5 made a 17.0 "consensus" and a +62% Over pick)
    two = L.over_odds.notna() & L.under_odds.notna()
    med_two = L[two].groupby(["player", "market"]).line.median()
    med_all = L.groupby(["player", "market"]).line.median()
    L["mkt_line"] = [med_two.get((p_, m_), med_all.get((p_, m_))) for p_, m_ in zip(L.player, L.market)]
    # the fair chance at each line: the vig-free chance of the books that quote both sides of exactly this line, averaged.
    # A book alone on its line is its own anchor; a one-sided price is priced against the two-way books on the same line.
    L["_fair"] = [fair_over(o, u) for o, u in zip(L.over_odds, L.under_odds)]
    cons = L[two].groupby(["player", "market", "line"])._fair.agg(["mean", "size"])
    key3 = list(zip(L.player, L.market, L.line))
    L["fair_cons"] = [cons["mean"].get(k_, np.nan) if len(cons) else np.nan for k_ in key3]
    L["books_n"] = [int(cons["size"].get(k_, 0)) if len(cons) else 0 for k_ in key3]
    books_pm = L.groupby(["player", "market"]).book.nunique().to_dict()      # how many books post this player and market at all
    # the league's solo share to date, from every projected player's game log (for the solo-share gap, config.SHARE_GAP)
    _tot = lambda col: float(sum(sum(_log(row, col)) for row in P[[col]].to_dict("records"))) if col in P.columns else 0.0
    lg_solo, lg_comb = _tot("log_solo"), _tot("log_comb")
    league_share = lg_solo / lg_comb if lg_comb > 0 else float("nan")
    P = P.copy()
    P["team_name"] = P.team.map(TEAM_NAMES)
    rows = []
    for r in L.itertuples():
        cand = P[P.name_key == r.name_key]
        if len(cand) > 1:
            cand2 = cand[cand.team_name.isin([getattr(r, "home_team", None), getattr(r, "away_team", None)])]
            cand = cand2 if len(cand2) else cand
        kind = C.market_kind(r.market)
        solo, ast = kind == "solo", kind == "assists"
        clean = lambda v: None if v is None or (isinstance(v, float) and pd.isna(v)) else v
        base = dict(player=r.player, book=r.book, market=r.market, line=float(r.line), over_odds=r.over_odds,
                    under_odds=r.under_odds, commence_time=getattr(r, "commence_time", ""), event_id=getattr(r, "event_id", ""),
                    book_key=clean(getattr(r, "book_key", None)), over_link=clean(getattr(r, "over_link", None)), under_link=clean(getattr(r, "under_link", None)),
                    over_sid=clean(getattr(r, "over_sid", None)), under_sid=clean(getattr(r, "under_sid", None)), market_link=clean(getattr(r, "market_link", None)))
        if cand.empty:
            rows.append({**base, "pick": "No projection", "why": "Player not in the model (no defensive snaps logged)"})
            continue
        p = cand.iloc[0]
        mu_model = p.proj_solo if solo else p.get("proj_ast", max(0.05, p.proj - p.proj_solo)) if ast else p.proj
        phi_col = "phi_solo" if solo else "phi_ast" if ast else "phi"
        phi_use = float(p.get(phi_col, p.phi)) if pd.notna(p.get(phi_col, np.nan)) else float(p.phi)
        if mu_model is None or not np.isfinite(float(mu_model)):
            rows.append({**base, "pick": "No projection", "why": "The model has no number for him this week"})
            continue
        # the level for players who get lines (config.LINED_LEVEL), set by the daily from the season's earlier lined games
        level = float(p.get("lined_level", 1.0)) if kind in C.LINED_LEVEL["kinds"] and pd.notna(p.get("lined_level", np.nan)) else 1.0
        mu_model, line = float(mu_model) * level, float(r.line)
        fair = float(r.fair_cons) if pd.notna(r.fair_cons) else float("nan")
        ident = dict(team=p.team, opp=p.opp_team, group=p.group, jersey=None if pd.isna(p.get("jersey", np.nan)) else int(p.get("jersey")),
                     player_id=None if pd.isna(p.get("player_id", np.nan)) else str(p.get("player_id")), espn_id=None if pd.isna(p.get("espn_id", np.nan)) else str(p.get("espn_id")).split(".")[0])
        if not np.isfinite(fair):
            rows.append({**base, **ident, "proj_model": mu_model, "pick": "Pass", "why": "One-sided price, and no book quotes both sides of this line: there is no fair chance to price it against"})
            continue
        po_model = float(np.clip(p_over(mu_model, phi_use, line), 0.02, 0.98))     # the model's own chance of the Over
        beta, beta_low = engine_betas(kind)
        po, po_low = engine_chance(po_model, fair, beta), engine_chance(po_model, fair, beta_low)
        # a line no other book posts, which the model's own number puts beyond doubt, does not belong to this player as the
        # model knows him: theScore's "Sam Williams" 8.5 (a rotational lineman projected 2.6) was the top lock two weeks running
        misfit = max(po_model, 1 - po_model) >= e_.get("misfit_model", 2.0) and int(books_pm.get((r.player, r.market), 0)) <= 1
        # informational only, never part of the grade: the model and the consensus line far apart means one of them
        # knows something; the card says so and the reader checks
        far_from_line = abs(mu_model - float(r.mkt_line)) / max(1.0, float(r.mkt_line)) >= 0.25
        d_o = american_to_decimal(r.over_odds) if pd.notna(r.over_odds) else None
        d_u = american_to_decimal(r.under_odds) if pd.notna(r.under_odds) else None
        ev_o = po * d_o - 1 if d_o else -9
        ev_u = (1 - po) * d_u - 1 if d_u else -9
        side, ev = ("Over", ev_o) if ev_o > ev_u else ("Under", ev_u)
        dec = d_o if side == "Over" else d_u
        sgn = lambda x: x if side == "Over" else 1 - x
        p_side, p_low, p_model_side, fair_side = sgn(po), sgn(po_low), sgn(po_model), sgn(fair)
        edge_low = p_low * dec - 1
        fl = {k: _flag(p.get(k, False)) for k in ("new_role", "reduced_role", "absence", "missed_game", "new_team")}
        new_role = fl["new_role"]
        shifted = any(fl.values())
        log = _log(p, "log_solo" if solo else "log_ast" if ast else "log_comb")
        log_raw = list(log)
        # games in his current role: games where he played at least 70% of the snap share he played last game
        lp = _log(p, "log_pct")
        pct_last = p.get("pct_last", np.nan)
        in_role_n = int(p.n_prev)
        if lp and len(lp) == len(log) and pd.notna(pct_last):
            in_role = [x for x, sh in zip(log, lp) if sh >= C.NEW_ROLE["in_role_share"] * float(pct_last)]
            in_role_n = len(in_role)
            # every past game rescaled to the share he is expected to play now, so the log reads as his current role
            exp_share = p.get("share_pred", np.nan)
            if pd.notna(exp_share) and exp_share > 0.05:
                scaled = [x * float(np.clip(exp_share / sh, 0.5, 2.5)) for x, sh in zip(log, lp) if sh >= 0.15]
                log = scaled if len(scaled) >= C.NEW_ROLE["min_in_role_games"] else ([] if new_role else log)
            else:
                log = in_role if len(in_role) >= C.NEW_ROLE["min_in_role_games"] else ([] if new_role else log)
        hits = [(x > line) if side == "Over" else (x < line) for x in log]
        consistency = float(np.mean(hits)) if hits else float("nan")       # shown on the card; it adds nothing to the chance (MODEL_LOG A9) and is in no score
        gap = (p["last"] - p.base) if pd.notna(p["last"]) else 0.0
        fade = side == "Under" and gap >= C.FADE_GAP and not shifted       # context for the card: an Under after a big game in his usual role
        role_now = bool(_flag(p.role_signal))                              # next man up: a backup, a regular at his position out
        role = role_now and side == "Over"
        flagged = str(p.status).lower() in OUT_STATUSES
        uncertain = str(p.status).lower() == "questionable"
        thin = p.n_prev < C.MIN_GAMES_FOR_PICK and not role
        # the lock checklist (the model's own ground): where his history does not describe his role, or he may not play
        settled = in_role_n >= C.LOCK_RULES["min_in_role_games"] or in_role_n >= int(p.n_prev)
        snaps_missing = pd.isna(pct_last) and int(p.n_prev) > 0      # he has games but no snap count for his last one: the role checks are blind
        block = [name for ok, name in ((new_role, "new role"), (role_now, "next man up"), (fl["reduced_role"], "reduced role"), (fl["absence"] or fl["missed_game"], "back from absence"),
                                       (fl["new_team"], "new team"), (not settled, f"only {in_role_n} game{'s' if in_role_n != 1 else ''} in this role"),
                                       (uncertain, "questionable"), (snaps_missing, "snap counts missing for his last game"),
                                       (side == "Over" and not C.LOCK_RULES.get("overs_eligible", True), "Over side")) if ok]
        # an Under on a backup stepping in for a regular who is out, when the share model does not expect him to play much:
        # the projection runs 16% low on exactly these (config.LOCK_RULES), and a book that posts a line on him knows he plays
        sp_ = p.get("share_pred", np.nan)
        blind_under = role_now and side == "Under" and not C.LOCK_RULES.get("next_man_up_under", False) and not (pd.notna(sp_) and float(sp_) >= C.PHI_SHARE_SPLIT)
        tier = "pick" if edge_low >= e_["pick_edge_low"] else "lean" if ev >= e_["lean_edge"] else "pass"
        if flagged or thin or blind_under or misfit:
            tier = "pass"
        pick = side if tier == "pick" else "Pass"
        lock = 100.0 * p_model_side                                   # the lock score: the model's own chance of this side
        # a sleeper: the model's own number disagrees with the line by a margin that held in every live week (config.SLEEPER);
        # a frozen rule set tracked on its own record whether or not the engine makes the line a pick
        sl, sleeper, s_grade, s_p, s_note, s_med, s_ev = C.SLEEPER, "", None, None, None, None, None
        if not flagged and not thin:
            g_ = mu_model - line
            ok_o = d_o is not None and (sl["min_ev"] is None or ev_o >= sl["min_ev"])
            ok_u = d_u is not None and (sl["min_ev"] is None or ev_u >= sl["min_ev"])
            med = float(np.median(log_raw)) if log_raw else float("nan")
            if kind == "combined" and sl["comb_over"][0] <= g_ < sl["comb_over"][1] and ok_o:
                sleeper = "Over"
            elif solo and g_ <= sl["solo_under"] and ok_u and med == med and med >= line + sl.get("solo_hist", -99):
                sleeper = "Under"
            if sleeper:
                so = sleeper == "Over"
                s_p = float(po_model if so else 1 - po_model)
                s_med = med if med == med else None
                unsteady = [nm for ok, nm in ((new_role, "new role"), (fl["reduced_role"], "reduced role"), (fl["absence"] or fl["missed_game"], "back from absence"),
                                              (fl["new_team"], "new team"), (uncertain, "questionable"), (snaps_missing, "snap count missing"),
                                              (in_role_n < C.LOCK_RULES["min_in_role_games"], f"only {in_role_n} games in this role")) if ok]
                eo = p.get("exp_opps", np.nan)
                eo = float(eo) if pd.notna(eo) else None
                s_grade, s_why = sleeper_grade(sleeper, s_p, eo, unsteady)
                s_dec = d_o if so else d_u
                s_win, s_low = (po if so else 1 - po), (po_low if so else 1 - po_low)
                s_ev = float(s_win * s_dec - 1)
                s_edge_low = s_low * s_dec - 1
                verdict = ("the pricing engine also makes it a pick" if s_edge_low >= e_["pick_edge_low"] and sleeper == side and tier == "pick" else
                           "a lean for the pricing engine (an edge at the win chance, none at the cautious one): not staked" if s_ev >= e_["lean_edge"] else
                           "no edge for the pricing engine at this price")
                at_price = f"At this price: win chance {s_win:.0%} against {1 / s_dec:.0%} to break even ({s_ev:+.0%}); {verdict}."
                s_note = sleeper_note(sleeper, kind, mu_model, line, phi_use, s_p, log_raw, eo, s_grade, s_why, at_price)
        # the solo-share gap: a measurement, logged for every solo line, used by no rule
        share_gap = own_share = book_share = None
        comb_line = med_two.get((r.player, "player_tackles_assists")) if solo else None
        if solo and comb_line is not None and pd.notna(comb_line) and float(comb_line) > 0 and league_share == league_share:
            k_ = C.SHARE_GAP["k"]
            own_share = (sum(_log(p, "log_solo")) + k_ * league_share) / (sum(_log(p, "log_comb")) + k_)
            book_share = float(r.mkt_line) / float(comb_line)
            share_gap = float(own_share - book_share)
        # the grade, once the sleeper is known: an A is a pick the sleeper rule also names on the same side
        grade = engine_grade(edge_low, p_model_side, bool(block), r.market, sleeper_match=(sleeper == side)) if tier == "pick" else None
        not_a = tier == "pick" and grade != "A" and sleeper == side and (bool(block) or r.market not in C.A_GRADE_MARKETS)   # an A but for the checklist or the market
        num = f"win chance {p_side:.0%} against {1 / dec:.0%} to break even at this price ({ev:+.0%}); at the cautious chance {p_low:.0%} ({edge_low:+.0%}). Model alone {p_model_side:.0%}, the book's fair price {fair_side:.0%}"
        if flagged:
            why = f"His own status is {p.status or 'uncertain'}: wait for the final report"
        elif thin:
            why = f"Only {int(p.n_prev)} games of data"
        elif misfit:
            why = (f"No pick: this line does not fit him. Only {r.book} posts it and the model's number is {mu_model:.1f} against a line of {line:g}: a mis-posted line or another player of the same name. "
                   f"Check the name on the slip before touching it; the numbers, for the record: {num}")
        elif blind_under:
            why = (f"No pick: he is the next man up (a regular at his position is out) and the model expects him at {float(sp_):.0%} of the snaps" if pd.notna(sp_) else "No pick: he is the next man up (a regular at his position is out)") + \
                  f". On backups like this the projection has run 16% low, so its Under is not an edge; the numbers, for the record: {num}"
        elif tier == "pass":
            why = f"No edge: {side} {line:g}, {num}"
        elif tier == "lean":
            why = f"Lean, not a pick: {side} {line:g}, {num}. The edge is there only if the model's disagreement is worth half its size; a pick must survive a quarter"
        else:
            why = f"{side} {line:g}: {num}"
            if role:
                why += "; backed by a role change (a regular at his position is out)"
            elif fade:
                why += "; after an outlier last game in his usual role"
            if uncertain:
                why += "; listed questionable: not a lock, voids if he sits"
            if new_role:
                sp = p.get("share_pred", np.nan)
                why += (f"; new role: {float(pct_last):.0%} of snaps last game vs {float(p.get('pct_prev', np.nan)):.0%} this season, "
                        f"projected at {float(sp):.0%} of the snaps with a wider range" if pd.notna(sp) else "; new role, projected with a wider range")
            elif fl["reduced_role"]:
                why += f"; reduced role: {float(pct_last):.0%} of snaps last game vs {float(p.get('pct_prev', np.nan)):.0%} this season"
            if fl["absence"] or fl["missed_game"]:
                why += f"; back from absence ({int(p.get('gap_weeks', 0))} weeks since his last game)"
            if fl["new_team"]:
                why += "; first game for a new team"
            if _flag(p.get("vacancy", False)) and pd.notna(pct_last) and float(p.get("snap_jump", 1.0) or 1.0) >= C.VACANCY["min_jump"]:
                why += f"; a regular at his position is out or gone and he played {float(pct_last):.0%} of the snaps: the share model holds him near that"
            if block:
                why += "; not lock-eligible: " + ", ".join(block)
            if not_a:
                why += f"; a sleeper on this side too, which would make it an A, shown as a {grade}: " + ("the lock checklist is not clear" if block else "this market cannot carry an A yet")
        if sleeper:
            why += f"; sleeper ({sleeper}, grade {s_grade}): the model's own number is {mu_model:.1f} against a line of {line:g}"
        # two measurements on trial (config.HOLES, tools/holes.py), named on the card and used by no rule
        lp_all = _log(p, "log_pct")
        if solo and lp_all and float(np.mean(lp_all)) < C.HOLES["part_time"]:
            why += f"; part-time: he has played {float(np.mean(lp_all)):.0%} of the snaps this season, and part-time players' solo Unders have run well (a measurement on trial, in no grade)"
        if book_share is not None and book_share >= C.HOLES["book_share"]:
            why += (f"; solo share: the book's solo line is {book_share:.0%} of its own combined line for him (he has made {own_share:.0%} of his tackles solo), and solo Unders on lines "
                    f"at {C.HOLES['book_share']:.0%} or more have won about two in three this season (a measurement on trial, in no grade)")
        lg_steps, lg_text = logic_steps(p, kind)
        mu_eng = implied_mean(po, phi_use, line)                       # the engine's win chance read back as a number of tackles
        mkt_mean = implied_mean(fair, phi_use, line)                   # the book's fair price read back the same way
        eng = dict(p_model=p_model_side, fair=fair_side, p=p_side, p_low=p_low, ev=ev, edge_low=edge_low, mkt_mean=mkt_mean)
        rows.append({**base, **ident, "proj": float(mu_eng), "proj_model": mu_model, "level": level, "misfit": bool(misfit), "share_gap": share_gap, "mkt_mean": float(mkt_mean),
                     "exp_opps": None if pd.isna(p.get("exp_opps", np.nan)) else float(p.get("exp_opps")),
                     "mkt_line": float(r.mkt_line), "books_n": int(r.books_n), "phi": phi_use, "model_over": po, "model_over_low": po_low, "model_over_own": po_model, "market_over": fair,
                     "ev": ev, "side": side, "far_from_line": bool(far_from_line),
                     "p_claim": float(p_side), "p_low": float(p_low), "p_model": float(p_model_side), "claim_ev": float(ev), "edge_low": float(edge_low),
                     "kelly_low": kelly_fraction(p_low, dec), "tier": tier, "segment": f"{side} {kind} {p.group}",
                     "pick": pick, "why": why, "signal_fade": bool(fade), "signal_role": role, "status": p.status,
                     "season_avg": float(p.season_avg), "last": None if pd.isna(p["last"]) else float(p["last"]),
                     "n_prev": int(p.n_prev), "consistency": consistency, "cons_hits": int(sum(hits)), "cons_n": len(hits),
                     "mkt_side": float(fair_side), "payout": None if dec is None else float(dec - 1),
                     "stake": kelly_stake(p_low, dec) if tier == "pick" else None,
                     "international": str(p.get("venue", "")) == "NEUTRAL", "depth": p.get("dc_status", ""), "uncertain": bool(uncertain),
                     "new_role": bool(new_role), "snap_jump": None if pd.isna(p.get("snap_jump", np.nan)) else float(p.get("snap_jump")),
                     "reduced_role": fl["reduced_role"], "absence": bool(fl["absence"] or fl["missed_game"]), "new_team": fl["new_team"],
                     "in_role_games": in_role_n, "lock_block": ", ".join(block), "lock_eligible": not block,
                     "vacancy": _flag(p.get("vacancy", False)), "share_pred": None if pd.isna(p.get("share_pred", np.nan)) else float(p.get("share_pred")),
                     "opp_qb_out": bool(_flag(p.get("opp_qb_out", False))), "opp_rb_out": bool(_flag(p.get("opp_rb_out", False))),
                     "rest": None if pd.isna(p.get("rest", np.nan)) else int(p.get("rest")),
                     "rundown": rundown(p, line, side, kind, mu_model, eng, pick, why, fl, new_role, in_role_n, log_raw),
                     "press_pg": None if pd.isna(p.get("press_pg", np.nan)) else float(p.get("press_pg")),
                     "fp_comb": None if pd.isna(p.get("fp_comb", np.nan)) else float(p.get("fp_comb")),
                     "fp_solo": None if pd.isna(p.get("fp_solo", np.nan)) else float(p.get("fp_solo")),
                     "fp_rel": None if ast or pd.isna(p.get("fp_rel_solo" if solo else "fp_rel_comb", np.nan)) else float(p.get("fp_rel_solo" if solo else "fp_rel_comb")),
                     "lock": lock, "grade": grade, "sleeper": sleeper, "sleeper_ev": s_ev,
                     "sleeper_grade": s_grade, "sleeper_p": s_p, "sleeper_note": s_note, "sleeper_med": s_med,
                     "logic": lg_text or None, "gone_regulars": (str(p.get("gone_regulars")) if str(p.get("gone_regulars") or "").strip() not in ("", "nan") else None), "logic_chips": [[lab, round(e, 3)] for lab, e, _ in lg_steps if e is not None and abs(e) >= 0.03] or None})
    out = pd.DataFrame(rows)
    # every column the log, the sizing and the site read exists even when no line on this board could be priced (a pull of
    # one-sided prices only, or of players the model does not carry): the replay of week 8 crashed on a missing column
    for c_, d_ in (("ev", np.nan), ("side", None), ("lock", np.nan), ("tier", None), ("grade", None), ("stake", np.nan), ("proj", np.nan), ("proj_model", np.nan),
                   ("level", 1.0), ("misfit", False), ("share_gap", np.nan), ("p_claim", np.nan), ("p_low", np.nan), ("p_model", np.nan), ("edge_low", np.nan), ("market_over", np.nan), ("model_over", np.nan), ("sleeper", ""),
                   ("lock_block", ""), ("payout", np.nan), ("segment", None), ("team", None), ("opp", None), ("group", None), ("phi", np.nan), ("exp_opps", np.nan)):
        if c_ not in out.columns:
            out[c_] = d_
    out = out.sort_values("ev", ascending=False, na_position="last")
    # line shopping: mark the best book for each player / market / side / line
    out["best_price"] = ~out.duplicated(["player", "market", "side", "line"]) & out.ev.notna()
    out = out.sort_values(["lock", "ev"], ascending=[False, False], na_position="last")
    return out


# ---------------------------------------------------------------- second model: gradient-boosted corrector
GBM_FEATURES = ["log_mu", "n_prev", "snap", "pct_prev", "vol", "spread", "tgt", "miss", "demoted", "promoted", "starter", "q", "limited",
                "rest", "week", "last", "avg", "ps_avg", "crew", "grp", "is_home", "exp_runs", "exp_comps", "run_tk_rate", "pass_tk_rate", "jump", "gap", "new_team",
                "rate_clean", "share_pred", "tsnaps", "blowout_last", "vacancy", "allowed_rel", "dome", "role"]


def gbm_features(F, mu):
    """The feature frame for the corrector: the factor model's projection plus the raw signals behind it."""
    n = F.n_prev.astype(float).clip(lower=1)
    col = lambda c, d=np.nan: F[c] if c in F else pd.Series(d, index=F.index)
    status = col("status", "").fillna("").astype(str).str.lower(); practice = col("practice", "").fillna("").astype(str).str.lower()
    X = pd.DataFrame({
        "log_mu": np.log(pd.Series(np.asarray(mu, dtype=float), index=F.index).clip(lower=0.05)),
        "n_prev": F.n_prev.astype(float),
        "snap": (col("pct_last3") / col("pct_prev").clip(lower=0.05)).fillna(1.0).clip(0.3, 3.0),
        "jump": snap_jump(F).clip(0.3, 5.0),
        "gap": pd.to_numeric(col("gap_weeks"), errors="coerce").fillna(1).clip(1, 8),
        "new_team": col("team_changed", False).map(_flag).astype(float),
        "rate_clean": persnap_rate(F).fillna(0.08), "share_pred": share_pred(F).fillna(col("pct_prev").fillna(0.3)),
        "tsnaps": pd.to_numeric(col("tsnaps_exp"), errors="coerce").fillna(65.0),
        "blowout_last": (pd.to_numeric(col("last_margin"), errors="coerce").fillna(0) >= C.SHARE_MODEL["blowout_margin"]).astype(float),
        "vacancy": col("vacancy", False).map(_flag).astype(float), "allowed_rel": pd.to_numeric(col("allowed_rel"), errors="coerce").fillna(1.0),
        "role": col("role_signal", False).map(_flag).astype(float),      # next man up: a backup whose regular is out (2026-11-09: the bias on these rows fell from +0.40 to +0.29 at a weight of 0.8)
        "dome": col("roof", "").fillna("").astype(str).str.lower().isin(["dome", "closed"]).astype(float),
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
