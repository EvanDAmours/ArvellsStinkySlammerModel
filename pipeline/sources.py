"""Load NFL data from nflverse (free, updated nightly) and normalize it.

Every loader tries nflreadpy first, then the raw nflverse release files, so a renamed
file or package change makes the pipeline fail loudly instead of silently.
Set TACKLE_FAKE_DATA=1 to run everything on synthetic data (used by the tests).
"""
import io
import os
import re

import pandas as pd
import requests

REL = "https://github.com/nflverse/nflverse-data/releases/download"
NFLDATA_GAMES = "https://github.com/nflverse/nfldata/raw/master/data/games.csv"


def _read_url(url):
    r = requests.get(url, timeout=90)
    r.raise_for_status()
    if url.endswith(".parquet"):
        return pd.read_parquet(io.BytesIO(r.content))
    comp = "gzip" if url.endswith(".gz") else None
    return pd.read_csv(io.BytesIO(r.content), compression=comp, low_memory=False)


def _nflreadpy(fn, **kw):
    import nflreadpy as nfl
    df = getattr(nfl, fn)(**kw)
    return df.to_pandas() if hasattr(df, "to_pandas") else pd.DataFrame(df)


def _first_working(attempts):
    errors = []
    for name, fn in attempts:
        try:
            df = fn()
            if df is not None and len(df):
                return df, name
        except Exception as e:  # noqa: BLE001 - every failure is reported below
            errors.append(f"  {name}: {type(e).__name__}: {e}")
    raise RuntimeError("Every source failed:\n" + "\n".join(errors))


def _col(df, *names, default=None):
    for n in names:
        if n in df.columns:
            return df[n]
    if default is not None:
        return pd.Series([default] * len(df), index=df.index)
    raise KeyError(f"None of {names} found. Columns: {list(df.columns)[:40]}")


def norm_name(s):
    s = str(s).lower().replace(".", " ").replace("'", "").replace("’", "")
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", " ", s)
    return re.sub(r"[^a-z]", "", s)


def pos_group(position, group=""):
    p = str(position).upper()
    if p in {"LB", "ILB", "MLB", "OLB"}:
        return "LB"
    if p in {"S", "FS", "SS", "SAF"}:
        return "S"
    if p == "CB":
        return "CB"
    if p in {"DE", "DT", "NT", "DL", "EDGE"}:
        return "DL"
    if p == "DB" or str(group).upper() == "DB":
        return "S"
    return ""


# ---------------------------------------------------------------- player stats
def load_player_week(seasons):
    if os.environ.get("TACKLE_FAKE_DATA"):
        from tests.fake_data import fake_player_week
        return fake_player_week(seasons), "synthetic"
    frames, used = [], []
    for s in seasons:
        df, name = _first_working([
            ("nflreadpy", lambda s=s: _nflreadpy("load_player_stats", seasons=[s], summary_level="week")),
            ("stats_player csv.gz", lambda s=s: _read_url(f"{REL}/stats_player/stats_player_week_{s}.csv.gz")),
            ("stats_player csv", lambda s=s: _read_url(f"{REL}/stats_player/stats_player_week_{s}.csv")),
            ("player_stats_def csv", lambda s=s: _read_url(f"{REL}/player_stats/player_stats_def_{s}.csv")),
        ])
        frames.append(normalize_player_week(df, s))
        used.append(f"{s}: {name}")
    return pd.concat(frames, ignore_index=True), "; ".join(used)


def normalize_player_week(df, season):
    out = pd.DataFrame({
        "season": pd.to_numeric(_col(df, "season", default=season)).astype(int),
        "week": pd.to_numeric(_col(df, "week")).astype(int),
        "season_type": _col(df, "season_type", default="REG").astype(str),
        "player_id": _col(df, "player_id", "gsis_id").astype(str),
        "player": _col(df, "player_display_name", "player_name").astype(str),
        "position": _col(df, "position", default="").astype(str),
        "position_group": _col(df, "position_group", default="").astype(str),
        "team": _col(df, "team", "recent_team").astype(str),
        "opp": _col(df, "opponent_team", "opponent", default="").astype(str),
        "solo": pd.to_numeric(_col(df, "def_tackles_solo", default=0), errors="coerce").fillna(0),
        "ast": pd.to_numeric(_col(df, "def_tackle_assists", "def_tackles_assists", default=0), errors="coerce").fillna(0),
        "with_ast": pd.to_numeric(_col(df, "def_tackles_with_assist", default=0), errors="coerce").fillna(0),
    })
    out = out[out.season_type.str.upper().str.startswith("REG")].copy()
    out["group"] = [pos_group(p, g) for p, g in zip(out.position, out.position_group)]
    out = out[out.group != ""].copy()
    out["name_key"] = out.player.map(norm_name)
    return out


