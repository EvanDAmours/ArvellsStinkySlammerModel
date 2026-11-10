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
"## Changelog".

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
   - Solo = the combined number x his solo share (his own, shrunk toward his position's over 25 tackles) x the
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
     0.35 on combined and 0.5 on assists (the model has beaten the book on solo lines and not on combined);
   - the **cautious chance**: the same with half of w;
   - the return at the win chance and the **cautious edge** (cautious chance x decimal odds - 1) at this book's
     price. The side with the better return is the line's side.
5. **Pick, lean, no pick.** A pick has a cautious edge of zero or better. A lean has 2%+ at the win chance and is
   under water at the cautious one: shown, logged, never staked. Never a pick: a player ruled out or doubtful,
   fewer than 3 games of data, and an Under on a next-man-up backup the share model expects under 60% of the snaps
   (the projection runs 16% low on exactly those), and a line that does not fit the player (one book alone on the
   player and market, the model's own chance 93%+: a mis-posted line or another player of the same name).
6. **Grades and the lock score.** A: a pick that is also a sleeper on the same side (item 11), checklist clear,
   in a market that can carry an A (solo and combined; assists is a trial market). B: cautious edge of 2%+. C: any
   other pick. The lock score is the model's own chance out of 100. Combined projections carry the level for
   players who get lines (actual over projected on the season's earlier lined games; decision R7).
7. **The checklist** (never a lock, an A or a parlay leg): new role, next man up, reduced role, back from absence,
   new team, fewer than 3 games in his current role, questionable, snap counts missing for his last game, an Over.
8. **Locks.** A picks only, highest model chance first, one per player, at most 3 on a one-game slate day and 5
   otherwise, at most two of a kind (side x market x position). A slate with no A has no lock.
9. **Stakes** (`grade.size_stakes`, `config.STAKE`). Each pick starts at a quarter of Kelly on a 100-unit bankroll
   at its cautious chance (0.1 to 3 units). Then the slate is sized as one book: each stake is divided by
   1 + (N - 1) x 0.02 for the N picks of its kind (side x market) that slate day, and stakes are scaled down
   together to at most 4 units a game, 10 a kind a day, 15 a day.
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
- **P6. Shrinkage by position** (LB 0.5 games, S 1, CB 3, DL 3), solo share shrunk over 25 tackles, league solo drift
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
- **E4. Grades: B at a cautious edge of 2%+, A with a model chance of 70%+ and a clear checklist.** The closing
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
- **S1. A quarter of Kelly at the cautious chance, 0.1 to 3 units.** Sized on the cautious chance because no edge
  is proven: a pick that only just passes gets the minimum. Move to the win chance when the scoreboard's margin
  over the book is two standard errors positive.
- **S2. The slate as one book:** divide by 1 + (N - 1) x 0.02 per kind per slate day; caps of 4 units a game, 10 a
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
  (changelog, 10 pm), before week 10 had a line; it stands again.
- **R7. Changed 2026-11-09, 10 pm, at the owner's instruction** (they amend E2, E4 and E5 above; evidence in the
  changelog, all of it in-sample):
  - *E2:* the weight is 0.65 on solo lines and 0.35 on combined (assists 0.5); the cautious chance is half of it.
    Same revert test as E2, read on weeks 10 to 13; the flat 0.5 is in the shadow.
  - *E4/E5:* an A is a pick that is also a sleeper on the same side, checklist clear; locks are A picks, the
    model's own chance highest first. It stays only if A picks hit 60% or better over their first 30 and beat B and
    C; else back to the old rule (cautious edge 2%+ and a model chance of 70%+), which is counted beside it.
  - *Combined level:* combined projections of the week times actual over projected on the season's earlier lined
    games (shrunk n / (n + 100), clipped 0.9 to 1.1). Off if that ratio falls inside 0.99 to 1.01 over four weeks
    or the scoreboard's combined margin is worse with it. Solo has no level.
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

1. **No edge has been demonstrated.** The record as bet is 200-183 (likely range 43% to 61%), +0.1 units; locks 10-4
   (44% to 89%, against a break-even near 58%). No-vig closing-line value -2.75 points, give or take 0.74 (a price
   that never moves scores -2.4). The scoreboard's margin over the book on the logged numbers is +0.0068 (t +1.9,
   three weeks, in-sample for the weight); with the rebuilt projection's numbers +0.0044 (t +1.0). It is all solo:
   +0.0107 (t +2.2) on solo lines, -0.0020 (t -0.4) on combined. Weeks 10 to 13 are the first out-of-sample test.
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
3. **Grades do not order yet.** Replay of weeks 7 to 9: A 10-6 (claimed 70%), B 20-21 (53%), C 73-58 (55%). Stakes
   that follow the cautious edge therefore did not beat flat stakes (-0.0 units on 69.1 staked against +17.7 flat).
   Every range overlaps; judged at 30 graded A picks. If A still claims 70% and hits near 60%, a ceiling on the
   model's own chance is the candidate.
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
7. **Odds credits (owner).** `PARLAY_API_KEY` is rejected as invalid: one key, under 200 credits to the end of
   November. The budget keeps every pre-kickoff pull and the Thursday and Monday looks, runs the first Saturday
   night look and leaves out later ones, the Sunday 10 am look and the assists market. A working second key or a
   paid plan restores the full schedule the next pull.
8. **The standing post-mortem task.** Its instructions were rewritten for this structure on 2026-11-09. Its run of
   that morning did have the repository (an earlier note here said it had none; the run's transcript shows a
   checkout). It stopped after a minute because the graded detail it was told to read is sealed on the site.
   `data/weekly_five.md` now carries that evidence in plain text. Its sessions are set up to push to a branch of
   their own (`claude/relaxed-heisenberg`), so a push to this branch may be refused: the task is told to push its
   entry to its own branch then, or to leave a patch, and to say where; the entry then needs merging. Read what its
   Tuesday and Friday runs produce. Week 9's Monday night game is still to be added to its post-mortem.
9. **The repository is public (owner).** Picks, projections, every odds snapshot and this file are readable without
   the site's password. A private repository needs paid Actions minutes for a ticker that runs all day.
10. **The closing price is an hour old** (the last pull before kickoff): closing-line value and the scoreboard are
    against that price, not the close.
11. **Prices are not Alberta prices.** theScore Bet's lines are its US feed; three books post tackle lines on the
    feed; bet365 is not carried. That a tackle made with an assist settles as solo at the book is inferred from
    ESPN, not confirmed: one settled slip would do it (Nohl Williams Under 2.5 solo, week 9).
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

### 2026-11-10, 6 am (five more ideas tested at the owner's request: none adopted)

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
