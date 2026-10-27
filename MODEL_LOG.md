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

**Where the wins come from (owner, 2026-10-26): an edge the market has not seen or is not pricing.** The
model's job is to know something the book does not: a stadium crew that splits tackles differently, a backup
stepping into a vacated role, an outlier game the line overreacts to, a defence that will be on the field more.
So no grade, lock or parlay may be sourced from the book's opinion. The book's price is what we bet *against*;
it is used to compute the expected return and, in the projection blend, to keep our claimed edges honest. It is
never an input that makes a pick look better because the book agrees with it. Agreement with the market is not
evidence; disagreement backed by our own evidence is the product.

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

1. **Projection.** Season-to-date tackles per game shrunk toward last season (or a position prior) with a
   position-specific weight (LB 0.5 games, S 1, CB 3, DL 3), times: a small point-spread tilt, a stat-crew factor
   for the venue, a role bump when a regular at the position group is out, a **snap-share trend** factor (last 3
   games vs season, damped), a **tackle-opportunity volume** factor (expected opponent carries + completions +
   sacks vs what the player has faced, damped and capped), a **depth-chart** factor (demoted x0.90, promoted
   x1.02), **PFR** factors (coverage targets for DBs, missed-tackle rate), a **run/pass mix** factor from
   play-by-play, and a **bye-week** factor (x0.96). A level calibration from the backtest (about 1.0) is applied. Count distribution tighter or looser than Poisson per position, re-estimated daily by the backtest.
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

## Research: where the model was missing (2026-10-26, evening MDT)

Question from the owner: what are we not using that predicts tackles? Method: one leakage-free table of 36,379
defender-games 2023-2026 with every candidate feature computed from prior games only; 28,781 test rows (2+ games
of history, week 3+); anything with a fitted parameter was fitted on 2023-24 and scored on 2025-26. Scripts are
in the session scratchpad; the adopted pieces are reproducible from the daily backtest's ablation rows.

### Adopted (validated, now in the model)

1. **Playing-time trend.** Snap share over the last 3 games vs the season share. Residual ratio actual/model ran
   from 0.70 (share down 20+ points) to 1.25 (up 20+ points); the model only used snaps for the role signal. As a
   multiplier, rises want exponent 0.45 (ratio 1.12 -> 1.00 on rows up 10%+) and drops a gentler 0.35 (0.45
   overcorrected them). Out of sample: MAE -0.95% with the shrink change; backtest ablation: removing it costs 0.36%.
2. **Tackle-opportunity volume.** Opponent carries + completions + sacks is the number of plays that end in a
   tackle. Defences that have faced few so far go on to face more (regression to the league mean), and a season
   average bakes the past volume in. Expected opportunities (defence's faced average and the opponent's generated
   average, each shrunk 4 games toward last season) vs the player's own faced average, power 0.5, capped at +/-10%
   because the extreme adjustments were wrong (ratio 1.00 -> 0.95 on the most-moved rows). Ablation: 0.25%.
3. **Shrinkage by position.** Linebackers are best predicted almost unshrunk (k 0.5), safeties at 1, corners and
   linemen pulled hard toward last season (k 3). MAE by group fell 0.6-1.0% out of sample. Ablation: 0.54%.
4. **Level calibration.** The full model ran 1.5-3% high overall (most of it on games where no new factor
   applied). The backtest now returns a scale (0.986 today) applied to the projected means.

Combined, on all 28,781 test games: full model MAE 1.679 -> 1.659 (-1.2%), RMSE 2.225 -> 2.197. Every ablation
row is worse than the full model.

### Measured and not adopted (do not retry without new data)

5. **Role bump size.** Flagged backups beat the model by 15-18% even after the 10% bump (1,204 games), and by 52%
   when their own snaps jumped 30%+. But raising the bump to 1.2-1.35 worsened out-of-sample MAE, and the snap
   trend now captures the jump. Kept at 1.10; re-measure after 4 weeks with the snap trend live.
