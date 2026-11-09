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
            for c in ["comb", "solo_t", "solo", "ast", "with_ast"]:
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


def outlier_damp_factor(F):
    """After a game far above or below his base, in a settled role, the season average still leans toward that game."""
    c = C.OUTLIER_DAMP
    last = pd.to_numeric(_col_or(F, "last", np.nan), errors="coerce")
    base = _base_for_outliers(F)
    settled = snap_jump(F).between(0.8, 1.25)
    hi = (last - base >= C.FADE_GAP) & settled; lo = (base - last >= C.FADE_GAP) & settled
    return pd.Series(np.where(hi.fillna(False), c["after_high"], np.where(lo.fillna(False), c["after_low"], 1.0)), index=F.index)


def _base_for_outliers(F):
    """The shrunk per-game base, recomputed cheaply (same formula as project_frame's base)."""
    k = F.group.map(C.SHRINK_GAMES_BY_GROUP).fillna(C.SHRINK_GAMES)
    prior = np.where(F.ps_games.fillna(0) >= 4, F.ps_avg, F.group.map(C.POS_PRIOR).fillna(4.0))
    n = F.n_prev.astype(float)
    return pd.Series(np.where(n + k > 0, (F.comb_prev + k * prior) / np.maximum(n + k, 1e-9), prior), index=F.index)


def rest_factor(F):
    r = C.REST
    return pd.Series(np.where(F.get("rest", pd.Series(7, index=F.index)).fillna(7) >= r["bye_days"], r["bye"], 1.0), index=F.index)


def project_frame(F, k=None, use_tilt=True, use_crew=True, use_role=True, use_snap=True, use_volume=True, use_depth=True, use_pfr=True, use_mix=True, use_rest=True, use_injury=True, use_new_role=True, use_role_shift=True,
                  use_persnap=True, use_vacancy=True, use_dome=True, use_solo_drift=True, use_outlier_damp=True, parts=None, pfr_typ=None):
    """(base, mu, mu_solo). `parts`, when a dict, receives every piece of the build per row (the base, the per-snap view,
    each game factor as a multiplier, the solo share) so a card can show how the number was made; the numbers are the same."""
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
        xf["damp"] = outlier_damp_factor(F).values
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
    solo_share = (F.solo_prev + m_s * F.group.map(C.POS_SOLO_SHARE).fillna(0.6)) / (F.comb_prev + m_s)
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
        solo_prev=("solo_adj", "sum"), pct_prev=("def_pct", "mean"), **sums).reset_index()
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
    if gbm is not None:
        g = gbm(gbm_features(F, mu))
        blended = pd.Series(blend_gbm(mu, g), index=F.index)
        ratio = (blended / mu.clip(lower=1e-6)).clip(0.5, 2.0)
        F = F.assign(proj_factor=mu.values, proj_gbm=np.asarray(g))
        mu, mu_solo = blended, mu_solo * ratio
    F = F.assign(base=base.values, proj=mu.values, proj_solo=mu_solo.values)
    # how the number was built, piece by piece, for the card (logic_steps): every factor as the multiplier it applied
    for k_, v in parts.items():
        F["lf_" + k_] = v
    F["lf_scale"] = float(scale) if np.isscalar(scale) else np.asarray(scale, dtype=float)
    F["lf_scale_solo"] = by_grp.fillna(scale_solo).values
    F["lf_gbm"] = (mu.values / np.clip(mu_raw.values * (float(scale) if np.isscalar(scale) else 1.0), 1e-6, None)) if gbm is not None else 1.0
    F["phi"] = F.group.map(phi_by_group).fillna(1.0)
    F["share_pred"] = share_pred(F).values
    F["rate_clean"] = persnap_rate(F).values
    F["vacancy_rule"] = vacancy_rule(F).values
    # a lineman's profile for the card (PFR pressures per game, prior games): no model effect (research round 5 rejected it)
    F["press_pg"] = (pd.to_numeric(_col_or(F, "press_prev", np.nan), errors="coerce") / F.n_prev.astype(float).clip(lower=1)).where(F.group == "DL").values
    low = F.share_pred.fillna(_col_or(F, "pct_prev", 1.0)).fillna(1.0) < C.PHI_SHARE_SPLIT
    low_phi = F.group.map({g: phi_by_group.get(f"{g}:low") for g in F.group.unique()})
    F.loc[low & low_phi.notna(), "phi"] = low_phi[low & low_phi.notna()]
    # solo tackles are less spread than combined ones (var/mean 1.05-1.27 vs 1.18-1.49): their own dispersion
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
    F.loc[F.new_role, "phi"] = F.phi + C.NEW_ROLE["phi_bump"]     # his count is far more spread than a settled player's
    F["fair_line"] = [fair_line(m, p) for m, p in zip(F.proj, F.phi)]
    F["fair_line_solo"] = [fair_line(m, p) for m, p in zip(F.proj_solo, F.phi_solo)]
    # assists: the combined projection less the solo one; their own dispersion from the backtest when it has one
    F["proj_ast"] = (F.proj - F.proj_solo).clip(lower=0.05)
    F["phi_ast"] = F.group.map({g: phi_by_group.get(f"{g}|ast") for g in F.group.unique()}) if isinstance(phi_by_group, dict) else np.nan
    F["phi_ast"] = F.phi_ast.fillna(F.phi)
    F.loc[F.venue == "NEUTRAL", "phi_ast"] = F.phi_ast + 0.15
    # a new role spreads his solo and assist counts too (new-role rows: solo var/mean 1.44 against 1.18 used)
    F.loc[F.new_role, "phi_solo"] = F.phi_solo + C.NEW_ROLE.get("phi_bump_solo", 0.25)
    F.loc[F.new_role & F.phi_ast.notna(), "phi_ast"] = F.phi_ast + C.NEW_ROLE.get("phi_bump_solo", 0.25)
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
    """A pick's claimed chance: shrunk toward even (never toward the book), then corrected by how claims like it have
    resolved (segment calibration, our own graded picks)."""
    return float(np.clip(0.5 + C.CLAIM_SHRINK * (float(p_side) - 0.5) + float(adj), 0.05, 0.95))


