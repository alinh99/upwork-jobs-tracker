import logging
import os
import time
import psutil
import requests
import undetected_chromedriver as uc
from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from concurrent.futures import ThreadPoolExecutor
import gspread

load_dotenv()

URL = "https://www.upwork.com/nx/find-work/most-recent"
WEBSITE_NAME = "Upwork"
NTFY_TOPIC = "upwork_job"  # Change this to your unique ntfy topic name
RUN_INTERVAL_SECONDS = 3600  # 1 hour
SPREADSHEET_NAME = "Upwork Jobs Tracker"
SERVICE_ACCOUNT_FILE = "service_account.json"

# In-memory set to track seen job links during the session
SEEN_JOBS = set()

# Global variable to hold Google Sheet URL dynamically
SPREADSHEET_URL = ""

# Header configuration for Google Sheet
SHEET_HEADERS = [
    "Posted On",
    "Title",
    "Budget",
    "Proposals",
    "Description",
    "Link",
    "Status",
]

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Google Sheets Integration
# ---------------------------------------------------------------------------
def init_google_sheet():
    """Authenticates, checks/creates headers, and returns the worksheet and Sheet URL."""
    global SPREADSHEET_URL
    try:
        gc = gspread.service_account(filename=SERVICE_ACCOUNT_FILE)
        sh = gc.open(SPREADSHEET_NAME)
        SPREADSHEET_URL = sh.url  # Captures full Google Sheet link dynamically
        worksheet = sh.sheet1  # Selects the first tab/sheet

        # Check if row 1 already has headers
        existing_headers = worksheet.row_values(1)
        if not existing_headers:
            logging.info("Google Sheet is empty. Adding header row...")
            worksheet.insert_row(SHEET_HEADERS, index=1)
            # Apply bold formatting to header row if supported
            try:
                worksheet.format("1:1", {"textFormat": {"bold": True}})
            except Exception:
                pass

        return worksheet
    except Exception as e:
        logging.error(f"Failed to connect to Google Sheets: {e}")
        return None


def get_existing_links_from_sheet(worksheet) -> set:
    """Reads Column F (Column 6) to get all previously saved job URLs."""
    if not worksheet:
        return set()
    try:
        # Since 'Link' is in Column 6 (F), fetch Column 6
        links = worksheet.col_values(6)
        return set(links[1:])  # Skip header row
    except Exception as e:
        logging.error(f"Error fetching existing links from Sheet: {e}")
        return set()


def save_jobs_to_sheets(worksheet, new_jobs: list):
    """Appends new jobs to Google Sheets in a single bulk API call."""
    if not worksheet or not new_jobs:
        return

    rows_to_append = []
    for job in new_jobs:
        rows_to_append.append([
            job.get("job_posted_on", "N/A"),
            job.get("job_title", "N/A"),
            job.get("job_budget", "N/A"),
            job.get("job_proposals", "N/A"),
            job.get("job_description", "")[:500],  # Truncate to avoid cell limit
            job.get("job_link", "#"),
            "New",  # Initial status column
        ])

    try:
        worksheet.append_rows(rows_to_append, value_input_option="USER_ENTERED")
        logging.info(
            f"Successfully saved {len(rows_to_append)} new jobs to Google Sheets!"
        )
    except Exception as e:
        logging.error(f"Error appending rows to Google Sheets: {e}")


# ---------------------------------------------------------------------------
# Driver & Extraction Pipeline
# ---------------------------------------------------------------------------
def initialize_uc_driver():
    """Initializes undetected-chromedriver on port 9222 with image/font blocking."""
    logging.info("Initializing undetected-chromedriver on port 9222...")

    options = uc.ChromeOptions()
    options.add_argument(r"--user-data-dir=D:\selenium\UpworkProfile")
    options.add_argument("--remote-debugging-port=9222")

    # Performance flags
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.add_argument("--disable-remote-fonts")

    prefs = {
        "profile.managed_default_content_settings.images": 2,
    }
    options.add_experimental_option("prefs", prefs)

    driver = uc.Chrome(
        options=options,
        version_main=150,
        port=9222,
    )
    logging.info("Driver initialized successfully!")
    return driver


