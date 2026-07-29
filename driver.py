import logging
import json
import undetected_chromedriver as uc


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