def segment_adjust(segments, side, kind, group):
    """Correction to a pick's claimed chance from the graded record of picks like it: finest segment with enough
    picks (side x market x position, then side x market, then side). `kind` is 'solo', 'assists' or 'combined'
    (True/False still read as solo/combined). Returns (adjustment, segment name)."""
    if not segments:
        return 0.0, ""
    c = C.SEGMENT_CAL
    mk = kind if isinstance(kind, str) else ("solo" if kind else "combined")
    for key in (f"{side} {mk} {group}", f"{side} {mk}", f"{side}"):
        seg = segments.get(key)
        if seg and seg.get("n", 0) >= c["min_n"]:
            n = float(seg.get("n_eff", seg["n"]))      # recency-weighted count when the calibration carries one
            w = n / (n + c["k"])
            return float(np.clip(w * (seg["hit"] - seg["claimed"]), -c["cap"], c["cap"])), key
    return 0.0, ""


def lock_score(ev, p_side, consistency, n_games, signal, adj=0.0):
    """0-100 confidence in a pick from the model's own evidence only: expected return at the price, the model's
    probability for the side, how often the player cleared the line this season, games of data, and whether a
    role-change or outlier-fade signal backs the pick. Weights in config.LOCK_WEIGHTS; tested on the Track record tab."""
    w = C.LOCK_WEIGHTS
    ev_part = float(np.clip(ev / C.LOCK_EV_FULL, 0, 1))
    lo, hi = C.LOCK_EV_FADE
    if ev > lo:                                   # too good to be true: the biggest disagreements with the market are mostly model error
        ev_part = float(np.clip((hi - ev) / (hi - lo), 0, 1))
    model_part = float(np.clip((claimed_prob(p_side, adj) - 0.5) / (C.LOCK_MODEL_FULL - 0.5), 0, 1))
    cons_part = 0.5 if consistency is None or np.isnan(consistency) else float(consistency)
    n_part = float(np.clip(n_games / 6.0, 0, 1))
    score = 100 * (w["ev"] * ev_part + w["model"] * model_part + w["consistency"] * cons_part + w["sample"] * n_part + w["signal"] * (1.0 if signal else 0.0))
    return float(np.clip(score, 0, 100))


def grade_of(score):
    return "A" if score >= C.GRADE_BARS["A"] else "B" if score >= C.GRADE_BARS["B"] else "C"


def _num(v, d=np.nan):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return d
    return d if np.isnan(v) else v


