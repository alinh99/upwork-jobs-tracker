import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

from curl_cffi import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import config
from driver import get_authorization_header, smart_scroll_and_load


def process_single_job(job):
    """Worker task executed in parallel threads to format job data from GraphQL response."""
    ciphertext = job.get("ciphertext", "")
    job_link = f"https://www.upwork.com/jobs/{ciphertext}" if ciphertext else "#"

    skills_list = [
        attr.get("prettyName", "")
        for attr in job.get("attrs", [])
        if attr.get("prettyName")
    ]
    skills_str = ", ".join(skills_list)

    amount_obj = job.get("amount") or {}
    fixed_amount = amount_obj.get("amount")
    hourly_obj = job.get("hourlyBudget") or {}

    if fixed_amount:
        budget_str = f"${fixed_amount}"
    elif hourly_obj.get("min") or hourly_obj.get("max"):
        budget_str = f"${hourly_obj.get('min', 0)}-${hourly_obj.get('max', 0)}/hr"
    else:
        budget_str = "Negotiate"
    
    job_level = job.get("tierText", "N/A")

    return {
        "job_title": job.get("title", "N/A"),
        "job_link": job_link,
        "job_description": job.get("description", ""),
        "job_budget": budget_str,
        "job_posted_on": config.format_upwork_time(job.get("createdOn", "N/A")),
        "job_proposals": job.get("proposalsTier", "N/A"),
        "job_skills": skills_str,
        "job_level": job_level
    }

def fetch_job_dom(driver, max_loads=3):
    """Navigates to Upwork, triggers smart scrolling, and extracts job card details from the DOM."""
    jobs = []
    wait = WebDriverWait(driver, 15)

    logging.info(f"Navigating to Upwork URL: {config.URL}...")
    driver.get(config.URL)
    time.sleep(3)  # Allow time for Cloudflare Turnstile & JS hydration

    smart_scroll_and_load(driver, max_loads=max_loads)

    logging.info("Extracting job details from DOM...")
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "section[data-ev-feed_name='Most Recent']")))
    except Exception as e:
        logging.warning(f"Could not find Most Recent feed section: {e}")
        return jobs

    job_cards = driver.find_elements(By.CSS_SELECTOR, "section[data-ev-feed_name='Most Recent']")
    for card in job_cards:
        try:
            # Extract Title & Link
            title_elem = card.find_element(By.CSS_SELECTOR, "h3.job-tile-title a, h2.job-tile-title a")
            job_title = title_elem.text.strip()
            job_link = title_elem.get_attribute("href")

            # Extract Description
            try:
                job_description = card.find_element(
                    By.CSS_SELECTOR, "span[data-test='job-description-text'], div.job-description"
                ).text.strip()
            except Exception:
                job_description = ""

            # Extract Posted On Timestamp
            try:
                job_posted_on = card.find_element(By.CSS_SELECTOR, "span[data-test='posted-on']").text.strip()
            except Exception:
                job_posted_on = ""

            # Extract Proposals
            try:
                job_proposals = card.find_element(By.CSS_SELECTOR, "span[data-test='proposals-tier']").text.strip()
            except Exception:
                job_proposals = ""

            # Extract Budget / Hourly Rate
            job_budget = "N/A"
            try:
                job_budget = card.find_element(By.CSS_SELECTOR, "span[data-test='budget']").text.strip()
            except Exception:
                try:
                    job_budget = card.find_element(By.CSS_SELECTOR, "strong[data-test='job-type']").text.strip()
                except Exception:
                    pass
            
            # Extract Skills
            try:
                skills_elements = card.find_elements(By.CSS_SELECTOR, "ul.air3-token-wrap li, button.air3-token")
                job_skills = ", ".join([elem.text.strip() for elem in skills_elements if elem.text.strip()])
            except Exception:
                job_skills = ""
            
            # Extract Job Level
            try:
                job_level = card.find_element(By.CSS_SELECTOR, "span[data-test='contractor-tier']").text.strip()
            except Exception:
                job_level = "N/A"
            
            jobs.append({
                "job_title": job_title,
                "job_link": job_link,
                "job_description": job_description,
                "job_budget": job_budget,
                "job_posted_on": job_posted_on,
                "job_proposals": job_proposals,
                "job_skills": job_skills,  # Standard DOM scraping yields empty skills string or requires extra parsing
                "job_level": job_level
            })
        except Exception as e:
            logging.debug(f"Skipping empty or malformed card: {e}")
            continue

    logging.info(f"Successfully fetched {len(jobs)} jobs via DOM live scroll!")
    return jobs


