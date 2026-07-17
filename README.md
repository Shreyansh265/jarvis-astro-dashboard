# Jarvis — Mundane Astrology Trading Desk

A free, always-on dashboard that generates stock/sector signals from real
planetary positions (Swiss Ephemeris), backtests those signals against real
historical prices before trusting them, runs a $20,000 simulated paper
trading bot, and reviews its own accuracy every week — adjusting its rules
based on what actually happened.

**This is a systematic backtester for financial astrology, not investment
advice.** There's no established scientific evidence that planetary
positions move markets. The whole point of this system is intellectual
honesty about that: every signal is scored against its own historical
hit-rate so you can see exactly how reliable (or not) each rule has been,
instead of taking any prediction on faith.

## How it's built (100% free)

- **Frontend:** static HTML/JS on GitHub Pages
- **Backend jobs:** GitHub Actions (free on public repos) — no server to pay for
- **Astrology engine:** Swiss Ephemeris (`pyswisseph`), fully offline, no API key
- **Market data:** Twelve Data free tier (NYSE + TSX)
- **Database:** Supabase free tier (portfolio, predictions, trades, chat, learning weights)
- **Chat agent:** rule-based Q&A over your real logged data (no LLM, no per-message cost)

## One-time setup still needed

### 1. Add remaining GitHub secrets
Go to **Settings → Secrets and variables → Actions → New repository secret**
in this repo and add:

| Name | Where to get it |
|---|---|
| `TWELVE_DATA_API_KEY` | already set ✅ |
| `SUPABASE_URL` | already set ✅ |
| `SUPABASE_SERVICE_KEY` | **Still needed.** Supabase dashboard → Project Settings → API → `service_role` key (NOT the anon key). This lets the GitHub Actions jobs write data. Keep it secret — never put it in any file in this repo, only in GitHub Secrets. |

*(Note: I wasn't able to set `TWELVE_DATA_API_KEY`/`SUPABASE_URL` via the API — the
token's permissions didn't include repo Secrets. Please add all three above manually,
it takes under a minute.)*

### 2. Run the database schema
Supabase dashboard → SQL Editor → New query → paste the contents of
`supabase/schema.sql` → Run.

### 3. Enable GitHub Pages
Settings → Pages → confirm source is "GitHub Actions" (should auto-detect
once the `Deploy Dashboard to GitHub Pages` workflow runs once). Your
dashboard will be live at `https://shreyansh265.github.io/jarvis-astro-dashboard/`.

### 4. Kick off the first runs manually
Go to the **Actions** tab → run each workflow once by hand (▶ "Run workflow"):
1. `Deploy Dashboard to GitHub Pages`
2. `Daily Astro Signals + Paper Trading` — populates your first signals/trades
3. `Weekly Review + Learning` — has no effect until there's a week of history, but confirms the job works

After that, everything runs on its own:
- **Daily**, ~9:35am ET on market days: new signals, prediction logging, paper trading
- **Weekly**, Sunday: reviews last week's predictions against actual outcomes, adjusts rule weights, logs lessons

## Repo structure

```
engine/            Python: astrology engine, backtester, paper trader, weekly review
  rulerships.py     The declared astrology rule set (planet -> sector mappings)
  ephemeris.py      Real planetary position calculations
  signals.py        Turns positions into bullish/bearish sector signals + confidence
  backtest.py        Tests rules against real historical prices (run manually, see below)
  paper_trader.py    $20k simulated trading bot
  weekly_review.py  Self-correction: checks outcomes, adjusts rule weights
  main_daily.py / main_weekly.py   entry points GitHub Actions calls
web/                Static dashboard (GitHub Pages)
supabase/schema.sql Database schema + row-level security
.github/workflows/  The three automations
```

## Running a backtest yourself (optional, recommended once)

The rule weights start at a neutral 0.5 prior for every planet. To seed them
with real historical hit-rates before the weekly auto-learning kicks in:

```bash
cd engine
pip install -r requirements.txt
export TWELVE_DATA_API_KEY=...   # your key
python backtest.py
```

This prints a hit-rate per planet/sector rule over the last year. You can
manually insert the suggested starting weights into the `rule_weights` table
in Supabase if you want the system calibrated from day one instead of
learning purely from scratch.

## Security notes

- The Supabase **anon key** in `web/config.js` is meant to be public — it's
  restricted by Row Level Security to only read data and write to
  `portfolio`/`chat_log`. The **service_role key** (used by GitHub Actions
  only, via secrets) is what can write predictions/trades/reviews, and must
  never be committed to the repo.
- Consider rotating your Twelve Data key and GitHub token periodically since
  early versions were shared in plain chat during setup.
