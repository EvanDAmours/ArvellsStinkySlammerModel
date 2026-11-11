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

**How the pricing engine of 2026-11-09 sits with this** (the owner delegated the decision that evening: "take full
creative liberty in how to make this the most rigorous model"). The claimed chance is no longer shrunk toward 50%:
it starts from the book's fair price and moves half of the way to the model's own chance. That is the use this
vision already allows ("to keep our claimed edges honest"), done with the price instead of the raw line. What the
vision forbids still cannot happen, and a test in the smoke suite enforces it. With no disagreement the chance is
the book's own and every price loses its margin, so nothing is a pick because the book agrees. A pick is chosen on
its cautious edge and graded on that edge and on the model's own chance, and neither can improve when the book
moves toward the model. The locks are ranked by the model's own chance, which does not look at the book at all.

## About this file

**Dates and times in this log are Edmonton local time** (MDT or MST, whichever is in force on that date), and
every schedule in the project is defined in Edmonton time. Entries from 2026-10-23 to 2026-10-26 were written
against UTC timestamps; from 2026-10-26 (MDT) onward they are local. Alberta stays on UTC-6 all year from
2026-11-01 ("Alberta Time": the clocks did not go back); entries from that date that say "MST" mean Edmonton local
time, six hours behind UTC.

The memory of this project, in two files since 2026-11-09:

- **MODEL_LOG.md (this file)** is read first and in full: the vision, how the model works now, the rules of
  evidence, the decision register (every live rule with its evidence and what would revert it), the
  rejected-experiments register (everything tried and dropped, one line each), the open issues, the latest research
  round and post-mortem, the changelog since the rebuild, the ideas backlog and the known pitfalls.
- **MODEL_LOG_ARCHIVE.md** is the history, moved there unchanged: research rounds 1 to 10, the audits and question
  sections, the post-mortems of weeks 7 and 8, every changelog entry through 2026-11-09, the specification that
  was replaced, and the review whose open-issues register led to the rebuild. Search it before repeating an
  experiment: the rejected register here names the round each write-up is in. One erratum covers all of it:
  **evidence quoted before 2026-11-09 was counted on the uncorrected record** (duplicate rows, late and phantom
  picks; for example "A 16-2" in the week 8 post-mortem). The corrected record is in the audit entry of that date.

Read this file before changing anything. After changing anything, append a changelog entry (date, what, why,
evidence, revert condition) and a line in the decision register or the rejected register. A change that is not in
this log did not happen. When this file passes about 1,200 lines, move the oldest changelog entries and research
rounds to the archive, unchanged. The site's Patch log tab is built from both files (`pipeline/patchlog.py`), so
keep the headings' form: "## Research ...", "### ..." under "## Weekly post-mortems", "### <when> (<what>)" under
"## The December exploration (plan; credits reset 2026-12-01, access ends 2026-12-10)

Written 2026-11-10 at the owner's request ("Dec 1 can plan for another big exploration"). A scheduled task wakes the
owner's session on 2026-12-01 at 9 am Edmonton to run it; any session can run it from this section. It measures and
logs; it changes no rule (the rules are read after week 13, on 2026-12-08, by their own conditions).

Budget: 20,000 credits from 12-01. Keep 1,500 for the live pulls of 12-01 to 12-10 (weeks 13 and 14). Check the count
first ("Check odds keys" workflow) and after every fetch. A historical snapshot costs 10 credits a market a game
(nothing when no line is posted). Fetch with the "Fetch past lines for a market" workflow (`run.py history`), one run
at a time; test with `python tools/season_test.py --season S` in a scratch copy.

In this order, each with what it would change:
1. **When to bet** (about 10,600): the 2025 season 24 hours and 6 hours before each kickoff, solo and combined, into
   `data/odds_early` (never into `data/odds`: the closing lines must stay the last snapshot). For the A and B
   picks of the replay: the price and the line at 24 h, 6 h and 1 h. Does the flagged solo Under pay more early or
   late, does the line move toward the model, and is a pick made at 24 h still a pick at the close? Decides the
   pull schedule and when the owner bets. This season's weeks 1 to 6 already say "no difference between 16 h and
   1 h" on six weeks.
2. **Alternate lines: answered on 2026-11-10, dropped.** Week 9 was sampled (`data/odds_alt`, 280 credits):
   DraftKings' alternates are Over-only ladders ("4+ tackles"), with no Under to bet the flag at, and every Over on
   them returned -5.7% (combined) and -13.8% (solo) that week. Nothing to fetch.
3. **Assists, 2024** (about 2,700): the third season for open issue 21 (the trial market's promotion).
4. **Assists at the close, 2026 weeks 7 and 8** (about 300): completes this season's scoreboard in three markets.
5. **2023** (31 to probe, about 5,300 if it is there): a fourth season for the book-share flag with no model (the
   projection has no season before 2023 to train on, so no replay). Only if credits remain after 1 to 4.
6. **Anything the live weeks 10 to 12 raise**: read "Rules on trial" and the post-mortems first; a question they
   open outranks 5.
By 12-09: spend what is left on the next item down, log the results under the changelog, and remind the owner that
the key ends on 12-10 (open issue 7).

## Changelog".

Losing picks are not mistakes. Tackle props are high-variance and a good bet loses often. A mistake is a change
made without evidence, a change not tested, a change not recorded, or a known pitfall repeated. This file exists
to prevent those.

## How the model works (current; rebuilt 2026-11-09, live from week 10)

Standing rule (2026-10-30): **a lock must come from where the model is reliable.** A player whose season history
does not describe his current role, or who may not play, can be a pick, never a lock, an A or a parlay leg.

1. **Who plays, and for whom.** Statuses come from three feeds merged per player-week, most severe wins: the
   league's weekly injury report, ESPN's injury feed, and the league's weekly roster (injured reserve, PUP, NFI,
   suspended, exempt, the week's inactives). A traded player moves to his new team when the depth chart or the
   weekly roster (a row newer than his last game) shows him there; his old team's position group gets the vacancy
   flag and, in its first game without him, the next-man-up flag for its backups.
2. **The projection** (`model.project_frame`, `model.finalize_projections`). A factor model and a second model,
   blended 40/60.
   - Factor model: two bases blended 60/40, the per-game base (season-to-date tackles per game, shrunk toward last
     season or a position prior: LB 0.5 games, S 1, CB 3, DL 3) and the per-snap base (tackles per real defensive
     snap, shrunk toward last season, x his expected snap share from a situation-aware share model x his defence's
     expected snaps). Then the factors switched on in `config.FACTORS`: next man up (x1.10 for a backup when a
     regular at his group is out), spread tilt, opponent volume (expected carries + completions + sacks against
     what he has faced), depth chart, coverage targets and missed tackles, indoors for corners, outlier damping.
     Then one level calibration from the backtest.
   - Out of the factor model since 2026-11-09, each still an input to the second model: stat crew, snap trend,
     run/pass mix, bye, injury report, role shift, the vacancy rule. The code stays and each is re-tested every
     morning (point 12).
   - Second model: a gradient-boosted corrector (Poisson loss, three seeds), trained every morning on every
     defender-game since 2023, with the factor model's number and the raw signals as inputs, the next-man-up flag
     among them. It carries 60% of the final number.
   - Solo = the combined number x his solo share (his own, shrunk toward his position's over 150 tackles since
     2026-11-10: a season of a player's own share is mostly noise; the positions' shares are CB 0.66, S 0.57,
     LB 0.49, DL 0.44) x the
     league's 3-week solo drift x a solo level per position x this season's official-count factor (the books and
     the box score count a tackle made with an assist as solo: 1.024 in 2026; the model trains on solo alone, the
     stable series). Assists = combined less solo.
3. **The spread.** Counts are negative binomial (binomial under 1) with variance = spread x mean. The spread is
   fitted by maximum likelihood around the out-of-sample final projection, per position, per class (expected at
   60%+ of the snaps or under) and per market: combined LB 1.32 / 1.38, S 1.33 / 1.43, CB 1.25 / 1.48, DL 1.08 /
   1.17; solo LB 1.18 / 1.20, S 1.18 / 1.28, CB 1.18 / 1.36, DL 1.02 / 1.08. A new role adds 0.45 (0.20 solo),
   fitted the same way; a neutral site adds 0.15.
4. **The engine: one chance per line** (`model.price_lines`, `config.ENGINE`). For every posted line:
   - the **book's fair chance**: its two-way price with the margin taken out in proportion, averaged over the books
     that quote both sides of exactly that line. A one-sided price is priced against those books; with none, the
     line is passed;
   - the **model's own chance**: from its number and spread at that line, held inside 2% to 98%;
   - the **win chance**: logit(p) = logit(fair) + w x [logit(model) - logit(fair)], with w = 0.65 on solo lines,
     0.35 on combined and 0.5 on assists (on 25 weeks of closing lines of 2025 and 2026 the solo weight is confirmed
     and nothing beats these by t 2: open issue 22);
   - the **cautious chance**: the same with half of w;
   - the return at the win chance and the **cautious edge** (cautious chance x decimal odds - 1) at this book's
     price. The side with the better return is the line's side.
5. **Pick, lean, no pick.** A pick has a cautious edge of zero or better. A lean has 2%+ at the win chance and is
   under water at the cautious one: shown, logged, never staked. Never a pick: a player ruled out or doubtful,
   fewer than 3 games of data, and an Under on a next-man-up backup the share model expects under 60% of the snaps
   (the projection runs 16% low on exactly those), a line that does not fit the player (one book alone on the
   player and market, the model's own chance 93%+: a mis-posted line or another player of the same name), and a
   solo Over on a line the book has set at 58% or more of its own combined line (item 6: decision H1).
6. **Grades and the lock score** (since 2026-11-10, noon; decision H1). The grade follows the book's own solo
   share: its solo line divided by its combined line for the same player (the consensus lines). At 58% or more the
   line is flagged (`config.HOLES`). A: a solo Under pick on a flagged line that is also a sleeper (item 11), the
   checklist clear. B: any other solo Under pick on a flagged line. C: every other pick. The size of the cautious
   edge no longer sets a grade. The lock score is the model's own chance out of 100. Combined projections carry
   the level for players who get lines (actual over projected on the season's earlier lined games; decision R7).
7. **The checklist** (never a lock, an A or a parlay leg): new role, next man up, reduced role, back from absence,
   new team, fewer than 3 games in his current role, questionable, snap counts missing for his last game, an Over.
8. **Locks.** A picks only, highest model chance first, one per player, at most 3 on a one-game slate day and 5
   otherwise, at most two of a kind (side x market x position). A slate with no A has no lock.
9. **Stakes** (`grade.size_stakes`, `config.STAKE`, mode "grade" since 2026-11-10; decision S3). The stake is the
   grade's units: A 1, B 0.5, C 0.25. Stakes are scaled down together only to stay within 5 units a game, 20 a kind
   (side x market) a slate day and 25 a slate day, which happens on about one slate day in nine. The quarter-Kelly
   stake and the divisor for like picks remain in the code (mode "kelly").
10. **Parlays.** One per slate day, 2 or 3 legs, combined tackles only (books refuse solo legs in a same-game
    parlay). A leg must be a pick, lock-eligible, with a model chance of 60%+ (56% if too few), at most two of a
    kind. The chance is the product of the legs' win chances times the same-defence correlation ratio. When two
    legs share a game the price recorded is the product divided by that ratio, flagged as an estimate.
11. **Sleepers** (frozen since 2026-11-09): solo Unders with the model 0.5+ under the line and his season median
    within a tackle of it; combined Overs with the model 0.5 to 1.0 over. Graded A/B/C from the model's own chance,
    a steady role and the game's volume; never the price. Own record, 1 unit each, never a lock. Each carries the
    engine's read of the same line at its price.
12. **The backtest** (`pipeline/backtest.py`), every morning: the final projection scored out of sample (the
    corrector trained on earlier seasons only, a fold a season) in Poisson deviance; every factor tested on the rows
    it moves, with season-weeks as the unit, for every player and for the regulars who get lines; the spread
    refitted; calibration and the shape of the distribution checked around the same projection. A factor that
    fails, or one that is out and passes, raises a flag on the site (never an automatic change).
13. **Grading and records** (`pipeline/grade.py`). ESPN's final box score settles a pick when its game ends; the
    official stats confirm overnight. **A bet settles once**: the first box score that grades it is kept
    (`data/settled.csv`), as at the book; a later stat correction is counted, not applied. One bet per player x
    market x side in every record; a pick logged after kickoff or on a line its game's board was not offering is
    void. Every record carries a likely range (a 95% interval that allows for a week's picks winning and losing
    together).
14. **The scoreboard** (`pipeline/evaluate.py`, Track record: "Against the market"). The win chance on every
    closing line the model had a number for, picked or not, scored in log-loss beside the book's own fair closing
    chance, by week. The line log (`data/lines_log.csv`) keeps the engine's read of every line so any rule can be
    scored later without having been live. The weeks since the engine's first week (`config.ENGINE_LIVE`) are
    reported by themselves: its verdict is read only there. Three candidates (`config.SHADOW`) are scored on the same
    lines against the engine and never used. The record of the engine's own weeks, with every condition of the
    decision register counted (`grade.engine_era`), is on the site as "Rules on trial". All of it is also written
    in plain text to `data/weekly_five.md`, because the site's copy is sealed and a post-mortem starts from it.
15. **Operations.** One workflow, the ticker, beats all day: the daily once after 4:15 am Edmonton, a pull at each
    slot, live grading when a game ends; a run that ends starts the next. Before each pull the odds-credit budget
    (`run.credit_budget`, `run.govern`) prices the rest of the month and keeps what is worth most per credit: the
    pull an hour before each kickoff first, then the Thursday and Monday looks, then Saturday night's, then the
    rest, then the assists market. The site is sealed behind a password; the repository is public.
16. **What a card shows.** The grade, the win chance, the cautious edge, the stake; both opinions (the model's
    number and chance, the book's fair chance and the number its price implies); the Game logic row: how far each
    signal moved the final projection, measured by rebuilding it with that signal neutral; the rundown.

## Evidence rules and the validation protocol

Rules of evidence (2026-11-09; they bind every change after this date):

1. **The week is the unit.** The picks of a week share a shock (every solo Under on the board won 68%, 64% and 53%
   in weeks 7, 8, 9). Differences are tested paired with season-weeks as clusters (`backtest.paired`); a record is
   read with its likely range (`grade.hit_interval`). A t from rows treated as independent is not evidence.
2. **Judge on who is priced.** Books post lines on regulars (expected at 80%+ of the snaps, `config.REGULAR_SHARE`).
   A projection change is decided on them, not on every defender: the corrector weight of 0.8 was better for every
   defender (t -4.5) and no better for regulars.
3. **The yardstick.** Poisson deviance for a projection (it is used as a mean; the absolute miss rewards the median
   and is reported, not decided on). Log-loss against the book's fair closing chance for a probability. No-vig
   closing-line value for timing.
4. **Out of sample, or marked provisional.** Projection pieces: walk-forward by season with the corrector retrained
   per fold. Pricing rules: on weeks not used to choose them. A number looked at on the weeks it was chosen on is
   labelled so wherever it is quoted. The engine's rules were chosen on weeks 7 to 9 of 2026; its first week is
   `config.ENGINE_LIVE` (2026 week 10). The scoreboard and the record report the weeks from there on by themselves
   ("since the engine"), and a revert condition in the decision register is read on those weeks alone.
5. **Rule 0 as a test.** At a fixed model chance, more agreement from the book must never raise what chooses a
   pick (the cautious edge) or its grade. The smoke test checks it over the whole grid.
6. **Frozen until 2026-12-08** (`config.FROZEN_UNTIL`; weeks 10 to 13). No bar, weight or cap in ENGINE, STAKE,
   FACTORS or GBM changes before then unless a defect is found (wrong arithmetic, a crash, data that is not what
   the code assumes). A candidate is tested in the shadow on the line log and written down as a candidate (open
   issues); its numbers are fixed in `config.SHADOW` before the weeks that test it, and the daily scores it on every
   closing line (decision R6). 100 changelog entries in 17 days against three graded weeks is why: no rule set had
   been left alone long enough to be measured.
7. **After the freeze, one change at a time,** each with its revert condition written before it ships.

Protocol before pushing a change to the model, pricing, bars, stakes, schedule or data sources:

1. `python tests/smoke_test.py` passes.
2. A projection change: the full test. The final projection walk-forward by season, corrector retrained, deviance,
   paired by season-week, on regulars and on everyone (the pattern is in Research round 11; `backtest.walk_forward_final`
   and `backtest.paired` are the pieces). The daily `factor_tests` table is the standing version at the factor-model
   level; its flags say when to run the full one.
3. A pricing or pick rule: score it on the line log against the book's fair close (`pipeline/evaluate.py`), weeks as
   the unit, and replay the graded weeks pull by pull through the live functions (`tools/replay_five.py`): record,
   calibration, units at the stakes.
4. Run the real daily in a scratch copy and read the board it makes. The solo-count error of 2026-11-09 and the
   missing-column crash of the rebuild were both found this way, not by the smoke test.
5. Record the change here: changelog entry, register line, revert condition.
6. Never fit a parameter to the weeks used to judge it and call it validated.
7. After the push, read the result of the Test workflow on GitHub. It runs the smoke test on a clean machine with
   only `requirements.txt` installed; a red check there is a failed push, whatever the test said by hand.

## Decision register

Every rule the model runs on: its value, the evidence, since when, and what would revert or re-open it. "Regulars":
players expected at 80%+ of the snaps. "Folds": the final projection out of sample, a fold a season (2024, 2025,
2026), corrector trained on earlier seasons only; deviance per game, t with season-weeks as the unit; negative is
better. "The closing lines": 745 lines of weeks 7 to 9, one per player and market, official box scores, the model
numbers logged at the time; these are the weeks the pricing rules were chosen on, so every figure from them is
in-sample. The full write-up is Research round 11.

**Projection**
- **P1. Two bases, 60% per game and 40% per snap.** Removing the per-snap base costs regulars +0.0138 (t +2.9, folds
  2025-26). Since 2026-10-30. Revert: the daily test calls it "hurts" and the full test agrees.
- **P2. Factors in the factor model:** coverage targets and missed tackles (removing it: +0.0058, t +2.6 for
  regulars), next man up x1.10 (+0.0016, t +1.2), spread tilt (+0.0029, t +0.9), opponent volume (+0.0017, t +0.9),
  indoors for corners (+0.0007, t +0.5; +0.0025, t +1.4 over three folds), depth chart (nothing overall, +0.034 on
  the 71 regulars it moves), outlier damping (0.0000). None hurts; at the factor-model level each earns its place on
  the regulars it moves (t -1.5 to -8.2). Revert one: "hurts" in the daily table (t at or above +2) and the full test
  agrees.
- **P3. Factors out since 2026-11-09:** stat crew (adding it back: +0.0024, t +1.4 for regulars), bye (+0.0022,
  t +1.4), injury report (+0.0025, t +1.3), role shift (+0.0031, t +1.9), vacancy rule (+0.0047, t +1.8; +0.32 on the
  46 regulars it moves, t +2.1), snap trend (-0.0008, t -0.4), run/pass mix (-0.0017, t -1.2; +0.0012 over three
  folds). Together, with P5: regulars -0.0089 (t -2.8) and everyone -0.0077 (t -3.2) against the old design, folds
  2025-26; over all three folds -0.0024 (t -0.6) and -0.0050 (t -2.4); the 2024 fold alone, where the corrector had
  one season to learn from, +0.0064 (t +0.9) for regulars. Each stays an input to the corrector. Back in: the daily
  table calls it a "candidate" (t at or below -2 on the regulars it moves) and the full test agrees.
- **P4. Corrector weight 0.6.** Tested against 0.8: for everyone the best weight by fold is 0.5, 0.9, 1.0; for regulars
  0.4, 0.6, 0.7, and 0.8 is no better than 0.6 on folds 2025-26 (-0.0085 against -0.0089) and worse on the 2024 fold
  (+0.024, t +2.3). Since 2026-10-27, kept 2026-11-09. Re-open: a full 2026 fold in which regulars prefer 0.8 by t -2.
- **P5. The next-man-up flag is an input to the corrector.** New 2026-11-09, adopted with P3 as one design.
- **P6. Shrinkage by position** (LB 0.5 games, S 1, CB 3, DL 3), solo share shrunk over 150 tackles of the
  position's share (CB 0.66, S 0.57, LB 0.49, DL 0.44; 25 tackles and 0.72, 0.62, 0.52, 0.45 until 2026-11-10, 11 am:
  changelog. Back to 25 if the solo deviance on regulars is worse with it over the 2026 season's remaining weeks by
  t +2, or the engine's solo margin over the book on weeks 10 to 13 is worse than the old share's on the same lines),
  league solo drift
  over 3 weeks, solo level per position, the official-count factor (1.024 in 2026, refreshed every morning). Rounds 1
  to 5 and the 2026-11-09 solo-count entry (archive). Re-open with a full extra season.
- **P7. The spread is fitted, not set:** maximum likelihood around the out-of-sample final projection, by position,
  class (60%+ or under) and market, refitted every morning; the new-role addition too (0.45 combined, 0.20 solo). It
  had been 1.57 for linebackers and 1.45 for safeties (now 1.32 and 1.33). The distribution's tails: 5.3% below its
  5th percentile, 4.7% above its 95th. Neutral site +0.15 is a setting (too few games to fit). Since 2026-11-09.

**Pricing**
- **E1. The book's fair chance:** proportional no-vig, averaged over the books quoting both sides of the same line.
  The proportional split is off by about a point at very short or long prices (open issue).
- **E2. Win chance = fair chance moved 0.5 of the way to the model's, in log-odds.** The closing lines: fitted weight
  +0.53 (se 0.20); log-loss 0.6823 against the book's 0.6898, the model alone 0.6865, the old raw-line blend 0.6827;
  better than the book in each week (+0.004, +0.013, +0.005). Honest limits: on solo lines the old blend scored
  better (0.6716 against 0.6753) and on combined the engine barely beats the book (0.6894 against 0.6918); with the
  rebuilt projection's own numbers the margin over the book is +0.0044 (t +1.0). Since 2026-11-09, provisional.
  Revert toward the book (a smaller weight) if the scoreboard's margin is negative by two standard errors after
  week 13; raise only by the same test.
- **E3. Cautious chance = the same at 0.25; a pick has a cautious edge of zero or better; a lean has 2%+ at the win
  chance.** The closing lines: picks 68-45 (60%, +17% a bet); cautious edge 0 to 2%: 37-25; 2%+: 31-20; leans 72-68
  (-1.3%); no pick 264-228 (+0.1%). Provisional (round numbers, looked at on those weeks).
- **H1. The grade follows the book's own solo share; no solo Over pick on a flagged line.** Since 2026-11-10, noon,
  on the owner's go-ahead ("take creative liberty... do whatever you think is best"); it replaces E4 and the A rule
  of R7. A: a solo Under pick on a line the book set at 58%+ of its own combined line, also a sleeper, checklist
  clear. B: any other solo Under pick on such a line. C: every other pick. Evidence: the flag itself is confirmed
  out of sample twice (176-103 on 2026 weeks 1 to 6, 609-363 on 2025, after it was found on weeks 7 to 9); replayed
  on 21 weeks, A 106-35 (75%), B 210-106 (66%), C 621-428 (59%), in that order in each of four stretches, where the
  cautious edge ordered nothing (B 60%, C 60%); the engine's solo Over picks on flagged lines 8-19, losing in each
  stretch. The B and C definitions were drawn on those same 21 weeks: in-sample. Revert, read on weeks 10 to 13
  and on at 30 A, 40 B and 100 C picks ("Rules on trial"): A under 60% or not ahead of B and C, back to the sleeper
  rule (`a_rule="sleeper"`); B not ahead of C, B and C become one grade; C under 52.4%, C picks become leans.
- **E4 (replaced by H1). Grades: B at a cautious edge of 2%+, A with a model chance of 70%+ and a clear checklist.** The closing
  lines: 13-6. Replay of weeks 7 to 9: A 10-6, B 20-21, C 73-58: the order is not there yet (ranges overlap).
  Built only from numbers that cannot improve with the book's agreement (rule 5 above). Provisional.
- **E5. The lock score is the model's own chance; locks are A picks, highest first,** 3 a one-game slate day, 5
  otherwise, two of a kind at most; solo and combined; never an Over; never assists. Replay: locks 6-4. The
  solo-only rule of 2026-11-08 was lifted with the pricer that caused it (combined Unders with a cautious edge of 2%+
  went 14-6 at the closing lines).
  Back to solo only if combined A picks hit under 55% over their first 20.
- **E6. Overs are picks under the same test and never locks.** Live 28-40 before the engine; picks at the closing
  lines 6-9; tackle Overs in the replay 15-20. No separate weight for Over disagreements: +0.18 (se 0.62) against +0.63 (se 0.27) for
  Unders is not a difference. Re-read at 40 further Over picks.
- **E7. Next man up:** never a lock or an A, and his Under is not a pick when the share model expects him under 60%
  of the snaps. Out of sample the final projection runs 12% low on next-man-up backups (918 games), all of it on
  those expected under 60% (16% low, +0.43 tackles, t +3.3 on 710 games; the 208 expected at 60%+ are level; measured at a
  corrector weight of 0.8). New
  2026-11-09. Lift when a correction for it passes the full test.
- **E8. Not a pick:** out, doubtful or on a reserve list; fewer than 3 games.

**Stakes and parlays**
- **S3. The stake is the grade's units: A 1, B 0.5, C 0.25,** with caps of 5 units a game, 20 a kind a slate day
  and 25 a slate day as a safety net. Since 2026-11-10, noon (owner's go-ahead, as H1); it replaces S1 and S2. On 21
  replayed weeks the Kelly stakes returned what one size did (+19.9% against +20% a unit) and lost on 2026 weeks 4
  to 6 where flat bets won; replayed with the ladder: +131.0 units on 560 staked (+23.4%) against +143.1 on 719
  (+19.9%), a worst week of -0.1 units against -4.5, +18.8% against +6.5% on the 2026 weeks, a staked profit in 20
  of 21 weeks against 18. Fewer units are out (27 a week against 34), so the same bankroll wins a little less in
  total and risks less; a larger unit restores it. A stake is now a round number on 99% of picks. Revert to
  `mode="kelly"` if, over weeks 10 to 13, the ladder's return per unit is under the same picks' return at one size.
- **S1 (replaced by S3). A quarter of Kelly at the cautious chance, 0.1 to 3 units.** Sized on the cautious chance because no edge
  is proven: a pick that only just passes gets the minimum. Move to the win chance when the scoreboard's margin
  over the book is two standard errors positive.
- **S2 (replaced by S3). The slate as one book:** divide by 1 + (N - 1) x 0.02 per kind per slate day; caps of 4 units a game, 10 a
  kind a day, 15 a day. 0.02 is the weekly shock as a correlation (6.5 points of hit rate against a binomial
  spread of 49). Week 9 as bet: 59.9 of 100 units on one Sunday. Replay under these rules: 19.5, 20.1 and 29.5
  units a week, -0.0 units on 69.1 staked, against +17.7 at one unit a bet: the stakes did not help, because C
  picks out-hit B picks in those weeks.
- **S3. Parlays:** legs are picks, combined only, lock-eligible, model chance 60%+ (56% if short), 2 or 3 legs; a
  same-game price is the product divided by the correlation ratio, flagged as an estimate. Replay: 0-4 at 0.1 unit.

**Sleepers, records, operations**
- **R1. Sleeper rules frozen** as of 2026-11-09 (archive: changelog of 2026-11-08 and 2026-11-09). Each kind comes
  off if it hits under 55% over its next 40; the A rule is reviewed if A sleepers hit under 70% over their next 20.
- **R2. One bet per player, market and side; late and phantom picks void; a bet settles once.**
- **R3. The odds-credit budget:** the richest schedule the credits can pay for; the pull an hour before kickoff is
  the last thing to go. The Sunday 10 am look duplicates that pull since the clocks changed (the early games kick
  off at noon Edmonton now) and is the first to go.
- **R4. Frozen until 2026-12-08** (rule 6 above). Lifted once by the owner on 2026-11-09 for six named changes
  (changelog, 10 pm), before week 10 had a line. On 2026-11-10 the solo share was corrected as a defect (P6), on the
  owner's instruction to test on the season's past lines and correct what they show, again before week 10 had a
  line. Lifted again by the owner at noon on 2026-11-10 ("take creative liberty... do whatever you think is best")
  for H1 and S3, with two seasons of past lines behind them and week 10 still without a line. It stands again
  from there: the weights, the pick test, the caps and the grades do not move before 2026-12-08 unless a defect
  is found or a revert condition is met.
- **R7. Changed 2026-11-09, 10 pm, at the owner's instruction** (they amend E2, E4 and E5 above; evidence in the
  changelog, all of it in-sample):
  - *E2:* the weight is 0.65 on solo lines and 0.35 on combined (assists 0.5); the cautious chance is half of it.
    Same revert test as E2, read on weeks 10 to 13; the flat 0.5 is in the shadow.
  - *E4/E5:* an A is a pick that is also a sleeper on the same side, checklist clear; locks are A picks, the
    model's own chance highest first. It stays only if A picks hit 60% or better over their first 30 and beat B and
    C; else back to the old rule (cautious edge 2%+ and a model chance of 70%+), which is counted beside it.
  - *Combined level:* combined projections of the week times actual over projected on the season's earlier lined
    games (shrunk n / (n + 100), clipped 0.9 to 1.1). Off if that ratio falls inside 0.99 to 1.01 over four weeks
    or the scoreboard's combined margin is worse with it. Solo has no level. Since 2026-11-10 the line log holds
    weeks 2 to 6 as well (replayed on their closing lines), so the level is read on the whole season: 1.008 for
    week 10, where weeks 7 to 9 alone gave about 1.03.
  - *Misfit:* one book alone on the player and market and a model chance of 93%+ is no pick.
  - *Role news:* a pull rebuilds the projections when a player expected at 30%+ of the snaps is newly out or
    newly cleared.
- **R5. The record and the scoreboard are split at the engine's first week** (`config.ENGINE_LIVE`: 2026 week 10).
  Weeks 7 to 9 chose the rules and test nothing. The conditions of E2, E4, E5, E6 and S1 are counted by the daily on
  the weeks since (`grade.engine_era`, the scoreboard's `since` and `watches`) and shown on the site ("Rules on
  trial") and in `data/weekly_five.md`. E2 and S1 are read after week 13, on weeks 10 to 13. Since 2026-11-09.
- **R6. Three candidates run in the shadow** (`config.SHADOW`, `evaluate._shadow`), scored on every closing line and
  never used for a pick. Since 2026-11-09, 10 pm (R7): the flat weight of 0.5 that the weight per market replaced;
  the combined gap centred on the week's own mean; the level for lined players on solo lines too. Until then: a
  weight per market (0.35 combined, 0.65 solo); the centred gap; a level for lined players. On weeks 7 to 9,
  where they were found (880 lines): +0.0012 (t +1.9), +0.0009 (t +7.7: the same small gain three weeks running)
  and +0.0012 (t +1.0) of log-loss against the engine. Adoption is decided after 2026-12-08, on the weeks from week
  10 on only: the gain over the engine positive by two standard errors with weeks as the unit, and positive in at
  least three of the four weeks. One at most is adopted at a time, and the rule it replaces then runs in the shadow
  against it. Four weeks make a t of 2 a weak bar (the 95% point at three degrees of freedom is 3.2), so an adopted
  candidate is provisional. Changing a number in `config.SHADOW` restarts that candidate's test.

## Rejected experiments register

Everything measured or tested and not adopted, one line each, so nothing is repeated by accident. The round or entry
named in each line is in MODEL_LOG_ARCHIVE.md unless it is round 11 (below). Do not repeat one without new evidence
(new data, a new season, or the condition the line names). Figures from before 2026-11-09 are on the uncorrected
record where they concern picks.

### Projection: inputs and factors
- **Wind and temperature** (2026-10-26, round 1; 2026-10-30, round 4): wind 15+ mph DL +3%, CB flat; 40F or below DL +2%, CB -2%; no test gain. By position again: DL +1% in 2023-24 but +11% in 2025-26; the halves disagree.
- **Opponent run share as a per-position slope** (2026-10-26; round 1): per +10 points DL +8.5%, LB +6%, CB -4.8%, S -1.4%; no out-of-sample gain (+0.09% MAE). Round 2 then adopted a damped mix factor. Re-open if: another season of data.
- **Indoor games (CB and LB)** (2026-10-26; round 1): CB +3%, LB -4% fitted; test gain 0.06%, not worth a parameter. Round 4 adopted corners in domes x1.05 only.
- **Removing the spread tilt** (2026-10-26; round 1): the tilt slightly overshoots (underdog rows 0.98, favourites 1.005) but removing it costs 0.04% MAE. Left as is.
- **Game total and opponent implied points** (2026-10-26, round 1; 2026-10-31, round 5): the total shows nothing; total slope -0.006 per 10 points, held-out miss -0.009%; implied points +0.004 per 5 points, -0.027%.
- **Home/away, rematches, week of season** (2026-10-26, round 1; 2026-10-30, round 4): ratios 0.986-1.000 (division games included); nothing there. Home/away again in round 4: 1.007 vs 1.008.
- **Divisional games** (2026-10-26, round 1; 2026-11-01, round 5; 2026-11-09, football logic): actual over model 0.987 / 0.986 against 0.982 / 0.992 in the rest; LB -0.07 (se 0.10), corners -0.17 (se 0.08), about -4%. Nothing added.
- **Recency weighting** (2026-10-26; round 1): exponentially weighted average, half-life 3/5/8 games; -0.2% at 8, overlaps with the position shrinkage. Not adopted; candidate.
- **Opponent yards after catch** (2026-10-26; round 1): for DB tackles; nothing. Rejected.
- **Bigger role bump** (2026-10-26; round 1): flagged backups beat the model by 15-18% after the 10% bump (1,204 games), but raising it to 1.2-1.35 worsened out-of-sample MAE; kept at 1.10. Re-open if: 4 weeks with the snap trend live.
- **Opportunity-volume factor without a cap** (2026-10-26; round 1): the extreme adjustments were wrong (ratio 1.00 to 0.95 on the most-moved rows); capped at +/-10%.
- **Snap-trend exponent 0.45 on drops** (2026-10-26; round 1): rises want exponent 0.45, but 0.45 overcorrected drops; drops use a gentler 0.35.
- **Opponent starting QB or lead rusher out, as a factor** (2026-10-27; round 2): the fitted effect (-6 to -9% for LB/S/DL) pointed the other way on the test years. Shown on cards as context only.
- **FTN box counts** (2026-10-27; round 2): a defence's box-count tendency lifted corners (+8.5% per extra box defender fitted) and linebackers, but no out-of-sample gain in the joint fit. Not loaded.
- **Years of experience (rookies)** (2026-10-27; round 2): from weekly rosters; rookies run 3-8% under the model through week 10 and above it late; no out-of-sample gain.
- **Opponent offensive EPA and first downs** (2026-10-27; round 2): nothing beyond the volume factor already in the model.
- **Short weeks** (2026-10-27; round 2): 4 days' rest, own or opponent's; nothing.
- **Promotion on the depth chart as a factor** (2026-10-27; round 2): +2% only; kept as a tag (the same round's adopted list still names a promoted x1.02 factor).
- **Demotion at the full joint fit** (2026-10-27; round 2): the -20% joint fit overcorrected the test years (demoted players ran 17% under the model over 397 games, test years 7%); damped to x0.90.
- **Zone matchups** (2026-10-27; round 3): his tackle rate by run direction and pass depth times the opponent's zone mix; a 2% raw spread between fifths, but as a factor worse at half strength (+0.09%) and much worse at full (+1.03%).
- **Opponent tendencies and FTN charting** (2026-10-27, round 3; 2026-11-02, week 8 post-mortem): nine rates as per-position multipliers, not one moved test error by more than 0.04%; then 28 FTN tests, none consistent in both halves.
- **Own-team starters out, by position group** (2026-10-27; round 3): fitted +7% DL, +14% LB, +12% S, +14% CB, +8% CB when a safety is out, +6% LB when a corner is out; every one was worse on the test years (LB +0.39%).
- **Blitz rate** (2026-10-27; round 3): PFR def_times_blitzed, LB and S; heavy blitzers ran 2% under the model, light ones 2% over, but the fitted slope rounded to zero out of sample (-0.00%).
- **Did-not-practise status** (2026-10-27; round 3): nothing (550); questionable (6% under the model) and limited practice (4% under) were the parts adopted.
- **New-role multiplier** (2026-10-30; week 8 Thursday post-mortem, retired in round 4): projection x (last-game share / season share)^0.25; with the per-snap base in the blend it double-counted (new-role bias -0.44 with it, -0.02 without).
- **Tackles the opponent allows to the position group** (2026-10-30; round 4): +0.06% on the per-game model, then slightly worse on both halves once the per-snap base was in. Kept as a corrector feature only.
- **Opponent pace and forecasting plays faced** (2026-10-30, round 4; 2026-11-02, week 8 post-mortem): pace slope negative and tiny; with spread, no-huddle, plays per drive and pass rate the held-out residual was 7.65 to 7.77 against 7.66 without.
- **Opponent QB scramble rate** (2026-10-30; round 4): nothing for any position (within 0.03%).
- **Opponent sack rate allowed** (2026-10-30; round 4): for DL; buckets inconsistent in the middle, 0.02% gain. Not worth its code.
- **Refitting the role-shift factor sizes** (2026-10-30; round 4): on the new core the existing sizes are MAE-optimal; softer absence factors trade a few hundredths of bias for worse error. Unchanged.
- **Lineman pressure profile** (2026-10-31; round 5): two buckets (+6%, +3%) for low-pressure linemen; the backtest rejected it: miss 1.6217 without, 1.6260 with; DL bias -0.033 without, -0.122 with. Kept as a card tag only.
- **Playing surface** (2026-10-31; round 5): actual over model 0.997 / 1.004 on grass, 0.988 / 0.994 on turf. Nothing.
- **Opponent pass rate over expected** (2026-10-31; round 5): by position, held-out miss +0.045% (LB) to -0.013% (DL), biases unmoved.
- **Opponent shotgun rate** (2026-10-31; round 5): -0.011% to +0.014%. Nothing.
- **Opponent plays per drive, third-down rate, plays gaining 3 yards or fewer** (2026-10-31; round 5): -0.039% / -0.042% / -0.016%, biases unmoved; below the bar (about -0.1% or a bias it fixes).
- **Next Gen Stats for the opponent** (2026-10-31; round 5): rushing (yards over expected, efficiency) -0.009% to +0.002%; QB time to throw and completion over expected -0.029% to +0.016%, CB bias moved the wrong way.
- **Corner coverage quality** (2026-11-02; round 6): yards per target allowed under 6 ran 1.084 (2023-24) and 0.956 (2025-26) of the model; as slopes held-out error got worse (+0.13% yards per target, +0.32% rating allowed); no lift on our picks.
- **Steeper PFR target factor** (2026-11-02; round 6): targets per game is consistent at the extremes (3 or fewer 1.107 and 1.069; more than 7.5, 0.905 and 0.904), but a steeper refit gains 0.1% on corners only. Not adopted.
- **Opponent passing quality** (2026-11-02; round 6): EPA per dropback vs that season's league, LB and DL; level-matched miss improves only 0.06% in both halves (LB and DL 0.11%). Re-open if: the two-bucket form clears the 0.1% bar on a full 2026 season.
- **Rain and linebacker Overs** (2026-11-02; round 7): an LB Over at his season-average line hit 45.2% in rain against 45.6% dry (321 and 5,313 games). Re-open if: measured precipitation (mm) and a season of rain games with lines.
- **Wind 18 mph or more** (2026-11-02; round 7): 11 games; linemen ran over the model in both halves (1.119, 1.169); too few to act on. A candidate to watch.
- **Opponent completions by receiver position** (2026-11-03; round 9): his tackle rate per completion to a back, tight end and receiver times the opponent's mix; factor sd 0.009, level-matched miss 1.6185 to 1.6185 in every season at every power.
- **Remaining starters absorb an absent starter's tackles** (2026-11-09; changelog, football logic): LB +0.34 tackles (+5%, se 0.19, n=255), CB +0.19 (+4%), S -0.16, DL noise; the backup who takes the snaps takes the tackles.
- **Recent form (last three games)** (2026-11-09; changelog, football logic): veterans best weight 0.10, out-of-sample error unchanged; rookies weight 0.15, 2% lower error out of sample, but slightly worse in the 2026 corrector fold. Not added.
- **Press-man corner read** (2026-11-09; changelog, football logic): corners allowing under 2 completions a game run +0.67 tackles above their season average next game, 4+ a game -0.92, in all three seasons; the low average regresses up.
- **Football reads as corrector features** (2026-11-09; changelog, football logic): completions allowed, catch rate, rookie, last-three trend; 2025 fold MAE 1.5887 to 1.5883, 2026 fold 1.5769 to 1.5765. Re-open if: a new data source (e.g. charted press/man coverage).
- **Separate next-man-up bump for trades** (2026-11-09; changelog, trades): 28 mid-season moves of regulars since 2023; backups rose 6-14 points of snap share and 0.2-1.4 tackles; too few trades to size a separate bump, so ROLE_BUMP applies.
- **The game total and the opponent's implied points as corrector inputs** (2026-11-10; changelog): final projection, corrector retrained per fold. Regulars 2025-26 +0.0002 (t +0.3), all folds +0.0032 (t +1.4): no gain, worse in 2024. The spread and the opponent's volume already carry it. Re-open if: a play-count projection from another source.
- **A backup quarterback for the opponent** (2026-11-10; changelog): the opponent's starter is not the one who started most of its earlier games (21% of games). Regulars 2025-26 -0.0002 (t -0.3); on the games it touches -0.0065 (t -1.7, 1,247 rows). Raw: linebackers 3.9% over their projection against a backup, corners and safeties 1.5% under. The right direction, short of the bar (t -2 on the rows it moves). Re-open if: a full extra season, or as a factor by position.
- **Wind and cold as corrector inputs** (2026-11-10; changelog): regulars 2025-26 -0.0010 (t -1.7), 2026 alone -0.0029 (t -2.1), all folds +0.0007, and worse on the windy games themselves (+0.014, 346 rows). Raw, wind 15 mph+: linebackers +6%, corners -7% (about 100 rows each). The schedule feed has no forecast before the game, so it could not run live anyway. Re-open if: a forecast feed, with a season more of windy games.
- **Recent form (last three games against the season average) as a corrector input** (2026-11-10; validation pass): regulars 2025-26 +0.0005 (t +0.5), all folds -0.0013 (t -0.7). Over 2024 and 2025 the final projection is level on hot players (actual over projected 0.99 to 1.01); only 2026 shows them 5 to 7% over, as it shows cold players 5% over: that is the season's level, not a lag. The books' lag on hot players (tools/holes.py) is theirs, not the model's.
- **Rotowire's weekly projection as a corrector input or a blend** (2026-11-10; validation pass): through Sleeper's public feed, 2024 to 2026, 5,575 regular games. Its deviance is 1.81 level-matched against 1.31 for the final projection (t +10.8), it runs 16 to 22% under the box score, and any blend is worse. As a corrector input: regulars 2025-26 -0.0026 (t -1.5), everyone -0.0061 (t -4.0): it helps on the players no book prices. Past weeks are served as they stood at the week's end, so even that may flatter it. Re-open if: its number captured at each pull for a season.
- **Stadium stat crews, again** (2026-11-10; validation pass): a stadium's lean toward solo or assisted credit carried from 2023 to 2024 (correlation 0.46) and 2024 to 2025 (0.31), and is gone in 2026: 2025 to 2026 -0.02, the first half of 2026 against the second 0.04. Nothing to price this season.

### Projection: structure and shrinkage
- **Per-snap rate as the whole base** (2026-10-26, round 1; 2026-10-30, round 4): rate per snap x expected snaps alone was worse (+1.7% MAE); with no per-game blend 1.7306 train / 1.7258 test. Adopted only as 40% of a blend in round 4.
- **Run/pass split model as a replacement** (2026-10-27; round 2): tackle credits on run and pass plays times the opponent's mix; the split model alone was 6.5% worse than the full model, so it is a damped correction only.
- **Play-by-play solo share** (2026-10-27; round 3): his own run/pass solo shares weighted by the expected mix; MAE 1.1406 vs 1.1276 for the current solo share, a 50/50 blend still worse (1.1327). Kept the current solo method.
- **Corrector weight above 0.6** (2026-10-27, round 3; 2026-10-30, audit; 2026-11-09, round 11): 0.7 marginally better in sample; in round 11 the best weight by fold was 0.5, 0.9, 1.0 for every defender but 0.4, 0.6, 0.7 for regulars, and 0.8 was no better than 0.6 for them (-0.0085 vs -0.0089) and worse on the 2024 fold (+0.024, t +2.3). Re-open if: a full 2026 fold where regulars prefer 0.8.
- **Per-snap rate at the last-game share for every jump** (2026-10-30; round 4): bias -1.0 to -1.2 (over-projection); most one-game spikes regress, so the rule is conditional on a vacancy or a listing.
- **Vacancy rule at full weight** (2026-10-30; round 4): at full weight the rule overshoots (-0.46); at half weight +0.05 to +0.11 with the lowest error of the three.
- **Per-snap definition of the outlier fade** (2026-10-30; round 4): a big game only if his per-snap rate was 1.5x his norm; identical results to the raw-count definition (0.981 vs 0.979), so the simpler one stays.
- **Separate OLB position group** (2026-10-30; audit): nflverse labels 1,226 of 1,316 linebacker rows "LB" in 2026; the few OLB rows have a DL-like rate (0.079 per snap vs 0.123). Too few to split.
- **Other solo drift windows** (2026-10-31, changelog; 2026-11-04, round 10): 1-4 weeks tested, no difference; three weeks has the lowest error (rmse 0.0363 against 0.0391 season-to-date, 0.0388 two weeks, 0.0410 last week). Stays 3.
- **Team tackle budget** (2026-11-03; round 9): scale a defence's projections to plays faced x 1.28 tackles per play; raw miss 1.6216 to 1.6089 but level-matched only 1.6185 to 1.6178, and 1.6194 with players expected to play. Removed the same evening.
- **Dropping the league solo drift** (2026-11-08; changelog, deep review): tested as the cause of week 9; drift was 0.973 that week, and without it the solo projection still ran 0.31 low (0.39 with it). Not the culprit; kept.
- **Training the solo series on the official count** (2026-11-09; changelog, two solo counts): solo + tackle with assist lifted every solo projection about 7% (Turner 1.79 to 2.06), far more than this season's 2.4%. Corrected within the hour.
- **In-season level by snap-share class** (2026-11-09; round 11): actual over projected for the season's earlier weeks per share class, shrunk over 300 to 10,000 tackles; the bias of the 60%+ class falls (2025: -0.095 to -0.005; 2026 at 80%+: +0.131 to +0.082) but its deviance does not (+0.0004, t +0.3). Candidate for the shadow test.
- **A level correction for next-man-up backups** (2026-11-09; round 11): the final projection runs 12% low on them out of sample, but a ratio fitted on earlier folds (1.13, 1.08) over-corrects the next: deviance +0.010 (t +0.3), bias +0.18 to -0.20. A guard instead (decision E7).
- **A bigger next-man-up bump (1.20)** (2026-11-09; round 11): bias on those rows +0.25 to +0.22, but deviance worse for everyone (-0.0121 against -0.0135) and for the 60%+ class.
- **The vacancy rule at half or quarter weight on the final projection** (2026-11-09; round 11): with it the final number over-projects its rows (-0.28 at 0.5, -0.11 at 0.25, +0.15 without); with against without +0.038 (t +0.6) on 213 rows. Out.
- **A minimal factor set** (2026-11-09; round 11): also dropping volume, spread tilt, indoors and depth chart loses the gain for the 60%+ class (+0.0000 against -0.0033); feeding the corrector the season rate alone is worse again (+0.0032).
- **Opponent and game effects on the solo share** (2026-11-10; hour's search): added to the recalibrated share one at a time, regulars 2024-26: the opponent's solo share allowed -0.0021 (t -0.9; the raw gradient is 0.538 to 0.574 across fifths and grows each season, so re-open with a season more), the defence's own lean, run share faced, spread, home, implied points, indoors, week, snaps: none at t -2.
- **An in-season level by position** (2026-11-10; hour's search): the season's actual over projected so far, shrunk over 300 to 2,000 tackles: +0.0029 to +0.0008 (worse) over 2024-26, better only in 2026 (-0.003), where linebackers run 5% over. A season's level by position is noise in a normal year.
- **The league's recent tackle volume as a level** (2026-11-10; hour's search): volume rose from 63.9 a team-game in 2023 to 66.2 in 2026, but the last three weeks' volume says nothing about next week's level (correlation 0.04 over 47 weeks).
- **Correcting the snap forecast's biases** (2026-11-10; hour's search): non-starters on the depth chart expected at 50%+ play 5 points less than forecast, demoted players 9, after a bye 2, heavy favourites 2. Removing the bias (walk-forward) leaves the tackle projection no better (+0.0010, t +1.0): the corrector already knows.
- **The corrector's weight, or the games of prior, by position** (2026-11-10; hour's search): 0.6 is the best weight for linebackers in every season and inside noise for the rest (corners at 0.45: -0.0038, t -1.8); more prior for safeties, corners or linebackers: nothing at t -2 on its own position.

### Spread and distribution
- **Player-level dispersion** (2026-10-26; round 1): per-player variance shrunk to the position value had worse likelihood than the position value at every shrinkage tried. Phi stays by position.
- **A free Under from skew, by position** (2026-10-31; "Why the CB Unders hit"): 45% of games land below the player's own average at every position; a half-point line at the average goes under 48% of the time for CB, DL, LB and S alike.
- **Wider spread for divisional games** (2026-11-01; round 5): about 5% more spread (residual var/mean 1.41 vs 1.34; miss 1.64 vs 1.62); too small for a parameter.
- **Plays-faced mixture for the count shape** (2026-11-03; round 9): the single negative binomial is already calibrated (5.1% below its 5th percentile, 4.8% above its 95th) and the mixture changes nothing (4.9%/4.8%, Brier 0.2413 in both).
- **Snap-share variance in the dispersion** (2026-11-03; round 9): fitted slope 0.01, -0.04, 0.06 and -0.01: nothing; tails two-bin 5.4%/5.4%, four share buckets 5.0%/5.4%, continuous form 4.9%/5.4%. The two-bin split stays.
- **Narrower count spread for starters** (2026-11-09; changelog, audit round): Brier 0.23786 (current) vs 0.23837 (starters, noise-corrected) vs 0.23794 (starters, raw); 2026 real combined lines 0.25079 vs 0.25046 vs 0.25052. Kept.
- **Variance = mean + a x mean^2** (2026-11-09; open issues A7): the current form (variance = spread x mean) scores slightly better out of sample than this one.
- **A wider spread for thin histories** (2026-11-09; round 11): best-fit spread around the final projection by prior games 1.28 (2 games), 1.27 (3-4), 1.26 (5-7), 1.25 (8+): nothing to allow for.

### Pricing, calibration and pick rules
- **The flag at over 60% in place of 58%** (2026-11-10, owner's question; three seasons of closing lines, one unit on every solo Under, no model): strictly over 60%, 1,554-1,043 (59.8%, +7.9% a bet); at 58% or more, 1,939-1,272 (60.4%, +9.8%). What the stricter cut drops is almost entirely the lines at exactly 60% (a solo line of 4.5 against a combined line of 7.5: 585 of 614), and those were the best of the lot: 385-229 (62.7%, +18.1%), and 125-56 where the engine also picked the Under. "60% and up" is the flag as it stands, to within 29 lines. Left at 58%.
- **Combined weight 0.5 in place of 0.35, by replay** (2026-11-10, noon; 21 weeks): 289 more picks (14 a week), nearly all combined Unders, 158-131 between them: +4.0 units on 71 more staked (+5.6% against +23.4% for the rest), and 36-46 on the 2026 weeks. More to bet for less a unit. The scoreboard's small gain (+0.0018, t +2.3) does not turn into picks worth taking.
- **A wider A** (2026-11-10, noon): every flagged solo Under with a clear checklist as an A: 229-97 (70%) on 15 a week, against 106-35 (75%) on 7 with the sleeper margin as well. The sleeper margin separates within the flag (73% against 65%), so it stays in the A.
- **Part-time players' solo Unders and Rotowire's confirmation** (2026-11-10 candidates; rejected 11:40 am on the 2025 season): under 85% of the snaps 188-142 (57%) against 59% for the rest of the solo board; the share-gap or part-time lines with Rotowire's solo number well under the line 123-73 (63%) against 421-283 (60%) without. Off the card; `tools/holes.py` still scores them.
- **A different weight on the model** (2026-11-10, 11:40 am; 25 weeks of two seasons): nothing clears t 2 leaving one week out (open issue 22). Solo 0.65 confirmed.
- **The hot player's combined Over** (2026-11-10, 8:30 am candidate; rejected 11 am): last three games half a tackle over his season average. 75-47 on weeks 7 to 9 where it was found, 36-45 (-13% a bet) on weeks 1 to 6. Off the card; still scored by `tools/holes.py`.
- **The book-share correction inside the engine** (2026-11-10, 11 am): the fair chance of a solo Under moved up when the book's solo line is 58%+ of its combined line. Fitted on weeks 7 to 9 and scored on weeks 2 to 6: -0.0090 (the shift is three times too large); leave one week out +0.0028 (t +0.7), worse in weeks 2, 4 and 5; a fixed small shift (0.15 to 0.2) +0.0015 to +0.0019 (t 2) on all weeks but +0.0005 (t 0.6) on weeks 2 to 6. The signal is real as a bet (issue 15) and too uneven week to week to be a probability. Re-open with weeks 10 to 13.
- **The solo-share gap as its own signal** (2026-11-10, 11 am): once the book's share is known the player's own share adds nothing: gap of -0.04 or lower without a book share of 58%: 44-42 on weeks 1 to 6; a book share of 58% without the gap: 41-26.
- **A level by position for lined players, solo or combined** (2026-11-10, 11 am): walk-forward on weeks 3 to 9, solo +0.0003 (t +0.1), combined -0.0037 (t -1.4, all of it weeks 8 and 9). Corners' solo ran 21% under the model on weeks 7 to 9 and 1% under on weeks 2 to 6.
- **Pricing from the model's number alone** (2026-10-26; week 7 post-mortem): claimed 62%, hit 53%; old rules on week 7 closing lines 59-57, -3.1 units against 50-41, +11.8 with the blend (partly in-sample). Re-open if: over 4+ weeks the pure model beats the blend.
- **Shrinking the probability toward the market on top of the blend** (2026-10-26; backlog): by 0.25-0.5; fewer picks and worse results on week 7 at every bar. The blend alone did the work (PROB_SHRINK left off). Superseded, not contradicted: that was week 7 picks on the raw-line blend; the engine of 2026-11-09 anchors on the fair price and was chosen on every closing line of three weeks.
- **Consistency as a filter** (2026-10-26, backlog; 2026-11-09, open issues A9): cleared the line in 67%+ of games: no lift on week 7; on 778 lines "cleared this line in his games" adds nothing (-0.21, t = -0.5).
- **Snap-share change, games of history and blowouts as miss explanations** (2026-10-26; week 7 post-mortem, backlog): snap-share changes were the same for winners and losers; small effects, inconsistent sign. None.
- **Market agreement in the lock score** (2026-10-26; changelog): the 40% component was removed on the owner's principle, though week 7 picks the book also favoured hit 60% and picks against it 45%.
- **Locks below the A bar** (2026-10-26 and 2026-11-02; changelog): on a two-player board the top three were C grades flagged as locks (floor 55 added); later locks at 55-72 went 2-1 against 5-1 at 72+ (floor now 72; uncorrected record, A10).
- **Outlier fade on new-role players** (2026-10-30; week 8 Thursday post-mortem): on new-role players actual was under the model only 45% (56% for settled players) and 18% over it on average; the fade now fires only in a settled role.
- **Over fade after a low game** (2026-10-30; week 8 Thursday post-mortem): after a low game actual ran 4.5% under the model for settled players, 18% under after fewer snaps, 13% under after an absence. Signal removed.
- **Line weight 0.3 or 0.4 in the pricing blend** (2026-10-30; audit): log-loss 0.6835 at 0.4 and 0.6844 at 0.3 against 0.6827 at 0.6 and 0.7 (0.6830 at 0.5); round 9 later estimated the weight per market (0.49). (Moot since 2026-11-09: the raw-line blend, its level corrections and the segment correction were retired.)
- **Overs as locks or parlay legs** (2026-10-30; risk pass): live Over picks 28-40 (41%); where the model sat above the market overs hit 32-46% (uncorrected record, A10). Removed. Re-open if: forty further Over picks at 55%+.
- **Spreading locks across games** (2026-10-30; risk pass): same-game residual correlation is +0.02 for teammates, so five Unders from one game are not materially correlated. Accepted as is.
- **Upward adjustments as the cause of Over misses** (2026-10-31; "Why the Overs miss"): ruled out; when the model projects 25%+ above his average he delivers 4-6% more than projected; over chances near the projection are honest (0.438 vs 0.456 observed).
- **Solo Unders as a blind rule** (2026-10-31; "Is the solo Under our play?", "Luck or skill"): our solo-Under picks hit 66%, every solo Under blind 67%; in week 7 they hit 64% because 67% of solo lines went under. Withdrawn as a finding.
- **Lower pick bar for signal-backed picks** (2026-11-02; week 8 post-mortem): SIGNAL_BAR 0.04 went back to 0.06; the 12 picks taken at 4-6% return went 3-9 (-6.5 u) (uncorrected record, A10). (The bars were replaced by the cautious edge on 2026-11-09; signals no longer touch a pick.)
- **One fitted calibration map** (2026-11-03; round 9): logistic map, fit on week 7 and scored on week 8: Brier 0.2433 (per market 0.2391) against 0.2299 for the layered claim; slope swung from 0.51 to 1.14 between fits. Re-open if: 600 picks.
- **Least-squares line weight** (2026-11-03; round 9): one weight for every market from a least-squares fit on week 7; unstable (the line's coefficient was 0.69 on week 7 and 0.08 on week 8). The inverse-variance weight replaced it. (Moot since 2026-11-09: the raw-line blend, its level corrections and the segment correction were retired.)
- **Middles and a slow or soft book** (2026-11-04, round 10; 2026-11-09, audit round): 25 middles in two weeks: 15 combined (hit both sides 0%, -0.31 units per middle), 10 solo (40%, +0.18); theScore Bet picks 75-76 vs DraftKings 140-116, inside the noise.
- **Regime-robust solo price** (2026-11-08; changelog, deep review): better Brier in all three weeks (0.2337 vs 0.2347, 0.2296 vs 0.2323, 0.2452 vs 0.2485) but as an A gate 11-8 against 15-8. Re-open if: tested as the solo pricer on out-of-sample lines (A12).
- **Level corrections only where every week agrees in sign** (2026-11-08; changelog, deep review): walk-forward solo Brier 0.2276 to 0.2322 (worse) in week 8, 0.2598 to 0.2571 in week 9; combined slightly worse both weeks. Kept as is. (Moot since 2026-11-09: the raw-line blend, its level corrections and the segment correction were retired.)
- **Segment correction as a gate** (2026-11-08; changelog, deep review): solo Unders that cleared the bars only because of it went 33-36 against 55-46 for the rest; suggestive, not decisive. Re-read due at the week 10 post-mortem. (Moot since 2026-11-09: the raw-line blend, its level corrections and the segment correction were retired.)
- **Pricer +EV filter on combined-Over sleepers** (2026-11-08; changelog, deep review): inside the combined band the Overs the pricer also called +EV went 7-10, the whole band 35-21. No price filter.
- **Wider sleeper bands** (2026-11-09; changelog, sleepers): combined Overs 1.0-1.5 over the line went 9-11 (whole board 47% of 19); solo Unders more than a tackle from his season median went 17-16 against 44-9 within. Cut.
- **Sleeper-grade features** (2026-11-09; changelog, sleepers): consistency (non-monotonic; 0.7-0.9 Unders hit 59% vs 81% below 0.7), spread, stat crew, opponent tackles allowed, snap trend, position: all mixed across weeks. Not adopted.
- **Season-median history check on ordinary picks** (2026-11-09; changelog, sleepers): it does not separate our ordinary picks (A 75% within a tackle vs 78% beyond), so it is a sleeper rule only.
- **Level corrections by position** (2026-11-09; changelog, audit round): walk-forward combined Brier flat to worse (0.2432 to 0.2439, 0.2510 to 0.2510), solo worse in week 8 (0.2276 to 0.2299), better in week 9 (0.2598 to 0.2534). Kept market-wide. (Moot since 2026-11-09: the raw-line blend, its level corrections and the segment correction were retired.)
- **Re-scaling claims that run 5 points high** (2026-11-09; changelog, audit round): claimed 59.0%, hit 53.8%, se 3.2; the solo-share regime, not a slope; claims of 67%+ hit 15 of 16. No re-scaling. (Moot since 2026-11-09: the raw-line blend, its level corrections and the segment correction were retired.)
- **Re-ordering B and C grades** (2026-11-09; changelog, audit round): replay of weeks 7-9: B 53% (+1%/bet), C 59% (+24%/bet); the hit-rate gap is inside the noise (se ~7 points), the return gap is price. Grades were redefined on 2026-11-09; the order is re-read at 30 graded A picks.
- **Further rules for Over picks** (2026-11-09; changelog, audit round): 7-12 solo, 14-17 combined, mostly week 7; already rare (3 in the replay of weeks 7-9); the solo model's 60%+ Over probabilities hit 6 of 21. Left as is.
- **A ceiling on large disagreements** (2026-11-09; round 11): the gap squashed at 0.5 to 1.5 log-odds scored worse than the plain form at every ceiling (0.6841 to 0.6855 against 0.6823). The weight of 0.5 already discounts big gaps.
- **A weight per market, or fitted on the other weeks** (2026-11-09; round 11): combined prefers about 0.35, solo 0.65 to 0.8, but the fits are 0.48 (se 0.27) and 0.57 (se 0.28); the weight fitted on two weeks and scored on the third (0.72, 0.43, 0.47) scored 0.6832 against 0.6823 fixed. Shadow candidate.
- **A separate weight for Over and Under disagreements** (2026-11-09; round 11): +0.18 (se 0.62) where the model is above the book, +0.63 (se 0.27) below; fixed pairs (0.25/0.5, 0/0.5) score 0.6818-0.6819 against 0.6823: no difference.
- **Mean blend with the book's implied mean** (2026-11-09; round 11): 0.6830 against 0.6823 for the log-odds form; same idea, more machinery. Not used.
- **Centring the model's gap on the book's level** (2026-11-09; round 11): the model sits below the book in both markets every week (gap -0.19 combined, -0.21 solo); centring on other weeks scores 0.6857, on earlier weeks 0.6821, on the same slate 0.6838, against 0.6823: helps combined, costs solo, a wash. Shadow candidate.
- **The win chance in the grade** (2026-11-09; round 11): A at a win chance of 60%+ went 15-6 on the closing lines, but a pick can then move from B to A because the book agrees more (model 68%: B at a fair 50%, A at 53%). Breaks rule 0; the model's own chance is used instead (13-6).
- **Ranking by the cautious edge or by Kelly** (2026-11-09; round 11): thirds of the picks by cautious edge hit 66%, 51%, 63%; by cautious Kelly 66%, 54%, 61%; by the model's own chance 53%, 54%, 74%. The lock score is the model's own chance.
- **Books on different lines** (2026-11-10; changelog): 82 of 914 closing player-markets had books a tackle apart. The Under at the higher line 27-20 but -5.1% a bet (it costs about -155); the Over at the lower line 45-37, -7.6%; both sides as a middle -0.20 on 2 units (both won 4 of 47). The half tackle is priced in. No signal, no rule.
- **A price better than the other books' fair chance on the same line** (2026-11-10; changelog): of 2,356 sides not one cleared the other books' no-vig chance; the best 37 (within 3%) went 15-22. Line shopping saves vig; it is not an edge by itself.
- **A stale line after another book moved** (2026-11-10; changelog): between pulls, one book moved 4+ points and another did not: 13 chances in three weeks, 4-9. Pulls are hours apart, so most moves are seen at every book at once. Re-open if: pulls minutes apart around news (credits).

### Stakes and parlays
- **5 units on one high-conviction pick** (2026-11-02; round 6): Williams solo Under 3.5 at -155: quarter-Kelly 3% at a 65.5% claim, but without the +8 point segment correction the claim is 57.5%, below the 60.8% break-even. Stake follows the grade.
- **Solo-tackle legs in the recommended parlay** (2026-11-02; changelog): books refuse solo legs in a same-game parlay, so legs are combined only, though solo Unders went 65-38 in week 8 against 25-27 combined.
- **Grade-ladder, flat and uncapped Kelly stakes** (2026-11-03; round 9): at 136.5 units staked the ladder made +18.1, flat +10.8, quarter Kelly +15.9, against +21.2 with the game cap (uncorrected record, A10). Re-open if: Kelly trails the ladder over the next 300 picks.

### Other markets and data sources
- **Alternate tackle lines** (2026-11-10; week 9 of 2026 at DraftKings, 2,219 prices): Over-only ladders, so the flagged solo Under cannot be bet on them; every Over returned -5.7% (combined) and -13.8% (solo). Re-open only if a book posts two-way alternates.
- **ESPN QBR** (2026-10-31; round 5): no loader in nflreadpy; not reachable as a table. Skipped.
- **Special-teams tackles** (2026-10-31; round 5): the player stats have no separate column and the books settle on the same box-score total, so there is nothing to separate.
- **PrizePicks and Underdog projection APIs** (2026-10-31; round 5): refused to scripts (HTTP 403 and HTTP 426); their lines cannot be read, so no pick-'em cross-check.
- **Other prop markets from this data** (2026-11-03; round 8): yards, pass attempts, completions, carries, interceptions, kicking, touchdowns; volume and yardage stats add only +1 to +3 points on disagreement. Not worth pursuing; no lines were pulled.
- **Past lines for an assists replay** (2026-11-03; changelog, assists): The Odds API historical endpoint answered 401 on the first game; the key's plan has no historical access, nothing charged. Re-open if: the plan is upgraded.

### Operations
- **Pull slots matched to the cron minute** (2026-10-27; changelog): the 14-minute match window missed the Monday 5:30 pm pull (GitHub ran the job at 5:03 and 5:54); a slot is now served once by the first run after its time.
- **Hourly pull windows and Friday pulls** (2026-10-31, changelog; trimmed 2026-11-03): week 8 cost 162 credits at two markets, about 240 a week at three, against 500 a month; Friday pulls found nothing in week 8. Re-open if: the key is upgraded.
- **Earlier pulls to catch the first line** (2026-11-04, round 10; 2026-11-09, audit round): solo open vs close error 3.69 vs 3.61 and 3.76 vs 3.83; only 11-13% of lines ever move; by hours to kickoff no pattern (0-2 h 68%, 2-6 h 48%, 6-14 h 48%, 14-24 h 55%).
- **GitHub crons starting each job** (2026-11-05; changelog): the scheduler started the pull job four times overnight instead of every fifteen minutes and ran the daily hours late; the ticker replaced them as the only scheduled workflow.
- **theScore Bet slip links** (2026-11-08; changelog): the lines come from the US feed (the espnbet key) and its links cannot open in the Alberta app; the site no longer shows them.
- **Straight-line live pace on My board** (2026-11-08; changelog): predicting the rest of the game after the first quarter: error 14.0 the old way against 4.3; prior weights 0.5 game 5.2, 1 game 4.6, 2 games 4.4, 4 games 4.30 (kept).

## Open issues

What is not settled, most consequential first. The register of the 2026-11-09 review (items A1 to D3) is in the
archive with its evidence; the rebuild closed A1, A2, A3, A4, A6, A7, A9, A10, C6, C8 and D1 to D3, and partly A11
and C9. What remains, and what the rebuild itself turned up:

1. **An edge is shown on two seasons of closing lines; grades and stakes are half shown.** Fetched on 2026-11-10,
   after every pricing rule was chosen on weeks 7 to 9 of 2026 (changelog, 11 am and 11:40 am). The engine against
   the book's fair closing price: 2025, 3,843 lines, +0.0143 of log-loss (t +5.5), better in 16 of 17 weeks, in solo
   (+0.0219), combined (+0.0114) and assists (+0.0098); 2026 weeks 2 to 6, +0.0075 (t +1.7); weeks 2 to 9, +0.0081
   (t +2.7). The picks, replayed under the current rules: 2025 weeks 4 to 18, 726-422 (63%), +260.9 units at 1 a
   bet, +132.4 on 553 staked; 2026 weeks 4 to 9, 219-166, +44.0 and +10.7 on 166. A flat profit in 20 of the 21
   weeks; at DraftKings' prices alone 595-369. A picks 134-53 (72%) against B 433-283 and C 378-252 (60% each): A is
   above the rest, B is not above C. Stakes returned what flat bets did (+19.9% against +20%): they add nothing yet.
   What tempers it: 2025 was a soft year (every solo Under at the best closing price won 58% and returned +10.8%,
   every combined Under 55%), the 2026 weeks are thinner (54% on weeks 4 to 6), the replays read one snapshot an
   hour before kickoff with the final injury report, the projection's constants were tuned with 2025 in the data,
   and the best price is taken across three books of which Alberta has one or two. Weeks 10 to 13 are still the
   live test, and the record as bet before the engine is still 200-183.
2. **The model sits below the book, in both markets, every week.** Mean gap -0.19 (combined) and -0.21 (solo) in
   log-odds: the model gives the Over 45% where the book gives 49.6%. On solo the book was the one that was wrong in
   weeks 7 and 8 (Overs hit 33% and 39%) and right in week 9 (50%). On combined the model was wrong all three weeks
   (Overs hit 51.6%). So the board is mostly Unders (98 of 113 picks at the closing lines), and that lean is a
   position on the level of the whole market, not selection. The slate sizing limits what it can cost (10 units a
   kind a day). Related: the projection runs low on the regulars of 2026 (+0.14 tackles a game; -0.06 in 2025,
   +0.03 in 2024) and lower still on the players who had lines in weeks 7 to 9 (+0.26).
   Candidates, to be scored in the shadow through week 13 and not adopted before: (a) the combined gap centred on
   the same slate's mean; (b) a level for lined players from the season's earlier lined games; (c) a weight per
   market (0.35 combined, 0.65 solo); (d) the in-season level by share class. (a) to (c) are scored by the daily
   since 2026-11-09 with their numbers fixed (decision R6). (d) changes the projection, not the price: it is not in
   the shadow and needs the full test (it is in the rejected register with its numbers).
3. **Grades order in the replay; the live weeks have to show it.** Under H1 the 21 replayed weeks give A 75%, B 66%,
   C 59%, in order in each of four stretches, at DraftKings' prices too (65-18, 117-61, 409-279). B and C were
   defined on those weeks. C on the 2026 weeks alone is 153-131 (54%, about +9% a bet at the logged prices): the
   thinnest part of the board, and the first to become leans if weeks 10 to 13 do not hold it up.
4. **The profit in the replay is a pocket.** (Four of those lineman wins were the mis-posted Sam Williams lines,
   now barred; under the rules of 2026-11-09, 10 pm, linemen are 13-2, linebackers 48-44, safeties 34-25, corners
   22-14.) Linemen 16-2 (+14.4 units of +17.7), the assists trial 17-11;
   linebackers 42-39 and safeties 29-32, most of the board, are at break-even. Either the books hang linemen's
   lines too high or three weeks were kind. Watch by position.
5. **Next man up.** The final projection is 12% low on these backups out of sample (16% on the ones it expects
   under 60% of the snaps), and no correction holds from one season to the next. Guarded (decision E7), not solved.
   The share model does not know which backup takes the snaps; a depth chart read the same morning would.
6. **Overs.** 6-9 as picks at the closing lines, 15-20 in the replay, 28-40 live before the engine. Same test as
   Unders, never locks. Candidate: Overs as leans only. Re-read at 40 further Over picks.
7. **Odds credits and the key's end date.** About 1,890 of the paid key's 20,000 are left (2026-11-10, 1 pm) after
   the 2024 season and a sample of alternate lines; a live week with the assists market costs 200 to 300, so weeks 10 to 12 are covered. The plan
   resets on 2026-12-01 (owner; `config.ODDS_RESET_DAY = 1` is right) and **the owner's access ends on 2026-12-10**.
   From 12-01 to 12-10 there are 20,000 more: "The December exploration" below is the plan for them. After 12-10
   the live pulls need another key in `ODDS_API_KEY` (the free plan's 500 a month pays for the pre-kickoff pulls in
   two markets and little else; the budget governor handles it): owner's decision before 12-10.
8. **The standing post-mortem task: working.** Its first run under the instructions of 2026-11-09 (Tuesday
   2026-11-10, 8:24 am) read the plain weekly log, ran the daily in a scratch copy, wrote the close of week 9 in the
   set order and pushed it to this branch itself (commit 6f35256, `MODEL_LOG.md` only), in eight minutes. Nothing
   to merge. Read its Friday entry, the first with engine-era picks in it.
9. **The repository is public (owner).** Picks, projections, every odds snapshot and this file are readable without
   the site's password. A private repository needs paid Actions minutes for a ticker that runs all day.
10. **The closing price is an hour old** (the last pull before kickoff): closing-line value and the scoreboard are
    against that price, not the close.
11. **Prices are not Alberta prices.** theScore Bet's lines are its US feed; three books post tackle lines on the
    feed; bet365 is not carried. That a tackle made with an assist settles as solo at the book is inferred from
    ESPN, not confirmed: one settled slip would do it (Nohl Williams Under 2.5 solo, week 9).
15. **The book's own solo share (candidate, confirmed twice out of sample).** Solo Under where the book's solo line is
    58% or more of its own combined line: 117-49 on weeks 7 to 9 of 2026 where it was found, then 176-103 on weeks 1
    to 6 and 609-363 on the 2025 season (up in 16 of 18 weeks; t +4.5 with weeks as the unit), both fetched
    afterwards: 902-515 (64%) in all, where the rest of the solo board is 52%. It needs no model. It splits the
    engine's own picks in every stretch of the 21 replayed weeks: solo Under picks on a flagged line 316-141 (69%),
    on an unflagged line 207-165 (56%; 48-54 in 2026); solo Over picks on a flagged line 8-19, losing in each of
    four stretches; A picks on a flagged line 106-35 (75%), the other A picks 28-18. As a correction inside the
    engine it did not hold week to week on 2026 (rejected register). So it is a flag on the card and three lines
    under "Rules on trial" (H1), in no grade. Put to the owner on 2026-11-10 as a pick rule (no solo Over pick on
    a flagged line; the flag as an input to the A grade): frozen until they say (R4).
    Two sharper forms, found on the two seasons together and so in-sample: the book's share less the position's
    own (CB 0.66, S 0.57, LB 0.49, DL 0.44) at +0.08 or more, 540-251 (68%; 57% to 80% in each of four stretches),
    and a flagged line of 4.5 solo tackles or more, 305-122 (71%). Linebackers carry most of it (flagged 215-94).
    Dropped on the 2025 season: part-time players' solo Unders (188-142, 57%, against 59% for the rest), Rotowire's
    confirmation (123-73 with it, 63%, against 60% without), the hot player's combined Over (201-241).
16. **Closed 2026-11-10: the solo share was over-dispersed.** Adopted (P6; changelog, 11 am).
18. **Stakes: now by grade (S3).** The Kelly stakes added nothing over one size on 21 replayed weeks; the ladder
    does, because the grade orders and the cautious edge did not. The live count is under "Rules on trial".
19. **Overs.** Combined Over picks at the closing lines of 2026 were 3-11; in the 21 replayed weeks 44-37 (+9% a
    bet), so no case against them. Solo Over picks are 37-43 (-6%), and all of that loss is the flagged lines
    (8-19; unflagged 29-24): issue 15.
20. **Lines open about a day before kickoff.** In the week 8 sample nothing was posted 96 hours out, one book at 72
    and 48, DraftKings in part at 24, the board at 6. On weeks 1 to 6, 91% of the closing board was up 16 hours
    before kickoff at the same line (89% of solo lines, 79% of combined did not move) and the same price: the
    book-share Unders went 159-93 at the early line. So the Wednesday early look (weeks 10 and 11) will most
    likely find nothing, at no cost; and there is no price to be had by waiting for the last hour or by going
    early. When a line did move it moved the right way (Under the early line 34-18 when a combined line fell,
    29-48 when it rose): the model's side at the early line against the later move is the test still to run.
    The first live early look (Wednesday 2026-11-11, 10 am) found no line for any week 10 game, as expected.
21. **The assists market has earned a look at promotion.** Engine against the book: +0.0098 (t +3.7) on 1,299 lines
    of 2025, +0.0066 (t +2.9) on 709 of 2026. Picks in the replays: 195-117 (62%; Unders 144-87, Overs 51-30). It
    is still the trial market (no A, no lock, no parlay leg: `config.LOCK_MARKETS`). An A needs a sleeper rule,
    and there is none for assists. Owner's decision after week 13 with the live record beside this.
22. **The engine's weight, on 25 weeks.** Solo 0.65 stands: the book alone is worse by 0.0179 (t -4.3), 0.5 by 0.0020
    (t -2.2), 0.8 no better. Combined 0.35 looks low: 0.5 is better by 0.0018 (t +2.3), the best weight leaving
    one week out is 0.70 (+0.0021, t +1.2), but weeks 7 to 9 of 2026 point the other way (-0.0010 at 0.5). Not
    changed: E2 is read on weeks 10 to 13, and the flat 0.5 runs in the shadow for exactly this. The centred
    combined gap in the shadow failed on both fetched samples (t -2.5 and -3.1): expect it rejected at the read.
23. **Closed 2026-11-10: the 2024 season is fetched and tested** (changelog, 12:40 pm). `data/odds/2024`.
17. **Corners and safeties are too spread out on combined** (candidate): a slope for the two positions and the
    opponent's implied points for safeties, -0.0085 (t -3.1) on regulars 2025-26, worse for part-time backs. Re-test
    as one pre-stated variant, applied to regulars only, before anything is built.
12. **Closing-line value and the prices disagree.** On the replay's picks the price logged beat the closing price
    of the same line (+29.9 units against +25.0 on 186 picks), yet the no-vig closing-line value of the same picks
    is -2 points. One of the two is measured wrong (the vig widening near kickoff, or the conversion through the
    mean in `grade.no_vig_clv`). Until it is settled, do not read the CLV tile as "we bet too early".
13. **Role news is untested.** The rebuild at pull time (R7) is a mechanism with no record: watch the first Sunday
    for a rebuild in the ticker's log and what it changed. The same goes for lines that do not fit the player:
    count how many the guard removes a week.
14. **Smaller.** The proportional no-vig split is off by about a point at very short and long prices. The solo
    share's own uncertainty is not in the solo spread. A same-game parlay's price is our estimate, not the book's.
    The regime-robust solo price (archive, 2026-11-08) has not been tried as the solo model. ESPN spells 9 of 528
    names differently from the stats feed. An outside heartbeat for the scheduler would cover a failed hand-over.

## Research round 11: the rebuild (2026-11-09, evening and night MST, at the owner's request)

Owner: "Take full creative liberty in how to make this the most rigorous model and scientifically optimal model to
estimate tackle lines for the nfl, adjust the memory file as needed." Scripts are in the session scratchpad
(`rev2_*` to `rev8_*`, `replay_new.py`); the pieces they use are now in the code (`backtest.walk_forward_final`,
`backtest.paired`, `backtest.deviance`, `evaluate.scoreboard`, `tools/replay_five.py`). Two data sets: the closing
lines (745 lines of weeks 7 to 9, one per player and market, official box scores, the model's numbers as logged)
and the history (31,467 defender-games since 2023; 22,434 of them with an out-of-sample corrector over 47 weeks).

### 1. How two opinions become one chance (the closing lines)

Log-loss, lower is better; in brackets how much better than the book's fair price by week.

| Rule | Both markets | Combined (370) | Solo (375) |
| --- | --- | --- | --- |
| The book's fair chance | 0.6898 | 0.6918 | 0.6877 |
| The model alone | 0.6865 (-0.002, +0.015, -0.004) | 0.6979 | 0.6752 |
| The old form: mean blended with the raw line | 0.6827 (+0.009, +0.011, +0.001) | 0.6939 | 0.6716 |
| Mean blended with the book's implied mean | 0.6830 | 0.6901 | 0.6759 |
| **Fair chance + 0.5 x the gap, in log-odds** | **0.6823 (+0.004, +0.013, +0.005)** | 0.6894 | 0.6753 |
| the same at 0.25 | 0.6842 (+0.004, +0.008, +0.005) | 0.6888 | 0.6797 |
| at 0.35 / 0.65 / 0.8 | 0.6831 / 0.6826 / 0.6837 | 0.6887 / 0.6911 / 0.6936 | 0.6775 / 0.6742 / 0.6741 |
| 0.5 with a ceiling on the gap (0.5 to 1.5) | 0.6855 to 0.6841 | | |
| weight fitted on the other two weeks (0.72, 0.43, 0.47) | 0.6832 | | |

The fitted weight with a level per week is +0.53 (se 0.20): +0.48 (0.27) combined, +0.57 (0.28) solo; +0.18 (0.62)
where the model is above the book and +0.63 (0.27) where it is below. None of those splits is a difference. What
the engine fixes is not the pooled score, which the old blend nearly matched: it is that the old blend's solo
score came from ignoring the price (every plus-money Under lifted, which paid while the whole solo market ran high
and stopped in week 9), that it lost to the book on combined, and that everything built on it (the claim shrunk
toward 50%, the lock score, the stake) was off: claims of 59% hit 53%.

Tiers at the closing price, the engine's side on every line: cautious edge 2%+ 31-20 (+20% a bet; by week 10-6, 7-5,
14-9); 0 to 2% 37-25 (+15%); leans 72-68 (-1%); no pick 264-228 (+0.1%). Calibration of the win chance: said 43%,
hit 45%; 48% / 52%; 53% / 50%; 57% / 56%; 62% / 65%; 71% / 70%. By market and side among picks: solo Unders 41-20,
combined Unders 21-16, Overs 6-9. By position: linemen 17-1, linebackers 28-20, corners 11-8, safeties 12-16.

Grades: every definition tried on the cautious-edge 2%+ lines gave 60% to 75% on 12 to 32 lines (win chance 60%+
15-6; model's own chance 70%+ 13-6; cautious Kelly 6%+ 12-4; cautious edge 6%+ 11-4): no way to choose among them
on the record, so the choice was made on rule 0. On a grid of model chances from 51% to 98% and book chances from
5% up to the model's, at a fixed margin, the cautious edge and the grade never rise as the book moves toward the
model; the win chance does, and so, at absurd disagreements (model 90%, book 30%), does the Kelly stake by a hair.

The level: the model is below the book in both markets in every week (see open issue 2). Centring the gap on the
book's level scored 0.6857 (other weeks), 0.6821 (earlier weeks, shrunk) and 0.6838 (the same slate) against 0.6823
as built: it helps combined (+0.0057 against +0.0024 over the book) and costs solo (+0.0063 against +0.0124).
Not adopted; a shadow candidate.

### 2. The projection (the history)

Each factor of the old factor model on the rows it moves (both variants at the same level, deviance, weeks as the
unit): supported: coverage targets and missed tackles (t -9.5), next man up (-5.9), outlier damping (-3.1), per-snap
base (-2.6), depth chart (-1.8), opponent volume (-1.5), indoors (-1.4), spread tilt (-1.2). Not supported: injury
report (-0.3; it over-corrects: bias +0.13 with it, -0.16 without), bye (-0.2), snap trend (+0.4), vacancy rule
(+0.4; it fixes a +0.53 bias on 325 rows at the factor-model level), stat crew (+0.9), role shift (+1.6), run/pass
mix (+1.7).

The final projection under candidate designs, against the old design (every factor, corrector 0.6):

| Design | Regulars, folds 2025-26 | Regulars, 3 folds | Everyone, folds 2025-26 | Everyone, 3 folds |
| --- | --- | --- | --- | --- |
| **Adopted: seven factors out, next-man-up input, weight 0.6** | **-0.0089 (t -2.8)** | -0.0024 (t -0.6) | -0.0077 (t -3.2) | -0.0050 (t -2.4) |
| the same at weight 0.8 | -0.0085 (t -2.5) | +0.0051 (t +1.0) | -0.0140 (t -4.5) | -0.0051 (t -1.6) |
| the same at 0.4 / 0.5 / 0.7 / 0.9 | -0.0062 / -0.0079 / -0.0091 / -0.0071 | -0.0037 / -0.0039 / +0.0005 / +0.0113 | | |
| every factor, weight 0.8 | -0.0010 (t -0.6) | | -0.0064 (t -4.0) | +0.0003 |

The weight was first set to 0.8 on the "everyone" column and corrected the same night on the regulars' column:
the gain from a heavier corrector is all on part-timers, who never have a line (best weight by fold: everyone 0.5,
0.9, 1.0; regulars 0.4, 0.6, 0.7; 2024 fold, regulars, at 0.8: +0.024, t +2.3). With the adopted set at 0.6 every
factor was then flipped one at a time on the final projection for regulars: none of the seven that are out helps
when added back (the nearest, run/pass mix, -0.0017, t -1.2, and +0.0012 over three folds); none of the eight that
are in hurts (decision register, P2 and P3).

Other results. The vacancy rule on the final projection over-projects its rows at any weight (-0.28 at 0.5, -0.11 at
0.25, +0.15 without). A next-man-up bump of 1.20 is worse overall. A minimal factor set loses the gain. The in-season
level by share class removes the seasonal bias of the 60%+ class without improving its deviance. The spread around
the out-of-sample final projection is tighter than the one in use for linebackers and safeties (1.34 and 1.33 against
1.57 and 1.45) and needs no allowance for thin histories. Next-man-up backups: the final projection runs 9% to 12%
low out of sample (by season 14%, 2%, 16%), all of it on the ones expected under 60% of the snaps (16% low on 710
games); a level fitted on earlier folds over-corrects the next.

### 3. Validation

- Smoke test: 168 checks, among them rule 0 on the whole grid, the engine's arithmetic on every priced line, the
  slate's caps, a bet settling once, the credit budget walked through a month, the daily factor tests.
- The real daily in a scratch copy: runs in two minutes; no protocol flag; the final projection beats the factor
  model out of sample by -0.0467 a game (t -10.6) and by -0.0144 for regulars (t -2.8); calibration of the model's
  own chance at lines around the projection within 2 points in every bucket (the Over a point or so likelier than
  it says); the scoreboard on 880 closing lines: book 0.6913, model 0.6876, engine 0.6845 (+0.0068, t +1.9).
- The rebuilt projection on the lined players of weeks 7 to 9, against the numbers logged at the time: model alone
  0.6910 against 0.6868, through the engine 0.6860 against 0.6833. Inside the noise of 746 lines (the backtest's
  verdict rests on 6,092 regulars), and most of the solo part is the official-count factor, which raises solo
  numbers 2.4% in weeks when the whole solo market ran high (the old numbers times 1.024: 0.6769 against 0.6792
  rebuilt). On regulars in 2026 weeks 7 to 9 alone the adopted design is +0.0047 (t +0.6) against the old.
- Replay of weeks 7 to 9 (`tools/replay_five.py`): the projection rebuilt from games before each week, every pull
  fed through the live functions with the clock set to the pull. Found a crash the smoke test had not (a pull where
  no line could be priced left a column out; fixed, with a check).

| | Week 7 | Week 8 | Week 9 | All |
| --- | --- | --- | --- | --- |
| As bet (old rules, corrected record) | | | | 200-183 (52%), +0.1 u at one unit a bet |
| Replay: all picks | 21-26 | 31-22 | 51-37 | 103-85 (55%; range 44% to 65%), +17.7 u |
| Replay: units at the stakes (staked) | -6.1 (19.5) | +3.9 (20.1) | +2.2 (29.5) | -0.0 (69.1) |
| Replay: locks | 1-1 | 3-1 | 2-2 | 6-4 |
| Replay: A / B / C | 2-2 / 2-6 / 17-18 | 5-1 / 6-6 / 20-15 | 3-3 / 12-9 / 36-25 | 10-6 / 20-21 / 73-58 |

  By market and side: solo Unders 45-29, combined Unders 26-25, tackle Overs 15-20, assists 17-11. By position:
  linemen 16-2, corners 16-12, linebackers 42-39, safeties 29-32. The win chance claimed 55.6% and 54.8% hit. No-vig
  closing-line value -1.97 points on 186 (as bet: -2.75); 63% of the 113 that moved beat the close.
  Read it for what it is: half the bets, and about as much staked over three weeks (69 units) as went out on the
  one Sunday of week 9 as bet (60), with the pricing weight chosen on these same weeks. It shows the rules do what
  they say. It does not show an edge.

## Weekly post-mortems

Each post-mortem starts from the luck table (Track record tab; `data/weekly_five.md`): per kind of pick, our hit
rate against the whole board's base rate and the beat-the-close share. Only where lift and the close agree with
the record is the week evidence about the model.

Post-mortems of weeks 7 and 8 are in the archive. From week 10 a post-mortem starts from the scoreboard (Track
record, "Against the market") and the luck table, reads every record with its likely range, and changes nothing
inside the freeze unless it finds a defect.

### Week 9 closed, Tuesday 2026-11-10 (standing post-mortem, 8:20 am MST; measures only, nothing changed)

Grading had landed: `data/weekly_five.md` generated 2026-11-10 10:16 UTC, after the last logged kickoff of the week
(Sunday night, 2026-11-09 01:20 UTC). **Monday night's game of week 9 carried no pick**: no pick in `data/picks.csv`
has a kickoff after Sunday night, so this slate adds no bet to any record. Week 10 has no line and no graded pick
yet (first kickoff Thursday 2026-11-12, 19:15 Edmonton).

1. **Scoreboard since week 10:** none (0 lines). Weeks 7 to 9 are in-sample background only: engine better than the
   book by +0.0091 (give or take 0.0033; t +2.8) on 912 lines; solo +0.0173 (0.0049), combined +0.0012 (0.0034),
   assists +0.0085. These test nothing. Distinguishable from nothing out of sample: not yet measurable.
2. **Record since the engine:** none graded. Counted record of all rules to date (scratch daily, 619 rows logged):
   200-183 (52%, range 43% to 61%), +0.14 u at 1 a bet; A 13-9 (59%, 37% to 78%, claimed 64%), B 74-63 (54%, 43% to
   65%, claimed 59%), C 46-45 (51%, 38% to 63%, claimed 57%): A over B over C in the point estimates, every range
   overlaps. Locks 10-4 (71%), +3.45 u. Parlays 1-2. Week 9 alone (results.json, one row per bet, counted): 73-67,
   6 void, which differs from the Sunday entry's best-grade-per-player count (68-63); both are the same bets seen
   with and without the void and duplicate rows, not a regrade. Stakes per slate day against the caps: not
   assessed this run (no engine-era slate).
3. **Calibration:** nothing since the engine. All weeks, engine's side on every line: said 42% hit 55%, 48/49,
   52/55, 57/58, 62/63, 69/73 (91 to 252 lines a bucket): no sign of over-claiming at any chance on the
   in-sample weeks.
4. **Luck or skill:** nothing new. Week 9 (already written): Unders lift -0% over the board (53% on 53%), the
   market's level, not selection. The whole board's Overs won 34%/38%/47% on solo in weeks 7/8/9 against a fair
   49% to 50%: the solo level swung 13 points from week 8 to week 9.
5. **Conditions on trial** (all 0 graded, state running): E4 A picks 0/30, E4 old A rule 0/30, E5 combined A
   0/20, E6 Overs 0/40, E5 locks 0, E2 0/4 weeks, S1 0/4 weeks. None reached its count.
6. **Shadow candidates since week 10:** none graded. All weeks (in-sample included): flat 0.5 weight -0.0012
   (t -2.0), centred combined gap +0.0006 (t +7.3), lined-player solo level +0.0008 (t +0.6). None adopted before
   2026-12-08; rule R6.
7. **Misses:** no losing pick on this slate (no pick), so no box-score audit.
8. **Backtest (scratch daily, 31,506 games):** no flags raised. Final projection against the factor model by
   fold, deviance: 2024 1.4071 vs 1.4412, 2025 1.3399 vs 1.3920, 2026 1.3181 vs 1.3802; overall -0.0464 (t -10.6),
   regulars (starters) -0.0124 (t -2.4). Regulars' bias +0.024 overall, +0.140 in 2026 (open issue 2). No factor
   "hurts" and none out of the model is a "candidate" (role-shift regulars t -1.7, the nearest; bar -2). Tails: 5.1%
   below the 5th percentile, 4.8% above the 95th.
9. **Open issues:** (2) model below the book: the 2026 regulars' bias is +0.14 a game, nothing new. (3) grade
   order: A 13-9 over B 74-63 over C 46-45 on all weeks, ranges overlap, 30 engine-era A picks still to come.
   (4) linemen pocket: nothing new. (5) next man up: still 918 games, 12% low out of sample. (6) Overs: 0 engine-era
   Over picks; Over combined 13-16, Over solo 7-11 over all plays.
10. **What changed:** nothing; frozen until 2026-12-08. For the owner: the odds-credit state (open issue 7)
   decides whether the Wednesday early look and the pre-kickoff pulls can run for week 10. The scratch run had no
   password for the sealed site files (`meta.json.enc` treated as missing), which is expected.

### Week 9 through Sunday, 2026 (graded 2026-11-09 from ESPN finals; Monday's game pending; written 6 am MST at the owner's request)

**Record** (one row per player, market and side, best grade): 68-63 (52%), -4.1 u at the logged prices. A 9-8
(-2.2 u; solo 9-7), B 41-30 (+3.5 u), C 18-25 (-5.4 u). Locks 3-2 (-0.2 u): Stewart (-280) and Sherwood lost,
Henderson, Stokes and Young won. Parlay 0-1 (Gardner Under 4.5 leg lost).

**Luck table:** Unders 219 picks, hit 55% against a 51% board (lift +4), claimed 63%, beat the close 18%. The board
moved against the solo Under: every closing solo Under went 71-66 (-1%/bet) after +24% and +19% in weeks 7-8. League
solo share 0.549 (0.565 in the 12:00 Edmonton window, 0.499 in weeks 7-8). The lift is real but small; the record
is the regime.

**Calibration:** claimed 60%, hit 52% (all picks); A claimed 64%, hit 53%; C claimed 59%, hit 42%. Week 8's A
claims were 6.6 points above their prices (0.648 vs 0.582); week 9's were 2 points above (0.642 vs 0.622).

**By market, side, signal, window:** solo 63-60 (-5.2 u), combined 5-3 (+1.0 u); Unders 68-62, the one Over lost;
outlier fade 8-5 (+1.4 u), price gap only 60-58 (-5.6 u); by position CB 20-16, DL 8-8, LB 21-20, S 19-19. By kickoff
(Edmonton): Thursday 6-1, Sunday 8:30 (international) 6-3, 12:00 29-39 (-14.1 u), 15:05 and 15:25 21-14 (+3.7 u), 19:20
6-6. The 12:00 window was the high-solo-share window (0.565), not a timing failure: the earliest pull's picks for
it went 9-3, the later pulls' 20-36.

**Why the A grades failed:** six of the eight A losses (Sherwood, Henley, Pitre, Greenlaw, Stewart, Brown) had a
claimed chance at or below the price's own (claimed edge -3% to +1%); they were A because the return bar and the
lock score's EV term use the pricer's probability, which shrinks less than the claim. Heavy-juice Unders with no
cushion lose as a group when the solo share turns. Across all picks of weeks 8-9, claimed edge under 0: 12-20 (-34%);
0-4%: 14-11 (-2%); 4-15%: 57-36 (+11%); over 15%: 43-41. A at 4%+: 13-2 (7-0, 6-2); A under 4%: 6-6.

**What changed because of it:** the claimed-edge gate (changelog 2026-11-09, morning). Retroactively, at the logged
prices: week 9 A 6-2 (+2.2 u) instead of 9-8 (-2.2 u), Sunday locks Gibbens, Henderson, Stokes, Belton, Allen
5-0 instead of 3-2; week 8 A 6-0 instead of 10-0 (it would have dropped four winners: Walker, Styles, Marshall
and the McDuffie solo row). Week 7 logged no claims and cannot be checked.

## Changelog

Newest first. Entries through 2026-11-09 (evening) are in MODEL_LOG_ARCHIVE.md.

### 2026-11-11, 1:15 pm (the calculator: the stake spelled out by grade, and the locks in their own box)

The owner read the calculator's "Money out" box as wrong: it showed $400 under "1 unit on every pick" and under
"By grade (A 1, B 0.5, C 0.25)". Site only; no rule changed.

- **What was found.** The sum was right. The calculator opens with only the A grade ticked, and an A pick is 1
  unit under both stake choices, so 40 A picks are $400 either way; with B and C ticked the two choices part
  ($3,720 flat against $1,350 by grade on weeks 4 to 9). The box gave no way to see that, which is the defect.
- **What changed.** The box is now "Money staked" and spells out how the stake was built ("40 A at $10, 48 B at
  $5, 284 C at $2.50"). When every chosen pick stakes 1 unit under both choices it says so and says to tick B
  or C. A fourth box, "Just the locks", shows what the locks of the chosen source and weeks paid at 1 unit each
  (2026 weeks 4 to 9: 7-2, +$22.70 at $10; 2025: 31-10, +$118.63); the other filters do not apply to it, and it
  is hidden when "Locks only" is already the selection.
- **Evidence.** Driven in a browser at 1,200 px and 390 px across both stake choices, the three sources and the
  three "Show" choices: the figures match the replay records already logged, no script error, no overflow.
- **Revert if** the owner prefers the three boxes: remove the fourth card in `whatIfSection`.

### 2026-11-11, 12:40 pm (then and now: what the A picks alone, A and B, and every pick paid)

The owner asked for the "Then and now" table on the Track record tab to show what the new model's picks would
have paid betting only the A picks, only A and B, and every pick. Site only; no rule, grade or stake changed.

- **What.** The table's "New, units" column became three, at 1 unit a pick: "A only", "A + B" and "All picks"
  (the last is the old column), beside the records by grade and "All, at its stakes". A second total row adds up
  every replayed week (4 to 9) for the new model alone, under the row for the weeks both exist for (7 to 9). A
  line under the table gives the same three answers in dollars at the unit value set in the calculator (and
  follows it when it changes), at 1 unit a pick and at the model's own stakes. On a phone the table shows the
  week, the new model's record and the three paid columns; a note points to the week list for what was bet.
- **Why.** Vision: an easier site. The question "what if I only bet the A picks" needed the calculator; it is
  now read off the table the owner was already looking at.
- **Evidence.** The figures come from `data/retro_five.json` (`by_grade[].units` and `.staked`, `plays`), with no
  new computation in the pipeline. Weeks 4 to 9, replayed: A only +13.5 units on 40 bets (32-8), A and B +24.4
  on 88, every pick +50.3 on 372 (216-156); at its stakes +13.5, +18.9 and +25.4. They match the replay record
  already logged (2026-11-10) and the calculator. Checked in a browser at 1,200 px and 390 px: no script error,
  no page overflow, the dollars line follows the unit value. Smoke test: 185 checks.
- **Caution, as before.** These are replays of the weeks the rules were chosen on (weeks 4 to 9 are in sample);
  the page says so. The out-of-sample read starts at week 10.
- **Revert if** the owner finds the table too wide: drop the three columns back to one in `historySection`.

### 2026-11-11, 11:10 am (the first Wednesday early look: no book had a line; the daily ran on the new rules)

Scheduled check of the first early look (`config.OPENER_DATES`, Wednesday 10 am Edmonton). Nothing changed.

- The pull ran on time (commit "Pipeline 2026-11-11T16:00", `data/cache/pull_log.json`: `"2026-11-11 10:00": games 0`).
  No book had a tackle line for any week 10 game, the Thursday game included, about 32 hours before its kickoff.
  It cost no credits. That is what the week 8 sample and weeks 1 to 6 said it would find (open issue 20). Next
  Wednesday's look (2026-11-18) stays in place as asked; if it is empty too, the trial has its answer and the
  dates come out.
- The morning's daily (10:17 UTC) ran on the rules of 2026-11-10: 708 projections for week 10, the level for
  lined players 1.008, and `data/weekly_five.md` lists the conditions of H1 and S3. No week 10 line, pick or log
  row exists yet, so the checks of the first priced board (grades, the ladder, the caps, the flag in the "why")
  wait for Thursday's 9 am pull, which has its own scheduled check.
- The ticker's run in progress could not be read for errors until it ends; the pull's own commit and log entry
  show it completed.

### 2026-11-10, 3:01 pm (the calculator: locks only, and the sleepers' own list)

Owner: "How about sleepers? And locks? Can you add those into the filter too." The site only.

"What would it have paid?" has a "Show" choice: every pick, locks only, or sleepers. Sleepers are their own list
(a line where the model's number sits clear of the book's, one unit each whether or not the board picked it, with
the sleeper's own grade), so choosing them swaps the grades for sleeper grades and drops the stake choice. Every
other filter works on all three. The week range now follows the first and last week on offer until the reader
narrows it: while testing, switching from locks (which end in week 17 of 2025) to sleepers silently left week 18
out, and that is fixed.

Data: `tools/season_test.py` keeps the replay's graded sleepers and marks which picks were locks, and writes both
into `data/replay_seasons.json` (pick cells carry a lock flag; `sleeper_cells` by week, sleeper grade, market, side
and position). The three seasons were re-run for it and reproduce the published records exactly (216-156, 721-413,
537-371). What the re-runs add, replayed under today's rules, one unit each:

| | locks | sleepers, their own list | A sleepers |
|---|---|---|---|
| 2026, weeks 4 to 9 | 7-2 | 129-61, +30.9u | 34-9 |
| 2025, weeks 4 to 18 | 31-10 | 268-153, +48.9u | 75-33 |
| 2024, weeks 4 to 18 | 2-2 | 203-134, +20.9u | 14-10 |

Sleepers are frozen rules of their own and nothing here changes them; the numbers are the same kind of replay as the
picks' (open issue 1 for what that is worth). Checked in a browser against sums made from the re-runs' own files,
twelve selections over four sources; the earlier filter checks still give the same answers. Smoke test 184 of 184
(one new check). Revert: `git revert` of this commit.

### 2026-11-10, 2:26 pm (the calculator filters by market, side and position, and lists the picks)

Owner: "I want to be able to sort too. Like with the new model last week if I wanted to bet solo under A graded CB
S what would my results have been." The site only.

"What would it have paid?" now also takes a market (solo, tackles + assists, assists), a side (Overs, Unders or
both) and positions (LB, S, CB, DL; none ticked means all). Under the answer: the same selection broken down by
grade, by position and by market and side, and, for this season's sources, the picks themselves with each one's
result and dollars. The owner's example (new model, week 9, A, solo Unders, corners and safeties, $25 a unit):
3-1, +$29.83.

`data/replay_seasons.json` carries each replayed season as cells of week, grade, market, side and position
(`tools/season_test.py`), so 2025 and 2024 filter the same way; their individual picks are not on the site.
Checked in a browser against sums made independently from the replay's own files, four selections across three
sources, at phone and desktop widths. Smoke test 183 of 183 (one new check: each season's cells add up to its
record). Revert: `git revert` of this commit.

### 2026-11-10, 2:14 pm (Track record: "What would it have paid?", a unit value turned into dollars)

Owner: "In the track record, I want to be able to input your unit value and see how much you would be up if you
were to bet one unit per pick... if I went back to week eight and I put one unit on all of the A's, what I would
be." The site only; no rule, number or pick changes.

A section under the cards: one unit's worth in dollars (kept in the browser), which picks (the new model this
season: replayed before week 10, live from it; the picks as bet at the time; the new model replayed on 2025 and on
2024), from which week to which, which grades, and one unit on every pick or the grade's units. It answers with
the dollars up or down, the record, the money put out and about how much a week, and a week-by-week table with a
running total. Each source says under the answer whether it is a replay or real bets.

`data/replay_seasons.json` now carries each week's wins, losses and units by grade (`tools/season_test.py`), which
the calculator needs for 2024 and 2025. Checked in a browser against sums made independently from the same data:
A picks of weeks 8 and 9 of the replay 14-1, +$205.29 at $25 a unit; A and B of weeks 4 to 9 63-25, +$608.96 flat
and +$473.62 at the grade's units; 2025 A and B 253-116. The unit value survives a reload; phone and desktop
widths; no script error. Smoke test 182 of 182 (one new check). Revert: `git revert` of this commit.

### 2026-11-10, 2 pm (My board repackaged the same way; both tabs made to read well on a phone)

Owner: "Ensure the same goes for the My Board page. Cross ref both for mobile and ensure pleasurable viewing
experience." The site only; no rule, number or pick changes, and nothing stored on a device changes shape (the
board and the ledger are read from the same browser storage as before).

**My board:** the row of nine loose numbers is now cards (this week's board, settled so far, in play now, if the
rest all hit), each shown only when it has something to say; the long explanation, the clear-the-week button and
"add a bet from a game that has started" sit behind dropdowns; the season ledger opens with two cards (up or down,
record) and one dropdown a week, each with a table of four columns (bet with its price, stake and book under it,
result, tackles he had, profit) that fits a phone without sideways scrolling; back-up and transfer is a dropdown;
the two unstyled buttons are styled; a voided bet is no longer counted as pending.

**Phones (390 pixels wide), both tabs:** tables put the number that matters second and drop the secondary columns
(`ph(table, "5 6")` hides those columns on a narrow screen; the full table is there on a wider one). Against the
market: week, margin, book, engine. Every pick: grade, player, bet with its market, actual, result. Then and now:
week, as bet, new model. Seasons: season, record, return, weeks up. Tighter type and padding in tables, cards one
to a row, the filter bar two to a row.

**Checked** at 390 and 1,100 pixels with a seeded board of 38 bets over four weeks, every dropdown closed and
open: no script error and no sideways scroll of the page on either tab. Smoke test 181 of 181. Revert: `git
revert` of this commit.

### 2026-11-10, 1:45 pm (the Track record tab repackaged; what was bet beside what the new model would have picked)

Owner: "Clean up the way the track record page looks. Add a section at the bottom that clearly shows our historical
data and picks and outcomes vs new model... every pick open in a scrollable browser, we don't need that... a lot of
data on the screen that could adjust behind drop-down menus, but I do like having rules on trial... and the against
the market stuff." A change to the site only (vision: an easier site); no rule, number or pick changes.

**The tab, top to bottom:**
1. Four cards: the new model live (from week 10; "no result yet" until it has one), the new model replayed on
   past lines, the record as bet before it, and the margin over the book's own price. The live number and the
   replayed number are never added together.
2. Rules on trial, in view: one line a rule (name, state, count), the wording behind a tap.
3. Against the market, in view: the three scores, the margin, the verdict and the latest weeks; earlier weeks, the
   tiers, calibration, the candidates in the shadow and how to read it behind dropdowns.
4. Locks, parlays, sleepers, by grade, by side and the luck tables: one line each with its record, opening to the
   full section.
5. Every pick: the totals in view; the filters and the list behind "Open the list".
6. New, at the bottom, "Then and now": by week, the record as bet beside the new model's replay of the same weeks
   (units at 1 a bet in both columns, so like is compared with like); what the new model does with the bets of
   weeks 7 to 9 (bet then and still a pick 67-46, bet then and dropped 133-137, not bet then and a pick now 54-34);
   every pick and its outcome for each week, the two lists side by side; and the three seasons replayed (2024,
   2025, 2026) with a week-by-week dropdown each.
The closed page is half as long as it was (about 4,000 pixels against 7,900); dropdowns stay as the reader left
them when a filter redraws the tab.

**Data.** `data/replay_seasons.json` holds the replayed seasons (record, grades, stakes, by week, weeks ahead of the
book); `tools/season_test.py --json data/replay_seasons.json` rewrites a season's entry, and `run.replay_seasons`
hands the file to the site. It must be re-made when a rule changes (with `data/retro_five.json`), or the tab shows
the old rules' replay under the new rules' name.

**Checked.** Smoke test 181 of 181 (one new check: the section, the dropdown and the seasons file agree with
themselves). A real daily in a scratch copy writes the seasons into the site's data. The page rendered at 1,100
and 390 pixels wide, closed and with every dropdown open: no script error, no sideways scroll of the page. Revert:
`git revert` of this commit; nothing else depends on it.

### 2026-11-10, 12:40 pm (the 2024 season: today's rules on lines they never saw; the December plan)

Owner: "Do it" (the Over block: it went in at noon). "Plan resets Dec 1, I will have access until Dec 10. Explore
accordingly. Maybe Dec 1 can plan for another big exploration?"

**Fetched:** the 2024 season's closing lines, solo and combined, weeks 1 to 18: 8,562 prices (`data/odds/2024`).
Credits left: 2,174 before the alternate-lines sample below, about 1,890 after: three live weeks cost about 900.

**Why 2024.** The grade (H1), the Over block and the stake ladder (S3) were drawn at noon on the 21 replayed weeks
of 2025 and 2026 and scored on the same weeks. 2024 was not in them. Its limits: the projection of 2024 is trained
on 2023 and the weeks before each game only (the model alone lost to the book there, 0.6887 against 0.6862), the
constants were tuned on seasons that include it, one snapshot a week, the final injury report.

**Result** (`python tools/season_test.py --season 2024`, a new tool that replays a season and prints all of this):

| 2024, weeks 4 to 18 | record | a bet | at the stakes |
|---|---|---|---|
| every pick | 537-371 (59%) | +14% | +49.0 units on 305 (+16.1%) |
| A | 12-5 (71%) | +24% | +4.0 on 17 |
| B | 170-92 (65%) | +21% | +27.3 on 131 |
| C | 355-274 (56%) | +11% | +17.7 on 157 |

The order holds in both halves of the season (B 66% and 64%, C 56% and 57%), a profit at the stakes in 13 of 15
weeks, a worst week of -1.6 units, and the ladder beat one size (+16.1% against +14%). DraftKings alone: A 12-5,
B 170-92, C 148-121. Solo Under picks on a flagged line 182-97 (65%), unflagged 76-60 (56%). The engine against
the book on 4,543 closing lines: +0.0051 (t +2.2), better in 12 of 17 weeks. The book-share flag with no model:
1,037-757 (58%, +5.7% a bet) against 239-224 for the rest, ahead in each of the 18 weeks; weaker than in 2025 and
2026 (63% to 66%) because in 2024 four solo lines in five carried the flag.
What it does not show: an A is rare there (one a week; 7 a week in 2025-26), so 12-5 says little, and locks were 2-2.

Three seasons of replays under today's rules: 1,474-940 (61%); A 118-40, B 380-198, C 976-702.

**Alternate lines, sampled** (week 9 of 2026, DraftKings, 2,219 prices): Over-only ladders, no Under. All Overs
on them: combined hit 43% where the prices imply 45% (-5.7% a bet), solo 36% against 40% (-13.8%). The hole cannot
be bet there and their Overs lose: off the December plan (rejected register).

**Also:** `tools/season_test.py` is in the repo so this can be repeated by any session. "The December exploration"
above is the plan for the 20,000 credits of 12-01 to 12-10, and a scheduled task wakes the owner's session for it on
12-01. Open issue 7: the key ends on 12-10. No rule changed in this entry.

### 2026-11-10, noon (the grade and the stake rebuilt on what two seasons of lines show; no solo Over on a flagged line)

Owner: "Take creative liberty. I trust you to do whatever you think is best to ensure the model is easiest to bet
and gives us the best return." The freeze is lifted for this entry (R4). Week 10 has no line yet, so the engine's
live record starts under these rules. Everything below was decided on the 21 replayed weeks of the entry before
(2025 weeks 4 to 18, 2026 weeks 4 to 9) and the 27 weeks of closing lines behind them.

**What the replays said about the old rules.** A picks won (72%); B and C were the same bet (60% each): the size
of the cautious edge, which set B against C and the stake, ordered nothing, and the stakes returned what one size
did. One thing did order every kind of pick in every stretch: the book's own solo share (open issue 15).

| the engine's picks, 21 weeks | 2025 wk 4-11 | 2025 wk 12-18 | 2026 wk 4-6 | 2026 wk 7-9 | all |
|---|---|---|---|---|---|
| solo Under, flagged line | 186-83 | 67-33 | 23-12 | 40-13 | 316-141 (69%) |
| solo Under, unflagged | 87-60 | 72-51 | 15-22 | 33-32 | 207-165 (56%) |
| solo Over, flagged line | 1-3 | 4-6 | 1-5 | 2-5 | 8-19 (30%) |
| every other pick | 128-83 | 181-103 | 57-42 | 48-35 | 414-263 (61%) |

**Changed** (decisions H1 and S3):
1. **Grades.** A: a solo Under pick on a flagged line (the book's solo line 58%+ of its own combined line) that is
   also a sleeper, checklist clear. B: any other solo Under pick on a flagged line. C: every other pick.
2. **No solo Over pick on a flagged line.**
3. **Stakes by grade:** A 1 unit, B 0.5, C 0.25; caps of 5 a game, 20 a kind a day, 25 a day as a safety net.
4. **The site:** the board sorts by grade first; the legend, the card's stake line, the locks box, the glossary and
   "Rules on trial" say the rules above; the replay record is the one under them.

**Replayed under the new rules** (`res/v1_25`, `v1_26`), against the rules of this morning:

| | before | new rules |
|---|---|---|
| picks | 945-588 (62%) | 937-569 (62%) |
| A / B / C | 134-53 / 433-283 / 378-252 (72%, 60%, 60%) | 106-35 / 210-106 / 621-428 (75%, 66%, 59%) |
| A, B, C a week | 9, 34, 30 | 7, 15, 50 |
| locks | 43-17 | 38-12 |
| units at the stakes | +143.1 on 719 (+19.9%) | +131.0 on 560 (+23.4%) |
| 2026 weeks alone | +10.7 on 166 (+6.5%) | +25.4 on 135 (+18.8%) |
| weeks with a profit at the stakes | 18 of 21 | 20 of 21 |
| worst week | -4.5 units | -0.1 units |
| DraftKings alone, A / B / C | 85-28 / 259-168 / 251-173 | 65-18 / 117-61 / 409-279 |

Fewer units are out (27 a week against 34), so the total won is a little lower and the risk lower still; the unit
is the owner's to size. 99% of stakes are exactly 1, 0.5 or 0.25.

**Tested and not adopted** (rejected register): the combined weight at 0.5 (more picks for less a unit, and a loss
on the 2026 weeks), and a wider A.

**What this is not.** The flag is confirmed out of sample twice; the grade built on it, the Over block and the
ladder were drawn on the same 21 weeks they are scored on. 2025 was a soft year for the books (open issue 1), the
replays read one closing snapshot a week with the final injury report, and the best price is across three books.
Weeks 10 to 13 decide: each rule has its number under "Rules on trial" and its revert in the register.

**Validation.** Smoke test 180 of 180 (the grade check now tests H1 on a synthetic board that carries flagged solo
lines; the stake check tests the ladder and the caps). A real daily in a scratch copy: clean, the site's data
carries the rules, the page renders with no script error. Replays of both seasons on the final code: the table
above. The Test workflow on GitHub read after the push.

### 2026-11-10, 11:40 am (last season's lines: the edge holds on 2025; one more flag dropped; a final validation run)

Owner: "put the solo share fix in before week 10. Then use the key to pull historical odds and gain better
insights. Then a validation run at the end." The solo share fix was already live (commit 0d45764, 11 am).

**Fetched** (`run.py history --season`, new): the 2025 season's closing lines, weeks 1 to 18, an hour before each
kickoff: 7,784 prices in solo and combined, 1,759 in assists (`data/odds/2025`). 2024 was probed and is there
(open issue 23). Credits: 7,482 left of 20,000.

**How it was tested.** `tools/replay_five.py` on each week of 2025: the projection rebuilt from the games before
that week (corrector, spread and levels refitted on those games only), priced and picked by the live functions,
graded on the box scores. No pricing rule, weight, grade or candidate had seen 2025: all were chosen on weeks 7 to
9 of 2026. What is not clean: the projection's constants (shrinkage, factors, the new solo share) were tuned on
seasons that include 2025; the injury report is the final one; one snapshot a week.

**1. The engine against the book, 2025** (3,843 decided closing lines, weeks 2 to 18): book 0.6878, model alone
0.6707, engine 0.6734: +0.0143 (t +5.5), better in 16 of 17 weeks; solo +0.0219 (t +3.9), combined +0.0114
(t +4.1), assists +0.0098 (t +3.7). The model's level was right (actual over projected 0.989 solo, 0.999
combined) and the books' lines were high: the box score came to 0.936 of the solo line and 0.972 of the combined
line; Overs hit 41% on solo and 44% on combined where the books' prices say 50%. That is the edge: the books shade
tackle lines up, as the public bets Overs, and the model does not.

**2. The picks, 2025 weeks 4 to 18:** 726-422 (63%), +260.9 units at 1 a bet, +132.4 on 553 staked; a flat profit
in 14 of 15 weeks. A 96-39, B 355-209, C 275-174; locks 35-14. With 2026 weeks 4 to 9 (219-166): 945-588 over 21
weeks, DraftKings alone 595-369. By kind: solo Under 523-306, combined Under 146-85, assists 195-117, combined
Over 44-37, solo Over 37-43. Open issue 1 holds the reading and its limits.

**3. The book-share hole, 2025:** 609-363 (63%, +14% a bet), up in 16 of 18 weeks, against 392-343 for the rest
of the solo board. Second out-of-sample confirmation (open issue 15, with the split of the engine's own picks).
Part-time and Rotowire's confirmation added nothing over the season and the hot flag failed again (rejected
register). The card now carries the one flag.

**4. The weight** (open issue 22): solo 0.65 confirmed on 25 weeks; combined 0.35 probably low, not changed.

**5. Changed in the code.** The part-time flag is off the card. A look-ahead in the replays is closed:
`upcoming_rows` read each offence's latest starting quarterback and back of the whole season to set the
"opponent's starter is out" flags; it now reads the weeks before the one projected (no effect on a live week,
none on the replayed picks of 2026 weeks 4 to 9). The "Rules on trial" lines quote the 21-week numbers.

**6. Validation run, on the final code.** Smoke test in the clean environment: 180 of 180. A real daily in a
scratch copy: 708 projections for week 10, level for lined players 1.008, the scoreboard on 2,567 closing lines
+0.0081 (t +2.7), no error. Replay of 2026 weeks 4 to 9: 219-166, each week identical to the record published
at 11 am (`data/retro_five.json` rewritten from it). Replay of 2025 weeks 2 to 18 in three markets: section 2.
The Test workflow on GitHub read after the push.

Scripts: scratchpad `replay_season.py`, `res/h30_holes25.py` to `h34_weight.py`; replays `s25f` (2025), `rn9` (2026).

### 2026-11-10, 11 am (the season's past lines fetched; the solo share corrected; one hole confirmed, one flag dropped)

Owner: "I gave you a brand new API key. 20,000 credits, with historical odds data. Run whatever historical tests
you want for this season to improve model prediction and find any other discrepancies we can correct and any holes
in the books lines that we can win on." And, of the site's banner ("169 credits to spend"): "is it right or no?"

**The banner was wrong.** It repeated the count of Monday's last pull, made with the old key. `write_site` now asks
the keys at every daily and pull (a free call; commit ea7ec87). The "Check odds keys" workflow read 20,000, and
15,414 after the fetches below.

**What was fetched** (`run.py history`, extended: it finds a past week's games in the feed, takes a snapshot per
game any number of hours before kickoff, and can save early looks apart in `data/odds_early`): the closing lines
(an hour before kickoff) of weeks 1 to 6 in three markets, 3,620 prices, into `data/odds`; the same weeks 16 hours
before kickoff in two markets; week 8 at 96, 72, 48, 24 and 6 hours as a timing sample. None of weeks 1 to 6 was
seen when the rules, the weights or the candidates were chosen (weeks 7 to 9), so they are an out-of-sample test of
all of them, with two limits: one snapshot a week, and the replay's injury report is the final one.

**1. The engine against the book on weeks 2 to 6** (1,655 decided closing lines; week 1 has no projection history):

| | book | model alone | engine | engine's margin |
|---|---|---|---|---|
| current solo share | 0.6817 | 0.6843 | 0.6779 | +0.0038 (t +0.8) |
| cautious solo share (adopted below) | 0.6817 | 0.6772 | 0.6742 | +0.0075 (t +1.7) |

With the cautious share the margin is positive in each market (solo +0.0089, combined +0.0076, assists +0.0060)
and in four of the five weeks; over all eight weeks +0.0081 (t +2.7). At the best closing price, the engine's side
with a cautious edge of 2% or more went 112-70 (+20% a bet) on weeks 2 to 6. The shadow candidates on the same
weeks: flat weight +0.0003 (t +0.8), centred combined gap -0.0012 (t -2.5: it failed where it was not found), solo
level -0.0001. None is adopted; they keep running.

**2. The picks, replayed** (`tools/replay_five.py`, weeks 4 to 6 on the closing snapshot, weeks 7 to 9 on every
pull; weeks 1 to 3 make no pick, a player needs three games):

| | weeks 4 to 6 | weeks 7 to 9 | all six |
|---|---|---|---|
| rules of 2026-11-09 | 94-89, +2.7u flat, -4.1u staked | 117-85, +28.6u, +7.4u | 211-174 |
| with the cautious solo share | 96-81, +11.1u flat, -3.0u on 87.5 staked | 123-85, +32.9u, +13.7u on 78.4 | 219-166, +44.0u, +10.7u |

A picks 14-8 and 24-6; locks 2-3 and 6-0. On weeks 4 to 6 the stakes lost where flat bets won (open issue 18) and
B picks (37-39) did no better than C (45-34): grades and stakes are not shown to order (issue 3). `data/retro_five.json`
now holds weeks 4 to 9 under the adopted rules.

**3. Adopted: the cautious solo share** (decision P6; open issue 16 closed). `SOLO_SHARE_PSEUDO` 25 to 150,
`POS_SOLO_SHARE` to the measured CB 0.66, S 0.57, LB 0.49, DL 0.44. Why: a player's own solo share over a season
is mostly noise, and the model believed it (the hour's search, below). Evidence, in the protocol's order: smoke
test 180 of 180; walk-forward on the final solo projection, regulars, three seasons: -0.0174 deviance (t -5.9),
each season; on this season's lined players 1.224 against 1.235 (weeks 2 to 6) and 1.124 against 1.136 (weeks 7
to 9); the scoreboard and the replay above, better on the weeks it was not found on as well as the ones it was;
a real daily in a scratch copy (708 projections, level and scoreboard as expected). It is a defect in the
projection, so the freeze (R4) allows it; no pricing rule moved. Week 10 has no line yet, so the engine's
out-of-sample record starts clean. Revert: P6.

**4. The level for lined players now reads the whole season.** The line log held weeks 7 to 9 only, so the
combined level (R7) was about 1.03 from three weeks in which combined ran high. Weeks 2 to 6 are added to
`data/lines_log.csv` from the replay (the model's number at each closing line, `pulled_at` marked `-replay`, as
weeks 7 and 8 already were). On the eight weeks the ratio is 1.01: the level for week 10 is 1.008. The site's
"Against the market" table therefore shows eight weeks; its verdict is still read on the weeks since the engine.

**5. Holes in the books' lines, on weeks 1 to 6** (`tools/holes.py`; each was written down from weeks 7 to 9):

| candidate | weeks 7 to 9 | weeks 1 to 6 |
|---|---|---|
| solo Under, book's solo line 58%+ of its combined line | 117-49 | 176-103 (63%, +12%); 4 of 6 weeks up, 2 flat |
| the same, and Rotowire's solo number well under the line | 35-9 | 68-30 (69%, +21%) |
| solo Under, share gap -0.04 or lower | 99-40 | 179-119, but 44-42 without a high book share |
| solo Under, part-time player | 82-40 | 66-47 (58%); 35-33 with neither a high book share nor a gap |
| combined Over, hot player | 75-47 | 36-45: failed |
| solo Under, neither gap nor part-time | 84-81 | 149-153 |

The book's solo share is the signal and it needs no model: where a book sets a solo line that is a large part of
its own combined line, the Under has won two in three, at the early price as well as the last one. Where the
engine also picks the Under: 51-25 and 33-11. As a probability inside the engine it fails (rejected register), so
nothing in the pricing changes. On the card: the "solo share" flag now fires on the book's share (58%+), the "hot"
flag is gone, "part-time" stays. In the replays the flag splits the engine's own solo picks in both halves: solo
Under picks on a flagged line 63-25, on an unflagged line 48-54; solo Over picks on a flagged line 3-10; A picks on a
flagged line 32-8, the rest 6-6. That is the case for a pick rule, and it is a pick rule: frozen (R4), so it is
counted from week 10 under "Rules on trial" (three new lines, rule H1) and put to the owner. Open issue 15 holds
the test.

**6. Also measured, nothing changed.** Lines open about a day before kickoff and barely move after (open issue
20): the Wednesday early look stays as asked but will most likely be empty. Solo Unders at a favourite's price
(1.83 or shorter) went 191-107 on weeks 1 to 6 and 115-58 on 7 to 9: the same lines as the book-share hole, mostly.
Corners' and linemen's Unders in both markets were 57% to 67% in both halves at the best price: a base rate to
re-read with more weeks, not a rule. Combined Unders as a whole: 55% on weeks 1 to 6, 49% on 7 to 9: no base rate.

Smoke test: the synthetic board had no solo line, so no solo-only flag had ever been exercised: a dozen solo lines
added (`tests/fake_data.py`), and the A-grade check, written for the older rule and passing by coincidence,
now tests the rule in force. 180 of 180. Scripts: scratchpad `res/h20_oos.py` to `h26_early.py`, replays `rn6`
(old share), `rn7`, `rn8` (adopted).

### 2026-11-10, 10 am (an hour's search for signals: the solo share is far too extreme; nothing changed yet)

Owner: "use one hour of real time to dive deep into the analytics and find any other signals." Sixteen parts,
9:08 to 10:08 am. Four seasons of the model's own out-of-sample projections where a question could be put to
them (thousands of games), the closing lines of weeks 7 to 9 where it could not (three weeks: hints only).
Scripts: scratchpad `res/h1_scan.py` to `h17_poslevel.py`. Nothing in the model changes in this entry.

**1. The solo share is over-dispersed (the finding of the hour; open issue 16).** Given the tackles a player
makes, the share that are solo regresses to his position's norm far more than the model allows. Regulars,
2024-26, by the model's share: it says 0.72 and they post 0.68; it says 0.46 and they post 0.49. A calibration
slope fitted walk-forward is 0.3 to 0.4 where 1.0 would be right. The share is built as his solo tackles plus 25
tackles of a position prior (`config.SOLO_SHARE_PSEUDO`, chosen on absolute error in round 5) and the priors
themselves are high (CB 0.72 against 0.67 posted, S 0.62 against 0.58, LB 0.52 against 0.49).
- As it would ship (the position's share from earlier seasons as the prior, 150 tackles of it): solo given
  combined -0.0375 (t -6.7) on 5,986 regular games, better in each season (-0.038, -0.029, -0.057); the solo
  projection itself -0.0174 of Poisson deviance (t -5.9). Counting last season's tackles at half weight too:
  -0.0194 (t -6.1). The surface is flat from 100 to 250 tackles; 25 is worth nothing (-0.0000).
- For scale: the whole rebuild of 2026-11-09 was worth -0.0089 on the combined projection.
- Against the books (384 solo lines, weeks 7 to 9): the model's typical miss 1.433 with the cautious share against
  1.451 now and 1.475 for the line itself; where the model sits 0.75+ under the line the Under went 28-10 against
  35-15 now. Replay through the engine with 150 tackles and corrected priors: 123-86, +32.2 units flat, +13.6 at
  the stakes, A 24-6, locks 6-0, against 117-85, +28.6, +7.4, 25-6, 8-1 now: no harm, a little better (three weeks).
- Not adopted here: the hour was for finding. Recommended to the owner as the next change.

**2. Corners and safeties: the combined projection is too spread out (open issue 17).** Top fifth of corners by
projection: 0.914 of projected over three seasons (t -4.0, each season); safeties 0.938 (t -3.7); the bottom
fifths 5 to 9% over. And safeties run over against an opponent the market expects to score (25.5+ implied points:
+5.6%, t +3.1, each season). A slope for the two positions plus the opponent's implied points for safeties,
fitted on earlier seasons: regulars 2025-26 -0.0085 (t -3.1), 2025 -0.0093, 2026 -0.0066. Six variants were tried
and it is worse for defensive backs expected at 50 to 80% (+0.016, t +1.7), so it is a candidate, not a result.
Linebackers need nothing (slope 0.93 to 0.98).

**3. Checked and found sound.** The corrector's weight by position (0.6 is the best or within noise for each; a
higher weight is worse everywhere). The chance the model quotes across the range of lines (within 1 to 3 points
of what happened, 18,000 synthetic lines; a little low on Overs at lines of 2.5 and under, which the two fixes
above address). Part-time players in the model's own history (level: 0.985 to 1.001), so the part-time solo
Under is the books' error, not ours.

**4. Tested and rejected** (rejected register): opponent and game effects on the solo share; an in-season level
by position; the league's recent tackle volume; a correction of the snap forecast's biases; games of prior by
position.

**5. On the books' lines (three weeks; hints).**
- **The books make the same mistake as the model, and their own lines show it.** Where a book's solo line is 58%
  or more of its own combined line, the solo Under went 117-49 (70%; by week 43-14, 42-18, 32-17) against 121-103
  below that, with no model at all: players the lines put at 0.58 to 0.65 posted 0.495. With the cautious share,
  his share 0.10 or more under the book's implied share: 42-10. In `tools/holes.py` as a sixth line
  (`config.HOLES["book_share"]`). It is the same at each book on its own two lines (DraftKings 112-47, theScore
  92-39) though the Under already costs about -131 there, and it is where the whole solo edge sat: under 58% and
  full-time, the solo Under was 71-77. Week 9 alone, the week the board did not go Under: 29-16 against 42-49.
- The two solo flags as a book: 153-72 (68%), +26% a bet, 75 lines a week; by week +38%, +28%, +11%. The edge is
  shrinking: the share the books' lines imply fell 0.583, 0.575, 0.558 while the share posted rose to 0.558.
- Left out one week at a time, the flags add to the book's price in each week (solo); "hot" and "corner or
  lineman" do on combined.
- Combined lines where the model sits half a tackle or more under the line: the Over won 39-21. The model's
  combined Unders have been wrong; the engine already gives combined disagreement little weight.
- A team's lead tacklers went Over 59-37 and Over 28-11 when also hot, but over 2024-25 the model shows no such
  lean (0.98) and the lean is one three-week burst (1.13 in weeks 7 to 9): probably luck, not a hole.
- Nothing in line movement (1,231 series), spread, total, home or away, opponent pace, or the assists market
  (one week of lines).

**Not finished.** The first replay run was stopped at its time limit during week 9; week 9 was re-run alone.

### 2026-11-10, 9 am (a validation pass against outside sources: the formula stands, nothing changes)

Owner: "creative liberty to re-dive into the formula and the things we source... anything to validate it:
injury reports, team sources, online pundits." Six checks, each against something the model did not build.
Numbers for the three tested as inputs are in the rejected register.
1. **An outside projection.** Rotowire's weekly tackle projections (Sleeper's public feed, 2024 to 2026): the final
   projection is far closer to the box score on the same 5,575 regular games (deviance 1.31 against 1.81), and no
   blend helps. The model is not behind what a pundit publishes.
2. **Recent form.** The sweep suggested the model lags hot players. Over four seasons it does not (level within
   1%); no input for it helps. The books' lag on hot players is theirs.
3. **The snap forecast.** Regulars are expected at 92% of the snaps and play 90.5%; the typical miss is 10 points;
   4% play under half of what was expected. Knowing the true snaps in advance would remove 10% of the tackle miss
   for regulars and 14% for players expected at 50 to 80%. So "faster on role changes" is worth a tenth of the
   miss at the very most: real, and smaller than it was pitched on 2026-11-09.
4. **The injury report.** Players listed questionable and expected at half the snaps or more play 3 points fewer
   snaps than expected and make 98.6% of their projected tackles; 1% do not play. The status handling is sound.
5. **Stat crews.** The stadium effect on solo against assisted credit was real through 2025 and is gone in 2026.
   Leaving it out of the solo share stands.
6. **A third box score.** Sleeper's stats feed against the official count we settle on, weeks 7 to 9 (1,361
   player-games): solo equal in 93.4%, combined in 89.1%; 5 of 374 solo lines would settle differently. The count a
   book settles on can flip about one solo bet in 75: open issue 11 stays open until a settled slip is seen.
One new candidate: on solo lines with the share gap or part-time, Rotowire's solo number well under the line too
(times 1.075, at least 0.75 under) went 47-16 (75%) against 104-58 without that agreement; alone, with neither
pattern, it calls nothing (17-14). An outside opinion as a confirmer, never a selector. In `tools/holes.py` as a
fifth line. Scripts: scratchpad `res/n6_outside.py`, `n7_snaps_crew.py`, `n8_pundit_lines.py`, `ext/`.

### 2026-11-10, 8:45 am (the part-time and hot flags on the card)

At the owner's request the two candidates of the sweep are named in a card's "why" where they apply, as the
solo-share gap already was: "part-time" on a solo line (under 85% of the snaps this season) and "hot" on a
combined line (last three games half a tackle or more over his season average). `config.HOLES` holds the two
numbers, shared with `tools/holes.py`. Each clause says it is a measurement on trial and in no grade; no pick,
grade or stake reads them. Smoke test 180 of 180. Revert: remove the two clauses in `model.price_lines`.

### 2026-11-10, 8:30 am (a sweep of the closing lines for other holes: two more candidates, written down before week 10)

Owner, after the solo-share gap: "are there any other holes in the books' lines like that?" Twelve things knowable
before kickoff were cut against the result at the closing line of weeks 7 to 9, solo and combined (about 120
cells). With that many looks some cells are luck: only patterns with 100+ lines, the same sign in each of the
three weeks and a plain reason were kept. Nothing is adopted; `tools/holes.py` scores them with fixed definitions
on any weeks (790 decided lines here, best closing price of the side).
- **Part-time players, solo Under** (under 85% of the snaps this season): 82-40 (67%, +30% a bet); by week 28-10,
  27-12, 27-18. It is not the share gap again: without the gap they went 55-31. Reason: the book's line follows
  his totals; a part-timer's good games came on more snaps than he will get.
- **What is left of the solo board is a coin flip.** Solo Unders with neither the share gap nor part-time: 84-81
  (-0.4% a bet). The "solo Under edge" of weeks 7 to 9 was these two kinds of player, not solo lines in general.
- **Hot players, combined Over** (his last three games average half a tackle or more over his season average):
  75-47 (61%, +21% a bet); by week 21-14, 24-17, 30-16. Reason: the line sits near the season average and trails
  a role that has grown. The model is the other way on these (it damps a hot streak), which may be why it has no
  edge on combined lines.
- Seen and left: corners and linemen combined Under 74-51 (59%); lines of 5.5+ on linebackers and safeties Over
  117-88 (57%), mostly the hot players again (big and not hot: 70-71). No sign at all: the last game alone, games
  played, back from a missed game, how many books post him, how swingy his games are.
Read at the end of week 13 with the share gap (open issue 15): each needs 58%+ out of sample and to beat the rest
of its market before it becomes a rule. Sweep script: scratchpad `res/n5_holes.py`.

### 2026-11-10, 8:20 am (an early look at the week for weeks 10 and 11; the solo-share gap measured and logged)

Owner: "add one early pull for week 10 and 11, and test solo share per player."

**The early look** (`config.OPENER_DATES`, `run.OPENER_SLOT`, `run.slots_on`). Wednesday 10 am Edmonton on
2026-11-11 and 2026-11-18: every game from Thursday to Monday, an "early" pull in the credit budget (about 28
credits each on two markets). It is a normal pull: lines priced, picks logged at the price of the moment. With 500
credits the budget runs every scheduled pull on two markets; the assists trial market stays out (540 needed).
Why: on the replay the price when a pick first appeared beat the closing price of the same line (+29.9 units
against +25.0), and books sharpen prop lines through the week; nothing earlier than Thursday had ever been pulled.
Read after week 11: how far Wednesday's lines and prices sit from the close, and what Wednesday's picks did.
Revert: empty `OPENER_DATES` (it ends by itself after 2026-11-18).

**The solo-share gap** (`config.SHARE_GAP`; `share_gap` on every solo line in `data/lines_log.csv`; a clause in
the card's "why"; in no grade, pick or stake). On the 386 players with both lines at the close in weeks 7 to 9:
- The book's solo line is not a flat share of its combined line, as this log had said: it follows the player's
  own share (correlation 0.59, slope 0.94; mean 0.57). But it follows it loosely, and his own share (shrunk over
  25 tackles) still predicts the share he actually posts beyond the book's (coefficient 0.62, t 2.5).
- Gap = his share minus the book's implied share. Solo Unders at the close with a gap of -0.04 or less: 96-39
  (71%, +25% a bet), in each week: 36-12, 35-16, 25-11. With a gap above -0.04: 136-111, and 46-54 in week 9, the
  one week the whole board did not go Under.
- It is not the model's picks restated: of those 135 lines the model picked 49 (35-14) and passed on 86, which
  went 61-25. The model's solo Under picks without the gap went 35-29 (16-17 in week 9).
Three weeks, one definition tried, thresholds in round steps; the weeks are the unit and all three agree. Not
adopted (the freeze): from week 10 the gap is in the line log, so weeks 10 to 13 score it out of sample with no
further code. Candidate rule if it holds: a solo Under with a gap of -0.04 or less is a pick and an A input.
Script: scratchpad `res/n4_soloshare.py`.

**Validation.** Smoke test 179 of 179 in the clean environment (two new checks).

### 2026-11-10, 5 am (five more ideas tested at the owner's request: none adopted)

The owner asked what else could find better picks, was given five ideas marked "measurable" or "a guess", and
said to do them. Each was tested first; none passed, so nothing in the model changes. Numbers are in the rejected
register (projection inputs; pricing and pick rules).
- Books disagreeing on a line, or on a price: no edge; the books price the half tackle and never beat each
  other's fair chance. Blind, DraftKings' Unders returned +2.3% and theScore's -0.8% over weeks 7 to 9.
- The game total as an input: no gain. A backup quarterback for the opponent: the right direction (linebackers
  up 4%), short of the bar. Weather: mixed, and there is no forecast before the game.
- Stale lines after another book moved: 13 cases, 4-9.
Scripts: scratchpad `res/n1_features.py`, `n2_books.py`, `n3_stale.py` (not in the repo). Also from the morning
check: the first daily on the new code ran clean at 4:16 am; the four-leg parlay given to the owner on Monday
night after kickoff lost on paper (Bishop and Turner Unders won, Cashman had 6 solo against 5.5).

### 2026-11-09, 10:45 pm (a free check of the odds keys)

**What.** `python run.py keys` and a by-hand workflow, "Check odds keys" (`.github/workflows/keys.yml`): for each
key name in `config.ODDS_KEY_ENV`, whether a secret is set, whether the Odds API accepts it, and the credits left.
It uses the free events call and prints names and counts only. **Why.** The owner added a key and asked whether it
works; until now the only way to find out was to wait for a pull. **Revert.** Delete the workflow and the command.

### 2026-11-09, 10 pm (six changes at the owner's instruction, before week 10 has a line)

Owner, after asking what would find better hits and being given six ideas: "do 1-6." That lifts the freeze for
these six and nothing else; it stands again until 2026-12-08. All of it is live from week 10's first pull, so
`config.ENGINE_LIVE` still marks the first week none of it was chosen on. Each was measured first; two of the six
did not turn out the way they were pitched, and the entry says so.

1. **Role news rebuilds the projections at pull time** (`run.role_news`, `run.reproject_on_news`). A pull already
   refreshed each player's status, but a starter ruled out after the 4:15 am run only made his own lines a pass:
   his backup's snaps and the next-man-up flag waited for the next morning. Now a player expected at 30%+ of the
   snaps who is newly out (or newly cleared), on a team that has not kicked off, triggers one rebuild (the daily,
   90 seconds, no credits) before the pull prices anything. No evidence yet beyond the mechanism: it cannot be
   replayed (the week's injury report in the replay is the final one). Revert: remove the call in `cmd_odds`.
2. **A level for lined players, combined only** (`config.LINED_LEVEL`, `evaluate.lined_level`). Pitched as "fix the
   lean toward Unders". Measured: on combined the model ran 3 to 4% under the box score of lined players in each of
   weeks 7, 8 and 9 (actual over projected 1.03, 1.04, 1.04), so each week's combined numbers are now multiplied by
   that ratio from the season's earlier lined games (shrunk, clipped to 0.9 to 1.1; 1.018 for week 10). On solo the
   pitch was wrong: the model ran 9 to 14% HIGH in weeks 7 and 8 and 7% low in week 9, so the solo lean to the Under
   is the book's line, not the model's level; a solo level would only chase the last two weeks. Solo is left alone
   and its level runs in the shadow.
3. **A weight per market: 0.65 on solo, 0.35 on combined** (`ENGINE["beta_by_kind"]`, `model.engine_betas`; assists
   stay at 0.5; the cautious chance is half the weight). Log-loss on the 880 closing lines 0.6833 against 0.6845
   flat (book 0.6913), and better on the rebuilt projection's numbers too (0.6853 against 0.6864). Combined picks at
   the close fall from 52 to 16: the model has no edge to claim there. The flat 0.5 runs in the shadow.
4. **An A is a pick that is also a sleeper on the same side** (`ENGINE["a_rule"]`, `model.engine_grade`), checklist
   clear. Was: cautious edge 2%+ and the model's own chance 70%+. Replay under the old rule: picks that were also
   sleepers 19-7, the rest 84-78; the old A 10-6, of which four wins were the mis-posted Sam Williams lines (6-6
   without). Rule 0 holds: a sleeper is the model's number against the line, and a book that agrees more moves the
   line toward the model and ends the sleeper. The old A is counted beside the new one ("Rules on trial").
5. **When to bet: no rule.** Pitched as "we lose to the close, so bet later". Measured on the replay's picks whose
   line was the same at the close (186): +29.9 units at the price logged against +25.0 at the closing price, so
   the price when a pick first appears has been the better one. Picks first logged inside two hours of kickoff
   went 13-7. Nothing supports waiting. The no-vig closing-line value reads -2 points on the same picks, which
   contradicts the prices themselves: open issue 12.
6. **A line that does not fit the player is not a pick** (`ENGINE["misfit_model"]`). Only one book posts the
   player and market, and the model's own chance is 93% or more: theScore's "Sam Williams" (8.5 tackles + assists,
   4.5 solo, for a rotational lineman projected 2.6) was the top lock of weeks 8 and 9 in the replay. The card says
   to check the name on the slip.

**Replay of weeks 7 to 9 with all six** (in-sample for all of it, and the sleeper rules were themselves found on
these weeks): 117-85 (58%), +28.6 units at one a bet, +7.4 on 73.3 at the stakes; A 25-6, B 34-36, C 58-43; locks
8-1; solo Unders 71-47; combined 16-12. Before: 103-85, +17.7, -0.0 on 69.1; A 10-6; locks 6-4. An A record of
25-6 on the weeks its rule was written from is a description, not a forecast: expect far less.

**Validation.** Smoke test 176 of 176 in the clean environment (new checks: the weights, the A rule, the level on
earlier weeks only and on the number before any level, role news). Real daily in a scratch copy, clean.

**Revert.** `config.py`: drop `beta_by_kind` (flat 0.5), `a_rule="model"`, `misfit_model=2`, `LINED_LEVEL` kinds
empty; remove the `reproject_on_news` call. Or restore `config.py`, `pipeline/` and `run.py` from commit 54f182d.

### 2026-11-09, 9 pm (the out-of-sample test written into the code before week 10 has a line; the evidence in plain text)

**What.** Nothing that chooses, grades or sizes a pick changes (the freeze holds). Four additions to how the
model is measured:
- `config.ENGINE_LIVE` (2026 week 10) splits the scoreboard and the record. `evaluate.scoreboard` returns `since`
  (the weeks from the engine's first week on, by themselves) and `grade.grade` returns `era` (the record of those
  weeks: by grade, side and market, position and week, calibration of the win chance and of the model's own
  chance, units at one a bet and at the stakes).
- The conditions of the decision register are counted by the daily: E2 and S1 on the scoreboard's weeks since the
  engine, E4 (A picks, read at 30), E5 (combined A picks over their first 20; the locks against 70%) and E6 (Over
  picks, re-read at 40) on the picks since. Each shows how far along it is and where it stands.
- The three candidates of open issue 2 are in `config.SHADOW` with their numbers fixed, and the scoreboard scores
  them on every closing line against the engine (`evaluate._shadow`). Their adoption rule is decision R6.
- `data/weekly_five.md` carries all of it in plain text (`grade._evidence_sections`): the scoreboard by week with
  the in-sample weeks marked, tiers, calibration, the shadow, the whole board with no model (how often the Over
  won each week against the book's fair chance), the record since the engine, the conditions on trial, the record
  to date by grade and by side and market, each with its likely range.
- The standing post-mortem's instructions rewritten around that file, the freeze (it measures and records, it
  changes nothing) and one entry a week. `data/cache/blend.json`, a leftover of the retired blend, removed.
- Site, Track record: the "Against the market" verdict is read only on the weeks since the engine (until week 10
  is graded it says there is none); "Candidates in the shadow"; a new section, "Rules on trial".

**Why.** The rebuild promised an out-of-sample test on weeks 10 to 13 and candidates "scored in the shadow", and
nothing in the code told the weeks apart or scored a candidate: both would have depended on someone remembering
to do it by hand, after seeing the results. The site's verdict line was reading a t of +1.9 from the three weeks
the weight was chosen on. And the standing post-mortem cannot read the sealed site: its run of 2026-11-09
stopped after a minute for want of the graded detail. Writing the test down before the data exist is the point.

**Evidence.** Real daily in a scratch copy (90 seconds, no flag); the weekly log and the site read on real data.
Weeks 7 to 9 (in-sample, 880 lines): book 0.6913, model 0.6876, engine 0.6845; the candidates 0.6833, 0.6836 and
0.6833. With the split moved to week 8 or 9 as a check, the weeks since and the conditions count as they should.
Smoke test 174 of 174 (five new checks: the split, each candidate on lines with a known answer, the record since
the engine, the weekly log's sections, the site).

**Rehearsed before it runs live.** The forced live grade and the daily, each on real data in a scratch clone with
this code: both clean; the first writes `data/settled.csv` (617 bets settled on the official count). No pick was
logged for Monday night's game of week 9, so the first live run of the new grader is Tuesday's daily. The ticker
run in progress predated the hand-over step, so the next run was started by hand (see the pitfalls).

**Revert.** Remove `ENGINE_LIVE` and `SHADOW` and the blocks that read them; no pick is affected either way.

### 2026-11-09, 7 pm (the test on GitHub had been failing for a week, unread)

**What.** `PyYAML` and `scipy` added to `requirements.txt`, pinned. The smoke test now reads every import in the
code and in itself and fails when a library is not in that file. The Test workflow also runs when
`requirements.txt`, a workflow file, `tools/` or `docs/index.html` changes. Protocol step 7 added: after a push,
read the Test workflow's result.

**Why.** Checking the rebuild's push, the Test workflow turned out to have failed on every push since 2026-11-03
(runs 50 to 79): `ModuleNotFoundError: No module named 'yaml'`. The smoke test has parsed the workflow files with
PyYAML since 2026-11-02, the library was never in `requirements.txt`, and it is installed on every machine the
test had been run on by hand, so it passed there. The pipeline itself never imports it, which is why the ticker
and the daily kept working. For a week the only run of the test on a clean machine was red and nobody read it;
the rebuild was pushed under the same red check (its code had passed the test locally, 168 of 168). `scipy` is
imported by the backtest since the rebuild and arrived only as a dependency of scikit-learn.

**Evidence.** Reproduced in a clean Python 3.12 environment built from `requirements.txt` alone, as the runner
does: the same error at the same line. With the two lines added: 169 of 169 in that environment.

**Revert.** None needed; removing either line turns the test red.

### 2026-11-09, night MST (the rebuild: one chance per line, the slate sized as one book, the projection judged on regulars, the memory restructured)

Owner, after the review of that evening: "Take full creative liberty in how to make this the most rigorous model
and scientifically optimal model to estimate tackle lines for the nfl, adjust the memory file as needed." Evidence
for everything below is Research round 11; each rule's revert condition is in the decision register. Live from the
first pull of week 10 (Thursday 2026-11-12); the picks of week 9 were made and are graded under the old rules.

**Pricing (`model.price_lines`, `config.ENGINE`).** One chance per line: the book's fair chance moved half of the
way to the model's own, in log-odds. Retired: the blend of the model's number with the raw line, both level
corrections, the shrink of the claim toward 50%, the 55% claim floor, the 6% and 10% return bars, the fade above a
20% return, the segment correction, the hand-weighted lock score. A pick is a line whose bet still breaks even
with the model's disagreement counted at a quarter (the cautious edge); a lean has an edge only at half and is
never staked. Grades from the cautious edge and the model's own chance; the lock score is the model's own chance.
A grades and locks are open to combined tackles again. A one-sided price is priced against the books quoting both
sides of the same line, or passed.

**Stakes (`grade.size_stakes`, `config.STAKE`).** A quarter of Kelly at the cautious chance, then the slate sized as
one book: divided for the number of picks of one kind that day, capped per game (4), per kind a day (10) and per
day (15). Every line of the same bet carries the bet's scale.

**Projection (`config.FACTORS`, `config.GBM`).** Seven factors out of the factor model (stat crew, snap trend,
run/pass mix, bye, injury report, role shift, the vacancy rule), each still an input to the corrector; the
next-man-up flag added to the corrector's inputs; the corrector's weight tested at 0.8 and kept at 0.6 once judged
on regulars; the solo share read without the stat-crew adjustment. The spread is fitted by maximum likelihood
around the out-of-sample final projection, with the new-role addition fitted too.

**Next man up.** Never a lock or an A, and an Under on a next-man-up backup expected under 60% of the snaps is not
a pick: the final projection runs 16% low on exactly those and no correction holds.

**The backtest (`pipeline/backtest.py`).** It now certifies the number the board prices with: the final projection
out of sample, a fold a season, in Poisson deviance; every factor tested each morning on the rows it moves, for
everyone and for regulars, with weeks as the unit; flags on the site when one fails or one that is out passes.
Calibration and the distribution's shape are checked around the same projection.

**Evaluation.** The scoreboard against the book's fair close on every logged line (`pipeline/evaluate.py`; Track
record, "Against the market"). A likely range on every record. A bet settles once (`data/settled.csv`). The line
log keeps the engine's read of every line (`pipeline/linelog.py`, renamed from `blend.py`). Same-game parlays are
recorded at an estimated price and flagged; parlay legs must be picks.

**Game logic on a card.** Each signal's effect is now measured on the final projection (the number rebuilt with
that signal neutral, through both models), not read off the factor model's multipliers, which the corrector mostly
overrides.

**Odds credits (`run.credit_budget`, `run.govern`).** Before each pull the rest of the month is priced and what is
worth most per credit is kept: the pull an hour before kickoff, then the Thursday and Monday looks, then Saturday
night's, then the rest, then the assists market. A look left out is marked "saved" on the site, which also warns
when credits are short.

**Site.** Cards, the "Why" box, the legend and the glossary rewritten around the win chance, the cautious edge and
the stake; the Model check tab shows the fold-by-fold final projection and the daily factor tests.

**Memory.** This file rebuilt as the current specification plus registers; the history moved unchanged to
MODEL_LOG_ARCHIVE.md; the Patch log tab reads both (and now shows research rounds 8 to 10, which its parser had
been skipping). `tools/replay_five.py` rewritten to run the live functions with the clock set to each pull; the
site's "replayed under the current rules" block was re-run with it for weeks 7 to 9.

**Corrected along the way.** The corrector weight was first raised to 0.8 on every defender's score and put back to
0.6 when the test was restricted to regulars. The replay crashed on a pull with nothing priceable (a missing
column); fixed with a check. Stakes on a second line of the same bet could exceed that line's own sizing; fixed.

**Validation.** Smoke test 168 of 168. Real daily in a scratch copy: two minutes, no flag. Replay of weeks 7 to 9:
103-85 (55%), +17.7 units at one unit a bet, -0.0 on 69.1 units at the stakes, locks 6-4, A 10-6; as bet those
weeks were 200-183, +0.1 units. In-sample for the pricing weight; see the table in Research round 11.

**Revert.** Whole: restore `config.py`, `pipeline/` and `docs/index.html` from commit 35a5f13. Piecewise: by the
decision register. Frozen until 2026-12-08 either way, unless a defect is found.

## Ideas backlog

Never tested; each with what would justify it. Anything tested and dropped is in the rejected register above.

- **Play-by-play opportunity model with participation data** (round 1; backlog): tackles per opponent play while on the field, split run/pass, and man-coverage share for corners; needs nflverse participation data published for 2026 again.
- **Two-season player prior** (round 1): weighted by games, instead of last season only; listed with the avenues that need data not loaded yet.
- **Solo-share crews with multi-season venue pooling** (round 1): with neutral-site handling; the crew is unknown overseas.
- **Neutral-site solo lines as C grade or skipped** (backlog): the crew is unknown there; needs a count of such games.
- **Alternate tackle lines** (round 8; backlog): first to test; pull closing lines for two or three weeks and run the blind-board test; double the credit cost per game.
- **Sacks market** (round 8): third to test, from PFR pressures; build only where a bias shows in two or three weeks of closing lines.
- **Receptions market** (round 8): worth a closing-line pull to measure, not worth a model before that.
- **Role-change signal and role flags the book may be slow on** (backlog; round 10): signal 0-3 so far, judge at 30 picks; flags watched until any flag reaches 30 lines.
- **A corrector for solo tackles** (backlog): justified if the solo-line record by grade lags the combined-line record.
- **No price for a questionable player with a Friday "did not participate"** (backlog): needs the daily report timing, which nflverse does not carry.
- **Rain by measured precipitation** (backlog; round 7): Open-Meteo ERA5 archive, mm per game hour at each stadium, to test real downpours separately from drizzle; the API refused requests on the day.
- **Line-level calibration for low lines** ("Why the Overs miss"): on lines of 2.5 or less overs hit 34-36% against a model 45% and a market 51%; pending more weeks.
- **Outside trigger for the scheduler** (changelog 2026-11-03; open issues C2): a cron service or heartbeat that starts a run when none has committed; needs a token the owner would create.
- **Per-pull count of unmatched defensive injury listings** (risk pass): noted as on the backlog.
- **A depth chart read the same morning for the next man up** (round 11): the projection does not know which backup takes a vacated starter's snaps (16% low on the ones it expects under 60%); a same-day starter listing by position would say.
- **A corrector trained or weighted for regulars only** (round 11): the best corrector weight differs between regulars (0.4 to 0.7 by fold) and everyone (0.5 to 1.0); the players who get lines are a fifth of the rows it learns from.
- **A design-test command** (round 11): `backtest.walk_forward_final` and `backtest.paired` are in the code, but comparing two designs still takes a scratch script; a `run.py` command that prints the regulars' table for a set of factor switches would make the full test one line.
- **A better no-vig split** (review, A12): the proportional split is off by about a point at very short and long prices; test a power or log-odds split on the scoreboard once there are more lines at long prices.

## Known pitfalls

- Codespaces secrets are invisible to Actions. Only Actions secrets work.
- A library the pipeline imports must be in requirements.txt; the runner installs only that file (the seal step
  failed on `cryptography`, 2026-11-02). A step that protects published output must stop the publish when it fails.
  The same holds for a library only the test imports: `PyYAML` was missing from 2026-11-03 to 2026-11-09. The smoke
  test now checks every import against the file.
- **Measure a pitch before building it.** Two of six ideas given to the owner as likely gains were wrong once
  measured (2026-11-09): "the model leans Under, fix its level" (on solo the model was high, not low, in two weeks
  of three) and "we lose to the close, bet later" (the logged price beat the closing price). Say what is measured
  and what is a guess when proposing.
- **A book's line for a name is not always that player's line.** theScore posted a linebacker's numbers under "Sam
  Williams" two weeks running; the model matched a lineman and called it 98%. A line far outside a player's range
  that only one book posts is a data question before it is an edge.
- **A verdict read on the weeks a rule was chosen on is not a verdict.** The site's "Against the market" line read
  a t of +1.9 from weeks 7 to 9, the weeks the engine's weight was fitted on. A split that is only in the log's
  prose gets forgotten the first good week: it is in the code now (`config.ENGINE_LIVE`), and the candidates'
  numbers are fixed before their test (`config.SHADOW`).
- **Why another session failed is in its transcript, not in its task's record.** This file said for a day that the
  standing post-mortem had no repository attached; its run shows a checkout and a different cause (the evidence it
  was sent to read is sealed on the site). Read the run before writing the reason down.
- **A run in progress keeps the workflow file it started with.** The hand-over step ("a run that ends starts the
  next") was pushed at 5:05 pm on 2026-11-09 while a ticker run that began at 2:38 pm was beating: that run could
  not hand over, and its successor was started by hand at 7:31 pm. A change to a workflow is live only from the
  next run that starts; after one, check that a run started since.
- **Site tables do not wrap** (cells are `nowrap`): a column of sentences pushes the rest off the screen. Rows of
  prose go in the stacked list (`.trials`), not in a table.
- **A test that passes by hand is not the gate; the run on the clean machine is.** The Test workflow failed on every
  push for a week (2026-11-03 to 2026-11-09) while the same test passed wherever it was run by hand, and nobody
  opened the red check. After every push, read the workflow's result (protocol step 7).
- A colon inside a workflow step name breaks the YAML, and GitHub then reports the workflow as having no triggers:
  every schedule and manual run stops without an error anywhere visible. The smoke test now parses every workflow
  file (found 2026-11-02 after the seal step was added; about three hours of pulls lost).
- A pick or parlay handed to the owner must come from the pricer's output (claimed chance, return, pick), never
  from the raw model chance: the segment correction and the bars are the difference between a play and a pass.
- Two feeds that both print a player's name do not print the same name (PFR "Cameron Lewis", league "Cam Lewis").
  Join by id wherever one exists; a name join silently drops the player and the model prices him blind.
- A game's plays faced cannot be forecast beyond the spread (correlation 0.15, residual 7.7 plays on 50). It is the
  largest explainable cause of misses and is noise to the model; do not spend another round on pace features.
- Open-Meteo's free APIs share a daily request limit per network; from this machine's network the limit can already
  be spent by others. Cache every response and treat a refusal as "try tomorrow", not as no data.
- A slate with several kickoff waves (Sunday noon, 2 pm, 6 pm Edmonton) needs pulls up to the last wave; a schedule that stops at the first wave prices the late games on stale lines.
- A week's hit rate is the market's base rate plus our lift. Judge a kind of pick on lift against every closing
  line of that kind (the luck check), never on the record alone: in week 7 every kind of pick hit at exactly the
  board's rate, and the record looked like skill. The segment correction learns hit rates, so after a week of
  board-wide drift it is partly learning the drift; read it beside the luck table.
- The Plays tab is the current board. Anything settled (a parlay whose games are over, a graded pick) belongs to
  the Track record tab only; a weekly file rendered whole will show last Thursday's bet on Saturday.
- A side table that only has a row when the player recorded something (PFR advanced defence, any "box score of
  events" table) conditions on the outcome. Merge it onto the full list of games played before computing any
  ratio from it, and treat a missing row as unknown, not zero. Research round 5's pressure factor was born of
  this and died in the backtest.
- Outside feeds carry their own vocabulary: ESPN's team codes (WSH, LAR, JAC) and statuses ("Injured Reserve",
  "Suspension", and "Active" for a player with a note who plays) must be translated before a merge, and an
  outside status may only raise severity, never lower it, because the two reports are not written at the same time.
- FantasyPros' projection pages embed only the top ten players per position; the full table needs their API key.
  The cross-check covers the high-volume names (the ones with lines) and no one else; do not read a blank as
  "the consensus disagrees".
- `el()` on the site must skip `undefined`/`null`/`false` attribute values: `setAttribute("open", undefined)` writes
  the string "undefined", which is truthy for a boolean attribute.
- A pick's claimed probability is biased upward by the act of picking (the biggest disagreements with the market
  are chosen, and the biggest disagreements are mostly error). Judge claims on hit rates after selection, and keep
  "expected return" as a threshold, not a confidence source.
- Anything priced hours after the morning run must re-read what can change in hours: the injury report (done),
  and ideally the depth chart. A cached projection is a cached status.
- A statistic that is priced must be validated on its own. Solo lines were half the picks and the solo side had
  no backtest row and no dispersion of its own until 2026-10-30.
- An Over "fading" a low game is not a signal. A low game predicts lower (the regression table says so); only the
  Under after a big game in a settled role has evidence behind it.
- A season average is only evidence about a player's current role, and a per-game base can only shade it. The
  per-snap base (round 4) is what lets the model say what a player does when his snaps change.
- A season average is only evidence about a player's current role. When his snap share just jumped (trade, injury
  ahead of him, a benching behind him), every history-based number (average, outlier test, consistency) describes
  someone else. Check the role before trusting the log; the week 8 Thursday post-mortem is the case study.
- GitHub disables scheduled workflows in a public repo after 60 days without a push, and a plain push does not
  re-enable them (only the Actions tab, the API, or a commit that edits the cron line does). The daily run log
  commit and `keepalive.yml` exist for this; do not remove them as "noise". Pushes made with the job's own token
  never trigger other workflows, so the bot's commits cannot re-enable anything themselves.
- GitHub did not register the scheduled workflows on the first push to the empty repo; a second push to the
  workflow files fixed it.
- Cron times are UTC. Alberta does NOT leave daylight time on 2026-11-01: the province moved to permanent UTC-6
  ("Alberta Time", in tzdata 2026e as "CST"). Pull slots are defined in Edmonton local time through zoneinfo, so no
  cron changes; `run.py` guards against a runner with stale zone data by pinning UTC-6 if the zone disagrees. The
  daily job at 11:15 UTC stays 5:15 am all year.
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
- GitHub scheduled runs can stall for hours: on Saturday 2026-10-31 the half-hourly pull job did not run between
  8:38 and 10:33 am, so the 9 am pull was fired by hand. The job now has a second cron on the quarter hours; slots
  are served once, so the two never double-pull. If both stall, run "Pull tackle lines" by hand from the Actions
  tab: a late run still serves every unserved slot.
- GitHub scheduled runs drift by up to half an hour and some are skipped; a job that keys off "is it 5:30 now"
  misses slots. Key off "has the 5:30 slot been served" instead.
- The smoke test copies the repo into a temp dir; it must skip live data (`data/odds/<season>`, `data/picks.csv`,
  `data/cache`, `data/parlays.csv`, `data/retro_five.json`, `docs/data/*.json`) or the synthetic run appends to real
  picks and parlays and the checks fail (fixed 2026-10-26; recurred when parlays.csv first appeared). Any new live
  data file must be added to that list. Also: chain a push on the test's exit code, never on a grep of its output.
- The daily job runs at 7:30 am Eastern; Sunday's box scores are in nflverse by then, Monday night's are graded
  Tuesday.
- Never run two pipeline processes at once on one machine: the corrector's thread pools oversubscribe the cores
  and both crawl (a 50 s smoke test and an 80 s replay both hit a 10-minute limit when run together).
- A replay must build everything (shrink weight, dispersion, level scale, corrector) from games before the
  replayed week. Training on "all finished games" silently includes the week under test once it is graded.
- Any second model must be reported walk-forward (trained on earlier seasons, scored on the latest). In-sample
  numbers for a boosted model are 3x the honest ones.
- The Odds API historical endpoint (`/v4/historical/...`) is a paid-tier feature: the key in use gets 401 there,
  with nothing charged. A past week can only be replayed for a market that was pulled live at the time, so a
  new market's record starts the week it is added to `ODDS_MARKETS`.
- Judge a projection piece on level-matched miss (`mae_cal`) before raw miss. The team-budget factor cut raw
  miss by 0.013 and level-matched miss by 0.0007: it had lowered the level by 4%, which the backtest's level
  calibration already does, and live it would have pinned at its clip because the projection frame holds more
  bench players than a box score. A factor whose mean is not 1 is a level change until proven otherwise.
- A profitable record on one market is not selection skill until the whole board is tested blind: every solo
  Under at the close made +21% per bet in weeks 7 and 8 with no model at all. Compare each kind of pick with the
  blind board before crediting the model (lift), and expect a market-level mispricing to be corrected by the
  books without notice.
- Count a pick once per player, market and side when judging a grade: the same pick logged at DraftKings and theScore
  Bet doubles its weight in a record (week 9's A grades read 10-9 with duplicates, 9-6 without).
- The weekly injury report drops a player once he goes on injured reserve, and ESPN's feed does not always carry him:
  read the league's weekly roster status too (2026 week 9: Edmunds, on IR since week 7, was priced as active).
- A football read that explains a player's past is not a prediction: test it against his own season rate, out of
  sample. Press-man corners have low tackle averages, and those averages regress up, not down.
- A model-vs-line disagreement has a ceiling: past about a tackle (combined model more than 1.0 over the line, a solo
  line more than a tackle above his season median) the book usually knows a role change the history does not show,
  and the signal turns into a coin flip (9-11, 17-16). Any new "model disagrees with the line" signal needs its
  outer limit tested, not just its inner one.
- Count one bet per player x market x side in every record and calibration: the same pick logs at two books and two
  lines. Measure a correction against the claim before the correction. The board is each game's latest pull, never
  the last price of every line ever seen. Join box scores on team and name (norm_name strips Jr/II). One solo
  definition across the model, the grader and the books (official: solo + tackle with assist). Never take a median
  of American odds. A failing step must not stop the steps after it. A stat whose recording drifts across seasons
  (nflverse's tackle with assist: 16% of official solo in 2023, 2% in 2026) must not be pooled into a training series:
  train on the stable part, adjust to the settled count with the current season's rate.
- The week is the unit of evidence: picks in one week share a shock of about 6.5 points of hit rate, so a count of
  picks overstates what is known by a factor of two to three, and a correction with a short memory fits the shock.
- A line is not a mean: the same line at -190 and at +150 says different things. Anything that uses the line as a
  number must use the price with it (the market-implied mean).
- A factor "proved" on synthetic data with the effect planted is not proved; and a difference in average miss in
  the fourth decimal is not a finding without its standard error over season-weeks.
- GitHub's scheduler can drop every scheduled run for half a day: nothing may depend on it alone.
- Two probabilities live on each line: the pricer's (`model_over`, shrunk toward the market by PROB_SHRINK) and the
  claim (shrunk toward 50% by CLAIM_SHRINK, plus the segment correction). The return bars used the first, so a pick
  could clear 6% while its claim did not beat the price. Any bar on "edge" must be checked at the claim.
- A filter that "agrees with the pricer" can select against a model signal: the pricer's EV leans on the book's line,
  so inside the combined-Over sleeper band the +EV rows went 7-10 while the band went 35-21. Test a signal on the
  model's own number before adding the pricer's return as a second condition.
- `picks.csv` gains columns over time (`uncertain` added 2026-10-27); older rows read back as empty, so every use
  of a newer column must `fillna` a neutral value.
- **Judge a projection change on the players who get lines.** The corrector weight of 0.8 beat 0.6 for every defender
  (t -4.5) and was no better for regulars, worse on one fold: the gain was all on part-timers no book prices. It was
  adopted and put back within the night (2026-11-09). The full test reports regulars first.
- **The rows a factor moves are found before the two variants are brought to the same level.** After level-matching
  every row differs a little and a "touched rows" test silently becomes an all-rows test (the first version of the
  daily factor table, 2026-11-09).
- **A board on which nothing can be priced still needs every column** the log, the sizing and the site read: a pull
  of one-sided prices only crashed the pick log in the replay of week 8 (2026-11-09). The smoke test now prices one.
- **A replay with today's code carries today's level fixes.** The rebuilt solo numbers scored worse than the logged
  ones on weeks 7 to 9 mostly because the official-count factor (2.4%) was not in the old ones; compare like with
  like before reading a difference.
- **A pick has several lines.** A stake sized for the bet's best line must not be shown on its other lines, and the
  caps must hold whichever line is taken (2026-11-09).
- **A slot at a fixed local hour drifts against kickoffs when only one side changes its clocks.** Since 2026-11-01 the
  early Sunday games kick off at noon Edmonton, so the "10 am look that ties with the pre-kickoff pull" became a
  second full pull an hour earlier, before the inactives are out (about 28 credits a Sunday).
- **The Patch log is parsed from this file's headings.** Its research block stopped at "Standing watch", so rounds 8
  to 10 were never shown. When a file's layout is a parser's input, check the count per kind after moving sections.
- **Rule 0 holds for what chooses and grades a pick, not for the stake.** At an absurd disagreement (model 90%, book
  30%) the Kelly fraction rises a hair as the price shortens, because the bet gets less volatile faster than its
  edge shrinks. The smoke test checks the cautious edge and the grade over the whole grid.
- `itertuples` renames a column whose name starts with an underscore; the site's JSON keeps four decimals, so a test
  that recomputes a number from its parts needs that tolerance.
- **A summary written by a helper is checked against its source before it enters this file.** The rejected register
  was compiled by a subagent from the archive; nine figures spot-checked against the text, all matched.

- **A test that cannot fail tests nothing.** The synthetic board had combined and assists lines only, so every
  solo-only card flag passed "where they apply" by never applying, and the A-grade check still tested the rule
  replaced a day earlier, passing because every synthetic A happened to clear the old bar too (2026-11-10). When a
  rule changes, read the check that names it; when a feature is per market, the synthetic board needs that market.
- **A level read on three weeks is those three weeks.** The lined-player level was 1.03 from weeks 7 to 9 and 1.01
  once weeks 2 to 6 were in. A walk-forward statistic says how many weeks feed it, in the log line that prints it.
- **Found on three weeks, checked on six.** Of six candidates written down from weeks 7 to 9, two held on weeks
  1 to 6 at nearly full size, two held only through the first, one was weak alone and one reversed (75-47 to
  36-45). A pattern from three weeks is a coin until other weeks agree.
- A DataFrame column named `level` cannot be read as an attribute (`df.level`, `groupby(...).level`): use brackets.
- **A replay of a past week must not read anything dated after it.** `upcoming_rows` took each offence's latest
  starters of the season, which for a past week is the future (2026-11-10). Small here; the habit is to filter by
  week wherever a frame holds the whole season.
- **A good year for a side is not a good model.** In 2025 every solo Under at the best closing price returned
  +10.8% with no model at all. A record on a season is read against that season's board, and the best price
  across three books is not the price one bettor gets.
- **When a number is supposed to rank picks, check that it ranks them.** The cautious edge set B against C and the
  size of every stake for a day and a half on three weeks of closing lines (37-25 against 31-20). On 21 weeks it
  ranked nothing. Before a number sets a grade or a stake, the record by its buckets is read on weeks it was not
  chosen on, and again whenever more weeks arrive.
- **A replay shown on the site is a file, and a file goes stale.** `data/retro_five.json` and
  `data/replay_seasons.json` are written by hand-run tools, not by the daily. After any change to a pick rule, a
  grade or a stake, re-run them before the push, or the Track record tab reports the previous rules' replay.
