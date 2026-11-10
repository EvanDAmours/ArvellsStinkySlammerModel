"""Settings for the tackle-prop pipeline. Edit here, not in the code."""
SEASON = 2026                      # current season
HISTORY_SEASONS = [2023, 2024, 2025]   # used for priors, stat crews and the backtest

# --- odds feed (The Odds API) ---
ODDS_SPORT = "americanfootball_nfl"
ODDS_MARKETS = ["player_tackles_assists", "player_solo_tackles", "player_assists"]   # assists added 2026-11-03 (scoping, research round 8): +1 credit per game
ASSIST_MARKET = "player_assists"
LOCK_MARKETS = ("player_solo_tackles", "player_tackles_assists")   # assists are a trial market: never a lock, an A or a parlay leg until their record earns it
A_GRADE_MARKETS = LOCK_MARKETS
# Until 2026-11-09 A grades and locks were solo tackles only: combined picks claimed 57% and hit 48% over weeks 7-9. The cause was the pricer
# (it read the line and ignored the price on it, which lifted every plus-money combined Under); the engine of 2026-11-09 prices from the
# book's fair chance, and on the closing lines of weeks 7-9 its combined Unders with a cautious edge of 2%+ went 14-6. Revert to solo only
# if combined A picks hit under 55% over their first 20.
# Sleepers (2026-11-08 night): lines where the model's own number, before any blend with the line, disagrees with the book by a margin that
# held in every live week. Blind board at the close, weeks 7-9: combined Overs with the model 0.5 to 1.5 above the line 48-25 (66%, +18%,
# 14-11 / 23-8 / 11-6); solo Unders with the model 0.5+ below the line 60-22 (73%, +23%, 21-8 / 25-3 / 14-11). The pick bars hide most of the
# combined ones (an Over needs a 10% return and a 55% claim after shrinking). Tracked as theoretical picks on their own record, never a lock.
# min_ev None: no price filter. Re-priced through the pipeline, the combined band went 35-21 (+14%/bet) at every price but 7-10 where the
# pricer (which leans on the line) also called the Over +EV; the rule was found on the model's number alone and is kept that way.
# Sleeper rules refined 2026-11-09 (weeks 7-9 re-priced at the close, Sunday night included; provisional, chosen on these weeks):
# - combined Overs only 0.5 to 1.0 above the line: 0.5-1.0 went 44-22 (67%), 1.0-1.5 went 9-11 (each week 50% or worse on the whole board
#   too: 47% of 19) -- when the model is that far off, the book usually knows a role change the history does not show.
# - solo Unders only when his season median is within a tackle of the line (`solo_hist`): 44-9 (83%) against 17-16 when the line sits more
#   than a tackle above his median (whole board: 83% of 48 vs 56% of 27).
# Sleeper grade (`sleeper_grade`), from the model's own evidence only (never the price): a steady role (no role change, absence, new team or
# questionable tag, 3+ games in role) is required for A or B. Solo Under A: steady and either the model's own chance of the Under is 70%+
# (`a_model`) or his defence expects fewer than 50 tackle opportunities (`a_opps`; carries + completions + sacks, league ~50): 20-2 in
# weeks 7-9; B the other steady ones 18-6; C 6-1. Combined Over B: steady and a model chance of 57%+ (`b_model_over`) 17-6; C 27-16. No
# combined A until its record earns one. Expect the A record to come down out of sample: the A conditions were chosen on these weeks.
SLEEPER = dict(comb_over=(0.5, 1.0), solo_under=-0.5, solo_hist=-1.0, min_ev=None, a_model=0.70, a_opps=50.0, b_model_over=0.57,
               review_after=40, review_hit=0.55, review_a_after=20, review_a_hit=0.70)


def market_kind(market):
    """'solo', 'assists' or 'combined' for a market key (alternate-line keys included)."""
    m = str(market)
    if "solo" in m:
        return "solo"
    if "assists" in m and "tackles" not in m:
        return "assists"
    return "combined"