6. **Opponent run/pass mix by position.** Fitted per +10 points of opponent run share: DL +8.5%, LB +6%, CB -4.8%,
   S -1.4%. Logical, but no out-of-sample gain (+0.09% MAE). Candidate for a second look with another season.
7. **Indoor games.** CB +3%, LB -4% fitted; test gain 0.06%. Not worth a parameter.
8. **Weather.** Wind 15+ mph: DL +3%, CB flat; temperature 40F or below: DL +2%, CB -2%. No test gain. Rejected.
9. **Point spread and total.** The current tilt slightly overshoots (underdog rows 0.98, favourites 1.005) but
   removing it costs 0.04% MAE. The game total shows nothing. Leave as is.
10. **Home/away, division games, rematches, week of season.** Ratios 0.986-1.000. Nothing there. Rejected.
11. **Recency weighting** (exponentially weighted average, half-life 3/5/8 games). -0.2% at 8; overlaps with the
    position shrinkage. Not adopted; candidate.
12. **Player-level dispersion.** Per-player variance shrunk to the position value had worse likelihood than the
    position value at every shrinkage tried. Rejected: keep phi by position.
13. **Opponent yards after catch** (for DB tackles). Nothing. Rejected.
14. **Rate per snap x expected snaps** as a full replacement for the average: worse alone (+1.7% MAE), useful only
    as a 30% blend (-0.5%); superseded by the snap-trend factor.

### Open avenues (need data we do not load yet)

15. **Play-by-play opportunity model**: tackles per opponent play while on the field, split run/pass, with
    participation data. Would replace the volume proxy with the real thing and give per-player run/pass rates.
16. **Opponent offensive injuries** (starting RB or QB out) as drivers of run/pass mix and plays.
17. **Official depth charts** (`nflreadpy.load_depth_charts`) to project snaps for a newly promoted starter before
    his first start, instead of waiting for one game of evidence.
18. **Game-script plays model**: expected plays from win probability rather than a flat spread tilt.
19. **Solo-share crews with multi-season venue pooling and neutral-site handling**: crew unknown overseas, so
    downgrade solo picks at neutral sites or treat them at league share.
20. **Two-season player prior** weighted by games, instead of last season only.

## Research round 2: five new data sources (2026-10-27, MDT)

Same method as round 1, on top of the round-1 model: 36,424 defender-games, 28,824 scored, fitted 2023-24,
scored 2025-26, then joint least squares so the pieces do not double count. Sources inventoried: play-by-play,
participation, depth charts, weekly rosters, FTN charting, PFR advanced defence, injuries (all seasons), schedule
rest days, team EPA. Participation data ends with 2025 and cannot be used live.

### Added to the pipeline (all five now loaded daily)

1. **Depth charts** (`nflreadpy.load_depth_charts`, two formats). A player **demoted** below starter on the latest
   chart ran 17% under the model over 397 games (test years 7%); promoted +7% (train fit +3%). Factors: demoted
   x0.90 (damped from the -20% joint fit, which overcorrected the test years), promoted x1.02. Status is shown on
   each card. Also used to keep projecting a starter who has missed four or more weeks and is listed again.
2. **PFR advanced defence** (`load_pfr_advstats`, type def). Two signals: DBs rarely targeted in coverage beat the
   model (10% at 2 or fewer targets a game, -6% at 6+): factor 1 - 0.065 x (target rate vs typical DB), capped
   0.85-1.12. Players with high missed-tackle rates beat it (+11% above 25%): being around the ball is the signal:
   factor 1 + 0.22 x (missed rate - 10%), capped 0.95-1.12.
3. **Play-by-play** (`load_pbp`, 18 columns selected). Each player's tackle credits on run plays and on pass plays,
   the run plays and completions each defence faced, and each offence's most-used passer and rusher. The run/pass
   **mix factor** compares the opponent's expected mix with what the player has faced, through his own rates:
   damped (weight 0.3, power 0.5, capped 0.85-1.15). The split model alone was 6.5% worse than the full model, so
   it is a correction, not a replacement.
