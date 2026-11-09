"""Settle picks from ESPN's final box score as soon as a game ends, instead of waiting for the official league stats
that reach nflverse overnight. Each settled pick is marked graded_by="live"; the next daily run grades from the
official stats and replaces it (they can differ by an assisted tackle).

A player missing from ESPN's defensive box score is left pending, never voided: ESPN lists only players with a
defensive stat, so missing can mean a zero-tackle game as easily as a player who sat. The official stats decide.
"""
import datetime as dt

import pandas as pd
import requests

from pipeline.sources import ESPN_TEAM, norm_name

SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary"


def final_events(dates):
    """ESPN events on these YYYYMMDD dates: [{id, teams (nflverse codes), state}]."""
    out = []
    for d in sorted(set(dates)):
        r = requests.get(SCOREBOARD, params={"dates": d}, timeout=20)
        r.raise_for_status()
        for e in r.json().get("events", []):
            c = e["competitions"][0]
            out.append(dict(id=e["id"], state=(c.get("status") or {}).get("type", {}).get("state"),
                            teams=[ESPN_TEAM.get(t["team"]["abbreviation"], t["team"]["abbreviation"]) for t in c["competitors"]]))
    return out


def box_rows(event_id, season, week):
    """Every defender in a game's ESPN box score: season, week, team, name_key, player, comb, solo_t."""
    r = requests.get(SUMMARY, params={"event": event_id}, timeout=20)
    r.raise_for_status()
    rows = []
    for team in r.json().get("boxscore", {}).get("players", []):
        code = ESPN_TEAM.get(team["team"]["abbreviation"], team["team"]["abbreviation"])
        for st in team.get("statistics", []):
            if st.get("name") != "defensive":
                continue
            ti, si = st["keys"].index("totalTackles"), st["keys"].index("soloTackles")
            for a in st.get("athletes", []):
                name = (a.get("athlete") or {}).get("displayName", "")
                try:
                    tot, solo = int(float(a["stats"][ti])), int(float(a["stats"][si]))
                except (ValueError, IndexError, KeyError):
                    continue
                rows.append(dict(season=season, week=week, team=code, name_key=norm_name(name), player=name, comb=tot, solo_t=solo))
    return rows


def finals(picks, season, week, now=None):
    """Box-score rows for every finished game of the week that has a pick still waiting for official stats."""
    now = now or dt.datetime.now(dt.timezone.utc)
    p = picks[(picks.season == season) & (picks.week == week)]
    if p.empty:
        return pd.DataFrame(), []
    kick = pd.to_datetime(p.commence_time, utc=True, errors="coerce")
    started = p[kick < now]
    if started.empty:
        return pd.DataFrame(), []
    dates = {(t - pd.Timedelta(hours=6)).strftime("%Y%m%d") for t in pd.to_datetime(started.commence_time, utc=True)}   # ESPN's date is US local
    teams = set(started.team.dropna())
    rows, done = [], []
    for e in final_events(dates):
        if e["state"] == "post" and teams & set(e["teams"]):
            rows += box_rows(e["id"], season, week)
            done.append(e["id"])
    return pd.DataFrame(rows), done