ODDS_REGIONS = "us"                # only used if ODDS_BOOKMAKERS is empty
# Books licensed in Alberta's regulated market (AGLC / Alberta iGaming Corporation roster, Oct 13 2026) that
# The Odds API carries. The API has no Alberta-specific feeds: brands with a Canadian (Ontario) feed use it,
# the rest use their US or UK feed. Keep this list at 10 or fewer: every 10 bookmakers costs as much as a region.
ODDS_BOOKMAKERS = [
    "betmgm_ca_on",            # BetMGM (Canadian feed)
    "betrivers_ca_on",         # BetRivers (Canadian feed)
    "sportsinteraction_ca_on", # Sports Interaction (Canadian feed)
    "draftkings",              # DraftKings
    "fanduel",                 # FanDuel
    "williamhill_us",          # Caesars Sportsbook
    "espnbet",                 # theScore Bet
    "ballybet",                # Bally Bet
    "betvictor",               # BetVictor
    "betway",                  # Betway
    # Also licensed in Alberta but left out: bet365 (the API only has its Australian feed, "bet365_au"),
    # 888 ("sport888", UK feed), BET99 ("bet99_ca_on", paid API plans only). PointsBet Canada and Betano
    # are not on the Alberta roster, and Play Alberta, Stake, DAZN Bet, Tonybet, PowerPlay are not on the API.
]
# The solo-share gap (a measurement since 2026-11-10, in no rule): his own solo share to date, shrunk over `k` tackles of the
# league's, minus the share the book's two lines imply (solo line / combined line). Logged for every solo line. On weeks 7 to 9
# a gap of `flag` or below went 96-39 on the solo Under; on weeks 1 to 6 (fetched afterwards) the gap added nothing once the
# book's own share was known (gap without a high book share 44-42), so the card's flag reads the book's share (HOLES) instead.
SHARE_GAP = dict(k=25.0, flag=-0.04)
# Candidates from the sweep of 2026-11-10 (tools/holes.py), in no rule. book_share: the book's solo line as a share of its own
# combined line; at 58% or more the solo Under went 117-49 on weeks 7 to 9 and 176-103 on weeks 1 to 6, which it was not found
# on (flagged on the card). part_time: under 85% of the snaps this season, solo Under 82-40 then 66-47 (flagged on the card).
# hot: last three games half a tackle over his season average, combined Over 75-47 then 36-45: failed, no longer on the card,
# still scored by the tool.
HOLES = dict(part_time=0.85, hot=0.5, book_share=0.58)
OPENER_DATES = ("2026-11-11", "2026-11-18")          # Wednesdays with an early look at the whole week's lines (weeks 10 and 11): a trial, see MODEL_LOG
ODDS_KEY_ENV = ["ODDS_API_KEY", "PARLAY_API_KEY"]   # GitHub secrets holding Odds API keys, used in this order
MIN_CREDITS_LEFT = 25              # a key with fewer credits left this month is skipped; pulling stops when every key is below it
# The credit budget (2026-11-09; run.credit_budget). A pull costs one credit per market per game. Before every scheduled pull the
# month's remaining schedule is priced at each service level and the richest one the credits can pay for is run:
#   3 every scheduled pull, three markets | 2 the same without the assists trial market | 1 two markets, each pre-kickoff pull only for
#   the games about to kick off, every earlier look kept | 0 the same with Saturday night's look only | -1 pre-kickoff pulls only.
# So the last thing to go is the pull an hour before a game's kickoff, with the inactives known.
ODDS_BASE_MARKETS = ["player_tackles_assists", "player_solo_tackles"]
ODDS_RESET_DAY = 1                 # day of the month the key's credits reset (assumed: the free plan follows the calendar month, UTC)

