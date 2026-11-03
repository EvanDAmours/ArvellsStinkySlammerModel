"""Research harness: cache the loaded history and walk-forward projections for weeks 7 and 8 of 2026."""
import pickle, sys, json
from pathlib import Path
import pandas as pd, numpy as np
sys.path.insert(0, "/home/user/ArvellsStinkySlammerModel")
import config as C
import run as R
from pipeline import backtest as B, model as M, odds as O, sources as S, grade as G
OUT = Path("/tmp/claude-0/-home-user-ArvellsStinkySlammerModel/9774aa0d-3733-5c2c-b44f-73ecd122b6e0/scratchpad/res")
seasons, pw, sched, snaps_df, inj, H, status, src = R.load_all()
H.to_parquet(OUT / "H.parquet"); sched.to_parquet(OUT / "sched.parquet"); pw.to_parquet(OUT / "pw.parquet")
pickle.dump(dict(seasons=seasons, inj=inj, vol=src["vol"], dc=src["dc"], pbp_starters=src["pbp"]["starters"], status=status), open(OUT / "aux.pkl", "wb"))
print("H", H.shape, "columns", len(H.columns), flush=True)
out = {}
for wk in (7, 8):
    prior = H[(H.season < 2026) | ((H.season == 2026) & (H.week < wk))]
    bt, phi, k, scale, gbm = B.run_backtest(prior, seasons)
    F = M.upcoming_rows(H, sched, inj, 2026, wk, vol=src["vol"], dc=src["dc"], pbp_starters=src["pbp"]["starters"])
    P = M.finalize_projections(F, phi, scale=scale, gbm=gbm)
    P = R.attach_game_logs(P, H, 2026, wk)
    P.to_parquet(OUT / f"P{wk}.parquet")
    json.dump(dict(phi=phi, k=k, scale=scale), open(OUT / f"state{wk}.json", "w"))
    cl = O.closing_lines(2026, wk).copy()
    cl["name_key"] = cl.player.map(S.norm_name)
    cons = cl.groupby(["event_id", "name_key", "market"]).agg(line=("line", "median"), over_odds=("over_odds", "median"), under_odds=("under_odds", "median"), books=("book", "nunique")).reset_index()
    cons["kind"] = cons.market.map(C.market_kind)
    st = H[(H.season == 2026) & (H.week == wk)][["name_key", "team", "comb", "solo_t", "player_id"]].drop_duplicates("name_key")
    cons = cons.merge(st, on="name_key", how="left")
    cons["actual"] = np.where(cons.kind == "solo", cons.solo_t, np.where(cons.kind == "assists", cons.comb - cons.solo_t, cons.comb))
    pk = P[["name_key", "proj", "proj_solo", "proj_ast", "phi", "phi_solo", "phi_ast", "exp_opps", "share_pred", "group", "n_prev", "team"]].drop_duplicates("name_key")
    cons = cons.merge(pk.rename(columns={"team": "team_p"}), on="name_key", how="left")
    cons["model"] = np.where(cons.kind == "solo", cons.proj_solo, np.where(cons.kind == "assists", cons.proj_ast, cons.proj))
    cons["phi_use"] = np.where(cons.kind == "solo", cons.phi_solo, np.where(cons.kind == "assists", cons.phi_ast, cons.phi))
    cons["week"] = wk
    out[wk] = cons
    print(f"week {wk}: {len(P)} projections, {len(cons)} consensus lines, {cons.actual.notna().sum()} with actuals, {cons.model.notna().sum()} with a model", flush=True)
pd.concat(out.values()).to_parquet(OUT / "lines78.parquet")
print("DONE", flush=True)