TACKLE_FORMULAS = ["solo+ast", "solo+with_ast+ast", "solo+with_ast"]


def apply_tackle_formula(pw, formula):
    pw = pw.copy()
    if formula == "solo+ast":
        pw["comb"] = pw.solo + pw.ast
        pw["solo_t"] = pw.solo
    elif formula == "solo+with_ast+ast":
        pw["comb"] = pw.solo + pw.with_ast + pw.ast
        pw["solo_t"] = pw.solo
    else:  # solo+with_ast
        pw["comb"] = pw.solo + pw.with_ast
        pw["solo_t"] = pw.solo
    return pw


def choose_tackle_formula(pw, checks):
    """Pick the combination of nflverse columns that reproduces official box-score totals."""
    best, report = None, []
    for f in TACKLE_FORMULAS:
        t = apply_tackle_formula(pw, f)
        errs = []
        for c in checks:
            rows = t[(t.season == c["season"]) & (t.name_key == norm_name(c["player"])) & (t.week <= c["through_week"])]
            if len(rows):
                errs.append(abs(float(rows.comb.sum()) - c["comb"]))
        mean_err = sum(errs) / len(errs) if errs else None
        report.append({"formula": f, "players_found": len(errs), "mean_abs_error": mean_err})
        if mean_err is not None and (best is None or mean_err < best[1]):
            best = (f, mean_err)
    chosen = best[0] if best else "solo+ast"
    ok = best is not None and best[1] <= 1.0
    return chosen, ok, report


# ---------------------------------------------------------------- snaps, schedule, injuries
def load_snaps(seasons):
    if os.environ.get("TACKLE_FAKE_DATA"):
        from tests.fake_data import fake_snaps
        return fake_snaps(seasons)
    frames = []
    for s in seasons:
        try:
            df, _ = _first_working([
                ("nflreadpy", lambda s=s: _nflreadpy("load_snap_counts", seasons=[s])),
                ("snap_counts csv.gz", lambda s=s: _read_url(f"{REL}/snap_counts/snap_counts_{s}.csv.gz")),
                ("snap_counts csv", lambda s=s: _read_url(f"{REL}/snap_counts/snap_counts_{s}.csv")),
            ])
        except RuntimeError:
            continue
        frames.append(pd.DataFrame({
            "season": pd.to_numeric(_col(df, "season", default=s)).astype(int),
            "week": pd.to_numeric(_col(df, "week")).astype(int),
            "game_type": _col(df, "game_type", default="REG").astype(str),
            "team": _col(df, "team").astype(str),
            "name_key": _col(df, "player").map(norm_name),
            "def_snaps": pd.to_numeric(_col(df, "defense_snaps", default=0), errors="coerce").fillna(0),
            "def_pct": pd.to_numeric(_col(df, "defense_pct", default=0), errors="coerce").fillna(0),
        }))
    if not frames:
        return pd.DataFrame(columns=["season", "week", "team", "name_key", "def_snaps", "def_pct"])
    sn = pd.concat(frames, ignore_index=True)
    sn = sn[sn.game_type.str.upper().str.startswith("REG")].drop(columns=["game_type"])
    sn.loc[sn.def_pct > 1.5, "def_pct"] = sn.def_pct / 100.0
    return sn


