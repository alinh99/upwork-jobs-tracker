import argparse
import logging
import os
import psutil

# Configuration Constants
URL = "https://www.upwork.com/nx/find-work/most-recent"
API_URL = "https://www.upwork.com/api/graphql/v1?alias=mostRecentRecommendationsFeed"
WEBSITE_NAME = "Upwork"
NTFY_TOPIC = "upwork_job"  # Unique ntfy topic name
RUN_INTERVAL_SECONDS = 1800  # Default: 30 mins
SPREADSHEET_NAME = "Upwork Jobs Tracker"
SERVICE_ACCOUNT_FILE = "service_account.json"
LIMITED_PER_PAGE = 50

# In-memory set to track seen job links during the session
SEEN_JOBS = set()
SPREADSHEET_URL = ""

SHEET_HEADERS = [
    "Posted On",
    "Title",
    "Skills",
    "Budget",
    "Proposals",
    "Description",
    "Link",
    "Status",
]


def setup_logging():
    """Sets up file and console logging."""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    file_handler = logging.FileHandler(f"{WEBSITE_NAME}.log", mode="a")
    file_handler.setLevel(logging.INFO)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


def parse_args():
    """Parses command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Upwork Job Scraper & Tracker"
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["backfill", "live"],
        default="live",
        help="'backfill' fetches all jobs from Jan 1 2026 without ntfy alerts. 'live' runs periodic loop for fresh jobs.",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=None,
        help="Optional maximum number of pages to fetch per cycle.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=RUN_INTERVAL_SECONDS,
        help="Sleep interval in seconds between cycles for live mode (Default: 1800s).",
    )
    return parser.parse_args()


def get_current_memory_usage_mb() -> float:
    """Returns process RAM usage in Megabytes."""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024**2)