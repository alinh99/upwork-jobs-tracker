import logging
import time
import config
from driver import initialize_uc_driver
from notifications import send_jobs_to_ntfy_fast
from scraper import fetch_job_multithreaded
from sheets import get_existing_links_from_sheet, init_google_sheet, save_jobs_to_sheets

if __name__ == "__main__":
    config.setup_logging()
    args = config.parse_args()

    driver = initialize_uc_driver()

    try:
        if args.mode == "backfill":
            logging.info(
                "=== Starting BACKFILL Mode: Fetching ALL jobs from Jan 1 2026 to NOW ==="
            )
            worksheet = init_google_sheet()
            sheet_seen_links = get_existing_links_from_sheet(worksheet)
            config.SEEN_JOBS.update(sheet_seen_links)

            all_jobs = fetch_job_multithreaded(
                driver, max_pages=args.pages, mode="backfill"
            )
            new_jobs = [
                j
                for j in all_jobs
                if j.get("job_link") not in config.SEEN_JOBS
            ]

            if new_jobs:
                logging.info(
                    f"Backfill found {len(new_jobs)} unseen jobs out of {len(all_jobs)} fetched."
                )
                save_jobs_to_sheets(worksheet, new_jobs)
                logging.info(
                    "Backfill complete! Saved to Google Sheets without triggering notifications."
                )
            else:
                logging.info("Backfill complete! No new jobs to add.")

        else:
            logging.info("=== Starting LIVE Mode: Periodic Monitoring Loop ===")
            while True:
                start_time = time.time()
                logging.info("==========================================")
                logging.info("Starting Scraper Pipeline Cycle...")
                logging.info("==========================================")

                try:
                    worksheet = init_google_sheet()
                    sheet_seen_links = get_existing_links_from_sheet(worksheet)
                    config.SEEN_JOBS.update(sheet_seen_links)

                    max_p = args.pages if args.pages else 1
                    all_jobs = fetch_job_multithreaded(
                        driver, max_pages=max_p, mode="live"
                    )

                    new_jobs = [
                        j
                        for j in all_jobs
                        if j.get("job_link") not in config.SEEN_JOBS
                    ]

                    if new_jobs:
                        logging.info(
                            f"Found {len(new_jobs)} NEW unseen jobs out of {len(all_jobs)} fetched."
                        )
                        save_jobs_to_sheets(worksheet, new_jobs)
                        send_jobs_to_ntfy_fast(new_jobs)

                        for j in new_jobs:
                            link = j.get("job_link")
                            if link and link != "#":
                                config.SEEN_JOBS.add(link)
                    else:
                        logging.info("No new unseen jobs found during this run.")

                except Exception as e:
                    logging.error(f"Execution error during cycle: {e}")

                elapsed = time.time() - start_time
                memory = config.get_current_memory_usage_mb()

                logging.info(f"Cycle completed in {elapsed:.2f} seconds.")
                logging.info(f"Current Memory Usage: {memory:.2f} MB")
                logging.info(
                    f"Sleeping for {args.interval} seconds until next run..."
                )

                time.sleep(args.interval)

    except KeyboardInterrupt:
        logging.info("Stopping scraper loop gracefully...")
    finally:
        driver.quit()