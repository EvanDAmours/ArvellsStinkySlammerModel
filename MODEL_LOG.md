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

## Standing watch: grade order (opened 2026-10-30, evening MDT, at the owner's request)

Live record by grade as of 2026-10-30: A 4-2 (67%), B 13-5 (72%), C 13-13 (50%). A below B on six A picks is not
yet evidence of anything, but the grade order is the one thing the grading formula must get right, so it is
watched after every slate (the Track record tab prints "Grade order check" in red while A trails B) and reviewed
after Sunday's games are graded (week 8). Decision rule: at 30 graded A picks, if A's hit rate is still below B's,
`LOCK_WEIGHTS` is re-fitted on the graded picks (which parts of the score actually predict a hit), and until then
the suggested stakes stay as they are. Under the 2026-10-30 pricing audit the lock score already changed (EV part
saturates at 10%, claimed chance shrunk), so A picks from here on are a different population from the first six;
the review keeps the two apart.

## Weekly post-mortems

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
