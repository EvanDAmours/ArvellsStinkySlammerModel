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


def credits_left(api_keys):
    """Credits left on every key (a free call each): {name: credits, or 0.0 for a rejected key, or None when unknown}."""
    if os.environ.get("TACKLE_FAKE_ODDS"):
        return {name: None for name in api_keys}
    out = {}
    for name, key in api_keys.items():
        try:
            out[name] = _credits(key)[0]
        except requests.HTTPError:
            out[name] = 0.0
        except requests.RequestException:
            out[name] = None
    return out


def pull(api_keys, hours_ahead=None, days=None, event_ids=None, markets=None):
    """Return (rows, credits_by_key). api_keys: {name: key}. Only games that haven't started; optionally only those
    within hours_ahead, or kicking off on the given Edmonton dates (days), or with the given event ids. `markets`: the
    market keys to ask for (each costs a credit a game); config.ODDS_MARKETS when not given."""
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
    now, rows, failed = _utcnow(), [], []
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
        label = f"{e['away_team']} @ {e['home_team']} {e['commence_time']}"
        r = _get_event_odds(e["id"], api_keys[name], label, markets)
        if r is None:
            failed.append(label)
            continue          # this game failed after retries: the other games still pull, and the next pull retries it
        if r.status_code in (404, 422):
            print(f"  {label}: HTTP {r.status_code} {r.text[:200].strip()}")
            continue
        if r.headers.get("x-requests-remaining") is not None:
            credits[name] = float(r.headers["x-requests-remaining"])
        books = r.json().get("bookmakers", [])
        if C.ODDS_BOOKMAKERS:
            books = [bk for bk in books if bk.get("key") in C.ODDS_BOOKMAKERS]
        n_books = sum(1 for bk in books if bk.get("markets"))
        print(f"  {label}: {n_books} books with tackle lines, cost {r.headers.get('x-requests-last', '?')} via {name}, left {credits[name]:g}")
        for bk in books:
            for m in bk.get("markets", []):
                sides, links, sids = {}, {}, {}
                for o in m.get("outcomes", []):
                    key = (o.get("description"), o.get("point")); side = str(o.get("name", "")).lower()
                    sides.setdefault(key, {})[side] = o.get("price")
                    links.setdefault(key, {})[side] = o.get("link"); sids.setdefault(key, {})[side] = o.get("sid")   # the book's own bet-slip link and selection id, when it gives them
                for (player, point), s in sides.items():
                    if player is None or point is None:
                        continue
                    lk, sd = links.get((player, point), {}), sids.get((player, point), {})
                    rows.append(dict(event_id=e["id"], commence_time=e["commence_time"], home_team=e["home_team"],
                                     away_team=e["away_team"], book=bk.get("title", bk.get("key")), book_key=bk.get("key"), market=m["key"],
                                     player=player, line=float(point), over_odds=s.get("over"), under_odds=s.get("under"),
                                     book_update=m.get("last_update"), over_link=lk.get("over"), under_link=lk.get("under"), over_sid=sd.get("over"), under_sid=sd.get("under"),
                                     market_link=m.get("link"), book_link=bk.get("link"), event_sid=e.get("sid")))
    if failed:
        print(f"odds api: {len(failed)} game(s) skipped after retries: {'; '.join(failed)}")
    return rows, credits


def _parse_books(e, books, keep_books=True):
    """One row per (book, market, player, line) from an event's bookmaker list, as the live pull stores them."""
    rows = []
    if keep_books and C.ODDS_BOOKMAKERS:
        books = [bk for bk in books if bk.get("key") in C.ODDS_BOOKMAKERS]
    for bk in books:
        for m in bk.get("markets", []):
            sides, links, sids = {}, {}, {}
            for o in m.get("outcomes", []):
                key = (o.get("description"), o.get("point")); side = str(o.get("name", "")).lower()
                sides.setdefault(key, {})[side] = o.get("price")
                links.setdefault(key, {})[side] = o.get("link"); sids.setdefault(key, {})[side] = o.get("sid")
            for (player, point), s in sides.items():
                if player is None or point is None:
                    continue
                lk, sd = links.get((player, point), {}), sids.get((player, point), {})
                rows.append(dict(event_id=e["id"], commence_time=e["commence_time"], home_team=e["home_team"],
                                 away_team=e["away_team"], book=bk.get("title", bk.get("key")), book_key=bk.get("key"), market=m["key"],
                                 player=player, line=float(point), over_odds=s.get("over"), under_odds=s.get("under"),
                                 book_update=m.get("last_update"), over_link=lk.get("over"), under_link=lk.get("under"), over_sid=sd.get("over"), under_sid=sd.get("under"),
                                 market_link=m.get("link"), book_link=bk.get("link"), event_sid=e.get("sid")))
    return rows


def historical_events(api_key, at):
    """The games the feed listed at a past moment (1 credit): [{id, commence_time, home_team, away_team}]."""
    r = requests.get(f"{BASE}/historical/sports/{C.ODDS_SPORT}/events", timeout=60, params={"apiKey": api_key, "date": at})
    r.raise_for_status()
    body = r.json()
    return body.get("data", body) or []


