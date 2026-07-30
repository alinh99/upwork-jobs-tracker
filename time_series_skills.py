from collections import Counter
import logging
import re
import config
import gspread
import pandas as pd


def analyze_skills_over_time(top_n_per_period: int = 10):
    """Reads saved jobs from Google Sheets, parses job posting timestamps,

    and aggregates top skills grouped by Month and Week.
    """
    logging.info(
        f"Connecting to Google Sheets [{config.SPREADSHEET_NAME}] for time-series skill analysis..."
    )

    try:
        gc = gspread.service_account(filename=config.SERVICE_ACCOUNT_FILE)
        sh = gc.open(config.SPREADSHEET_NAME)
        worksheet = sh.sheet1

        records = worksheet.get_all_records()
        if not records:
            logging.warning("No data found in Google Sheet to analyze.")
            return None

        df = pd.DataFrame(records)
        df.drop_duplicates(inplace=True)

        if "Skills" not in df.columns or "Posted On" not in df.columns:
            logging.error(
                "Required columns ('Skills', 'Posted On') missing from Google Sheet."
            )
            return None

        # Clean and parse datetime column
        df["Parsed_Date"] = pd.to_datetime(df["Posted On"], errors="coerce")

        # Drop rows with invalid dates or missing skills
        valid_df = df.dropna(subset=["Parsed_Date"]).copy()
        if valid_df.empty:
            logging.warning("No valid dates found in 'Posted On' column.")
            return None

        # Add Year-Month and Year-Week grouping columns
        valid_df["Month"] = valid_df["Parsed_Date"].dt.strftime("%Y-%m")
        valid_df["Week"] = valid_df["Parsed_Date"].dt.strftime("%Y-W%V")

        monthly_results = process_time_grouping(
            valid_df, "Month", top_n_per_period
        )
        weekly_results = process_time_grouping(
            valid_df, "Week", top_n_per_period
        )

        # Print summaries to console
        print_analysis_summary("MONTHLY TOP SKILLS", monthly_results)
        print_analysis_summary("WEEKLY TOP SKILLS", weekly_results)

        # Export to Google Sheets
        export_time_series_to_sheet(sh, monthly_results, "Skills by Month")
        export_time_series_to_sheet(sh, weekly_results, "Skills by Week")

        return monthly_results, weekly_results

    except Exception as e:
        logging.error(f"Error during time-series skill analysis: {e}")
        return None


def process_time_grouping(df: pd.DataFrame, group_col: str, top_n: int):
    """Groups DataFrame by period (Month or Week) and counts skill frequencies."""
    rows = []

    for period, group in df.groupby(group_col):
        total_period_jobs = len(group)
        skill_counter = Counter()

        for row_skills in group["Skills"].dropna().astype(str):
            if not row_skills or row_skills.upper() in ["N/A", "NONE", ""]:
                continue

            individual_skills = [
                s.strip()
                for s in re.split(r"[,;]\s*", row_skills)
                if s.strip() and len(s.strip()) > 1
            ]

            for skill in individual_skills:
                skill_counter[skill] += 1

        top_skills = skill_counter.most_common(top_n)

        for rank, (skill, count) in enumerate(top_skills, start=1):
            percentage = round((count / total_period_jobs) * 100, 2)
            rows.append({
                "Period": period,
                "Rank": rank,
                "Skill": skill,
                "Job Count": count,
                "Total Jobs in Period": total_period_jobs,
                "Demand Rate (%)": percentage,
            })

    return pd.DataFrame(rows)


def print_analysis_summary(title: str, results_df: pd.DataFrame):
    """Prints a formatted summary to the console."""
    if results_df is None or results_df.empty:
        return

    print("\n" + "=" * 70)
    print(f" 📅 {title}")
    print("=" * 70)

    # Show top 3 skills for each period in console for quick scanning
    top3_df = results_df[results_df["Rank"] <= 3]
    print(
        top3_df.to_string(
            index=False,
            columns=[
                "Period",
                "Rank",
                "Skill",
                "Job Count",
                "Demand Rate (%)",
            ],
        )
    )
    print("=" * 70 + "\n")


def export_time_series_to_sheet(spreadsheet, results_df: pd.DataFrame, tab_name: str):
    """Exports structured time-series data to a designated tab in Google Sheets."""
    if results_df is None or results_df.empty:
        return

    try:
        try:
            ws = spreadsheet.worksheet(tab_name)
            ws.clear()
        except gspread.exceptions.WorksheetNotFound:
            ws = spreadsheet.add_worksheet(
                title=tab_name, rows=len(results_df) + 10, cols=10
            )

        headers = list(results_df.columns)
        values = [headers] + results_df.values.tolist()

        ws.update("A1", values)
        ws.format("1:1", {"textFormat": {"bold": True}})

        logging.info(
            f"Successfully updated '{tab_name}' tab in Google Sheets!"
        )
    except Exception as e:
        logging.error(f"Failed to export '{tab_name}' to Google Sheets: {e}")


if __name__ == "__main__":
    config.setup_logging()
    analyze_skills_over_time(top_n_per_period=10)