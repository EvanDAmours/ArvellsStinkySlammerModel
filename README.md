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
| `pipeline/sources.py` | Loads nflverse data (free, updated nightly) with fallbacks and a self-check against official tackle totals |
| `pipeline/model.py` | Projections, stat crews for every stadium, the tackle distribution, and line pricing |
| `pipeline/backtest.py` | Walk-forward test of every predictor on every past game |
| `pipeline/odds.py` | Pulls tackle lines from The Odds API and stores timestamped snapshots |
| `pipeline/grade.py` | Logs picks and grades them against box scores and the closing line |
| `docs/` | The website (`index.html`) and the data it reads (`docs/data/*.json`) |
| `.github/workflows/` | The schedules: daily update, odds pulls, and tests on every code change |
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

All times are set for US daylight time (Eastern = UTC−4).

| Job | When (Eastern) | What it does |
| --- | --- | --- |
| Daily model update | Every day 7:30 am | New stats, backtest, projections, grading |
| Pull tackle lines | Thu 6:45 pm | Thursday night game |
| | Fri 6:00 pm | Full weekend slate |
| | Sun 9:00 am | Full slate |
| | Sun 11:50 am | 1 pm games, after inactives |
| | Sun 3:45 pm | Late games, after inactives |
| | Sun 7:35 pm, Mon 7:35 pm | Night games |

**When daylight time ends** (first Sunday in November), add one hour to every `cron` line in
`.github/workflows/odds.yml` and `daily.yml` (for example `50 15 * * 0` becomes `50 16 * * 0`),
or the Sunday pulls will run before inactives are announced. Reverse it in March.
GitHub can start scheduled jobs a few minutes late at busy times.

## Odds credits

Each pull costs 2 credits per game (two tackle markets, one region). The Friday and early-Sunday pulls
cover the whole slate (about 28 credits); later pulls only cover games starting within four hours.
That's roughly 90 credits a week, inside the free 500 per month. The site shows the balance after each pull,
and pulling stops automatically below 25. More pulls, or historical lines, need a paid plan.

You can add more keys: each secret named in `ODDS_KEY_ENV` in `config.py` (by default `ODDS_API_KEY` and
`PARLAY_API_KEY`) is treated as one pool of credits. Every key returns the same lines, so each game is
fetched once with whichever key has the most credits left, and a key that runs low is set aside until
its month resets. The site shows the pooled balance.

## Keeping it private

Odds providers' terms often restrict republishing their prices. A private repo plus a login
(Cloudflare Access, free) is the safe setup. Check The Odds API's terms before making anything public.

## Is the data right? The self-check

Tackles aren't an official NFL stat, and data sources label them differently. Every daily run compares
the totals it computes for a few players against verified official totals in `data/known_checks.json`.
If they don't match, the site shows a warning. Add more checks to that file over time (any player's
season total from Pro Football Reference works).

## Changing settings

Edit `config.py`. The most useful knobs:

- `PICK_BAR` and `SIGNAL_BAR`: minimum expected return for a pick, without and with a supporting signal.
- `FADE_GAP`: how far off his average a last game must be to count as an outlier.
- `SEASON` and `HISTORY_SEASONS`: update every year.

The backtest re-estimates the averaging weight and the spread of tackle counts every day,
so those adjust themselves.

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
