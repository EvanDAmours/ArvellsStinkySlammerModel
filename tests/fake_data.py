"""Synthetic league in the exact shape of nflverse data, with effects planted so the tests can check
that the pipeline recovers them:
  - every stadium has its own stat crew (solo share 0.48 to 0.66)
  - linebacker tackle counts are tighter than Poisson (variance = 0.75 x mean)
  - when a starting linebacker sits, the backup's role (and tackles) jump 60%
  - underdog defenses face more plays
Deterministic (fixed seed) so test results are repeatable.
"""
import datetime as dt
from functools import lru_cache

import numpy as np
import pandas as pd

TEAMS = ["ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
         "LV", "LAC", "LA", "MIA", "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SF", "SEA", "TB", "TEN", "WAS"]
CURRENT, DONE_WEEKS, WEEKS = 2026, 6, 17
ROLES = [("LB", "start", 7.5, 0.97), ("LB", "second", 6.0, 0.92), ("LB", "rot", 3.0, 0.45), ("LB", "backup", 0.8, 0.08),
         ("S", "start", 5.5, 0.98), ("S", "second", 4.5, 0.95), ("CB", "start", 4.2, 0.97), ("CB", "second", 3.8, 0.94),
         ("CB", "nickel", 3.0, 0.70), ("DL", "start", 2.6, 0.75), ("DL", "second", 2.2, 0.70), ("DL", "rot", 1.4, 0.45)]


@lru_cache(maxsize=None)
def _league(seasons):
    rng = np.random.default_rng(20261023)
    crew_share = {t: float(rng.uniform(0.48, 0.66)) for t in TEAMS}
    crew_share["NEUTRAL"] = 0.56
    players, pid = {}, 0
    for t in TEAMS:
        for g, role, rate, pct in ROLES:
            pid += 1
            players[f"P{pid:04d}"] = dict(team=t, group=g, role=role, base_rate=rate * float(rng.lognormal(0, 0.18)), pct=pct,
                                          name=f"{t} {g} {role}")
    # plant the known check player so the tackle-formula self-check can run
    den_lb = next(k for k, v in players.items() if v["team"] == "DEN" and v["group"] == "LB" and v["role"] == "start")
    players[den_lb]["name"] = "Alex Singleton"
    sched, stats, snaps, inj = [], [], [], []
    for s in seasons:
        season_rate = {k: v["base_rate"] * float(rng.lognormal(0, 0.10)) for k, v in players.items()}
        for w in range(1, WEEKS + 1):
            order = list(rng.permutation(TEAMS))
            for i in range(0, 32, 2):
                home, away = order[i], order[i + 1]
                spread = float(np.round(rng.normal(0, 5.5) * 2) / 2)   # positive = home favored
                neutral = rng.random() < 0.03
                final = not (s == CURRENT and w > DONE_WEEKS)
                gid = f"{s}_{w:02d}_{away}_{home}"
                sched.append(dict(game_id=gid, season=s, game_type="REG", week=w,
                                  gameday=str(dt.date(s, 9, 7) + dt.timedelta(days=7 * (w - 1))), gametime="13:00",
                                  home_team=home, away_team=away, home_score=float(rng.integers(10, 35)) if final else np.nan,
                                  away_score=float(rng.integers(10, 35)) if final else np.nan,
                                  location="Neutral" if neutral else "Home", spread_line=spread,
                                  total_line=float(np.round(rng.normal(44, 4) * 2) / 2), roof="outdoors"))
                if not final:
                    continue
                venue = "NEUTRAL" if neutral else home
                for team, opp, dog in ((home, away, -spread), (away, home, spread)):
                    plays = rng.normal(56, 6) * (1 + np.clip(0.005 * dog, -0.05, 0.05))
                    roster = {k: v for k, v in players.items() if v["team"] == team}
                    # a starting linebacker sits about 8% of the time; the backup absorbs the role
                    lb_out = [k for k, v in roster.items() if v["group"] == "LB" and v["role"] in ("start", "second") and rng.random() < 0.08 and v["name"] != "Alex Singleton"]
                    for k, v in roster.items():
                        if k in lb_out:
                            inj.append(dict(season=s, week=w, team=team, full_name=v["name"], report_status="Out"))
                            continue
                        boost = 1.6 if (lb_out and v["group"] == "LB" and v["role"] in ("rot", "backup")) else 1.0
                        pct = min(1.0, v["pct"] * (1.9 if boost > 1 and v["role"] == "rot" else 1.0) + (0.6 if boost > 1 and v["role"] == "backup" else 0))
                        a_lg, sh = (1 - 0.56) / (1 + 0.56), crew_share[venue]
                        crew = (1 + (1 - sh) / (1 + sh)) / (1 + a_lg)
                        lam = season_rate[k] * plays / 56 * crew * boost
                        if v["group"] == "LB":
                            n = int(np.ceil(lam / 0.25))
                            comb = int(rng.binomial(n, lam / n))
                        else:
                            comb = int(rng.poisson(lam))
                        solo = int(rng.binomial(comb, sh)) if comb else 0
                        snaps.append(dict(season=s, week=w, game_type="REG", team=team, opponent=opp, player=v["name"],
                                          position=v["group"], defense_snaps=round(pct * plays * 1.1), defense_pct=round(pct, 3)))
                        if v["name"] == "Alex Singleton" and s == CURRENT:   # planted official totals for the self-check
                            comb = [16, 9, 8, 14, 8, 13][w - 1]
                            solo = min(comb, int(rng.binomial(comb, sh)))
                        if comb > 0 or rng.random() < 0.5:   # like nflverse: zero-stat players are sometimes missing
                            stats.append(dict(player_id=k, player_display_name=v["name"], position=v["group"],
                                              position_group="DB" if v["group"] in ("S", "CB") else v["group"],
                                              team=team, opponent_team=opp, season=s, week=w, season_type="REG",
                                              def_tackles_solo=solo, def_tackle_assists=comb - solo, def_tackles_with_assist=0))
        if s == CURRENT:   # injury report for the upcoming week
            for t in TEAMS[:6]:
                k = next(k for k, v in players.items() if v["team"] == t and v["group"] == "LB" and v["role"] == "start")
                inj.append(dict(season=s, week=DONE_WEEKS + 1, team=t, full_name=players[k]["name"], report_status="Out"))
    return (pd.DataFrame(stats), pd.DataFrame(sched), pd.DataFrame(snaps), pd.DataFrame(inj), crew_share)


