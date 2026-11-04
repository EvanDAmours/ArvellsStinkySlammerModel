import sys, numpy as np, pandas as pd
sys.path.insert(0, "/home/user/ArvellsStinkySlammerModel")
import config as C
from pipeline import odds as O
from pipeline.sources import norm_name
from pipeline.model import american_to_decimal as dec
R_ = "/tmp/claude-0/-home-user-ArvellsStinkySlammerModel/9774aa0d-3733-5c2c-b44f-73ecd122b6e0/scratchpad/res"
H = pd.read_parquet(f"{R_}/H.parquet")
pd.set_option("display.width", 220)
snaps = []
for wk in (7, 8):
    s = O.load_snapshots(2026, wk); s["week"] = wk; snaps.append(s)
Sn = pd.concat(snaps, ignore_index=True)
Sn["name_key"] = Sn.player.map(norm_name); Sn["kind"] = Sn.market.map(C.market_kind)
Sn["t"] = pd.to_datetime(Sn.pulled_at, format="%Y%m%dT%H%M%SZ", utc=True); Sn["kick"] = pd.to_datetime(Sn.commence_time, utc=True)
Sn = Sn[Sn.t < Sn.kick]
box = H[(H.season == 2026) & H.week.isin([7, 8])].groupby(["week", "name_key"]).agg(comb=("comb", "sum"), solo=("solo_t", "sum")).reset_index()
Sn = Sn.merge(box, on=["week", "name_key"], how="left")
Sn["actual"] = np.where(Sn.kind == "solo", Sn.solo, Sn.comb)
Sn = Sn[Sn.actual.notna() & (Sn.kind != "assists")].copy()
Sn["hrs_before"] = (Sn.kick - Sn.t).dt.total_seconds() / 3600
key = ["week", "event_id", "book", "market", "name_key"]
g = Sn.sort_values("t").groupby(key)
first = g.first().reset_index(); last = g.last().reset_index()
F = first.merge(last[key + ["line", "over_odds", "under_odds", "hrs_before"]], on=key, suffixes=("_open", "_close"))
print("=== 2. TIMING: the first posted line vs the closing line, against the box score")
for wk, d in F.groupby("week"):
    for kind, dd in d.groupby("kind"):
        e_o, e_c = dd.actual - dd.line_open, dd.actual - dd.line_close
        moved = dd[dd.line_open != dd.line_close]
        better = (np.abs(moved.actual - moved.line_close) < np.abs(moved.actual - moved.line_open)).mean() if len(moved) else np.nan
        worse = (np.abs(moved.actual - moved.line_close) > np.abs(moved.actual - moved.line_open)).mean() if len(moved) else np.nan
        print(f"wk{wk} {kind:9s} n={len(dd):4d}  first posted {dd.hrs_before_open.median():5.1f} h before kick (close {dd.hrs_before_close.median():4.1f} h)  "
              f"MSE open {np.mean(e_o**2):.3f} close {np.mean(e_c**2):.3f}  bias open {e_o.mean():+.2f} close {e_c.mean():+.2f}  "
              f"moved {len(moved)} ({len(moved)/len(dd):.0%}): close better {better:.0%}, worse {worse:.0%}")
# how early is early: error by hours-before-kick of the first post
F["bucket"] = pd.cut(F.hrs_before_open, [0, 6, 24, 48, 200], labels=["<6h", "6-24h", "24-48h", "48h+"])
print(F.groupby(["kind", "bucket"], observed=True).apply(lambda d: pd.Series(dict(n=len(d), mse_open=np.mean((d.actual - d.line_open) ** 2), mse_close=np.mean((d.actual - d.line_close) ** 2), moved=(d.line_open != d.line_close).mean())), include_groups=False).round(3).to_string())