# --- model ---
SHRINK_GAMES = 1                   # weight (in games) of the prior when averaging; the backtest reports the best single value
# Shrinkage by position (research 2026-10-26, out of sample 2025-26): linebackers are best predicted by their own season
# almost unshrunk, corners and linemen need a heavy pull toward last season. MAE by group fell 0.6-1.0%.
SHRINK_GAMES_BY_GROUP = {"LB": 0.5, "S": 1.0, "CB": 3.0, "DL": 3.0}
# Snap-share trend: last 3 games' defensive snap share vs the season share, as a multiplier (ratio ** power).
# Rises are captured almost fully at 0.45; drops are overcorrected at that power, so they get a smaller one (0.35 now).
SNAP_TREND = dict(games=3, power_up=0.45, power_down=0.35, cap=(0.6, 1.5), min_share=0.05)
# Tackle opportunities (opponent carries + completions + sacks) expected this game vs the ones the player has faced:
# volume regresses to the league mean, which a season average ignores. Damped and capped: the extremes were wrong.
VOLUME = dict(power=0.5, cap=(0.9, 1.1), pseudo_games=4)
# New data sources (research 2026-10-27, fitted on 2023-24, scored on 2025-26; see MODEL_LOG.md):
DEPTH = dict(demoted=0.90, promoted=1.02)            # listed below a starter he was above last game: -17% observed, damped to -10%
PFR = dict(target_slope=-0.065, target_cap=(0.85, 1.12), miss_slope=0.22, miss_base=0.10, miss_cap=(0.95, 1.12))
MIX = dict(weight=0.3, power=0.5, cap=(0.85, 1.15))   # opponent run/pass mix vs the player's own run- and pass-tackle rates
REST = dict(bye=0.96, bye_days=10)                    # a defence coming off a bye runs ~4% under its average
# Own injury report (research round 3): listed questionable and played, -6% over 1,191 games; limited practice -4%.
# Questionable players are priced (not passed) but never locks or parlay legs, since they may not play.
INJURY = dict(questionable=0.92, limited_practice=0.97)
# New role (post-mortem, week 8 Thursday 2026): a part-timer who just played a starter's snaps. His season history does
# not describe him: actual ran 18-23% over the model on 1,050 such games, the outlier-fade signal failed on him (45%
# landed under the model vs 56% otherwise), and his count is far more spread (variance/mean 1.9 vs 1.4). So: projection
# x (last-game share / season share)^power, no outlier-fade signal, a wider distribution, consistency counted over
# in-role games only, and NEVER a lock or a parlay leg until his season share catches up.
NEW_ROLE = dict(max_prev_share=0.6, min_last_share=0.6, min_ratio=1.5, power=0.0, cap=2.5, phi_bump=0.5, phi_bump_solo=0.25, in_role_share=0.7, min_in_role_games=3)   # power 0 since round 4: the per-snap base carries the role change; the flag still drives the checklist and the wider distribution
# Role shifts (audit after the week 8 Thursday post-mortem; 28,861 defender-games, fitted 2023-24, checked 2025-26):
# - last game's snap share under 70% of his season share: ran 5-14% under the model -> x ratio^0.1 (bias -0.25 -> -0.02
#   train, -0.16 -> +0.07 test; overall error -0.7%)
# - 3+ weeks since his last game: 10-12% under -> x0.95 (conservative: the two halves disagree on the size)
# - one missed game without a bye: 11% under -> x0.92
# - first game after a mid-season team change: 20% under on 124 games -> x0.90
# - an Over "fading" a low last game is wrong on average (actual 4.5% under the model even for settled players, 18% under
#   when he had simply played less), so the outlier-fade signal now fires only for Unders after a big game in a settled role.
ROLE_SHIFT = dict(contraction_ratio=0.7, contraction_power=0.1, absence_weeks=3, absence_factor=0.95, missed_game_factor=0.92, new_team_factor=0.90)
# Lock eligibility, market-free: a lock must come from where the model is reliable. Never a lock or a parlay leg: new role,
# reduced role, back from absence, new team, fewer than 3 games in his current role (unless every game he has was), questionable.
LOCK_RULES = dict(min_in_role_games=3, overs_eligible=False, next_man_up_under=False)   # Overs: 28-40 live (41%) and 32-46% on all lines where the model sat above the market; never a lock or a parlay leg until 40 further Over picks hit 55%+
# next_man_up_under (2026-11-09): the final projection, out of sample, runs 12% under the actual count on next-man-up backups (918 games; 9% and +0.29 tackles,
# t +2.3, at a corrector weight of 0.8; 14%, 2% and 16% by season), all of it on the ones the share model expects under 60% of the snaps (710 games: 16% low, +0.43,
# t +3.3; the 208 expected at 60%+ are level). No correction holds: a level fitted on earlier seasons over-corrects the next (deviance +0.010, t +0.3).
# So a next-man-up player is never a lock or an A, and an Under on one expected under 60% is not a pick at all: when a book posts a line on a backup it
# knows he is playing, and the model does not. His Over stays a pick (the model is the cautious side of it).
# ---- Research round 4 (2026-10-30, after the McDuffie post-mortem). Per-snap projection and what hangs off it. Evidence in MODEL_LOG.
# Per-snap base = tackles per defensive snap (games with 10+ defensive snaps only, shrunk toward last season's rate or the
# position rate over 150 pseudo-snaps) x expected snap share x expected team defensive snaps, calibrated; blended with
# the per-game base at `weight` (0.4 now; 30% when introduced: error -0.5% train, -0.3% test; new-role error -3%).
PERSNAP = dict(weight=0.4, pseudo_snaps=150, cal=1.097, min_game_snaps=10, min_prior_snaps=150, group_rate={"CB": 0.074, "DL": 0.066, "LB": 0.110, "S": 0.093})
# Next-game snap share from (last game, last three, season) with weights by situation, fitted 2023-24: a jump backed by a
# vacancy or a depth-chart listing holds; a jump in a blowout or with nothing behind it regresses; a drop half-holds.
SHARE_MODEL = dict(vacancy=(1.02, 0.0, -0.29), blowout=(0.55, 0.43, -0.16), up=(0.48, 0.42, 0.02), down=(0.19, 0.41, 0.41), steady=(0.32, 0.22, 0.44),
                   up_ratio=1.5, down_ratio=0.7, blowout_margin=17)
