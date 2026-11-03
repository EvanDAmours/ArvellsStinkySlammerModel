"""Scoping scan: for every count stat the same data carries, how much a snaps-and-matchup projection beats a
book-style season average walk-forward, and how often (and how well) it disagrees with that average by an A-size
margin. Tackles are the reference row; everything is measured the same way."""
import sys, math, re, numpy as np, pandas as pd
from scipy.stats import nbinom, poisson, norm
S = "/tmp/claude-0/-home-user-ArvellsStinkySlammerModel/9774aa0d-3733-5c2c-b44f-73ecd122b6e0/scratchpad/scope"
D = pd.read_parquet(f"{S}/player_week.parquet"); D = D[D.season_type == "REG"].copy()
SN = pd.read_parquet(f"{S}/snaps.parquet"); SN = SN[SN.game_type == "REG"].copy()
def nk(s): return re.sub(r"[^a-z]", "", str(s).lower().replace(" jr", "").replace(" sr", "").replace(" iii", "").replace(" ii", "").replace(" iv", ""))
D["nk"] = D.player_display_name.map(nk); SN["nk"] = SN.player.map(nk)
D["comb"] = D.def_tackles_solo.fillna(0) + D.def_tackle_assists.fillna(0)
D["kick_pts"] = 3 * D.fg_made.fillna(0) + D.pat_made.fillna(0)
SN = SN.rename(columns={"opponent": "opp"})
tsn = SN.groupby(["season", "week", "team"]).agg(t_off=("offense_snaps", "max"), t_def=("defense_snaps", "max")).reset_index()
D = D.merge(SN[["season", "week", "team", "nk", "offense_snaps", "defense_snaps"]].drop_duplicates(["season", "week", "team", "nk"]), on=["season", "week", "team", "nk"], how="left")
D = D.merge(tsn, on=["season", "week", "team"], how="left")

