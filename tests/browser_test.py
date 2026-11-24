"""The site in a real browser. Run after the smoke test has written a synthetic site:

    SMOKE_SITE_OUT=/tmp/site python tests/smoke_test.py
    python tests/browser_test.py /tmp/site

The smoke test reads the page's text; this opens it. At a phone's width and a computer's it visits every tab, opens
every dropdown, and drives the parts that have broken before (week 10, 2026-11-15): a card printing
"[object HTMLElement]", a card squeezed to one word a line on a phone, a record stacked in small type, the noon games
filed under the wrong slot, a stale grade on My board. A check fails on a script error, a page wider than the screen,
garbled text ("[object", "undefined", "NaN"), or a block of text squeezed into a sliver.

Needs only the standard library and Playwright (`pip install playwright && python -m playwright install chromium`).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PORT = 8931
WIDTHS = (("phone", 390), ("computer", 1200))
fails = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


# what is wrong on the page as it stands: run after every step
PROBE = r"""(scope) => {
  const root = document.querySelector(scope) || document.body, W = document.documentElement.clientWidth;
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== 'hidden' && (!e.checkVisibility || e.checkVisibility()); };   // checkVisibility: a closed dropdown keeps its layout in Chromium
  const text = root.innerText || '';
  const bad = (text.match(/\[object [A-Za-z]+\]|\bundefined\b|\bNaN\b/g) || []).slice(0, 3);
  // a block of text squeezed into a sliver: its own words sit about one to a line (the lines are counted on the text itself,
  // so a short label in a tall table row is not mistaken for one)
  const squeezed = [];
  for (const e of root.querySelectorAll('div, p, td, li, span, b, small, label')) {
    if (!vis(e)) continue;
    const nodes = [...e.childNodes].filter((n) => n.nodeType === 3 && n.textContent.trim());
    const own = nodes.map((n) => n.textContent.trim()).join(' '), words = own.split(/\s+/).length;
    if (words < 4 || own.length < 20) continue;
    const tops = new Set();
    for (const n of nodes) { const rg = document.createRange(); rg.selectNodeContents(n); for (const r of rg.getClientRects()) if (r.width > 0) tops.add(Math.round(r.top)); }
    const w = e.getBoundingClientRect().width;
    if (tops.size >= 4 && tops.size >= 0.9 * words) squeezed.push(`${e.tagName.toLowerCase()}.${String(e.className).split(' ')[0]} ${Math.round(w)}px wide, ${words} words on ${tops.size} lines: "${own.slice(0, 40)}"`);
  }
  // anything reaching past the right edge that no scrolling box contains
  const wide = [];
  if (document.documentElement.scrollWidth > W + 1) {
    for (const e of root.querySelectorAll('*')) {
      const r = e.getBoundingClientRect(); if (!r.width || r.right <= W + 1) continue;
      let p = e.parentElement, clipped = false;
      while (p && p !== document.body) { const o = getComputedStyle(p).overflowX; if (o === 'auto' || o === 'scroll' || o === 'hidden') { clipped = true; break; } p = p.parentElement; }
      if (!clipped) { wide.push(`${e.tagName.toLowerCase()}.${String(e.className).split(' ')[0]} reaches ${Math.round(r.right)}px`); if (wide.length > 2) break; }
    }
  }
  return { bad, squeezed: squeezed.slice(0, 3), overflow: document.documentElement.scrollWidth > W + 1, wide, chars: text.trim().length };
}"""


def site_dir():
    """The synthetic site to open: the folder given, or one built by running the smoke test (slow)."""
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    out = Path(tempfile.mkdtemp()) / "site"
    print("no site folder given: running the smoke test to build one (a few minutes)", flush=True)
    r = subprocess.run([sys.executable, str(ROOT / "tests" / "smoke_test.py")], env=dict(os.environ, SMOKE_SITE_OUT=str(out)), capture_output=True, text=True)
    if not out.exists():
        sys.exit("the smoke test did not write a site:\n" + r.stdout[-2000:] + r.stderr[-2000:])
    return out


def prepare(src):
    """A copy of the site with this repository's page and the real replay of the season (the smoke copy leaves it out)."""
    dst = Path(tempfile.mkdtemp()) / "docs"
    shutil.copytree(src, dst)
    shutil.copy(os.environ.get("BROWSER_TEST_PAGE") or ROOT / "docs" / "index.html", dst / "index.html")
    shutil.copy(os.environ.get("BROWSER_TEST_NHL") or ROOT / "docs" / "nhl.html", dst / "nhl.html")   # the override lets a broken copy of the page prove the test fails on it
    res = dst / "data" / "results.json"
    retro = ROOT / "data" / "retro_five.json"
    if res.exists() and retro.exists():
        r = json.loads(res.read_text())
        if not r.get("retro"):
            r["retro"] = json.loads(retro.read_text())
            res.write_text(json.dumps(r))
    return dst


READY = "typeof BOOT !== 'undefined' && BOOT.rest"        # every data file is in and the open tab is drawn


def launch(p):
    exe = os.environ.get("CHROMIUM_PATH") or ("/opt/pw-browsers/chromium" if Path("/opt/pw-browsers/chromium").exists() else None)
    return p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()


