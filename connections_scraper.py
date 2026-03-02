import requests
from bs4 import BeautifulSoup
import re
import csv
import os
import json
import random
import time
from datetime import datetime, timedelta, date
import logging
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("connections_scraper.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Paths
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / "data"
HISTORY_FILE = DATA_DIR / "connections_difficulty_history.csv"
DAILY_FILE = DATA_DIR / "connections_difficulty_daily.csv"
# New JSON output files
LATEST_JSON = DATA_DIR / "connections_difficulty_data_latest.json"
HISTORY_JSON = DATA_DIR / "connections_difficulty_history.json"
FOUR_DAY_JSON = DATA_DIR / "connections_difficulty_four_day.json"
FOUR_DAY_CSV = DATA_DIR / "connections_difficulty_four_day.csv"

# Ensure data directory exists
DATA_DIR.mkdir(exist_ok=True)

# User agent for more reliable requests
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

# Proxy configuration -- set from environment or CLI argument
PROXY_URL = None


def _build_proxy_url():
    """Build proxy URL from APIFY_PROXY_PASSWORD environment variable, if set."""
    password = os.environ.get("APIFY_PROXY_PASSWORD")
    if password:
        return f"http://auto:{password}@proxy.apify.com:8000"
    return None


def get_random_user_agent():
    """Return a random user agent string to rotate between requests."""
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (iPad; CPU OS 17_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Mobile/15E148 Safari/604.1",
    ]
    return random.choice(user_agents)


def get_puzzle_number_for_date(target_date):
    """
    Calculate the puzzle number for a given date.

    This is based on the fact that puzzle #638 is for March 9, 2025.
    The puzzle numbers increment by 1 each day.
    """
    # Known reference point: March 9, 2025 is puzzle #638
    reference_date = date(2025, 3, 9)
    reference_puzzle = 638

    # Calculate the difference in days
    day_difference = (target_date - reference_date).days

    # Calculate the puzzle number
    puzzle_number = reference_puzzle + day_difference

    return puzzle_number


def get_companion_url_for_date(target_date):
    """Generate the URL for the Connections Companion for a specific date."""
    # Format: https://www.nytimes.com/YYYY/MM/DD/crosswords/connections-companion-XXX.html
    year = target_date.year
    month = target_date.month
    day = target_date.day

    # Format the date parts with leading zeros
    month_str = f"{month:02d}"
    day_str = f"{day:02d}"

    # Calculate the puzzle number
    puzzle_number = get_puzzle_number_for_date(target_date)

    url = f"https://www.nytimes.com/{year}/{month_str}/{day_str}/crosswords/connections-companion-{puzzle_number}.html"
    return url


def scrape_difficulty_score(url, rotate_user_agent=True):
    """Scrape difficulty score from a given URL."""
    try:
        # For debugging purposes, print the URL we're trying to access
        logger.info(f"Requesting URL: {url}")

        # Create a copy of headers so we don't modify the global one
        headers = HEADERS.copy()

        # Rotate user agent if enabled
        if rotate_user_agent:
            headers["User-Agent"] = get_random_user_agent()
            logger.debug(f"Using user agent: {headers['User-Agent']}")

        # Add some randomness to request parameters to mimic human behavior
        # Sometimes browsers include a referer
        if random.random() < 0.7:  # 70% of the time
            headers["Referer"] = "https://www.nytimes.com/crosswords"

        # Build proxies dict if a proxy URL is configured
        proxies = None
        if PROXY_URL:
            proxies = {"http": PROXY_URL, "https": PROXY_URL}
            logger.debug(f"Using proxy: {PROXY_URL.split('@')[1] if '@' in PROXY_URL else PROXY_URL}")

        response = requests.get(url, headers=headers, timeout=30, proxies=proxies)
        response.raise_for_status()

        # Save HTML content for debugging (uncomment if needed)
        # with open("debug_page.html", "w", encoding="utf-8") as f:
        #     f.write(response.text)

        soup = BeautifulSoup(response.text, "html.parser")

        # Try different methods to find the difficulty text

        # Method 1: Look for exact text pattern about difficulty
        patterns = [
            r"Today's difficulty is (\d+(?:\.\d+)?) out of (\d+)",
            r"difficulty is (\d+(?:\.\d+)?) out of (\d+)",
            r"difficulty rating of (\d+(?:\.\d+)?) out of (\d+)",
            r"difficulty.*?(\d+(?:\.\d+)?).*?out of (\d+)",
            r".*?(\d+(?:\.\d+)?) out of 5\.",  # More relaxed pattern to catch variants
        ]

        # First, check for strong tags with difficulty info
        for strong in soup.find_all(["strong", "b"]):
            if strong and strong.string:
                for pattern in patterns:
                    match = re.search(pattern, strong.string)
                    if match:
                        logger.info(f"Found difficulty in strong tag: {strong.string}")
                        return float(match.group(1)), int(
                            match.group(2) if len(match.groups()) > 1 else 5
                        )

        # Check all paragraphs for the pattern
        for p in soup.find_all("p"):
            if p and p.text:
                for pattern in patterns:
                    match = re.search(pattern, p.text)
                    if match:
                        logger.info(f"Found difficulty in paragraph: {p.text}")
                        return float(match.group(1)), int(
                            match.group(2) if len(match.groups()) > 1 else 5
                        )

                # Log paragraphs that mention difficulty for debugging
                if "difficulty" in p.text.lower():
                    logger.info(
                        f"Found paragraph with possible difficulty info: {p.text}"
                    )

        # Method 3: Check the entire document for the pattern
        for pattern in patterns:
            match = re.search(pattern, soup.text)
            if match:
                logger.info(
                    f"Found difficulty in document text with pattern '{pattern}': {match.group(0)}"
                )
                return float(match.group(1)), int(
                    match.group(2) if len(match.groups()) > 1 else 5
                )

        # Method 4: Print paragraphs for debugging to identify where the difficulty info might be
        if logger.level <= logging.DEBUG:
            logger.debug("Printing all paragraph texts for debugging:")
            for i, p in enumerate(soup.find_all("p")):
                logger.debug(f"Paragraph {i}: {p.text.strip()}")

        # Try a direct search for "Today's difficulty is X out of 5"
        direct_search = re.search(
            r"Today's difficulty is (\d+(?:\.\d+)?) out of (\d+)", response.text
        )
        if direct_search:
            return float(direct_search.group(1)), int(direct_search.group(2))

        # Even more general search for "difficulty is X out of Y"
        general_search = re.search(
            r"difficulty is (\d+(?:\.\d+)?) out of (\d+)", response.text
        )
        if general_search:
            return float(general_search.group(1)), int(general_search.group(2))

        # Method 5: Find any sentence containing both numerical values and "out of"
        text_blocks = [p.text for p in soup.find_all("p")]
        for block in text_blocks:
            sentences = re.split(r"[.!?]\s+", block)
            for sentence in sentences:
                if "out of" in sentence and re.search(r"\d+(?:\.\d+)?", sentence):
                    logger.info(f"Found potential difficulty sentence: {sentence}")
                    # Extract the first number and the number after "out of"
                    numbers = re.findall(r"\d+(?:\.\d+)?", sentence)
                    if len(numbers) >= 2:
                        return float(numbers[0]), int(float(numbers[1]))

        # If we get here, we couldn't find the difficulty score
        logger.error(f"Could not find difficulty score in {url}")
        return None, None

    except Exception as e:
        logger.error(f"Error scraping {url}: {e}")
        return None, None


def update_json_latest(data_row):
    """
    Update the latest JSON file with the most recent puzzle data.

    Args:
        data_row (dict): The latest puzzle data row
    """
    # Format the date to match the requested format (M/D/YYYY)
    date_obj = datetime.strptime(data_row["date"], "%Y-%m-%d")
    # Handle Windows vs Unix platform differences for date formatting
    try:
        # Unix-style formatting (works on macOS and Linux)
        formatted_date = date_obj.strftime("%-m/%-d/%Y")
    except ValueError:
        # Windows alternative (remove leading zeros manually)
        month = str(date_obj.month)
        day = str(date_obj.day)
        year = date_obj.strftime("%Y")
        formatted_date = f"{month}/{day}/{year}"
        
    # Format the puzzle_date to match the requested format (M/D/YYYY)
    puzzle_date_obj = datetime.strptime(data_row["puzzle_date"], "%Y-%m-%d")
    # Handle Windows vs Unix platform differences for date formatting
    try:
        # Unix-style formatting (works on macOS and Linux)
        formatted_puzzle_date = puzzle_date_obj.strftime("%-m/%-d/%Y")
    except ValueError:
        # Windows alternative (remove leading zeros manually)
        month = str(puzzle_date_obj.month)
        day = str(puzzle_date_obj.day)
        year = puzzle_date_obj.strftime("%Y")
        formatted_puzzle_date = f"{month}/{day}/{year}"

    # Create the JSON structure
    json_data = {
        "puzzles": [
            {
                "date": formatted_date,
                "puzzle_date": formatted_puzzle_date,
                "day": data_row["day"],
                "month": int(data_row["month"]),
                "puzzle_number": int(data_row["puzzle_number"]),
                "difficulty_score": float(data_row["difficulty_score"]),
                "max_score": int(data_row["max_score"]),
            }
        ],
        "metadata": {
            "last_updated": data_row["date"],
            "total_puzzles": 1,
            "source": "Connections Game Difficulty Data",
        },
    }

    # Write to JSON file
    with open(LATEST_JSON, "w") as json_file:
        json.dump(json_data, json_file, indent=2)

    logger.info(f"Updated latest JSON file with data for {data_row['date']} (Puzzle Date: {data_row['puzzle_date']})")


def update_json_latest_from_csv():
    """
    Update the latest JSON file by finding the most recent entry in the daily CSV file.
    Used when we don't have a new row to add but want to ensure the latest file is up to date.
    """
    if not os.path.exists(DAILY_FILE):
        logger.warning(
            f"Daily file {DAILY_FILE} does not exist, cannot update latest JSON"
        )
        return

    try:
        # Read all data from the CSV file
        with open(DAILY_FILE, "r", newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            rows = list(reader)

            if not rows:
                logger.warning("Daily CSV file exists but contains no data")
                return

            # Find the most recent date
            latest_row = None
            latest_date = None

            for row in rows:
                # Try to parse the date in different formats
                date_obj = None
                for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%-m/%-d/%Y"]:
                    try:
                        date_obj = datetime.strptime(row["date"], fmt)
                        break
                    except ValueError:
                        continue

                if date_obj and (latest_date is None or date_obj.date() > latest_date):
                    latest_date = date_obj.date()
                    latest_row = row

            if latest_row:
                update_json_latest(latest_row)
                logger.info(
                    f"Updated latest JSON file with most recent data from daily CSV (date: {latest_row['date']})"
                )
            else:
                logger.warning(
                    "Could not determine the most recent date in the daily CSV"
                )

    except Exception as e:
        logger.error(f"Error updating latest JSON from CSV: {e}")


def update_json_history():
    """
    Update the history JSON file with all puzzle data from the CSV history file.
    """
    if not os.path.exists(HISTORY_FILE):
        logger.warning(
            f"History file {HISTORY_FILE} does not exist, cannot update JSON history"
        )
        return

    try:
        # Read all data from the CSV file
        puzzles = []
        with open(HISTORY_FILE, "r", newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                try:
                    # Try to detect the date format and parse appropriately
                    date_obj = None
                    original_date = row["date"]

                    # Try different date formats
                    date_formats = [
                        "%Y-%m-%d",  # ISO format: 2024-09-01
                        "%m/%d/%Y",  # US format: 9/1/2024 or 09/01/2024
                        "%-m/%-d/%Y",  # Unix format without leading zeros
                    ]

                    for date_format in date_formats:
                        try:
                            date_obj = datetime.strptime(original_date, date_format)
                            break
                        except ValueError:
                            continue

                    # If none of the standard formats worked, try a manual parse for M/D/YYYY
                    if date_obj is None and "/" in original_date:
                        try:
                            parts = original_date.split("/")
                            if len(parts) == 3:
                                month = int(parts[0])
                                day = int(parts[1])
                                year = int(parts[2])
                                date_obj = datetime(year, month, day)
                        except (ValueError, IndexError):
                            pass

                    # If we still don't have a valid date, skip this row
                    if date_obj is None:
                        logger.error(
                            f"Could not parse date '{original_date}' in any known format. Skipping row."
                        )
                        continue
                        
                    # Calculate puzzle date (companion date + 1 day)
                    puzzle_date_obj = date_obj + timedelta(days=1)
                    
                    # Handle puzzle_date field - if it exists in the row use it, otherwise calculate it
                    if "puzzle_date" in row:
                        puzzle_date_str = row["puzzle_date"]
                        # Try to parse it to ensure it's valid
                        for fmt in date_formats:
                            try:
                                puzzle_date_obj = datetime.strptime(puzzle_date_str, fmt)
                                break
                            except ValueError:
                                continue
                    else:
                        # If puzzle_date doesn't exist in the CSV, calculate it
                        puzzle_date_obj = date_obj + timedelta(days=1)

                    # Format the dates for display (M/D/YYYY)
                    try:
                        # Unix-style formatting (works on macOS and Linux)
                        formatted_date = date_obj.strftime("%-m/%-d/%Y")
                        formatted_puzzle_date = puzzle_date_obj.strftime("%-m/%-d/%Y")
                    except ValueError:
                        # Windows alternative
                        formatted_date = f"{date_obj.month}/{date_obj.day}/{date_obj.year}"
                        formatted_puzzle_date = f"{puzzle_date_obj.month}/{puzzle_date_obj.day}/{puzzle_date_obj.year}"

                    # Convert ISO date for sorting
                    sort_date = date_obj.strftime("%Y-%m-%d")

                    # Get day and month based on puzzle_date
                    day_of_week = puzzle_date_obj.strftime("%A")
                    month_number = puzzle_date_obj.month

                    puzzles.append(
                        {
                            "date": formatted_date,  # Formatted for display (M/D/YYYY)
                            "puzzle_date": formatted_puzzle_date,  # Puzzle date (companion date + 1 day)
                            "day": day_of_week,  # Based on puzzle_date
                            "month": month_number,  # Based on puzzle_date
                            "puzzle_number": int(row["puzzle_number"]),
                            "difficulty_score": float(row["difficulty_score"]),
                            "max_score": int(row["max_score"]),
                            "_sort_date": sort_date,  # Hidden field for sorting
                        }
                    )
                except Exception as e:
                    logger.error(
                        f"Error processing row in history file: {e}, Row: {row}"
                    )
                    # Skip this row if there's an error

        # Sort puzzles by date (newest first) using the hidden sort date field
        puzzles.sort(key=lambda x: x.get("_sort_date", ""), reverse=True)

        # Remove the hidden _sort_date field before outputting to JSON
        for puzzle in puzzles:
            if "_sort_date" in puzzle:
                del puzzle["_sort_date"]

        # Create the JSON structure
        json_data = {
            "puzzles": puzzles,
            "metadata": {
                "last_updated": datetime.now().strftime("%Y-%m-%d"),
                "total_puzzles": len(puzzles),
                "source": "Connections Game Difficulty Data",
            },
        }

        # Write to JSON file
        with open(HISTORY_JSON, "w") as json_file:
            json.dump(json_data, json_file, indent=2)

        logger.info(f"Updated history JSON file with {len(puzzles)} puzzles")

    except Exception as e:
        logger.error(f"Error updating history JSON file: {e}")


def update_json_four_days():
    """
    Update the four-day JSON and CSV files with the most recent 4 puzzles
    from the history JSON file.
    """
    if not os.path.exists(HISTORY_JSON):
        logger.warning(
            f"History JSON file {HISTORY_JSON} does not exist, cannot update four-day files"
        )
        return

    try:
        # Read the full history JSON (already sorted newest-first)
        with open(HISTORY_JSON, "r") as json_file:
            history_data = json.load(json_file)

        puzzles = history_data.get("puzzles", [])
        four_day_puzzles = puzzles[:4]

        # Write the four-day JSON file
        json_data = {
            "puzzles": four_day_puzzles,
            "metadata": {
                "last_updated": datetime.now().strftime("%Y-%m-%d"),
                "total_puzzles": len(four_day_puzzles),
                "source": "Connections Game Difficulty Data",
            },
        }

        with open(FOUR_DAY_JSON, "w") as json_file:
            json.dump(json_data, json_file, indent=2)

        # Write the four-day CSV file
        fieldnames = [
            "date",
            "puzzle_date",
            "day",
            "month",
            "puzzle_number",
            "difficulty_score",
            "max_score",
        ]
        with open(FOUR_DAY_CSV, "w", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for puzzle in four_day_puzzles:
                writer.writerow(puzzle)

        logger.info(
            f"Updated four-day files with {len(four_day_puzzles)} puzzles"
        )

    except Exception as e:
        logger.error(f"Error updating four-day files: {e}")


def save_score_to_csv(date_str, puzzle_number, difficulty_score, max_score, file_path):
    """Save score to CSV file with additional day, month, and puzzle_date columns."""
    file_exists = os.path.exists(file_path)

    # Parse the date string to extract day and month
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    
    # Calculate puzzle_date (one day after the companion date)
    puzzle_date_obj = date_obj + timedelta(days=1)
    puzzle_date_str = puzzle_date_obj.strftime("%Y-%m-%d")
    
    # Get day of week and month for the puzzle date (not the companion date)
    day_of_week = puzzle_date_obj.strftime("%A")  # Full day name (e.g., "Monday")
    month_number = puzzle_date_obj.month  # Month as a number (1-12)

    # Check for duplicates if file exists
    duplicate_found = False
    existing_rows = []

    if file_exists:
        with open(file_path, "r", newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            existing_rows = list(reader)

            # Check if this entry already exists
            for row in existing_rows:
                # Try to match by date or puzzle number
                date_match = False

                # Try different date formats for comparison
                try:
                    row_date_obj = None
                    for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%-m/%-d/%Y"]:
                        try:
                            row_date_obj = datetime.strptime(row["date"], fmt)
                            break
                        except ValueError:
                            continue

                    if row_date_obj and row_date_obj.date() == date_obj.date():
                        date_match = True
                except Exception:
                    # If date parsing fails, fall back to string comparison
                    date_match = row["date"] == date_str

                # Check for a match by date or puzzle number
                if date_match or (row["puzzle_number"] == str(puzzle_number)):
                    logger.info(
                        f"Entry for {date_str} (Puzzle #{puzzle_number}) already exists in {file_path}, skipping"
                    )
                    duplicate_found = True
                    break

    # Only add if not a duplicate
    if not duplicate_found:
        row_data = {
            "date": date_str,
            "puzzle_date": puzzle_date_str,
            "day": day_of_week,
            "month": month_number,
            "puzzle_number": puzzle_number,
            "difficulty_score": difficulty_score,
            "max_score": max_score,
        }

        # If file exists, append the new row
        if file_exists:
            with open(file_path, "a", newline="") as csvfile:
                fieldnames = [
                    "date",
                    "puzzle_date",
                    "day",
                    "month",
                    "puzzle_number",
                    "difficulty_score",
                    "max_score",
                ]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writerow(row_data)
        else:
            # If file doesn't exist, create it with a header
            with open(file_path, "w", newline="") as csvfile:
                fieldnames = [
                    "date",
                    "puzzle_date",
                    "day",
                    "month",
                    "puzzle_number",
                    "difficulty_score",
                    "max_score",
                ]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerow(row_data)

        logger.info(
            f"Saved score for {date_str} (Puzzle #{puzzle_number}, Puzzle Date: {puzzle_date_str}) to {file_path}"
        )

        # Update JSON files after adding to CSV
        if file_path == DAILY_FILE:
            update_json_latest(row_data)

        # Always update the history JSON when adding to any CSV
        update_json_history()

        # Update four-day files after daily collection
        if file_path == DAILY_FILE:
            update_json_four_days()
    elif file_path == DAILY_FILE:
        # Even if we didn't add a new row, ensure JSON latest reflects most recent date
        update_json_latest_from_csv()
        update_json_four_days()

def collect_daily_score(max_retries=1, retry_delay_seconds=7200):
    """Collect today's difficulty score with optional retry logic.

    Args:
        max_retries (int): Maximum number of attempts (default 1 = no retry).
        retry_delay_seconds (int): Seconds to wait between retries (default 7200 = 2 hours).
    """
    today = date.today()
    formatted_date = today.strftime("%Y-%m-%d")

    # Get today's puzzle number
    puzzle_number = get_puzzle_number_for_date(today)

    # Get the URL for today's Connections Companion
    url = get_companion_url_for_date(today)

    for attempt in range(1, max_retries + 1):
        logger.info(
            f"Attempt {attempt}/{max_retries}: Collecting score for {formatted_date} "
            f"(Puzzle #{puzzle_number}) from {url}"
        )

        difficulty_score, max_score = scrape_difficulty_score(url)

        if difficulty_score is not None:
            save_score_to_csv(
                formatted_date, puzzle_number, difficulty_score, max_score, DAILY_FILE
            )
            # Also append to the history file
            save_score_to_csv(
                formatted_date, puzzle_number, difficulty_score, max_score, HISTORY_FILE
            )
            logger.info(
                f"Successfully collected score for {formatted_date}: {difficulty_score}/{max_score}"
            )
            return

        # Failed this attempt
        if attempt < max_retries:
            logger.warning(
                f"Attempt {attempt}/{max_retries} failed for {formatted_date}. "
                f"Retrying in {retry_delay_seconds} seconds ({retry_delay_seconds / 3600:.1f} hours)..."
            )
            time.sleep(retry_delay_seconds)
        else:
            logger.error(
                f"All {max_retries} attempts failed to collect score for {formatted_date}"
            )


def collect_historical_scores(
    start_date=None, end_date=None, delay=2, jitter=True, batch_size=10, cooldown=60
):
    """
    Collect historical difficulty scores.

    Args:
        start_date (date, optional): Starting date for collection. Defaults to Jan 1, 2023.
        end_date (date, optional): Ending date for collection. Defaults to today.
        delay (int, optional): Base delay in seconds between requests. Defaults to 2.
        jitter (bool, optional): Add random jitter to delay to appear more like human traffic. Defaults to True.
        batch_size (int, optional): Number of requests after which to take a longer break. Defaults to 10.
        cooldown (int, optional): Time in seconds to pause after each batch. Defaults to 60.
    """
    logger.info("Starting collection of historical scores")

    # Define the date range for historical data
    if start_date is None:
        # Connections started around June 2023, but we'll go back to January 1, 2023 just to be safe
        start_date = date(2023, 1, 1)

    if end_date is None:
        end_date = date.today()

    logger.info(f"Date range: {start_date} to {end_date}")

    # Prepare a set of dates we've already processed
    processed_dates = set()
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                processed_dates.add(row["date"])

    # Count for batch processing
    request_count = 0
    failed_consecutive = 0
    max_consecutive_failures = 5

    # Iterate through each date in the range
    current_date = start_date
    while current_date <= end_date:
        formatted_date = current_date.strftime("%Y-%m-%d")

        # Skip if we've already processed this date
        if formatted_date in processed_dates:
            logger.info(f"Date {formatted_date} already in history, skipping")
            current_date += timedelta(days=1)
            continue

        # Get the puzzle number for this date
        puzzle_number = get_puzzle_number_for_date(current_date)

        # Get the URL for this date's Connections Companion
        url = get_companion_url_for_date(current_date)

        logger.info(
            f"Attempting to collect historical score for {formatted_date} (Puzzle #{puzzle_number}) from {url}"
        )

        # Check for too many consecutive failures - may indicate IP blocking
        if failed_consecutive >= max_consecutive_failures:
            logger.error(
                f"Too many consecutive failures ({failed_consecutive}). Pausing for 30 minutes to avoid IP ban."
            )
            time.sleep(1800)  # 30 minute pause
            failed_consecutive = 0

        difficulty_score, max_score = scrape_difficulty_score(url)

        if difficulty_score is not None:
            save_score_to_csv(
                formatted_date, puzzle_number, difficulty_score, max_score, HISTORY_FILE
            )
            logger.info(
                f"Successfully collected historical score for {formatted_date}: {difficulty_score}/{max_score}"
            )
            failed_consecutive = 0
        else:
            logger.warning(
                f"Could not find score for {formatted_date} - this date may not have a puzzle"
            )
            failed_consecutive += 1

        # Increment request counter
        request_count += 1

        # Take a longer break after each batch
        if request_count % batch_size == 0:
            logger.info(
                f"Completed batch of {batch_size} requests. Taking a {cooldown} second break..."
            )
            time.sleep(cooldown)

            # Save progress to a temporary file
            with open("scraper_progress.txt", "w") as f:
                f.write(f"Last processed date: {formatted_date}\n")
                f.write(f"Total requests: {request_count}\n")

        # Be respectful with rate limiting - add jitter to appear more human-like
        actual_delay = delay
        if jitter:
            # Add random jitter between -0.5 and +1.5 seconds
            actual_delay = delay + random.uniform(-0.5, 1.5)
            actual_delay = max(1.0, actual_delay)  # Ensure minimum 1 second delay

        logger.debug(f"Waiting {actual_delay:.2f} seconds before next request")
        time.sleep(actual_delay)

        current_date += timedelta(days=1)

    logger.info(
        f"Historical data collection complete. Processed {request_count} dates."
    )

    # Make sure to update the history JSON file after collecting historical data
    update_json_history()


def migrate_existing_csv_files():
    """
    Migrate existing CSV files to include day, month, and puzzle_date columns.
    This function reads the existing CSV files, adds the new columns,
    and writes back to the same file.
    """
    for file_path in [HISTORY_FILE, DAILY_FILE]:
        if not file_path.exists():
            logger.info(f"File {file_path} does not exist, no migration needed.")
            continue

        logger.info(f"Migrating {file_path} to include day, month, and puzzle_date columns.")

        # Read the existing file
        with open(file_path, "r", newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            rows = list(reader)

            # Check if day, month, and puzzle_date columns already exist
            need_migration = False
            if "day" not in reader.fieldnames or "month" not in reader.fieldnames:
                need_migration = True
            
            if "puzzle_date" not in reader.fieldnames:
                need_migration = True
                
            if not need_migration:
                logger.info(f"File {file_path} already has all required columns.")
                continue

            # Process each row to add day, month, and puzzle_date
            updated_rows = []
            for row in rows:
                try:
                    date_obj = datetime.strptime(row["date"], "%Y-%m-%d")
                    
                    # Calculate puzzle_date (one day after the companion date)
                    puzzle_date_obj = date_obj + timedelta(days=1)
                    puzzle_date_str = puzzle_date_obj.strftime("%Y-%m-%d")
                    
                    # Calculate day and month based on puzzle_date
                    day_of_week = puzzle_date_obj.strftime("%A")
                    month_number = puzzle_date_obj.month

                    # Create updated row with new columns
                    updated_row = {
                        "date": row["date"],
                        "puzzle_date": puzzle_date_str,
                        "day": day_of_week,
                        "month": month_number,
                        "puzzle_number": row["puzzle_number"],
                        "difficulty_score": row["difficulty_score"],
                        "max_score": row["max_score"],
                    }
                    updated_rows.append(updated_row)
                except Exception as e:
                    logger.error(f"Error processing row {row}: {e}")
                    # Keep the original row if there's an error
                    updated_rows.append(row)

        # Write updated data back to the file
        with open(file_path, "w", newline="") as csvfile:
            fieldnames = [
                "date",
                "puzzle_date",
                "day",
                "month",
                "puzzle_number",
                "difficulty_score",
                "max_score",
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(updated_rows)

        logger.info(f"Successfully migrated {file_path}.")

    # Update JSON files after migration
    update_json_history()


def generate_initial_json_files():
    """
    Generate initial JSON files from existing CSV data.
    This can be run manually to create JSON files from scratch.
    """
    logger.info("Generating initial JSON files from existing CSV data")

    # Generate history JSON from history CSV
    update_json_history()

    # Generate four-day JSON and CSV from history JSON
    update_json_four_days()

    # Generate latest JSON from daily CSV if it exists
    if os.path.exists(DAILY_FILE):
        try:
            with open(DAILY_FILE, "r", newline="") as csvfile:
                reader = csv.DictReader(csvfile)
                rows = list(reader)
                if rows:
                    # Get the most recent entry (assuming the file is in chronological order)
                    latest_row = rows[-1]
                    update_json_latest(latest_row)
                    logger.info(
                        f"Generated latest JSON file with data from {latest_row['date']}"
                    )
                else:
                    logger.warning("Daily CSV file exists but contains no data")
        except Exception as e:
            logger.error(f"Error generating latest JSON file: {e}")
    else:
        logger.warning(
            f"Daily CSV file {DAILY_FILE} does not exist, cannot generate latest JSON"
        )


def main():
    """Main function to run the scraper."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Scrape NYT Connections difficulty scores"
    )
    parser.add_argument(
        "--historical", action="store_true", help="Collect historical scores"
    )
    parser.add_argument(
        "--date", type=str, help="Specific date to collect (YYYY-MM-DD format)"
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable additional debug logging"
    )
    parser.add_argument(
        "--start-date",
        type=str,
        help="Start date for historical collection (YYYY-MM-DD format)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        help="End date for historical collection (YYYY-MM-DD format)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Base delay between requests in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--no-jitter",
        action="store_true",
        help="Disable random timing jitter between requests",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of requests before taking a longer break (default: 10)",
    )
    parser.add_argument(
        "--cooldown",
        type=int,
        default=60,
        help="Seconds to pause after each batch (default: 60)",
    )
    parser.add_argument(
        "--user-agent", type=str, help="Custom user agent string to use for requests"
    )
    parser.add_argument(
        "--save-html", action="store_true", help="Save HTML content for debugging"
    )
    parser.add_argument(
        "--proxy",
        type=str,
        help="Proxy URL to use for requests (overrides APIFY_PROXY_PASSWORD env var). "
             "Example: http://user:pass@proxy.example.com:8000",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=1,
        help="Number of attempts for daily collection (default: 1, no retry)",
    )
    parser.add_argument(
        "--retry-delay",
        type=int,
        default=7200,
        help="Seconds to wait between retry attempts (default: 7200 = 2 hours)",
    )
    parser.add_argument(
        "--migrate",
        action="store_true",
        help="Migrate existing CSV files to include day and month columns",
    )
    parser.add_argument(
        "--generate-json",
        action="store_true",
        help="Generate JSON files from existing CSV data",
    )
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)
        logger.info("Debug mode enabled")

    # Configure proxy: CLI argument takes precedence over environment variable
    global PROXY_URL
    if args.proxy:
        PROXY_URL = args.proxy
        logger.info("Using CLI-specified proxy")
    else:
        PROXY_URL = _build_proxy_url()
        if PROXY_URL:
            logger.info("Using Apify proxy from APIFY_PROXY_PASSWORD environment variable")
        else:
            logger.info("No proxy configured -- using direct connection")

    # Update user agent if specified
    if args.user_agent:
        HEADERS["User-Agent"] = args.user_agent
        logger.info(f"Using custom user agent: {HEADERS['User-Agent']}")

    # Generate initial JSON files if requested
    if args.generate_json:
        generate_initial_json_files()
        return

    # Migrate existing CSV files if requested
    if args.migrate:
        migrate_existing_csv_files()
        return

    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
            puzzle_number = get_puzzle_number_for_date(target_date)
            url = get_companion_url_for_date(target_date)
            logger.info(
                f"Collecting score for specific date: {args.date} (Puzzle #{puzzle_number})"
            )

            difficulty_score, max_score = scrape_difficulty_score(url)

            if difficulty_score is not None:
                save_score_to_csv(
                    args.date, puzzle_number, difficulty_score, max_score, HISTORY_FILE
                )
                logger.info(
                    f"Successfully collected score for {args.date}: {difficulty_score}/{max_score}"
                )
            else:
                logger.error(f"Failed to collect score for {args.date}")

                # If save-html flag is set, save the HTML content for debugging
                if args.save_html:
                    proxies = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None
                    response = requests.get(url, headers=HEADERS, timeout=30, proxies=proxies)
                    with open(f"debug_{args.date}.html", "w", encoding="utf-8") as f:
                        f.write(response.text)
                    logger.info(f"Saved HTML content to debug_{args.date}.html")

        except ValueError:
            logger.error("Invalid date format. Please use YYYY-MM-DD format.")
    elif args.historical or args.start_date or args.end_date:
        logger.info("Running historical data collection")

        # Parse dates if provided
        start_date = None
        end_date = None

        if args.start_date:
            try:
                start_date = datetime.strptime(args.start_date, "%Y-%m-%d").date()
            except ValueError:
                logger.error("Invalid start date format. Please use YYYY-MM-DD format.")
                return

        if args.end_date:
            try:
                end_date = datetime.strptime(args.end_date, "%Y-%m-%d").date()
            except ValueError:
                logger.error("Invalid end date format. Please use YYYY-MM-DD format.")
                return

        # Run historical collection with parameters
        collect_historical_scores(
            start_date=start_date,
            end_date=end_date,
            delay=args.delay,
            jitter=not args.no_jitter,
            batch_size=args.batch_size,
            cooldown=args.cooldown,
        )
    else:
        logger.info("Running daily data collection")
        collect_daily_score(
            max_retries=args.retries,
            retry_delay_seconds=args.retry_delay,
        )


if __name__ == "__main__":
    main()