def fetch_time_window_chunk(
    from_time_ms,
    to_time_ms,
    headers,
    selenium_cookies,
    chunk_label,
    max_pages=None,
):
    """Paginates through a specific isolated time window via GraphQL API."""
    chunk_jobs = []
    current_to_time = to_time_ms
    page_count = 1

    query_str = """query MostRecentRecommendationsFeed($request: JobRecommendationsRequest!) {
        mostRecentRecommendationsFeed(request: $request) {
            results {
                id uid: id title ciphertext description type recno freelancersToHire
                duration durationLabel engagement amount { amount } createdOn: createdDateTime
                prefFreelancerLocationMandatory connectPrice
                client { totalHires totalSpent paymentVerificationStatus location { country } totalReviews totalFeedback hasFinancialPrivacy topClient lastRecruitingActivity proposalReviewedAt }
                tierText tier tierLabel proposalsTier enterpriseJob premium jobTs: jobTime
                attrs: skills { id uid: id prettyName: prefLabel prefLabel }
                hourlyBudget { type min max } isApplied annotations { tags } upworkNowJob upworkNowJobExpiresAt
            }
            paging { total count resultSetTs: minTime maxTime }
        }
    }"""

    with requests.Session() as client:
        while True:
            if max_pages and page_count > max_pages:
                break

            if current_to_time <= from_time_ms:
                logging.info(f"[{chunk_label}] Completed window back to start date.")
                break

            payload = {
                "query": query_str,
                "variables": {
                    "request": {
                        "limit": config.LIMITED_PER_PAGE,
                        "fromTime": from_time_ms,
                        "toTime": current_to_time,
                    }
                },
            }

            try:
                response = client.post(
                    config.API_URL,
                    headers=headers,
                    json=payload,
                    cookies=selenium_cookies,
                    impersonate="chrome120",
                    timeout=20,
                )

                if response.status_code != 200:
                    logging.error(f"[{chunk_label}] HTTP Error {response.status_code}")
                    break

                res_json = response.json()
                feed_data = res_json.get("data", {}).get("mostRecentRecommendationsFeed", {})
                results = feed_data.get("results", [])
                paging = feed_data.get("paging", {})

                if not results:
                    break

                for job in results:
                    chunk_jobs.append(process_single_job(job))

                logging.info(f"[{chunk_label}] Page {page_count}: +{len(results)} jobs (Subtotal: {len(chunk_jobs)})")

                raw_next_time = (
                    paging.get("resultSetTs")
                    or paging.get("minTime")
                    or paging.get("maxTime")
                )

                if raw_next_time is not None:
                    try:
                        next_time = int(raw_next_time)
                    except (ValueError, TypeError):
                        next_time = None
                else:
                    next_time = None

                if not next_time or next_time >= current_to_time:
                    break

                current_to_time = next_time
                page_count += 1
                time.sleep(0.3)

            except Exception as e:
                logging.error(f"[{chunk_label}] Error during pagination: {e}")
                break

    return chunk_jobs


def fetch_job_multithreaded(
    driver, max_pages=None, max_workers=8, mode="live"
):
    """
    - mode='live': Uses Selenium Smart Scroll to pull live feed jobs straight from the DOM.
    - mode='backfill': Generates contiguous chunks covering 01/01/2026 -> NOW and fetches all in parallel via GraphQL.
    """
    if mode == "live":
        return fetch_job_dom(driver, max_loads=max_pages or 3)

    # --- BACKFILL MODE ---
    logging.info(f"Navigating to Upwork URL: {config.URL}...")
    driver.get(config.URL)
    time.sleep(3)

    auth_token = get_authorization_header(driver)
    if not auth_token:
        logging.error("Could not capture Authorization header.")
        return []

    selenium_cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
    headers = {
        "Authorization": auth_token,
        "User-Agent": driver.execute_script("return navigator.userAgent;"),
    }

    start_date = datetime(2025, 12, 1, 0, 0, 0, tzinfo=timezone.utc)
    now_date = datetime.now(timezone.utc)

    chunk_days = 5
    window_slices = []
    curr_start = start_date

    while curr_start < now_date:
        curr_end = min(curr_start + timedelta(days=chunk_days), now_date)
        f_ms = int(curr_start.timestamp() * 1000)
        t_ms = int(curr_end.timestamp() * 1000)
        label = f"{curr_start.strftime('%d/%m')}->{curr_end.strftime('%d/%m')}"

        window_slices.append((f_ms, t_ms, label))
        curr_start = curr_end

    logging.info(
        f"=== Starting FULL BACKFILL from 01/01/2026 to {now_date.strftime('%d/%m/%Y')} across {len(window_slices)} parallel threads ==="
    )

    all_jobs = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(
                fetch_time_window_chunk,
                f_ms,
                t_ms,
                headers,
                selenium_cookies,
                label,
                max_pages,
            )
            for f_ms, t_ms, label in window_slices
        ]

        for future in as_completed(futures):
            try:
                res = future.result()
                if res:
                    all_jobs.extend(res)
            except Exception as e:
                logging.error(f"Thread execution failed: {e}")

    logging.info(f"=== FULL BACKFILL COMPLETE: Retrieved ALL {len(all_jobs)} jobs! ===")
    return all_jobs