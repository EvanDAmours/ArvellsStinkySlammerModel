# Tackle board

An automatic NFL tackle-prop model. Every day it downloads fresh stats, reruns a multi-season
backtest and the projections, and grades past picks. On game days it pulls tackle lines from
every US sportsbook, prices them, and logs any picks. A small website shows the results.

Everything runs on GitHub's servers on a schedule. You don't run anything by hand.

## What's inside

| Path | What it is |
| --- | --- |
| `run.py` | Entry point: `python run.py daily` and `python run.py odds --auto` |
| `config.py` | Every setting (seasons, betting thresholds, model knobs) in one place |
| `pipeline/sources.py` | Loads nflverse data (player stats, snaps, schedule, injuries, team stats, play-by-play, depth charts, PFR advanced defence incl. pressures) with fallbacks and a self-check against official tackle totals; ESPN's injury feed (suspensions, injured reserve) merged with the league report; FantasyPros expert-consensus tackle projections as a cross-check |
| `pipeline/model.py` | Projections: a per-game base and a per-snap base (tackles per snap x expected snap share x expected team snaps) blended, the vacancy rule, stat crews, opportunity volume, depth chart, PFR, run/pass mix, rest, injury report, dome corners; a gradient-boosted second model blended in; the tackle distribution (by position and snap share); line pricing and grading |
| `pipeline/backtest.py` | Walk-forward test of every predictor on every past game |
| `pipeline/odds.py` | Pulls tackle lines from The Odds API and stores timestamped snapshots |
| `pipeline/grade.py` | Logs picks and grades them against box scores and the closing line |
| `docs/` | The website (`index.html`) and the data it reads (`docs/data/*.json`) |
| `.github/workflows/` | The schedules: daily update, odds pulls, tests on every code change, and the keepalive that re-enables schedules |
| `tests/` | A synthetic league with known effects, and an end-to-end test |

## One-time setup (about 30 minutes)

1. **Get an odds key.** Sign up for the free plan at the-odds-api.com. Copy your API key.
2. **Create the repo.** On github.com, click *New repository*. Private is recommended (see *Keeping it private*).
3. **Upload the files.** The easiest way is GitHub Desktop: clone the empty repo, copy every file from this folder into it (including the hidden `.github` folder), then commit and push.
   If you upload in the browser instead, hidden folders are often skipped. Check that `.github/workflows/` exists afterwards; if not, use *Add file → Create new file*, type `.github/workflows/daily.yml` as the name, and paste the file's contents. Repeat for `odds.yml` and `test.yml`.
4. **Add the key as a secret.** *Settings → Secrets and variables → Actions → New repository secret*. Name: `ODDS_API_KEY`. Value: your key. It is never visible on the website or in the code.
   It has to be an *Actions* secret: a *Codespaces* secret with the same name is a separate store that the scheduled jobs cannot read.
5. **Let the jobs save their results.** *Settings → Actions → General → Workflow permissions →* choose *Read and write permissions*.
6. **Run it once.** *Actions* tab → *Daily model update* → *Run workflow*. It takes a few minutes. Open the run and look for the line starting `daily:`. Then run *Pull tackle lines* once the same way (it only finds lines when books have posted them, usually Thursday to Saturday).
7. **Turn on the website.**
   - Public repo: *Settings → Pages →* Source: *Deploy from a branch*, branch `main`, folder `/docs`. Your site appears at the address shown there.
   - Private repo: on a free GitHub account, Pages only serves public repos. Use Cloudflare Pages instead (free): connect your GitHub account, pick the repo, leave the build command empty, set the output directory to `docs`. Add Cloudflare Access if you want a login.

## When things run

Pull slots are in **Edmonton time** (Alberta Time, UTC-6 all year from November 2026; the job converts from the
zone data and pins UTC-6 if that data is stale, so nothing needs editing). The pull job runs every quarter hour and serves each slot once; a pull costs 1-3 odds credits per game (0 when no line is up).

