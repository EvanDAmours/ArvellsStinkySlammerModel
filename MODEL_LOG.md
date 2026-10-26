# Model log

## Vision (set by the owner, 2026-10-26)

The product is the most comprehensive resource for betting on NFL tackles. That means three things, and every
change is judged against all three:

1. **A site that is easy to use** and shows what matters without digging.
2. **Automatic updates at the right times**: fresh stats every morning, fresh lines as books post them and again
   after inactives, grading the morning after.
3. **The most accurate picks**, with the standard being **at least five picks per NFL week that are as close to
   certain as a tackle prop can be**: the "weekly five", five locks a week that the model is nearly certain will
   hit.

No tackle prop is a guarantee, so the weekly five is run as a measured target, not a promise: the five highest
lock-score picks of the week (one per player) are named before kickoff, pinned at the top of the site, and their
record is tracked on its own. The season-long standard for the weekly five is a 70%+ hit rate. If it falls short,
the lock score and the pick rules are what gets changed, in that order. Before any change is pushed, answer:
does it make the site easier, the updates timelier, or the weekly five more reliable? If none, don't push it.

## About this file

**Dates and times in this log are Edmonton local time** (MDT or MST, whichever is in force on that date), and
every schedule in the project is defined in Edmonton time. Earlier entries from 2026-10-23 to 2026-10-26 were
written against UTC timestamps; from 2026-10-26 (MDT) onward they are local.

The memory of this project. Every change to the model, the pipeline, the schedule or the site is recorded here
with the evidence behind it, and every idea that was tried and rejected is recorded so it is not tried again by
accident. **Read this file before changing anything. Append to it after changing anything.** A change that is not
in this log did not happen.

Losing picks are not mistakes. Tackle props are high-variance and a good bet loses often. A mistake is a change
made without evidence, a change not tested, a change not recorded, or a known pitfall repeated. This file exists
to prevent those.

## How the model works (current)

1. **Projection.** Season-to-date tackles per game shrunk toward last season (or a position prior), a small
   point-spread tilt, a stat-crew factor for the venue, and a role bump when a regular at the position group is
   out. Count distribution tighter or looser than Poisson per position, re-estimated daily by the backtest.
2. **Pricing (changed 2026-10-26).** The mean used to price a line is `0.4 x projection + 0.6 x consensus line`
   (`LINE_WEIGHT`). Expected return is computed from that mean against the no-vig market price.
3. **Picks.** A side is a pick when its expected return clears `PICK_BAR` (6%), or `SIGNAL_BAR` (4%) with a
   role-change or outlier-fade signal, the player is not flagged on the injury report, and he has at least 3 games.
4. **Grade (added 2026-10-26).** Every priced line gets a 0-100 lock score and an A/B/C grade from expected return,
   market agreement, how often the player cleared the line this season, and games of data. Logged with every pick
   and summarised by grade on the Track record tab so the grade itself is tested.
5. **Grading.** Picks are graded against official box scores the next morning, with closing-line value.

## Validation protocol (do this before pushing any model change)

1. `python tests/smoke_test.py` must pass.
2. Re-price the most recent graded week offline with the change and compare picks, hit rate, units and
   calibration (model side-probability vs hit rate) against the current rules. The script pattern is in the
   2026-10-26 entry below. One week is noise, so a change needs a reason beyond "it scored better this week".
3. For projection changes, check the daily backtest table (`docs/data/backtest.json`): the full model must not get
   worse than the season-average predictor.
4. Record the change here: date, what, why, evidence, and what would make us revert it.
5. Never fit a parameter to the same week used to judge it and call it validated. Mark it provisional.

## Weekly post-mortems

### Week 7, 2026 (first live week; graded 2026-10-26)

Scope: 194 logged lines (131 unique player/market/side), Thursday to Sunday games. Original rules.

Results: 102-92, +0.09 units, breakeven. Unique picks 67-64, -0.9 units.