print("\n=== 3. CROSS-BOOK: disagreement, offsets, middles, who moves first")
# same pull, same player-market, two books
by_pull = Sn.groupby(["week", "pulled_at", "event_id", "market", "name_key"]).agg(n_books=("book", "nunique"), lo=("line", "min"), hi=("line", "max")).reset_index()
multi = by_pull[by_pull.n_books >= 2]
print(f"player-market snapshots with 2+ books: {len(multi)} of {len(by_pull)}; lines differ in {(multi.hi > multi.lo).mean():.1%}; by a full point or more in {((multi.hi - multi.lo) >= 1).mean():.1%}")
cons = Sn.groupby(["week", "pulled_at", "event_id", "market", "name_key"]).line.transform("median")
Sn["vs_cons"] = Sn.line - cons
print("each book's line against the consensus at the same pull (mean, points):")
print(Sn[Sn.groupby(["week", "pulled_at", "event_id", "market", "name_key"]).book.transform("nunique") >= 2].groupby(["book", "kind"]).vs_cons.agg(["mean", "count"]).round(3).to_string())
# middles at the close: Over at the lower line, Under at the higher, both priced; profit when the actual lands strictly between
L = last.copy()
mid = []
for (wk, ev, mk, nk), d in L.groupby(["week", "event_id", "market", "name_key"]):
    if d.line.nunique() < 2: continue
    lo, hi = d.loc[d.line.idxmin()], d.loc[d.line.idxmax()]
    if pd.isna(lo.over_odds) or pd.isna(hi.under_odds) or lo.over_odds == 0 or hi.under_odds == 0: continue
    a = lo.actual; both = (a > lo.line) and (a < hi.line); one = (a > lo.line) != (a < hi.line)
    # two one-unit bets: both win (middle), or exactly one wins
    pnl = (dec(lo.over_odds) - 1 if a > lo.line else -1) + (dec(hi.under_odds) - 1 if a < hi.line else -1)
    mid.append(dict(week=wk, kind=C.market_kind(mk), gap=hi.line - lo.line, lo=lo.book, hi=hi.book, over_odds=lo.over_odds, under_odds=hi.under_odds, both=both, pnl=pnl))
Mi = pd.DataFrame(mid)
if len(Mi):
    print(f"middles at the close (two books, different lines): {len(Mi)}  hit both {Mi.both.mean():.1%}  P&L per middle (2 u staked) {Mi.pnl.mean():+.3f}  by kind: " + ", ".join(f"{k}: n={len(d)} both {d.both.mean():.0%} pnl {d.pnl.mean():+.2f}" for k, d in Mi.groupby("kind")))
    print("   which book is low vs high:", Mi.groupby(["lo", "hi"]).size().to_dict())
# who moves first: for lines that changed at a book, the earliest pull at which the new closing line appeared, by book
mv = []
for k_, d in Sn.sort_values("t").groupby(key):
    if d.line.iloc[0] == d.line.iloc[-1]: continue
    mv.append(dict(book=d.book.iloc[0], kind=d.kind.iloc[0], first_move=d[d.line != d.line.iloc[0]].t.iloc[0], week=d.week.iloc[0], event_id=d.event_id.iloc[0], market=d.market.iloc[0], name_key=d.name_key.iloc[0]))
Mv = pd.DataFrame(mv)
if len(Mv):
    lead = Mv.groupby(["week", "event_id", "market", "name_key"]).first_move.transform("min")
    Mv["led"] = Mv.first_move == lead; Mv["lag_h"] = (Mv.first_move - lead).dt.total_seconds() / 3600
    print("line moves by book: " + ", ".join(f"{b}: {len(d)} moves, first to move {d.led.mean():.0%}, lag when not {d[~d.led].lag_h.mean():.1f} h" for b, d in Mv.groupby("book")))