# The McDuffie rule: a regular (75%+ share) at his position group is out or gone, his share jumped 1.5x+, and it was not a
# blowout: project per-snap at his last-game share. The per-game model ran 24% under on these (bias +1.03 -> +0.14 test).
VACANCY = dict(min_jump=1.5, regular_share=0.75, recent_weeks=3, weight=0.5)   # weight: how far the projection moves to his last-game share (0.5: bias +0.05, full: -0.46)
# Tackles the opponent allows to this position group vs league (prior games, shrunk to 3 pseudo-games). Measured and NOT used
# as a factor (round 4: no gain once the per-snap base is in); kept as a feature for the corrector.
MATCHUP = dict(pseudo_games=3)
DOME_CB = 1.05            # corners in domes / closed roofs: +4.6% (2023-24) and +7.1% (2025-26) over the model
SOLO_DRIFT = dict(weeks=3, cap=(0.85, 1.15))   # league solo share, last 3 weeks / season to date: solo crediting drifts down through a season (2025: 0.55 -> 0.51)
PHI_SHARE_SPLIT = 0.6     # dispersion estimated separately for players expected below this snap share (var/mean 1.6-1.7 vs 1.2-1.4)
# ---- The factor set (rebuild of 2026-11-09; evidence in MODEL_LOG "Decision register"). Which hand-built factors move the factor
# model's mean. Judged on the FINAL projection (factor model + corrector), walk-forward by season, Poisson deviance, paired, season-weeks
# as the unit, and on the regulars who get lines (REGULAR_SHARE). Out: stat crew, snap trend, run/pass mix, bye, injury report, role shift
# and the vacancy rule (none distinguishable from zero or each worsening the mean; together, with the corrector's next-man-up input:
# deviance -0.0089 a game for regulars (t -2.8) and -0.0077 for every player (t -3.2), folds 2025-26). Each stays a corrector input, so a
# real effect is still learned; the code stays so the daily test (backtest.json "factor_tests") can show one earning its way back.
FACTORS = dict(tilt=True, role=True, volume=True, depth=True, pfr=True, dome=True, outlier_damp=True, persnap=True, new_role=True, solo_drift=True,
               crew=False, snap=False, mix=False, rest=False, injury=False, role_shift=False, vacancy=False)
