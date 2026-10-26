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
    h = sched[base + ["home_team", "away_team"]].rename(columns={"home_team": "team", "away_team": "opp_team"}).assign(is_home=True)
    a = sched[base + ["home_team", "away_team"]].rename(columns={"away_team": "team", "home_team": "opp_team"}).assign(is_home=False)
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
    keep = ["season", "week", "team", "game_id", "venue", "spread_dog", "is_home", "opp_team", "gameday", "gametime", "final"]
    pw = pw.drop_duplicates(["player_id", "season", "week"], keep="first")
    H = pw.merge(tg[keep].drop_duplicates(["season", "week", "team"]), on=["season", "week", "team"], how="inner")
    H["ast_t"] = H.comb - H.solo_t
    # each game's stat crew, estimated only from games before it; then remove it so averages are crew-neutral
    H = attach_crews(H, H)
    H["comb_adj"] = H.comb / H.crew_comb
    H["solo_adj"] = H.solo_t / H.crew_solo
    return H.sort_values(["player_id", "season", "week"]).reset_index(drop=True)


def add_history_features(H):
    H = H.sort_values(["player_id", "season", "week"]).copy()
    g = H.groupby(["player_id", "season"], sort=False)
    H["n_prev"] = g.cumcount()
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
def project_frame(F, k=None, use_tilt=True, use_crew=True, use_role=True):
    k = C.SHRINK_GAMES if k is None else k
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
    solo_share = (F.solo_prev + 8 * F.group.map(C.POS_SOLO_SHARE).fillna(0.6)) / (F.comb_prev + 8)
    mu = base * tilt * crew_c * role
    mu_solo = base * tilt * solo_share * crew_s * role
    return pd.Series(base, index=F.index), pd.Series(mu, index=F.index), pd.Series(mu_solo, index=F.index)


def upcoming_rows(H, sched, injuries, season, week):
    """Feature rows for every active defender whose team plays in `week`."""
    tg = team_games(sched)
    games = tg[(tg.season == season) & (tg.week == week)]
    done = H[(H.season == season) & (H.week < week)]
    if done.empty:
        return pd.DataFrame()
    recent = done[done.week >= week - 4]
    active = recent.drop_duplicates("player_id")[["player_id"]]
    agg = done.groupby("player_id").agg(
        player=("player", "last"), name_key=("name_key", "last"), team=("team", "last"), group=("group", "last"),
        n_prev=("comb", "size"), comb_prev=("comb_adj", "sum"), comb_prev_raw=("comb", "sum"),
        solo_prev=("solo_adj", "sum"), pct_prev=("def_pct", "mean")).reset_index()
    lasts = done.sort_values("week").groupby("player_id").agg(last=("comb", "last"), pct_last=("def_pct", "last"))
    last2 = done.sort_values("week").groupby("player_id").comb.apply(lambda x: x.tail(2).mean() if len(x) >= 2 else np.nan).rename("last2")
    F = agg.merge(active, on="player_id").join(lasts, on="player_id").join(last2, on="player_id")
    ps = H[H.season == season - 1].groupby("player_id").agg(ps_games=("comb", "size"), ps_avg=("comb_adj", "mean"),
                                                            ps_avg_raw=("comb", "mean"))
    F = F.join(ps, on="player_id")
    F = F.merge(games[["team", "game_id", "venue", "spread_dog", "is_home", "opp_team", "gameday", "gametime", "final"]], on="team", how="inner")
    F["season"], F["week"] = season, week
    F = attach_crews(F, H)
    # injuries for this week: own status, and role signal when a regular at his position group is out
    inj = injuries[(injuries.season == season) & (injuries.week == week)] if len(injuries) else injuries
    status = {(r.team, r.name_key): r.status for r in inj.itertuples()} if len(inj) else {}
    F["status"] = [status.get((t, n), "") for t, n in zip(F.team, F.name_key)]
    out_keys = {(t, n) for (t, n), s in status.items() if str(s).lower() in OUT_STATUSES}
    regs = F[(F.pct_prev >= 0.75) & (F.n_prev >= 2)]
    vacated = {(r.team, r.group) for r in regs.itertuples() if (r.team, r.name_key) in out_keys}
    F["role_signal"] = [((t, g) in vacated) and not (p >= 0.75) and (t, n) not in out_keys
                        for t, g, p, n in zip(F.team, F.group, F.pct_prev.fillna(0), F.name_key)]
    return F


def finalize_projections(F, phi_by_group, k=None):
    if F.empty:
        return F
    base, mu, mu_solo = project_frame(F, k=k)
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


def lock_score(ev, mkt_side, consistency, n_games, fade):
    """0-100 confidence in a pick. Components are in config.LOCK_WEIGHTS; validated week by week on the Track record tab."""
    w = C.LOCK_WEIGHTS
    ev_part = float(np.clip(ev / C.LOCK_EV_FULL, 0, 1))
    mkt_part = float(np.clip((mkt_side - 0.35) / 0.30, 0, 1))        # 35% market chance -> 0, 65% -> 1
    cons_part = 0.5 if consistency is None or np.isnan(consistency) else float(consistency)
    n_part = float(np.clip(n_games / 6.0, 0, 1))
    score = 100 * (w["ev"] * ev_part + w["market"] * mkt_part + w["consistency"] * cons_part + w["sample"] * n_part)
    return float(np.clip(score + (C.LOCK_FADE_BONUS if fade else 0), 0, 100))


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
        flagged = str(p.status).lower() in OUT_STATUSES or str(p.status).lower() == "questionable"
        thin = p.n_prev < C.MIN_GAMES_FOR_PICK and not role
        bar = C.SIGNAL_BAR if (fade or role) else C.PICK_BAR
        pick = side if (ev >= bar and not flagged and not thin) else "Pass"
        lock = lock_score(ev, mkt_side, consistency, int(p.n_prev), fade)
        if flagged:
            why = f"His own status is {p.status or 'uncertain'}: wait for the final report"
        elif thin:
            why = f"Only {int(p.n_prev)} games of data"
        elif ev < bar:
            why = f"Best side returns {ev:+.0%}; needs {bar:.0%}"
        else:
            why = f"{side} returns {ev:+.0%}" + (", backed by a role change" if role else ", fading an outlier last game" if fade else ", price gap only")
        rows.append({**base, "team": p.team, "opp": p.opp_team, "group": p.group, "proj": float(mu), "proj_model": float(mu_model),
                     "mkt_line": float(r.mkt_line), "phi": float(p.phi), "model_over": po, "market_over": mkt, "ev": ev, "side": side,
                     "pick": pick, "why": why, "signal_fade": bool(fade), "signal_role": role, "status": p.status,
                     "season_avg": float(p.season_avg), "last": None if pd.isna(p["last"]) else float(p["last"]),
                     "n_prev": int(p.n_prev), "consistency": consistency, "cons_hits": int(sum(hits)), "cons_n": len(hits),
                     "mkt_side": float(mkt_side), "payout": None if dec is None else float(dec - 1),
                     "international": str(p.get("venue", "")) == "NEUTRAL",
                     "lock": lock, "grade": grade_of(lock)})
    out = pd.DataFrame(rows)
    if "ev" in out:
        out = out.sort_values("ev", ascending=False, na_position="last")
        # line shopping: mark the best book for each player / market / side / line
        out["best_price"] = ~out.duplicated(["player", "market", "side", "line"]) & out.ev.notna()
        out = out.sort_values(["lock", "ev"], ascending=[False, False], na_position="last")
    return out
