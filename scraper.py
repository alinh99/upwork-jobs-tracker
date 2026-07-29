from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
import logging
import time
import config
from curl_cffi import requests
from driver import get_authorization_header


def process_single_job(job):
    """Worker task executed in parallel threads to format job data."""
    ciphertext = job.get("ciphertext", "")
    job_link = (
        f"https://www.upwork.com/jobs/{ciphertext}" if ciphertext else "#"
    )

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
        budget_str = (
            f"${hourly_obj.get('min', 0)}-${hourly_obj.get('max', 0)}/hr"
        )
    else:
        budget_str = job.get("tierText", "N/A")

    return {
        "job_title": job.get("title", "N/A"),
        "job_link": job_link,
        "job_description": job.get("description", ""),
        "job_budget": budget_str,
        "job_posted_on": job.get("createdOn", "N/A"),
        "job_proposals": job.get("proposalsTier", "N/A"),
        "job_skills": skills_str,
    }


def fetch_time_window_chunk(
    from_time_ms,
    to_time_ms,
    headers,
    selenium_cookies,
    chunk_label,
    max_pages=None,
):
    """Paginates through a specific isolated time window (e.g., a single month)."""
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
                logging.info(
                    f"[{chunk_label}] Completed window back to start date."
                )
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
                    logging.error(
                        f"[{chunk_label}] HTTP Error {response.status_code}"
                    )
                    break

                res_json = response.json()
                feed_data = (
                    res_json.get("data", {})
                    .get("mostRecentRecommendationsFeed", {})
                )
                results = feed_data.get("results", [])
                paging = feed_data.get("paging", {})

                if not results:
                    break

                for job in results:
                    chunk_jobs.append(process_single_job(job))

                logging.info(
                    f"[{chunk_label}] Page {page_count}: +{len(results)} jobs (Subtotal: {len(chunk_jobs)})"
                )

                # Get oldest timestamp in current batch
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
                time.sleep(0.3)  # Fast delay between inner requests

            except Exception as e:
                logging.error(f"[{chunk_label}] Error during pagination: {e}")
                break

    return chunk_jobs


def fetch_job_multithreaded(
    driver, max_pages=None, max_workers=8, mode="live"
):
    """- mode='live': Fetches recent 1 page immediately.

    - mode='backfill': Generates contiguous chunks covering 01/01/2026 -> TODAY (29/07/2026) and fetches all in parallel.
    """
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

    # Live Mode: Pull top 1 page right now
    if mode == "live":
        from_time_ms = int(
            datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp()
            * 1000
        )
        to_time_ms = int(time.time() * 1000)
        return fetch_time_window_chunk(
            from_time_ms,
            to_time_ms,
            headers,
            selenium_cookies,
            "LIVE_FEED",
            max_pages=max_pages or 1,
        )

    # --- BACKFILL MODE: Full Range (Jan 1, 2026 to NOW) ---
    start_date = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    now_date = datetime.now(timezone.utc)

    # Chunk size in days (15 days ensures high speed & bypasses API depth caps)
    chunk_days = 15
    window_slices = []
    curr_start = start_date

    # Build seamless contiguous windows covering Jan 1, 2026 all the way to NOW
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

    logging.info(
        f"=== FULL BACKFILL COMPLETE: Retrieved ALL {len(all_jobs)} jobs from Jan 1 to NOW! ==="
    )
    return all_jobs