def smart_scroll_and_load(driver, max_loads=3):
    """
    Smart Scroll Pipeline:
    - Incrementally scrolls down to trigger Upwork's lazy-loading & infinite scroll.
    - Attempts to locate and click 'Load More' buttons using fallback selectors.
    - Dynamically stops if no new content is loaded into the DOM.
    """
    logging.info("Starting Smart Scroll pipeline...")

    for i in range(max_loads):
        logging.info(f"Smart Scroll Iteration {i + 1}/{max_loads}")

        # 1. Incremental scrolling to trigger scroll events
        last_height = driver.execute_script("return document.body.scrollHeight")
        scroll_step = 600
        current_scroll = 0

        while current_scroll < last_height:
            current_scroll += scroll_step
            driver.execute_script(f"window.scrollTo(0, {current_scroll});")
            time.sleep(0.3)  # Short delay for UI and lazy-loading render
            last_height = driver.execute_script(
                "return document.body.scrollHeight"
            )

        time.sleep(2)  # Allow time for background API requests to complete

        # 2. Search for Load More button using fallback selectors
        load_more_selectors = [
            "button[data-ev-label='load-more-button']",
            "button[data-test='load-more-button']",
            "button.up-btn-primary.load-more-button",
            "//button[contains(translate(text(), 'LOAD MORE', 'load more'), 'load more')]",  # XPath text search fallback
        ]

        button_clicked = False
        for selector in load_more_selectors:
            try:
                if selector.startswith("//"):
                    elements = driver.find_elements(By.XPATH, selector)
                else:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)

                for btn in elements:
                    if btn.is_displayed():
                        logging.info(
                            f"Found 'Load More' button via selector: {selector}. Clicking via JS..."
                        )
                        # Scroll button into view and execute JS click
                        driver.execute_script(
                            "arguments[0].scrollIntoView({block: 'center'});",
                            btn,
                        )
                        time.sleep(0.5)
                        driver.execute_script("arguments[0].click();", btn)
                        button_clicked = True
                        time.sleep(3)  # Wait for AJAX response
                        break
            except Exception:
                continue

            if button_clicked:
                break

        # 3. Verify whether new content was appended to DOM
        new_height = driver.execute_script("return document.body.scrollHeight")
        if not button_clicked and new_height == last_height:
            logging.info(
                "No new content loaded and no Load More button found. Reached end of feed."
            )
            break


def fetch_job(driver):
    """Navigates to Upwork, triggers smart scrolling, and extracts job card details."""
    jobs = []
    wait = WebDriverWait(driver, 15)

    logging.info(f"Navigating to Upwork URL: {URL}...")
    driver.get(URL)
    time.sleep(3)  # Allow time for Cloudflare Turnstile & JS hydration

    smart_scroll_and_load(driver, max_loads=3)

    logging.info("Extracting job details...")
    wait.until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "section[data-ev-feed_name='Most Recent']")
        )
    )

    job_cards = driver.find_elements(
        By.CSS_SELECTOR, "section[data-ev-feed_name='Most Recent']"
    )
    for card in job_cards:
        try:
            # Extract Title & Link
            title_elem = card.find_element(
                By.CSS_SELECTOR, "h3.job-tile-title a, h2.job-tile-title a"
            )
            job_title = title_elem.text.strip()
            job_link = title_elem.get_attribute("href")

            # Extract Description
            try:
                job_description = card.find_element(
                    By.CSS_SELECTOR,
                    "span[data-test='job-description-text'], div.job-description",
                ).text.strip()
            except Exception:
                job_description = ""

            # Extract Posted On Timestamp
            try:
                job_posted_on = card.find_element(
                    By.CSS_SELECTOR, "span[data-test='posted-on']"
                ).text.strip()
            except Exception:
                job_posted_on = ""
                
            # Extract Proposal
            try:
                job_proposals = card.find_element(
                    By.CSS_SELECTOR, "span[data-test='proposals-tier']"
                ).text.strip()
            except Exception:
                job_proposals = ""

            # Extract Budget / Hourly Rate (Safe fallback to prevent crashing)
            job_budget = "N/A"
            try:
                job_budget = card.find_element(
                    By.CSS_SELECTOR, "span[data-test='budget']"
                ).text.strip()
            except Exception:
                try:
                    job_budget = card.find_element(
                        By.CSS_SELECTOR, "strong[data-test='job-type']"
                    ).text.strip()
                except Exception:
                    pass

            jobs.append({
                "job_title": job_title,
                "job_link": job_link,
                "job_description": job_description,
                "job_budget": job_budget,
                "job_posted_on": job_posted_on,
                "job_proposals": job_proposals,
            })
        except Exception as e:
            logging.debug(f"Skipping empty or malformed card: {e}")
            continue

    logging.info(f"Successfully fetched {len(jobs)} jobs!")
    return jobs


