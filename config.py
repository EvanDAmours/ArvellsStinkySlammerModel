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
# Second model (research round 3): a gradient-boosted corrector on the same features, Poisson loss, trained fresh each
# morning on every finished game, blended with the factor model. Out of sample it cut error 1.1% (2025-26) and 1.5%
# (2026 trained through 2025). The backtest reports it walk-forward: trained on earlier seasons, scored on the latest.
GBM = dict(weight=0.6, max_iter=800, learning_rate=0.02, max_leaf_nodes=31, min_samples_leaf=40, l2=0.5, seeds=(0, 1, 2))
POS_PRIOR = {"LB": 6.0, "S": 4.5, "CB": 3.5, "DL": 2.5}       # tackles per game, used only with no history
POS_SOLO_SHARE = {"LB": 0.52, "S": 0.62, "CB": 0.72, "DL": 0.45}
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
SIGNAL_BAR = 0.04                  # minimum with a role-change or outlier-fade signal
FADE_GAP = 3.0                     # last game this many tackles from his average counts as an outlier
MIN_GAMES_FOR_PICK = 3

# --- confidence grade for every pick (0-100 "lock score", then a letter) ---
# Built only from the model's own evidence, never from the book's opinion (see the vision in MODEL_LOG.md):
# the expected return at the posted price, the model's own probability for the side, how often the player cleared
# this line in his games this season, how many games of data he has, and whether a role-change or outlier-fade
# signal is behind the pick. Owner's decision 2026-10-26, replacing a version that rewarded market agreement.
LOCK_WEIGHTS = dict(ev=0.35, model=0.25, consistency=0.20, sample=0.10, signal=0.10)
LOCK_EV_FULL = 0.15                # an expected return this high scores full marks on the EV component
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
PARLAY_MIN_PROB = 0.60                      # a leg needs at least this blended chance of hitting
PARLAY_FALLBACK_PROB = 0.55                 # if too few legs clear that, legs down to this chance are allowed; below it, no parlay
PARLAY_KELLY_FRACTION = 0.25                # stake = this fraction of the Kelly stake for the parlay
PARLAY_UNITS = (0.1, 1.0)                   # stake bounds, in units