def rundown(p, line, side, kind, mu_model, mu, p_side, claim, ev, pick, why, fl, new_role, in_role_n, log_raw):
    """A templated read-up of one line from the numbers the pricer used: who he is, his recent games, the model's
    read, what the book's line implies about his snaps, what decides it, and the nudges. Every sentence is a
    number restated; nothing here is a view the data does not hold. `kind`: 'solo', 'assists' or 'combined'."""
    kind = kind if isinstance(kind, str) else ("solo" if kind else "combined")
    solo = kind == "solo"; ast = kind == "assists"
    stat = {"solo": "solo tackles", "assists": "assists"}.get(kind, "tackles + assists")
    n = int(_num(p.get("n_prev"), 0)); grp = str(p.get("group", "")); team = str(p.get("team", "")); opp = str(p.get("opp_team", ""))
    avg = (_num(p.get("solo_prev")) if solo else (_num(p.get("comb_prev_raw")) - _num(p.get("solo_prev"))) if ast else _num(p.get("comb_prev_raw"))) / max(n, 1) if n else np.nan
    share = _num(p.get("pct_prev")); last_sh = _num(p.get("pct_last")); exp_sh = _num(p.get("share_pred")); rate = _num(p.get("rate_clean")); tsn = _num(p.get("tsnaps_exp"))
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
    # the model's read
    out.append(f"The model's own number is {mu_model:.1f}; priced from {mu:.1f} after blending with the line. {side} {line:g}: model {p_side:.0%}, claimed {claim:.0%} after shrinking, {ev:+.0%} expected return at this price.")
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
    # nudges
    nud = []
    st = str(p.get("status", "")).lower()
    if st == "questionable":
        nud.append("listed questionable (priced 8% down; the bet voids if he sits)")
    gone = str(p.get("gone_regulars") or "").strip()
    if gone and gone.lower() != "nan":
        nud.append(f"gone at his position: {gone}")
    elif _flag(p.get("vacancy_rule", False)) or _flag(p.get("vacancy", False)):
        nud.append("a regular at his position is out or gone, so his share is read from his last game")
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
        nud.append(f"{dc} on the latest depth chart ({'+2' if dc == 'promoted' else '-10'}% in the number)")
    crew = _num(p.get("crew_solo") if solo else p.get("crew_comb"), 1.0)
    if abs(crew - 1) >= 0.02:
        nud.append(f"this stadium's stat crew credits {stat} {abs(crew - 1):.0%} {'high' if crew > 1 else 'low'}")
    roof = str(p.get("roof", "")).lower()
    if grp == "CB" and roof in ("dome", "closed"):
        nud.append("indoors: corners run 5% higher")
    rest = _num(p.get("rest"))
    if not np.isnan(rest) and rest >= 10:
        nud.append("off a bye (defences run 4% under their average)")
    fp = _num(p.get("fp_rel_solo") if solo else p.get("fp_rel_comb"))
    if not np.isnan(fp) and abs(fp) >= 0.08:
        nud.append(f"the outside expert consensus sits {fp:+.0%} from its usual relation to this model for him")
    if nud:
        out.append("Also: " + "; ".join(nud) + ".")
    out.append(("Pick: " if pick in ("Over", "Under") else "Pass: ") + why + ".")
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


def kelly_stake(claim, dec):
    """Units to stake on a pick (config.STAKE): a fraction of the Kelly fraction of the bankroll, from the claimed
    chance and the decimal price; None when there is no edge or no price. The per-game cap is applied later
    (grade.cap_stakes), once every pick on the game is known."""
    c = C.STAKE
    if dec is None or pd.isna(dec) or dec <= 1 or claim is None or pd.isna(claim):
        return None
    b = float(dec) - 1
    f = (float(claim) * b - (1 - float(claim))) / b
    if f <= 0:
        return None
    return float(np.clip(c["kelly_fraction"] * f * c["bankroll"], c["min"], c["max"]))


def blend_mean(mu_model, mkt_line, kind, blend=None):
    """The pricing mean: the model's number and the consensus line, each level-corrected, weighted by the market's
    estimated blend (pipeline/blend.py) or the default line weight. NaN when the model has no number (never 0.05)."""
    if mu_model is None or not np.isfinite(float(mu_model)):
        return float("nan")
    b = (blend or {}).get(kind) if blend else None
    if b:
        w, bm, bl = float(b.get("w", C.LINE_WEIGHT)), float(b.get("bias_model", 0.0)), float(b.get("bias_line", 0.0))
    else:
        w, bm, bl = C.LINE_WEIGHT, 0.0, 0.0
    return max(0.05, (1 - w) * (float(mu_model) + bm) + w * (float(mkt_line) + bl))