def pull_historical(api_key, season, week, markets, hours_before=1.0, event_ids=None, games=None, at=None, max_games=None):
    """Lines for a finished week from The Odds API's historical endpoint, one snapshot per game taken `hours_before`
    kickoff (a closing line for grading). Games and their event ids come from the week's own live snapshots, so
    only weeks the live pull covered can be fetched. Cost: 10 credits x markets x regions per game (historical
    requests cost ten times a live one). Returns (rows, credits_left); each row carries the snapshot time as
    `pulled_at`, so closing_lines() reads them like any other pull."""
    # `games`: a frame of event_id, commence_time, home_team, away_team for a week the live pull never covered (found with
    # historical_events); `at`: one fixed moment for every game instead of `hours_before` its kickoff; `max_games`: a sample.
    if games is None:
        s = load_snapshots(season, week)
        if s.empty:
            return [], None
        games = s.drop_duplicates("event_id")[["event_id", "commence_time", "home_team", "away_team"]]
    if event_ids:
        games = games[games.event_id.isin(set(event_ids))]
    if max_games:
        games = games.head(int(max_games))
    rows, left, fixed_at = [], None, at
    for g in games.itertuples():
        start = dt.datetime.fromisoformat(str(g.commence_time).replace("Z", "+00:00"))
        at = fixed_at or (start - dt.timedelta(hours=hours_before)).strftime("%Y-%m-%dT%H:%M:%SZ")
        r = requests.get(f"{BASE}/historical/sports/{C.ODDS_SPORT}/events/{g.event_id}/odds", timeout=60, params={
            "apiKey": api_key, "date": at, "markets": ",".join(markets), "oddsFormat": "american", **_book_params()})
        label = f"{g.away_team} @ {g.home_team} {g.commence_time}"
        if r.status_code == 401:
            raise SystemExit("history: the key's plan does not include historical odds (HTTP 401 on the historical endpoint; "
                             "The Odds API sells past lines on its paid tiers). Nothing was charged. Past weeks cannot be replayed "
                             "with this key; the market builds its record from the live pulls instead.")
        if r.status_code in (404, 422):
            print(f"  {label}: HTTP {r.status_code} {r.text[:200].strip()}")
            continue
        r.raise_for_status()
        if r.headers.get("x-requests-remaining") is not None:
            left = float(r.headers["x-requests-remaining"])
        body = r.json()
        data = body.get("data", body)
        stamp = str(body.get("timestamp") or at).replace("-", "").replace(":", "")
        stamp = stamp[:15] + "Z" if len(stamp) >= 15 else stamp
        e = dict(id=g.event_id, commence_time=g.commence_time, home_team=g.home_team, away_team=g.away_team, sid=None)
        got = _parse_books(e, data.get("bookmakers", []))
        for row in got:
            row["pulled_at"] = stamp
        rows.extend(got)
        print(f"  {label}: snapshot {body.get('timestamp', at)}, {len(got)} prices, cost {r.headers.get('x-requests-last', '?')}, left {left}")
    return rows, left


RETRY_WAITS = (3, 10, 30)      # seconds between attempts at one game after a server error or a dropped connection


def _get_event_odds(event_id, api_key, label, markets=None):
    """One game's odds. A server error (5xx, 429) or a dropped connection is retried with waits of RETRY_WAITS; a game
    that still fails returns None so the rest of the slate pulls (2026-11-07: one game's 502 at 8 pm threw away the
    whole Saturday pull). A client error other than 404/422 (a bad key) still raises."""
    params = {"apiKey": api_key, "markets": ",".join(markets or C.ODDS_MARKETS), "oddsFormat": "american", "includeLinks": "true", "includeSids": "true", **_book_params()}
    import time
    for attempt, wait in enumerate((0,) + RETRY_WAITS):
        if wait:
            time.sleep(wait)
        try:
            r = requests.get(f"{BASE}/sports/{C.ODDS_SPORT}/events/{event_id}/odds", timeout=30, params=params)
        except (requests.ConnectionError, requests.Timeout) as ex:
            print(f"  {label}: {type(ex).__name__} (attempt {attempt + 1})")
            continue
        if r.status_code >= 500 or r.status_code == 429:
            print(f"  {label}: HTTP {r.status_code} (attempt {attempt + 1})")
            continue
        if r.status_code not in (404, 422):
            r.raise_for_status()
        return r
    print(f"  {label}: still failing after {len(RETRY_WAITS) + 1} attempts; skipped this pull")
    return None


def save_snapshot(rows, season, week, root=None):
    if not rows:
        return None
    d = (Path(root) if root else ODDS_DIR) / str(season) / f"wk{week:02d}"
    d.mkdir(parents=True, exist_ok=True)
    stamp = _utcnow().strftime("%Y%m%dT%H%M%SZ")
    df = pd.DataFrame(rows)
    if "pulled_at" not in df.columns:
        df = df.assign(pulled_at=stamp)
    path = d / f"{stamp}.csv"
    df.to_csv(path, index=False)
    return path


def load_snapshots(season, week):
    d = ODDS_DIR / str(season) / f"wk{week:02d}"
    files = sorted(d.glob("*.csv")) if d.exists() else []
    return pd.concat([pd.read_csv(f) for f in files], ignore_index=True) if files else pd.DataFrame()


def latest_lines(season, week):
    """Each game's current board: the lines of its most recent pull. A pull fetches every book and market of a game in
    one call, so a line missing from the game's latest pull is one the book has moved or taken down. (Until 2026-11-09
    this kept the last price of every line ever seen that week: 21 graded picks, 4 of them A grades and a lock, were
    logged on lines no book was offering, e.g. Dante Trader Jr. Under 3.5 at -169 when both books showed 2.5.)"""
    s = load_snapshots(season, week)
    if s.empty:
        return s
    s = s.sort_values("pulled_at")
    s = s[s.pulled_at == s.groupby("event_id").pulled_at.transform("max")]
    return s.drop_duplicates(["event_id", "book", "market", "player", "line"], keep="last")


def all_lines(season, week):
    """The last price of every (book, market, player, line) seen this week, current or not: for My board, where a bet
    already placed on a line the book has since moved must still be found. Never for pricing (use latest_lines)."""
    s = load_snapshots(season, week)
    if s.empty:
        return s
    return s.sort_values("pulled_at").drop_duplicates(["event_id", "book", "market", "player", "line"], keep="last")


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