STATS = [  # stat, side (off/def/kick), population rule: prior season-to-date mean at least X, position groups
    ("comb", "def", 3.0, None), ("def_tackles_solo", "def", 2.0, None), ("def_tackle_assists", "def", 1.0, None),
    ("def_sacks", "def", 0.3, None), ("def_qb_hits", "def", 0.7, None), ("def_tackles_for_loss", "def", 0.4, None), ("def_pass_defended", "def", 0.5, None),
    ("def_interceptions", "def", 0.15, None),
    ("receptions", "off", 2.5, None), ("targets", "off", 3.5, None), ("receiving_yards", "off", 30.0, None),
    ("carries", "off", 7.0, None), ("rushing_yards", "off", 30.0, None),
    ("completions", "off", 12.0, ["QB"]), ("attempts", "off", 20.0, ["QB"]), ("passing_yards", "off", 150.0, ["QB"]), ("passing_tds", "off", 0.8, ["QB"]),
    ("fg_made", "kick", 0.8, ["K"]), ("kick_pts", "kick", 4.0, ["K"]),
]
CONT = {"receiving_yards", "rushing_yards", "passing_yards"}
rows = []
for stat, side, floor, poss in STATS:
    X = D.copy()
    if poss: X = X[X.position.isin(poss)]
    snapcol = "offense_snaps" if side == "off" else "defense_snaps"; tcol = "t_off" if side == "off" else "t_def"
    X[stat] = X[stat].fillna(0.0)
    X = X.sort_values(["season", "nk", "team", "week"])
    g = X.groupby(["season", "nk"])
    X["n_prev"] = g.cumcount()
    X["mean_prev"] = g[stat].transform(lambda s: s.shift().expanding().mean())
    if side != "kick":
        X["snap_prev"] = g[snapcol].transform(lambda s: s.shift().expanding().mean())
        X["share_last3"] = g.apply(lambda d: (d[snapcol] / d[tcol]).shift().rolling(3, min_periods=1).mean(), include_groups=False).reset_index(level=[0, 1], drop=True)
        X["rate_prev"] = g.apply(lambda d: (d[stat].shift().expanding().sum() / d[snapcol].shift().expanding().sum()), include_groups=False).reset_index(level=[0, 1], drop=True)
        tg = X.drop_duplicates(["season", "week", "team"]).sort_values(["season", "team", "week"]).groupby(["season", "team"])
        tsnap = tg[tcol].transform(lambda s: s.shift().expanding().mean()); X = X.merge(pd.DataFrame({"season": X.drop_duplicates(["season", "week", "team"]).sort_values(["season", "team", "week"]).season.values, "week": X.drop_duplicates(["season", "week", "team"]).sort_values(["season", "team", "week"]).week.values, "team": X.drop_duplicates(["season", "week", "team"]).sort_values(["season", "team", "week"]).team.values, "tsnap_prev": tsnap.values}), on=["season", "week", "team"], how="left")
    pop = X[(X.n_prev >= 3) & (X.mean_prev >= floor)].copy()
    if side != "kick":
        pop = pop[pop.snap_prev.fillna(0) > 0]
    # opponent factor: what the opponent allowed per game of this stat to this population, season to date, shrunk
    allowed = pop.groupby(["season", "week", "opponent_team"])[stat].sum().reset_index().rename(columns={"opponent_team": "opp", stat: "allowed"})
    allowed = allowed.sort_values(["season", "opp", "week"]); ag = allowed.groupby(["season", "opp"])
    allowed["allowed_prev"] = ag.allowed.transform(lambda s: s.shift().expanding().mean()); allowed["n_opp"] = ag.cumcount()
    lg = allowed.groupby(["season", "week"]).allowed.transform("mean")
    allowed["lg_prev"] = allowed.sort_values(["season", "week"]).groupby("season").allowed.transform(lambda s: s.shift().expanding().mean())
    allowed["opp_f"] = ((allowed.allowed_prev / allowed.lg_prev).fillna(1.0) * allowed.n_opp + 6 * 1.0) / (allowed.n_opp + 6)
    pop = pop.merge(allowed[["season", "week", "opp", "opp_f"]].rename(columns={"opp": "opponent_team"}), on=["season", "week", "opponent_team"], how="left")
    pop["opp_f"] = pop.opp_f.fillna(1.0).clip(0.7, 1.3)
    # shrink the season mean toward the population mean of prior games (m = 4 games)
    prior = pop.mean_prev.mean()
    pop["naive"] = (pop.mean_prev * pop.n_prev + prior * 4) / (pop.n_prev + 4)
    if side != "kick":
        pop["exp_snaps"] = (pop.share_last3.clip(0, 1) * pop.tsnap_prev).fillna(pop.snap_prev)
        pop["model"] = (pop.rate_prev * pop.n_prev * pop.snap_prev + prior / max(pop.snap_prev.mean(), 1) * 4 * pop.snap_prev) / ((pop.n_prev + 4) * pop.snap_prev) * pop.exp_snaps
        pop["model"] = pop.model.fillna(pop.naive)
    else:
        pop["model"] = pop.naive
    pop["model_opp"] = pop.model * pop.opp_f
    y = pop[stat].astype(float)
    def mae(p): return float((y - p).abs().mean())
    m_naive, m_model, m_opp = mae(pop.naive), mae(pop.model), mae(pop.model_opp)
    resid = y - pop.model_opp
    mu = float(y.mean()); phi = float(resid.var() / max(mu, 1e-6)) if stat not in CONT else float("nan")
    sd = float(resid.std())
    # disagreement with the naive line: the naive fair line (half-point nearest naive mean) and the model's chance of clearing it
    L = np.floor(pop.naive) + 0.5
    if stat in CONT:
        p_over = 1 - norm.cdf((L - pop.model_opp) / sd)
    else:
        m = pop.model_opp.clip(0.05, None)
        if phi > 1.05:
            r = m / (phi - 1); p_nb = 1 / phi
            p_over = 1 - nbinom.cdf(np.floor(L), r, p_nb)
        else:
            p_over = 1 - poisson.cdf(np.floor(L), m)
    p_over = pd.Series(np.asarray(p_over), index=pop.index)
    edge = (p_over - 0.5).abs()
    big = edge >= 0.10
    side_over = p_over > 0.5
    won = np.where(side_over, y > L, y < L); push = y == L
    hit_big = float(won[big & ~push].mean()) if (big & ~push).sum() else float("nan")
    hit_all = float(won[~push].mean()) if (~push).sum() else float("nan")
    rows.append(dict(stat=stat, games=len(pop), mean=round(mu, 2), naive_mae=round(m_naive, 3), model_mae=round(m_model, 3), with_opp_mae=round(m_opp, 3),
                     gain=f"{(m_naive - m_opp) / m_naive:+.1%}", phi=None if math.isnan(phi) else round(phi, 2), big_edge_share=f"{big.mean():.0%}", big_edge_hit=None if math.isnan(hit_big) else f"{hit_big:.1%}", n_big=int((big & ~push).sum()), all_hit=f"{hit_all:.1%}"))
    print(rows[-1], flush=True)
R = pd.DataFrame(rows); R.to_csv(f"{S}/scope_results.csv", index=False)
print(R.to_string(index=False))