LOGIC_LABELS = {   # factor -> (short label for the card, what it means in football terms)
    "snap": ("Snap trend", "his snap share over his last three games against his season share"),
    "role": ("Next man up", "a regular at his position is out and he is the backup who steps in"),
    "new_role": ("New role", "a part-timer who just played a starter's snaps"),
    "share_shift": ("Role shift", "his last game's role against his season role"),
    "tilt": ("Spread", "point spread: an underdog's defence faces more plays"),
    "crew": ("Stat crew", "this stadium's stat crew credits tackles high or low"),
    "volume": ("Opponent volume", "tackle chances expected this game (opponent carries + completions + sacks) against what he has faced"),
    "depth": ("Depth chart", "promoted or demoted on the latest depth chart"),
    "pfr": ("Coverage", "how often he is targeted in coverage and how often he misses tackles"),
    "mix": ("Run/pass mix", "this opponent's run/pass mix through his own run and pass tackle rates"),
    "rest": ("Bye", "defences off a bye run under their average"),
    "injury": ("Injury report", "listed questionable or limited in practice"),
    "availability": ("Absence", "back from a missed game or new to the team"),
    "dome": ("Indoors", "corners run higher indoors"),
    "damp": ("Outlier damp", "one big game in his log counts for less"),
    "scale": ("Level", "the backtest's level calibration"),
    "gbm": ("Second model", "the boosted model trained on every defender-game since 2023"),
}


def logic_steps(p, kind="combined", min_effect=0.0):
    """How the model built a player's number, from the pieces finalize_projections stored (lf_*): his base rate, the
    per-snap view, every game factor as a percentage, the second model, the solo share. Returns (steps, text): steps
    are (label, effect as a fraction or None, detail) in order; text is one paragraph. Empty when the row has no pieces."""
    g = lambda c, d=np.nan: _num(p.get(c), d) if hasattr(p, "get") else d
    if np.isnan(g("lf_base")):
        return [], ""
    kind = kind if isinstance(kind, str) else ("solo" if kind else "combined")
    n = int(g("n_prev", 0)); avg = g("comb_prev_raw", np.nan) / max(n, 1) if n else np.nan
    grp = str(p.get("group", "")); steps = []
    prior = f"last season's {g('ps_avg'):.1f}" if g("ps_games", 0) >= 4 and not np.isnan(g("ps_avg")) else f"the {grp} average"
    rate_lab = "Season rate" if kind == "combined" else "Season rate (tackles + assists; the solo share comes last)"
    steps.append((rate_lab, None, f"{avg:.1f} a game over {n} games; adjusted for the stat crews of his games and weighted with {prior}: {g('lf_base'):.1f}" if n else f"no games yet: {prior}"))
    ps = g("lf_persnap")
    if not np.isnan(ps):
        steps.append(("Per-snap view", None, f"{g('rate_clean'):.3f} tackles a snap x {g('share_pred'):.0%} of {g('tsnaps_exp'):.0f} expected defensive snaps = {ps:.1f}; blended 60/40 with the season rate"))
    if _flag(p.get("lf_vacancy_rule", False)):
        steps.append(("Vacancy rule", None, "a regular at his position is out and his snaps jumped: moved halfway to his rate at last game's share"))
    pg, core_pre, core = g("lf_pg"), g("lf_core_pre"), g("lf_core")
    w_ps = 0.0 if np.isnan(ps) else C.PERSNAP["weight"]
    for k_ in ("snap", "role", "new_role", "share_shift", "tilt", "crew", "volume", "depth", "pfr", "mix", "rest", "injury", "availability", "dome", "damp", "scale", "gbm"):
        src = {"crew": "crew_solo", "scale": "scale_solo"}.get(k_, k_) if kind == "solo" else k_
        v = g("lf_" + src, 1.0)
        if k_ in ("snap", "role", "new_role", "share_shift") and not np.isnan(v) and v > 0 and not any(np.isnan(x) for x in (pg, core_pre, core)):
            # these move only the per-game part (60% of the base when the per-snap view is in): their effect on the number
            pre_wo = (1 - w_ps) * pg / v + w_ps * (0 if np.isnan(ps) else ps)
            wv = C.VACANCY["weight"]       # the vacancy rule mixes in his last-game share's rate, which these do not touch
            core_wo = (core - (1 - wv) * core_pre) + (1 - wv) * pre_wo if _flag(p.get("lf_vacancy_rule", False)) else pre_wo
            v = core / core_wo if core_wo > 0 else v
        if np.isnan(v) or abs(v - 1) < max(min_effect, 0.005):
            continue
        lab, what = LOGIC_LABELS[k_]
        detail = what
        if k_ == "volume" and not np.isnan(g("exp_opps")) and not np.isnan(g("opps_prev_mean")):
            detail = f"{g('exp_opps'):.0f} tackle chances expected against the {g('opps_prev_mean'):.0f} he has faced a game"
        elif k_ == "snap" and not np.isnan(g("pct_last3")):
            detail = f"{g('pct_last3'):.0%} of the snaps over his last three games against {g('pct_prev'):.0%} this season"
        elif k_ == "tilt" and not np.isnan(g("spread_dog")):
            sd = g("spread_dog"); detail = f"his team is a {abs(sd):g}-point {'underdog' if sd > 0 else 'favourite'}: {'more' if sd > 0 else 'fewer'} plays for his defence"
        elif k_ == "depth":
            detail = f"{p.get('dc_status')} on the latest depth chart"
        elif k_ == "injury":
            detail = f"listed {str(p.get('status') or p.get('practice') or 'on the report').lower()}"
        steps.append((lab, float(v - 1), detail))
    if kind == "solo":
        steps.append(("Solo share", None, f"{g('lf_solo_share'):.0%} of his tackles solo (his own, weighted with his position's)"))
    total = g("proj_solo") if kind == "solo" else g("proj") - g("proj_solo") if kind == "assists" else g("proj")
    unit = {"solo": "solo tackles", "assists": "assists"}.get(kind, "tackles + assists")
    bits = [f"{lab} {e:+.0%}" if e is not None else f"{lab}: {d}" for lab, e, d in steps]
    text = f"How the model built {total:.1f} {unit}: " + "; ".join(bits) + "."
    if kind == "assists":
        text += " Assists are the combined number less the solo one."
    gone = str(p.get("gone_regulars") or "").strip() if hasattr(p, "get") else ""
    if gone and gone.lower() != "nan":
        text += f" Gone at his position (the vacancy and next-man-up effects above already price it): {gone}."
    if _flag(p.get("team_changed", False)) if hasattr(p, "get") else False:
        text += f" He was traded or moved: first games for {p.get('team')}, priced down and never a lock until he settles."
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