# Second model (research round 3): a gradient-boosted corrector on the same features, Poisson loss, trained fresh each
# morning on every finished game, blended with the factor model. Out of sample it cut error 1.1% (2025-26) and 1.5%
# (2026 trained through 2025). The backtest reports it walk-forward: trained on earlier seasons, scored on the latest.
# weight 0.6, kept on 2026-11-09 after testing 0.8: for every defender the fold results say the more seasons the corrector has learned
# from the more of the number it deserves (best weight by fold 0.5, 0.9, 1.0), but that gain is all on part-timers who never get a line.
# For the regulars who do (expected at 80%+ of the snaps) the best weight by fold is 0.4, 0.6, 0.7 and 0.8 is no better than 0.6 on the
# 2025-26 folds (deviance -0.0085 vs -0.0089 against the old design) and worse on the 2024 fold (+0.024, t +2.3). Judge on who is priced.
GBM = dict(weight=0.6, max_iter=800, learning_rate=0.02, max_leaf_nodes=31, min_samples_leaf=40, l2=0.5, seeds=(0, 1, 2))
REGULAR_SHARE = 0.8                 # "regulars": expected at this share of the snaps or more. They are the players the books post lines on, so they are who a change is judged on
POS_PRIOR = {"LB": 6.0, "S": 4.5, "CB": 3.5, "DL": 2.5}       # tackles per game, used only with no history
POS_SOLO_SHARE = {"LB": 0.49, "S": 0.57, "CB": 0.66, "DL": 0.44}       # the positions' solo shares measured on 2023-26 (were 0.52, 0.62, 0.72, 0.45)
SOLO_SHARE_PSEUDO = 150            # tackles of position prior mixed into a player's solo share (was 25, 8 before): a player's own share is mostly noise over a
                                   # season. Solo deviance on regulars -0.0174 (t -5.9) in each of three seasons; on 2026's closing lines the engine's margin over
                                   # the book goes from +0.0038 to +0.0075 on weeks 2 to 6 and +0.0073 to +0.0092 on weeks 7 to 9 (MODEL_LOG, 2026-11-10)
# Segment calibration (2026-10-31): a pick's claimed chance is corrected by how the model's claims have actually
# resolved for picks like it (side x market x position), shrunk by n/(n+k) toward no correction. Our own results only,
# never the book's. Finest segment with min_n graded picks wins; the correction is capped.
SEGMENT_CAL = dict(k=40, min_n=10, cap=0.08, ev_weight=0.5, half_life_weeks=3)   # tightened 2026-10-31 evening: 15 picks were moving claims 10 points; now at most 8, and n/(n+40)
LOCKS_PER_SEGMENT = 2            # risk control: no more than two locks a day of the same kind (side x market x position); if the market corrects one kind, not every lock falls with it
PARLAY_LEGS_PER_SEGMENT = 2      # same for parlay legs   # ev_weight: how much of the correction also moves the probability that decides whether a line is a pick
# After an outlier game in a settled role the season average still leans toward it: actual ran 5.5% under the model
# after a game 3+ above his base (both halves) and 4-9% under after a game 3+ below. Damping on top of the shrinkage.
OUTLIER_DAMP = dict(after_high=0.975, after_low=0.96)
SPREAD_TILT = 0.005                # +0.5% tackles per point a defense is an underdog (capped)
SPREAD_TILT_CAP = 0.05
CREW_PSEUDO_TACKLES = 250          # how hard each stadium's crew rate is pulled toward league average
ROLE_BUMP = 1.10                   # boost for a backup when a regular at his position group is inactive
DEFAULT_PHI = {"LB": 0.75, "S": 1.0, "CB": 1.0, "DL": 1.0}  # variance / mean; replaced by backtest estimates