def load_schedule(seasons):
    if os.environ.get("TACKLE_FAKE_DATA"):
        from tests.fake_data import fake_schedule
        return fake_schedule(seasons)
    df, _ = _first_working([
        ("nflreadpy", lambda: _nflreadpy("load_schedules", seasons=list(seasons))),
        ("nfldata games.csv", lambda: _read_url(NFLDATA_GAMES)),
    ])
    sc = pd.DataFrame({
        "game_id": _col(df, "game_id").astype(str),
        "season": pd.to_numeric(_col(df, "season")).astype(int),
        "game_type": _col(df, "game_type", default="REG").astype(str),
        "week": pd.to_numeric(_col(df, "week")).astype(int),
        "gameday": _col(df, "gameday", default="").astype(str),
        "gametime": _col(df, "gametime", default="").astype(str),
        "home_team": _col(df, "home_team").astype(str),
        "away_team": _col(df, "away_team").astype(str),
        "home_score": pd.to_numeric(_col(df, "home_score", default=float("nan")), errors="coerce"),
        "location": _col(df, "location", default="Home").astype(str),
        # nflverse convention: positive spread_line means the home team is favored
        "spread_line": pd.to_numeric(_col(df, "spread_line", default=0), errors="coerce").fillna(0),
        "total_line": pd.to_numeric(_col(df, "total_line", default=float("nan")), errors="coerce"),
        "home_rest": pd.to_numeric(_col(df, "home_rest", default=7), errors="coerce").fillna(7),
        "away_rest": pd.to_numeric(_col(df, "away_rest", default=7), errors="coerce").fillna(7),
    })
    sc = sc[sc.season.isin(list(seasons)) & sc.game_type.str.upper().str.startswith("REG")]
    return sc.drop(columns=["game_type"]).reset_index(drop=True)


def load_injuries(seasons):
    if os.environ.get("TACKLE_FAKE_DATA"):
        from tests.fake_data import fake_injuries
        return fake_injuries(seasons)
    frames = []
    for s in seasons:
        try:
            df, _ = _first_working([
                ("nflreadpy", lambda s=s: _nflreadpy("load_injuries", seasons=[s])),
                ("injuries csv.gz", lambda s=s: _read_url(f"{REL}/injuries/injuries_{s}.csv.gz")),
                ("injuries csv", lambda s=s: _read_url(f"{REL}/injuries/injuries_{s}.csv")),
            ])
        except RuntimeError:
            continue
        frames.append(pd.DataFrame({
            "season": pd.to_numeric(_col(df, "season", default=s)).astype(int),
            "week": pd.to_numeric(_col(df, "week")).astype(int),
            "team": _col(df, "team").astype(str),
            "name_key": _col(df, "full_name", "player_name").map(norm_name),
            "player_id": _col(df, "gsis_id", default="").astype(str),
            "status": _col(df, "report_status", default="").fillna("").astype(str),
        }))
    if not frames:
        return pd.DataFrame(columns=["season", "week", "team", "name_key", "player_id", "status"])
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------- team volume (plays that end in a tackle)
def load_team_volume(seasons):
    """Per team-game: opportunities the offense generated (carries + completions + sacks taken) and, from the
    defense's side, the opportunities it faced. Columns: season, week, team, opp_team, gen, faced."""
    if os.environ.get("TACKLE_FAKE_DATA"):
        from tests.fake_data import fake_team_volume
        return fake_team_volume(seasons)
    frames = []
    for s in seasons:
        try:
            df, _ = _first_working([
                ("nflreadpy", lambda s=s: _nflreadpy("load_team_stats", seasons=[s], summary_level="week")),
                ("stats_team csv.gz", lambda s=s: _read_url(f"{REL}/stats_team/stats_team_week_{s}.csv.gz")),
            ])
        except RuntimeError:
            continue
        d = pd.DataFrame({
            "season": pd.to_numeric(_col(df, "season", default=s)).astype(int),
            "week": pd.to_numeric(_col(df, "week")).astype(int),
            "season_type": _col(df, "season_type", default="REG").astype(str),
            "team": _col(df, "team").astype(str),
            "opp_team": _col(df, "opponent_team", "opponent").astype(str),
            "gen": pd.to_numeric(_col(df, "carries", default=0), errors="coerce").fillna(0)
                   + pd.to_numeric(_col(df, "completions", default=0), errors="coerce").fillna(0)
                   + pd.to_numeric(_col(df, "sacks_suffered", default=0), errors="coerce").fillna(0),
        })
        frames.append(d[d.season_type.str.upper().str.startswith("REG")].drop(columns=["season_type"]))
    if not frames:
        return pd.DataFrame(columns=["season", "week", "team", "opp_team", "gen", "faced"])
    v = pd.concat(frames, ignore_index=True)
    faced = v.rename(columns={"team": "opp_team", "opp_team": "team", "gen": "faced"})
    return v.merge(faced, on=["season", "week", "team", "opp_team"], how="left")


