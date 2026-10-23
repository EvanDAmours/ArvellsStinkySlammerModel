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
            "status": _col(df, "report_status", default="").fillna("").astype(str),
        }))
    if not frames:
        return pd.DataFrame(columns=["season", "week", "team", "name_key", "status"])
    return pd.concat(frames, ignore_index=True)
