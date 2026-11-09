"""Load NFL data from nflverse (free, updated nightly) and normalize it.

Every loader tries nflreadpy first, then the raw nflverse release files, so a renamed
file or package change makes the pipeline fail loudly instead of silently.
Set TACKLE_FAKE_DATA=1 to run everything on synthetic data (used by the tests).
"""
import io
import json
import os
from pathlib import Path
import re

import numpy as np
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
SEASON_GAME_TYPES = ("REG", "POST", "WC", "DIV", "CON", "SB")   # regular season and the playoffs; preseason stays out


def _season_game(kind):
    """True for regular-season and playoff rows (nflverse codes them REG and POST, or WC/DIV/CON/SB in schedules)."""
    k = kind.astype(str).str.upper().str.strip()
    return k.isin(SEASON_GAME_TYPES) | k.str.startswith("REG") | k.str.startswith("POST")


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
    out = out[_season_game(out.season_type)].copy()
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
        pw["solo_t"] = pw.solo + pw.with_ast       # a tackle made with an assist is a solo tackle in the official count
    else:  # solo+with_ast
        pw["comb"] = pw.solo + pw.with_ast
        pw["solo_t"] = pw.solo + pw.with_ast
    # 2026-11-09 audit: solo_t was nflverse's solo alone, booking "tackle with assist" as an assist, while ESPN's box score
    # (the official count, and what the live grader settles on) has solo = solo + with_ast for 523 of 523 week-9
    # defenders. 2-3% of solo tackles in 2025-26 (13% in 2024): solo projections ran low and solo Unders were flattered.
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
            "name_key": _canon_names(df, "player", "pfr_player_id"),
            "def_snaps": pd.to_numeric(_col(df, "defense_snaps", default=0), errors="coerce").fillna(0),
            "def_pct": pd.to_numeric(_col(df, "defense_pct", default=0), errors="coerce").fillna(0),
        }))
    if not frames:
        return pd.DataFrame(columns=["season", "week", "team", "name_key", "def_snaps", "def_pct"])
    sn = pd.concat(frames, ignore_index=True)
    sn = sn[_season_game(sn.game_type)].drop(columns=["game_type"])
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
        "away_score": pd.to_numeric(_col(df, "away_score", default=float("nan")), errors="coerce"),
        "roof": _col(df, "roof", default="").fillna("").astype(str),
        "location": _col(df, "location", default="Home").astype(str),
        # nflverse convention: positive spread_line means the home team is favored
        "spread_line": pd.to_numeric(_col(df, "spread_line", default=0), errors="coerce").fillna(0),
        "total_line": pd.to_numeric(_col(df, "total_line", default=float("nan")), errors="coerce"),
        "home_rest": pd.to_numeric(_col(df, "home_rest", default=7), errors="coerce").fillna(7),
        "away_rest": pd.to_numeric(_col(df, "away_rest", default=7), errors="coerce").fillna(7),
    })
    sc = sc[sc.season.isin(list(seasons)) & _season_game(sc.game_type)]
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
            "practice": _col(df, "practice_status", default="").fillna("").astype(str),
        }))
    if not frames:
        return pd.DataFrame(columns=["season", "week", "team", "name_key", "player_id", "status", "practice"])
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------- one name per player across feeds
_PFR_NAMES = None


def pfr_name_map():
    """PFR player id -> the stats feed's name key (via nflverse's players table, pfr_id -> display name). The snap-count
    and PFR advanced feeds print PFR's names ("Cameron Lewis", "Kamren Curl", "Patrick Surtain"); the stats feed prints
    the league's ("Cam Lewis", "Kam Curl", "Pat Surtain"). Thirteen regulars had no snaps at all in 2026 for that reason."""
    global _PFR_NAMES
    if _PFR_NAMES is None:
        try:
            pl = _nflreadpy("load_players")
            pl = pl[pl.pfr_id.notna() & pl.display_name.notna()]
            _PFR_NAMES = dict(zip(pl.pfr_id.astype(str), pl.display_name.map(norm_name)))
        except Exception as e:  # noqa: BLE001
            print(f"  players table: {type(e).__name__}: {e} (feed names used as printed)")
            _PFR_NAMES = {}
    return _PFR_NAMES


