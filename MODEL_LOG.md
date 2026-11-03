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

Standing rule (2026-10-30): **a lock must come from where the model is reliable.** A player whose season history
does not describe his current role (a part-timer who just played a starter's snaps) or who may not play (listed
questionable) can be a pick, never a lock or a parlay leg.


1. **Projection (rebuilt 2026-10-30, research round 4).** Two bases blended 60/40: the per-game base (season-to-date
   tackles per game shrunk toward last season or a position prior with a position-specific weight, LB 0.5 games,
   S 1, CB 3, DL 3, times the snap-share trend, the role bump and the reduced-role correction) and the **per-snap
   base** (tackles per defensive snap from games with real snaps, shrunk toward last season's rate, times the
   expected snap share from a situation-aware share model, times expected team defensive snaps). When a regular at
   his position is out or gone and his share jumped outside a blowout, the projection moves halfway to his per-snap
   rate at his last-game share (the vacancy rule). Then the game-context factors: a small point-spread tilt, a stat-crew factor
   for the venue, a role bump when a regular at the position group is out, a **snap-share trend** factor (last 3
   games vs season, damped), a **tackle-opportunity volume** factor (expected opponent carries + completions +
   sacks vs what the player has faced, damped and capped), a **depth-chart** factor (demoted x0.90, promoted
   x1.02), **PFR** factors (coverage targets for DBs, missed-tackle rate), a **run/pass mix** factor from
   play-by-play, a **bye-week** factor (x0.96) and an **injury-report** factor (listed questionable x0.92, limited
   practice x0.97). A level calibration from the backtest (about 1.0) is applied. Then a **second model** (added
   2026-10-27): a gradient-boosted regressor with Poisson loss, trained every morning on every finished
   defender-game since 2023 from the same 25 signals plus the factor projection itself, takes 60% of the final
   number and the factor model 40% (`GBM`). The solo projection moves in the same proportion. Count distribution
   tighter or looser than Poisson per position, re-estimated daily by the backtest.
2. **Pricing (changed 2026-10-26).** The mean used to price a line is `0.4 x projection + 0.6 x consensus line`
   (`LINE_WEIGHT`). Expected return is computed from that mean against the no-vig market price.
3. **Picks.** A side is a pick when its expected return clears `PICK_BAR` (6%), or `SIGNAL_BAR` (4%) with a
   role-change or outlier-fade signal, the player is not out or doubtful, and he has at least 3 games. A player
   listed questionable is priced (with the x0.92 factor) and can be a pick, tagged "Questionable", but is never a
   lock or a parlay leg: he may not play, and the bet voids if he sits.
4. **Grade (added 2026-10-26, market agreement removed the same day).** Every priced line gets a 0-100 lock score
   and an A/B/C grade from expected return, the model's own side probability, how often the player cleared the line
   this season, games of data, and a signal bonus. Nothing from the market. Logged with every pick
   and summarised by grade on the Track record tab so the grade itself is tested.
5. **Grading.** Picks are graded against official box scores the next morning, with closing-line value.

## Validation protocol (do this before pushing any model change)

1. `python tests/smoke_test.py` must pass.
2. Re-price the most recent graded week offline with the change and compare picks, hit rate, units and
   calibration (model side-probability vs hit rate) against the current rules. The script pattern is in the
   2026-10-26 entry below. One week is noise, so a change needs a reason beyond "it scored better this week".
3. For projection changes, check the daily backtest table (`docs/data/backtest.json`): judge on the level-matched
   miss (`mae_cal`, each predictor scaled to zero bias first; added 2026-10-30), and the full model must beat every
   "without X" row on it, or that piece goes.
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

## Research round 3: ten more data sets and a second model (2026-10-27, late afternoon MDT)

The owner asked for ten more data sets or models to find an edge beyond the one measured so far. Same method:
36,424 defender-games built with every source loaded daily plus the candidates below, 28,824 scored (2+ prior
games, week 3+), fitted on 2023-24 (17,213), scored on 2025-26 (11,611). Reference: the round-2 full model,
test-years MAE 1.6254. Scripts: scratch `research/build3.py`, `evaluate3.py`, `gbm3b.py` (not in the repo; the
numbers below are what they printed).

### Adopted

1. **Own injury report, played anyway** (`load_injuries`, all seasons; now also `practice_status`). A defender
   listed questionable who played ran 6% under the model over 1,191 games; limited practice that week, 4% under
   over 1,274 games; did-not-practise, nothing (550). Factors x0.92 and x0.97 (`INJURY`): test MAE -0.07% and
   -0.05%, both halves agree. Questionable players were previously passed outright; they are now priced with the
   factor and can be picks (tagged "Questionable" on the card, with a note in the reason), but never locks or
   parlay legs. Backtest row "Full model without injury report": +0.0025 worse than the full model.
2. **A second model: gradient-boosted corrector.** A `HistGradientBoostingRegressor` with Poisson loss (800 trees,
   learning rate 0.02, 31 leaves, 40 games per leaf, L2 0.5, three seeds averaged) on 25 features the pipeline
   already computes: the factor model's log projection, games, snap-share trend, snap share, volume ratio, spread,
   PFR target and missed-tackle rates, depth-chart flags, starter flag, questionable and limited flags, rest, week,
   last game, raw average, last-season average, crew factor, position, home, expected opponent runs and
   completions, and the player's run- and pass-tackle rates. Fitted on 2023-24 and scored on 2025-26: alone
   -0.91% MAE; blended 50/60/70% with the factor model -1.00 / -1.08 / -1.11%. A second, stricter check trained
   through 2025 and scored 2026 only (2,649 games): 1.6281 -> 1.6041 (-1.47%). Calibration of the 60% blend is
   as honest as the factor model's (the 0.55-0.65 bucket predicts 0.567 and hits 0.550; the factor model predicts
   0.570 and hits 0.605). Weight set at 0.6 (`GBM`): 0.7 was marginally better in sample but leans harder on the
   less interpretable half. Training takes a few seconds; the daily job is now about 80 s.
   How it is reported: the backtest table carries two walk-forward rows, "Full model, 2026 fold" and "60% boosted
   corrector blend, 2026 fold (trained on earlier seasons)", so the gain shown is never measured on games the
   corrector saw. Live, it is retrained each morning on every finished game, and each projection carries
   `proj_factor` and `proj_gbm` beside the blended `proj`. Without scikit-learn the factor model runs alone.
   Real daily run on 2026-10-27: full model 1.6482 on 28,824 games (was 1.6507); 2026 fold 1.6289 -> 1.6032 with
   the corrector; scale 1.0012; every ablation row worse than the full model.

### Measured and not adopted (do not retry without new data)

3. **Zone matchups** (play-by-play `run_location`, `pass_length`, scrambles): each player's tackle rate by run
   direction and pass depth, times the opponent's mix of those zones, against a neutral mix. The raw diagnostic
   showed a 2% spread between the lowest and highest fifths, but as a factor it was worse at half strength
   (+0.09%) and much worse at full (+1.03%). The run/pass mix factor already carries what is real here.
4-12. **Opponent offensive tendencies**, nine of them, each as a per-position multiplier fitted on the train
   years: short-pass rate (air yards 5 or less), running-back target rate, screen rate, play-action rate, RPO
   rate, no-huddle rate, pre-snap motion rate, quarterback out-of-pocket rate, players in the backfield (the last
   six from FTN charting). Not one moved the test error by more than 0.04% in either direction, and the fitted
   slopes flipped sign across positions. None loaded; FTN charting stays out of the pipeline.
13. **Cross-position starters out** (own team, from the report by position group): fitted +7% DL when a DL starter
   is out, +14% LB, +12% S, +14% CB, +8% CB when a safety is out, +6% LB when a corner is out. Every one was
   worse on the test years (LB +0.39%), because the role bump already pays the same-group effect and the
   cross-group effects did not hold out of sample. Not adopted; the role bump stays as is.
14. **Blitz rate** (PFR `def_times_blitzed`, LB and S): heavy blitzers ran 2% under the model, light ones 2% over,
   but the fitted slope rounded to zero out of sample (-0.00%).
15. **Play-by-play solo share** for the solo projection (run tackles are solo 42% of the time, pass tackles 69%):
   the player's own run/pass solo shares weighted by the expected mix scored worse than the current solo share
   (MAE 1.1406 vs 1.1276), and a 50/50 blend was still worse (1.1327). Kept the current solo method.
16. **Participation data** (`load_participation`: defenders on the field per play) ends with the 2025 season on
   nflverse and cannot be used live. Not built.

### Pitfalls found this round

- The corrector must be scored walk-forward. Trained and scored on the same seasons it looks 3-4% better than
  the factor model; the honest number is 1.1-1.5%. The backtest rows are built that way on purpose.
- A corrector feature must exist for upcoming rows exactly as in the backtest rows. `gbm_features` fills every
  missing column with the same neutral value in both paths; a column present in one and absent in the other
  silently shifts the prediction.
- The replay tool used a cached `model_state.json` for phi and scale and would have had no corrector; it now
  runs the backtest itself so the replay prices with the same model the daily job would have had.