# ---------------------------------------------------------------------------
# Notification Pipeline
# ---------------------------------------------------------------------------
def send_single_job_notification(args):
    """Worker function for concurrent ThreadPool execution."""
    index, job = args
    title = job.get("job_title", "N/A")
    link = job.get("job_link", "#")
    budget = job.get("job_budget", "N/A")
    description = job.get("job_description", "")[:250]
    posted_on = job.get("job_posted_on", "N/A")
    proposals = job.get("job_proposals", "N/A")

    message = (
        f"💰 Budget: {budget}\n"
        f"⏰ Posted: {posted_on}\n"
        f"📩 Proposals: {proposals}\n\n"
        f"📝 Desc: {description}\n\n"
        f"🔗 Job Link: {link}\n"
        f"📊 Sheet Tracker: {SPREADSHEET_URL}"
    )

    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={
                "Title": f"#{index} {title}".encode("utf-8"),
                "Priority": "high",
                "Tags": "briefcase,fire,clock1",
                "Click": link,
            },
            timeout=10,
        )
    except Exception as e:
        logging.error(f"Failed to push job #{index} to ntfy: {e}")


def send_jobs_to_ntfy_fast(new_jobs: list):
    """Dispatches new notifications in parallel."""
    if not new_jobs:
        return

    logging.info(f"Sending {len(new_jobs)} new notifications concurrently...")

    with ThreadPoolExecutor(max_workers=10) as executor:
        executor.map(send_single_job_notification, enumerate(new_jobs, 1))

    logging.info("All notifications dispatched successfully!")


def get_current_memory_usage_mb() -> float:
    """Returns process RAM usage in Megabytes."""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024**2)


# ---------------------------------------------------------------------------
# Hourly Execution Loop
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    driver = initialize_uc_driver()

    try:
        while True:
            start_time = time.time()
            logging.info("==========================================")
            logging.info("Starting Hourly Scraper Pipeline Cycle...")
            logging.info("==========================================")

            try:
                # 1. Connect to Google Sheets & ensure headers exist
                worksheet = init_google_sheet()
                sheet_seen_links = get_existing_links_from_sheet(worksheet)
                SEEN_JOBS.update(sheet_seen_links)

                # 2. Fetch fresh jobs from Upwork
                all_jobs = fetch_job(driver)

                # 3. Filter out duplicates
                new_jobs = [j for j in all_jobs if j.get("job_link") not in SEEN_JOBS]

                if new_jobs:
                    logging.info(
                        f"Found {len(new_jobs)} NEW unseen jobs out of {len(all_jobs)} fetched."
                    )

                    # 4. Save new jobs to Google Sheets
                    save_jobs_to_sheets(worksheet, new_jobs)

                    # 5. Push notifications to ntfy (includes Proposals & Google Sheet link)
                    send_jobs_to_ntfy_fast(new_jobs)

                    # 6. Update local memory set
                    for j in new_jobs:
                        link = j.get("job_link")
                        if link and link != "#":
                            SEEN_JOBS.add(link)
                else:
                    logging.info("No new unseen jobs found during this run.")

            except Exception as e:
                logging.error(f"Execution error during cycle: {e}")

            elapsed = time.time() - start_time
            memory = get_current_memory_usage_mb()

            logging.info(f"Cycle completed in {elapsed:.2f} seconds.")
            logging.info(f"Current Memory Usage: {memory:.2f} MB")
            logging.info("Sleeping for 1 hour until next run...")

            time.sleep(RUN_INTERVAL_SECONDS)
            
    except KeyboardInterrupt:
        logging.info("Stopping scraper loop gracefully...")
    finally:
        driver.quit()