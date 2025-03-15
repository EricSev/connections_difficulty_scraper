# connections_difficulty_scraper
Runs daily and scrapes the NYT Connections Difficulty Rating.

Usage Examples:

1. Collect today's difficulty score: Python connections_scraper.py 

3. Collect data for a specific date: python connections_scraper.py --date 2025-02-15

4. Collect historical data with custom parameters: python connections_scraper.py --historical --start-date 2024-01-01 --end-date 2024-06-30 --delay 3 --batch-size 5 --cooldown 120

6. Generate JSON files from existing CSV data: python connections_scraper.py --generate-json

7. Add day and month columns to existing CSV files: python connections_scraper.py --migrate

8. Enable debug logging: python connections_scraper.py --debug

9. Use a custom user agent: python connections_scraper.py --user-agent "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

10. Save HTML content when collection fails for debugging: python connections_scraper.py --date 2024-12-25 --save-html

![image](https://github.com/user-attachments/assets/59ac42c7-f359-4fce-b639-61b306eaa907)
