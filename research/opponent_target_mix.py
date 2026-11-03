"""Item 9: the opponent's completions by receiver position (RB, TE, WR) as a factor on each defender's pass tackles.
Walk-forward: a defender's tackle rate per completion of each kind from his prior games; the opponent's mix from
its prior games (shrunk to the league). Factor = expected pass tackles under the opponent's mix / under the league mix,
applied to the full model, judged on level-matched miss per season."""
import sys, pickle, numpy as np, pandas as pd
sys.path.insert(0, "/home/user/ArvellsStinkySlammerModel")
import config as C
from pipeline import model as M, backtest as B, sources as S
R_ = "/tmp/claude-0/-home-user-ArvellsStinkySlammerModel/9774aa0d-3733-5c2c-b44f-73ecd122b6e0/scratchpad/res"
H = pd.read_parquet(f"{R_}/H.parquet"); aux = pickle.load(open(f"{R_}/aux.pkl", "rb")); seasons = aux["seasons"]
import nflreadpy as nfl
COLS = ["season", "week", "season_type", "play_type", "defteam", "posteam", "complete_pass", "receiver_player_id",
        "solo_tackle_1_player_id", "solo_tackle_2_player_id", "assist_tackle_1_player_id", "assist_tackle_2_player_id", "assist_tackle_3_player_id", "assist_tackle_4_player_id",
        "tackle_with_assist_1_player_id", "tackle_with_assist_2_player_id"]
frames = []
for s in seasons:
    df = nfl.load_pbp(seasons=[s]); df = df.select([c for c in COLS if c in df.columns]).to_pandas(); frames.append(df); print("pbp", s, len(df), flush=True)
pbp = pd.concat(frames, ignore_index=True)
pbp = pbp[S._season_game(pbp.season_type) & (pbp.play_type == "pass") & (pd.to_numeric(pbp.complete_pass, errors="coerce").fillna(0) == 1)]
pl = nfl.load_players().to_pandas(); pos = dict(zip(pl.gsis_id.astype(str), pl.position.astype(str)))
grp = {"RB": "RB", "FB": "RB", "HB": "RB", "TE": "TE", "WR": "WR"}
pbp["rpos"] = pbp.receiver_player_id.astype(str).map(pos).map(grp).fillna("WR")
print("completions by receiver kind:", pbp.rpos.value_counts(normalize=True).round(3).to_dict(), flush=True)
# per defender-game: tackles on completions by receiver kind
tk = []
for c in COLS[8:]:
    tk.append(pbp[["season", "week", "defteam", "rpos", c]].dropna(subset=[c]).rename(columns={c: "player_id"}))
tk = pd.concat(tk, ignore_index=True)
D = tk.groupby(["season", "week", "player_id", "rpos"]).size().unstack(fill_value=0).reset_index()
for k in ("RB", "TE", "WR"):
    if k not in D.columns: D[k] = 0
D = D.rename(columns={"RB": "tk_RB", "TE": "tk_TE", "WR": "tk_WR"})
# per offence-game: completions by kind (what the opponent generates); per defence-game: faced
O = pbp.groupby(["season", "week", "posteam", "rpos"]).size().unstack(fill_value=0).reset_index().rename(columns={"posteam": "team", "RB": "gen_RB", "TE": "gen_TE", "WR": "gen_WR"})
F = pbp.groupby(["season", "week", "defteam", "rpos"]).size().unstack(fill_value=0).reset_index().rename(columns={"defteam": "team", "RB": "fc_RB", "TE": "fc_TE", "WR": "fc_WR"})
H2 = H.merge(D, on=["season", "week", "player_id"], how="left").merge(F, on=["season", "week", "team"], how="left")
for k in ("RB", "TE", "WR"):
    H2[f"tk_{k}"] = H2[f"tk_{k}"].fillna(0); H2[f"fc_{k}"] = H2[f"fc_{k}"].fillna(0)