4. **Rest days** (schedule `home_rest`/`away_rest`). A defence off a bye ran 3-4% under its average in both halves
   of the data: x0.96. Short weeks showed nothing. Shown on cards.
5. **Opponent starters out** (injuries x play-by-play starters). The opponent's starting QB or lead rusher listed
   out or doubtful is shown on cards as context. Not a factor: the fitted effect (-6 to -9% for LB/S/DL) pointed
   the other way on the test years.

Backtest with all five: full model MAE 1.6586 -> 1.6507 (round 1 was 1.6792 -> 1.6586); every new ablation row
is worse than the full model (depth +0.0013, mix +0.0014, rest +0.0023, PFR +0.0025). Level scale 0.996.

### Measured and not adopted

6. **FTN box counts** (`load_ftn_charting`): a defence's box-count tendency lifted corners (+8.5% per extra box
   defender fitted) and linebackers, but no out-of-sample gain in the joint fit. Not loaded.
7. **Weekly rosters** (years of experience): rookies run 3-8% under the model through week 10 and above it late;
   no out-of-sample gain. Not loaded.
8. **Opponent offensive EPA and first downs**: nothing beyond the volume factor already in the model.
9. **Short weeks** (4 days' rest), own or opponent's: nothing.
10. **Promotion on the depth chart** as a factor: +2% only; kept as a tag.

### Pitfalls found this round

- A factor that comes out undefined for some rows makes the projection undefined, and the backtest then scored
  the full model on a different subset of games than its ablation rows, so the full model looked worse than
  "without X" by 0.03. Every factor now fills undefined with 1.0, missing play-by-play credits are zero, and the
  backtest scores an undefined prediction instead of dropping it.
- Depth charts changed format in 2025 (dated snapshots with `pos_rank`, versus `depth_team` per week before), and
  the old format has rows without a week.

**Week 7 replayed under this model**: Sunday locks 2-3, Monday locks 2-0, all plays 96-92
(+5.3 units); Sunday parlay Loss, Monday parlay Win.
Live Monday night: lock Kenny Clark Under 2.5 won; all four Monday picks won.

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

### 2026-10-27, afternoon MDT (five new data sources in the model)
- See research round 2 above. New loaders in `pipeline/sources.py`: `load_depth_charts`, `load_pfr_def`,
  `load_pbp_tackles`; `load_schedule` carries rest days; `load_injuries` carries player ids. New config:
  `DEPTH`, `PFR`, `MIX`, `REST`. New backtest ablation rows for each. Cards show Promoted / Demoted / Opp QB out /
  Opp RB out / Off a bye / Short week tags. Revert condition: any new ablation row beating the full model two
  weeks running on the daily backtest.
- Daily job now loads play-by-play for four seasons (about 70 s total run; was 15 s).

### 2026-10-27, morning MDT (pull slots served once, not matched to the minute)
- The Monday 5:30 pm pull was missed: GitHub ran the half-hourly job at 5:03 and 5:54 (its cron drifts up to
  25 minutes and skips some half-hours), both outside the 14-minute match window. A slot is now served by the
  first run after its time, once; served keys live in `data/cache/pull_slots.json` (committed by the job).
  International windows work the same way: once in the hour before 12 h out, once in the hour before 1 h out.
- Pitfall: never match a GitHub cron run to a time; match "has this slot been served yet".

### 2026-10-26, evening MDT (lock floor, parlay removal)
- A lock needs a lock score of 55+ (grade B or better; `LOCK_MIN_SCORE`). On a two-player Monday board the top
  three were C grades flagged as locks, which is not what a lock means. Fewer locks beats fake ones.
- An open slate's parlay is re-chosen from scratch at every pull; if the board no longer supports one, the old
  parlay is removed rather than left showing (it was lingering with a leg under the 55% floor).

### 2026-10-26, evening MDT (model: snap trend, opportunity volume, shrink by position, calibration)
- See the research section above. New config: `SHRINK_GAMES_BY_GROUP`, `SNAP_TREND`, `VOLUME`. New loader
  `sources.load_team_volume` (nflverse team weekly stats; synthetic fallback). The daily backtest has ablation
  rows for snap trend, volume and single-shrink, and returns a level `scale` stored in `model_state.json`.
- Full model MAE 1.679 -> 1.659 on 28,781 games. Revert condition: any ablation row beating the full model on
  the daily backtest for two weeks running.
- **Week 7 replay under the new model and the model-only grade: Sunday locks 1-4, the Sunday parlay lost.** The
  locks it now picks are all solo Unders where the model sits far below the line (Queen, Abdul Carter, Anzalone,
  Lenoir, Elliss). Five picks is noise, but it is the profile the week 7 post-mortem flagged: our largest
  disagreements with the book were the least reliable. Watch the live by-grade table; the standard stands.

### 2026-10-26, afternoon MDT (lock score rebuilt from model evidence only)
- Owner's principle recorded in the vision: wins come from edges the market has not priced; nothing is graded
  by the book's opinion. The lock score's 40% "market agreement" component is gone. New weights: 35% expected
  return, 25% the model's own probability for the side, 20% game-log consistency, 10% games of data, 10% for a
  role-change or outlier-fade signal. `LOCK_MODEL_FULL` 0.75.
- Evidence note, kept for honesty: in week 7 picks the book also favoured hit 60% and picks against it 45%, which
  is why the old score leaned on agreement. The owner's call is that the project exists to find what the market
  misses, so the grade must measure our evidence, not theirs. Watch the by-grade table: the standard for the
  new score is that A beats C over 150+ graded picks.
- Open picks (game not started) now have their lock score, grade and evidence refreshed from the board at every
  pull, so the current formula and latest game logs apply; the logged price stays as first taken.
- The 60% line weight in the projection stays. It is calibration, not deference: without it the model claimed
  62% and hit 53%; with it, claimed 56% and hit 55%. It makes the model's disagreements honest in size; it does
  not decide which side we take or how a pick is graded.

### 2026-10-26, afternoon MDT (name, grading legend)
- Site titled "Arvell's Stinky Slammer Model" with the week as a subtitle.
- A legend above the picks shows each grade's lock-score cutoff, a suggested stake (A 1 unit, B 0.5, C 0.25 or
  pass; `GRADE_UNITS` in config), what the grade means, and how the score is built. It reads the cutoffs and
  weights from `meta.json`, which the daily job writes from config, so it cannot drift from the formula.
