import logging
import config
import gspread


def init_google_sheet():
    """Authenticates, checks/creates headers, and returns the worksheet."""
    try:
        gc = gspread.service_account(filename=config.SERVICE_ACCOUNT_FILE)
        sh = gc.open(config.SPREADSHEET_NAME)
        config.SPREADSHEET_URL = sh.url
        worksheet = sh.sheet1

        existing_headers = worksheet.row_values(1)
        if not existing_headers:
            logging.info("Google Sheet is empty. Adding header row...")
            worksheet.insert_row(config.SHEET_HEADERS, index=1)
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
        links = worksheet.col_values(6)
        return set(links[1:])  # Skip header
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
            job.get("job_skills", "N/A"),
            job.get("job_budget", "N/A"),
            job.get("job_proposals", "N/A"),
            job.get("job_description", "")[:500],
            job.get("job_link", "#"),
            "New",
        ])

    try:
        worksheet.append_rows(
            rows_to_append, value_input_option="USER_ENTERED"
        )
        logging.info(
            f"Successfully saved {len(rows_to_append)} new jobs to Google Sheets!"
        )
    except Exception as e:
        logging.error(f"Error appending rows to Google Sheets: {e}")