# ---------------------------------------------------------------- depth charts
def load_depth_charts(seasons):
    """Defensive depth-chart starters. Two nflverse formats: through 2024 one chart per (season, week, team) with a
    rank in depth_team; from 2025 dated snapshots with pos_rank. Returns rows (season, week|None, date|None, team,
    player_id, rank) for defensive positions only."""
    if os.environ.get("TACKLE_FAKE_DATA"):
        from tests.fake_data import fake_depth_charts
        return fake_depth_charts(seasons)
    frames = []
    for s in seasons:
        try:
            df, _ = _first_working([("nflreadpy", lambda s=s: _nflreadpy("load_depth_charts", seasons=[s]))])
        except RuntimeError:
            continue
        if "depth_team" in df.columns and df.depth_team.notna().any():
            d = df[_col(df, "formation", default="").astype(str).eq("Defense")]
            d = d[pd.to_numeric(d.week, errors="coerce").notna() & pd.to_numeric(d.season, errors="coerce").notna() & d.gsis_id.notna()]
            frames.append(pd.DataFrame({"season": pd.to_numeric(d.season).astype(int), "week": pd.to_numeric(d.week).astype(int), "date": None,
                                        "team": d.club_code.astype(str), "player_id": d.gsis_id.astype(str),
                                        "rank": pd.to_numeric(d.depth_team, errors="coerce")}))
        elif "dt" in df.columns:
            d = df[df.pos_grp.fillna("").astype(str).str.contains(" D")]
            frames.append(pd.DataFrame({"season": s, "week": None, "date": d.dt.astype(str).str[:10], "team": d.team.astype(str),
                                        "player_id": d.gsis_id.astype(str), "rank": pd.to_numeric(d.pos_rank, errors="coerce")}))
    if not frames:
        return pd.DataFrame(columns=["season", "week", "date", "team", "player_id", "rank"])
    return pd.concat(frames, ignore_index=True).dropna(subset=["rank"])


def starters_for(dc, season, week, team, gameday):
    """Set of starters (rank 1) for a team's game, from the chart for that week (old format) or the latest dated
    chart on or before the game day (new format)."""
    if dc is None or len(dc) == 0:
        return None
    d = dc[(dc.season == season) & (dc.team == team)]
    if d.empty:
        return None
    if d.week.notna().any():
        d = d[d.week == week]
        return set(d[d["rank"] == 1].player_id) if len(d) else None
    d = d[(d.date <= str(gameday)) & (d.date >= f"{season}-08-01")]
    if d.empty:
        return None
    last = d.date.max()
    return set(d[(d.date == last) & (d["rank"] == 1)].player_id)


# ---------------------------------------------------------------- PFR advanced defence (targets, missed tackles)
def load_pfr_def(seasons):
    """Per player-game: targets in coverage and missed tackles (Pro Football Reference via nflverse)."""
    if os.environ.get("TACKLE_FAKE_DATA"):
        from tests.fake_data import fake_pfr_def
        return fake_pfr_def(seasons)
    frames = []
    for s in seasons:
        try:
            df, _ = _first_working([("nflreadpy", lambda s=s: _nflreadpy("load_pfr_advstats", seasons=[s], stat_type="def", summary_level="week"))])
        except RuntimeError:
            continue
        d = df[_col(df, "game_type", default="REG").astype(str).str.upper().str.startswith("REG")]
        frames.append(pd.DataFrame({"season": pd.to_numeric(_col(d, "season", default=s)).astype(int), "week": pd.to_numeric(d.week).astype(int),
                                    "team": d.team.astype(str), "name_key": d.pfr_player_name.map(norm_name),
                                    "targets": pd.to_numeric(d.def_targets, errors="coerce").fillna(0),
                                    "missed": pd.to_numeric(d.def_missed_tackles, errors="coerce").fillna(0),
                                    "pfr_comb": pd.to_numeric(d.def_tackles_combined, errors="coerce").fillna(0)}))
    if not frames:
        return pd.DataFrame(columns=["season", "week", "team", "name_key", "targets", "missed", "pfr_comb"])
    return pd.concat(frames, ignore_index=True).groupby(["season", "week", "team", "name_key"], as_index=False).sum()


