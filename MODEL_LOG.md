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

## Research round 8: could the same data price other markets? (2026-11-03, morning MDT, scoping at the owner's request)

Question: which other player props, priced from the same nflverse data the tackle model uses, could produce picks
like the A tier? Method, so every stat is judged the same way: four seasons (2023-2026, regular season, 65,476
player-games), one generic walk-forward projection per stat (per-snap rate shrunk to the population, times the
snaps expected from the last three games' share and the team's snaps, times the opponent's allowed rate
shrunk over 6 games), against a book-style season average shrunk toward the population. Population per stat:
players a book would post (season-to-date mean above a floor, three or more prior games). Two readings per stat:
the projection's gain in miss over the season average, and, where the projection disagrees with the
season-average line by 10 or more probability points (an A-size edge), how often its side hit, against its hit
rate on every game. The market list is The Odds API's (player props per event; alternate-line markets exist
for every one of these). No credits spent; no lines for any new market have been pulled, so market efficiency is
untested for all of them.

| Stat | Games | Mean | Gain over season average | Dispersion | Games with a 10-pt disagreement | Hit on those | Hit on all | Disagreement adds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Tackles + assists (reference) | 11,391 | 4.7 | -0.3% | 1.42 | 40% | 63.0% | 56.4% | +6.6 |
| Solo tackles | 9,987 | 2.9 | -0.1% | 1.25 | 39% | 64.6% | 58.2% | +6.4 |
| Assists | 15,348 | 1.8 | +0.3% | 1.32 | 47% | 65.2% | 59.9% | +5.3 |
| Sacks | 4,305 | 0.4 | +1.3% | 1.04 | 59% | 74.6% | 68.1% | +6.5 |
| QB hits | 3,956 | 1.0 | +0.3% | 1.13 | 60% | 71.2% | 65.0% | +6.2 |
| Tackles for loss | 6,133 | 0.5 | +0.5% | 1.09 | 40% | 66.8% | 58.9% | +7.9 |
| Passes defended | 4,476 | 0.5 | +0.7% | 1.17 | 32% | 65.8% | 57.1% | +8.7 |
| Interceptions | 2,708 | 0.1 | +2.0% | 1.14 | 98% | 90.1% | 89.8% | +0.3 |
| Receptions | 4,943 | 3.9 | +0.2% | 1.35 | 43% | 64.3% | 59.4% | +4.9 |
| Targets | 5,097 | 5.8 | +1.1% | 1.50 | 44% | 62.7% | 57.6% | +5.1 |
| Receiving yards | 4,070 | 49.6 | -0.4% | | 26% | 54.8% | 53.5% | +1.3 |
| Carries | 1,933 | 12.7 | -2.0% | 2.62 | 57% | 57.7% | 55.4% | +2.3 |
| Rushing yards | 1,978 | 54.5 | -1.9% | | 47% | 56.0% | 53.2% | +2.8 |
| Completions | 1,333 | 20.1 | -0.7% | 2.25 | 35% | 56.2% | 55.4% | +0.8 |
| Pass attempts | 1,339 | 30.8 | -2.0% | 3.08 | 34% | 55.9% | 52.7% | +3.2 |
| Passing yards | 1,279 | 224 | -1.1% | | 32% | 55.1% | 52.5% | +2.6 |
| Passing TDs | 1,162 | 1.5 | -0.1% | 0.96 | 43% | 58.6% | 55.9% | +2.7 |
| Field goals made | 1,381 | 1.7 | -0.6% | 0.97 | 37% | 61.4% | 54.9% | +6.5 |
| Kicking points | 1,396 | 7.2 | -0.5% | 2.01 | 31% | 57.2% | 55.6% | +1.6 |