print("\n=== 4. ROLE CHANGES: blind sides at the close on flagged players")
L2 = pd.read_parquet(f"{R_}/lines78.parquet"); L2 = L2[L2.actual.notna() & (L2.kind != "assists")].copy()
flags = []
for wk in (7, 8):
    P = pd.read_parquet(f"{R_}/P{wk}.parquet")
    P["flag"] = np.select([P.new_role.fillna(False).astype(bool), P.reduced_role.fillna(False).astype(bool), P.dc_status.eq("promoted"), P.dc_status.eq("demoted"), P.vacancy_rule.fillna(False).astype(bool), P.absence.fillna(False).astype(bool)],
                          ["new role", "reduced role", "promoted", "demoted", "vacancy", "back from absence"], "none")
    flags.append(P[["name_key", "flag"]].assign(week=wk))
L2 = L2.merge(pd.concat(flags), on=["week", "name_key"], how="left"); L2["flag"] = L2.flag.fillna("none")
L2 = L2[(L2.over_odds.fillna(0) != 0) & (L2.under_odds.fillna(0) != 0) & (L2.actual != L2.line)]
L2["over_pnl"] = np.where(L2.actual > L2.line, L2.over_odds.map(dec) - 1, -1.0); L2["under_pnl"] = np.where(L2.actual < L2.line, L2.under_odds.map(dec) - 1, -1.0)
rows = []
for (fl, kind), d in L2.groupby(["flag", "kind"]):
    rows.append(dict(flag=fl, kind=kind, n=len(d), over_hit=(d.actual > d.line).mean(), over_pnl=d.over_pnl.mean(), under_pnl=d.under_pnl.mean(), line_minus_actual=(d.line - d.actual).mean(), model_minus_actual=(d.model - d.actual).mean()))
print(pd.DataFrame(rows).round(3).sort_values(["kind", "flag"]).to_string(index=False))

print("\n=== 5. WHY THE SOLO LINE IS HIGH: the league solo share and the implied share in the lines")
H26 = H[H.season >= 2023]
ss = H26.groupby(["season", "week"]).apply(lambda d: d.solo_t.sum() / d.comb.sum(), include_groups=False).unstack(0)
print("league solo share by week (rows) and season (columns):"); print(ss.round(3).iloc[:10].to_string())
print("season solo share:", H26.groupby("season").apply(lambda d: d.solo_t.sum() / d.comb.sum(), include_groups=False).round(3).to_dict())
# implied solo share in the closing lines: solo line / combined line for the same player at the same book
cl = last[last.kind.isin(["solo", "combined"])].pivot_table(index=["week", "event_id", "book", "name_key"], columns="kind", values="line").dropna().reset_index()
cl = cl.merge(box, on=["week", "name_key"], how="left")
cl["implied_share"] = cl.solo / cl.combined
prior = H[(H.season == 2026)].sort_values("week").groupby("name_key").apply(lambda d: (d.solo_t.cumsum().shift(1) / d.comb.cumsum().shift(1)).iloc[-1] if len(d) > 1 else np.nan, include_groups=False)
cl["prior_share"] = cl.name_key.map(prior)
print(f"solo line / combined line at the close: mean {cl.implied_share.mean():.3f} sd {cl.implied_share.std():.3f} (n={len(cl)}); players' own prior solo share: mean {cl.prior_share.mean():.3f} sd {cl.prior_share.std():.3f}; corr(line ratio, prior share) = {cl[['implied_share', 'prior_share']].corr().iloc[0, 1]:.2f}")
print("by book:", cl.groupby("book").implied_share.agg(["mean", "std", "count"]).round(3).to_dict("index"))
cl["actual_share"] = cl["solo_y"] / cl["comb"].clip(lower=1) if "solo_y" in cl.columns else np.nan
print("combined line - actual: %+.2f; solo line - actual solo: %+.2f; solo line implied by (combined line x actual league share %.3f) - actual solo: %+.2f" % (
    (cl.combined - cl.comb).mean(), (cl.solo_x - cl.solo_y).mean() if "solo_y" in cl.columns else float("nan"), ss[2026].dropna().iloc[-3:].mean(), (cl.combined * ss[2026].dropna().iloc[-3:].mean() - cl.solo_y).mean() if "solo_y" in cl.columns else float("nan")))
