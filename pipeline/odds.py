"""Pull tackle prop lines from The Odds API and store timestamped snapshots.

Cost: (markets x regions) credits per game, where every 10 named bookmakers count as one region.
Two tackle markets x up to 10 books = 2 credits per game, so a full Sunday slate is ~28 credits.
Empty responses are free. Several keys can be given; every key hits the same API and returns the
same lines, so they are used in order as one pool of credits: each game is fetched once with the
first key still above MIN_CREDITS_LEFT, and the next key takes over when it drops below.
Only the bookmakers in config.ODDS_BOOKMAKERS are requested (and anything else is dropped).
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


def local_date(t):
    """Edmonton calendar date of a UTC datetime, as YYYY-MM-DD."""
    from zoneinfo import ZoneInfo
    return t.astimezone(ZoneInfo("America/Edmonton")).strftime("%Y-%m-%d")


def _credits(api_key):
    """Credits left this month for one key (the events call is free), plus the event list."""
    ev = requests.get(f"{BASE}/sports/{C.ODDS_SPORT}/events", params={"apiKey": api_key}, timeout=30)
    ev.raise_for_status()
    rem = ev.headers.get("x-requests-remaining")
    return (float(rem) if rem is not None else None), ev.json()


def list_events(api_key):
    """Upcoming NFL events (free call)."""
    return _credits(api_key)[1]


def _pick_key(credits):
    """First key, in config order, that is still above the credit floor (or of unknown balance); None if all are low."""
    for name, c in credits.items():
        if c is None or c >= C.MIN_CREDITS_LEFT:
            return name
    return None


def _book_params():
    if C.ODDS_BOOKMAKERS:
        return {"bookmakers": ",".join(C.ODDS_BOOKMAKERS)}
    return {"regions": C.ODDS_REGIONS}


def pull(api_keys, hours_ahead=None, days=None, event_ids=None):
    """Return (rows, credits_by_key). api_keys: {name: key}. Only games that haven't started; optionally only those
    within hours_ahead, or kicking off on the given Edmonton dates (days), or with the given event ids."""
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
    window = f"next {hours_ahead:g} hours" if hours_ahead else f"games on {sorted(days)}" if days else f"events {sorted(event_ids)}" if event_ids else "all upcoming"
    print(f"odds api: {len(events)} NFL events listed, pulling {window}, credits left " +
          ", ".join(f"{n} {c if c is not None else '?'}" for n, c in credits.items()))
    for e in events:
        start = dt.datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00"))
        if start <= now or (hours_ahead and (start - now).total_seconds() > hours_ahead * 3600):
            continue
        if days is not None and local_date(start) not in set(days):
            continue
        if event_ids is not None and e["id"] not in set(event_ids):
            continue
        name = _pick_key(credits)
        if name is None:
            print(f"Stopping: every key is below {C.MIN_CREDITS_LEFT} credits for this month.")
            break
        r = requests.get(f"{BASE}/sports/{C.ODDS_SPORT}/events/{e['id']}/odds", timeout=30, params={
            "apiKey": api_keys[name], "markets": ",".join(C.ODDS_MARKETS), "oddsFormat": "american", **_book_params()})
        label = f"{e['away_team']} @ {e['home_team']} {e['commence_time']}"
        if r.status_code in (404, 422):
            print(f"  {label}: HTTP {r.status_code} {r.text[:200].strip()}")
            continue
        r.raise_for_status()
        if r.headers.get("x-requests-remaining") is not None:
            credits[name] = float(r.headers["x-requests-remaining"])
        books = r.json().get("bookmakers", [])
        if C.ODDS_BOOKMAKERS:
            books = [bk for bk in books if bk.get("key") in C.ODDS_BOOKMAKERS]
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
                                     away_team=e["away_team"], book=bk.get("title", bk.get("key")), book_key=bk.get("key"), market=m["key"],
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


def upcoming_only(lines):
    """Drop lines for games that have already kicked off, so the board only shows bets that can still be placed."""
    if lines is None or len(lines) == 0 or "commence_time" not in lines:
        return lines
    start = pd.to_datetime(lines.commence_time, utc=True, errors="coerce")
    return lines[start.isna() | (start > _utcnow())]


def closing_lines(season, week):
    """Last price pulled before each game's kickoff: the closing line used to grade our timing."""
    s = load_snapshots(season, week)
    if s.empty:
        return s
    pulled = pd.to_datetime(s.pulled_at, format="%Y%m%dT%H%M%SZ", utc=True)
    start = pd.to_datetime(s.commence_time, utc=True)
    s = s[pulled < start].sort_values("pulled_at")
    return s.drop_duplicates(["event_id", "book", "market", "player"], keep="last")