| Job | When (Edmonton) | What it does |
| --- | --- | --- |
| Daily model update (with a fallback run 85 minutes later that does nothing when the first succeeded) | Every day, early morning | New stats, backtest, projections, grading, parlay grading |
| Pull tackle lines | Any day, 1 h before every kickoff (kickoffs within 30 min share one pull) | Every game not yet started that day, from the schedule: Thursday, Friday, Saturday, Sunday and Monday games alike, holiday games included |
| | Thu 9:00 am, 1:00 pm | Thursday game, and Friday games on holiday weeks |
| | Sat 8:00 pm | Saturday and Sunday games, once the books have posted the slate (most Sunday tackle lines go up Saturday evening) |
| | Sun 10:00 am | The Sunday slate with the inactives known (on a normal week this is also the pre-kickoff pull, so one pull) |
| | Mon 9:00 am, 1:00 pm | The Monday game |
| | Mon, every two hours 9:00 am-5:00 pm and 5:30 pm | Monday game |
| | 12 h and 1 h before kickoff | Any international game (neutral-site game overseas), that game only |

Locks and the recommended parlay for a slate day are re-chosen at every pull until the day's first kickoff.
GitHub can start scheduled jobs late at busy times; a slot is served by the first run after its time, so a late run still pulls once.

## Keeping it running with no hands on

GitHub switches off every scheduled workflow in a public repository after 60 days without a push. Three things
keep this site alive on their own:

1. The daily job commits a run log (`data/cache/last_run.txt`) every day, even when the update itself failed
   (a failed run leaves yesterday's site in place and commits only the log line). A push a day means the repo is
   never inactive, in season or out.
2. Each job switches the other's schedule back on: the daily job re-enables the line pulls, and a pull that found
   lines re-enables the daily job. A workflow that was turned off, for whatever reason, comes back within a day.
3. `keepalive.yml` runs on every push by a person and re-enables both schedules. If both were ever off at once,
   the next commit anyone pushes brings them back, with no button to click.

Schedules only run on the default branch, so keep the branch the site deploys from as the default.

## Assists (trial market)

The Assists tab prices the book's assists lines from the combined projection less the solo one, with the same
bars, grades, checklist and slip links as the tackle board. Assists picks are logged and graded like any pick but
are never locks or parlay legs. To replay a finished week the market was not pulled live for, run the manual
workflow "Fetch past lines for a market" (10 credits a game per market, ten times a live pull), then
`python tools/replay_five.py --week N --markets player_assists --out data/retro_assists.json --all-picks` and
commit the result; the next daily run shows it on the tab.

## Odds credits

Each pull costs 3 credits per game (two tackle markets and the assists market, one region; 2 before the assists market was added on 2026-11-03). A whole-slate pull (Saturday
evening, Sunday morning) costs about 36 credits; the later looks only cover games not yet kicked off. The schedule above
spends about 105 credits a week (Thursday 9, Saturday 36, Sunday 51, Monday 9), about 450 a month, inside one free
500-credit key with a margin for international games. Before 2026-11-03 the Saturday hourly pulls alone cost 68 a week. The site shows the balance after each pull,
and pulling stops automatically below 25. More pulls, or historical lines, need a paid plan.

You can add more keys: each secret named in `ODDS_KEY_ENV` in `config.py` (by default `ODDS_API_KEY` and
`PARLAY_API_KEY`) is treated as one pool of credits, used in that order. Every key returns the same lines, so
each game is fetched once with the first key that still has credits, and the next key takes over when it runs
low. The site shows the pooled balance.

## Keeping it private

Set an Actions secret named `SITE_PASSWORDS` (Settings, Secrets and variables, Actions) with one line per person,
`name: password` (the name is only a label; a line of just a password works too). A single `SITE_PASSWORD` secret
also works. Any of the passwords opens the site; delete a line to shut one person out at the next run; change a
password to make that person enter the new one. From the next run, every
data file the site reads is encrypted with it before it is published (AES-256-GCM, key from the password), the
plaintext is deleted, and the page asks for the password once per device and decrypts in the browser. Give the
password to the people who should see the board; change the secret to lock everyone out at the next run. Without
the secret the site stays open.

That protects the published site only. The repository itself is public: `data/picks.csv`, the odds snapshots and
the projections are readable on GitHub by anyone. To close that too, make the repository private (Settings,
General, Danger Zone); GitHub Pages keeps publishing from a private repository on a paid personal plan (Pro).
Odds providers' terms often restrict republishing their prices, so a private repository is the right setting
either way.

## Is the data right? The self-check

Tackles aren't an official NFL stat, and data sources label them differently. Every daily run compares
the totals it computes for a few players against verified official totals in `data/known_checks.json`.
If they don't match, the site shows a warning. Add more checks to that file over time (any player's
season total from Pro Football Reference works).