H2 = H2.sort_values(["player_id", "season", "week"])
g = H2.groupby("player_id")
# walk-forward per-player rates per completion of each kind (prior games, this and last season), shrunk to the position's league rate
lg = {}
for k in ("RB", "TE", "WR"):
    H2[f"ptk_{k}"] = g[f"tk_{k}"].cumsum() - H2[f"tk_{k}"]; H2[f"pfc_{k}"] = g[f"fc_{k}"].cumsum() - H2[f"fc_{k}"]
    lg[k] = H2.groupby("group").apply(lambda d: d[f"tk_{k}"].sum() / max(1, d[f"fc_{k}"].sum()), include_groups=False)
    H2[f"rate_{k}"] = (H2[f"ptk_{k}"] + 40 * H2.group.map(lg[k])) / (H2[f"pfc_{k}"] + 40)
print("league tackle rate per completion by position and receiver kind:\n", pd.DataFrame(lg).round(3), flush=True)
# the opponent's mix, walk-forward (its prior games this season, shrunk to the league mix over 6 games)
O = O.sort_values(["team", "season", "week"]); og = O.groupby(["team", "season"])
tot = O[["gen_RB", "gen_TE", "gen_WR"]].sum(axis=1)
league_mix = {k: O[f"gen_{k}"].sum() / tot.sum() for k in ("RB", "TE", "WR")}
for k in ("RB", "TE", "WR"):
    O[f"p{k}"] = og[f"gen_{k}"].cumsum() - O[f"gen_{k}"]
O["pn"] = og.apply(lambda d: d[["gen_RB", "gen_TE", "gen_WR"]].sum(axis=1).cumsum().shift(1).fillna(0), include_groups=False).reset_index(level=[0, 1], drop=True)
O["games_prev"] = og.cumcount()
for k in ("RB", "TE", "WR"):
    O[f"mix_{k}"] = (O[f"p{k}"] + 6 * 30 * league_mix[k]) / (O.pn + 6 * 30)
mix = O[["season", "week", "team", "mix_RB", "mix_TE", "mix_WR"]].rename(columns={"team": "opp_team"})
H2 = H2.merge(mix, on=["season", "week", "opp_team"], how="left")
for k in ("RB", "TE", "WR"):
    H2[f"mix_{k}"] = H2[f"mix_{k}"].fillna(league_mix[k])
# expected pass tackles under the opponent's mix vs the league mix (per completion faced), the factor on the pass part only
exp_opp = sum(H2[f"rate_{k}"] * H2[f"mix_{k}"] for k in ("RB", "TE", "WR"))
exp_lg = sum(H2[f"rate_{k}"] * league_mix[k] for k in ("RB", "TE", "WR"))
ratio = (exp_opp / exp_lg).clip(0.7, 1.3)
# share of a player's tackles that come on completions (prior games), so the factor weighs only his pass part
pass_share = ((H2.ptk_RB + H2.ptk_TE + H2.ptk_WR) / (g.comb.cumsum() - H2.comb).clip(lower=1)).clip(0, 1).fillna(0.4)
H2["tmix"] = 1 + pass_share * (ratio - 1)
print("factor: mean %.3f sd %.3f p5 %.3f p95 %.3f" % (H2.tmix.mean(), H2.tmix.std(), H2.tmix.quantile(.05), H2.tmix.quantile(.95)), flush=True)
T = B.build_test_rows(H2, seasons); a = T.comb.astype(float).values; m = M.project_frame(T)[1].values
def mae_cal(p, i=None):
    aa, pp = (a, p) if i is None else (a[i], p[i]); sc = aa.sum() / pp.sum(); return float(np.mean(np.abs(aa - pp * sc)))
print("full model mae_cal %.4f" % mae_cal(m))
for power in (0.5, 1.0, 1.5):
    f = (T.tmix.values) ** power; parts = []
    for s in sorted(T.season.unique()):
        i = (T.season == s).values; parts.append(f"{s}: {mae_cal(m, i):.4f}->{mae_cal(m * f, i):.4f}")
    print(f"power {power}: mae_cal {mae_cal(m * f):.4f}  | " + "  ".join(parts), flush=True)
# does the ratio predict the residual at all? correlation of (actual/model) with the factor, by position
r = (T.comb / np.clip(m, 0.3, None)).values
for grp_ in ("LB", "S", "CB", "DL"):
    i = (T.group == grp_).values; print(f"  {grp_}: corr(factor, actual/model) = {np.corrcoef(T.tmix.values[i], r[i])[0, 1]:+.3f}  factor sd {T.tmix.values[i].std():.3f}")
print("DONE", flush=True)
