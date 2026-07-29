from concurrent.futures import ThreadPoolExecutor
import logging
import config
from curl_cffi import requests


def send_single_job_notification(args):
    """Worker function for sending individual ntfy alert."""
    index, job = args
    title = job.get("job_title", "N/A")
    link = job.get("job_link", "#")
    budget = job.get("job_budget", "N/A")
    description = job.get("job_description", "")[:250]
    posted_on = job.get("job_posted_on", "N/A")
    proposals = job.get("job_proposals", "N/A")
    skills = job.get("job_skills", "N/A")

    message = (
        f"💰 Budget: {budget}\n"
        f"⏰ Posted: {posted_on}\n"
        f"📩 Proposals: {proposals}\n"
        f"🛠 Skills: {skills}\n\n"
        f"📝 Description:\n{description[:300]}...\n\n"
        f"🔗 Apply Job: {link}\n"
        f"📊 Google Sheet: {config.SPREADSHEET_URL}"
    )

    try:
        requests.post(
            f"https://ntfy.sh/{config.NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={
                "Title": f"#{index} {title}".encode("utf-8"),
                "Priority": "high",
                "Tags": "briefcase,fire,clock1",
                "Click": link,
                "Actions": f"view, Open Job, {link}; view, Open Sheet, {config.SPREADSHEET_URL}",
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