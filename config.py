"""Settings for the tackle-prop pipeline. Edit here, not in the code."""
SEASON = 2026                      # current season
HISTORY_SEASONS = [2023, 2024, 2025]   # used for priors, stat crews and the backtest

# --- odds feed (The Odds API) ---
ODDS_SPORT = "americanfootball_nfl"
ODDS_MARKETS = ["player_tackles_assists", "player_solo_tackles"]
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
ODDS_KEY_ENV = ["ODDS_API_KEY", "PARLAY_API_KEY"]   # GitHub secrets holding Odds API keys, used in this order
MIN_CREDITS_LEFT = 25              # a key with fewer credits left this month is skipped; pulling stops when every key is below it

# --- model ---
SHRINK_GAMES = 1                   # weight (in games) of the prior when averaging; the backtest reports the best single value
# Shrinkage by position (research 2026-10-26, out of sample 2025-26): linebackers are best predicted by their own season
# almost unshrunk, corners and linemen need a heavy pull toward last season. MAE by group fell 0.6-1.0%.
SHRINK_GAMES_BY_GROUP = {"LB": 0.5, "S": 1.0, "CB": 3.0, "DL": 3.0}
# Snap-share trend: last 3 games' defensive snap share vs the season share, as a multiplier (ratio ** power).
# Rises are captured almost fully at 0.45; drops are overcorrected at that power, so they get 0.25.
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
NEW_ROLE = dict(max_prev_share=0.6, min_last_share=0.6, min_ratio=1.5, power=0.0, cap=2.5, phi_bump=0.5, in_role_share=0.7, min_in_role_games=3)   # power 0 since round 4: the per-snap base carries the role change; the flag still drives the checklist and the wider distribution
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
LOCK_RULES = dict(min_in_role_games=3, overs_eligible=False)   # Overs: 28-40 live (41%) and 32-46% on all lines where the model sat above the market; never a lock or a parlay leg until 40 further Over picks hit 55%+
# ---- Research round 4 (2026-10-30, after the McDuffie post-mortem). Per-snap projection and what hangs off it. Evidence in MODEL_LOG.
# Per-snap base = tackles per defensive snap (games with 10+ defensive snaps only, shrunk toward last season's rate or the
# position rate over 150 pseudo-snaps) x expected snap share x expected team defensive snaps, calibrated; blended 30% with
# the per-game base (error -0.5% train, -0.3% test; new-role error -3%).
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
# Second model (research round 3): a gradient-boosted corrector on the same features, Poisson loss, trained fresh each
# morning on every finished game, blended with the factor model. Out of sample it cut error 1.1% (2025-26) and 1.5%
# (2026 trained through 2025). The backtest reports it walk-forward: trained on earlier seasons, scored on the latest.
GBM = dict(weight=0.6, max_iter=800, learning_rate=0.02, max_leaf_nodes=31, min_samples_leaf=40, l2=0.5, seeds=(0, 1, 2))
POS_PRIOR = {"LB": 6.0, "S": 4.5, "CB": 3.5, "DL": 2.5}       # tackles per game, used only with no history
POS_SOLO_SHARE = {"LB": 0.52, "S": 0.62, "CB": 0.72, "DL": 0.45}
SOLO_SHARE_PSEUDO = 25             # tackles of position prior mixed into a player's solo share (was 8): solo error -1.0% on 2025-26, -0.7% on 2023-24
# Segment calibration (2026-10-31): a pick's claimed chance is corrected by how the model's claims have actually
# resolved for picks like it (side x market x position), shrunk by n/(n+k) toward no correction. Our own results only,
# never the book's. Finest segment with min_n graded picks wins; the correction is capped.
SEGMENT_CAL = dict(k=30, min_n=10, cap=0.15)
SPREAD_TILT = 0.005                # +0.5% tackles per point a defense is an underdog (capped)
SPREAD_TILT_CAP = 0.05
CREW_PSEUDO_TACKLES = 250          # how hard each stadium's crew rate is pulled toward league average
ROLE_BUMP = 1.10                   # boost for a backup when a regular at his position group is inactive
DEFAULT_PHI = {"LB": 0.75, "S": 1.0, "CB": 1.0, "DL": 1.0}  # variance / mean; replaced by backtest estimates

