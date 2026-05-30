# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A single-file Python scraper that collects the NYT Connections daily difficulty
rating ("Today's difficulty is X out of 5") from the NYT "Connections Companion"
editorial pages, stores it as CSV, and derives several JSON/CSV views. It runs
daily via GitHub Actions, commits new data, and publishes the history JSON to
GitHub Pages.

All logic lives in `connections_scraper.py`. There is no package structure, no
test suite, and no build step.

## Commands

```bash
pip install -r requirements.txt        # install deps (requests, beautifulsoup4, python-dotenv)

python connections_scraper.py                       # daily mode: scrape today, append to daily + history
python connections_scraper.py --date 2025-02-15     # scrape one date, append to history only
python connections_scraper.py --historical --start-date 2024-01-01 --end-date 2024-06-30
python connections_scraper.py --generate-json       # rebuild all JSON files from existing CSVs
python connections_scraper.py --migrate             # backfill day/month/puzzle_date columns into CSVs
python connections_scraper.py --regenerate-four-day # rebuild only the 4-day window files
python connections_scraper.py --debug --date 2024-12-25 --save-html   # debug a failing scrape
```

See `README.md` for the full argument reference (retry, proxy, rate-limiting flags).

## Key domain concepts

These two points are non-obvious and drive most of the logic — read them before
changing date or URL handling:

- **Companion date vs. puzzle date.** The script scrapes the NYT *Companion*
  article, which is published the evening *before* the puzzle it discusses. So
  `date` in the data = the companion/scrape date, and `puzzle_date` = `date + 1
  day`. The `day` and `month` columns are derived from `puzzle_date`, **not**
  `date`. Keep this offset consistent anywhere dates are computed.

- **Puzzle number is calculated, not scraped.** `get_puzzle_number_for_date()`
  anchors on a hardcoded reference point (March 9, 2025 = puzzle #638) and adds
  the day delta. The Companion URL is built from this number, so if NYT ever
  skips/renumbers puzzles this anchor must be corrected.

## Architecture & data flow

The core write path is `save_score_to_csv()`. Understanding its cascade is the
key to the codebase:

1. **Scrape** — `scrape_difficulty_score(url)` fetches the Companion page and
   runs a waterfall of regex patterns (over `<strong>`/`<b>`, then `<p>`, then
   whole-document text, then a loose "X out of Y" sentence search). It returns
   `(difficulty_score, max_score)` or `(None, None)` on failure. Failures never
   raise — they log and return `None`, which callers treat as "no puzzle / try
   again".

2. **Persist + dedupe** — `save_score_to_csv()` appends a row but first checks
   for an existing entry by matching either the date (parsed across multiple
   formats) *or* the puzzle number, so re-runs are idempotent.

3. **Derive JSON (cascade)** — writing a CSV row triggers regeneration of the
   JSON views. The functions are layered and depend on each other's outputs:
   - `update_json_latest()` / `update_json_latest_from_csv()` → `connections_difficulty_data_latest.json` (single most-recent puzzle).
   - `update_json_history()` reads the **history CSV** → `connections_difficulty_history.json` (all puzzles, sorted newest-first).
   - `update_json_four_days()` reads the **history JSON** (not the CSV) → `connections_difficulty_four_day.{json,csv}` (top 4 entries). It must run *after* `update_json_history()`.

   Because of these dependencies, daily mode writes the **daily CSV first, then
   the history CSV** — the four-day update keys off the history file, which
   isn't populated until the second write.

### Files

| Path | Role |
|---|---|
| `connections_scraper.py` | Everything: scraping, CSV/JSON I/O, CLI. |
| `data/connections_difficulty_history.csv` | Source of truth — full history. |
| `data/connections_difficulty_daily.csv` | Rows added via daily mode only. |
| `data/*.json` | Derived views; regenerated from CSV, not hand-edited. |
| `.github/workflows/daily-run.yml` | Cron (18:00 UTC) → run scraper → commit `data/`. |
| `.github/workflows/publish-data.yml` | On push to `main` touching the history JSON → deploy to GitHub Pages. |

CSV schema (all files): `date, puzzle_date, day, month, puzzle_number, difficulty_score, max_score`.
Note CSVs may contain mixed date formats (`YYYY-MM-DD` and `M/D/YYYY`); the
read paths parse multiple formats defensively — preserve that tolerance.

## Conventions

- **Date format for JSON output** uses `strftime("%-m/%-d/%Y")` (no leading
  zeros), with a Windows fallback that strips zeros manually. Keep both branches
  when touching date formatting.
- **Proxy**: requests route through Apify when `APIFY_PROXY_PASSWORD` is set
  (or `--proxy` is passed). CI passes this as a secret. Local runs work without
  it (direct connection).
- **Rate limiting** in historical mode is deliberate (jitter, batch cooldowns,
  consecutive-failure backoff) to avoid IP bans — don't strip it when modifying
  historical collection.
- Editing `data/` files by hand is almost always wrong: change the CSV via the
  script (or `--migrate`) and regenerate JSON with `--generate-json`.