Reading the table. The generic projection beats the season average by nothing anywhere, tackles included (the
real tackle model's gain comes from the pieces this scan leaves out: role flags, crews, the line blend). The
column that separates the stats is the last one: how much the model's disagreement with the season-average
line is worth. The defensive count stats and the receiving counts behave like tackles (+5 to +9 points);
volume and yardage stats for quarterbacks and backs do not (+1 to +3; dispersion 2 to 3 times the mean, which
is game script, and no data set forecasts game script beyond the spread, as the plays-faced test showed). The
"hit on those" figures for sacks, QB hits and interceptions are inflated by the base rate: a 0.37-a-game player
against a 0.5 line is an Under most of the time whatever the model says, and the book prices that in (Under
-200), so those rows say the stat is predictable, not that the market is beatable.

Where the tackle edge really came from matters more than this table: the A tier won because the books posted
solo lines 0.4 too high, a market-level mispricing in a thin, formula-set market, plus selection on top. The
candidates are therefore ranked by how much they look like that, not by the table alone.

1. **Alternate tackle lines** (`player_tackles_assists_alternate`, `player_solo_tackles_alternate`). Same
   players, same model, same data, more lines: the book's ladder of alternate numbers is derived from its own
   distribution assumption, and ours (position dispersion, the crew, the role flags) differs from it. Where the
   solo line is 0.4 too high, the alternate Under one point lower at plus money is the same edge at a longer
   price. No new model; a market pull and a pricing pass over the ladder. First to test.
2. **Assists** (`player_assists`). Combined minus solo, which the model already projects; the thinnest of the
   defensive markets and the one the home scorekeeper decides most: assists per team-game run from 23 to 30 by
   stadium (coefficient of variation 0.057, against 0.021 for combined and 0.025 for solo), though a stadium's
   assist share correlates only 0.2 between 2023-24 and 2025-26, so it must be read from recent games, which is
   what the crew model does. If the books derive assist lines by formula, the crew is the edge they miss. Second
   to test.
3. **Sacks** (`player_sacks`). The one market where a data set we already load and do not use for pricing
   (PFR pressures; sacks per QB hit 0.43) carries the signal: expected pass plays faced (the opponent's pass
   rate and the pace the model already has) times pressure rate. Low counts (0.37 a game) mean most lines are
   0.5 with the price doing the work, so the edge is in the price, not the side, and it is capped. Third.
4. **Receptions** (`player_receptions`). Structurally the closest offensive analogue (target share times team
   attempts times catch rate; +4.9 points on disagreement; the data is richer than for tackles). The market is
   not: receptions is among the most bet player props and lines move, so the formula-mispricing that made the
   solo edge is unlikely to be there. Worth a closing-line pull to measure, not worth a model before that.
5. **Not worth pursuing from this data:** yards of any kind, pass attempts and completions, carries (game
   script, dispersion 2 to 3), interceptions (a coin toss at 0.11 a game), kicking (field goals look predictable
   in the table, but it is the team's drives, not the kicker, and the book prices the team), touchdowns
   (binary, heavily bet, efficient).

**Recommended next step, before any model work:** pull the closing lines for markets 1 to 4 (and the alternate
ladders) at DraftKings and theScore Bet for two or three weeks, one per-event request with the extra markets
added to the tackle pull (cost: each market is charged per request; check `odds_credits_remaining` first), and
run the blind-board test on each (every Under, every Over, at the close, mean line minus mean actual). The
solo-tackle mispricing showed at p = 0.004 in one week; a market with a bias of that size declares itself in
two. Build only where a bias shows or where the model disagrees with the book and wins. Nothing in the pipeline
changes for this round. Revert condition: none (no change).

## Research round 9: the math the model was missing (2026-11-03, evening MDT, at the owner's request)

Nine candidates, worked in the order given, each tested walk-forward before anything was adopted. Harness:
four seasons of history (30,919 backtest games with the playoffs), and weeks 7 and 8 of 2026 projected as of
the time (calibration from earlier games only) against 512 consensus closing lines with box scores.

### Adopted

**1. The pricing blend per market, estimated from closing-line errors** (`pipeline/blend.py`, `config.BLEND`).
Before: 40% model, 60% line, one weight for every market, from a least-squares fit on week 7. That fit is
unstable (the line's coefficient was 0.69 on week 7 and 0.08 on week 8); the inverse-variance weight is not
(0.50 and 0.48 on combined, 0.50 and 0.48 on solo), so the line's weight is now mse_model / (mse_model +
mse_line), shrunk toward 0.5 by n / (n + 100). The bigger finding is the levels: the solo line ran 0.48 and 0.32
high in the two weeks and the model's own solo number 0.38 and 0.25 high; the combined line 0.12 and 0.10 low,
the model 0.17 and 0.16 low. Both sides get a level correction (mean error, shrunk the same way). Walk-forward:
fit on week 7, test on week 8: solo error 3.418 to 3.309 (-3.2%), combined 6.634 to 6.550 (-1.3%); fit on
8, test on 7: solo 3.488 to 3.373 (-3.3%), combined 6.762 to 6.757. The model's number for every line is now
logged at each pull (`data/lines_log.csv`, latest per player-market-week; weeks 7 and 8 seeded from the
walk-forward projections), and the daily job re-estimates the blend after grading. `LINE_WEIGHT` is 0.5 (the
no-data default). Expect the solo Under claims to rise toward their hit rate (claimed 58.8%, hit 63.7%).

Validation of the blend on the real data (daily in a scratch copy): estimated from weeks 7 and 8, 255 combined
and 257 solo lines: line weight 0.49 on both; combined line +0.12 and model +0.16; solo line -0.27 and model
-0.21. The lines log and the estimate are live from the next daily run; the first picks priced with it are week 9's.

**2. Parlay chance with a shared plays draw** (`model.parlay_corr_ratio`, `config.PARLAY_CORR`). Two legs on
one defence are not independent: both face the same number of plays. A simulation that draws the game's plays
once (sd 7.6 around expectation) and each leg's count around its mean scaled by that draw, with the within-game
dispersion (the leg's dispersion less the plays' share of it), gives the joint chance against the product. On
every pair of the four most-tackled lined players per defence in weeks 7-8 (270 pairs): two Unders 1.053 times
the product (range 1.02-1.08), an Under with an Over 0.936 (0.86-0.97); the recommended three-Under parlay of
November 1 was 0.155 joint against 0.140 as a product. Small, systematic, and in the direction the books price
their same-game parlays, so the parlay's claimed chance is now the product times that ratio (clipped 0.8-1.3;
legs in different games stay independent), and the ratio is written on the parlay. Tackle sharing between the
two (one man's tackle is not the other's) pulls the other way and is not modelled; it is second order at these
counts.

### Measured and not adopted

**5. A plays-faced mixture for the distribution shape.** Plays faced vary with an sd of 7.6 around expectation,
shared by everyone on the defence, so the count distribution should be a mixture over plays. Tested on 12,000
backtest games by randomised PIT and at 504 posted lines: the single negative binomial is already calibrated
(5.1% of actuals below its 5th percentile, 4.8% above its 95th; deciles 0.092 to 0.110), and the mixture
changes nothing that matters (tails 4.9%/4.8%, Brier 0.2413 in both at the posted lines, log-loss 0.6754 in
both). The empirical dispersion already absorbs the plays variance; the shape difference is invisible at these
counts. Rejected as a pricing change; the decomposition is kept for the parlay test below. Side finding worth
keeping: at the posted lines the model's probability scores Brier 0.2413 against 0.2539 for the market's own
no-vig price (log-loss 0.675 against 0.730).

**3. The team tackle budget.** Scaling a defence's projections so they sum to the plays it should face times the
league's tackles per play (1.28) looked like a clear win on raw miss (1.6216 to 1.6089, better in every season,
and the factor correlates 0.44 with the team's actual-to-projected ratio). It is not: on level-matched miss, the
measure the protocol says pieces are judged on, the gain is 0.0007 (1.6185 to 1.6178) with the population
the backtest sees, and it turns negative (1.6194) once the players counted are the ones expected to play, which
is the only definition that works live. The raw gain was the factor lowering the level by 4%, which the
backtest's own level calibration already does. Live the factor pinned at the 0.9 floor for every team, because
the projection frame carries more bench players than a game's box score. Built, measured, removed the same
evening; the research script is `research/team_budget.py`. Pitfall added: judge a piece on level-matched miss
first; a raw-miss gain with a bias change is a level change, not information.

**4. One fitted calibration map instead of the three devices.** A logistic map from the model's chance to the
hit rate (one for all picks, and one per market), fitted on one week and scored on the other by Brier: fit on
week 7, scored on week 8 (150 picks): raw model chance 0.2379, shrink alone 0.2405, the layered claim as logged
(shrink plus segment correction) 0.2299, the logistic map 0.2433 (per market 0.2391), the market's own price
0.2460. Fit on week 8, scored on week 7 (227): shrink alone 0.2500, logistic 0.2610 (per market 0.2578), market
0.2477. The map's slope swung from 0.51 to 1.14 between fits: on 150-230 picks it learns the week, not the
model. The layered claim is the best calibrated of the lot on the one week it can be scored, so it stays.
Revisit at 600 picks.

**6. Snap-share variance in the dispersion.** The expected share misses the actual share by an sd of 0.19 in
every bucket of expected share, so the hypothesis that a rotation player's count is wider because his share is
less certain predicts the extra dispersion should grow with mu times the squared coefficient of variation.
Fitted on 2023-2025 per position, the slope on that term is 0.01, -0.04, 0.06 and -0.01: nothing. Tail
coverage on 2026 (9,000 games): the current two-bin dispersion 5.4%/5.4% below the 5th and above the 95th
percentile, four share buckets 5.0%/5.4%, the continuous form 4.9%/5.4%; by bucket the differences are a
point either way. Rejected; the two-bin split stays.

### Adopted (continued)

**7. Probability scores in the backtest.** The bet is a chance at a line, so the backtest now scores the shape
as well as the mean: a randomised probability integral transform over 4,000 games (how often the actual falls
below the model's 5th percentile and above its 95th, and the decile histogram) and the Brier and log-loss of
the model's chance at the lines around each projection; the blend estimate adds, per market, the Brier and
log-loss at the posted closing lines for the market's no-vig price, the model's number alone and the blended
mean. Reported in `backtest.json` (`prob_scores`) and `blend.json` (`scores`), and in a "Does the chance at the
line hold up?" section on the Model check tab. Current reading: 5.1% and 4.8% in the tails on the full history;
at 504 posted lines of weeks 7-8 the blended chance scores Brier 0.2413 against the market's 0.2539.

**8. Stakes from the claimed edge, capped per game** (`model.kelly_stake`, `grade.cap_stakes`, `config.STAKE`).
Each pick's stake is a quarter of the Kelly fraction of a 100-unit bankroll from its claimed chance and price,
clipped to 0.25-3 units, and the picks on one game are scaled down together above 4 units. Judged on the 394
graded picks with every scheme scaled to the same total staked (136.5 units): the grade ladder +18.1 units
(+13.3%), flat +10.8 (+7.9%), quarter Kelly +15.9, quarter Kelly with the game cap +21.2 (+15.6%); by week,
+8.3% against +5.8% and +23.2% against +19.5%; the most on one game 5.4 units against 10.8. Kelly stakes hardly
differ by grade (A 0.24, B 0.32, C 0.28 on the 100-unit bankroll): the claimed edges are similar across grades,
because the grade also weighs consistency and sample; the grade says how sure, the stake says how wrong the
price is. The stake is logged with the pick and shown on the card; the record's "units at suggested stake"
follows it (older picks keep the grade ladder). Thin evidence (two weeks, claims partly in sample for week 7),
so revert if the Kelly stakes trail the grade ladder over the next 300 picks at the same total staked.

**9. The opponent's completions by receiver position.** Each defender's tackle rate per completion to a back, a tight end and a receiver from his
prior games (shrunk to his position's league rate over 40 completions), times the opponent's mix of completions
by receiver kind from its prior games (shrunk to the league over six games), against the same rates at the
league mix; the ratio applied to the pass share of his tackles. The rates differ by position as expected
(linebackers 0.093 per completion to a back and 0.035 to a receiver, corners 0.070 and 0.121), but once an
opponent's mix is shrunk the way it has to be to be known before the game, the factor has an sd of 0.009 and a
correlation of at most 0.04 with the residual; level-matched miss 1.6185 to 1.6185 in every season at every
power. The information is real at the position level and already in the model (the run/pass mix and each
player's own rates); the between-opponent part is too small to price. Rejected.

### Pitfalls found this round

- Judge a projection piece on level-matched miss (`mae_cal`) before raw miss (the team budget).
- A calibration map fitted on one week of picks learns the week: its slope moved from 0.51 to 1.14 between
  fits. At a few hundred picks, corrections with structure (shrink plus per-kind segment) beat free fits.
- The smoke test's temporary repository copies were never deleted; 140 of them sat in /tmp. It now removes its
  copy at exit (the old ones are left for the owner to clear).

## Weekly post-mortems

Each post-mortem starts from the luck table (Track record tab; `data/weekly_five.md`): per kind of pick, our hit
rate against the whole board's base rate and the beat-the-close share. Only where lift and the close agree with
the record is the week evidence about the model.

### Week 8 final, 2026, and the season to date (graded 2026-11-03; written 8 am MDT at the owner's question "are we beating the books or getting lucky")

Monday night (CHI and SEA; the one graded pick): Dillon Thieneman Under 4.5 solo at -155, B, 3 solo, win. Week 8
closes 96-71 (57.5%), +23.6 u at 1 u each; locks 7-2 for the week, 8-2 on the season; parlays 1-1.

**Season to date, every pick regraded against the official box scores (394 decided, weeks 7 and 8):**

| Slice | Record | Hit | Book's implied | Claimed | Units | Chance luck alone does this |
| --- | --- | --- | --- | --- | --- | --- |
| All | 217-177 | 55.1% | 51.1% | 57.5% | +31.0 | 6.5% |
| Grade A | 16-2 | 88.9% | 58.6% | 64.6% | +9.5 | 0.6% |
| Grade B | 56-42 | 57.1% | 50.1% | 58.1% | +13.2 | 10% |
| Grade C | 44-40 | 52.4% | 47.9% | 55.2% | +9.8 | 24% |
| Ungraded (week 7, before grades) | 101-93 | 52.1% | 52.4% | | -1.4 | 56% |
| Locks | 8-2 | 80% | 55.9% | 63.7% | +4.2 | 11% |
| Under solo | 128-73 | 63.7% | 51.6% | 58.8% | +47.8 | <0.1% |
| Under combined | 56-64 | 46.7% | 50.8% | 55.3% | -8.9 | 84% |
| Over combined | 24-23 | 51.1% | 50.8% | 59.0% | +0.2 | 54% |
| Over solo | 9-17 | 34.6% | 50.1% | 42.8% | -8.1 | 96% |

"Chance luck alone does this" is the one-sided binomial chance of at least that many wins at the book's own
average implied chance. Grade order holds (A > B > C), and A is the only tier that is clearly ahead of luck;
it is 18 picks.

**Where the edge actually is: the book's solo lines, not our selection.** The luck table said "the market went
our way" on Unders both weeks, so the whole board was tested blind: one line per player-market at the close,
every Under taken, no model.

| Blind "every solo Under at the close" | Record | Hit | Book's implied | Units | Per bet | Chance luck does this |
| --- | --- | --- | --- | --- | --- | --- |
| Week 7 | 82-41 | 66.7% | 54.5% | +28.6 | +23% | 0.4% |
| Week 8 | 85-49 | 63.4% | 53.5% | +25.5 | +19% | 1.3% |
| Solo CB, both weeks | 43-18 | 70.5% | 53.6% | +21.2 | +35% | 0.5% |
| Solo S | 52-29 | 64.2% | 53.7% | +16.5 | +20% | 3.7% |
| Solo DL | 15-6 | 71.4% | 53.5% | +7.9 | +38% | 7.5% |
| Solo LB | 57-37 | 60.6% | 54.5% | +8.5 | +9% | 14% |
| Every combined Under | 127-128 | 49.8% | 53.2% | -86.3 | -34% | |
| Every Over, any market | | | | -99.4 | | |

Solo lines ran 3.16 on average against 2.79 actual (CB 2.75 vs 2.15; DL 1.69 vs 1.24; LB 3.63 vs 3.23; S 3.31 vs
3.15), while combined lines were about right or slightly low (LB 7.07 vs 7.28; S 5.62 vs 6.07). The books have
been posting solo-tackle lines about four tenths of a tackle too high for two weeks running, at every position,
and a bettor with no model who took every solo Under did as well per bet as our solo Unders (ours: +24% per bet
on 201; blind: +21% on 257). Our lift over the board on Under solo is -2.5 and -0.7 points in the two weeks:
the model's choice of which solo Unders added nothing. The model is profitable because it leans on the one
mispriced market, and it leans there because its solo projection (combined times a shrunk solo share with the
league drift) sits below the book's solo lines. That is a real edge against the book, not luck, but it is the
market's edge, not the selection's, and it ends the week the books lower their solo lines.

Within the mispriced market the A grade does add selection: the 16-2 A picks are nearly all solo Unders at CB
and S whose board base rate was 58-69%, and they hit 89%. Lift of +20 to +30 points on 18 picks is the only
selection skill the record shows so far. B and C add nothing over the board.

**Closing-line value says nothing here, and why.** No-vig CLV in points is -2.6 on 396 closes: 352 picks closed
on the line taken and the book barely re-prices a held tackle line (price moved our way on 22%, against on 15%,
average +0.3 points, which is less than the 3.1-point vig paid at the time of the bet). The 44 lines that
moved split 21-23. The owner's reading was that locks and A picks "beat the line" because they won; the two
measures differ: CLV is what the market did before kickoff, the record is what the field did. In a market the
book does not move, CLV cannot see an edge that exists, and the blind test above is the right instrument.

**Under combined LB: 3-10 on the season**, eight of the ten losses within two tackles and the board itself 44-50
on combined LB Unders. The segment correction already sits at -6.1 points on 13 picks; it stays a watch, no
rule.

**Decisions.**
- No model change. The edge is a market-level mispricing of solo lines; the model already prices from the
  league solo drift and the segment corrections (+4.7 points on Under solo, -6.6 on Under combined) carry the
  rest. Fitting anything further to two weeks of one mispriced market would be fitting the bookmaker's mistake.
- New standing watch, **"Is the solo line still too high?"**: each post-mortem reports the blind every-solo-Under
  result at the close for the slate (record, per-bet return, mean line minus mean actual by position). The day
  it goes to zero the model's claimed solo edges are stale and the claim shrink or the solo level needs a look
  before any pick is trusted; the day it flips the solo Unders are a fade.
- The grade-order watch stands: judged at 30 A picks (18 now).
- The standing post-mortem task fired at 6:20 am before Monday's grading had landed (the daily run drifted to
  7:14 am) and pushed nothing; it now fires at 8:20 am Edmonton and carries the blind solo-Under benchmark.

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

### 2026-11-03, late afternoon MDT (six things that would have broken later, fixed now)
Owner asked what would cause trouble down the line and picked six of the ten named. Each in turn:
1. **Dependencies pinned.** `requirements.txt` now pins pandas 3.0.5, numpy 2.5.3, requests 2.34.2, pyarrow 26.0.0,
   polars 2.0.0, nflreadpy 0.1.5, scikit-learn 1.9.1, cryptography 50.0.1 (the versions the smoke test passes
   with). The runner used to install whatever was newest each run; pandas 3 already broke a groupby once. Bump on
   purpose, smoke test as the gate.
2. **The season no longer ends at week 18 for the code.** Every loader kept regular-season rows only, and after the
   last regular game the week counter would roll to 19 with no games behind it and the daily job would fail every
   morning through the playoffs. `sources._season_game()` now keeps REG and POST rows (schedules: WC, DIV, CON,
   SB; nflverse numbers playoff weeks 19-22), so the playoffs are projected, priced and graded like any week and
   playoff games join the history. After the Super Bowl `cmd_daily` sees no game left on the schedule, grades
   what is there, writes the site with `season_over` in the meta (the header says so) and projects nothing; the
   pull job's planner has no kickoffs and does nothing. Validation (real-data daily in a scratch copy): the backtest now covers 30,919 defender-games
   (1,528 playoff games added); full model miss 1.6216 against 1.6212 without them (level-matched 1.6185),
   season average 1.6855, held-out 2026 fold 1.6023: the playoff games neither help nor hurt the model, and
   every piece keeps its place. 768 week-9 projections, 99.7% with an ESPN id, all with a league id.
5. **Picks carry the league player id and grade on it.** Every priced row has `player_id` (gsis) and `espn_id`
   (from the players table); the pick log keeps `player_id`; the grader matches box scores by id first and by
   name only for older picks; `actuals.json` carries each row by id as well as by name. On the site, a bet on My
   board stores both ids, the live tracker matches ESPN's box score by athlete id before falling back to the
   name, and the official grade looks the id up first. A pick on a misspelled name now grades (smoke-tested).
6. **Segment calibration weighs recent weeks more.** A pick's weight halves every three weeks
   (`SEGMENT_CAL["half_life_weeks"] = 3`): the correction, its n/(n+k) weight and the hit and claimed rates use the
   weighted count (`n_eff`); the raw count still gates `min_n` and is what the site shows. Reason: the Under solo
   correction was earned entirely from the books' high solo lines; when the books re-price, the old record would
   outvote the new one for about 30 picks (a losing week or two). With weeks 7 and 8 only, the change is small (old to new, points):
   Under solo +4.7 to +4.6 (201 picks, 181 weighted), Under combined -6.6 to -6.2, Over -8.0 to -7.5, Over solo
   -8.0 to -7.2, Over combined -4.4 to -4.0; the position-level segments (all from week 8) are unchanged. No pick
   on the current board changes, because there is none yet; the week 9 picks will be the first priced with it.
7. **My board says when the live feed is down.** A warning at the top when ESPN's scoreboard or a game's box
   score is not answering during games, and a per-bet line ("live feed unavailable, graded from the official box
   score tomorrow") instead of a misleading "behind" verdict with no data.
8. **Late scratches show.** Week lines carry the player's status from the last pull; a card for a player ruled out
   since the morning report gets a "Ruled out" tag; a bet on My board on such a player reads "Void, ruled out
   before kickoff (stake refunded)", its money leaves the day's totals, and once the game is in the books without
   him the official grade is a Void rather than pending forever (any bet whose team has box-score rows and whose
   player has none).
Not done, by the owner's choice: 3 (credit budget in December), 4 (the dead second key), 9 (private repo), 10
(snapshot archive).
- Revert: `half_life_weeks` very large restores the unweighted calibration; `SEASON_GAME_TYPES = ("REG",)` restores
  the regular-season-only history (then the stand-down fires at week 19 instead of after the Super Bowl).

### 2026-11-03, afternoon MDT (stalled pulls: every hole closed that can be closed from here)
- Owner: go through the site and model so stalled pulls are never an issue again. GitHub's scheduler is the one
  thing that cannot be fixed from the repository (it stalled two hours on 2026-10-31 and the 11:15 UTC daily
  drifted to 13:14 on 2026-11-03), so every dependency on it running on time is removed:
  - **Pre-kickoff pulls come from the schedule, any day.** `kickoff_slots()` gives every game day one pull an hour
    before each cluster of kickoffs (kickoffs within 30 minutes share one). Before, only Sunday had one; a Friday
    game (Black Friday, Christmas Day 2026 is a Friday), a Saturday game in weeks 16-17 or a holiday Thursday
    kickoff relied on fixed weekday slots that no longer existed after the credit trim. The fixed slots are now
    only the extra looks (Thursday 9 am and 1 pm, Saturday 8 pm, Sunday 10 am, Monday 9 am and 1 pm); the
    Thursday, Sunday and Monday 5:30 pm looks and Sunday 1 pm are replaced by the kickoff pulls (5:15 pm, 1:05 pm,
    1:25 pm, 5:20 pm as the schedule says). The international 1-hour window is now the same rule; the 12-hour one
    stays. Credits unchanged, about 105 a week.
  - **A late run still serves the missed pull.** Slots are served by the first run after their time and each
    exactly once, so when the scheduler wakes after a stall it pulls every game that has not kicked off; nothing
    is lost that can still be bet. (Already true for fixed slots; now true for every pre-kickoff pull.)
  - **Two schedules, off the hour.** The pull job's crons move to :07/:37 and :22/:52: GitHub's own guidance is
    that runs queued at the top of the hour are delayed most, and both stalls so far were at those minutes.
  - **The daily job has a fallback.** A second cron 85 minutes after the first; scheduled runs pass `--auto`,
    which does nothing when a run already succeeded in the last 8 hours (`daily_is_fresh()`, from the run log the
    workflow writes). A by-hand run never skips. The standing post-mortem already fires at 8:20 am, after both.
  - **The site says when a pull is overdue.** A warning at the top when the published next pull time is more than
    45 minutes past (with the time of the lines on the board and how to force a pull from the Actions tab), and
    another when the model has not been updated in 30 hours. Stale lines are never shown as current without a
    notice.
  - Checked and sound: a pull that fails before saving leaves its slot unserved (the served list is only
    committed by a successful job); a save-step push conflict retries four times with the job's own version of
    generated files; credits are checked before every game and pulling stops at the floor; the keepalive and the
    daily run log keep both schedules enabled; the odds job falls back to a daily run when the cache is missing.
  - Not closable from here: GitHub stalling for longer than a kickoff window. A pull that the scheduler misses
    entirely until after kickoff cannot be bet, and the site now says so. The only remedy beyond this is an
    external trigger (a cron service calling the workflow with a token), which needs a token the owner would
    create; not done.
- Smoke test: the slot checks rewritten (pre-kickoff pulls on Thursday, Sunday clusters, a Friday game, the
  stalled-run case, the international morning kickoff, next-pull walking any day). README schedule updated.
- Revert: `INTL_WINDOWS_H = (12, 1)` and the fixed 5:30 pm slots if the kickoff rule misbehaves; the fallback
  daily cron is harmless either way.

### 2026-11-03, early afternoon MDT (pull schedule trimmed to one free key a month)
- Owner: cut the Saturday pulls to stay inside 500 credits a month. Measured from the stored snapshots, week 8
  cost 162 credits at two markets (Thursday 4, Saturday 68 over 9 pulls, Sunday 80 over 4, Monday 10); at three
  markets that is about 240 a week, 1,000 a month. Cutting Saturday alone leaves about 140 a week, 600 a month,
  still over, so the whole schedule is trimmed to a morning, midday and pre-kickoff look each game day: Thursday
  9 am, 1 pm, 5:30 pm; no Friday pulls (they found nothing in week 8); Saturday 8 pm only (the books post most
  Sunday lines Saturday evening); Sunday 10 am (ties with the pull an hour before the first kickoff on a normal
  week), 1 pm, 5:30 pm; Monday 9 am, 1 pm, 5:30 pm. About 105 credits a week, 450 a month. The cron is unchanged
  (the job still runs every quarter hour and serves each slot once). Smoke test checks rewritten for the new
  slots; README schedule and credits section updated. Cost: fewer in-week line updates on Saturday and early
  Sunday; the board still refreshes before every kickoff.
- Revert: put the hourly Saturday and Sunday slots back in `run.py` `PULL_SLOTS` if the key is upgraded.

### 2026-11-03, midday MDT (assists: a trial market on its own tab)
- Owner, after research round 8: build a separate tab for assists, replay past weeks to see where the model's
  theoretical assists picks would have landed, and give every assists pick the same slip links as the tackle
  picks. Done as a third market through the existing pipeline, never as a second model:
  - `config.ODDS_MARKETS` now pulls `player_assists` with the two tackle markets (one more credit per game per
    pull; the pull job is otherwise unchanged). `config.market_kind()` names a market key solo, assists or
    combined (alternate-line keys included); every place that used to test `"solo" in market` reads the kind.
  - Projection: `proj_ast = proj - proj_solo` (floored at 0.05), `phi_ast` from the backtest (`<group>|ast`,
    same corrected-dispersion estimate as solo), `fair_line_ast`. The pricer prices an assists line from it with
    the same bars, claim floor, segment correction (new segments "Under assists <pos>" and so on), lock score,
    grade, checklist, rundown ("assists" wording, average from combined less solo) and the book's links and
    selection ids. The game log for consistency is the per-game assists (`log_ast`).
  - Grading: the box-score number an assists pick settles on is combined less solo (`_actual_for`); the luck
    table, market watch, segment calibration, side-market records ("Over assists", "Under assists") and the
    weekly log all carry the third kind. `actuals.json` now holds [combined, solo, assists] per defender-game so
    My board grades an assists bet officially; the live tracker reads assists as ESPN's total less solo.
  - **Never a lock or a parlay leg** (`config.LOCK_MARKETS`): assists picks are theoretical until their record
    earns more. The tackle board (Plays tab) hides them; the Assists tab shows them with the same cards, book
    filter, best-price toggle, picks-only toggle and sort. The Track record market filter and a chip cover them.
  - Backtest adds "Assists: full model" and "Assists: season average" rows (Model check tab, own section).
  - Past weeks: no assists line was ever pulled, so the replay needs the book's historical lines. New
    `run.py history --weeks 7,8 --markets player_assists` fetches, for each game of a finished week (event ids
    from that week's live snapshots), the historical snapshot one hour before kickoff from The Odds API's
    historical endpoint and stores it as a snapshot with that timestamp, so `closing_lines()` and the replay read
    it like a live pull. The manual workflow "Fetch past lines for a market" (`history.yml`) runs it with the
    secret. Then `python tools/replay_five.py --week 7 --markets player_assists --out data/retro_assists.json
    --all-picks` prices those lines with the week's projections (calibration from games before the week, as the
    tackle replay does), grades every pick, and the daily job carries the result into the site as
    `meta.retro_assists`, shown on the Assists tab as "What the model would have picked in past weeks", every pick
    listed. Caveat built into the tab's wording: a historical snapshot is a closing line, so the replay has no
    early price and no line shopping; it tests the model's read, not the timing.
  - **Tried for week 8 at the owner's call (2026-11-03, 11:10 am MDT): the historical endpoint answered 401 on
    the first game. The key's plan has no historical access (The Odds API sells past lines on its paid tiers);
    nothing was charged. So the replay of weeks 7 and 8 cannot be done with this key, and the assists record
    starts with week 9's live pulls. The command now stops with that message instead of a traceback. If the plan
    is ever upgraded, the workflow and replay are ready as written.**
- Validation: smoke test passes (assists lines priced on the synthetic board with links, never a lock, no
  assists parlay leg, an assists pick graded on assists, actuals with three numbers, market kinds). Real-data
  daily run in a scratch copy (29,391 games): full model miss 1.6212, unchanged to the fourth decimal (the tackle
  pricing is untouched); assists full model miss 1.057 against 1.107 for the assists season average (4.5%
  better, bias +0.05), solo 1.128 vs 1.179 for comparison. Assists dispersion by position: CB 1.21, DL 1.03,
  LB 1.40, S 1.30 (1.4 to 1.6 for expected shares under 60%). Week 9 projections: 768 defenders, assists
  projection 0.3 to 5.8, mean 1.5; fair assists lines 0.5 to 5.5.
- Revert: drop `player_assists` from `ODDS_MARKETS` to stop the pull (everything else is inert without lines);
  the tab then shows "no assists lines" and the record keeps what was graded.

### 2026-11-03, morning MDT (no-vig closing-line value, in points; glossary tab)
- Owner sent the bettors' definition of CLV: the fair (no-vig) closing chance of the side taken minus the chance
  implied by the price taken, in probability points, with +1 to +2 good and +3 to +5 excellent. The grader now
  writes `clv_novig` on every pick with a closing price (`no_vig_clv` in `pipeline/grade.py`). On a held line it
  is exactly that difference. When the close is on a different line, the closing no-vig over chance is carried
  to our line through the market's own expected tackles (the mean that reproduces the closing chance at the
  closing line, with the position's default dispersion), so a line that moved our way counts as value and one
  that moved against us as its loss. Summary carries `avg_clv_novig`, `clv_novig_n`, `clv_held`; the site shows
  the average as a tile under the pick filters (per slice) and on "By side", with the benchmarks in the legend
  and `CLV_PCT_BARS` in `config.py` (good 0.01, excellent 0.03, elite 0.05). The old "beat the close" share
  (moved lines only) stays; the two answer different questions.
- Evidence, weeks 7 and 8 (398 picks, every one with a close at the same book): average no-vig CLV **-2.6
  points**. 352 picks closed on the line we took, averaging -2.8 (the vig, with the price barely moving: the
  books do not re-price tackle props between pulls); 21 lines moved our way (+5.5 average) and 23 against
  (-7.1). By grade: A -2.1 on 18, B -2.0 on 99, C -2.2 on 84. By side: Overs -2.2, Unders -2.7. Read plainly:
  by the market's own measure we have no closing-line value yet; the positive record so far is not something
  the closing line saw coming. This agrees with the week 7 luck table (selection lift about zero). It is also
  the expected reading of a market that rarely moves: a held -110 line can only ever score -2.4, so the
  measure can only turn positive through the few lines that move, and 44 moved lines is far too few to judge.
  Judge it on a few hundred moved lines; until then the record, calibration and lift carry more information.
- Glossary tab on the site (`renderGloss`): every term the site uses, from the bet itself (odds, implied
  chance, vig, no-vig price, push, unit, hit rate, parlay) through the projection (dispersion, snap share, stat
  crew, claimed chance, calibration), choosing picks (expected return, bars, lock score, grades, lock, the
  checklist, "an A in yellow", consistency, signal, thin, tags, rundown, consensus) to judging the record
  (closing line, beat the close, no-vig CLV, claimed and realised edge, whole board, lift, luck table, segment,
  market watch, backtest, walk-forward) and My board. Thresholds are read live from `meta.grading`; searchable.
- Revert: drop `clv_novig` if the translation through the market mean proves unstable on lines that moved two
  or more points (none yet); the held-line value needs no revert, it is the definition.

### 2026-11-03, early morning MDT (implied-probability edge on the Track record)
- Owner asked to track the average implied-probability edge. Two tiles under the pick filters, following every
  slice: "Claimed edge vs the price" (the model's claimed chance for the side minus the book's implied chance at
  the price taken, averaged) and "Realised edge vs the price" (hit rate minus that same implied chance; the book's
  average implied chance is shown beside it). The gap between the two is the overclaim, read per slice. Site only.

### 2026-11-03, early morning MDT (Track record: A + B and B + C grade filters)
- Owner asked to review the record of A and B picks together. The grade filter on "Every pick" has "A + B" and
  "B + C", and the chips under the totals carry an A+B record and a Locks record for the slice. Site only.

### 2026-11-02, late night MDT (My board: no bet stays pending once its game is graded)
- Owner: bets showed pending after every game was done. Two causes. Bets stored before weeks were recorded on them
  had no week, so the official grade could not be matched; the ledger now writes the week from the storage key,
  and the board uses the current week. And only the model's own picks had an official grade (the grader's rows);
  a bet added from the picker had to wait for the live feed, which forgets a game once the week rolls. The daily
  run now publishes `actuals.json`, the official box score (tackles and solo) for every defender-game this season,
  and the board and ledger grade any bet from it. Smoke check. Picks on the Track record tab still read
  "Pending" until the 4:15 am daily job grades them; that is the grader, not the board.

### 2026-11-02, late night MDT (clearing the board keeps the ledger)
- Owner: clearing the board must not clear the season ledger. "Clear this week's board" now marks the bets
  archived: they leave the live board and stay in the ledger with their stakes and results; adding one of them
  again from the Plays tab brings it back rather than duplicating it. "Remove" on a single card still deletes a bet
  (a bet added by mistake does not belong in the ledger), and the ledger's "Delete week" is the only way to erase a
  week. Live refresh, tail links and totals read the board; the ledger reads everything.

### 2026-11-02, late night MDT (ledger: grades on every bet; numbers on My board)
- Owner wants the grade of each pick he took visible in the ledger. Each ledger row leads with the grade badge
  (lock score on hover), rows sort A to C, and each week's line and the season bar carry a record and profit by
  grade, so the owner can see how the model's confidence has paid on his own board. Jersey numbers show on every
  My board card and ledger row; a bet stored before numbers existed looks its number up in the day's projections.

### 2026-11-02, late night MDT (jersey numbers on every bet)
- Owner asked for player numbers on the slip. `load_jerseys` (nflverse weekly rosters, latest week, 99.9% of
  players) puts `jersey` on each projection; the pricer, the week's line file, parlay legs and My board carry
  it, and the site shows "#3" beside the name on cards, parlay legs, the picker, the ledger and the Projections
  tab. Site and data plumbing only.

### 2026-11-02, late night MDT (My board: season ledger, backup and transfer)
- Owner wants his picks kept across weeks so the site keeps saying how much he is up or down, with a backup, and
  closed weeks hidden so the screen stays clean. Each week's board already lived in the browser under its own
  key; now every board is read into a "Season ledger" under My board: season record, settled stakes, up or down,
  return on stakes, and one collapsible row per week (record, staked, profit, the bets with the result written on
  each). A result is written on a bet once and kept: the grader's official box-score result when the Track
  record has one (older weeks are graded this way too), the live feed's final otherwise. Closed weeks (any week
  before the current one) fold away behind "Show N closed weeks"; the current week stays open. "Clear" now clears
  one week; a week can be deleted from the device.
- Backup: a JSON file download; a compact backup code (deflate + base64); a transfer link that imports the whole
  ledger on another device when opened (merge by bet, never duplicate; existing stakes and results kept); restore
  from file or code. The QR idea: a QR code is a link in a picture, so the transfer link is the same move; the QR
  library could not be vetted in this environment, so the link is sent as text for now. Checked in a browser:
  two seeded weeks graded officially, closed week folded, transfer link opened on a fresh device restored both
  weeks. Site only.

### 2026-11-02, late night MDT (Patch log tab)
- Owner asked for a place to see, every time a calibration or evaluation happens, what was investigated and what
  was found. `pipeline/patchlog.py` reads this file at each daily run into `docs/data/patchlog.json`: every
  research and analysis section (what was investigated, found, adopted or rejected), every weekly post-mortem,
  and every changelog entry with its evidence and revert condition; newest first, grouped by date. The site has
  a "Patch log" tab with filters by kind, a search, and each entry opening to the full text (lists, tables and
  emphasis rendered). This log stays the record; the tab is a view of it, so the standing post-mortem's entries
  appear there the morning they are written. Sealed with the rest of the site. Smoke check.

### 2026-11-02, night MDT (site sealed live; the post-mortem is now a standing scheduled task)
- The owner set `SITE_PASSWORDS`; the daily job sealed the site at 8:50 pm and the live site serves only the
  sealed files (plain `meta.json` answers 404, `meta.json.enc` 200). The first attempt had failed on the missing
  library (entry above).
- Owner: "after every slate of games we are re-evaluating the model and internally validating." That is now a
  scheduled task that starts a fresh session on Friday, Monday and Tuesday at 6:20 am Edmonton, two hours after
  the daily job has graded the slate, and runs the post-mortem protocol in CLAUDE.md rule 4: record and units,
  grade order, locks and parlays, calibration by claimed chance, the luck table, miss anatomy (snaps, plays
  faced, variance, missed role flags), the backtest's "without X" rows on level-matched miss, segment corrections
  at their caps; a rule change only on evidence across weeks or both halves, under the validation protocol; the
  write-up appended here and a short report to the owner. It reads the plain data under `data/` (picks, parlays,
  weekly log, segments, cache), since the site files are sealed and no secret is available to it.

### 2026-11-02, night MDT (seal: the runner lacked the crypto library; unsealed files never published again)
- The first sealed run failed: `cryptography` was installed on this machine but not in `requirements.txt`, so the
  runner could not seal and the save step published the plain files anyway. Fixed both: the library is a
  requirement, and when the seal step fails the save step restores the site files instead of committing them
  unsealed. Pitfall: a library used by the pipeline must be in requirements.txt; "works here" is not "works on the
  runner". Pitfall: a step that protects published output must stop the publish when it fails.

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
- A library the pipeline imports must be in requirements.txt; the runner installs only that file (the seal step
  failed on `cryptography`, 2026-11-02). A step that protects published output must stop the publish when it fails.
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
- `picks.csv` gains columns over time (`uncertain` added 2026-10-27); older rows read back as empty, so every use
  of a newer column must `fillna` a neutral value.