def run_width(browser, name, width):
    ctx = browser.new_context(viewport={"width": width, "height": 900})
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.route("**/site.api.espn.com/**", lambda r: r.abort())          # the live feed is simulated below; no network in the test
    pg.goto(f"http://localhost:{PORT}/#record")              # a link to another tab: the page still opens on My board
    at = f"at {name} width ({width}px)"
    # the home screen: two tiles, NFL and NHL, over the board while it loads behind them
    hub = pg.evaluate("(() => { const h = document.querySelector('#hub'); return { shown: !!h && !h.hidden, tiles: [...h.querySelectorAll('.hub-tile b')].map((b) => b.textContent), badges: [...h.querySelectorAll('.hub-tile svg.hub-badge')].map((g) => Math.round(g.getBoundingClientRect().width)), nhl: document.querySelector('#hub-nhl').getAttribute('href') }; })()")
    check(hub["shown"] and hub["tiles"] == ["NFL", "NHL"] and hub["nhl"] == "nhl.html" and len(hub["badges"]) == 2 and min(hub["badges"]) >= 60, f"a visit opens on the home screen with an NFL and an NHL tile {at} ({hub})")
    r = pg.evaluate(PROBE, "#hub")
    check(not r["overflow"] and not r["bad"] and not r["squeezed"], f"the home screen fits the screen {at} ({r['wide']} {r['squeezed']})")
    pg.click("#hub-nfl")
    pg.wait_for_function("typeof BOOT !== 'undefined' && BOOT.first", timeout=20000)
    first = pg.evaluate("({ tab: TAB, mine: !document.querySelector('#mine').hidden, others: [...document.querySelectorAll('.wrap > section, body > section, section')].filter((x) => x.id && TABS.includes(x.id) && !x.hidden).map((x) => x.id) })")
    check(first["tab"] == "mine" and first["mine"] and first["others"] == ["mine"], f"the page opens on My board {at} ({first})")
    pg.wait_for_function(READY, timeout=20000)
    check(pg.evaluate("document.querySelector('#loading').hidden"), f"the loading note goes once every file is in {at}")

    def probe(scope, what, prose=False):
        """`prose`: the Patch log prints MODEL_LOG, which may quote "[object HTMLElement]" when it describes a past defect."""
        r = pg.evaluate(PROBE, scope)
        problems = ([f"script errors {errors[:2]}"] if errors else []) + ([f"garbled text {r['bad']}"] if r["bad"] and not prose else []) + ([f"squeezed {r['squeezed']}"] if r["squeezed"] else []) \
            + ([f"wider than the screen {r['wide']}"] if r["overflow"] else []) + (["nothing rendered"] if r["chars"] < 20 else [])
        check(not problems, f"{what} {at}" + (": " + "; ".join(problems) if problems else ""))
        del errors[:]

    # ---- every tab as it opens, then with every dropdown open
    tabs = pg.evaluate("[...document.querySelectorAll('nav button')].map((b) => b.dataset.tab)")
    check(tabs == ["mine", "plays", "record", "check", "ast", "gloss", "patch", "ledger", "sync", "proj"], f"the tabs are in the owner's order, My board first {at} ({tabs})")
    nav = pg.evaluate("(() => { const n = document.querySelector('nav'), bs = [...n.querySelectorAll('button')].map((b) => b.getBoundingClientRect()); return { slides: n.scrollWidth > n.clientWidth + 1, out: bs.filter((r) => r.left < -1 || r.right > innerWidth + 1 || r.width < 30).length, rows: new Set(bs.map((r) => Math.round(r.top))).size }; })()")
    check(not nav["slides"] and nav["out"] == 0 and nav["rows"] <= 2, f"every tab is in sight without sliding the bar {at} ({nav})")
    for t in tabs:
        pg.click(f'nav button[data-tab="{t}"]')
        pg.wait_for_timeout(350)
        probe(f"#{t}", f"tab '{t}' opens clean", prose=t == "patch")
        pg.evaluate(f"document.querySelectorAll('#{t} details').forEach((d) => {{ d.open = true; }})")
        pg.wait_for_timeout(250)
        probe(f"#{t}", f"tab '{t}' with every dropdown open", prose=t == "patch")

    # ---- Plays: the jump bar, a pick opened from the one-line list, the full-card view, the slots
    pg.reload()
    pg.wait_for_function(READY, timeout=20000)
    check(pg.evaluate("document.querySelector('#hub').hidden"), f"a reload keeps the board, not the home screen {at}")
    pg.click('nav button[data-tab="plays"]')
    pg.evaluate("(() => { try { localStorage.removeItem('plays-view'); } catch (e) {} PLAY_VIEW = null; renderPlays(); })()")
    jumps = pg.locator(".plays-jump button").count()
    rows = pg.locator("table.plays-compact tbody tr").count()
    check(jumps >= 3 and rows >= 3, f"Plays shows a jump bar and one line a pick {at} ({jumps} buttons, {rows} lines)")
    opened = pg.evaluate("""(() => { const d = document.querySelector('details.plays-grp[open]') || document.querySelector('details.plays-grp'); d.open = true;
        const row = d.querySelector('table.plays-compact tbody tr'); row.click(); const ex = row.nextSibling, card = ex && ex.querySelector('.play');
        return card ? { card: card.getBoundingClientRect().width, table: d.querySelector('table').getBoundingClientRect().width, lines: card.getBoundingClientRect().height } : null; })()""")
    check(bool(opened) and opened["card"] > 200 and opened["card"] >= 0.8 * opened["table"] and opened["lines"] < 900, f"a pick opened from the list takes the list's width {at} ({opened})")
    why = pg.evaluate("""(() => { const ex = document.querySelector('table.plays-compact tr.mine-expand'); const d = ex && ex.querySelector('details.why-box'); if (!d) return null; d.open = true;
        const td = d.querySelector('tbody td'); return td ? { label: td.getBoundingClientRect().width, text: td.textContent } : null; })()""")
    check(why is None or why["label"] >= 90, f"the 'Why' table inside an opened pick keeps a readable label column {at} ({why})")
    probe("#plays", "Plays with a pick opened and its 'Why' open")
    pg.locator(".plays-jump button", has_text="Show full cards").click()
    pg.wait_for_timeout(250)
    check(pg.locator("#plays-list details.plays-grp .play").count() >= 3, f"'Show full cards' shows the cards {at}")
    probe("#plays", "Plays as full cards")
    pg.evaluate("(() => { PLAY_VIEW = null; try { localStorage.removeItem('plays-view'); } catch (e) {} renderPlays(); })()")
    slots = pg.evaluate("['2026-11-15T14:30:00Z', '2026-11-15T18:00:00Z', '2026-11-15T21:05:00Z', '2026-11-15T21:25:00Z', '2026-11-16T01:20:00Z'].map((t) => slateOf(new Date(t)))")
    check(slots == ["intl", "early", "late", "late", "prime"], f"kickoffs fall in the right slot in Edmonton time: 8:30 am overseas, noon early, 3 pm afternoon, 7:20 pm prime ({slots})")
    filt = pg.evaluate("""(() => { const out = {}; for (const v of ['', 'intl', 'early', 'late', 'prime']) { document.querySelector('#slate').value = v; renderPlays(); out[v || 'all'] = document.querySelectorAll('table.plays-compact tbody tr').length; }
        document.querySelector('#slate').value = ''; renderPlays(); return out; })()""")
    check(filt["all"] >= max(filt["intl"], filt["early"], filt["late"], filt["prime"]), f"the Slate filter narrows the list {at} ({filt})")

    # ---- Track record: the live card with a result in it, the calculator, then and now
    pg.click('nav button[data-tab="record"]')
    pg.wait_for_timeout(300)
    live = pg.evaluate("""(() => { const s = DATA.results.summary; s.era = Object.assign({}, s.era, { wins: 8, losses: 6, pushes: 0, hit: 8 / 14, units_at_stake: 1.23, staked: 5.3, pending: 75 });
        renderRecord(); return document.querySelector('#record .rec-card').innerText.replace(/\\n/g, ' '); })()""")
    check("+1.2u on 5.3 staked" in live and "[object" not in live and "75 pending" in live, f"the live card reads its units as text {at} ({live[-60:]})")
    calc = pg.evaluate("""(() => { const sec = document.querySelector('#rec-whatif'); if (!sec) return null;
        const pick = (label, v) => { const s = sec.querySelector(`select[aria-label="${label}"]`); if (!s) return false; s.value = v; s.dispatchEvent(new Event('change')); return true; };
        const tick = (g, on) => { const c = sec.querySelector(`input[aria-label="Grade ${g}"]`); if (c && c.checked !== on) c.click(); };
        const staked = () => [...sec.querySelectorAll('.rec-card')].find((c) => /money staked/i.test(c.innerText))?.innerText.replace(/\\n/g, ' ');
        tick('A', true); tick('B', true); tick('C', true); pick('Stake', 'flat'); const flat = staked(); pick('Stake', 'grade'); const grade = staked();
        tick('B', false); tick('C', false); const onlyA = staked();
        return { flat, grade, onlyA, locks: !![...sec.querySelectorAll('.rec-card')].find((c) => /just the locks/i.test(c.innerText)), text: sec.innerText.slice(0, 0) }; })()""")
    check(bool(calc) and calc["flat"] and calc["grade"] and calc["flat"] != calc["grade"] and "at $" in calc["grade"] and "same answer" in (calc["onlyA"] or ""),
          f"the calculator's stake choices give different money with B and C ticked, and say why they match with A alone {at}")
    hist = pg.evaluate("(() => { const h = document.querySelector('#rec-history'); return h ? { heads: [...h.querySelectorAll('table th')].map((t) => t.textContent).slice(0, 12), pay: document.querySelector('#then-now-pay')?.innerText || '' } : null; })()")
    check(bool(hist) and "A only" in hist["heads"] and "$" in hist["pay"], f"'Then and now' shows what A alone, A and B, and every pick paid {at}")
    pg.evaluate("document.querySelectorAll('#record details').forEach((d) => { d.open = true; })")
    pg.wait_for_timeout(300)
    probe("#record", "Track record after the live card, the calculator and every dropdown")

    # ---- My board: a pick added from Plays, custom bets, a simulated game, the ledger, the backup
    pg.evaluate("(() => { for (const k of Object.keys(localStorage)) if (/^mine-/.test(k)) localStorage.removeItem(k); MINE = null; })()")
    pg.click('nav button[data-tab="plays"]')
    pg.locator("table.plays-compact button.add").first.click()
    pg.wait_for_timeout(250)
    pg.click('nav button[data-tab="mine"]')
    pg.wait_for_timeout(300)
    check(pg.evaluate("board().length") == 1, f"'+ My board' on a pick puts it on the board {at}")
    stale = pg.evaluate("""(() => { const b = mine()[0], want = b.grade; b.grade = want === 'C' ? 'A' : 'C'; b.commence_time = new Date(Date.now() + 3600e3).toISOString();
        const x = DATA.bets.find((y) => betKey({ ...y, side: y.pick }) === b.key); if (x) x.commence_time = b.commence_time; saveMine(mine()); renderMine(); return { want, got: mine()[0].grade }; })()""")
    check(stale["want"] == stale["got"], f"a bet's grade on My board follows the board until kickoff ({stale})")
    # custom bets through the form: a win last week, an open one this week
    wk = pg.evaluate("DATA.meta.week")
    for desc, price, stake, week, res in (("Giants moneyline", "+150", "20", wk - 1, "Win"), ("Chiefs -6.5", "1.91", "25", wk, "")):
        pg.evaluate("document.querySelector('#mine-custom-add').closest('details').open = true")
        f = pg.locator("#mine-custom-add")
        f.locator('input[aria-label="What the bet is"]').fill(desc)
        f.locator('input[aria-label="Odds"]').fill(price)
        f.locator('input[aria-label="Stake in dollars"]').fill(stake)
        f.locator('select[aria-label="Week"]').select_option(str(week))
        f.locator('select[aria-label="Result"]').select_option(res)
        f.locator("button", has_text="Add the bet").click()
        pg.wait_for_timeout(200)
    check(pg.locator(".live.custom").count() == 1 and "22.73" in pg.locator(".live.custom").inner_text(), f"a custom bet typed at 1.91 shows what a $25 stake wins at -110 {at}")
    # a game in the third quarter: an Under past its line, one heading past it, one on track, an Over past its line
    pg.evaluate("""(() => {
        const g = { id: 'g1', date: new Date(Date.now() - 5400e3).toISOString(), state: 'in', detail: '3rd 7:00', clock: '7:00', period: 3, teams: ['GB', 'MIN'], score: { GB: 0, MIN: 17 } };
        const mk = (player, side, line, odds) => ({ key: `t|${player}|${side}`, player, team: 'MIN', opp: 'GB', market: 'player_solo_tackles', side, line, book: 'DraftKings', odds, stake: 10, grade: 'A',
          season: DATA.meta.season, week: DATA.meta.week, commence_time: g.date, proj: 3 });
        const keep = mine().filter((b) => b.custom);
        // yesterday's game, final: a win that belongs to the week, not to today
        const g0 = { id: 'g0', date: new Date(Date.now() - 26 * 3600e3).toISOString(), state: 'post', detail: 'Final', clock: '0:00', period: 4, teams: ['DAL', 'NYG'], score: { DAL: 20, NYG: 17 } };
        const old = Object.assign(mk('Yesterday Win', 'Under', 4.5, -110), { team: 'DAL', opp: 'NYG', commence_time: g0.date });
        MINE = [...keep, old, mk('Past Line', 'Under', 2.5, -150), mk('Heading Past', 'Under', 3.5, -125), mk('On Track', 'Under', 4.5, -110), mk('Over Cleared', 'Over', 2.5, 104)];
        saveMine(MINE); LIVE.events = [g0, g]; LIVE.at = Date.now(); LIVE.error = null;
        LIVE.box.g0 = { final: true, at: Date.now(), players: { [normName('Yesterday Win')]: { tot: 3, solo: 1 } } };
        LIVE.box.g1 = { final: false, at: Date.now(), players: { [normName('Past Line')]: { tot: 4, solo: 3 }, [normName('Heading Past')]: { tot: 5, solo: 3 }, [normName('On Track')]: { tot: 2, solo: 1 }, [normName('Over Cleared')]: { tot: 4, solo: 3 } } };
        MINE_VIEW = 'cards'; renderMine(); })()""")
    read = "Object.fromEntries([...document.querySelectorAll('#mine-body .live:not(.custom)')].map((c) => [c.querySelector('.who').childNodes[1].textContent.trim(), c.className + ' | ' + c.querySelector('.trend').innerText.split(' · ')[0]]))"
    s1 = pg.evaluate(read)
    check("confirming" in s1.get("Past Line", "") and "behind" in s1.get("Heading Past", "") and "good" in s1.get("On Track", "") and "LOST" not in json.dumps(s1), f"a bet just past its line waits to be confirmed; one heading past it is 'behind' {at}")
    pg.evaluate("(() => { mine().forEach((b) => { if (b.past_line) b.past_line.at -= (CONFIRM_MIN + 1) * 60000; }); saveMine(mine()); renderMine(); })()")
    s2 = pg.evaluate(read)
    check(s2.get("Past Line", "").endswith("LOST") and " lost" in s2["Past Line"] and s2.get("Over Cleared", "").endswith("WON"), f"past the line for ten minutes reads LOST, and an Over past it WON {at}")
    tick = pg.evaluate("(() => { const t = document.querySelector('.now-ticker'); return t ? { cls: t.className, text: t.innerText.replace(/\\n/g, ' ') } : null; })()")
    # by hand: Past Line lost (-10), Heading Past heads for a loss (-10), On Track wins (10 at -110 = +9.09), Over Cleared wins (10 at +104 = +10.40): -0.51
    # yesterday's settled win (+9.09) is the week's, not today's: the banner starts each day from nothing
    check(bool(tick) and "-$0.51" in tick["text"] and "down" in tick["cls"] and "2 heading for a win, 2 for a loss" in tick["text"] and "settled today" not in tick["text"],
          f"'Where today is heading' adds up by hand on today's bets only, and is red when down {at} ({tick})")
    now = pg.evaluate("[...document.querySelectorAll('#mine-body .tile')].find((t) => /ended right now/.test(t.textContent))?.textContent.replace(/\\n/g, ' ')")
    # right now: yesterday's win is settled (+9.09), Past Line lost, the other two Unders are under their lines (+8 and +9.09), the Over is past its line (+10.40): +26.58
    check(bool(now) and "+$26.58" in now, f"'if every bet ended right now' adds up by hand {at} ({now})")
    pg.evaluate("(() => { LIVE.box.g1.players[normName('Past Line')].solo = 2; renderMine(); })()")
    check("LOST" not in pg.evaluate(read).get("Past Line", "LOST"), f"a stat correction back under the line clears LOST {at}")
    check(pg.locator("#mine-body > .stat-panels .stat-panel").count() == 3, f"My board shows its three panels {at}")
    # the week's panel: the top line (every pending bet hits) and the bottom line (every one loses). Settled +9.09; open
    # stakes 4 x $10 and the $25 custom bet: 9.09 - 65 = -55.91. To win: 6.67 + 8 + 9.09 + 10.40 + 22.73 = 56.89, so +65.98
    week_p = pg.evaluate("(() => { const d = document.querySelector('#mine-p-week'); d.open = true; return d.innerText.replace(/\\n/g, ' '); })()")
    check(f"WEEK {wk}" in week_p.upper() and "+$65.98" in week_p and "-$55.91" in week_p and "if every pending bet loses" in week_p, f"the week's panel is named for the week and shows its top and bottom line by hand {at} ({week_p[:120]})")
    pg.evaluate("(() => { try { localStorage.removeItem('mine-panels'); } catch (e) {} PANEL_OPEN.clear(); renderMine(); })()")
    tall = pg.evaluate("document.querySelector('#mine-body .mine-panels').getBoundingClientRect().height")
    check(tall < (190 if width <= 640 else 330), f"the three panels leave room for the bets {at} ({round(tall)}px tall)")
    probe("#mine", "My board with a game in play")
    # a custom bet waits under 'Custom bets' until it has a result, then sits with the settled bets
    moved = pg.evaluate("""(() => { const c = mine().find((b) => b.custom); const before = !!document.querySelector('#mine-custom') && !document.querySelector('details.mine-settled .live.custom');
        setCustomResult(MINE_KEY(), c.key, 'Win'); const inSettled = document.querySelectorAll('details.mine-settled .live.custom').length, head = document.querySelector('details.mine-settled summary').innerText;
        const out = { before, inSettled, open: !!document.querySelector('#mine-custom'), head }; setCustomResult(MINE_KEY(), c.key, ''); return out; })()""")
    check(moved["before"] and moved["inSettled"] == 1 and not moved["open"] and "Settled · 2" in moved["head"], f"a custom bet moves to Settled once it has a result {at} ({moved})")
    # the book a bet is at: chosen on the card, counted by book, and the board read one book at a time
    books = pg.evaluate("""(() => { const find = (name) => [...document.querySelectorAll('#mine-body .live:not(.custom)')].find((c) => c.querySelector('.who').textContent.includes(name));
        const names = () => [...document.querySelectorAll('#mine-body .live:not(.custom)')].map((c) => c.querySelector('.who').childNodes[1].textContent.trim());
        const chip = (n) => [...document.querySelectorAll('.book-chips button')].find((x) => x.textContent.startsWith(n));
        const key = mine().find((x) => x.player === 'On Track').key, sel = find('On Track').querySelector('.bookpick select'), had = sel.value;
        sel.value = 'FanDuel'; sel.dispatchEvent(new Event('change'));
        const chips = [...document.querySelectorAll('.book-chips button')].map((x) => x.textContent); chip('FanDuel').click(); const only = names(); chip('FanDuel').click();
        const b = mine().find((x) => x.player === 'On Track'), back = ledgerFromShort(ledgerShort()).weeks[MINE_KEY()].find((x) => x.player === 'On Track');
        return { had, placed: b.placed, sameKey: b.key === key, book: b.book, chips, only, all: names().length, shown: find('On Track').querySelector('.bookpick .full').textContent, code: back.placed }; })()""")
    check(books["had"] == "DraftKings" and books["placed"] == "FanDuel" and books["sameKey"] and books["book"] == "DraftKings" and "FanDuel 1 · $10 open" in books["chips"]
          and books["only"] == ["On Track"] and books["all"] == 5 and books["shown"] == "FanDuel" and books["code"] == "FanDuel",
          f"a bet's book is chosen on its card, counted under 'By book', filters the board, and travels in a backup code {at} ({books['chips']})")
    row = pg.evaluate("""(() => { MINE_VIEW = 'compact'; renderMine(); const tr = [...document.querySelectorAll('#mine-body table.mine-compact > tbody > tr')].find((r) => r.textContent.includes('On Track')), pill = tr.querySelector('.bookpick');
        pill.click(); const vis = (q) => getComputedStyle(pill.querySelector(q)).display !== 'none';
        const out = { opened: !!document.querySelector('table.mine-compact tr.mine-expand'), full: vis('.full'), short: vis('.short'), text: pill.querySelector('.short').textContent }; MINE_VIEW = 'cards'; renderMine(); return out; })()""")
    check(not row["opened"] and row["text"] == "FD" and (row["short"] and not row["full"] if width <= 640 else row["full"] and not row["short"]), f"the one-line view shows the book too, short on a phone, and choosing it does not open the card {at} ({row})")
    # a bet from the sleepers' list is not a pick: it carries the sleeper's grade in a purple box, not an empty one
    sl = pg.evaluate("""(() => { const x = DATA.bets.find((y) => y.under_odds != null && !mine().some((m) => m.key === betKey({ ...y, side: 'Under' })));
        Object.assign(x, { sleeper: 'Under', sleeper_grade: 'B', pick: '', grade: null, commence_time: new Date(Date.now() + 3 * 3600e3).toISOString() });
        toggleMine({ ...x, side: 'Under' }); const k = betKey({ ...x, side: 'Under' }), get = () => mine().find((m) => m.key === k);
        const box = () => { const c = [...document.querySelectorAll('#mine-body .live:not(.custom)')].find((c) => c.querySelector('.who').textContent.includes(x.player)); const g = c && c.querySelector('.who .grade'); return g ? { cls: g.className, text: g.textContent, bg: getComputedStyle(g).backgroundColor } : null; };
        const added = { sg: get().sg, grade: get().grade ?? null, box: box() };
        delete get().sg; saveMine(mine()); renderMine(); const old = { sg: get().sg, box: box() };                     // a bet added before today: read off the board
        const chipSl = !!document.querySelector('#mine-body .grade-chips .grade.sl'), code = ledgerFromShort(ledgerShort()).weeks[MINE_KEY()].find((b) => b.player === x.player && b.side === 'Under').sg;
        x.sleeper_grade = 'A'; renderMine(); const moved = get().sg; toggleMine({ ...x, side: 'Under' });
        return { added, old, chipSl, code, moved, left: mine().some((m) => m.key === k) }; })()""")
    check(sl["added"]["sg"] == "B" and sl["added"]["grade"] is None and sl["added"]["box"] and sl["added"]["box"]["text"] == "B" and "sl" in sl["added"]["box"]["cls"].split() and sl["added"]["box"]["bg"] == "rgb(122, 75, 196)"
          and sl["old"]["sg"] == "B" and sl["old"]["box"] and sl["chipSl"] and sl["code"] == "B" and sl["moved"] == "A" and not sl["left"],
          f"a sleeper on My board shows its sleeper grade in a purple box, an older bet picks it up from the board, and it follows the board until kickoff {at} ({sl['added']['box']})")
    # a pick that is also a sleeper shows both boxes; and '+ My board' on a sleeper adds the sleeper's side, whatever side
    # the pricing engine leans to on that line
    both = pg.evaluate("""(() => { const free = (y) => !mine().some((m) => m.player === y.player) && y.under_odds != null && y.over_odds != null;
        const x = DATA.bets.find(free), soon = new Date(Date.now() + 3 * 3600e3).toISOString();
        Object.assign(x, { sleeper: 'Under', sleeper_grade: 'A', pick: 'Under', side: 'Under', grade: 'C', commence_time: soon });
        toggleMine({ ...x }); const k = betKey({ ...x, side: 'Under' });
        const card = [...document.querySelectorAll('#mine-body .live:not(.custom)')].find((c) => c.querySelector('.who').textContent.includes(x.player));
        const boxes = [...card.querySelectorAll('.who .grade')].map((g) => [g.textContent, g.classList.contains('sl'), getComputedStyle(g).backgroundColor]);
        MINE_VIEW = 'compact'; renderMine(); const tr = [...document.querySelectorAll('#mine-body table.mine-compact > tbody > tr')].find((r) => r.textContent.includes(x.player));
        const line = [...tr.querySelectorAll('td:first-child .grade')].map((g) => g.textContent).join('+'), w = tr.querySelector('td:first-child').getBoundingClientRect().width; MINE_VIEW = 'cards';
        toggleMine({ ...x });
        // a sleeper on the Over where the engine's side of the line is the Under
        const y = DATA.bets.find((z) => free(z) && z.player !== x.player);
        Object.assign(y, { sleeper: 'Over', sleeper_grade: 'C', pick: 'Pass', side: 'Under', grade: null, over_odds: -150, under_odds: 115, commence_time: soon });
        for (const z of DATA.bets) if (z !== y && z.player === y.player && z.market === y.market) z.sleeper = '';
        renderPlays(); const rowS = [...document.querySelectorAll('.sleeper-row')].find((r) => r.textContent.includes(y.player)); rowS.querySelector('button.add').click();
        const got = mine().find((m) => m.player === y.player && m.market === y.market), out = got && { side: got.side, odds: got.odds, sg: got.sg, grade: got.grade ?? null };
        const on = [...document.querySelectorAll('.sleeper-row')].find((r) => r.textContent.includes(y.player)).querySelector('button.add').textContent;
        if (got) toggleMine({ ...y, side: got.side, pick: got.side }); renderPlays();
        return { boxes, line, w, sleeper: out, on, left: mine().some((m) => m.player === y.player || m.player === x.player) }; })()""")
    check(both["boxes"] == [["C", False, "rgb(138, 143, 152)"], ["A", True, "rgb(122, 75, 196)"]] and both["line"] == "C+A" and both["w"] < (40 if width <= 640 else 200),     # on a phone the two boxes stack inside the 30px grade column
          f"a pick that is also a sleeper shows its grey C and its purple A, in the card and in the one-line view {at} ({both["boxes"]}, {both["line"]}, {round(both["w"])}px)")
    check(both["sleeper"] == {"side": "Over", "odds": -150, "sg": "C", "grade": None} and "✓" in both["on"] and not both["left"],
          f"'+ My board' on a sleeper adds the sleeper's side at its price, not the engine's side of the line {at} ({both['sleeper']})")
    # every game final: nothing is open today, so the banner goes; the week's result is in the panels
    gone = pg.evaluate("""(() => { const g = LIVE.events.find((e) => e.id === 'g1'), was = JSON.stringify(MINE); g.state = 'post'; renderMine(); const none = !document.querySelector('.now-ticker');
        g.state = 'in'; MINE = JSON.parse(was); saveMine(MINE); renderMine(); return { none, back: !!document.querySelector('.now-ticker') }; })()""")
    check(gone["none"] and gone["back"], f"'Where today is heading' shows only while a bet of today's is open {at} ({gone})")
    pg.evaluate("(() => { MINE_VIEW = 'compact'; renderMine(); })()")
    probe("#mine", "My board, one line a bet")
    # the ledger, on its own tab: the season record on one line at the panel's size, last week's fold with what was wagered and won
    pg.click('nav button[data-tab="ledger"]')
    pg.wait_for_timeout(250)
    check(pg.evaluate("!document.querySelector('#mine #ledger-sec') && !!document.querySelector('#ledger #ledger-sec') && !document.querySelector('#mine #mine-sync') && !document.querySelector('#mine #mine-backup')"), f"the ledger, the sync and the backups are off My board, on their own tabs {at}")
    rec = pg.evaluate("""(() => { const t = [...document.querySelectorAll('#ledger .tile')].find((x) => x.textContent.includes('season record')); if (!t) return null; const b = t.querySelector(':scope > b');
        return { text: b.textContent, size: parseFloat(getComputedStyle(b).fontSize), height: b.getBoundingClientRect().height }; })()""")
    check(bool(rec) and rec["size"] >= 20 and rec["height"] < 2 * rec["size"], f"the season record sits on one line at full size {at} ({rec})")
    week = pg.evaluate(f"""(() => {{ const d = [...document.querySelectorAll('#ledger details.fold')].find((x) => x.id.endsWith('wk{wk - 1}')); if (!d) return null; d.open = true; return d.querySelector('.stat-panel')?.innerText.replace(/\\n/g, ' '); }})()""")
    check(bool(week) and "+$30" in week and "$20" in week and "$50" in week, f"a week of the ledger opens to what was wagered ($20), paid back ($50) and won (+$30) {at} ({(week or '')[:90]})")
    back = pg.evaluate("""(async () => { const want = JSON.stringify(allWeeks().map((w) => [w.key, w.list.filter((b) => b.custom).map((b) => [b.key, b.desc, b.odds, b.stake, b.settled?.result || null])]));
        const code = await pack(ledgerShort()); for (const w of allWeeks()) localStorage.removeItem(w.key); MINE = null;
        const first = ledgerImport(await unpack(code)), again = ledgerImport(await unpack(code));
        const got = JSON.stringify(allWeeks().map((w) => [w.key, w.list.filter((b) => b.custom).map((b) => [b.key, b.desc, b.odds, b.stake, b.settled?.result || null])]));
        renderMine(); return { same: want === got, added: first.added, again: again.added }; })()""")
    check(back["same"] and back["added"] >= 2 and back["again"] == 0, f"a backup code restores the ledger and a second restore adds nothing {at} ({back})")
    pg.evaluate("document.querySelectorAll('#ledger details').forEach((d) => { d.open = true; })")
    pg.wait_for_timeout(250)
    probe("#ledger", "the Ledger tab with every week open")
    pg.click('nav button[data-tab="sync"]')
    pg.wait_for_timeout(250)
    check(pg.locator("#sync #mine-sync").count() == 1 and pg.locator("#sync #mine-backup").count() == 1, f"the Sync tab holds the sync and the backups {at}")
    pg.evaluate("document.querySelectorAll('#sync details').forEach((d) => { d.open = true; })")
    probe("#sync", "the Sync tab with its steps open")
    pg.click('nav button[data-tab="mine"]')
    pg.evaluate("document.querySelectorAll('#mine details').forEach((d) => { d.open = true; })")
    pg.wait_for_timeout(250)
    probe("#mine", "My board with every dropdown open")
    ctx.close()


