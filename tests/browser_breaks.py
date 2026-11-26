"""Does the browser test catch what it is for? Break the page one known way at a time and confirm it fails on each.

    python tests/browser_breaks.py SITE_FOLDER [words of one break]

SITE_FOLDER is the synthetic site the smoke test writes (SMOKE_SITE_OUT). Each break below is a defect that reached the
owner in week 10 (2026-11-15 and 16), put back by undoing its fix in a copy of docs/index.html. Run it by hand after
changing tests/browser_test.py; it is not part of the Test workflow (seven browser runs). A break whose text no
longer matches the page stops the run: update it with the page.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
site = sys.argv[1]
src = (ROOT / "docs" / "index.html").read_text()
M_ALL = {
 "the live card prints [object HTMLElement]": [("...(liveN ? [units(e.units_at_stake, 1), `u on ${num(e.staked, 1)} staked`, e.pending ? ` · ${e.pending} pending` : \"\"] : [`Its first picks are week ${lw}'s. This is the number that counts.`])),", "liveN ? [units(e.units_at_stake, 1), `u on ${num(e.staked, 1)} staked`, e.pending ? ` · ${e.pending} pending` : \"\"] : [`Its first picks are week ${lw}'s. This is the number that counts.`]),")],
 "an opened pick squeezed into the grade column": [("table.plays-compact > tbody > tr.mine-expand > td, table.plays-compact > tbody > tr.mine-expand > td:first-child { width: auto; white-space: normal; box-shadow: none; }", ""), ("table.plays-compact > tbody > tr > td:first-child { width: 48px; }", "table.plays-compact td:first-child { width: 48px; }")],
 "the season record stacked in small type": [(".stat-panel .tile > span { display: block;", ".stat-panel .tile span { display: block;")],
 "noon games filed under Afternoon": [('h < 14 ? "early" : h < 18 ? "late"', 'h < 12 ? "early" : h < 17 ? "late"')],
 "a stale grade on My board": [("if (x && ((x.grade || null) !== (b.grade ?? null) || (x.lock ?? null) !== (b.lock ?? null)))", "if (false)")],
 "the why table mangled inside an opened pick": [("  table.mine-compact > tbody > tr { display: grid;", "  table.mine-compact tr { display: grid;"), ("  table.mine-compact > tbody > tr > td { border: 0; padding: 0; white-space: nowrap; }", "  table.mine-compact td { border: 0; padding: 0; white-space: nowrap; display: block; }"),
   ("  .play .why-box table, .play .why-box tbody { display: block; } .play .why-box thead { display: none; }", ""), ("  .play .why-box tbody tr { display: grid; grid-template-columns: minmax(0, 1fr) auto; column-gap: 10px; padding: 5px 0; border-bottom: 1px solid var(--line); }", ""),
   ("  .play .why-box tbody td { padding: 0; border: 0; color: var(--ink); } .play .why-box tbody td:nth-child(3) { grid-column: 1 / -1; color: var(--muted); font-size: 0.82rem; }", "")],
 "a long file name pushing the Patch log off a phone": [(".patch-body code { overflow-wrap: anywhere; }", "")],
 "the tab bar sliding off a phone again": [("  nav { display: grid; grid-template-columns: repeat(5, 1fr); gap: 0; margin: 12px 0 12px; }", "  nav { display: flex; flex-wrap: nowrap; overflow-x: auto; margin: 12px 0 12px; }")],
 "yesterday's result carried into today's banner": [("if (isToday) { daySettled += result; dayN++; }", "{ daySettled += result; dayN++; }")],
 "the page opening on the last tab, not My board": [('  show("mine");                 // always My board, whatever tab the last visit ended on', '  show(location.hash.slice(1));')],
 "a settled custom bet left out of Settled": [("    groups.post.push(c); }", "    customOpen.push(c); }")],
 "a sleeper shown with no grade on My board": [("  if (sg) out.append(el(\"span\", { class: `grade sl ${sg}`,", "  if (false) out.append(el(\"span\", { class: `grade sl ${sg}`,")],
 "a sleeper added to the board on the engine's side": [("addButton({ ...b, side, pick: side, grade: isPick ? b.grade : null, lock: isPick ? b.lock : null })", "addButton(b)")],
 "a pick's sleeper grade hidden": [("  if (sg) out.append(el(\"span\", { class: `grade sl ${sg}`, title: b.grade ?", "  if (sg && !b.grade) out.append(el(\"span\", { class: `grade sl ${sg}`, title: b.grade ?")],
 "choosing a book opening the card": [("  pill.addEventListener(\"click\", (e) => e.stopPropagation());", "")],
}
M = {k: v for k, v in M_ALL.items() if len(sys.argv) < 3 or sys.argv[2] in k}
ok = True
work = Path(tempfile.mkdtemp())
for name, reps in M.items():
    t = src
    for a, b in reps:
        assert t.count(a) == 1, (name, a[:60])
        t = t.replace(a, b)
    f = work / "broken.html"
    f.write_text(t)
    r = subprocess.run([sys.executable, str(ROOT / "tests" / "browser_test.py"), site], env=dict(os.environ, BROWSER_TEST_PAGE=str(f)), capture_output=True, text=True)
    fl = [l for l in r.stdout.splitlines() if l.startswith("FAIL")]
    print(("CAUGHT " if fl else "MISSED ") + name + (f": {fl[0][:170]}" if fl else ""), flush=True)
    ok &= bool(fl)
print("every break caught" if ok else "SOME BREAKS MISSED")
sys.exit(0 if ok else 1)
