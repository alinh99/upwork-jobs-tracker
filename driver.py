import logging
import json
import undetected_chromedriver as uc
import time
from selenium.webdriver.common.by import By

def initialize_uc_driver():
    """Initializes undetected-chromedriver on port 9222 with performance logging."""
    logging.info("Initializing undetected-chromedriver on port 9222...")

    options = uc.ChromeOptions()
    options.add_argument(r"--user-data-dir=D:\selenium\UpworkProfile")
    options.add_argument("--remote-debugging-port=9222")

    options.add_argument("--blink-settings=imagesEnabled=false")
    options.add_argument("--disable-remote-fonts")
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)

    driver = uc.Chrome(
        options=options,
        version_main=150,
        port=9222,
    )
    logging.info("Driver initialized successfully!")
    return driver


def get_authorization_header(driver) -> str | None:
    """Scans Chrome performance logs for the most recent Authorization header."""
    try:
        logs = driver.get_log("performance")
        for entry in reversed(logs):
            log_obj = json.loads(entry["message"])
            message = log_obj.get("message", {})
            if message.get("method") == "Network.requestWillBeSent":
                params = message.get("params", {})
                request = params.get("request", {})
                headers = request.get("headers", {})

                auth_header = headers.get("Authorization") or headers.get(
                    "authorization"
                )
                if auth_header:
                    return auth_header
    except Exception as e:
        logging.error(f"Error extracting authorization header: {e}")
    return None

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