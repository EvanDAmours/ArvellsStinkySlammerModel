"""Pull tackle prop lines from The Odds API and store timestamped snapshots.

Cost: (markets x regions) credits per game. Two tackle markets x one region = 2 credits per game,
so a full Sunday slate is ~28 credits. Several keys can be given; every key hits the same API and
returns the same lines, so they are used as one pool of credits: each game is fetched once, with
whichever key has the most credits left, and a key that drops below MIN_CREDITS_LEFT is retired.
Set TACKLE_FAKE_ODDS=1 to generate synthetic lines (used by the tests).
"""
import datetime as dt
import os
from pathlib import Path

import pandas as pd
import requests

import config as C

BASE = "https://api.the-odds-api.com/v4"
ODDS_DIR = Path("data/odds")


def _utcnow():
    return dt.datetime.now(dt.timezone.utc)


def _credits(api_key):
    """Credits left this month for one key (the events call is free), plus the event list."""
    ev = requests.get(f"{BASE}/sports/{C.ODDS_SPORT}/events", params={"apiKey": api_key}, timeout=30)
    ev.raise_for_status()
    rem = ev.headers.get("x-requests-remaining")
    return (float(rem) if rem is not None else None), ev.json()


def _pick_key(credits):
    """Name of the key with the most credits left that is still above the floor, or None."""
    usable = {n: c for n, c in credits.items() if c is None or c >= C.MIN_CREDITS_LEFT}
    if not usable:
        return None
    return max(usable, key=lambda n: -1 if usable[n] is None else usable[n])


def pull(api_keys, hours_ahead=None):
    """Return (rows, credits_by_key). api_keys: {name: key}. Only games that haven't started; optionally only those within hours_ahead."""
    if os.environ.get("TACKLE_FAKE_ODDS"):
        from tests.fake_data import fake_odds_rows
        return fake_odds_rows(), {name: "synthetic" for name in api_keys}
    if isinstance(api_keys, str):
        api_keys = {"ODDS_API_KEY": api_keys}
    credits, events = {}, None
    for name, key in api_keys.items():
        try:
            credits[name], ev = _credits(key)
            events = events or ev
        except requests.HTTPError as e:
            print(f"  {name}: rejected ({e.response.status_code} {e.response.text[:120].strip()}); skipping this key")
            credits[name] = 0.0
    if events is None:
        raise RuntimeError("No Odds API key worked")
    now, rows = _utcnow(), []
    window = f"next {hours_ahead:g} hours" if hours_ahead else "all upcoming"
    print(f"odds api: {len(events)} NFL events listed, pulling {window}, credits left " +
          ", ".join(f"{n} {c if c is not None else '?'}" for n, c in credits.items()))
    for e in events:
        start = dt.datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00"))
        if start <= now or (hours_ahead and (start - now).total_seconds() > hours_ahead * 3600):
            continue
        name = _pick_key(credits)
        if name is None:
            print(f"Stopping: every key is below {C.MIN_CREDITS_LEFT} credits for this month.")
            break
        r = requests.get(f"{BASE}/sports/{C.ODDS_SPORT}/events/{e['id']}/odds", timeout=30, params={
            "apiKey": api_keys[name], "regions": C.ODDS_REGIONS, "markets": ",".join(C.ODDS_MARKETS), "oddsFormat": "american"})
        label = f"{e['away_team']} @ {e['home_team']} {e['commence_time']}"
        if r.status_code in (404, 422):
            print(f"  {label}: HTTP {r.status_code} {r.text[:200].strip()}")
            continue
        r.raise_for_status()
        if r.headers.get("x-requests-remaining") is not None:
            credits[name] = float(r.headers["x-requests-remaining"])
        books = r.json().get("bookmakers", [])
        n_books = sum(1 for bk in books if bk.get("markets"))
        print(f"  {label}: {n_books} books with tackle lines, cost {r.headers.get('x-requests-last', '?')} via {name}, left {credits[name]:g}")
        for bk in books:
            for m in bk.get("markets", []):
                sides = {}
                for o in m.get("outcomes", []):
                    key = (o.get("description"), o.get("point"))
                    sides.setdefault(key, {})[str(o.get("name", "")).lower()] = o.get("price")
                for (player, point), s in sides.items():
                    if player is None or point is None:
                        continue
                    rows.append(dict(event_id=e["id"], commence_time=e["commence_time"], home_team=e["home_team"],
                                     away_team=e["away_team"], book=bk.get("title", bk.get("key")), market=m["key"],
                                     player=player, line=float(point), over_odds=s.get("over"), under_odds=s.get("under"),
                                     book_update=m.get("last_update")))
    return rows, credits


def save_snapshot(rows, season, week):
    if not rows:
        return None
    d = ODDS_DIR / str(season) / f"wk{week:02d}"
    d.mkdir(parents=True, exist_ok=True)
    stamp = _utcnow().strftime("%Y%m%dT%H%M%SZ")
    df = pd.DataFrame(rows).assign(pulled_at=stamp)
    path = d / f"{stamp}.csv"
    df.to_csv(path, index=False)
    return path


def load_snapshots(season, week):
    d = ODDS_DIR / str(season) / f"wk{week:02d}"
    files = sorted(d.glob("*.csv")) if d.exists() else []
    return pd.concat([pd.read_csv(f) for f in files], ignore_index=True) if files else pd.DataFrame()


def latest_lines(season, week):
    """Most recent price for every (book, market, player, line) among games that haven't kicked off at the latest pull."""
    s = load_snapshots(season, week)
    if s.empty:
        return s
    s = s.sort_values("pulled_at")
    return s.drop_duplicates(["event_id", "book", "market", "player", "line"], keep="last")


def closing_lines(season, week):
    """Last price pulled before each game's kickoff: the closing line used to grade our timing."""
    s = load_snapshots(season, week)
    if s.empty:
        return s
    pulled = pd.to_datetime(s.pulled_at, format="%Y%m%dT%H%M%SZ", utc=True)
    start = pd.to_datetime(s.commence_time, utc=True)
    s = s[pulled < start].sort_values("pulled_at")
    return s.drop_duplicates(["event_id", "book", "market", "player"], keep="last")