class FakeGitHub:
    """One private repo and one public one, in memory: the calls My board's sync makes, answered as GitHub answers them."""
    TOKEN = "github_pat_" + "x" * 40

    def __init__(self):
        self.file, self.sha, self.puts, self.gets, self.conflict_once = None, 0, 0, 0, False
        self.visible = [{"full_name": "me/board-data", "private": True, "permissions": {"push": True}}, {"full_name": "me/open-repo", "private": False, "permissions": {"push": True}}]   # what the token may see

    def handle(self, route):
        import base64
        req = route.request
        path = req.url.split("api.github.com", 1)[1].split("?")[0]
        def answer(status, body):
            route.fulfill(status=status, content_type="application/json", body=json.dumps(body), headers={"access-control-allow-origin": "*"})
        if req.method == "OPTIONS":
            return route.fulfill(status=204, headers={"access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "GET, PUT"})
        if req.headers.get("authorization") != f"Bearer {self.TOKEN}":
            return answer(401, {"message": "Bad credentials"})
        if path == "/user/repos":
            return answer(200, self.visible)
        if path == "/repos/me/open-repo":
            return answer(200, {"private": False, "permissions": {"push": True}})
        if path == "/repos/me/board-data":
            return answer(200, {"private": True, "permissions": {"push": True}})
        if path == "/repos/me/board-data/contents/slammer-board.json":
            if req.method == "GET":
                self.gets += 1
                if self.file is None:
                    return answer(404, {"message": "Not Found"})
                return answer(200, {"sha": f"sha{self.sha}", "content": base64.b64encode(self.file.encode()).decode()})
            body = json.loads(req.post_data)
            if self.conflict_once or (self.file is not None and body.get("sha") != f"sha{self.sha}"):
                self.conflict_once = False
                return answer(409, {"message": "is at a different sha"})
            self.file, self.sha, self.puts = base64.b64decode(body["content"]).decode(), self.sha + 1, self.puts + 1
            return answer(200, {"content": {"sha": f"sha{self.sha}"}})
        return answer(404, {"message": "Not Found"})


def run_sync(browser):
    """Two devices and one private repo: what one does reaches the other, nothing is wiped, and they settle."""
    hub = FakeGitHub()

    def device():
        ctx = browser.new_context(viewport={"width": 390, "height": 900})
        pg = ctx.new_page()
        pg.errors = []
        pg.on("pageerror", lambda e: pg.errors.append(str(e)))
        pg.route("**/site.api.espn.com/**", lambda r: r.abort())
        pg.route("**/api.github.com/**", hub.handle)
        pg.goto(f"http://localhost:{PORT}/")
        pg.click("#hub-nfl")
        pg.wait_for_function(READY, timeout=20000)
        return ctx, pg

    def sync(pg):
        pg.evaluate("(async () => { clearTimeout(SYNC.timer); await runSync(); await new Promise((r) => setTimeout(r, 50)); if (SYNC.busy) await SYNC.p; })()")

    board = "JSON.stringify(allWeeks().map((w) => [w.key, w.list.map((b) => [b.key, b.stake ?? null, b.settled?.result || null, !!b.archived]).sort()]).sort())"
    ca, a = device()
    wk = a.evaluate("DATA.meta.week")
    # device A: two picks with stakes and a custom bet, then connect
    a.evaluate("""(() => { const ps = DATA.bets.filter((b) => b.pick === 'Over' || b.pick === 'Under').slice(0, 2); for (const p of ps) toggleMine({ ...p, side: p.pick });
        setStake(mine()[0].key, '10'); setStake(mine()[1].key, '20'); addCustom({ desc: 'Giants moneyline', odds: 150, stake: 20, result: null, week: DATA.meta.week }); renderMine(); })()""")
    msg = a.evaluate(f"connectSync('me/open-repo', '{hub.TOKEN}').then(() => 'connected', (e) => e.msg)")
    check("public" in msg and a.evaluate("SYNC.cfg") is None, f"sync refuses a public repo ({msg[:60]})")
    msg = a.evaluate("connectSync('me/board-data', 'github_pat_' + 'y'.repeat(40)).then(() => 'connected', (e) => e.msg)")
    check("rejected the token" in msg, f"sync says so when GitHub rejects the token ({msg[:50]})")
    # a repo the token cannot see: the message names what the token can reach, or says its access is the trouble
    msg = a.evaluate(f"connectSync('me/lifting-data', '{hub.TOKEN}').then(() => 'connected', (e) => e.msg)")
    check("cannot see me/lifting-data" in msg and "It can reach: me/board-data" in msg, f"a repo the token cannot see is answered with the repos it can ({msg[:90]})")
    msg = a.evaluate(f"connectSync('someone/Board-Data', '{hub.TOKEN}').then(() => 'connected', (e) => e.msg)")
    check("Type the repo as me/board-data" in msg, f"a wrong owner is answered with the right name ({msg[:70]})")
    hub.visible = [x for x in hub.visible if not x["private"]]
    msg = a.evaluate(f"connectSync('me/lifting-data', '{hub.TOKEN}').then(() => 'connected', (e) => e.msg)")
    check("cannot see any private repo" in msg and "Only select repositories" in msg and a.evaluate("SYNC.cfg") is None, f"a token left on public repositories is told so ({msg[:70]})")
    hub.visible = [{"full_name": "me/board-data", "private": True, "permissions": {"push": True}}, {"full_name": "me/open-repo", "private": False, "permissions": {"push": True}}]
    a.click('nav button[data-tab="sync"]')
    a.fill("#sync-repo", "https://github.com/me/board-data")
    a.fill("#sync-token", hub.TOKEN)
    a.locator("#mine-sync button", has_text="Connect").click()
    a.wait_for_function("SYNC.state === 'ok'", timeout=10000)
    saved = json.loads(hub.file)
    check(hub.puts == 1 and saved["app"] == "slammer-board" and len(saved["weeks"][f"mine-{a.evaluate('DATA.meta.season')}-wk{wk}"]) == 3 and hub.TOKEN not in hub.file and "past_line" not in hub.file,
          f"connecting through the form writes the board to the repo, without the token ({hub.puts} save, {len(hub.file)} characters)")
    check("in step with me/board-data" in a.locator("#mine-sync").inner_text() and a.evaluate("document.querySelector('nav button[data-tab=\"sync\"]').dataset.sync") == "ok",
          "the Sync tab says the board is in step with the repo, and its button shows it")
    check(hub.TOKEN not in a.evaluate("JSON.stringify(ledgerExport()) + JSON.stringify(ledgerShort())"), "the token is in no backup file or code")
    # device B: empty, connects, receives everything
    cb, b = device()
    b.evaluate(f"connectSync('me/board-data', '{hub.TOKEN}')")
    b.wait_for_function("SYNC.state === 'ok'", timeout=10000)
    check(b.evaluate(board) == a.evaluate(board) and b.evaluate("board().length") == 3 and hub.puts == 1, "a second device connects and has the same board, with nothing written back")
    # B changes a stake, removes a pick, settles the custom bet; A receives all three
    b.evaluate("""(() => { const t = mine().filter((x) => !x.custom); setStake(t[0].key, '55'); toggleMine({ ...t[1], pick: t[1].side });
        const c = mine().find((x) => x.custom); setCustomResult(MINE_KEY(), c.key, 'Win'); })()""")
    sync(b)
    sync(a)
    got = a.evaluate("(() => { const t = mine().filter((x) => !x.custom && !x.archived), c = mine().find((x) => x.custom); return { n: t.length, stake: t[0] && t[0].stake, custom: c && c.settled && c.settled.result }; })()")
    check(got == {"n": 1, "stake": 55, "custom": "Win"} and a.evaluate(board) == b.evaluate(board), f"a stake change, a removal and a settled custom bet on one device reach the other ({got})")
    check(a.locator(".live.custom").count() == 1 and "Won" in a.locator(".live.custom .trend select").evaluate("(s) => s.selectedOptions[0].textContent"), "the page redraws with what arrived")
    # they settle: more syncs write nothing, and a removed pick stays removed
    before = hub.puts
    for _ in range(2):
        sync(a)
        sync(b)
    check(hub.puts == before and a.evaluate(board) == b.evaluate(board), f"two devices in step stop writing ({hub.puts - before} saves in four more syncs)")
    # both change different things while apart; then a save that collides is retried
    a.evaluate("addCustom({ desc: 'Chiefs -6.5', odds: -110, stake: 25, result: null, week: DATA.meta.week })")
    b.evaluate("(() => { const t = mine().find((x) => !x.custom); setStake(t.key, '60'); })()")
    sync(a)
    hub.conflict_once = True
    sync(b)
    sync(a)
    got = a.evaluate("({ customs: mine().filter((x) => x.custom).length, stake: mine().find((x) => !x.custom).stake })")
    check(got == {"customs": 2, "stake": 60} and a.evaluate(board) == b.evaluate(board) and b.evaluate("SYNC.state") == "ok", f"changes made apart are both kept, and a save that collides is retried ({got})")
    # a week deleted on one device goes on the other; a bet added again after a removal comes back
    a.evaluate("addCustom({ desc: 'Old bet', odds: -110, stake: 5, result: 'Loss', week: DATA.meta.week - 1 })")
    sync(a)
    sync(b)
    had = b.evaluate("allWeeks().length")
    a.on("dialog", lambda d: d.accept())
    a.evaluate(f"(() => {{ renderLedger(); const d = [...document.querySelectorAll('#ledger details.fold')].find((x) => x.id.endsWith('wk{wk - 1}')); d.open = true; [...d.querySelectorAll('button')].find((x) => /Delete week/.test(x.textContent)).click(); }})()")
    sync(a)
    sync(b)
    check(had == 2 and b.evaluate("allWeeks().length") == 1 and a.evaluate("allWeeks().length") == 1, "a week deleted on one device is deleted on the other")
    b.evaluate("(() => { const p = DATA.bets.filter((x) => x.pick === 'Over' || x.pick === 'Under')[1]; toggleMine({ ...p, side: p.pick }); })()")
    sync(b)
    sync(a)
    check(a.evaluate("mine().filter((x) => !x.custom).length") == 2 and a.evaluate(board) == b.evaluate(board), "a pick removed earlier and added again comes back on both")
    # the merge itself: the same answer whichever device runs it, and nothing more to do once it has run
    order = a.evaluate("""(() => {
        const past = '2026-01-01T00:00:00Z', future = new Date(Date.now() + 864e5).toISOString(), wk = 'mine-2026-wk10';
        const bet = (o) => Object.assign({ key: 'k1', player: 'P', market: 'player_solo_tackles', side: 'Under', line: 3.5, book: 'DraftKings', odds: -110, added: past, commence_time: past }, o);
        const pairs = [
          [bet({ stake: 10 }), bet({ stake: 15 })],                                                                    // the same moment, two stakes
          [bet({ stake: 10, u: 5 }), bet({ stake: 15, u: 9 })],                                                        // the later change
          [bet({ settled: { result: 'Win', actual: 2, source: 'live', at: '2026-01-02T00:00:05Z' } }), bet({ settled: { result: 'Win', actual: 2, source: 'live', at: '2026-01-02T00:00:09Z' } })],
          [bet({ settled: { result: 'Loss', actual: 4, source: 'live', at: 'x' } }), bet({ settled: { result: 'Win', actual: 3, source: 'official' } })],
          [bet({ grade: 'A', lock: 71, gu: 3 }), bet({ grade: 'C', lock: 55, gu: 8 })],                                // two readings of the board, after kickoff
          [bet({ grade: 'A', gu: 3, commence_time: future }), bet({ grade: 'C', gu: 8, commence_time: future, past_line: { kind: 'lost', at: 1 } })],
          [bet({ key: 'custom|a', custom: true, desc: 'ML', u: 4, settled: { result: 'Win', source: 'manual', at: 'a' } }), bet({ key: 'custom|a', custom: true, desc: 'ML', u: 7 })]];
        const same = pairs.every(([x, y]) => canonBet(mergeBet(x, y)) === canonBet(mergeBet(y, x)));
        const A = { weeks: { [wk]: pairs.map((p, i) => ({ ...p[0], key: 'k' + i })) }, deleted: { [wk + '|k1']: 7 } }, B = { weeks: { [wk]: pairs.map((p, i) => ({ ...p[1], key: 'k' + i })) }, deleted: {} };
        const ab = mergeBoards(A, B), ba = mergeBoards(B, A);
        return { same, boards: canonBoard(ab) === canonBoard(ba), settled: canonBoard(mergeBoards(ab, B)) === canonBoard(ab) && canonBoard(mergeBoards(ab, A)) === canonBoard(ab),
                 later: mergeBet(pairs[1][0], pairs[1][1]).stake, official: mergeBet(pairs[3][0], pairs[3][1]).settled.source, earlier: mergeBet(pairs[2][1], pairs[2][0]).settled.at.slice(-3),
                 grade: mergeBet(pairs[4][0], pairs[4][1]).grade, cleared: mergeBet(pairs[6][0], pairs[6][1]).settled === undefined, tomb: ab.weeks[wk].some((x) => x.key === 'k1') }; })()""")
    check(order["same"] and order["boards"] and order["settled"], f"a merge gives the same board whichever device runs it, and merging again changes nothing ({order})")
    check(order["later"] == 15 and order["official"] == "official" and order["earlier"] == "05Z" and order["grade"] == "C" and order["cleared"] and order["tomb"],
          "the later change wins, an official result beats a live one, and a removal older than the bet does not delete it")
    # the lifting app's connection, held by this browser under the same site, is offered and works
    cc, c = device()
    c.evaluate(f"localStorage.setItem('liftledger.sync.v1', JSON.stringify({{ repo: 'me/board-data', token: '{hub.TOKEN}' }}))")
    c.click('nav button[data-tab="sync"]')
    c.evaluate("renderSyncTab()")
    c.locator("#sync-use-lifting").click()
    c.wait_for_function("SYNC.state === 'ok'", timeout=10000)
    check(c.evaluate(board) == a.evaluate(board), "'Use my lifting app's connection' connects a new device in one tap")
    c.on("dialog", lambda d: d.accept())
    c.locator("#mine-sync button", has_text="Disconnect this device").click()
    check(c.evaluate("SYNC.cfg") is None and c.evaluate("localStorage.getItem('slammer.sync.v1')") is None and c.evaluate("board().length") >= 3, "disconnecting forgets the token and keeps the board")
    for pg in (a, b, c):
        for tab in ("mine", "sync"):
            pg.click(f'nav button[data-tab="{tab}"]')
            r = pg.evaluate(PROBE, f"#{tab}")
            check(not pg.errors and not r["bad"] and not r["overflow"], f"the '{tab}' tab with sync on is clean on a phone ({pg.errors[:1]} {r['bad']} {r['wide']})")
    for ctx in (ca, cb, cc):
        ctx.close()


def run_sealed(browser, docs):
    """The site as it is published: every data file sealed behind a password. The gate, the wrong password, the right
    one, and how much work the page does to open: one key derivation per password entry, not one per file."""
    sys.path.insert(0, str(ROOT))
    from pipeline import seal
    site = Path(tempfile.mkdtemp()) / "docs"
    shutil.copytree(docs, site)
    plain = sum(f.stat().st_size for f in (site / "data").glob("*.json"))
    seal.seal_dir(site / "data", [("evan", "second-pw"), ("friend", "third-pw"), ("main", "owner-pw")])
    sealed = sum(f.stat().st_size for f in (site / "data").glob("*.json.enc"))
    check(not list((site / "data").glob("*.json")) and sealed < 0.5 * plain, f"the sealed files are compressed before they are encrypted ({plain:,} bytes of data travel as {sealed:,})")
    srv = subprocess.Popen([sys.executable, "-m", "http.server", "--directory", str(site), str(PORT + 1)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.2)
    try:
        ctx = browser.new_context(viewport={"width": 390, "height": 900})
        pg = ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.route("**/site.api.espn.com/**", lambda r: r.abort())
        pg.add_init_script("window.__derived = 0; const __d = crypto.subtle.deriveKey.bind(crypto.subtle); crypto.subtle.deriveKey = (...a) => { window.__derived++; return __d(...a); };")
        pg.goto(f"http://localhost:{PORT + 1}/")
        pg.click("#hub-nfl")                                     # the home screen sits above the gate
        pg.wait_for_selector("#gate-pw", timeout=20000)
        check(pg.evaluate("!BOOT.first && !document.querySelector('#loading').hidden"), "a sealed site asks for the password and shows it is opening, not a blank page")
        pg.fill("#gate-pw", "not-the-password")
        pg.click("#gate button[type=submit]")
        pg.wait_for_function("document.querySelector('#gate-err').textContent.length > 0", timeout=20000)
        check(pg.evaluate("!BOOT.first"), "a wrong password opens nothing")
        pg.evaluate("window.__derived = 0")
        pg.fill("#gate-pw", "owner-pw")
        pg.click("#gate button[type=submit]")
        pg.wait_for_function(READY, timeout=20000)
        first = pg.evaluate("({ week: DATA.meta && DATA.meta.week, files: [DATA.meta, DATA.bets, DATA.proj, DATA.results, DATA.backtest, DATA.week_lines, DATA.patch, DATA.actuals].filter(Boolean).length, derived: window.__derived, slot: localStorage.getItem('site-pw-slot'), gate: document.querySelector('#gate').hidden })")
        check(first["week"] and first["files"] == 8 and first["gate"] and first["slot"] == "main" and first["derived"] <= 3 and not errors,
              f"the right password opens every sealed file, working the key out once per entry and not once per file ({first}, {errors[:1]})")
        pg.reload()
        pg.wait_for_function(READY, timeout=20000)
        again = pg.evaluate("({ derived: window.__derived, gate: !!document.querySelector('#gate') && !document.querySelector('#gate').hidden, tab: TAB })")
        check(again["derived"] == 1 and not again["gate"] and again["tab"] == "mine" and not errors, f"a returning device opens without the gate on one key derivation ({again}, {errors[:1]})")
        ctx.close()
    finally:
        srv.terminate()
        shutil.rmtree(site.parent, ignore_errors=True)


def nhl_feed():
    """ESPN's NHL scoreboard and box scores, in memory: one game on, one final, one to come. `state` is changed by the test."""
    state = {"live": {"period": 2, "clock": "10:00", "state": "in"}, "hits": {"Victor Eklund": 1, "Emil Heineman": 0, "Adam Klapka": 4, "Jack McBain": 2}}
    def team(ab, name, home, score):
        return {"homeAway": "home" if home else "away", "score": str(score), "team": {"abbreviation": ab, "displayName": name}}
    def event(i, start, away, home, st):
        return {"id": i, "date": start, "competitions": [{"status": {"period": st["period"], "displayClock": st["clock"], "type": {"state": st["state"], "shortDetail": {"in": f"{st['clock']} - {st['period']}nd", "post": "Final", "pre": "7:30 PM"}[st["state"]]}},
                "competitors": [team(away[0], away[1], False, 1), team(home[0], home[1], True, 2)]}]}
    def handle(route):
        u = route.request.url
        if "/scoreboard" in u:
            body = {"events": [event("901", "2026-11-24T00:30Z", ("TOR", "Toronto Maple Leafs"), ("NYI", "New York Islanders"), state["live"]),
                               event("902", "2026-11-24T00:30Z", ("CGY", "Calgary Flames"), ("OTT", "Ottawa Senators"), {"period": 3, "clock": "0:00", "state": "post"}),
                               event("903", "2026-11-24T03:00Z", ("MIN", "Minnesota Wild"), ("SJ", "San Jose Sharks"), {"period": 0, "clock": "20:00", "state": "pre"})]}
        else:
            ev = u.split("event=")[1].split("&")[0]
            keys = ["blockedShots", "hits", "takeaways", "plusMinus", "timeOnIce"]
            who = {"901": [("NYI", ["Victor Eklund", "Emil Heineman"]), ("TOR", ["Auston Matthews"])], "902": [("OTT", ["Adam Klapka"]), ("CGY", ["Jack McBain"])]}.get(ev, [])
            body = {"boxscore": {"players": [{"team": {"abbreviation": t}, "statistics": [{"name": "forwards", "keys": keys, "athletes": [
                {"athlete": {"displayName": n, "id": n[:3]}, "stats": ["0", str(state["hits"].get(n, 0)), "0", "0", "14:02"]} for n in names]},
                {"name": "goalies", "keys": ["saves"], "athletes": [{"athlete": {"displayName": "A Goalie"}, "stats": ["20"]}]}]} for t, names in who]}}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body), headers={"access-control-allow-origin": "*"})
    return state, handle


def run_nhl(browser):
    """The NHL hits page: reached from the home screen, a bet added through the form and followed live, bets added by a
    link, settled when the game is final (a win, a loss, a void for a player not in the box score), and a result by hand."""
    for name, width in WIDTHS:
        at = f"at {name} width ({width}px)"
        state, handle = nhl_feed()
        ctx = browser.new_context(viewport={"width": width, "height": 900})
        pg = ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.route("**/site.api.espn.com/apis/site/v2/sports/football/**", lambda r: r.abort())
        pg.route("**/site.api.espn.com/apis/site/v2/sports/hockey/**", handle)
        pg.add_init_script("Date.now = ((n) => () => n)(Date.parse('2026-11-24T01:10:00Z')); const __D = Date; window.Date = class extends __D { constructor(...a) { super(...(a.length ? a : [Date.now()])); } static now() { return __D.parse('2026-11-24T01:10:00Z'); } };")
        pg.goto(f"http://localhost:{PORT}/")
        pg.click("#hub-nhl")
        pg.wait_for_selector("#f-game option[value='901']", state="attached", timeout=20000)
        check(pg.url.endswith("/nhl.html") and pg.evaluate("document.querySelector('#home-link').getAttribute('href')") == "index.html", f"the NHL tile opens the hits page, which links home {at}")
        # a bet through the form
        pg.select_option("#f-game", "901")
        pg.fill("#f-player", "Victor Eklund")
        pg.select_option("#f-line", "1.5")
        pg.fill("#f-odds", "-208")
        pg.fill("#f-stake", "20")
        pg.click("#f-add")
        pg.wait_for_function("document.querySelectorAll('#list .bet').length === 1 && /hits/.test(document.querySelector('#list .bet .now').innerText) && document.querySelector('#list .bet .now b').textContent !== '–'", timeout=20000)
        card = pg.evaluate("(() => { const c = document.querySelector('#list .bet'); return { cls: c.className, hits: c.querySelector('.now b').textContent, text: c.innerText.replace(/\\n/g, ' ') }; })()")
        # one hit halfway through: heading for 1 + (1 + 1.5) / 1.5 x 0.5 = 1.83, over 1.5
        check(card["hits"] == "1" and "On track" in card["text"] and "heading for 1.8" in card["text"] and "good" in card["cls"] and "$20.00 to pay $29.62" in card["text"],
              f"a bet added through the form is followed live: hits so far, where he is heading, on track, the payout {at} ({card['text'][:160]})")
        r = pg.evaluate(PROBE, "body")
        check(not errors and not r["bad"] and not r["overflow"] and not r["squeezed"], f"the hits page with a live bet is clean {at} ({errors[:1]} {r['bad']} {r['wide']} {r['squeezed']})")
        # three more by a link: two on the final game, one whose player is not in the box score
        import base64
        add = [dict(player="Adam Klapka", side="Over", line=2.5, odds=-212, stake=20, book="Stake", day="2026-11-23", event="902", game="CGY @ OTT", start="2026-11-24T00:30Z"),
               dict(player="Jack McBain", side="Over", line=2.5, odds=-209, stake=20, book="Stake", day="2026-11-23", event="902", game="CGY @ OTT", start="2026-11-24T00:30Z"),
               dict(player="Nobody Dressed", side="Over", line=1.5, odds=-150, stake=10, book="Stake", day="2026-11-23", event="902", game="CGY @ OTT", start="2026-11-24T00:30Z")]
        link = base64.urlsafe_b64encode(json.dumps(add).encode()).decode().rstrip("=")
        pg.on("dialog", lambda d: d.accept())
        pg.goto(f"http://localhost:{PORT}/nhl.html#add={link}")
        pg.wait_for_function("JSON.parse(localStorage.getItem('nhl-bets-v1') || '[]').filter((b) => b.settled).length === 3", timeout=20000)
        got = pg.evaluate("JSON.parse(localStorage.getItem('nhl-bets-v1')).map((b) => [b.player, b.settled ? b.settled.result : null])")
        check(sorted(got) == sorted([["Victor Eklund", None], ["Adam Klapka", "Win"], ["Jack McBain", "Loss"], ["Nobody Dressed", "Void"]]) and "#add=" not in pg.url,
              f"bets added by a link settle when the game is final: 4 hits over 2.5 wins, 2 loses, a player not in the box score is void {at} ({got})")
        pg.goto(f"http://localhost:{PORT}/nhl.html#add={link}")       # the same link again adds nothing
        check(pg.evaluate("JSON.parse(localStorage.getItem('nhl-bets-v1')).length") == 4, f"opening the same link twice adds nothing {at}")
        pg.click(".tabs button[data-v='settled']")
        tot = pg.evaluate("document.querySelector('#totals').innerText.replace(/\\n/g, ' ')")
        # Klapka won 20 at -212: +9.43; McBain lost 20: -20.00; void: 0
        check("1-1" in tot and "-$10.57" in tot, f"the settled record and profit add up by hand {at} ({tot})")
        r = pg.evaluate(PROBE, "body")
        check(not errors and not r["bad"] and not r["overflow"], f"the settled list is clean {at} ({errors[:1]} {r['bad']} {r['wide']})")
        # a result set by hand moves an active bet to Settled
        pg.click(".tabs button[data-v='active']")
        pg.select_option("#list .bet select", "Loss")
        pg.wait_for_function("document.querySelectorAll('#list .bet').length === 0", timeout=5000)
        tot = pg.evaluate("document.querySelector('#totals').innerText.replace(/\\n/g, ' ')")
        check("1-2" in tot and "-$30.57" in tot, f"a result set by hand settles the bet {at} ({tot})")
        ctx.close()


def main():
    docs = prepare(site_dir())
    srv = subprocess.Popen([sys.executable, "-m", "http.server", "--directory", str(docs), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.2)
    try:
        with sync_playwright() as p:
            browser = launch(p)
            for name, width in WIDTHS:
                run_width(browser, name, width)
            run_sync(browser)
            run_sealed(browser, docs)
            run_nhl(browser)
            browser.close()
    finally:
        srv.terminate()
        shutil.rmtree(docs.parent, ignore_errors=True)
    print("\nALL BROWSER CHECKS PASSED" if not fails else f"\n{len(fails)} BROWSER CHECK(S) FAILED")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