def _key(seasons):
    return tuple(sorted(set(int(s) for s in seasons)))


def fake_player_week(seasons):
    from pipeline.sources import normalize_player_week
    return normalize_player_week(_league(_key(seasons))[0], None)


def fake_schedule(seasons):
    df = _league(_key(seasons))[1]
    return df[df.season.isin(list(seasons))].drop(columns=["game_type"]).reset_index(drop=True)


def fake_snaps(seasons):
    from pipeline.sources import norm_name
    sn = _league(_key(seasons))[2]
    return pd.DataFrame(dict(season=sn.season, week=sn.week, team=sn.team, name_key=sn.player.map(norm_name),
                             def_snaps=sn.defense_snaps, def_pct=sn.defense_pct))


def fake_injuries(seasons):
    from pipeline.sources import norm_name
    inj = _league(_key(sorted(set([2023, 2024, 2025, 2026]) | set(seasons))))[3]
    inj = inj[inj.season.isin(list(seasons))]
    return pd.DataFrame(dict(season=inj.season, week=inj.week, team=inj.team, name_key=inj.full_name.map(norm_name),
                             status=inj.report_status))


def planted_crews():
    return _league((2023, 2024, 2025, 2026))[4]


def fake_odds_rows():
    """Lines a book might hang: season average, rounded, with a typical margin."""
    from pipeline.model import TEAM_NAMES
    P = pd.read_csv("data/cache/projections.csv")
    P = P[P.group == "LB"].sort_values("proj", ascending=False).head(50)
    rng = np.random.default_rng(7)
    start = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=2)).isoformat()
    rows = []
    for r in P.itertuples():
        for book in ("DraftKings", "FanDuel"):
            line = float(np.floor(r.season_avg + rng.normal(0, 0.6))) + 0.5
            rows.append(dict(event_id=f"E{r.team}", commence_time=start, home_team=TEAM_NAMES.get(r.team), away_team=TEAM_NAMES.get(r.opp_team),
                             book=book, market="player_tackles_assists", player=r.player, line=line,
                             over_odds=int(rng.choice([-125, -115, -110, -105, 100])), under_odds=int(rng.choice([-115, -110, -105, -120])),
                             book_update=start))
    return rows
