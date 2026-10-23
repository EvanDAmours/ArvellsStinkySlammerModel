"""Settings for the tackle-prop pipeline. Edit here, not in the code."""
SEASON = 2026                      # current season
HISTORY_SEASONS = [2023, 2024, 2025]   # used for priors, stat crews and the backtest

# --- odds feed (The Odds API) ---
ODDS_SPORT = "americanfootball_nfl"
ODDS_MARKETS = ["player_tackles_assists", "player_solo_tackles"]
ODDS_REGIONS = "us"
MIN_CREDITS_LEFT = 25              # stop pulling if the monthly credit balance drops below this

# --- model ---
SHRINK_GAMES = 1                   # weight (in games) of the prior when averaging; the backtest reports the best value
POS_PRIOR = {"LB": 6.0, "S": 4.5, "CB": 3.5, "DL": 2.5}       # tackles per game, used only with no history
POS_SOLO_SHARE = {"LB": 0.52, "S": 0.62, "CB": 0.72, "DL": 0.45}
SPREAD_TILT = 0.005                # +0.5% tackles per point a defense is an underdog (capped)
SPREAD_TILT_CAP = 0.05
CREW_PSEUDO_TACKLES = 250          # how hard each stadium's crew rate is pulled toward league average
ROLE_BUMP = 1.10                   # boost for a backup when a regular at his position group is inactive
DEFAULT_PHI = {"LB": 0.75, "S": 1.0, "CB": 1.0, "DL": 1.0}  # variance / mean; replaced by backtest estimates

# --- betting rules ---
PICK_BAR = 0.08                    # minimum expected return without a supporting signal
SIGNAL_BAR = 0.05                  # minimum with a role-change or outlier-fade signal
FADE_GAP = 3.0                     # last game this many tackles from his average counts as an outlier
MIN_GAMES_FOR_PICK = 3