def _canon_names(df, name_col, id_col):
    """Name keys for a PFR-named feed: the stats feed's name where the id maps, the printed name otherwise."""
    printed = _col(df, name_col).map(norm_name)
    if id_col not in df.columns:
        return printed
    m = pfr_name_map()
    if not m:
        return printed
    mapped = df[id_col].astype(str).map(m)
    return mapped.where(mapped.notna(), printed)


# ---------------------------------------------------------------- jersey numbers (nflverse weekly rosters)
JERSEY_CACHE = Path("data/cache/jerseys.json")


def load_jerseys(season):
    """gsis player id -> jersey number from the latest weekly roster of the season. Tried three times; on failure the
    last good map (data/cache/jerseys.json) is used, so a network hiccup never blanks every number on the site
    (2026-11-08: one failed fetch left all 763 projections without one). Empty on synthetic data."""
    if os.environ.get("TACKLE_FAKE_DATA"):
        return {}
    import time
    for attempt in range(3):
        try:
            r = _nflreadpy("load_rosters_weekly", seasons=[season])
            r = r[r.gsis_id.notna() & r.jersey_number.notna()].sort_values("week")
            latest = r.groupby("gsis_id").tail(1)
            out = {str(g): int(j) for g, j in zip(latest.gsis_id, latest.jersey_number)}
            if out:
                try:
                    JERSEY_CACHE.parent.mkdir(parents=True, exist_ok=True)
                    JERSEY_CACHE.write_text(json.dumps(out))
                except OSError:
                    pass
                return out
            print(f"  jersey numbers: the roster feed came back empty (attempt {attempt + 1})")
        except Exception as e:  # noqa: BLE001
            print(f"  jersey numbers: {type(e).__name__}: {e} (attempt {attempt + 1})")
        time.sleep(5 * (attempt + 1))
    try:
        cached = json.loads(JERSEY_CACHE.read_text())
        print(f"  jersey numbers: using the last good copy ({len(cached)} players)")
        return cached
    except (OSError, ValueError):
        return {}


def load_espn_ids():
    """gsis player id -> ESPN athlete id, from the players table; empty on synthetic data or failure. Lets the site's
    live tracker match a bet to ESPN's box score by id instead of by name."""
    if os.environ.get("TACKLE_FAKE_DATA"):
        return {}
    try:
        pl = _nflreadpy("load_players")
        pl = pl[pl.gsis_id.notna() & pl.espn_id.notna()]
        return {str(g): str(e).split(".")[0] for g, e in zip(pl.gsis_id, pl.espn_id)}
    except Exception as e:  # noqa: BLE001
        print(f"  espn ids: {type(e).__name__}: {e}")
        return {}


# ---------------------------------------------------------------- outside injury feed (ESPN)
ESPN_INJURIES = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries"
ESPN_TEAM = {"WSH": "WAS", "LAR": "LA", "JAC": "JAX"}     # ESPN codes that differ from nflverse's
ESPN_STATUS = {"out": "out", "doubtful": "doubtful", "questionable": "questionable", "injured reserve": "injured reserve",
               "suspension": "suspended", "physically unable to perform": "pup"}
SEVERITY = {"out": 3, "injured reserve": 3, "ir": 3, "pup": 3, "suspended": 3, "doubtful": 2, "questionable": 1}


def parse_espn_injuries(payload, season, week):
    """The ESPN injury feed as rows like load_injuries(): one per listed player, current week. 'Active' listings
    (a note but no designation) are dropped. Suspensions and injured-reserve stays are listings here and not on the
    league report, which only carries the week's designations."""
    rows = []
    for team in (payload or {}).get("injuries", []) or []:
        for i in team.get("injuries", []) or []:
            a = i.get("athlete") or {}
            raw = str(i.get("status") or "").strip().lower()
            status = ESPN_STATUS.get(raw, "")
            if not status:
                if "reserve" in raw:
                    status = "injured reserve"
                elif "suspen" in raw:
                    status = "suspended"
                else:
                    continue
            code = str(((a.get("team") or {}).get("abbreviation")) or "").upper()
            rows.append(dict(season=int(season), week=int(week), team=ESPN_TEAM.get(code, code), name_key=norm_name(a.get("displayName", "")),
                             player_id="", status=status, practice="", pos=str((a.get("position") or {}).get("abbreviation") or ""),
                             return_date=str((i.get("details") or {}).get("returnDate") or ""), listed_at=str(i.get("date") or "")))
    cols = ["season", "week", "team", "name_key", "player_id", "status", "practice", "pos", "return_date", "listed_at"]
    return pd.DataFrame(rows, columns=cols)