- Locks box renamed from "This week's five" to "Locks" with the slate day(s) named.

### 2026-10-26, afternoon MDT (parlay edge shown)
- Parlay boxes show the book's implied chance (1 / combined decimal odds, so including the vig) beside the model's
  chance, the edge in percentage points and the expected return; each leg shows model vs book (no-vig market
  probability where saved, else the price's implied chance). `mkt_side` is now saved with every parlay leg.

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
- A parlay is only recommended when at least two legs have a blended chance of 55%+ (60%+ preferred). On a thin
  board (two players posted for Monday night at midday) no parlay is shown rather than a coin-flip pair.
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
- GitHub scheduled runs drift by up to half an hour and some are skipped; a job that keys off "is it 5:30 now"
  misses slots. Key off "has the 5:30 slot been served" instead.
- The smoke test copies the repo into a temp dir; it must skip live data (`data/odds/<season>`, `data/picks.csv`,
  `data/cache`, `data/parlays.csv`, `data/retro_five.json`, `docs/data/*.json`) or the synthetic run appends to real
  picks and parlays and the checks fail (fixed 2026-10-26; recurred when parlays.csv first appeared). Any new live
  data file must be added to that list. Also: chain a push on the test's exit code, never on a grep of its output.
- The daily job runs at 7:30 am Eastern; Sunday's box scores are in nflverse by then, Monday night's are graded
  Tuesday.
