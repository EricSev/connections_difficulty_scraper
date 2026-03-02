# connections_difficulty_scraper
Runs daily and scrapes the NYT Connections Difficulty Rating.

## Usage Examples

```bash
# Collect today's difficulty score
python connections_scraper.py

# Collect data for a specific date
python connections_scraper.py --date 2025-02-15

# Collect with retries (try 3 times, wait 2 hours between attempts)
python connections_scraper.py --retries 3 --retry-delay 7200

# Collect using a proxy
python connections_scraper.py --proxy http://user:pass@proxy.example.com:8000

# Collect historical data with custom parameters
python connections_scraper.py --historical --start-date 2024-01-01 --end-date 2024-06-30 --delay 3 --batch-size 5 --cooldown 120

# Generate JSON files from existing CSV data
python connections_scraper.py --generate-json

# Add day and month columns to existing CSV files
python connections_scraper.py --migrate

# Enable debug logging
python connections_scraper.py --debug

# Use a custom user agent
python connections_scraper.py --user-agent "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Save HTML content when collection fails for debugging
python connections_scraper.py --date 2024-12-25 --save-html
```

## Command-Line Arguments

### Collection Modes

| Argument | Type | Description |
|---|---|---|
| *(no args)* | — | Collect today's difficulty score (daily mode) |
| `--date DATE` | `str` | Collect score for a specific date (`YYYY-MM-DD` format) |
| `--historical` | flag | Collect historical scores over a date range |
| `--generate-json` | flag | Generate JSON files from existing CSV data |
| `--migrate` | flag | Migrate existing CSV files to include `day`, `month`, and `puzzle_date` columns |

### Retry Options (Daily Mode)

| Argument | Type | Default | Description |
|---|---|---|---|
| `--retries` | `int` | `1` | Number of attempts for daily collection. Set to `1` for no retry. |
| `--retry-delay` | `int` | `7200` | Seconds to wait between retry attempts (default 2 hours) |

### Proxy Options

| Argument | Type | Default | Description |
|---|---|---|---|
| `--proxy` | `str` | — | Proxy URL for requests. Overrides the `APIFY_PROXY_PASSWORD` env var. Example: `http://user:pass@proxy.example.com:8000` |

If `--proxy` is not provided, the scraper checks for the `APIFY_PROXY_PASSWORD` environment variable and builds an Apify proxy URL automatically. If neither is set, requests are made directly.

### Historical Mode Options

| Argument | Type | Default | Description |
|---|---|---|---|
| `--start-date` | `str` | `2023-01-01` | Start date for historical collection (`YYYY-MM-DD` format) |
| `--end-date` | `str` | today | End date for historical collection (`YYYY-MM-DD` format) |
| `--delay` | `float` | `2.0` | Base delay in seconds between requests |
| `--no-jitter` | flag | — | Disable random timing jitter between requests |
| `--batch-size` | `int` | `10` | Number of requests before taking a longer cooldown break |
| `--cooldown` | `int` | `60` | Seconds to pause after each batch |

### Debugging Options

| Argument | Type | Description |
|---|---|---|
| `--debug` | flag | Enable verbose debug logging |
| `--save-html` | flag | Save HTML content to `debug_DATE.html` when collection fails (use with `--date`) |
| `--user-agent` | `str` | Custom user agent string for requests |

## Environment Variables

| Variable | Description |
|---|---|
| `APIFY_PROXY_PASSWORD` | Apify proxy password. When set, requests are routed through `http://auto:<password>@proxy.apify.com:8000`. Overridden by `--proxy`. |

## Data Outputs

| File | Description |
|---|---|
| `data/connections_difficulty_history.csv` | Full history of all collected scores |
| `data/connections_difficulty_history.json` | JSON version of full history (published to GitHub Pages) |
| `data/connections_difficulty_daily.csv` | Scores collected via daily mode |
| `data/connections_difficulty_data_latest.json` | Most recent single puzzle entry |
| `data/connections_difficulty_four_day.json` | Rolling 4-day window |
| `data/connections_difficulty_four_day.csv` | CSV version of 4-day window |

![image](https://github.com/user-attachments/assets/59ac42c7-f359-4fce-b639-61b306eaa907)