# --- pricing: how much to trust the market ---
# The posted line is itself a forecast, and in week 7 of 2026 it predicted tackles better than the raw projection
# (actual = 0.44 x projection + 0.60 x line). The mean used for pricing is a blend of the two.
LINE_WEIGHT = 0.6                  # weight on the consensus line (median across books); 0 = pure model, 1 = pure market
PROB_SHRINK = 1.0                  # 1 = use the blended model probability as is; <1 pulls it further toward the market's no-vig probability

# --- betting rules ---
PICK_BAR = 0.06                    # minimum expected return without a supporting signal
PICK_BAR_OVER = 0.10               # an Over needs more: the model's Over leans hit 32-46% on weeks 7-8 lines where it was above the market (audit 2026-10-30)
SIGNAL_BAR = 0.04                  # minimum with a role-change or outlier-fade signal
# Selected picks claim more than they hit (weeks 7-8 replay: claimed 55.8%, hit 50.9% on 163 picks; the winner's curse of
# picking the biggest disagreements). The claimed chance of a pick is shrunk toward even by this factor for the lock score,
# the card and parlays. Market-free: it shrinks toward 50%, not toward the book.
CLAIM_SHRINK = 0.6
FADE_GAP = 3.0                     # last game this many tackles from his average counts as an outlier
MIN_GAMES_FOR_PICK = 3

# --- confidence grade for every pick (0-100 "lock score", then a letter) ---
# Built only from the model's own evidence, never from the book's opinion (see the vision in MODEL_LOG.md):
# the expected return at the posted price, the model's own probability for the side, how often the player cleared
# this line in his games this season, how many games of data he has, and whether a role-change or outlier-fade
# signal is behind the pick. Owner's decision 2026-10-26, replacing a version that rewarded market agreement.
LOCK_WEIGHTS = dict(ev=0.35, model=0.25, consistency=0.20, sample=0.10, signal=0.10)
LOCK_EV_FULL = 0.10                # an expected return this high scores full marks on the EV component (was 0.15)
LOCK_EV_FADE = (0.20, 0.40)        # above 20% the EV component falls off, to zero at 40%: picks with 25%+ claimed return hit 33% (n=15), 15-25% hit 50%, 6-10% hit 57%
LOCK_MODEL_FULL = 0.75             # a model probability this high for our side scores full marks (50% scores zero)
GRADE_BARS = dict(A=72, B=55)      # lock score at or above these is an A or a B; the rest are C
GRADE_UNITS = dict(A=1.0, B=0.5, C=0.25)   # suggested stake per grade, in units (shown in the site legend)
# Closing-line value: among picks whose closing number differed from ours, the share that moved our way. Below
# ~52% is indistinguishable from noise over a few hundred bets (standard error ~3% at 300); sharp bettors sustain
# 55-60% and 60%+ is rare. Shown in the site legend.
CLV_BARS = dict(decent=0.52, good=0.56, great=0.60)

# --- locks per slate day (Edmonton time) and the recommended parlay ---
LOCKS_PER_SLATE = dict(single=3, multi=5)   # one game kicking off that day -> 3 locks; more games -> 5
LOCK_MIN_SCORE = 55                         # a pick needs at least a B to be a lock; fewer locks beats fake ones
PARLAY_LEGS = (2, 3)                        # fewest and most legs in the recommended parlay (fewer legs = better chance of hitting)
PARLAY_MIN_PROB = 0.56                      # a leg needs at least this claimed (shrunk) chance of hitting: 0.60 before the claim shrink
PARLAY_FALLBACK_PROB = 0.53                 # if too few legs clear that, legs down to this chance are allowed; below it, no parlay
PARLAY_KELLY_FRACTION = 0.25                # stake = this fraction of the Kelly stake for the parlay
PARLAY_UNITS = (0.1, 1.0)                   # stake bounds, in units