**Week 7 replayed under this model** (`tools/replay_five.py --week 7`, every pull from Saturday to Monday,
restated 2026-10-29 after the replay leak fix: calibration and corrector built from weeks 1-6 only; superseded by
the week 8 Thursday post-mortem's replay under the lock-eligibility checklist, locks 3-2): locks 3-3
(-0.50 units: Elliss W, Schwesinger W, Clark W; Lenoir, Queen, Carter L), all plays 102-95 of 199 (+8.13 units;
the round-2 model replayed 96-92, +5.3), by grade A 7-7 (-0.9u), B 39-37 (+0.3u), C 56-51 (+8.7u), Sunday parlay
Elliss/Lenoir/Tranquill (+310) Loss. **The Monday slate came up short**: the board had nine lines on three players
and only Kenny Clark Under 2.5 reached the 55 lock floor (score 55 exactly, B grade; 64 under the factor model),
because the corrector projects him nearer the 2.5 line. Only one Monday leg cleared the 55% parlay fallback, so no
parlay could be built. Trade-off to watch: the corrector sits closer to the line than the factor model, so on a
thin single-game board fewer picks clear the lock floor, against the owner's target of three locks on Thursday and
Monday. Nothing is changed for that here; see the backlog. One week is noise; the evidence for the change is the
walk-forward backtest, not this replay.

## Research round 4: the model rebuilt around snaps (2026-10-30, midday MDT)

The McDuffie post-mortem fixed the symptom; the owner's reply ("he wouldn't have been a pick at all is that a joke?")
was the right diagnosis of the disease. A model whose base is a per-game season average cannot say what a player
does when his snaps change: it can only shade the average. This round rebuilt the base around snaps and tested
every other idea that a per-snap view opens up. Same method as always: 28,861 defender-games, fitted on 2023-24,
scored on 2025-26, every comparison level-calibrated (each predictor scaled to zero bias on the training years, so
a piece cannot look good by shifting the level). Scripts: scratch `pm8/r1_persnap.py` to `r4_eval.py`.

### Adopted (13 changes)

1. **Per-snap base.** Tackles per defensive snap x expected snap share x expected team defensive snaps, blended
   40/60 with the per-game base. Old core 1.6532 train / 1.6164 test; new core 1.6324 / 1.5985 (-1.3% / -1.1%),
   the largest gain in the project's history. Weight 0.4 chosen on train; 0.3-0.5 are within 0.001 of each other.
2. **A clean per-snap rate.** Only games with 10+ defensive snaps count toward the rate; special-teams tackles
   made on 0-9 snaps had inflated part-timers' rates by up to 2x. Prior: last season's rate (150+ snaps) or the
   position rate (CB .074, DL .066, LB .110, S .093 per snap), over 150 pseudo-snaps.
3. **Expected team defensive snaps** from the defence's own prior games and the plays the opponent's offence has
   run per game (the mean of both). Error 7.39 snaps vs 7.41 for the league average: the pace signal is small but it
   is the right unit for the per-snap base.
4. **A snap-share model by situation.** Next-game share from (last game, last three, season) with weights fitted
   separately for: a jump backed by a vacancy or a depth-chart listing (1.02 / 0 / -0.29: it holds), a jump in a
   blowout (0.55 / 0.43 / -0.16: it regresses), any other jump (0.48 / 0.42 / 0.02), a drop (0.19 / 0.41 / 0.41) and
   steady (0.32 / 0.22 / 0.44). Share error on backed jumps 0.26 -> 0.22; one-size weights had bias +0.15 there.
5. **The game margin as data** (`away_score` now loaded): a share spike in a 17+ point blowout is garbage time
   and regresses (next share 0.74x the spike) where a spike with a vacancy behind it grows (1.32x).
6. **The vacancy rule (the McDuffie rule).** A regular (75%+ share) at his position group is out, gone or missed
   the team's last game within the last three weeks, his share jumped 1.5x+, and the jump was not in a blowout:
   the projection moves halfway to his per-snap rate at his last-game share. The per-game model ran 24% under on
   these (bias +1.03 tackles on 41 test games); at full weight the rule overshoots (-0.46), at half weight +0.05
   to +0.11 with the lowest error of the three. McDuffie week 8 under the final model: 9.9 (factor 11.9, corrector
   8.6) against a 7.5 line and an actual 10. He would have been an Over pick, not a lock.
7. **Vacancy detection reads trades and releases**, not just the injury report: a regular who moved per the latest
   depth chart, or who missed the team's last game, vacates his group. The Quay Walker trade is exactly this. In
   the backtest the vacancy is persistent for three weeks (`role_signal` fired once and missed McDuffie's week 8).
8. **Dispersion by expected snap share.** Part-timers' counts are far more spread than starters' (var/mean LB 1.90
   vs 1.57, S 1.85 vs 1.43, CB 1.59 vs 1.27, DL 1.04 vs 1.02), so the backtest now estimates phi per position and
   again for expected share under 60%, and pricing uses the right one. Probabilities on low-snap players were
   overconfident before.
9. **Corners in domes** x1.05: +4.6% (2023-24) and +7.1% (2025-26) over the model, consistent in both halves; the
   only weather or venue effect that was.
10. **Role-adjusted consistency.** "How often he cleared the line" now rescales each past game to the share he is
    expected to play (games with 15%+ share, ratio capped 0.5-2.5), so a part-timer's log is read at his new role
    and a starter's early-season rotation games do not count against him.
11. **The corrector learns the new view**: per-snap rate, expected share, expected team snaps, blowout last game,
    vacancy, tackles allowed to his group and dome join its features (32 now). 2026 fold 1.6156 -> 1.5968, blend
    1.5867 -> 1.5751.
12. **The new-role multiplier is retired** (power 0): with the per-snap base in the blend it double-counted (new-role
    bias -0.44 with it, -0.02 without). The flag still drives the lock checklist and the wider distribution.
13. **Data freshness is reported**: the daily run records the latest week with stats and with snap counts and
    whether snap counts lag (`meta.freshness`), so a snap-count outage can never again read as "0% of snaps".

### Validation (daily run on 2026-10-30 data, 28,861 games)

Full model 1.6321 -> 1.6234; "without per-snap base" 1.6318 and "without role-shift factors" 1.6330 are the two
worst ablations in the table. 2026 walk-forward fold 1.6156 -> 1.5970, with the corrector 1.5867 -> 1.5769. Weak
spots with their factors: vacancy +4.5% (without +22%), new role +1.2% (+14%), reduced role +7.9%, 3+ weeks out
+1.7%, one missed game +5.1%, new team -3.3%. Dispersion now LB 1.57 / 1.90 (starters / under 60% expected share),
S 1.43 / 1.85, CB 1.27 / 1.59, DL 1.02 / 1.04. The backtest table gained a **level-matched miss** column (each
predictor scaled to zero bias before scoring) and is judged on it from now on; on raw miss, a piece that happens to
lower the level on a day the model over-projects looks better than it is.

**McDuffie under the final model**: projection 9.1 (factor model 10.0, corrector 8.5) against the 7.5 line. The
Under lock is gone: he is not lock-eligible (new role, one game in it) and the Under returns -3%. The Over is not
a pick either, and that is the honest answer to "he would not have been a pick at all": DraftKings priced Over 7.5
at -129 and Under at -101 (Bally Bet Over -130). The book had already moved to his new role, so at that price the
Over returned -9% even with the model at 9.1 (the pricing mean is 40% model, 60% line, and his distribution is the
wide new-role one); the only edge on him was Under 3.5 solo at +124 (+18%, won: 3 solo). The vision says the
edge is what the market has not priced; here the market had priced it. What the model must never do again is
back the wrong side of a role change at 83 confidence, and it cannot now.

**Replays under the final model**: Thursday week 8 locks 1-2 (McKinney W, Moehrig L, Okereke L), all plays 8-6
(+3.1u), parlay Bullard/Cisse win; week 7 locks 4-3 (+0.5u; Sunday 2-3, Monday Bland and Clark 2-0), all plays
93-93 (+3.5u; fewer and different picks than the previous model's 100-93), parlays 1-1. One week each; the
evidence for the change is the backtest.

### Measured and not adopted

- **Per-snap base alone** (no per-game blend): 1.7306 train / 1.7258 test. Share prediction is too noisy to carry
  the whole projection; the blend takes what is reliable from each.
- **Per-snap at the last-game share for every jump**: bias -1.0 to -1.2 (over-projection). Most one-game spikes
  regress; only a vacancy or a listing makes one hold. That is why the rule is conditional.
- **Tackles the opponent allows to the position group** (shrunk, prior games): +0.06% on the per-game model, then
  slightly worse on both halves once the per-snap base was in. Kept as a corrector feature only.
- **Opponent pace** (plays per game): slope negative and tiny; nothing beyond the volume factor.
- **Opponent QB scramble rate**: nothing for any position (within 0.03%).
- **Opponent sack rate allowed** (DL): buckets inconsistent in the middle, 0.02% gain. Not worth its code.
- **Wind 15+ mph / freezing / outdoors** by position: DL +1% in 2023-24 but +11% in 2025-26; the halves disagree.
- **Home / away**: 1.007 vs 1.008.
- **A per-snap definition of the outlier fade** (big game only if his per-snap rate was 1.5x his norm): identical
  results to the raw-count definition (0.981 vs 0.979), so the simpler one stays.
- **Role-shift factor sizes refitted on the new core**: the existing sizes are MAE-optimal; softer absence factors
  trade a few hundredths of bias for worse error. Unchanged; the weak-spot table watches them.

### Pitfalls found this round

- A per-snap rate must exclude games without real defensive snaps or special-teams tackles make a 2-snap player
  look like a 2-tackles-per-snap player.
- Factors fitted on one base double count on another: the new-role multiplier (fitted on the per-game base) had
  to be retired once the per-snap base carried the same information. Refit everything that touches the same
  signal when the base changes.
- Judge ablations on level-calibrated error. Without that, any piece that happens to lower the level looks good on
  a day the model over-projects, and vice versa.
- Keep every pipeline process alone on the machine (see the earlier pitfall): this round's evaluations ran one at
  a time.

## Audit of everything so far (2026-10-30, afternoon MDT)

The owner asked for every other hole, after Thursday. Everything between the data and the bet slip was walked
through again: what the pull jobs know at pull time, the solo-tackle side of the model, pricing calibration under
the new model, parlay construction, source consistency, the vacancy logic's edge cases, and the schedule.

### Found and fixed

1. **The pull jobs priced with the morning's injury report.** Projections are built at 5:15 am Edmonton; the
   Thursday 5:30 pm pull, two and a half hours before kickoff, used that morning's statuses. A player ruled out
   in the afternoon was still priced; a new questionable listing could still be a lock. The odds job now reloads
   the week's report before pricing and rewrites every projection's status and practice fields (logged as "N
   statuses changed since the morning run"). Out becomes a pass, questionable leaves the locks, as it should.
2. **Solo tackles had never been validated.** Half the lines are solo markets, and the solo projection (the
   combined projection times a shrunk solo share) was priced with the combined-tackle dispersion. Measured on
   2025-26: solo counts are less spread than combined (variance/mean CB 1.19 vs 1.31, DL 1.05 vs 1.18, LB 1.27 vs
   1.49, S 1.16 vs 1.35), so solo probabilities were too timid; and the solo projection ran 3-4% high for CBs and
   safeties. The backtest now estimates a solo dispersion per position (and per low expected share), a solo level
   calibration, and reports two solo rows (full model vs season average) so the solo side is judged every day.
   Pricing uses the solo dispersion for solo lines.
3. **A returning regular read as a vacancy.** A regular who missed the team's last game counted as "gone" even
   when this week's depth chart lists him as a starter, which would have pushed his backup's projection up the
   week he came back. The listing now cancels the vacancy.
4. **No warning when the model and the line disagree a lot.** McDuffie's card showed 6.1 against a 7.5 line with
   no comment. Lines carry a "Model far from line" tag when the model's own number and the consensus line are 25%
   or more apart. It changes nothing in the grade, rank or pick (the market never does); it tells the reader that
   one side knows something and to check the news before betting.

5. **Pricing calibration under the new model** (weeks 7-8, every line at every pull, 1,768 line-pulls, pushes
   removed; scripts `pm8/calib.py`). Against the outcome, the model's over-probability has log-loss 0.6827 at
   `LINE_WEIGHT` 0.6 and 0.7, 0.6830 at 0.5, 0.6835 at 0.4 (equal to the market's own no-vig probability, 0.6835)
   and 0.6844 at 0.3. So 0.6 stays, and the honest size of the edge is now on record: the model beats the market's
   probability by a hair on all lines. Where it beats it is lopsided: on lines where the model sits 8+ points
   below the market on the over, overs hit 47.6% against the market's 53.6% (n=103); where the model sits above
   the market, overs hit 32-46% against the model's 46-57% (n=47). The model's Under leans carry information; its
   Over leans do not.
   On the 163 unique picks the replay makes for those two weeks: hit 50.9%, claimed 55.8%. By expected return,
   6-10% hit 57%, 10-15% 47%, 15-25% 50%, 25%+ 33% (n=15): return beyond the bar is not confidence, it is the
   winner's curse. By lock score the hit rate is flat at 50-52% while the claim rises with the score. Overs 5-9,
   Unders 78-71; combined-tackle lines 33-45, solo lines 50-35. Two weeks is a small sample and these are noted
   as provisional, but every one of them points the same way as the week 7 post-mortem did, so:
   - **An Over needs 10% expected return** (`PICK_BAR_OVER`), an Under 6%, a signal-backed pick 4%.
   - **The EV part of the lock score saturates at 10% and falls away above 20%** (`LOCK_EV_FULL`, `LOCK_EV_FADE`),
     to zero at 40%: a 30% "edge" is a flag, not a lock.
   - **A pick's claimed chance is shrunk 40% of the way toward even** (`CLAIM_SHRINK` 0.6) for the lock score's
     model part, the card and parlay legs. Market-free: toward 50%, never toward the book. Claimed 55.8% becomes
     53.5% against the 50.9% observed. Parlay thresholds move to 56% / 53% claimed (the same raw 60% / 55%).
   Revert condition: 200+ further picks where the hit rate matches the unshrunk claim within 2 points, or where
   Over picks at 6-10% return hit above 55%.

**Validation (daily run on 2026-10-30 data).** Solo tackles: full model 1.1368 (level-matched 1.1291) against the
season-average 1.1802; solo level 0.973 (the solo projection was 2.7% high; now calibrated daily); solo dispersion
CB 1.16, DL 0.94, LB 1.25, S 1.23 against 1.29 / 1.02 / 1.57 / 1.44 combined. Replays under the audited pricing:
week 7 locks 6-1 (+3.9u; A grade 4-0), all plays 86-87 of 176 (+0.8u), parlays 1-1; Thursday week 8 locks 1-2
(McKinney W, Moehrig L, Okereke L), all plays 8-6 (+3.1u), parlay Cisse/Bullard win. Fewer plays than before
the Over bar and the claim shrink, as intended. One week each; the evidence is the calibration above.

### Checked and sound

- **Team codes** are identical across stats, schedule, depth charts, injuries and snap counts (32 codes, LA for
  the Rams everywhere), so the depth-chart move detection cannot misfire on a naming mismatch.
- **Parlay legs from the same game** are priced as independent. Measured: standardised residuals of teammates in
  the same game correlate +0.018 and of opponents -0.031 (100k+ pairs each). Independence is fine.
- **The corrector's weight** (0.6): 2026 fold 1.5779 at 0.6, 1.5774 at 0.7, 1.5773 at 0.8, 1.5793 at 1.0. Within
  noise; unchanged.
- **Position groups**: nflverse labels almost every linebacker "LB" (1,226 of 1,316 rows in 2026); the few OLB
  rows have a DL-like rate (0.079 per snap vs 0.123). Too few to split; the per-snap base prices individuals
  anyway, and the group only sets early-season priors and dispersion.
- **Backtest and live features agree**: every corrector feature exists on both the history rows and the upcoming
  rows with the same meaning (vacancy, blowout, team snaps, matchup, dome, gap, team change).
- **Daylight time ends 2026-11-01**: pull slots are defined in Edmonton local time and convert themselves; the
  daily job moves from 5:15 to 4:15 am local, still before any game and after Sunday's stats land.

### Recommended, then adopted the same afternoon (the owner's call)

- **No Sunday pull.** (Adopted: a Sunday pull one hour before the day's first kickoff, the whole slate.) The last look at the Sunday slate is Saturday 6 pm, about 17 hours before the early
  kickoffs. Inactives are published 90 minutes before kickoff and the Friday report's "questionable" players
  resolve then; lines also move most on Sunday morning. A Sunday 9:30 am Edmonton pull limited to games inside
  four hours (about 14 credits) would re-choose the early-slate locks and parlay with the inactives known. Same
  for a Sunday 1:30 pm pull for the afternoon slate. Credits: 406 remain on the first key for the month; the
  second key is still rejected as invalid.

## Risk pass on the algorithm (2026-10-30, evening MDT)

Asked for after the audit: what in the algorithm itself could hurt us. Each item has a status.

**Acted on**
1. **Overs.** Live Over picks 28-40 (41%); on every line where the model sat above the market, overs hit 32-46%.
   Overs are not lock-eligible and not parlay legs (`LOCK_RULES["overs_eligible"]`), on our own record, not the
   market's. They stay picks at the 10% bar. Revert: forty further Over picks at 55%+.
2. **A silent blind spot.** If snap counts for a player's last game have not landed, every role check (new role,
   reduced role, vacancy, in-role games) reads as "nothing happened". Such a player is now not lock-eligible
   ("snap counts missing for his last game"), so a data lag cannot recreate the McDuffie failure quietly.
3. **Injury-report name matching** checked for week 8: every defender with a game status matches a projection
   (the unmatched listings are offensive players). Noted; a per-pull count of unmatched defensive listings is
   on the backlog.

**Accepted, with the reason**
4. **The corrector's vacancy feature means slightly different things in training and live.** In the history
   rows a vacancy is "a regular absent this week" (which includes surprise inactives); live it is "out on the
   report, moved, or missed the last game and not listed back". The live signal is a subset, so the corrector
   will under-use it rather than over-use it. Acceptable; the per-game rule carries the case.
5. **Test-set iteration.** Rounds 1-4 chose among variants partly on 2025-26 results, so the 2025-26 numbers are
   optimistic. The 2026 walk-forward fold row in the daily backtest (trained before 2026) is the clean number and
   is the one to quote: 1.5970 factor model, 1.5769 with the corrector.
6. **The lock score was rebuilt on 2026-10-30 and has no live record of its own.** The first picks under it come
   Saturday. The grade-order watch and the Sunday-night review cover it; nothing more can be done before then.
7. **Parlay stakes are quarter-Kelly on claimed probabilities.** The claim shrink makes the claims honest on the
   two weeks measured; stakes are capped at one unit and have run at 0.1. Acceptable.
8. **The line blend (60% posted line) is a dependence on the market for the number, not for the grade.** It is what
   keeps the probabilities calibrated (log-loss 0.6827 at 0.6, 0.6844 at 0.3). The vision's rule is about grading,
   ranking and choosing, which never use it.
9. **Off-market books.** Only 7 of 247 live picks were taken at a line that differed from the consensus; no
   systematic exposure.
10. **Share-model and factor sizes are fitted constants** (2023-24) that will drift. The weak-spot table and the
    "without X" rows are checked every day; the revert conditions are in each changelog entry.
11. **Locks are chosen on score alone, not spread across games.** Measured same-game residual correlation is
    +0.02 for teammates, so five Unders from one game are not materially correlated. Acceptable.
12. **Pass rushers labelled "LB"** get the linebacker prior for their first game or two of a season. Shrink is half
    a game for LB, so it washes out immediately. Acceptable.

## Why the Overs miss (2026-10-31, morning MDT, at the owner's question)

Measured on the live picks (68 Overs, 179 Unders) and on every priced line of weeks 7-8 (315 unique lines; scripts
`pm8/calib.py`). Three causes, in order of size.

1. **The market's over side is where the public money is, and the model's Over picks are its biggest upward
   disagreements with that market.** On the Over picks the model claimed 60%, the market's no-vig price said 48%,
   and reality was 41%. On all lines where the model sat above the market, overs hit 32-46%; where it sat well
   below, they hit 47.6% against the market's 53.6%. The market's price already leans toward the over, so a
   model-found Over edge means the model is far above a number that was set high to begin with. Those are the
   model's errors, not the market's. The Under side has the opposite property: the market's over-lean leaves real
   value on Unders, which is where the live record comes from (Unders 103-76, +22 units; Overs 28-40, -13 units).
   Fix in place: an Over needs 10% return, is never a lock or a parlay leg, and the lock score's return part fades
   above 20%.
2. **Solo lines ran cold, and the solo projection lagged a league-wide drift.** Overs on solo lines hit 32.5% in
   weeks 7-8 (the model said 44%, the market 49%); on combined lines overs hit 55% (model 46%, market 50%). The
   league's solo share of tackles fell from 0.55 in weeks 1-6 to 0.50 in week 7 (2025 drifted the same way across
   the season, 0.55 to 0.51), and a player's season-to-date solo share lags that. Fix: the solo share now carries a
   league drift factor (last three weeks over the season to date, `SOLO_DRIFT`): test-years solo bias -0.044 ->
   -0.003 tackles, error -0.5%, plus the solo level calibration from the audit. It cannot catch a one-week swing
   like week 7 in time; it catches a season-long drift, which 2025 had.
3. **Low lines.** On lines of 2.5 or less, overs hit 34-36% against a model 45% and a market 51%: for low-volume
   players the whole market sets the number too high and the blend imports that. The Over bar and lock rule
   cover it; a line-level calibration is on the backlog pending more weeks.

What it is **not**: the backtest shows the model's upward adjustments do not overshoot a player's own history
(when it projects 25%+ above his average, he delivers 4-6% more than projected), and the count distribution's
over-probabilities are honest at lines just above and below the projection (0.438 vs 0.456 observed, 0.641 vs
0.673). The Over problem is relative to the market, not to the player.

## Is the solo Under our play? (2026-10-31, midday MDT, at the owner's question)

Live: Under solo 70-36 (66%, +30 units), the best segment by far. Measured properly before building on it:

- **The edge was the market's, not our selection's.** On every solo line on the board in weeks 7-8 (154 unique
  closing lines), the over hit 32.5% while the market's own price said 49%. Our solo-Under picks hit 66%; betting
  every solo Under blind would have hit 67%. The model added nothing within the solo market those two weeks; it
  was right to lean Under, and that lean is what earned the units.
- **Part of it was week 7's crediting.** The league's solo share of tackles fell to 0.50 in week 7 from 0.53-0.55
  before. Across seasons the share is flat in 2023 and 2024 and declined through 2025, so the drift is not a law;
  the league drift factor (2026-10-31) catches a season-long drift and cannot catch a one-week dip in time.
- **Where the Under works and where it does not**, live: on defensive backs it is excellent (CB combined 14-3, CB
  solo 13-2, S solo 22-8); on linebackers it is bad (LB combined 5-12, LB solo 19-16), and Under combined on lines
  of 4.5 or more is 10-25. The Under after a big game (the fade) on solo lines is 14-0. LB combined totals are the
  headline tackle props and the sharpest market on the board; DB solo lines are the thinnest. That is a plausible
  structural reason, not just two weeks' noise.

**What changed (the model's own math, not a rule to bet solo Unders blind):**
1. **Segment calibration of claims.** Every graded pick now teaches the pricer: for each kind of pick (side x
   market x position, then coarser), the grader records the hit rate against the claimed chance; the pricer corrects
   the next pick's claimed chance by that gap, shrunk by n/(n+30) and capped at 15 points (`SEGMENT_CAL`,
   `segment_calibration` in the grader, `segment_adjust` in the pricer, `data/cache/segments.json` between them).
   Today that lifts Under solo claims by about 8 points and cuts Under combined LB claims by about 4, so the locks
   lean where the record says the claims have been honest, and it self-corrects as the record moves. Our own
   results only; the book's opinion never enters. Replays do not use it (that would be hindsight).
2. **Solo share shrinkage 8 -> 25 pseudo-tackles** (`SOLO_SHARE_PSEUDO`): solo error -1.0% on 2025-26, -0.7% on
   2023-24, bias unchanged.
3. **Solo level per position** from the backtest (CB and S run 2.5-3.5% high, LB 1.7%): applied in pricing.
4. **Market watch on the site**: every closing line on the board, by week and market, over rate against the
   market's own price. It is the gauge for the owner's question: while the solo market keeps resolving under its
   own price, the solo Under stays the lead play, and the day that gap closes it stops being one.

**Should the solo Under be the ongoing play?** Yes as the lead, no as a blind rule. Lead, because the market watch
and the live record both say so and the model now weights its claims that way. Not blind, because a 66% hit rate
on 106 picks has a standard error of about 5 points, the week 7 crediting dip explains part of it, and a blanket
rule cannot tell when the market adjusts; the segment calibration can, and the Over record already shows what
happens when a side goes cold.

## Research round 5: beyond nflverse, and the minutiae (2026-10-31, midday MDT)

The owner's brief: find five to ten more sources, "expand to other sites", "sneaky little datasets... that we can
cross verify against our own model", "minutiae instead of the big details", because "an amalgamation of the big
books and big sites is just going to set us up to fall victim to the big books". Sixteen sources were examined.
Model factors were tested the usual way: fitted on 2023-24, checked on 2025-26 (11,648 held-out games), reported
as the change in held-out miss and the bias on the subset the factor touches. Outside feeds were tested for
reachability from a script, for what they carry that nflverse does not, and for whether they could be validated.

### Adopted

1. **ESPN's injury feed**, **FantasyPros as a cross-check** (items 2 and 3 below) and, for the card only, **a lineman's
   pressure profile** (item 4: rejected as a model factor, kept as a tag). The round's model-moving candidate did not
   survive the pipeline's own backtest; see item 4 for what happened, because it is the lesson of the round.
2. **ESPN's injury feed (`site.api.espn.com/.../nfl/injuries`), merged with the league report.** The league report
   carries only the week's designations. ESPN's feed carries **suspensions and injured-reserve stays** as listings
   (on 2026-10-31: 55 Out, 3 Doubtful, 96 Questionable, 49 Injured Reserve, 1 Suspension, 596 "Active" notes), with
   a return date. C.J. Gardner-Johnson (S, BUF) sat on it as a suspension through 2026-11-09 and on no league
   report: a regular the model would have projected and priced, and who was not going to play. Rule: one listing
   per player-week, the more severe status wins (out / IR / suspended > doubtful > questionable), the league
   report's practice status and player id are kept, an "Active" note never downgrades anyone. Loaded at the
   morning run and again at every line pull (`load_espn_injuries`, `merge_injury_sources`; team codes WSH, LAR,
   JAC translated). On synthetic data the feed is empty, so the smoke test checks the parser and the merge rule on
   a planted payload instead.
3. **FantasyPros expert-consensus IDP projections, as a cross-check only.** The projections pages for DL, LB and
   DB embed the consensus solo tackles and assists for the top ten players at each position (the ones with lines);
   the full table sits behind their API key, which this project does not use. Loaded each morning for the week,
   kept under `data/consensus/fantasypros_<season>_w<week>.csv`, shown on the Projections tab ("Outside consensus")
   and in each pick's "Why" box (above or below the line, same side as the pick or not), and logged with every
   pick (`fp_comb`, `fp_solo`, `fp_rel`) so that in a month the picks log can say whether agreement with the
   consensus predicts hits. It prices nothing and chooses nothing: the owner's rule is that the edge is what the
   market has not priced, and a consensus is the market's cousin. One thing learned on the first load: their
   numbers are not box-score tackles. Across the 30 matched players the consensus "tackles + assists" ran 24% above
   the players' own season averages (Roquan Smith: 11.0 against a 7.9 average; Jack Campbell 11.4 against 9.2),
   a mix of sites' tackle definitions. Shown raw it would read as "the model is low on everyone", which is false.
   So the site reads it relatively: how far the consensus sits above or below its usual relation to this model
   for that player (`fp_rel`, median-normalised each morning), and says so.

### Examined and rejected (no new evidence needed to re-open; new data would be)

4. **A lineman's pressure profile as a model factor (PFR via nflverse, `def_pressures`).** The research script said
   run-stuffers (1 or fewer pressures a game, own prior games) ran +9.7% / +7.9% over the model (1,983 games) and
   1-2 a game +3.2% / +4.0%; it was built as two buckets (+6%, +3%) and sent through the validation protocol. The
   pipeline's backtest (28,861 games) rejected it: miss 1.6217 without, 1.6260 with; DL bias -0.033 without,
   -0.122 with (the model priced linemen 5% too high). The diagnosis: PFR's advanced table only has a row for a
   player-game in which he recorded something, and the research script computed the profile and the ratio on
   those rows only, so a low-pressure lineman entered the table mostly in games where he made tackles. That is
   conditioning on the outcome. On the full game list (every game he played, a missing PFR row counted as a
   missing value, not as zero pressures), the buckets sit on the model: 0.996 / 1.005 (1 or fewer), 0.970 / 1.016
   (1-2), 0.964 / 0.970 (2-3). Nothing to fix. Kept: `press` loaded from PFR, `press_pg` on each lineman's
   projection, and a Run-stuffer / Interior / Pass rusher tag on the card that says what kind of lineman he is and
   claims no model effect. Pitfall recorded below.
5. Game total (nflverse schedules): slope -0.006 per 10 points, held-out miss -0.009%. Nothing.
6. Opponent implied points (total and spread): slope +0.004 per 5 points, -0.027%. Nothing; the spread tilt
   already carries what there is.
7. Playing surface (grass / turf): actual over model 0.997 / 1.004 on grass, 0.988 / 0.994 on turf. Nothing.
8. Opponent pass rate over expected (play-by-play, prior games): by position, held-out miss +0.045% (LB) to
   -0.013% (DL), biases unmoved. The run/pass mix factor already uses the opponent's actual mix.
9. Opponent shotgun rate: -0.011% to +0.014%. Nothing.
10. Opponent plays per drive, third-down rate, share of plays gaining 3 yards or fewer: -0.039% / -0.042% /
   -0.016%, biases unmoved. Below the bar (a piece earns its place at about -0.1% or a bias it fixes).
11. Next Gen Stats rushing of the opponent (rush yards over expected per attempt, efficiency): -0.009% to
    +0.002%. Nothing.
12. Next Gen Stats passing of the opponent's QB (time to throw, completion over expected): -0.029% to +0.016%,
    CB bias moved the wrong way. Nothing.
13. ESPN QBR: no loader in nflreadpy; not reachable as a table. Skipped.
14. Special-teams tackles in the player stats: there is no separate column (`def_tackles_solo`,
    `def_tackle_assists`, `def_tackles_with_assist`, `def_tackles_for_loss` only), and the books settle on the
    same box-score total, so there is nothing to separate.
15. nflverse weekly rosters (status ACT / RES / INA / CUT / RET / DEV / EXE / TRT): usable to drop a regular who is
    gone (cut, retired, reserve) from the vacancy logic. Not adopted this round because the ESPN feed covers the
    live hole (IR and suspension); a candidate for the next round as a second check on "gone".
16. ESPN scoreboard: reachable; carries nothing the nflverse schedule lacks (kickoffs, venues).
17. PrizePicks (HTTP 403) and Underdog (HTTP 426) projection APIs: refused to scripts. Their lines cannot be
    read; no pick-'em cross-check this round.
18. Divisional matchups (2026-11-01, at the owner's question; nflverse team divisions): actual over model 0.987 /
    0.986 in divisional games against 0.982 / 0.992 in the rest (10,156 divisional games of 28,861), no consistent
    sign by position, solo +1 point in both halves, first and second meetings alike. Divisional games are about
    5% more spread (residual var/mean 1.41 vs 1.34; miss 1.64 vs 1.62), a familiarity effect on the spread and
    not the level, too small for a parameter. Nothing to add.

### What the owner should read into it

- Of ten more "big" game-context sources (totals, implied points, surface, tendencies, NGS), none moved the
  held-out miss by a tenth of a percent. The model's own history, snaps and role already carry them. The find
  is in the minutiae: who is suspended or on reserve and not on the league report.
- The validation protocol caught a factor that a research script had "proven" in both halves of the data. A
  side-script result is a hypothesis until the pipeline's own backtest, on the full game list, agrees.
- The outside feeds are there to catch what the league report and the model cannot see (a suspension, an IR stay)
  and to show the owner an outside number next to ours, not to steer picks. The cross-check is logged so it can
  be judged later, the way everything else here is.

## Why the CB Unders hit (2026-10-31, afternoon MDT, at the owner's question)

The owner asked why the corner Unders have been so good and what the model sees that the books do not. The
record on the site: CB Unders 27-5 (combined 14-3, solo 13-2) against a claimed 55%. Before answering, the
question was put to the data four ways. Scripts: `scratchpad/cb_why*.py` (not in the repo).

1. **The whole CB market went under in week 7, not just our picks.** Every closing CB line pulled in week 7,
   picked or not, across every book: 108 lines, **74% under** (solo lines 82%, combined 67%). DL lines 80% under,
   S 61%, LB 45%. Our CB Unders hit 74-84%, about the market's own base rate. In week 7 the edge was that the
   books' CB lines sat where they always sit, near the season average (0.1 below it, like every position), and
   corners came in far below their averages: CB solo tackles ran at 1.02x their season pace in week 7 against
   1.31-1.39x in weeks 5-6, and the CB solo share of tackles fell to 0.57 from 0.68-0.70 (2023-25 norm 0.66-0.69).
   That is the league solo-crediting dip found on 2026-10-30 (league solo share 0.50 in week 7), hitting the
   position whose tackles are most often credited solo. A scorer's habit, not a football event.
2. **Tackle counts are not skewed for corners.** 2023-2026 regulars, 11,400 games: 45% of games land below the
   player's own average at every position; a half-point line at the average goes under 48% of the time for CB,
   DL, LB and S alike. There is no free Under in the shape of the distribution.
3. **The books did not come to us.** Our CB Unders beat the closing line 21% of the time (LB 29%, S 26%); the
   closing-line probability moved 0.2 points on average. Whatever we see, the market did not price it in by
   kickoff, which is either a persistent blind spot or a week of luck. One week cannot say which.
4. **The model is lower than the books on corners, consistently.** On our CB Under picks the model gave the Under
   58% and the book's price 47%; the model's own number sat 0.2-0.6 under the line (Ward 2.2 vs 2.5, Rodgers 1.8
   vs 2.5, Humphrey 3.8 vs 4.5, Stephens 2.9 vs 3.5). That gap comes from pieces the books do not use:
   - **coverage usage (PFR targets per game):** a corner's tackles come from his own targets; one who is not
     thrown at (a shadow corner, or the side quarterbacks avoid) tackles less than his average says. The backtest
     says the PFR piece earns its place (miss 1.6305 without, 1.6217 with: the largest single-piece gain).
   - **the dome factor (+5% for corners indoors):** more passing, more corner tackles; absent indoors, the
     number is lower than a season average built partly on dome games.
   - **league solo drift:** solo lines hang on season averages while solo crediting drifts down through a season
     (CB solo share 0.69 in weeks 1-7 to 0.66 after; league 0.55 to 0.51 in 2025) and dipped hard in week 7.
     Added after week 7, so it earned none of the record above; it is there for the next dip.
   - **the lowest dispersion of any position** (variance/mean 1.19 for CB against 2.08 for LB): a corner's
     count is the most predictable, so the same gap between the model and the line is worth more probability
     for a corner than for a linebacker, and the per-position phi lets the pricer say so.
   - **opponent run/pass mix:** a corner facing a run-heavy offence sees fewer completions to tackle.

What to tell the owner: a real structural reason (books hang corners at the season average and do not adjust for
targets, venue, scorer drift or mix) plus one very favourable week. Keep betting the CB Unders the model likes,
keep the segment correction (it feeds +8 pts into CB Under claims, shrunk by n/(n+40)), and judge it on the
closing-line share and the next hundred corner picks, not on 27-5. The A/B/C grade order and the solo Under
question stay on the same watch.

Data note: two "Byron Murphy"s share a name key (MIN corner, SEA lineman); the pricer separates them by the
game's teams, so no line was mispriced, but any by-name analysis must use the logged `group` or the team.

## Luck or skill: the whole record against the market (2026-10-31, afternoon MDT, at the owner's question)

After the corner answer the owner asked for every other place we "got lucky by accident", and for a weekly
review that says whether we saw a result coming. The test is the one that undid the corner story: for each kind of
pick, our hit rate against the share of EVERY closing line of that kind on the board (one consensus line per
player and market, picked or not) that resolved the same way. That share is the market's base rate for the week;
lift = our hit rate minus it, what our choice of lines added. Beating the close is the second tell.

Week 7, all plays (245 consensus lines on the board):

| Kind | Picks | Hit | Claimed | Whole market | Lift | Beat the close |
| --- | --- | --- | --- | --- | --- | --- |
| Under | 165 | 56% | 62% | 58% | -1 pt | 25% |
| Over | 65 | 43% | 60% | 42% | +1 pt | 39% |
| Under solo | 97 | 64% | 63% | 67% | -3 pts | 21% |
| Under combined | 68 | 46% | 60% | 48% | -3 pts | 31% |
| Over solo | 24 | 33% | 58% | 33% | 0 | 38% |
| Over combined | 41 | 49% | 62% | 52% | -3 pts | 39% |

Read it plainly: **in week 7 our choice of lines added nothing.** Every kind of pick hit at the rate the whole
board did. The 131-116 record, the "solo Under is a huge play", the Over problem: all of it is the shape of one
week in which two thirds of solo lines went under league-wide (the solo-crediting dip), not something the model
saw. We did not beat the closing line either (25% on Unders). The only pockets with real lift are corner Unders
(+24 pts combined, +10 solo, 31 picks) and, on the other side, safety combined Unders (-17) and linebacker
combined Unders (-9), where our picks did worse than the board. Week 8 so far is 14 Unders at 71% against a 63%
board (+9, few picks) and three Overs that all lost.

What this changes:
1. The claim "solo Unders are our play" is withdrawn as a finding. The solo Under hit 64% because 67% of solo
   lines went under; the model's share of that was zero. The solo drift factor (3-week league solo share) is the
   right response to the mechanism and stays; the segment correction, which learned the week's hit rates, is now
   partly learning the board's drift rather than our selection (see the pitfall below). It stays for now, shrunk
   by n/(n+40), and is reviewed against lift from here on.
2. The weekly review the owner asked for is automatic. `luck_check` in `pipeline/grade.py` runs at every grading:
   per week and kind of pick (side; side x market; side x market x position), picks, hit, claimed, the market's
   base rate over the whole board, lift, beat-the-close, and a verdict ("the market went our way", "we picked
   well", "we picked badly", "nothing added", with a "few picks" tag under 8). It is on the Track record tab
   ("Luck or skill: did we see it coming?") and in `data/weekly_five.md`. The weekly post-mortem protocol now
   starts from this table: a week is only evidence for a piece of the model where lift and beat-the-close agree
   with the record.
3. What is "fixable": nothing in the record was a bug. The model prices every line at the base rate the market
   itself produced, which is what a model with no selection edge looks like after one week. The pieces with a
   measured out-of-sample gain (per-snap base, PFR targets, dome corners, the corrector) are the case for a
   selection edge; one graded week with 245 lines cannot show one either way. Judge on lift over 500 lines.

## Research round 6: cornerback quality, opponent passing, and stake size (2026-11-02, 3 am MDT, at the owner's request)

The owner's question after Sunday: "in retrospect I should have put 5 units on Nohl Williams: he's very good and the
Broncos can't pass." Two hypotheses (a good corner tackles less than the model says; a bad passing offence makes it
more so) and one stake question. Data: PFR advanced defence 2022-2026 (targets, completions, yards, TDs and
interceptions allowed, per game; each corner's prior games this season shrunk 30 targets toward last season, then
the league), nflverse play-by-play 2023-2026 (each offence's prior dropbacks this season: EPA per dropback, yards
per dropback, completion rate, sack rate). Tested on the current model the usual way: fit 2023-24, check 2025-26
(28,861 games through 2026 week 7; 3,722 corner games with 10+ prior targets). Scripts: `scratchpad/cbq/` (not in
the repo).

**1. Corner quality: no effect the model misses. Rejected.** Actual over the model by coverage tier flips sign
between the halves: yards per target allowed under 6, 1.084 (2023-24) and 0.956 (2025-26); passer rating allowed
under 80, 1.036 and 0.999; completion rate allowed under 58%, 1.064 and 1.012. As slopes, held-out error got worse
(+0.13% yards per target, +0.32% rating allowed). Targets per game shows a consistent pattern at the extremes
(3 or fewer, 1.107 and 1.069; more than 7.5, 0.905 and 0.904), but the existing PFR target factor already carries
it; a steeper refit gains 0.1% on corners only. Not adopted.

**2. Opponent passing quality: real, but too small for a factor. Rejected, kept as a candidate.** For corners and
safeties nothing. For linebackers and linemen there is a consistent pattern: against offences well below the
league that season in EPA per dropback (0.1 or more below), LBs ran 1.056 and 1.026 of the model and DL 1.015 and
1.012. Against offences 0.1 or more above, LBs ran 0.965 and 0.967 and DL 0.953 and 0.950. A worse passing offence
means more short completions, scrambles and sacks for the front seven to finish; a good one means more yards after
the catch for safeties and corners. But as a factor measured against each season's league, it improves the
whole model's level-matched miss by only 0.06% in both halves (LB and DL 0.11%), and solo tackles slightly worse.
An absolute (not season-relative) version looked better on held-out games, -0.18%, but only because the league's
passing improved in 2025-26 and the factor pulled every projection down, which raw MAE rewards on count data. Below
the 0.1% bar. Reopen if the two-bucket form clears it on a full 2026 season.

**3. Our corner picks by corner quality: no lift.** Corner Unders on good corners (rating allowed under 85) went
13-8 (62%), on the rest 22-10 (69%). Across every graded corner line on the board, good corners went under 57% and
the rest 55%.

**4. Nohl Williams, week 8.** Through week 7: 68 passer rating allowed, 6.1 yards per target, 5.2 targets a game
(top-tier coverage). Denver before week 8: -0.10 EPA per dropback, 5.0 yards per dropback (bottom tier). The model
had four A-grade Unders on him: solo Under 3.5 (lock score 85, a Sunday lock) and combined Under 4.5. Actual: 1
solo, 4 combined. All four won. The corner-quality and opponent-passing checks above say that combination does not
go under more than the model already expects; the model was right about him for the reasons it always uses.

**5. Should the grade scale the stake, and was 5 units right?**

| Grade | Graded | Hit | 95% lower bound | Claimed | Break-even at the average price |
| --- | --- | --- | --- | --- | --- |
| A | 18 | 89% | 67% | 65% | 59% |
| B | 97 | 57% | 47% | 58% | 50% |
| C | 84 | 52% | 42% | 54% | 48% |

- Only A has a lower bound above its break-even. B and C are not yet shown to be profitable on their own record.
  The suggested stakes (A 1u, B 0.5u, C 0.25u) already follow that order; they stay until 30 graded A picks, the same
  rule as the grade weights.
- Kelly on the model's claimed chance, Williams solo Under 3.5 at -155: claimed 65.5%, full Kelly 12% of bankroll,
  quarter-Kelly 3%. Combined Under 4.5 at -105: claimed 62%, quarter-Kelly 5.5%. With a unit at 1% of bankroll,
  quarter-Kelly is 3 to 5 units, so 5 units was not reckless by the model's own numbers.
- But both claims include +8 points from the corner-Under segment correction, which learned from a corner record
  that the luck table puts down mostly to the whole board going under. Without it, the solo claim is 57.5%, below
  the break-even of 60.8% at -155: no bet. The case for a big stake on Williams rested on the part of the model
  with the least evidence behind it. Stake size follows the grade, not the hindsight.

## Research round 7: rain and linebacker Overs (2026-11-02, 3 am MDT, at the owner's question)

The owner asked, after the Falcons at Buccaneers game on 2026-11-01: "in heavy rain games, is the Over on linebacker
tackles a lock?" The plan was measured rainfall (Open-Meteo's ERA5 archive, mm per hour at each stadium through the
game). Open-Meteo refused this machine's requests on the day ("daily API request limit exceeded", shared network),
so game weather comes from the kickoff weather note in nflverse play-by-play ("Rain, Temp: 78 F, Wind: E 9 mph"),
parsed into dry, rain, heavy or steady rain, and snow, with the reported wind. Outdoor and open-roof games only:
2023 to 2026 week 8, 633 games: 586 dry, 37 rain, 2 heavy or steady rain, 8 snow. Scripts: `scratchpad/rain/`.

**1. Sunday's game first.** Falcons at Buccaneers, Raymond James Stadium, "Rain, 78 F, wind E 9 mph". Only two
linebacker combined lines were up: Josiah Trotter 9.5 (6 tackles, Under) and Alex Anzalone 5.5 (6, Over). One each
way. Across all eleven combined lines in the game, six went over and five under. Our picks in the game went 5-7, LB
Unders 2-1. Nothing in it says linebackers out-tackle their lines in the rain.

**2. Every rain game since 2023, against the model** (actual over the model's number, 2023-24 | 2025-26):

| Condition | Games | LB combined | LB solo | DL combined | S combined | CB combined |
| --- | --- | --- | --- | --- | --- | --- |
| Dry | 501 | 1.009 / 1.008 | 0.988 / 0.983 | 0.977 / 1.008 | 0.987 / 0.999 | 1.002 / 0.986 |
| Rain | 29 | 1.042 / 0.978 | 0.990 / 0.998 | 0.947 / 0.907 | 0.978 / 0.940 | 0.999 / 1.069 |
| Heavy or steady | 2 | 1.134 / 0.947 | 0.969 / 1.200 | 1.132 / 1.171 | 1.528 / 0.888 | 1.401 / 1.147 |
| Snow | 8 | 0.954 / 0.887 | 0.914 / 0.900 | 1.061 / 1.103 | 1.007 / 1.095 | 0.871 / 1.173 |

Rain flips sign between the halves for linebackers and, as a test of the bet itself, a linebacker Over at a
half-point line at his season average hit 45.2% in rain against 45.6% when dry (321 and 5,313 games); the model's
own Over chance on those lines was 44% and 45%. Two heavy-rain games (14 linebacker games, Overs 36%) are too few to
say anything.

**3. Why rain does not help the Over.** Per offence-game against the same team's season average, rain games had
the same number of plays (-0.1), 0.6 more runs and 0.8 fewer passes, but 1.4 fewer completions and 0.9 more
incompletions. The extra runs a linebacker can tackle are cancelled by the completions that never happen: an
incompletion is a play with no tackle. Snow cuts passing harder (3.9 fewer passes, 3.5 fewer completions).

**4. Wind.** At 18 mph or more (11 games) linemen ran over the model in both halves (1.119, 1.169) and linebackers
and corners under it in the second; 11 games is too few to act on.

**5. Do the books move linebacker lines for rain?** Lines are collected from 2026 week 7 on; Sunday's game is the
only rain game with lines, so this cannot be answered yet.

**Verdict: rejected.** Rain is not a lock for linebacker Overs and not an edge: the extra runs are offset by fewer
completions, and the result flips between the halves. Overs stay ineligible for locks. To reopen: measured
precipitation (mm) once Open-Meteo answers again, to separate real downpours from drizzle, and the line check once
a season of rain games with lines exists. Wind at 18 mph or more for linemen is a candidate to watch.

## Standing watch: grade order (opened 2026-10-30, evening MDT, at the owner's request)

Live record by grade as of 2026-10-30: A 4-2 (67%), B 13-5 (72%), C 13-13 (50%). A below B on six A picks is not
yet evidence of anything, but the grade order is the one thing the grading formula must get right, so it is
watched after every slate (the Track record tab prints "Grade order check" in red while A trails B) and reviewed
after Sunday's games are graded (week 8). Decision rule: at 30 graded A picks, if A's hit rate is still below B's,
`LOCK_WEIGHTS` is re-fitted on the graded picks (which parts of the score actually predict a hit), and until then
the suggested stakes stay as they are. Under the 2026-10-30 pricing audit the lock score already changed (EV part
saturates at 10%, claimed chance shrunk), so A picks from here on are a different population from the first six;
the review keeps the two apart.

**Review after week 8 Sunday (2026-11-01, 11:20 pm MDT; graded by a hand-run daily job).**

| Grade | All live | Before the audit | After the audit (Sunday) |
| --- | --- | --- | --- |
| A | 16-2 (89%), +9.46 u at stake | 4-2 (67%) | 12-0 (100%) |
| B | 55-42 (57%), +6.26 u at stake | 13-5 (72%) | 42-37 (53%) |
| C | 44-40 (52%), +2.46 u at stake | 13-13 (50%) | 31-27 (53%) |

- **A is no longer below B.** The order is A > B > C on the live record. On the post-audit population alone, A is
  12-0 and B and C are level at 53%: the score separates A from the rest, and does not yet separate B from C.
  18 graded A picks is still under the 30 the decision rule asks for; no change to `LOCK_WEIGHTS`.
- **Read the 12-0 with the luck table beside it.** All twelve Sunday A picks were Unders, eleven of them solo,
  on a day the whole board's solo lines went under 64% of the time (luck table: our solo Unders 63% vs the
  board 64%, lift -1 pt; beat the close 24%). Twelve straight at a 64% base would happen by chance about 1 time
  in 200 if they were independent, but they are not: same day, same direction, same crediting drift. It is a
  real point for the A band and a weak one, until A keeps its lead over the board on a day the board goes over.
- Sunday: all plays 85-64 (+18.4 u at 1 u each), Overs 5-3, Unders 80-61. Locks 5-0 (Winston, Williams,
  Marshall, Trader, Styles; all solo Unders), week 8 locks 6-2 with Thursday, 7-2 live. Sunday's parlay
  (three legs, +346, 0.1 u) won: parlays 1-1 live, +0.25 u.
- Week 8's full post-mortem waits for Monday's game (Seahawks at Bears) to be graded on Tuesday.

## Weekly post-mortems

Each post-mortem starts from the luck table (Track record tab; `data/weekly_five.md`): per kind of pick, our hit
rate against the whole board's base rate and the beat-the-close share. Only where lift and the close agree with
the record is the week evidence about the model.

### Week 8 through Sunday, 2026 (graded 2026-11-02; Monday's game pending; review at the owner's request, 4 am MDT)

**Record:** 95-71 (57%), +23.0 u at 1 u each; locks 6-2; parlays 1-1. Claimed 57.2%, hit 57.2%: calibrated in total,
and the luck table says the whole board went the same way (Unders 58% vs a 57% board, lift +1; solo Unders 63% vs
64%). By grade A 13-1, B 49-40, C 33-30. By kind: Under solo 65-38 (+25.5 u), Under combined 25-27 (-1.8 u), Overs
5-6. Signals: the outlier fade went 13-16 (-4.0 u) after 17-6 in week 7; price-gap picks 81-55. No role-shift flag
was on any graded pick.

**Why the 71 losses missed.** Every loss was put against what happened on the field: the player's snap share
against the share the model expected, his team's plays faced against the expected plays, and what was left (the
tackle rate itself).

- 40 of the 71 losses were within one tackle of the line; 20 were 1.5 to 2.5 off; 11 were blown out by 3 or more.
- Snap share and plays faced together explain 13% of the miss against the model (an R-squared of 0.13). The rest
  is the tackle rate on a normal day's work: 50 of the 71 losses came with normal snaps and a normal number of
  plays. That is variance, and no data set removes it.
- The explainable part is plays faced. Under losses came in games where the defence faced 3.3 more plays than
  expected; Under wins 0.3 fewer. By defence: Buffalo faced 16 fewer plays than expected and our picks on its
  defenders went 9-2; Minnesota, Arizona, Cincinnati, Washington, Carolina, Atlanta and Denver faced 6 to 12 more
  and our picks on them went 7-27. All 11 blow-outs sat in high-play games (Anthony Hill 10 solo on 60 plays
  faced, Byron Murphy 10 combined on 61, Alex Singleton 14 on 56).
- Snap surprises were the minor cause: 9 losses from a man playing far fewer snaps than expected (benched or hurt
  in-game) against 13 wins from the same thing; 5 losses from far more snaps (C.J. Henderson, 100% of the snaps
  against 79% expected, 8 tackles against a 4.5 line).

**Can plays faced be forecast better?** Tested on 1,848 team-games since 2023. The model's expectation (the
defence's own average and the opponent's, shrunk toward last season) has a correlation of 0.15 with the game's
plays; the residual spread is 7.7 plays on a mean of 50. Adding the spread (an underdog's defence faces 2 more
plays at 7+ points, a favourite's 2 fewer), the opponent's no-huddle rate and plays per drive, the own offence's
plays per drive and the opponent's pass rate: held-out residual 7.65 to 7.77 against 7.66 without. Nothing
forecasts a game's plays beyond the spread, which the spread tilt already carries. Plays faced are game-script
noise, and a tackle line pays on them.

**Data sets not yet explored, tested now.**

- *FTN charting (nflverse, 2023-2026, play by play):* the opponent's play-action, screen, RPO, scramble (QB out
  of pocket) and motion rates, and the defence's own box count and blitz rate, each as a factor by position, fit
  2023-24 and checked 2025-26. 28 tests; none consistent in both halves. Largest held-out gains (safeties vs
  screens -0.41%, linebackers vs motion -0.40%) have the opposite sign in the fitting half. Rejected.
- *nflverse participation (on-field defenders per play, coverage scheme man or zone, defenders in box):* covers
  2016-2025 only; not published for 2026, so it cannot price a live line. Kept for research (whether a corner's
  man-coverage share predicts his tackles) if it returns.
- Open-Meteo rain, corner quality, opponent passing: research rounds 6 and 7 (above), all rejected or below the
  bar.

**What changed because of it (validated on the live record, both weeks separately).**

1. **A pick needs a claimed chance of at least 55%** (`PICK_MIN_CLAIM`). The 108 picks claimed under 55% went 44-64
   (-6.1 u): week 7 25-33 and -0.5 u, week 8 19-31 and -5.7 u. Those are plus-money sides where the return clears
   6% on a coin-flip claim. Under the rule: week 7 94-75 (+6.2 u) instead of 121-109 (+4.4 u); week 8 73-40
   (+29.9 u) instead of 95-71 (+23.0 u). One lock of nine would not have been a pick (and it won).
2. **A signal no longer lowers the bar** (`SIGNAL_BAR` 0.04 to 0.06). The 12 picks taken at 4-6% return went 3-9
   (-6.5 u); the fade signal itself went 30-22 over the two weeks and keeps its place in the lock score.
3. Smoke check: every pick clears both. Legend updated. Revert if, over the next 100 picks that the floor would
   have dropped, they hit above 52%.

**Standing watch.** LB combined Unders are 8-23 live (3-11 this week, 29 points below the board). The segment
correction already sits at its cap for them (-8 points on the claim); if the next 20 go the same way the cap
rises for that segment.

### Week 8 Thursday, 2026 (GB at CAR; graded 2026-10-30, morning MDT)

**Record:** 10-7, +4.56 units. **Locks 1-2:** Xavier McKinney Under 2.5 solo won (2); Isaiah McDuffie Under 7.5
tackles+assists lost (10), score 83, grade A; Bobby Okereke Over 6.5 lost (5), score 65. The McDuffie lock is the
worst miss the model has produced and the owner's question was the right one: where did it go wrong?

**What happened.** McDuffie was a 2% part-timer in week 1 and worked up to 55% of snaps by week 6. Green Bay then
traded Quay Walker, and in week 7 McDuffie played 100% of the snaps for the first time and made 11 tackles. The
model looked at a season average of 4.7 built on part-time games, applied its damped snap-share trend (last three
games 67% vs 38% season: x1.29), and projected 6.1. It then called the 11 an **outlier** (3+ above his base) and
fired the outlier-fade signal: lower pick bar, a signal bonus in the lock score, and "fading an outlier last game"
on the card. His consistency read 6 of 7 under 7.5, all from part-time games. The book had him at 7.5, a starter's
number, because the book knew his role had changed. He played 100% again and made 10.

So three things went wrong at once, all the same root cause: **his season history did not describe his current
role**, and every piece of the lock score (projection, fade signal, consistency) was computed from that history.

**Evidence across the backtest** (28,861 defender-games; "new role" = season share under 60%, last game 60% or
more, at least 1.5x his season share: 850 games in 2023-24, 508 in 2025-26):
- Actual ran 19-23% over the full model on new-role games in both halves of the data, and 30-34% over it when the
  jump was 2x or more. Everywhere else the model is unbiased.
- The outlier-fade signal, which works on settled players (actual under the model 56% of the time, under the last
  game 93%), fails on new-role players: under the model only 45%, actual 18% over the model on average.
- New-role games are far more spread: variance/mean 1.9 against 1.4 for everyone else (LB 2.4 vs 1.5). The model's
  probabilities for them were overconfident.
- A mean correction fixes the direction without fixing the spread: x ratio^0.25 (cap 2.5) brings the bias on
  new-role rows from +0.63 to -0.02 tackles (train +0.79 to +0.14) at a cost of 0.05% overall MAE, because a
  right-skewed count is best scored at its median but must be priced at its mean. Stronger corrections overshoot.

**What changed because of it** (`NEW_ROLE` in config.py):
1. Projection x (last-game share / season share)^0.25, capped at 2.5x, for new-role players. McDuffie would have
   been priced from 7.4 rather than 5.9 before the line blend.
2. No outlier-fade signal when the big game came on a starter's snaps: that game is the new normal, not noise.
3. A wider count distribution for new-role players (phi +0.5), so their side probabilities are not overconfident.
4. Consistency counts in-role games only (games at 70%+ of the snap share he played last game); fewer than three
   such games and it counts for nothing, instead of counting part-time games as evidence.
5. **A new-role player is never a lock and never a parlay leg**, whatever his score, until his season share catches
   up (the flag clears on its own as his average share rises). Tagged "New role" on the card with the numbers.
6. The corrector gets the snap jump as a feature; the backtest carries a "without new-role factor" row and a
   new-role subset diagnostic (count, actual vs model with and without the factor).

**The audit that followed (same morning).** The owner's next question was the right one too: what else falls
through the same crack? Every situation where a season log stops describing a player was measured the same way
(actual against the full model, 28,861 games). Four more showed up, all market-free, all now handled:

| Situation | Games | Actual vs model | Spread (var/mean) |
| --- | --- | --- | --- |
| Settled starters (reference) | 11,254 | +0.4% | 1.27 |
| New role: part-timer who just played a starter's snaps | 1,050 | +19 to +23% | 1.9 (LB 2.4) |
| Reduced role: last game's snaps under 70% of his season share | 4,538 | -5 to -14% | 1.4-1.8 |
| Back after 3+ weeks out | 1,549 | -10 to -12% (starters -13%) | 1.6 |
| Back after one missed game, no bye | 1,193 | -11% | 1.5 |
| First game for a new team | 124 | -20% | 1.7 |
| Only 1 game at his current snap share | 1,666 | +12% | 2.3 |

And the outlier-fade signal is only half right: an **Under after a big game** works for settled players (actual
2% under the model, 93% under the big game); an **Over after a low game** does not (actual 4.5% under the model
for settled players, 18% under when he had simply played fewer snaps, 13% under after an absence). A low game
predicts lower, not a bounce, which the "what follows an outlier" table had been saying all along.

Fitted on 2023-24 and checked on 2025-26 (`ROLE_SHIFT`): reduced role x ratio^0.1 (bias -0.25 -> -0.02 train,
-0.16 -> +0.07 test, and overall error -0.7%), 3+ weeks out x0.95 (kept conservative: the halves disagree on size),
one missed game x0.92, new team x0.90 (small sample, conservative). The Over-fade signal is removed; the Under-fade
fires only in a settled role. The corrector gets the snap jump, the weeks since his last game and the team change
as features.

**The lock-eligibility checklist** (`LOCK_RULES`, computed by the pricer, market-free, shown on every card as
"Not lock-eligible: ..."): never a lock or a parlay leg when he is in a new role, a reduced role, back from an
absence, in his first game for a new team, has fewer than three games in his current role (unless every game he
has played was in it), or is listed questionable. The lock score's sample part now counts in-role games, and
consistency counts in-role games only. A mid-season team change is read off the latest depth chart before he
plays for the new team, so he is projected for the right game. The Model check tab has a "Where the model is
weakest" table so these subsets are watched every day.

**Validation (daily run on 2026-10-30 data, 28,861 games).** Full model error 1.6472 -> 1.6321 (-0.9%), the
largest single gain since the project started, almost all from the reduced-role and absence factors; the row
without the role-shift factors is the worst ablation in the table. Every weak spot now sits within 5% of
unbiased (new role +2.5%, reduced role +2.8%, 3+ weeks out -1.6%, one missed game +1.2%, new team -5.2%; without
their factors +22%, -9%, -11%, -11%, -21%). 2026 walk-forward fold 1.6156, with the corrector 1.5867. Replays under
the final rules: **Thursday week 8** locks 2-1 (+1.56u: McKinney W, Bullard W, Okereke L; McDuffie is priced at 7.5
against a 7.5 line and is not a pick at all), all plays 10-7 (+4.56u), the Thursday parlay a 2-leg win; **week 7**
locks 3-2 (+0.22u), all plays 100-93 (+8.06u), A grade 8-5. Live, the McDuffie loss stands: locks 2-2.

**What this does not do.** It does not make a lock a sure thing: a lock is the model's most confident pick, and
the live record of locks is now 2-2. What it guarantees is that a lock is never again built on a game log that
belongs to a different role. The honest target stays 70% on locks over the season, judged on hundreds, not three.

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

### 2026-11-02, night MDT (workflow YAML broken by the seal step name; fixed)
- The seal step's name held a colon, which broke both workflow files; GitHub answered "workflow does not have a
  workflow_dispatch trigger" and the scheduled pulls stopped for about three hours. Renamed; the smoke test now
  parses every workflow file. Pitfall recorded.

### 2026-11-02, late evening MDT (several passwords)
- Owner asked what it would take to have more than one password. The sealed files now carry one random data key
  wrapped once per password (`SITE_PASSWORDS`, one `name: password` per line; `SITE_PASSWORD` still works);
  the browser tries each wrapping with the password typed. Removing a line shuts that person out at the next run
  without touching anyone else's password. Smoke check with three passwords and a wrong one; browser check with
  two. The sealed format is versioned (v2); v1 files still open.

### 2026-11-02, evening MDT (the gate: the site sealed behind a shared password)
- Owner does not want the board public yet but wants a few people to see it. GitHub Pages serves every file to
  anyone with the link, so `pipeline/seal.py` encrypts each site JSON after every job (AES-256-GCM, key from the
  password by PBKDF2-SHA256 at 200,000 rounds, one salt per run, a nonce per file), deletes the plaintext, and the
  page decrypts in the browser (WebCrypto) after asking for the password once per device; wrong password, ask
  again; "Lock this device" forgets it. `run.py seal` runs in both workflows with the `SITE_PASSWORD` secret; the
  jobs read the sealed meta back with the same secret so credits and the week carry over. No secret set: the site
  stays open and says so in the log. Smoke checks: files sealed and plaintext gone, decrypts with the password and
  not without, a pull after sealing still works, no secret leaves the site open. Checked in a headless browser:
  gate shown, wrong password refused, right password opens the board, remembered on reload.
- What it does not do: the repository is public, so the picks log, odds snapshots and projections are readable on
  GitHub. README says how to make the repository private (Pages needs a paid plan for that). The owner sets the
  secret; nothing in this session can.

### 2026-11-02, evening MDT (a lock needs an A)
- Owner, after asking whether Monday's lone lock (Thieneman Under 4.5 solo, score 61, grade B) was a true lock or
  just the best of a thin night: "locks should only be a lock if the model strongly believes it will happen, not
  just because the model sees that as the only viable pick." `LOCK_MIN_SCORE` is now the A bar (72) instead of the
  B bar (55); the slate caps (3 and 5) are maxima, and a slate with no A has no lock. Live evidence: locks scored
  72 or better went 5-1, locks at 55-72 went 2-1 on three picks; A grades 16-2 against B 55-42. Site: the locks box
  and the Track record lead say so; an empty slate reads "Locks · none" with the reason. Smoke test.
- Also recorded: the two-leg parlays suggested by hand on 2026-11-02 ranked legs by the model's raw chance, not the
  segment-corrected claim the board uses; Thieneman Under 6.5 combined was a pass on the board (claimed 48%) while
  the hand ranking had it at 58%. Pitfall: any pick or parlay handed to the owner must come from `price_lines`
  output (p_claim, ev, pick), never from model_over alone.

### 2026-11-02, 10:20 am MDT (one-tap parlay links)
- The 9 am pull carried links for every DraftKings outcome (`https://sportsbook.draftkings.com/?outcomes=<id>`);
  several ids join with "+" in one query, which the owner's slip on Sunday night confirmed loads as one parlay.
  The site now builds that link: "Tail this parlay at DraftKings: all N legs in one slip" on an open parlay whose
  legs are all DraftKings, and on My board "open every unstarted bet in one slip" when two or more have links. Any
  other book, or a mixed-book parlay, keeps one link per leg until its format has been seen; FanDuel and
  theScore Bet have posted no lines with links yet. Site only.

### 2026-11-02, midday MDT (parlay legs: combined tackles only)
- Owner: the books refuse solo-tackle legs in a same-game parlay, so the recommended parlay must be combined
  tackles + assists on every leg. `PARLAY_MARKETS` in `config.py`; `choose_parlay` filters on it; the board note,
  the parlay-history lead and a smoke check say so. Solo picks stay picks and locks; they just never enter the
  parlay. Note for the record: solo Unders have been the stronger kind (65-38 in week 8 against 25-27 combined),
  so the parlay gives up some chance for placeability; the parlay record is judged on its own line.

### 2026-11-02, late morning MDT (the rundown: a templated read-up under every line)
- Owner asked for a Kyler Gordon-style read-up on every bet every day. `rundown` in `pipeline/model.py` writes one
  from the numbers the pricer already used: who he is (season rate, snap share, last season when it is a full
  one), his last three games with their snap shares, a change in expected share, the model's own number and the
  priced one, the side's chance, claim and return, what the book's line implies about his snap share (the share at
  which the model's number meets the line, since the per-snap part scales with share) and so whether the two
  sides disagree about playing time or tackle rate, how many of his games landed on this side, the nudges
  (questionable, vacancy, new or reduced role, absence, new team, opposing QB or RB out, depth chart move, the
  stadium's crew, dome, bye, the outside consensus) and the pick or pass with its reason. Every sentence is a
  number restated; no language model, no view the data does not hold. It sits at the top of every card's "Why"
  box, for passes too, and in the week's line file for My board. Smoke test; checked on tonight's 20 lines.

### 2026-11-02, morning MDT (one name per player: PFR-named feeds matched by id)
- Owner asked why Cam Lewis (CHI) had no snap counts. The snap-count and PFR advanced feeds print Pro Football
  Reference's names ("Cameron Lewis"); the stats feed prints the league's ("Cam Lewis"); the join was by name, so
  thirteen regulars had no snaps at all this season (Pat Surtain II, Kam Curl, Greg Rousseau, Nate Landman, Foley
  Fatukasi, J.T. Tuimoloau, Que Robinson, Cam Lewis among them): no per-snap base, blind role checks, "snap counts
  missing" on every line. Now `pfr_name_map` (nflverse players table, pfr_id to display name, 99.8% of ids) gives
  both feeds the stats feed's name (`_canon_names` in `load_snaps` and `load_pfr_def`); the printed name stays
  where an id is unknown. After: 2 unmatched (rookies missing from the table), 99.7% of snap rows join a stats
  row; Cam Lewis carries six games of snaps and his projection moved from 4.0 to 4.55 (share 84%).
- Validation: smoke test; real-data daily in a scratch copy: backtest 29,352 games (491 more, the recovered
  players' games), full model 1.6212 / level-matched 1.6192 against 1.6217 / 1.6195 before on 28,861; the
  per-snap base ablation gap grew (1.6306 without). 2026 fold 1.5975, corrector blend 1.5772.
- Pitfall: two feeds that both print a name do not print the same name. Join feeds by id wherever one exists.

### 2026-11-02, 4 am MDT (week 8 review: claimed-chance floor, no lowered signal bar)
- See the week 8 post-mortem. `PICK_MIN_CLAIM = 0.55` and `SIGNAL_BAR = 0.06` in `config.py`; the pricer computes the
  segment-corrected claim before the pick decision and passes a line with a low claim with its own reason; the
  legend says so; smoke check. Evidence: the live record on both weeks (above). FTN charting tested and rejected;
  participation data unavailable for 2026.

### 2026-11-02, 3 am MDT (research round 7: rain and linebacker Overs)
- See "Research round 7". Rain flips sign between halves for LB; LB Overs at their season-average line hit 45% in
  rain and 46% dry; mechanism: more runs, fewer completions. Rejected; Overs stay ineligible for locks. Measured
  rainfall (Open-Meteo) was refused on the day and is the first thing to redo. No model change.

### 2026-11-02, 3 am MDT (research round 6: corner quality, opponent passing, stake size)
- See "Research round 6". Corner quality rejected (flips sign between halves); opponent passing quality consistent
  for LB and DL at the extremes but 0.06% on the whole model, below the bar, kept as a candidate; no lift from
  corner quality among our picks; stake order kept until 30 graded A picks. No model change.

### 2026-11-02, 3 am MDT (Track record rebuilt: pick filters, parlay history)
- Owner asked for readability on the Track record tab, a filter system (week, rating, Over/Under and the like)
  and a parlay history. The tab now opens with the records bar and a row of jump links (every pick, parlay
  history, locks, by grade, by side, luck/calibration/replays). "Every pick" has filters for week, grade, side,
  market, position, result, book, locks only and a player/team search, a sort (newest, grade, lock score, units,
  result, player, Over/Under), and a summary that follows the filters: record, hit rate, units at 1 per bet,
  return per bet, units at the suggested stake, beat-the-close (the grader's moved-line rule), and a breakdown by
  grade, side and position. The table shows 60 rows with "show all", has a position column, colours the side,
  and breaks ties by lock score. "Parlay history": record, hit rate against the model's average claim, units,
  return per unit staked, then every parlay newest first as a collapsible row (week, day, legs with ticks,
  odds, model chance, stake, result, running record and units) opening to the full parlay. Luck, calibration,
  market watch and the replays moved into collapsibles under one section. Checked on the live data at desktop and
  phone width (no errors, no sideways scroll; totals match the grader: 216-180, A 16-2, CB Unders 62-23,
  beat the close 57% of 191 moved). Site only.

### 2026-11-01, late evening MDT (grade-order review after week 8 Sunday)
- See "Standing watch: grade order". A 16-2, B 55-42, C 44-40; A no longer trails B; no weight change (18 graded
  A picks, rule needs 30).

### 2026-11-01, evening MDT (first real bet-slip links)
- A pull by hand at 6:40 pm returned links for every DraftKings outcome, in the form
  `https://sportsbook.draftkings.com/?outcomes=<outcome id>` with the id URL-encoded (`#` as `%23`); `over_sid`
  and `under_sid` hold the raw ids. Several outcomes join with `+` in one `outcomes=` value, which is the
  one-click parlay link. The combined link on cards, parlays and My board is built from this at the Monday
  check-in after FanDuel's format is seen too.

### 2026-11-01, evening MDT (Sunday pulls through 6 pm)
- Found while pricing a Sunday-night parlay for the owner: the Sunday slots ran hourly 7-11 am plus the
  pre-kickoff pull at noon, so the 4 pm and night games were priced on lines from 12:36 pm. Sunday is now hourly
  7 am-6 pm (`PULL_SLOTS`), about seven more pulls a week at 1-2 credits each. Pitfall: a slate with several
  kickoff waves needs pulls up to the last wave, not the first.

### 2026-11-01, evening MDT (bet-slip links: tail a pick or a parlay at the book)
- Owner asked for links that open DraftKings or FanDuel with the parlay ready to tail. The Odds API returns each
  book's own bet-slip link and selection id per outcome when asked (`includeLinks`, `includeSids`; no extra
  credits). The pull now asks for them and keeps them in the snapshots (`over_link`, `under_link`, `over_sid`,
  `under_sid`, `market_link`, `book_link`, `event_sid`); priced lines, the week's line file, parlay legs and My
  board carry the chosen side's link. On the site: "Bet at <book> ↗" on each card, "Tail it" with one link per
  leg on an open parlay, "Open at <book>" on a My board bet before kickoff. Links are the book's own, opened in a
  new tab; nothing is placed by the site.
- One link per leg, not one link for the whole parlay, until a real pull shows the two books' link formats
  (DraftKings puts outcome ids in a query string, FanDuel market and selection ids; both can carry several
  selections, but the exact form is checked against real links before anything is built on it). The first pull
  with links is Monday 9 am for the Monday game. Smoke check: synthetic lines carry links on both sides.

### 2026-11-01, afternoon MDT (My board: money counts from kickoff)
- Owner: a bet on a game that has not started can still be withdrawn, so it should not count. The bar's money
  now covers started games only ("in play or settled", "to win if every started bet hits", "on current pace");
  stakes on games yet to kick off sit in their own column, labelled as withdrawable. Site only.

### 2026-11-01, afternoon MDT (My board: the day on its current pace)
- Owner: "if every bet hits I'd make $80, but given I'm 4 of 6 what would that pay out?" The bar now carries "on
  current pace": settled results plus every bet in play finishing the way it is trending right now (on track
  pays, behind loses the stake); bets not yet started are left out and counted beside it. Checked by hand on a
  five-bet board (settled +$0.60, one live on track +$11.98, one live behind -$20: -$7.42 on pace, one not
  started). Site only.

### 2026-11-01, afternoon MDT (My board: grouped and sorted by grade)
- Owner asked for the board sorted by grade rather than by the order bets were added, and a little more
  readability. Bets sit in three groups (In play, Still to kick off, Settled), each sorted A to C and then by
  lock score and kickoff; the trend line leads with the verdict (on track / behind / won / lost) and the clock
  and score follow. Site only.

### 2026-11-01, early afternoon MDT (My board: stakes and the day's money)
- Owner wants the board for record keeping during the day: each bet now takes a stake (kept with the bet in the
  browser), shows what it wins at the price taken and its dollar result once final, and the bar at the top adds
  up what is in for the day, what the day pays if every bet hits, and what has settled so far with what is still
  riding. Verified on a live game and the finished Thursday game (stakes 50/20/30: in for $100, settled -$9.40,
  $50 riding). Site only.

### 2026-11-01, early afternoon MDT (My board: add a bet after its game has started)
- Owner: Quay Walker was on the site in the morning and gone by the time he wanted to add his bet. The board shows
  only games that have not kicked off (the Jets-Raiders game started at noon), and the add button lived on the
  card. Now every line pulled this week is written at its last price, started games included
  (`write_week_lines`, `docs/data/lines_week.json`, at every pull and daily run), and the My board tab has a
  search box to add a bet from it, with the model's number beside each line. Smoke check. Pitfall: anything the
  owner can act on must not depend on a card that disappears at kickoff.

### 2026-11-01, midday MDT (My board: the bets you took, tracked live)
- Owner asked for a tab where he picks his bets for the day and watches them live. ESPN's public scoreboard and
  game-summary endpoints (`site.api.espn.com/.../scoreboard`, `.../summary?event=`) answer cross-origin requests
  (`access-control-allow-origin: *`) and carry per-player defensive totals and solo tackles that update during
  the game, so the page can do it with no server: a "+ My board" button on every card, the list kept in the
  viewer's browser (localStorage, per week; nothing leaves the browser), and a "My board" tab that polls ESPN
  every minute while any of its games is on (every two minutes in the half hour before kickoff, every ten
  otherwise): tackles so far, the full-game pace from the clock, on track / behind / won / lost, the score, and
  the settled record at the top. A player with no box-score row yet counts as zero. Team codes WSH, LAR, JAC
  translated; names matched the way the pipeline matches them. Verified in a headless browser on the real
  Cowboys-Cardinals box score from the first quarter. Caveat on the tab: the official box score the books settle
  on can differ by a tackle from the live feed.
- Site only; no model change. Revert condition: ESPN closing the cross-origin door, in which case the tab says
  "last update (failed)" and the board itself still works.

### 2026-11-01, morning MDT (book filter on the board)
- Owner asked to filter by DraftKings or theScore Bet. The Plays toolbar has a Book dropdown built from the books
  on the board at each render (so a book appears the moment it posts); choosing one shows that book's lines only
  and sets "Best price per line" aside, since a line is never hidden behind another book's price while you are
  looking at one book. Site only; no model change.

### 2026-10-31, afternoon MDT (luck check: every kind of pick against the whole board)
- See "Luck or skill" above. `luck_check` in `pipeline/grade.py` (consensus closing line per player and market
  from `O.closing_lines`, resolved against the box score, split by side, market and position; `group` now passed
  to the grader from `run.py`), `summary["luck"]`, Track record section, weekly log section, smoke check.
  Protocol: the weekly post-mortem starts from this table.

### 2026-10-31, early afternoon MDT (hourly pulls, every live line on the board)
- Owner: "you should be grading picks as soon as they come in, not waiting; I wanna see the lines that are live
  and know if it's worth getting in early." Two things were in the way. (1) Pulls ran at three fixed slots a
  weekend, so a line posted at 1 pm Saturday was not priced until 6 pm. The credit log says a pull costs 1-2
  credits with lines up and 0 without (416 -> 401 over the last two weeks of pulls), so the windows in which
  books post and move tackle lines are now hourly: Thursday 9-5:30, Friday noon-6 every two hours, Saturday
  9 am-9 pm, Sunday 7-11 am plus the pre-kickoff pull, Monday 9-5:30 every two hours (`PULL_SLOTS`, `_hourly`).
  About 40 pulls a week, roughly 60 credits, against the ~500 a month the key has. Slots are still served once;
  a tie between the fixed 10 am Sunday look and the pre-kickoff pull goes to the pre-kickoff pull (the sort on
  due slots now keys on time only; sorting tuples with dicts inside would have raised on a tie). (2) "Picks only"
  was the board's default, so with nothing clearing the bar the owner saw an empty board. Now, when no line is a
  pick, every live line is shown with the model's read, and each card carries both sides' expected return at the
  book's price ("Over -13% at -109 · Under not offered"). Every line was already priced at every pull; the
  grading of results waits on the box score, which nflverse posts the morning after, so that part cannot move.
- The five lines that were live at 10:34 am (Bally Bet, Cardinals at Dallas) were Over-only postings: no Under
  price at all. The model is against all five Overs (-13% to -54%); the sides it would like (Browning Under 6.5,
  Sweat Under 5.5, Wilson Under 9.5) were not offered. Nothing to get in early on. A pull was run by hand at
  noon to refresh the board.
- Smoke checks rewritten for the hourly table (several stale slots marked at once, the Sunday tie, Friday
  afternoon weekend pulls, next-pull walk, international windows behind the hourly slots). README table updated.
- Seen while checking the render: a browser with stale zone data shows Sunday's noon kickoffs as 11 am, since it
  still believes Alberta falls back on 2026-11-01. The site's clock is now a fixed UTC-6 (`Etc/GMT+6`), which is
  Edmonton all year from here on, so no viewer's device can shift a kickoff. The both-sides line on a card reads
  the pricer's chance back from the card's own return and price, so it includes the segment correction and
  agrees with the headline number.
- Revert condition: credits. If a month's pulls approach the key's quota, the Friday and Monday every-two-hours
  slots go first, then Saturday before noon.

### 2026-10-31, afternoon MDT (settled parlays off the board, next pull shown)
- Owner: "the homepage still shows the Thursday parlay". The Plays tab rendered every parlay of the week from
  `parlays.json`, so Thursday's (settled Friday, a loss on the Track record tab) sat on the board until the week
  rolled over. Now `write_parlays` flags a parlay `finished` once every leg's game is 4.5 h past kickoff, the
  board shows open parlays only (and also hides by clock, so a parlay drops off between pulls), and when no
  parlay is open the box says why: how many lines are on the board, the two-leg 53% rule, and the next pull. On
  Saturday at 11:30 am the board held 5 Sunday lines (Bally Bet, all Cardinals): the books post most Sunday
  tackle lines Saturday evening and Sunday morning, which the 6 pm, 8 am and pre-kickoff pulls cover.
- `next_pull` (`run.py`) computes the next scheduled slot (fixed slots plus Sunday's pre-kickoff slot) and is
  published in the site meta by the daily run and every pull; the header shows "Next pull". Header stamps are
  rendered in Edmonton time whatever the browser's zone, like kickoffs already were.
- Smoke checks: open parlays carry `finished: false`, meta carries `next_pull`, and `next_pull` walks Saturday
  6 pm -> Sunday 8 am -> an hour before Sunday's first kickoff.

### 2026-10-31, midday MDT (research round 5: pressure profile, ESPN injuries, outside consensus; Plays tab rebuilt)
- See "Research round 5" above. `press` from `load_pfr_def` (and `fake_pfr_def`), `press_prev` through
  `attach_extras`, `add_history_features`, `upcoming_rows`; `press_pg` on each lineman's projection for the card's
  profile tag (the model factor built on it was rejected by the backtest: miss 1.6217 -> 1.6260, DL bias -0.03 ->
  -0.12; removed before the push). `parse_espn_injuries`, `load_espn_injuries`, `merge_injury_sources` in `pipeline/sources.py`,
  merged in `load_all` (morning) and `refresh_injury_status` (every pull); `espn_injury_rows` in the site meta.
  `parse_fantasypros`, `load_fantasypros`; `attach_consensus` in `run.py` (snapshot under `data/consensus/`,
  `fp_comb`/`fp_solo`/`fp_ast` on projections, logged with each pick). Smoke checks for all three.
- Site, at the owner's request: the Plays tab has a toolbar (position, side, market, slate, sort by lock score /
  return / kickoff / player / line, picks only, best price per line) so the board can be read by position (the CB
  Unders); the legend is collapsed by default; the locks box sits first with each lock carrying a "Why this is a
  lock" dropdown (the score piece by piece, the checklist, the record of picks of its kind, his game log, the
  outside consensus); every other pick has the same box as "Why this pick"; cards carry tags (new role, reduced
  role, questionable, promoted, run-stuffer, far from line) with hover explanations; the Projections tab shows
  the outside consensus. Fixed while checking it on a phone: the helper that builds elements wrote the string
  "undefined" into attributes (every dropdown opened by default), and the why-box tables overflowed the card.
- Also fixed: an empty player id on an outside-feed listing could match a team whose starting QB or RB is unknown
  and flag "Opp QB out" on every defender facing it; empty ids are now dropped from that set.
- Validation: smoke test; real-data daily run in a scratch copy (backtest on 28,861 games, 204 ESPN listings
  merged: 6 injured-reserve and 1 suspended regular now carry a status the league report did not have, 10 more
  questionable listings than the league report; 30 consensus rows matched); the live site after the pushed daily
  job (run by hand at 11:23 am MDT: Test green, 204 ESPN listings merged, 30 consensus rows, the new fields on
  the site, `data/consensus/fantasypros_2026_w08.csv` committed). The Saturday 6 pm and Sunday pulls run on this
  code.
- Revert conditions: the ESPN merge if it ever marks a player out who then plays (then
  the feed's "date" is checked against the league report's week before it may override); the consensus column if
  it is found to have steered a pick (it must never enter a price, a grade or a lock score).

### 2026-10-31, late morning MDT (Sunday 8 am pull)
- The Saturday 9 am pull (fired by hand after the cron stall) found tackle lines for one of twelve Sunday games:
  the books post Sunday tackle props late Saturday or Sunday morning. Had that held through the 6 pm pull, the
  11 am pre-kickoff pull would have been the only full look, with no time for a second. Added a Sunday 8 am pull
  (`PULL_SLOTS[6]`, the whole Sunday slate, about 26 credits when the board is full; empty games cost nothing).
  Reversible in one line if the owner prefers the two-pull Sunday.

### 2026-10-31, morning MDT (second pull schedule)
- The half-hourly pull cron stalled for two hours on Saturday morning; the 9 am pull was triggered by hand and a
  second cron on the quarter hours added to `odds.yml`. Serve-once keys prevent double pulls.

### 2026-10-31, night MDT (final pre-Sunday sweep: concentration limits, tighter segment correction)
- Rehearsed Sunday's pull on a synthetic board built from the real week 8 projections and the real segment file:
  no exceptions, no undefined scores, the checklist and the segment corrections work, 10 players blocked for
  missing snap counts. The rehearsal showed one unforced error in waiting: every top lock was a corner's solo
  Under, because 15 graded picks (13-2) had moved that kind's claim by the full 10-point cap. If the solo market
  corrects on Sunday, five locks of one kind fall together.
- `SEGMENT_CAL` tightened: k 30 -> 40, cap 0.15 -> 0.08 (a 15-pick segment now moves a claim at most 8 points).
- `LOCKS_PER_SEGMENT` 2 and `PARLAY_LEGS_PER_SEGMENT` 2: no more than two locks a day, or two parlay legs, of the
  same kind of pick (side x market x position). Market-free diversification across the kinds the model likes.
- Parlay legs now use the segment-corrected claim (they were using the uncorrected one).
- Checked and sound: 709 projections for exactly the 28 teams playing, none undefined or absurd; 3 Out and 4
  Questionable defenders attached; the two mid-season movers (Simmons, Laulu) on their new teams; Saturday's two
  slots unserved and due; the last six pull runs green; 402 credits against about 85 needed; Sunday kickoffs at
  noon Alberta Time, so the Sunday pull serves at 11:00.

### 2026-10-31, late evening MDT (before Sunday: outlier damping, segment correction steers picks)
- **Outlier damping** (`OUTLIER_DAMP`): in a settled role, after a game 3+ above his base the player ran 5.5% under
  the model in both halves of the data (n 706 / 461), and 4-9% under after a game 3+ below (373 / 236). Half a game
  of shrinkage for linebackers lets one game pull the season average. Factors x0.975 after a big game, x0.96 after
  a low game, settled roles only; subset bias -0.25 -> -0.13 and -0.15 -> +0.10 tackles, overall error unchanged.
  Backtest row "Full model without outlier damping". Also reinforces the Under fade in the math itself.
- **Segment correction steers the pick decision** (`SEGMENT_CAL["ev_weight"]` 0.5): half of each side's correction
  (how our claims for picks of that kind have resolved) moves the probability that decides whether a line clears the
  pick bar; the full correction reaches the claim and the score. So solo Unders on defensive backs clear the bar
  more often and combined Unders on linebackers less often, until the record says otherwise.
- Solo drift window 1-4 weeks tested: no difference; stays 3.
- **Replay tool bug**: it dropped the lock-eligibility columns when logging picks, so replayed locks ignored the
  checklist (an Over and a new-role player could be replayed locks). Fixed and re-run: week 7 locks 5-2 (+2.7u),
  all plays 83-87 of 173 (-1.7u), parlays 1-1; Thursday week 8 locks 2-1 (McKinney W, Moehrig L, Nixon W; +1.3u),
  all plays 10-5 (+6.4u), parlay win. Daily backtest with damping: full model 1.6195 level-matched against 1.6197
  without; 2026 fold 1.6019, with the corrector 1.5778.
- Revert conditions: the damping row beating the full model for a season; the segment-steered picks' hit rate
  below the unsteered picks' over 100 picks (both are logged: `segment_adj` on each pick).

### 2026-10-31, midday MDT (segment calibration, stronger solo prior, solo level by position, market watch)
- See "Is the solo Under our play?" above. `SEGMENT_CAL`, `SOLO_SHARE_PSEUDO`; `segment_calibration`, `market_watch`,
  `SEGMENTS` in `pipeline/grade.py`; `segment_adjust`, `claimed_prob(adj)`, `price_lines(segments=)` in
  `pipeline/model.py`; per-position `G|solo_scale` from the backtest; `load_segments` in `run.py`; picks log `group`,
  `p_claim`, `segment`, `segment_adj`; two new Track record sections; legend line; smoke checks. Revert conditions:
  the segment correction making the by-grade order worse over 100 picks (then k rises), the solo rows in the
  backtest getting worse than the 8-pseudo version.

### 2026-10-31, morning MDT (Track record and Model check tabs reorganised)
- Track record: sections with a one-line lead each (all plays, by grade, by side, locks, parlays, replays, every
  pick); the duplicated stat rows above tables are gone; long explanations sit in collapsibles; each replayed week
  is a collapsible with its summary in the heading. Model check: a summary strip (full model, season average,
  held-out 2026 with and without the second model, solo), then "Does each piece earn its place?" (miss without
  each piece against the full model, with a verdict), the held-out rows, simple benchmarks, solo rows, weak spots,
  a compact dispersion grid by position, calibration with readable bins, and outlier regression.

### 2026-10-31, morning MDT (record by side on the site)
- Owner asked to track wins on Overs and Unders. The grader's summary carries `by_side` and `by_side_market`
  (Over/Under x combined/solo: bets, record, hit, units, return, pending); the records bar on both tabs shows the
  Over and Under records; the Track record tab has a "Record by side" block with the side-by-market table, where
  the Over rule (plays only, never locks, until forty more Overs say otherwise) gets judged.

### 2026-10-31, morning MDT (league solo drift)
- `SOLO_DRIFT`, `solo_drift_table` / `solo_drift_for` in `pipeline/model.py`, applied to the solo share; backtest row
  "Solo tackles: full model without league solo drift"; smoke check. See "Why the Overs miss" above. Revert: the
  without-drift solo row beating the with-drift row for a season.

### 2026-10-30, evening MDT (risk pass: Overs ineligible for locks, snap-count blind spot)
- See the risk pass above. `LOCK_RULES["overs_eligible"]` false; "snap counts missing for his last game" and
  "Over side" join the lock checklist; legend and smoke test updated.

### 2026-10-30, evening MDT (before Sunday: void bets, off-the-board picks, Alberta Time)
- **Void bets.** A pick on a player who did not play stayed "Pending" forever and could sit among the locks. Grading
  now uses the snap-filled history (a player who played and made no tackle has a zero row) and marks a pick "Void"
  when his game is in the books and he has no row: no units, outside every record. **Off the board:** at a pull, a
  logged open pick whose player has vanished from a board that still lists his game (ruled out, inactive, line
  pulled) is marked "off the board", loses lock eligibility and drops out of the locks and parlay.
- **Alberta Time.** Checked that the province stays on UTC-6 this Sunday (no fall-back) and that the code's zone
  data agrees; pinned UTC-6 as a guard. The old pitfall ("add one hour to each cron") was wrong and is corrected.
- Checked before Sunday: week 8 injury listings present for all 27 teams with a game (7 out, 5 questionable as of
  Friday), depth charts dated 2026-10-30, games.json carries the 14 games with the right Edmonton kickoffs, snap
  counts and stats through week 8, 402 credits left (about 100 needed this week).

### 2026-10-30, afternoon MDT (Sunday pull an hour before the first kickoff)
- Owner's call after the audit: a Sunday pull one hour before the day's first kickoff (Edmonton time), the whole
  Sunday slate, so the early-slate locks and parlay are re-chosen with the inactives known and the afternoon and
  prime-time lines refreshed. The slot time comes from the schedule each week (`SUNDAY_PRE_KICK_MIN` in `run.py`;
  a London game at 7:30 am makes it 6:30 am), served once like every slot. About 28 credits a week more.

### 2026-10-30, afternoon MDT (audit: injury refresh at pull time, solo dispersion and level, vacancy return, far-from-line flag)
- See the audit above. Pricing: `PICK_BAR_OVER`, `LOCK_EV_FULL` 0.15 -> 0.10, `LOCK_EV_FADE`, `CLAIM_SHRINK`
  (`claimed_prob` in `pipeline/model.py`, used by `lock_score`, the `p_claim` field and `choose_parlay`), parlay
  thresholds 0.56 / 0.53 claimed; legend rewritten. `run.py`: `refresh_injury_status` before pricing in the odds job. `pipeline/backtest.py`:
  solo dispersion keys (`G|solo`, `G:low|solo`), `__scale_solo__`, two solo rows. `pipeline/model.py`: `phi_solo`
  on projections, used for solo lines; `far_from_line` on priced lines; a listed starter cancels a vacancy.
  Site: "Model far from line" tag. Smoke test checks the solo rows, the solo level and the flag.

### 2026-10-30, midday MDT (research round 4: per-snap projection base and 12 more changes)
- See research round 4 above. Config: `PERSNAP`, `SHARE_MODEL`, `VACANCY`, `DOME_CB`, `PHI_SHARE_SPLIT`, `MATCHUP`
  (feature only); `NEW_ROLE["power"]` 0. `pipeline/sources.py`: schedule carries `away_score` and `roof`.
  `pipeline/model.py`: `team_games` margin and roof; history features `c_real_prev`, `s_real_prev`, `ps_rate`,
  `last_margin`, `tsnaps_exp` (`attach_team_snaps`), `allowed_rel` (`attach_matchup`); `share_pred`, `persnap_rate`,
  `persnap_base`, `vacancy_rule`, `dome_factor`; `project_frame` restructured (per-game core x snap x role x share
  corrections, blended with the per-snap base, vacancy rule, then the game-context factors); persistent `vacancy`
  in `role_signals_backtest` and in `upcoming_rows` (report, depth-chart move, missed game); `finalize_projections`
  writes `share_pred`, `rate_clean`, `vacancy_rule` and uses `:low` dispersion keys; pricer rescales the game log to
  the expected share; corrector features. `pipeline/backtest.py`: rows "without per-snap base", "without vacancy
  rule", "without dome corners"; dispersion per position and per low expected share; vacancy weak-spot row.
  `run.py`: freshness status; projections carry the new fields. Smoke test checks the rows, the share, the
  dispersion split and freshness. Revert conditions: the "without per-snap base" row beating the full model two
  weeks running (level-calibrated); the vacancy weak-spot row drifting past +/-15% for a season; dome corners'
  row beating the full model for a season.

### 2026-10-30, morning MDT (post-mortem week 8 Thursday: new-role rule)
- See the week 8 Thursday post-mortem below. `NEW_ROLE` config; `snap_jump`, `new_role_flag`, `new_role_factor`
  in `pipeline/model.py`; the flag and jump written to projections and priced lines; fade signal off and
  consistency in-role only for flagged players; `mark_locks` and `choose_parlay` skip them; `log_pct` game log
  from `attach_game_logs`; backtest row "Full model without new-role factor" plus a `new_role` subset block;
  "New role" tag and a legend line on the site; smoke test checks the flag, the lock exclusion and the backtest
  row. Revert condition: the new-role subset's actual-vs-model drifting past +10% or below -10% over a season, or
  the flagged players' live record (tagged picks) beating the locks' record over 50+ picks, which would mean the
  exclusion costs more than it saves.
- **Audit, same morning: the lock-eligibility checklist.** `ROLE_SHIFT` factors (reduced role, absence, missed
  game, new team) and `LOCK_RULES`; `role_shift_flags`, `role_shift_factor`, `gap_weeks`, `team_changed` in
  `pipeline/model.py` (history and upcoming rows; team change read from the latest dated depth chart, player
  re-teamed); the pricer writes `lock_block`, `lock_eligible`, `in_role_games` and every flag; `lock_blocked` in
  `pipeline/grade.py` is the one gate for locks and parlays; Over-fade signal removed; backtest row "Full model
  without role-shift factors" and a `weak_spots` table (also on the Model check tab); tags and legend on the site;
  smoke test checks the checklist, the gate and that no Over is sold as fading an outlier. Revert condition for each
  factor: its weak-spot row drifting past +/-10% for a season; for the checklist, as above.

### 2026-10-29, morning MDT (record by grade on the site)
- Owner asked for an area showing the record for A, B and C grade picks. The records bar on both the Plays and
  Track record tabs now carries the A, B and C records (with hit rate and pending) beside locks, all plays and
  parlays. Track record has a "Record by grade" block right under "All plays": record, hit rate, units at 1 per
  bet, return per bet, units at the suggested stake (A 1u, B 0.5u, C 0.25u) and pending, with "No grade yet" for
  the week 7 picks logged before grades existed. The replayed weeks now carry a by-grade record too
  (`record_by_grade` in `pipeline/grade.py`, shared by the grader and `tools/replay_five.py`), shown in the
  replay section and in the records bar's replay line, since the live graded sample is still tiny.
- The by-grade summary gained `pushes`, `pending`, `hit`, `stake` and `staked`; the smoke test checks them.
- **Replay leak fixed.** `tools/replay_five.py` built its calibration and corrector from every finished game,
  including the week being replayed, so the week 7 replay was priced by a corrector that had seen week 7's box
  scores. It now uses only games before the replayed week. The round 3 replay numbers above are restated from the
  honest run.

### 2026-10-28, morning MDT (schedules kept alive without hands on)
- GitHub switches off every scheduled workflow in a public repository after 60 days without a push (the repo is
  public because GitHub Pages on a free account needs it). The daily job already pushed a results commit each day
  in season, but a failed run (or an off-season with nothing new) pushed nothing. Now: the daily save step runs
  even when the update failed, keeps yesterday's data and site, and commits a run log (`data/cache/last_run.txt`)
  every day; the daily job re-enables `odds.yml` and a pull that found lines re-enables `daily.yml` (both have
  `actions: write`); new `keepalive.yml` runs on any push by a person and re-enables both. Revert condition: none;
  if GitHub changes the rule the extra commit a day is harmless.

### 2026-10-27, late afternoon MDT (research round 3: injury report factor, second model)
- See research round 3 above. **Injury factor** (`INJURY`, `injury_factor`, `attach_injury_status`): questionable
  x0.92, limited practice x0.97; injuries now loaded for every history season with practice status. Questionable
  players are priced and can be picks (`uncertain` flag in `price_lines`, logged in `data/picks.csv`, "Questionable"
  tag on cards) but `mark_locks` and `choose_parlay` skip them. Backtest ablation row "Full model without injury
  report". Revert condition: the ablation row beats the full model two weeks running.
- **Second model** (`GBM`, `gbm_features`, `fit_gbm`, `blend_gbm` in `pipeline/model.py`): a gradient-boosted
  Poisson corrector trained each morning on all finished games, 60% of the final projection. `run_backtest` now
  returns it as a fifth value and reports it walk-forward in two extra table rows; `finalize_projections` takes
  `gbm=` and writes `proj_factor` / `proj_gbm` to `projections.json`. New dependency `scikit-learn>=1.5`. Smoke
  test checks the walk-forward row and the corrector's numbers. Daily job about 80 s. Revert condition: the
  "boosted corrector blend" fold row worse than the "Full model" fold row on the daily backtest two weeks running,
  or the live plays record by grade turning worse than before the change over 200+ picks.
- `tools/replay_five.py` now runs the backtest for phi, scale and the corrector instead of reading the cached
  model state, so replays use the same model the daily job would have had.
- README: model description, grade description (market agreement was still mentioned there), `GBM` knob.

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

### 2026-10-27, afternoon MDT (closing-line value: definition, cutoffs, legend)
- "Beat the close" is now the standard definition: among picks whose closing number differed from ours at all,
  the share where the line moved our way or the line held and the no-vig price moved our way. Unmoved lines are
  excluded (half-point tackle lines rarely move between pulls, and counting them as misses pinned the figure near
  zero). The same-line price comparison now uses the no-vig chance at bet time, not our price with the vig in it.
- Cutoffs (`CLV_BARS`): below 52% no visible edge, 52-56% decent, 56-60% good, 60%+ great. The legend on the Plays
  tab explains the concept, the measurement and the cutoffs; the Track record figure is coloured by them and
  shows how many moved lines it rests on.

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

- nflverse participation data (on-field defenders per play, man/zone, box count) for research on corner and
  linebacker usage, if it is published for 2026 again.

- Rain by measured precipitation (Open-Meteo ERA5 archive, mm per game hour at each stadium) to test real downpours
  separately from drizzle; and high wind (18 mph+) for linemen, which ran over the model in both halves on 11 games.

- Opponent passing quality (EPA per dropback vs that season's league, two buckets at ±0.1) for LB and DL: consistent
  in both halves at the extremes, 0.06% on the whole model in research round 6. Re-test on a full 2026 season.

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
- Single-game slates can come up short of three locks now that the corrector sits closer to the line (week 7
  Monday replay: one lock, Kenny Clark at exactly the 55 floor, nothing else above 50). Options, none adopted without evidence: a lower
  floor on single-game slates, or filling the three with the best scores and marking any below 55 as "lean".
  Decide after the Thursday and Monday slates of weeks 8-9 have been graded.
- Corrector weight 0.7: marginally better in sample (-1.11% vs -1.08%); revisit after 2026 ends with a full
  extra season of walk-forward evidence.
- A corrector for solo tackles: the current one moves the solo projection in proportion to the combined one.
  Justified if the solo-line record by grade lags the combined-line record.
- Stop pricing a questionable player at all when his practice status is "did not participate" on Friday: needs
  the daily report timing, which nflverse does not carry.

## Known pitfalls

- Codespaces secrets are invisible to Actions. Only Actions secrets work.
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
- `picks.csv` gains columns over time (`uncertain` added 2026-10-27); older rows read back as empty, so every use
  of a newer column must `fillna` a neutral value.
