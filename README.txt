# 🎯 Upwork Jobs Tracker & Notification Pipeline

[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Selenium](https://img.shields.io/badge/scraping-undetected--chromedriver-green)](https://github.com/ultrafunkamsterdam/undetected-chromedriver)
[![Google Sheets](https://img.shields.io/badge/integration-Google%20Sheets-success)](https://developers.google.com/sheets/api)

An automated Python tracking pipeline that monitors Upwork's most recent jobs using **Undetected Chromedriver**, syncs unseen leads directly to **Google Sheets**, and dispatches parallel mobile/desktop push notifications via **ntfy**.

---

# 📋 Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
- [Prerequisites](#-prerequisites)
- [Installation & Setup](#-installation--setup)
  - [1. Chrome Remote Debugging Setup](#1-chrome-remote-debugging-setup)
  - [2. Google Sheets API Credentials](#2-google-sheets-api-credentials)
  - [3. Python Environment Setup](#3-python-environment-setup)
- [Usage](#-usage)
- [How It Works](#-how-it-works)
- [File Structure](#-file-structure)
- [License](#-license)

---

# 🚀 Overview

This automation script attaches to a dedicated, pre-authenticated Google Chrome profile running on port `9222`. It periodically parses the **Most Recent** Upwork feed, deduplicates job links against historical Google Sheet records, appends new leads in bulk, and sends instant push notifications using `ntfy.sh`.

---

# ✨ Key Features

- 🛡️ **Cloudflare & Anti-Bot Bypass**
  - Uses `undetected-chromedriver` with a dedicated Chrome debugging profile.
  - Preserves authenticated Upwork sessions.
  - Handles Cloudflare and dynamic page hydration.

- 📜 **Smart Scroll & Lazy Loading**
  - Automatically scrolls through the feed.
  - Detects and clicks **Load More** buttons.
  - Uses multiple CSS/XPath fallback selectors for reliability.

- 📊 **Google Sheets Synchronization**
  - Reads existing job URLs from **Column F**.
  - Prevents duplicate entries.
  - Performs efficient bulk inserts for new jobs.

- ⚡ **Concurrent Push Notifications**
  - Uses `ThreadPoolExecutor`.
  - Sends instant `ntfy` notifications containing:
    - Job title
    - Direct Upwork URL
    - Google Sheet link

- ⚡ **Resource Optimized**
  - Disables image rendering.
  - Blocks external fonts.
  - Reduces memory consumption for long-running execution.

---

# ⚙️ Prerequisites

- **Operating System:** Windows
- **Google Chrome:** Installed at

```text
C:\Program Files\Google\Chrome\Application\chrome.exe
```

- **Python:** 3.10+
- **Chrome User Profile:**

```text
D:\selenium\UpworkProfile
```

- **Google Service Account**
  - A valid `service_account.json`
  - Shared with your Google Sheet using **Editor** permission

---

# ⚡ Installation & Setup

## 1. Chrome Remote Debugging Setup

Launch Chrome using your dedicated Upwork profile before running the scraper.

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 `
  --user-data-dir="D:\selenium\UpworkProfile"
```

> **Note**
>
> Log into your Upwork account in this Chrome instance before starting the automation pipeline.

---

## 2. Google Sheets API Credentials

1. Create a Google Sheet named **Upwork Jobs Tracker**.
2. Enable the **Google Sheets API** in Google Cloud Console.
3. Download your Service Account credentials.
4. Save the file as:

```text
service_account.json
```

5. Share your Google Sheet with the `client_email` contained in `service_account.json` and grant **Editor** access.

---

## 3. Python Environment Setup

Clone the repository and install the required dependencies.

```bash
pip install \
    undetected-chromedriver \
    gspread \
    psutil \
    requests \
    python-dotenv \
    selenium
```

---

# 💡 Usage

Run the pipeline:

```bash
python main.py
```

The application starts an automated monitoring loop that:

- Connects to the Chrome debugging session
- Scrapes newly posted Upwork jobs
- Syncs new jobs into Google Sheets
- Sends push notifications
- Sleeps for **3600 seconds** before repeating

Each iteration logs:

- Execution time
- Memory usage
- Number of new jobs discovered
- Notification status

---

# 🛠 How It Works

```text
+----------------------------+
| Chrome DevTools (Port 9222)|
+-------------+--------------+
              |
              v
+----------------------------+
| Navigate to Most Recent    |
| Upwork Feed                |
+-------------+--------------+
              |
              v
+----------------------------+
| Smart Scroll Pipeline      |
| Infinite Scroll            |
| Load More Detection        |
+-------------+--------------+
              |
              v
+----------------------------+
| Extract Job Cards          |
+-------------+--------------+
              |
              v
+----------------------------+
| Google Sheets Sync         |
| Read Existing URLs         |
| Remove Duplicates          |
+-------------+--------------+
              |
      +-------+--------+
      |                |
      v                v
+-------------+   +----------------+
| Bulk Insert |   | ntfy Push      |
| Google Sheet|   | Notifications  |
+-------------+   +----------------+
```

---

# 📁 File Structure

```text
.
├── main.py
├── service_account.json
├── .env
├── Upwork.log
└── README.md
```

| File | Description |
|------|-------------|
| `main.py` | Core scraping pipeline, Google Sheets synchronization, and notification loop |
| `service_account.json` | Google Cloud Service Account credentials |
| `.env` | Environment variables |
| `Upwork.log` | Runtime logs and execution metrics |
| `README.md` | Project documentation |

---

# 📄 License

This project is distributed under the **MIT License**.