## Confidence grades

Every priced line gets a lock score (0-100) and a grade: **A** (72+), **B** (55+) or **C**. The score blends the
expected return, the model's own probability for the side, how often the player has cleared the line this season,
and how many games of data he has; a role-change or outlier-fade signal adds a bonus. Nothing in the score comes
from the market agreeing with the pick: the edge is what the market has not priced. Weights are in `config.py`.
The records bar on both tabs shows the A, B and C records, and the Track record tab has a full "Record by grade"
block (hit rate, units, return per bet, units at the suggested stake), so the grade itself is tested: if A does
not beat C over time, the weights are wrong. A lock-eligibility checklist, computed without any reference to the market, keeps locks and
parlay legs to players the model is reliable on: never a lock when he is in a new role (a part-timer who just
played a starter's snaps), a reduced role, back from an absence, in his first game for a new team, has fewer than
three games in his current role, or is listed questionable. Each reason is tagged on the card; the pick can still be
played at its grade. The Model check tab's "Where the model is weakest" table watches these situations daily.

## The model log

`MODEL_LOG.md` is the project's memory: every change with its evidence, weekly post-mortems, ideas tried and
rejected, and pitfalls. Read it before changing anything and append to it after.

## Changing settings

Edit `config.py`. The most useful knobs:

- `LINE_WEIGHT`: how far the pricing mean leans toward the posted line (0 = pure model, 1 = pure market).
- `PICK_BAR` and `SIGNAL_BAR`: minimum expected return for a pick, without and with a supporting signal.
- `LOCK_WEIGHTS` and `GRADE_BARS`: the confidence grade.
- `FADE_GAP`: how far off his average a last game must be to count as an outlier.
- `SEASON` and `HISTORY_SEASONS`: update every year.

- `PERSNAP`: the per-snap base. `weight` is how much of the core projection comes from it (0.4).
- `VACANCY`: the rule for a backup stepping into a vacated starter's role; `weight` is how far the projection moves
  to his last-game share (0.5).
- `GBM`: the second model. `weight` is how much of the final projection comes from the gradient-boosted
  corrector (0.6); the rest is the factor model.

The backtest re-estimates the averaging weight, the level calibration and the spread of tackle counts every day,
and retrains the second model on every finished game, so those adjust themselves. The backtest table reports the
second model walk-forward (trained on earlier seasons, scored on the latest) so its gain is never measured on
games it was trained on. `scikit-learn` is required for it; without it the factor model runs alone.

## Testing on your own computer

```
pip install -r requirements.txt
python tests/smoke_test.py                       # synthetic league, no internet needed
TACKLE_FAKE_DATA=1 TACKLE_FAKE_ODDS=1 python run.py daily && python run.py odds   # try the site with fake data
python -m http.server --directory docs 8000      # then open http://localhost:8000
```

The test also runs automatically on GitHub whenever the code changes.

## How to judge it

Give it a few hundred logged picks before trusting the win-loss record. The earlier signal is the
*Beat the closing line* figure on the Track record tab: consistently getting a better number than the
final market price is the most reliable sign of a real edge. If it hovers at or below 50%, the model
isn't finding one, whatever the short-term record says.