def load_espn_injuries(season, week):
    """Current listings from ESPN (empty on synthetic data or when the feed is down: the league report still applies)."""
    if os.environ.get("TACKLE_FAKE_DATA"):
        return parse_espn_injuries({}, season, week)
    try:
        r = requests.get(ESPN_INJURIES, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        return parse_espn_injuries(r.json(), season, week)
    except Exception as e:  # noqa: BLE001
        print(f"  ESPN injuries: {type(e).__name__}: {e}")
        return parse_espn_injuries({}, season, week)


# the league's weekly roster: reserve lists the weekly injury report stops carrying (2026 week 9: Tremaine Edmunds, on
# injured reserve since week 7, was priced as active; ESPN's injury feed did not list him either)
ROSTER_OUT = {"RES": "injured reserve", "PUP": "injured reserve", "NFI": "injured reserve", "NON": "injured reserve",
              "SUS": "suspended", "EXE": "out"}


_ROSTERS = {}


def rosters_weekly(season):
    """The league's weekly rosters for a season (nflverse), fetched once per run. Empty on synthetic data or a failure."""
    if os.environ.get("TACKLE_FAKE_DATA"):
        return pd.DataFrame()
    if season not in _ROSTERS:
        try:
            r = _nflreadpy("load_rosters_weekly", seasons=[season])
            r = r[r.gsis_id.notna()].copy()
            r["week"] = pd.to_numeric(r.week, errors="coerce")
            _ROSTERS[season] = r
        except Exception as e:  # noqa: BLE001
            print(f"  weekly rosters: {type(e).__name__}: {e}")
            return pd.DataFrame()
    return _ROSTERS[season]


def roster_teams(season, week):
    """player id -> (team, roster week) from each player's latest weekly-roster row at or before `week`: where the
    league has him now. A trade shows here within days, often before the depth charts move him."""
    r = rosters_weekly(season)
    if r is None or len(r) == 0:
        return {}
    r = r[r.week <= week].sort_values("week").groupby("gsis_id").tail(1)
    return {str(g): (str(t), int(w)) for g, t, w in zip(r.gsis_id, r.team, r.week)}


def load_roster_out(season, week):
    """Players the league's weekly roster has on a reserve list (injured reserve, PUP, NFI), suspended or exempt as of
    `week` (his latest roster row at or before it), plus anyone the week's own rows list inactive. Rows like
    load_injuries(), for merge_injury_sources(). Empty on synthetic data or when the feed is down."""
    cols = ["season", "week", "team", "name_key", "player_id", "status", "practice"]
    if os.environ.get("TACKLE_FAKE_DATA"):
        return pd.DataFrame(columns=cols)
    r = rosters_weekly(season)
    if r is None or len(r) == 0 or "status" not in r.columns:
        return pd.DataFrame(columns=cols)
    r = r[r.week <= week].sort_values("week")
    last = r.groupby("gsis_id").tail(1)
    st = last.status.astype(str).str.upper()
    pick = st.isin(set(ROSTER_OUT)) | ((st == "INA") & (last.week == week))
    out = last[pick]
    return pd.DataFrame({"season": int(season), "week": int(week), "team": out.team.astype(str).values,
                         "name_key": out.full_name.map(norm_name).values, "player_id": out.gsis_id.astype(str).values,
                         "status": [ROSTER_OUT.get(x, "out") for x in st[pick]], "practice": ""}, columns=cols)


def merge_injury_sources(league, outside):
    """One listing per player-week: the more severe status wins (out/IR/suspended > doubtful > questionable), so a
    suspension or an IR stay that the league report never carries still rules a player out; the league report's
    practice status is kept. A player the outside feed calls 'Active' is not downgraded (it is not listed there)."""
    if outside is None or len(outside) == 0:
        return league
    cols = ["season", "week", "team", "name_key", "player_id", "status", "practice"]
    L = league[[c for c in cols if c in league.columns]].copy() if league is not None and len(league) else pd.DataFrame(columns=cols)
    for c in cols:
        if c not in L.columns:
            L[c] = ""
    O = outside[cols].copy()
    key = ["season", "week", "team", "name_key"]
    both = pd.concat([L.assign(_src=0), O.assign(_src=1)], ignore_index=True)
    both["_sev"] = both.status.fillna("").astype(str).str.lower().map(SEVERITY).fillna(0)
    both = both.sort_values(key + ["_sev", "_src"], ascending=[True] * len(key) + [False, True])
    first = both.drop_duplicates(key, keep="first")
    # keep the league report's practice status and player id even when the outside status wins
    lg = L.drop_duplicates(key).set_index(key)
    first = first.set_index(key)
    for c in ("practice", "player_id"):
        have = lg[c].reindex(first.index)
        first[c] = np.where(have.fillna("").astype(str) != "", have, first[c])
    return first.reset_index()[cols]


# ---------------------------------------------------------------- outside projections (FantasyPros expert consensus)
FP_URL = "https://www.fantasypros.com/nfl/projections/{pos}.php?week={week}"
FP_TEAM = {"JAC": "JAX", "LAR": "LA", "WSH": "WAS"}


def parse_fantasypros(html):
    """The rows FantasyPros embeds in its projection page (the top players at the position): expert-consensus solo
    tackles and assists per player. Returns name_key, team, fp_solo, fp_ast, fp_comb."""
    import json
    rows = []
    for m in re.finditer(r'"rows":\[', html or ""):
        try:
            arr, _ = json.JSONDecoder().raw_decode(html[m.end() - 1:])
        except ValueError:
            continue
        for r in arr:
            if not isinstance(r, dict) or "def_tackle" not in r:
                continue
            pl = r.get("player") or {}
            code = str(pl.get("team") or "").upper()
            solo, ast = float(r.get("def_tackle") or 0), float(r.get("def_assist") or 0)
            rows.append(dict(name_key=norm_name(pl.get("name", "")), team=FP_TEAM.get(code, code), fp_solo=solo, fp_ast=ast, fp_comb=solo + ast))
    return pd.DataFrame(rows, columns=["name_key", "team", "fp_solo", "fp_ast", "fp_comb"]).drop_duplicates(["name_key", "team"])


def load_fantasypros(week):
    """Expert-consensus tackle projections for the week's top defenders (DL, LB, DB pages). Never prices a line: a
    cross-check shown beside the model's number and kept for later validation."""
    if os.environ.get("TACKLE_FAKE_DATA"):
        return parse_fantasypros("")
    frames = []
    for pos in ("dl", "lb", "db"):
        try:
            r = requests.get(FP_URL.format(pos=pos, week=int(week)), timeout=60, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            if f"Week {int(week)}" not in r.text:
                print(f"  FantasyPros {pos}: page is not for week {week}, skipped")
                continue
            frames.append(parse_fantasypros(r.text))
        except Exception as e:  # noqa: BLE001
            print(f"  FantasyPros {pos}: {type(e).__name__}: {e}")
    if not frames:
        return parse_fantasypros("")
    return pd.concat(frames, ignore_index=True).drop_duplicates(["name_key", "team"])


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
        frames.append(d[_season_game(d.season_type)].drop(columns=["season_type"]))
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
        d = df[_season_game(_col(df, "game_type", default="REG"))]
        frames.append(pd.DataFrame({"season": pd.to_numeric(_col(d, "season", default=s)).astype(int), "week": pd.to_numeric(d.week).astype(int),
                                    "team": d.team.astype(str), "name_key": _canon_names(d, "pfr_player_name", "pfr_player_id"),
                                    "targets": pd.to_numeric(d.def_targets, errors="coerce").fillna(0),
                                    "missed": pd.to_numeric(d.def_missed_tackles, errors="coerce").fillna(0),
                                    "pfr_comb": pd.to_numeric(d.def_tackles_combined, errors="coerce").fillna(0),
                                    "press": pd.to_numeric(_col(d, "def_pressures", default=0), errors="coerce").fillna(0)}))
    if not frames:
        return pd.DataFrame(columns=["season", "week", "team", "name_key", "targets", "missed", "pfr_comb", "press"])
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
    pbp = pbp[_season_game(pbp.season_type) & pbp.play_type.isin(["run", "pass"])]
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
