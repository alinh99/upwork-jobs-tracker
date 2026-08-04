# 🎯 Upwork Jobs Tracker & Notification Pipeline

[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Selenium](https://img.shields.io/badge/scraping-undetected--chromedriver-green)](https://github.com/ultrafunkamsterdam/undetected-chromedriver)
[![curl-cffi](https://img.shields.io/badge/http-curl--cffi-orange)](https://github.com/yifeikong/curl_cffi)
[![Google Sheets](https://img.shields.io/badge/integration-Google%20Sheets-success)](https://developers.google.com/sheets/api)

An enterprise-grade hybrid tracking pipeline for Upwork jobs. It combines **Undetected Chromedriver** for browser authentication and live DOM scraping with **`curl_cffi`** for high-performance multithreaded GraphQL requests. Newly discovered jobs are synchronized with **Google Sheets** and delivered instantly through **ntfy** push notifications.

---

# 📋 Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
- [Prerequisites](#-prerequisites)
- [Installation & Setup](#-installation--setup)
  - [1. Chrome Remote Debugging](#1-chrome-remote-debugging)
  - [2. Google Sheets Credentials](#2-google-sheets-credentials)
  - [3. Python Environment](#3-python-environment)
- [Usage](#-usage)
  - [Live Monitoring Mode](#live-monitoring-mode)
  - [Historical Backfill Mode](#historical-backfill-mode)
- [How It Works](#-how-it-works)
- [Project Structure](#-project-structure)
- [License](#-license)

---

# 🚀 Overview

This project provides a dual-mode scraping engine for collecting Upwork jobs efficiently.

### Live Monitoring Mode

- Connects to an authenticated Chrome instance through Remote Debugging.
- Scrolls the job feed automatically.
- Detects and clicks **Load More** buttons.
- Extracts newly posted jobs.
- Removes duplicates using Google Sheets.
- Sends instant notifications through **ntfy**.

### Historical Backfill Mode

- Captures authenticated session cookies and headers from Chrome.
- Uses Upwork's GraphQL API through **curl_cffi**.
- Downloads historical jobs in parallel using multiple worker threads.
- Imports historical data directly into Google Sheets without sending notifications.

---

# ✨ Key Features

## 🛡️ Hybrid Authentication

- Uses **undetected-chromedriver** attached to a Chrome Remote Debugging session.
- Bypasses Cloudflare protection.
- Automatically extracts authentication cookies and OAuth headers.

---

## 📜 Smart DOM Scrolling Engine

- Incremental scrolling for lazy-loaded content.
- Automatically detects **Load More** buttons.
- Multiple XPath/CSS selector fallbacks.
- Optimized for long-running monitoring.

---

## ⚡ Parallel GraphQL Backfill

- Uses **curl_cffi** with Chrome browser impersonation.
- Splits date ranges into configurable chunks.
- Executes concurrent GraphQL requests using `ThreadPoolExecutor`.
- Significantly faster than browser-only scraping.

---

## 📊 Google Sheets Integration

- Reads existing job URLs into memory.
- Prevents duplicate inserts.
- Bulk appends newly discovered jobs.
- Stores a continuously growing dataset.

---

## 🔔 Instant Notifications

- Sends asynchronous push notifications through **ntfy**.
- Only alerts for newly discovered jobs.
- Prevents duplicate alerts.

---

# ⚙️ Prerequisites

## Operating System

- Windows

## Google Chrome

Install Chrome at:

```text
C:\Program Files\Google\Chrome\Application\chrome.exe
```

## Python

- Python 3.10+
- Python 3.11

## Chrome Profile

```text
D:\selenium\UpworkProfile
```

## Google Service Account

Place the following file in the project root:

```text
service_account.json
```

Grant the service account **Editor** permission on your target Google Sheet.

---

# ⚙️ Installation & Setup

## 1. Chrome Remote Debugging

Launch Chrome before starting the application:

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 `
  --user-data-dir="D:\selenium\UpworkProfile"
```

> **Important**
>
> Log into your Upwork account using this Chrome instance before running the application.

---

## 2. Google Sheets Credentials

1. Create a Google Sheet.
2. Name it **Upwork Jobs Tracker**.
3. Download your Google Cloud Service Account key.
4. Save it as:

```text
service_account.json
```

5. Share the spreadsheet with the service account email using **Editor** permission.

---

## 3. Python Environment

Install all dependencies:

```bash
pip install -r requirements.txt
```

---

# 💡 Usage

## Live Monitoring Mode

Runs continuously, scrapes newly posted jobs, updates Google Sheets, and sends push notifications.

```bash
python main.py --mode live --pages 3 --interval 3600
```

---

## Historical Backfill Mode

# Default backfill (Jan 1, 2026 to present, 5-day chunks, 8 worker threads)
python main.py --mode backfill

# Custom date range with smaller chunks for high-density job windows
python main.py --mode backfill --from-date 2026-03-01 --to-date 2026-06-01 --chunk-days 2

# Low-concurrency mode (optimized for 1 vCPU / small VPS / n8n environment)
python main.py --mode backfill --workers 2 --chunk-days 7

# High-speed burst backfill on a powerful machine
python main.py --mode backfill --workers 16 --chunk-days 1

Notifications are disabled during backfill.

---

## Command Line Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--mode` | string | `live` | Operating mode: `live` or `backfill` |
| `--pages` | int | `None` | Maximum pages / load-more operations per cycle/chunk |
| `--interval` | int | `1800` | Delay between live monitoring cycles in seconds (Default: 30 min) |
| `--from-date` | string | `2026-01-01` | Backfill start date in `YYYY-MM-DD` format |
| `--to-date` | string | `None` | Backfill end date in `YYYY-MM-DD` format (Default: Today / Now) |
| `--chunk-days` | int | `5` | Time window size in days per backfill chunk thread |
| `--workers` | int | `8` | Maximum parallel worker threads for GraphQL backfill fetching |

---

# 🛠 How It Works

```text
                     +-----------------------------+
                     | Chrome DevTools (Port 9222) |
                     +--------------+--------------+
                                    |
                         Extract Driver & Auth
                                    |
              +---------------------+---------------------+
              |                                           |
              |                                           |
              v                                           v
        +-------------+                           +----------------+
        | LIVE MODE   |                           | BACKFILL MODE  |
        +-------------+                           +----------------+
              |                                           |
      Smart DOM Scroll                           Split Date Ranges
      Load More Buttons                          (Jan 1, 2026 → Now)
              |                                           |
        Extract Job Cards                      ThreadPoolExecutor
              |                               curl_cffi GraphQL
              +---------------------+---------------------+
                                    |
                                    v
                      +-------------------------------+
                      | Google Sheets Synchronization |
                      +---------------+---------------+
                                      |
                      +---------------+---------------+
                      |                               |
                      v                               v
               Append New Jobs              Send ntfy Notifications
                (Google Sheets)              (Live Mode Only)
```

---

# 📁 Project Structure

```text
.
├── __pycache__/
├── .env
├── .env.example
├── .gitignore
├── config.py
├── driver.py
├── main.py
├── notifications.py
├── README.md
├── requirements.txt
├── scraper.py
├── service_account.json
├── sheets.py
```

## Module Overview

| File | Description |
|------|-------------|
| `main.py` | Application entry point and pipeline orchestration |
| `driver.py` | Chrome initialization and authentication extraction |
| `scraper.py` | Live DOM scraper and GraphQL backfill engine |
| `sheets.py` | Google Sheets wrapper and deduplication |
| `notifications.py` | ntfy notification handler |
| `config.py` | Configuration, CLI arguments, logging |

---

# 📄 License

This project is licensed under the **MIT License**.