What the numbers said:
- **Calibration was the failure.** The model claimed 62% on average on its sides and hit 53%. The 70-80% bucket hit
  55%. Picks with claimed expected return above 30% hit 42%. Regressing hit rate on the model's disagreement with
  the market gave a weight of 0.03: the size of the model's edge over the market predicted almost nothing.
- **The line is a better forecast than the projection.** Across unique picks, actual = 0.44 x projection +
  0.60 x line. The line's absolute error was lower than the projection's in both markets.
- **Market agreement mattered.** Picks on the side the market also favoured (price shorter than even): 60% and
  +2% per bet. Picks against the market: 45% and -5% per bet.
- **The outlier-fade signal worked**: 16-5, +8.8 units. Role-change signal: 0-3 (too few to judge).
- **By market and side**: solo Unders 49-27 (+15 units); solo Overs 8-15; combined Unders 25-31 (-7.9 units) with
  players beating our projection by +0.95 on average; combined Overs 20-19.
- **Not the cause**: snap-share changes (same for winners and losers), games of history, blowouts (small
  effects, inconsistent sign).
- **Consistency** (share of a player's prior games that would have cashed) did not predict wins this week.
- The 13 picks recommended in chat before Sunday went 4-9. Mostly variance on large-edge lines: McKinney 10 vs
  4.0 projected, Rodriguez 4 vs 10.7, Queen 7 solo vs 2.0.
- Solo-tackle splits in the data are correct (verified against ESPN's official game log for Patrick Queen).
  Venue crews do differ a lot on solo share (sd 0.047 vs 0.024 expected from chance; 9 of 33 venues significant),
  and Saints-Steelers was at a neutral site, where the crew factor is unknown and set to 1.

What changed because of it: see the 2026-10-26 changelog entries. What did not change: the projection model
itself, the signals, the bars' structure, the crew model.

Re-pricing week 7 closing lines under the new rules: 91 picks, 50-41, +11.8 units, claimed 56% vs hit 55%.
Partly in-sample (the 0.6 line weight came from the regression on the same week), so this is a sanity check, not
proof. The old rules on the same lines: 116 picks, 59-57, -3.1 units.

## Changelog

### 2026-10-23
- Imported the tackle model into the repo; default branch is `claude/sleepy-bell-wot0ys`.
- Found that a Codespaces secret does not reach Actions; `ODDS_API_KEY` moved to an Actions secret.
- Added per-game logging to the odds puller (status, books found, cost, credits left).
- Capped full-slate pulls at 96 hours: the events feed lists two weeks of games, which doubled credit cost.
- Added `PARLAY_API_KEY` as a second pooled key. **It is rejected by The Odds API as invalid (401) on every run.**
  Until the secret's value is fixed, only `ODDS_API_KEY` (500 credits/month) is in use.
- Keys are used in config order: first key until it drops below 25 credits, then the next. No game is fetched twice.
- Restricted pulls to Alberta-licensed books that the API carries (`ODDS_BOOKMAKERS`): BetMGM, BetRivers, Sports
  Interaction (Canadian feeds), DraftKings, FanDuel, Caesars, theScore Bet, Bally Bet, BetVictor, Betway. In practice
  only DraftKings, theScore Bet and Bally Bet have posted tackle lines so far.

### 2026-10-24
- Three Saturday full-slate pulls (9 am, 2 pm, 10 pm Mountain). Credit use is now ~700/month: needs the second key.

### 2026-10-25
- Site: slate filter (early 11 am / afternoon 2 pm / prime time, Edmonton time) on Plays and Projections; kickoff
  time on each card.

### 2026-10-26 (vision and the weekly five)
- Vision recorded above. **Weekly five** added: at every line pull, the five highest lock-score picks of the week
  (one per player, among games not yet kicked off; a pick whose game has started keeps its place) are flagged
  `five` in `data/picks.csv`, shown in a pinned block at the top of Plays, and reported as their own record on the
  Track record tab. Target: 70%+ hit rate over the season. First measured week: week 8.
- **Running tally of the weekly five**: `data/weekly_five.md` is rewritten by the daily job with the record to date,
  a line per week with the running record, and every pick with its result. The site shows the same tally in the
  five box on Plays ("season to date 24-1") and as a per-week table on Track record.

### 2026-10-26, afternoon MDT (pull schedule in Edmonton time, international games, Projections day filter)
- **Pull schedule rewritten** (owner's spec): Thu 9:00 am / 2:00 pm / 5:30 pm for Thursday and Friday games;
  Fri 6:00 pm for Saturday games when there are any; Sat 9:00 am (Saturday and Sunday games) and 6:00 pm (Sunday
  games); Mon 9:00 am / 5:30 pm for the Monday game. Slots live in `PULL_SLOTS` in `run.py` in Edmonton local time;
  the workflow runs every half hour and `--auto` does nothing unless within 14 minutes of a slot, so the clock
  change needs no cron edits. **No Sunday pulls are in this spec**: Sunday locks and the Sunday parlay are placed on
  Saturday 6 pm prices and inactives (announced 90 minutes before kickoff) are not captured. Flagged to the owner.
- **International games**: nflverse marks overseas games as neutral site. The daily job writes this week's games
  with kickoff and an international flag to `data/cache/games.json` and the site header; cards carry an
  "International" tag; the half-hourly job pulls that game alone 12 h and 1 h before kickoff.
- Projections tab: day buttons (Thursday to Monday, greyed when there are no games that day); Sunday opens the
  early / afternoon / prime-time slate filter.
- Credit note: a Thursday or Saturday pull with a day filter only requests games on those days; empty responses
  stay free.

### 2026-10-26 (locks per slate day, recommended parlays)
- **Locks are per slate day** (Edmonton date of kickoff): 3 on a one-game day (Thursday, Monday), 5 on a
  multi-game day. Same mechanics as before (highest lock scores, one per player, a pick keeps its place once its
  game starts). The running tally is the total of all locks. `LOCKS_PER_SLATE` in config.
- **Recommended parlay per slate day**: the highest blended probabilities on the board, one per player, 2 to 4
  legs, never a side with negative expected return; combined odds, the model's chance all legs hit (product of the
  blended probabilities), and a stake from a quarter-Kelly rule bounded to 0.1-1.0 units. Re-chosen at every pull
  until the day's first kickoff, then frozen as placed. Saved to `data/parlays.csv`, graded leg by leg (a push drops
  the leg), record on both tabs and in `data/weekly_five.md`. Replayed for week 7 alongside the locks.
- Correlation caveat: legs from the same game are allowed and treated as independent in the chance shown, which
  overstates the chance a little when legs are correlated (two Unders on the same defence). Revisit if parlays
  underperform their stated chance over 20+ parlays.

### 2026-10-26 (replay tool, locks record on both screens)
- `tools/replay_five.py --week N` replays a finished week under the current rules, pull by pull, using only what
  was known at each pull (small stated look-ahead: final injury report, phi from a backtest including the week).
  Writes `data/retro_five.json`; the daily job copies it into `results.json`; the site shows it under the locks
  record on Plays and Track record. **Week 7 replay: locks 4-1 (+1.6 units), all plays 86-72 (+15.8 units).**
  Weeks 1-6 cannot be replayed: no lines were collected before week 7. Re-run the replay whenever pricing or
  grade rules change, so the projected record always reflects the current rules.
- Site: wins green, losses red, units coloured by sign; locks and all-plays records side by side at the top of
  both the Plays and Track record tabs; the replayed record in a line underneath.

### 2026-10-26 (after the week 7 post-mortem)
- **Pricing mean blends toward the market line**: `LINE_WEIGHT = 0.6`. Evidence: the regression above.
  Revert if, over 4+ weeks, picks under the pure model (`LINE_WEIGHT = 0`, re-priced offline) beat the blend.
- **Bars lowered** to 6% / 4% because blended expected returns are much smaller than the old inflated ones.
  Provisional. Revisit after 4 weeks of graded picks.
- **`PROB_SHRINK` knob added** (default 1.0, off). Measured value this week was 0.03 but on 131 picks; left off
  because blending the mean already removed most of the overconfidence (calibration 56% vs 55%).
- **Confidence grade** (`lock`, `grade`) on every priced line and every logged pick. Weights
  ev 0.25 / market 0.40 / consistency 0.20 / sample 0.15, fade bonus 5, A at 72, B at 55. **Unvalidated**: on
  week 7 no component correlated with winning. The Track record tab shows results by grade; if A does not beat C
  after ~150 graded picks, change or drop the grade.
- The board drops lines for games that have kicked off (it was showing Sunday's lines on Monday). Snapshots are
  untouched, so grading and closing-line value still work.
- Monday pulls look 12 hours ahead (the 4-hour window missed the night game); extra Monday pull at 2 pm Mountain.
- `Pull tackle lines` can be run by hand with an `hours` input to reach a game outside the automatic window.
- Game logs (`log_comb`, `log_solo`) saved with projections so the pricer can report "cleared this line in x of n".
- Picks are sorted by lock score on the site.

## Ideas backlog

Tried and rejected (do not retry without new evidence):
- Shrinking the model probability toward the market by 0.25-0.5 on top of the blend: fewer picks and worse results
  on week 7 at every bar. The blend alone did the work.
- Consistency as a filter (cleared the line in 67%+ of games): no lift on week 7.
- Snap-share change as a miss explanation: none.

Open, with what would justify them:
- Per-venue crew factor for solo tackles with less shrinkage (`CREW_PSEUDO_TACKLES` 250 -> 100): justified if the
  backtest's solo error improves. The backtest currently only scores combined tackles; add a solo table first.
- Neutral-site games: crew unknown, treat solo lines there as C grade or skip. Needs a count of such games.
- Opponent pace / plays per game as a feature: needs play-by-play; check whether it moves the backtest.
- Alternate-line markets (`player_tackles_assists_alternate`): more lines to shop, double the credit cost per game.
- Role-change signal: 0-3 so far. Keep logging; judge at 30 picks.
- Second key: fix `PARLAY_API_KEY` so Saturday pulls stay inside the credit budget.

## Known pitfalls

- Codespaces secrets are invisible to Actions. Only Actions secrets work.
- GitHub did not register the scheduled workflows on the first push to the empty repo; a second push to the
  workflow files fixed it.
- Cron times are UTC. Alberta leaves daylight time on 2026-11-01: every cron in `odds.yml` and `daily.yml` then runs
  an hour early in local terms. Add one hour to each.
- The Odds API has no Alberta-specific feeds. Canadian feeds are Ontario-facing; prices at a book's Alberta site
  can differ. Empty responses cost nothing; every 10 named bookmakers cost as much as one region.
- The events feed lists games two weeks out. Never pull "all upcoming" without a window.
- pandas 3: `groupby(...).apply(f)` no longer passes the grouping columns to `f`; use `.agg`.
- Duplicate player names within a week (two "Mack Wilson"-type cases) break `.map` on a name index; dedupe first.
- Neutral-site games (international) are flagged `NEUTRAL` and get crew factor 1.0.
- Two jobs can run at the same moment despite the shared concurrency group when they are queued within seconds
  of each other; the second one's rebase then conflicts on generated files and its work is lost. The save step now
  keeps the job's own version of conflicting files and retries; the daily cron sits at 11:15 UTC, off the
  half-hour the pull job uses.
- The smoke test copies the repo into a temp dir; it must skip live data (`data/odds/<season>`, `data/picks.csv`,
  `data/cache`, `docs/data/*.json`) or the synthetic run appends to real picks and the checks fail (fixed 2026-10-26).
- The daily job runs at 7:30 am Eastern; Sunday's box scores are in nflverse by then, Monday night's are graded
  Tuesday.