# --- pricing: one probability per line (the engine of 2026-11-09, live from week 10; evidence and the decision in MODEL_LOG) ---
# For every posted line the book's own two-way price gives a fair chance (its price with the vig taken out). The model's count
# distribution gives its own chance at the same line. The win chance moves the book's fair chance by a fraction `beta` of the model's
# disagreement, in log-odds:  logit(p) = logit(p_book) + beta x [logit(p_model) - logit(p_book)].
# Nothing but disagreement can make a pick: at zero disagreement p is the fair chance and every price loses its vig.
#   beta 0.5: on the 745 closing lines of weeks 7-9 the fitted weight was +0.53 (se 0.20; +0.48 combined, +0.57 solo); at 0.5 the log-loss
#   was 0.6823 against the market's 0.6898, the model's own 0.6865 and the old raw-line blend's 0.6827, better than the market in every
#   week (+0.004, +0.013, +0.005). A ceiling on large disagreements made it worse; a different weight per side did not help.
#   beta_low 0.25: the cautious chance, about 1.4 standard errors under the fitted weight. A PICK is a bet that still breaks even there.
# Grades are built only from numbers that cannot improve when the book agrees more (checked in the smoke test): the cautious edge
# (cautious chance x decimal odds - 1) and the model's own chance. Provisional: the bars are round numbers, not fitted, but weeks 7-9
# is where they were looked at (closing lines: cautious edge 0 to 2%: 37-25; 2%+: 31-20; 2%+ with a model chance of 70%+: 13-6).
ENGINE = dict(beta=0.5, beta_low=0.25,
              pick_edge_low=0.0,     # a pick: cautious edge at or above this
              lean_edge=0.02,        # a lean: this much at the win chance but under water at the cautious one. Shown and logged, never staked (72-68 at the close)
              b_edge_low=0.02,       # B: cautious edge of 2%+
              a_model=0.70,          # A: a B whose model's own chance is 70%+ and whose lock checklist is clear
              rho=0.02,
              beta_by_kind=dict(combined=0.35, solo=0.65),   # the weight by market since 2026-11-09 (owner's instruction): the model has beaten the book on solo lines and not on combined
              low_ratio=0.5,         # the cautious chance counts the disagreement at this share of the weight
              a_rule="sleeper",      # A: a pick that is also a sleeper on the same side (the model's number and the line apart by the sleeper margin), checklist clear
              misfit_model=0.93)     # a line only one book posts, on which the model's own chance is this or more: the line does not fit this player (a mis-posted line or a wrong match), no pick              # how alike two picks of one kind on one slate are: the weekly shock (6.5 points of hit rate on solo Unders) as a correlation
FROZEN_UNTIL = "2026-12-08"          # evidence rule: no bar, weight or cap in ENGINE, STAKE, FACTORS or GBM changes before this date (four graded weeks)
                                     # unless a defect is found; candidates are tested in the shadow on data/lines_log.csv and reported, not adopted
CLAIM_SHRINK = 0.6                   # legacy: only to read the claimed chance of picks logged before the engine (through week 9) that carry none
# The engine's first week. Its weight and bars were chosen on weeks 7 to 9 of 2026, so every figure from those weeks is
# in-sample. The scoreboard and the record report the weeks from here on separately ("since the engine"), and the
# decision register's revert conditions are read on those weeks alone.
ENGINE_LIVE = dict(season=2026, week=10, read_after_week=13)   # decisions E2 and S1 are read after week 13, on weeks 10 to 13
# Candidates scored in the shadow on every closing line and never used for a pick (MODEL_LOG, open issue 2). Written
# down on 2026-11-09, before week 10 had a line: changing a number here restarts that candidate's test.
SHADOW = dict(beta_by_kind=dict(combined=0.5, solo=0.5),      # the flat weight of 0.5 that the weight by market replaced on 2026-11-09
              centre_kinds=("combined",),                    # the model's gap to the book centred on the week's own mean gap, for these markets
              level_kinds=("solo",), level_shrink=100)       # the level for lined players applied to solo lines too (adopted for combined only)
# The level for players who get lines: the model's combined number ran 3 to 4% under the box score of lined players in each of
# weeks 7, 8 and 9. Each week's combined projections are multiplied by actual over projected on the season's earlier lined
# games, shrunk n / (n + shrink) and clipped. Solo is left alone: there the model ran high two weeks and low the third.
LINED_LEVEL = dict(kinds=("combined",), shrink=100, clip=(0.9, 1.1))

# --- betting rules ---
FADE_GAP = 3.0                     # last game this many tackles from his average counts as an outlier (the damping factor and the card's wording)
MIN_GAMES_FOR_PICK = 3

