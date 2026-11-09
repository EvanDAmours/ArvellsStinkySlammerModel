"""Settings for the tackle-prop pipeline. Edit here, not in the code."""
SEASON = 2026                      # current season
HISTORY_SEASONS = [2023, 2024, 2025]   # used for priors, stat crews and the backtest

# --- odds feed (The Odds API) ---
ODDS_SPORT = "americanfootball_nfl"
ODDS_MARKETS = ["player_tackles_assists", "player_solo_tackles", "player_assists"]   # assists added 2026-11-03 (scoping, research round 8): +1 credit per game
ASSIST_MARKET = "player_assists"
LOCK_MARKETS = ("player_solo_tackles",)   # assists are tracked as theoretical picks: never a lock or a parlay leg until their record earns it.
# Combined tackles left the locks 2026-11-08 night: its picks claimed 57% and hit 48% over weeks 7-9 (177 picks, 2.4 SE), its A picks went 1-3
A_GRADE_MARKETS = ("player_solo_tackles",)  # an A grade only in these markets; a combined pick that scores 72+ shows as a B until 40 further combined picks hit their claim
# Sleepers (2026-11-08 night): lines where the model's own number, before any blend with the line, disagrees with the book by a margin that
# held in every live week. Blind board at the close, weeks 7-9: combined Overs with the model 0.5 to 1.5 above the line 48-25 (66%, +18%,
# 14-11 / 23-8 / 11-6); solo Unders with the model 0.5+ below the line 60-22 (73%, +23%, 21-8 / 25-3 / 14-11). The pick bars hide most of the
# combined ones (an Over needs a 10% return and a 55% claim after shrinking). Tracked as theoretical picks on their own record, never a lock.
# min_ev None: no price filter. Re-priced through the pipeline, the combined band went 35-21 (+14%/bet) at every price but 7-10 where the
# pricer (which leans on the line) also called the Over +EV; the rule was found on the model's number alone and is kept that way.
SLEEPER = dict(comb_over=(0.5, 1.5), solo_under=-0.5, min_ev=None, review_after=40, review_hit=0.55)


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

# --- pricing: how much to trust the market ---
# The posted line is itself a forecast, and in week 7 of 2026 it predicted tackles better than the raw projection
# (actual = 0.44 x projection + 0.60 x line). The mean used for pricing is a blend of the two.
LINE_WEIGHT = 0.5                  # default weight on the consensus line (0 = pure model, 1 = pure market); the live weight per market is
                                   # estimated from closing-line errors (BLEND below) and shrunk toward this
# Per-market blend, estimated from graded weeks' closing lines (pipeline/blend.py): the line's weight is the
# inverse-variance weight mse_model / (mse_model + mse_line), and both the line and the model get a level correction
# (their average error against the box score), each shrunk by n / (n + k) lines. Weeks 7-8 of 2026: the solo line
# ran 0.3-0.5 high and the model 0.2-0.4 high; correcting both cut the solo error 3% on each held-out week.
BLEND = dict(k=100, max_bias=1.0, min_lines=30)
PROB_SHRINK = 1.0                  # 1 = use the blended model probability as is; <1 pulls it further toward the market's no-vig probability

# --- betting rules ---
PICK_BAR = 0.06                    # minimum expected return without a supporting signal
PICK_BAR_OVER = 0.10               # an Over needs more: the model's Over leans hit 32-46% on weeks 7-8 lines where it was above the market (audit 2026-10-30)
SIGNAL_BAR = 0.06                  # a signal no longer lowers the bar: the 12 live picks taken at 4-6% went 3-9 (-6.5 u) on weeks 7-8
# A pick also needs a claimed chance (shrunk, segment-corrected) of at least this. Live weeks 7-8: the 108 picks claimed
# under 55% went 44-64 (-6.1 u) in both weeks; the rest 57% and +33 u. A plus-money side with a 50% claim is a coin flip.
PICK_MIN_CLAIM = 0.55
# Claimed edge (2026-11-09 post-mortem): the return at our own claimed chance, claim x decimal odds - 1. The return bars above use the
# pricer's probability, which shrinks less than the claim, so a pick could clear 6% there while its claimed chance did not beat the price:
# weeks 8-9, claimed edge under 0: 12-20 (-34%/bet), 0-4%: 14-11 (-2%), 4-15%: 57-36 (+11%). A picks at 4%+ went 13-2, under 4% 6-6
# (week 9: six of its eight A losses had a claimed chance at or below the price's). Thresholds from 2% to 6% all give A 83-90%.
PICK_MIN_CLAIM_EV = 0.02           # a pick must beat its price by 2% at the claimed chance
A_MIN_CLAIM_EV = 0.04              # an A (and so a lock) by 4%; a 72+ score below that shows as a B
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
GRADE_UNITS = dict(A=1.0, B=0.5, C=0.25)   # the grade ladder, kept for the record's "units at grade stake"; the stake on a pick is STAKE below
# Stake per pick: a quarter of the Kelly fraction of a 100-unit bankroll from the pick's claimed chance and price,
# clipped, with at most game_cap units on one game (stakes in that game scaled down together). Research round 9,
# weeks 7-8 at the same total staked: +21.2 u against +18.1 for the grade ladder and +10.8 flat, better in both
# weeks, and the most on one game 5.4 u against 10.8.
STAKE = dict(bankroll=100.0, kelly_fraction=0.25, min=0.25, max=3.0, game_cap=4.0)
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
# A lock is a pick the model strongly believes in, never "the best of a thin board" (owner, 2026-11-02). It needs an
# A-grade score; a slate with no A has no lock. Live: locks at 72+ went 5-1, locks at 55-72 went 2-1 on three picks.
LOCK_MIN_SCORE = GRADE_BARS["A"]
PARLAY_LEGS = (2, 3)                        # fewest and most legs in the recommended parlay (fewer legs = better chance of hitting)
# Legs on one defence share the plays it faces (sd 7.6 around expectation): two Unders rise or fall together, an
# Under and an Over pull apart. The parlay's chance is the product of the legs' claimed chances times the ratio a
# simulation with a shared plays draw gives over independence (weeks 7-8: 1.05 for two Unders, 0.94 for an
# Under and an Over, 1.10 for three Unders). Research round 9.
PARLAY_CORR = dict(sd_plays=7.6, sims=20000, phi_floor=0.55, clip=(0.8, 1.3))
PARLAY_MARKETS = ("player_tackles_assists",)  # combined tackles only: the books refuse solo-tackle legs in a same-game parlay (owner, 2026-11-02)
PARLAY_MIN_PROB = 0.56                      # a leg needs at least this claimed (shrunk) chance of hitting: 0.60 before the claim shrink
PARLAY_FALLBACK_PROB = 0.53                 # if too few legs clear that, legs down to this chance are allowed; below it, no parlay
PARLAY_KELLY_FRACTION = 0.25                # stake = this fraction of the Kelly stake for the parlay
PARLAY_UNITS = (0.1, 1.0)                   # stake bounds, in units

# Trade watch (pipeline/watch.py): the owner is notified (a GitHub issue that mentions them, so GitHub emails and
# pushes) the first time a trade appears on the team's ESPN transaction wire. On every ticker beat until `until`.
TRADE_WATCH = dict(team="NYG", espn_team_id=19, notify="EvanDAmours", until="2026-11-11T06:00:00+00:00")   # deadline: Tue 2026-11-10, 4 pm ET