def sleeper_note(side, kind, mu, line, phi, p_model, log_raw, exp_opps, grade, why):
    """One short paragraph for the site: the model's number against the line, its own chance of the side from its count
    distribution, the player's season against the line, the game's volume and the grade with its reason."""
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
    return " ".join(parts)


def price_lines(lines, P, segments=None, blend=None):
    """Evaluate every posted line against the projection; return one row per line with EV, pick and confidence grade.
    blend: per-market line weights and level corrections (pipeline/blend.py), else the default line weight."""
    if lines is None or len(lines) == 0 or P is None or len(P) == 0:
        return pd.DataFrame()
    from pipeline.sources import norm_name
    L = lines.copy()
    L["name_key"] = L.player.map(norm_name)
    # consensus line across books, from rows that quote both sides: Bally Bet posts Over-only rows, sometimes far off
    # (2026-10-31: Jordyn Brooks 25.5 against DraftKings' 8.5 made a 17.0 "consensus" and a +62% Over pick)
    two = L.over_odds.notna() & L.under_odds.notna()
    med_two = L[two].groupby(["player", "market"]).line.median()
    med_all = L.groupby(["player", "market"]).line.median()
    L["mkt_line"] = [med_two.get((p_, m_), med_all.get((p_, m_))) for p_, m_ in zip(L.player, L.market)]
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
        mu = blend_mean(mu_model, r.mkt_line, kind, blend)
        if not np.isfinite(mu):
            rows.append({**base, "pick": "No projection", "why": "The model has no number for him this week"})
            continue
        po_model = p_over(mu, phi_use, float(r.line))
        # informational only, never part of the grade: the model and the consensus line far apart means one of them
        # knows something; the card says so and the reader checks
        far_from_line = abs(float(mu_model) - float(r.mkt_line)) / max(1.0, float(r.mkt_line)) >= 0.25
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
        # half of each side's segment correction (how our claims for picks of this kind have resolved) moves the
        # probability that decides whether this line is a pick; the full correction reaches the claim and the score
        wv = C.SEGMENT_CAL.get("ev_weight", 0.0)
        adj_o = segment_adjust(segments, "Over", kind, p.group)[0] if wv else 0.0
        adj_u = segment_adjust(segments, "Under", kind, p.group)[0] if wv else 0.0
        po_o = float(np.clip(po + wv * adj_o, 0.02, 0.98)); pu_u = float(np.clip(1 - po + wv * adj_u, 0.02, 0.98))
        ev_o = po_o * (d_o - 1) - (1 - po_o) if d_o else -9
        ev_u = pu_u * (d_u - 1) - (1 - pu_u) if d_u else -9
        side, ev = ("Over", ev_o) if ev_o >= ev_u else ("Under", ev_u)
        fl = {k: _flag(p.get(k, False)) for k in ("new_role", "reduced_role", "absence", "missed_game", "new_team")}
        new_role = fl["new_role"]
        shifted = any(fl.values())
        log = _log(p, "log_solo" if solo else "log_ast" if ast else "log_comb")
        log_raw = list(log)
        # consistency counts in-role games only: games where he played at least 70% of the snap share he played last game
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
        hits = [(x > r.line) if side == "Over" else (x < r.line) for x in log]
        consistency = float(np.mean(hits)) if hits else float("nan")
        mkt_side = mkt if side == "Over" else 1 - mkt
        dec = d_o if side == "Over" else d_u
        gap = (p["last"] - p.base) if pd.notna(p["last"]) else 0.0
        # the outlier fade: Under after a big game, only when that game came in his usual role. (An Over after a low game
        # is not a signal: the backtest says a low game predicts lower, not a bounce.)
        fade = side == "Under" and gap >= C.FADE_GAP and not shifted
        role = bool(p.role_signal) and side == "Over"
        flagged = str(p.status).lower() in OUT_STATUSES
        uncertain = str(p.status).lower() == "questionable"
        thin = p.n_prev < C.MIN_GAMES_FOR_PICK and not role
        bar = C.SIGNAL_BAR if (fade or role) else (C.PICK_BAR_OVER if side == "Over" else C.PICK_BAR)
        p_side = po if side == "Over" else 1 - po
        seg_adj, seg_key = segment_adjust(segments, side, kind, p.group)
        claim = claimed_prob(p_side, seg_adj)
        low_claim = claim < C.PICK_MIN_CLAIM
        claim_ev = claim * dec - 1 if dec else float("nan")       # the return at our own claimed chance (config.PICK_MIN_CLAIM_EV)
        low_edge = not (claim_ev >= C.PICK_MIN_CLAIM_EV)
        pick = side if (ev >= bar and not flagged and not thin and not low_claim and not low_edge) else "Pass"
        # lock eligibility checklist (market-free): the model must be on ground where it is reliable
        settled = in_role_n >= C.LOCK_RULES["min_in_role_games"] or in_role_n >= int(p.n_prev)
        snaps_missing = pd.isna(pct_last) and int(p.n_prev) > 0      # he has games but no snap count for his last one: the role checks are blind
        block = [name for ok, name in ((new_role, "new role"), (fl["reduced_role"], "reduced role"), (fl["absence"] or fl["missed_game"], "back from absence"),
                                       (fl["new_team"], "new team"), (not settled, f"only {in_role_n} game{'s' if in_role_n != 1 else ''} in this role"),
                                       (uncertain, "questionable"), (snaps_missing, "snap counts missing for his last game"),
                                       (side == "Over" and not C.LOCK_RULES.get("overs_eligible", True), "Over side")) if ok]
        lock = lock_score(ev, p_side, consistency, in_role_n, fade or role, seg_adj)
        grade, capped, thin_edge = grade_of(lock), False, False
        if grade == "A" and not (claim_ev >= C.A_MIN_CLAIM_EV):     # an A must beat its price by 4% at the claimed chance (2026-11-09 post-mortem)
            grade, thin_edge = "B", True
        if grade == "A" and r.market not in C.A_GRADE_MARKETS:     # combined claims ran 9 points high over weeks 7-9: no A there until they earn it
            grade, capped = "B", True                               # (not a lock_block: that would also bar it from the combined-only parlays)
        # a sleeper: the model's own number, before the blend with the line, disagrees with the book by a margin that held in
        # every live week (config.SLEEPER); tracked on its own record whether or not the bars make it a pick
        sl, sleeper, s_grade, s_p, s_note, s_med = C.SLEEPER, "", None, None, None, None
        if not flagged and not thin:
            g_ = float(mu_model) - float(r.line)
            ok_o = d_o is not None and (sl["min_ev"] is None or ev_o >= sl["min_ev"])
            ok_u = d_u is not None and (sl["min_ev"] is None or ev_u >= sl["min_ev"])
            med = float(np.median(log_raw)) if log_raw else float("nan")
            if kind == "combined" and sl["comb_over"][0] <= g_ < sl["comb_over"][1] and ok_o:
                sleeper = "Over"
            elif solo and g_ <= sl["solo_under"] and ok_u and med == med and med >= float(r.line) + sl.get("solo_hist", -99):
                sleeper = "Under"
            if sleeper:
                po_m = p_over(float(mu_model), phi_use, float(r.line))
                s_p = float(po_m if sleeper == "Over" else 1 - po_m)
                s_med = med if med == med else None
                unsteady = [nm for ok, nm in ((new_role, "new role"), (fl["reduced_role"], "reduced role"), (fl["absence"] or fl["missed_game"], "back from absence"),
                                              (fl["new_team"], "new team"), (uncertain, "questionable"), (snaps_missing, "snap count missing"),
                                              (in_role_n < C.LOCK_RULES["min_in_role_games"], f"only {in_role_n} games in this role")) if ok]
                eo = p.get("exp_opps", np.nan)
                eo = float(eo) if pd.notna(eo) else None
                s_grade, s_why = sleeper_grade(sleeper, s_p, eo, unsteady)
                s_note = sleeper_note(sleeper, kind, float(mu_model), float(r.line), phi_use, s_p, log_raw, eo, s_grade, s_why)
        if flagged:
            why = f"His own status is {p.status or 'uncertain'}: wait for the final report"
        elif thin:
            why = f"Only {int(p.n_prev)} games of data"
        elif ev < bar:
            why = f"Best side returns {ev:+.0%}; needs {bar:.0%}"
        elif low_claim:
            why = f"{side} returns {ev:+.0%} but the claimed chance is only {claim:.0%}; a pick needs {C.PICK_MIN_CLAIM:.0%}"
        elif low_edge:
            why = f"{side} at {claim:.0%} claimed returns {claim_ev:+.0%} at this price; a pick needs {C.PICK_MIN_CLAIM_EV:.0%} at the claimed chance"
        else:
            why = f"{side} returns {ev:+.0%}" + (", backed by a role change" if role else ", fading an outlier last game" if fade else ", price gap only")
            if uncertain:
                why += "; listed questionable: priced 8% under his average, not a lock, voids if he sits"
            if new_role:
                sp = p.get("share_pred", np.nan)
                why += (f"; new role: {float(pct_last):.0%} of snaps last game vs {float(p.get('pct_prev', np.nan)):.0%} this season, "
                        f"projected at {float(sp):.0%} of the snaps with a wider range" if pd.notna(sp) else "; new role, projected with a wider range")
            elif fl["reduced_role"]:
                why += f"; reduced role: {float(pct_last):.0%} of snaps last game vs {float(p.get('pct_prev', np.nan)):.0%} this season, priced down"
            if fl["absence"] or fl["missed_game"]:
                why += f"; back from absence ({int(p.get('gap_weeks', 0))} weeks since his last game), priced down"
            if fl["new_team"]:
                why += "; first game for a new team, priced down"
            if _flag(p.get("vacancy_rule", False)):
                why += f"; a regular at his position is out or gone and he played {float(pct_last):.0%} of the snaps: projected at that share"
            if block:
                why += "; not lock-eligible: " + ", ".join(block)
        if thin_edge and pick != "Pass":
            why += f"; scores as an A, shown as a B: at its {claim:.0%} claimed chance it returns {claim_ev:+.0%}, an A needs {C.A_MIN_CLAIM_EV:.0%}"
        lg_steps, lg_text = logic_steps(p, kind)
        if capped and pick != "Pass":
            why += "; scores as an A, shown as a B: A grades and locks are solo tackles only (combined claims ran 9 points high in weeks 7-9)"
        if sleeper:
            why += f"; sleeper ({sleeper}, grade {s_grade}): the model's own number is {float(mu_model):.1f} against a line of {float(r.line):g}"
        rows.append({**base, "team": p.team, "opp": p.opp_team, "group": p.group, "jersey": None if pd.isna(p.get("jersey", np.nan)) else int(p.get("jersey")), "proj": float(mu), "proj_model": float(mu_model),
                     "player_id": None if pd.isna(p.get("player_id", np.nan)) else str(p.get("player_id")), "espn_id": None if pd.isna(p.get("espn_id", np.nan)) else str(p.get("espn_id")).split(".")[0],
                     "exp_opps": None if pd.isna(p.get("exp_opps", np.nan)) else float(p.get("exp_opps")),
                     "mkt_line": float(r.mkt_line), "phi": phi_use, "model_over": po, "market_over": mkt, "ev": ev, "side": side, "far_from_line": bool(far_from_line),
                     "p_claim": claim, "claim_ev": None if claim_ev != claim_ev else float(claim_ev), "segment": seg_key, "segment_adj": float(seg_adj),
                     "pick": pick, "why": why, "signal_fade": bool(fade), "signal_role": role, "status": p.status,
                     "season_avg": float(p.season_avg), "last": None if pd.isna(p["last"]) else float(p["last"]),
                     "n_prev": int(p.n_prev), "consistency": consistency, "cons_hits": int(sum(hits)), "cons_n": len(hits),
                     "mkt_side": float(mkt_side), "payout": None if dec is None else float(dec - 1),
                     "stake": kelly_stake(claim, dec) if pick in ("Over", "Under") else None,
                     "international": str(p.get("venue", "")) == "NEUTRAL", "depth": p.get("dc_status", ""), "uncertain": bool(uncertain),
                     "new_role": bool(new_role), "snap_jump": None if pd.isna(p.get("snap_jump", np.nan)) else float(p.get("snap_jump")),
                     "reduced_role": fl["reduced_role"], "absence": bool(fl["absence"] or fl["missed_game"]), "new_team": fl["new_team"],
                     "in_role_games": in_role_n, "lock_block": ", ".join(block), "lock_eligible": not block,
                     "vacancy": _flag(p.get("vacancy_rule", False)), "share_pred": None if pd.isna(p.get("share_pred", np.nan)) else float(p.get("share_pred")),
                     "opp_qb_out": bool(p.get("opp_qb_out", False)), "opp_rb_out": bool(p.get("opp_rb_out", False)),
                     "rest": None if pd.isna(p.get("rest", np.nan)) else int(p.get("rest")),
                     "rundown": rundown(p, float(r.line), side, kind, float(mu_model), float(mu), float(p_side), float(claim), float(ev), pick, why, fl, new_role, in_role_n, log_raw),
                     "press_pg": None if pd.isna(p.get("press_pg", np.nan)) else float(p.get("press_pg")),
                     "fp_comb": None if pd.isna(p.get("fp_comb", np.nan)) else float(p.get("fp_comb")),
                     "fp_solo": None if pd.isna(p.get("fp_solo", np.nan)) else float(p.get("fp_solo")),
                     "fp_rel": None if ast or pd.isna(p.get("fp_rel_solo" if solo else "fp_rel_comb", np.nan)) else float(p.get("fp_rel_solo" if solo else "fp_rel_comb")),
                     "lock": lock, "grade": grade, "sleeper": sleeper,
                     "sleeper_ev": (ev_o if sleeper == "Over" else ev_u) if sleeper else None,
                     "sleeper_grade": s_grade, "sleeper_p": s_p, "sleeper_note": s_note, "sleeper_med": s_med,
                     "logic": lg_text or None, "gone_regulars": (str(p.get("gone_regulars")) if str(p.get("gone_regulars") or "").strip() not in ("", "nan") else None), "logic_chips": [[lab, round(e, 3)] for lab, e, _ in lg_steps if e is not None and abs(e) >= 0.03] or None})
    out = pd.DataFrame(rows)
    if "ev" in out:
        out = out.sort_values("ev", ascending=False, na_position="last")
        # line shopping: mark the best book for each player / market / side / line
        out["best_price"] = ~out.duplicated(["player", "market", "side", "line"]) & out.ev.notna()
        out = out.sort_values(["lock", "ev"], ascending=[False, False], na_position="last")
    return out


# ---------------------------------------------------------------- second model: gradient-boosted corrector
GBM_FEATURES = ["log_mu", "n_prev", "snap", "pct_prev", "vol", "spread", "tgt", "miss", "demoted", "promoted", "starter", "q", "limited",
                "rest", "week", "last", "avg", "ps_avg", "crew", "grp", "is_home", "exp_runs", "exp_comps", "run_tk_rate", "pass_tk_rate", "jump", "gap", "new_team",
                "rate_clean", "share_pred", "tsnaps", "blowout_last", "vacancy", "allowed_rel", "dome"]


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