# --- the lock score and the grade ---
# The lock score is the model's own chance of the pick's side, out of 100: the model's evidence and nothing else. It ranks the locks.
LOCK_MIN_SCORE = 100 * ENGINE["a_model"]
GRADE_BARS = dict(A=LOCK_MIN_SCORE, B=None)      # kept for the site's legend: an A needs this score (and the cautious edge and the checklist)
GRADE_UNITS = dict(A=1.0, B=0.5, C=0.25)   # the grade ladder, kept for the record's "units at grade stake"; the stake on a pick is STAKE below
# Stake per pick: a quarter of the Kelly fraction of a 100-unit bankroll AT THE CAUTIOUS CHANCE, so a pick that only just survives the
# cautious test gets the minimum. Then the slate is sized as one book, because its picks are not independent (week 9: 59.9 of 100 units
# were out on one Sunday, 86% of them on solo Unders, each sized as if alone): every stake is divided by 1 + (N - 1) x rho for the N picks
# of its kind (side x market) on its slate day, and capped per game, per kind per slate and per slate (scaled down together).
# Revert / raise: move to the win chance (not the cautious one) once the engine has beaten the market's fair close by two standard
# errors with weeks as the unit (Track record, "Against the market").
STAKE = dict(bankroll=100.0, kelly_fraction=0.25, min=0.1, max=3.0, game_cap=4.0, kind_cap=10.0, slate_cap=15.0)
# Closing-line value: among picks whose closing number differed from ours, the share that moved our way. Below
# ~52% is indistinguishable from noise over a few hundred bets (standard error ~3% at 300); sharp bettors sustain
# 55-60% and 60%+ is rare. Shown in the site legend.
CLV_BARS = dict(decent=0.52, good=0.56, great=0.60)
# No-vig closing-line value, the way bettors quote it: the fair (vig-free) closing chance of our side minus the
# chance implied by the price we took, averaged in probability points. A -110 price that closes -110/-110 is -2.4
# points (the vig). Sustained +1 to +2 points is good, +3 to +5 excellent, above +5 is rare. Shown on the site.
CLV_PCT_BARS = dict(good=0.01, excellent=0.03, elite=0.05)

# --- locks per slate day (Edmonton time) and the recommended parlay ---
LOCKS_PER_SLATE = dict(single=3, multi=5)   # at most this many locks: 3 on a one-game day, 5 on a multi-game day
# A lock is a pick the model strongly believes in, never "the best of a thin board" (owner, 2026-11-02). It needs an A grade;
# a slate with no A has no lock. Among the A picks the locks are the highest lock scores (the model's own chance).
PARLAY_LEGS = (2, 3)                        # fewest and most legs in the recommended parlay (fewer legs = better chance of hitting)
# Legs on one defence share the plays it faces (sd 7.6 around expectation): two Unders rise or fall together, an
# Under and an Over pull apart. The parlay's chance is the product of the legs' claimed chances times the ratio a
# simulation with a shared plays draw gives over independence (weeks 7-8: 1.05 for two Unders, 0.94 for an
# Under and an Over, 1.10 for three Unders). Research round 9.
PARLAY_CORR = dict(sd_plays=7.6, sims=20000, phi_floor=0.55, clip=(0.8, 1.3))
PARLAY_MARKETS = ("player_tackles_assists",)  # combined tackles only: the books refuse solo-tackle legs in a same-game parlay (owner, 2026-11-02)
PARLAY_MIN_PROB = 0.60                      # a leg must be a pick (cautious edge at or above zero) whose model's own chance is at least this
PARLAY_FALLBACK_PROB = 0.56                 # if too few legs clear that, picks down to this model chance are allowed; below it, no parlay
PARLAY_KELLY_FRACTION = 0.25                # stake = this fraction of the Kelly stake for the parlay
PARLAY_UNITS = (0.1, 1.0)                   # stake bounds, in units

# Trade watch (pipeline/watch.py): the owner is notified (a GitHub issue that mentions them, so GitHub emails and
# pushes) the first time a trade appears on the team's ESPN transaction wire. On every ticker beat until `until`.
TRADE_WATCH = dict(team="NYG", espn_team_id=19, notify="EvanDAmours", until="2026-11-11T06:00:00+00:00")   # deadline: Tue 2026-11-10, 4 pm ET