# ---------------------------------------------------------------- play-by-play: run / pass tackle split, starters
PBP_COLS = ["season", "week", "season_type", "play_type", "defteam", "posteam", "complete_pass", "qb_scramble", "passer_player_id",
            "rusher_player_id", "solo_tackle_1_player_id", "solo_tackle_2_player_id", "assist_tackle_1_player_id", "assist_tackle_2_player_id",
            "assist_tackle_3_player_id", "assist_tackle_4_player_id", "tackle_with_assist_1_player_id", "tackle_with_assist_2_player_id"]


def load_pbp_tackles(seasons):
    """From play-by-play: per player-game tackle credits on run plays and on pass plays; per team-game the run plays
    and completions the defence faced; and each offence's most-used passer and rusher (its starters)."""
    if os.environ.get("TACKLE_FAKE_DATA"):
        from tests.fake_data import fake_pbp_tackles
        return fake_pbp_tackles(seasons)
    frames = []
    for s in seasons:
        try:
            import nflreadpy as nfl
            df = nfl.load_pbp(seasons=[s])
            df = df.select([c for c in PBP_COLS if c in df.columns]).to_pandas()
        except Exception as e:  # noqa: BLE001
            print(f"  play-by-play {s}: {type(e).__name__}: {e}")
            continue
        frames.append(df)
    empty = dict(players=pd.DataFrame(columns=["season", "week", "player_id", "run_tk", "pass_tk"]),
                 teams=pd.DataFrame(columns=["season", "week", "team", "runs_faced", "comps_faced"]),
                 starters=pd.DataFrame(columns=["season", "week", "team", "qb1", "rb1"]))
    if not frames:
        return empty
    pbp = pd.concat(frames, ignore_index=True)
    pbp = pbp[pbp.season_type.astype(str).str.upper().str.startswith("REG") & pbp.play_type.isin(["run", "pass"])]
    rows = []
    for c in PBP_COLS[10:]:
        if c in pbp.columns:
            rows.append(pbp[["season", "week", "play_type", c]].dropna(subset=[c]).rename(columns={c: "player_id"}))
    tk = pd.concat(rows, ignore_index=True)
    tk["run_tk"] = (tk.play_type == "run").astype(int)
    tk["pass_tk"] = (tk.play_type == "pass").astype(int)
    players = tk.groupby(["season", "week", "player_id"], as_index=False)[["run_tk", "pass_tk"]].sum()
    teams = pbp.groupby(["season", "week", "defteam"]).agg(runs_faced=("play_type", lambda x: int((x == "run").sum())),
                                                           comps_faced=("complete_pass", lambda x: int(pd.to_numeric(x, errors="coerce").fillna(0).sum()))).reset_index().rename(columns={"defteam": "team"})
    top = lambda x: x.dropna().value_counts().index[0] if x.notna().any() else None
    qb = pbp[pbp.play_type == "pass"].groupby(["season", "week", "posteam"]).passer_player_id.agg(top).reset_index().rename(columns={"posteam": "team", "passer_player_id": "qb1"})
    rb = pbp[(pbp.play_type == "run") & (pd.to_numeric(pbp.qb_scramble, errors="coerce").fillna(0) == 0)].groupby(["season", "week", "posteam"]).rusher_player_id.agg(top).reset_index().rename(columns={"posteam": "team", "rusher_player_id": "rb1"})
    starters = qb.merge(rb, on=["season", "week", "team"], how="outer")
    for d in (players, teams, starters):
        d["season"] = d.season.astype(int); d["week"] = d.week.astype(int)
    return dict(players=players, teams=teams, starters=starters)
