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
    shutil.copy(os.environ.get("BROWSER_TEST_PAGE") or ROOT / "docs" / "index.html", dst / "index.html")   # the override lets a broken copy of the page prove the test fails on it
    res = dst / "data" / "results.json"
    retro = ROOT / "data" / "retro_five.json"
    if res.exists() and retro.exists():
        r = json.loads(res.read_text())
        if not r.get("retro"):
            r["retro"] = json.loads(retro.read_text())
            res.write_text(json.dumps(r))
    return dst


def launch(p):
    exe = os.environ.get("CHROMIUM_PATH") or ("/opt/pw-browsers/chromium" if Path("/opt/pw-browsers/chromium").exists() else None)
    return p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()


def run_width(browser, name, width):
    ctx = browser.new_context(viewport={"width": width, "height": 900})
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.route("**/site.api.espn.com/**", lambda r: r.abort())          # the live feed is simulated below; no network in the test
    pg.goto(f"http://localhost:{PORT}/")
    pg.wait_for_function("typeof DATA !== 'undefined' && DATA.meta && document.querySelector('#plays-list') && document.querySelector('#plays-list').children.length > 0", timeout=20000)
    at = f"at {name} width ({width}px)"

    def probe(scope, what, prose=False):
        """`prose`: the Patch log prints MODEL_LOG, which may quote "[object HTMLElement]" when it describes a past defect."""
        r = pg.evaluate(PROBE, scope)
        problems = ([f"script errors {errors[:2]}"] if errors else []) + ([f"garbled text {r['bad']}"] if r["bad"] and not prose else []) + ([f"squeezed {r['squeezed']}"] if r["squeezed"] else []) \
            + ([f"wider than the screen {r['wide']}"] if r["overflow"] else []) + (["nothing rendered"] if r["chars"] < 20 else [])
        check(not problems, f"{what} {at}" + (": " + "; ".join(problems) if problems else ""))
        del errors[:]

    # ---- every tab as it opens, then with every dropdown open
    tabs = pg.evaluate("[...document.querySelectorAll('nav button')].map((b) => b.dataset.tab)")
    check(len(tabs) >= 8, f"the page has its tabs {at} ({tabs})")
    for t in tabs:
        pg.click(f'nav button[data-tab="{t}"]')
        pg.wait_for_timeout(350)
        probe(f"#{t}", f"tab '{t}' opens clean", prose=t == "patch")
        pg.evaluate(f"document.querySelectorAll('#{t} details').forEach((d) => {{ d.open = true; }})")
        pg.wait_for_timeout(250)
        probe(f"#{t}", f"tab '{t}' with every dropdown open", prose=t == "patch")

    # ---- Plays: the jump bar, a pick opened from the one-line list, the full-card view, the slots
    pg.reload()
    pg.wait_for_function("typeof DATA !== 'undefined' && DATA.meta && document.querySelector('#plays-list').children.length > 0", timeout=20000)
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
        MINE = [...keep, mk('Past Line', 'Under', 2.5, -150), mk('Heading Past', 'Under', 3.5, -125), mk('On Track', 'Under', 4.5, -110), mk('Over Cleared', 'Over', 2.5, 104)];
        saveMine(MINE); LIVE.events = [g]; LIVE.at = Date.now(); LIVE.error = null;
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
    check(bool(tick) and "-$0.51" in tick["text"] and "down" in tick["cls"] and "2 heading for a win, 2 for a loss" in tick["text"], f"'Where today is heading' adds up by hand and is red when down {at} ({tick})")
    now = pg.evaluate("[...document.querySelectorAll('#mine-body .tile')].find((t) => /ended right now/.test(t.innerText))?.innerText.replace(/\\n/g, ' ')")
    # right now: Past Line lost, the other two Unders are under their lines (+8 and +9.09), the Over is past its line (+10.40): +17.49
    check(bool(now) and "+$17.49" in now, f"'if every bet ended right now' adds up by hand {at} ({now})")
    pg.evaluate("(() => { LIVE.box.g1.players[normName('Past Line')].solo = 2; renderMine(); })()")
    check("LOST" not in pg.evaluate(read).get("Past Line", "LOST"), f"a stat correction back under the line clears LOST {at}")
    check(pg.locator("#mine-body > .stat-panels .stat-panel").count() == 3, f"My board shows its three panels {at}")
    probe("#mine", "My board with a game in play")
    pg.evaluate("(() => { MINE_VIEW = 'compact'; renderMine(); })()")
    probe("#mine", "My board, one line a bet")
    # the ledger: the season record on one line at the panel's size, last week's fold with what was wagered and won
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
    pg.evaluate("document.querySelectorAll('#mine details').forEach((d) => { d.open = true; })")
    pg.wait_for_timeout(250)
    probe("#mine", "My board with the ledger and every dropdown open")
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
            browser.close()
    finally:
        srv.terminate()
        shutil.rmtree(docs.parent, ignore_errors=True)
    print("\nALL BROWSER CHECKS PASSED" if not fails else f"\n{len(fails)} BROWSER CHECK(S) FAILED")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
