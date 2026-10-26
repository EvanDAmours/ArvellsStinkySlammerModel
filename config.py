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
SHRINK_GAMES = 1                   # weight (in games) of the prior when averaging; the backtest reports the best value
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
# Weighted blend of: expected return, whether the market also favours our side, how often the player cleared this
# line in his games this season, and how many games of data he has; an outlier-fade signal adds a bonus.
# Market agreement carries the most weight: in week 7 of 2026 picks on the side the market also favoured hit 60%,
# picks against the market 45%, while the size of the model's disagreement predicted nothing. Provisional; see MODEL_LOG.md.
LOCK_WEIGHTS = dict(ev=0.25, market=0.40, consistency=0.20, sample=0.15)
LOCK_EV_FULL = 0.15                # an expected return this high scores full marks on the EV component
LOCK_FADE_BONUS = 5
GRADE_BARS = dict(A=72, B=55)      # lock score at or above these is an A or a B; the rest are C

# --- locks per slate day (Edmonton time) and the recommended parlay ---
LOCKS_PER_SLATE = dict(single=3, multi=5)   # one game kicking off that day -> 3 locks; more games -> 5
PARLAY_LEGS = (2, 3)                        # fewest and most legs in the recommended parlay (fewer legs = better chance of hitting)
PARLAY_MIN_PROB = 0.60                      # a leg needs at least this blended chance of hitting
PARLAY_FALLBACK_PROB = 0.55                 # if too few legs clear that, legs down to this chance are allowed; below it, no parlay
PARLAY_KELLY_FRACTION = 0.25                # stake = this fraction of the Kelly stake for the parlay
PARLAY_UNITS = (0.1, 1.0)                   # stake bounds, in units
