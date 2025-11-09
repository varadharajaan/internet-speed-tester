# Speed Test System Architecture

## 📡 Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                       INTERNET SPEED TEST SYSTEM                     │
└─────────────────────────────────────────────────────────────────────┘

┌───────────────┐
│ speed_        │  Every 15 minutes
│ collector.py  │──────────────┐
└───────────────┘              │
                               ▼
                    ┌─────────────────────┐
                    │  S3: vd-speed-test  │
                    │  /raw/year=/month=/ │
                    │  /day=/hour=/       │
                    │  minute=/test.json  │
                    └─────────────────────┘
                               │
                    ┌──────────┴──────────┐
                    ▼                     ▼
         ┌──────────────────┐  ┌──────────────────┐
         │ Hourly Aggregator│  │  Daily Aggregator│
         │ (Every hour)     │  │  (Daily 06:00)   │
         └──────────────────┘  └──────────────────┘
                    │                     │
                    ▼                     ▼
         ┌──────────────────┐  ┌──────────────────┐
         │ S3: hourly-prod  │  │ S3: vd-speed-test│
         │ /aggregated/     │  │ /aggregated/     │
         └──────────────────┘  └──────────────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
         ┌──────────────────┐┌──────────────────┐┌──────────────────┐
         │Weekly Aggregator ││Monthly Aggregator││Yearly Aggregator │
         │(Tue 02:00 IST)   ││(1st 02:00 IST)   ││(Jan 1 02:00 IST) │
         └──────────────────┘└──────────────────┘└──────────────────┘
                    │                   │                   │
                    ▼                   ▼                   ▼
         ┌──────────────────┐┌──────────────────┐┌──────────────────┐
         │ S3: weekly-prod  ││S3: monthly-prod  ││S3: yearly-prod   │
         │ /aggregated/     ││/aggregated/      ││/aggregated/      │
         └──────────────────┘└──────────────────┘└──────────────────┘
                    │                   │                   │
                    └───────────────────┼───────────────────┘
                                        ▼
                              ┌───────────────────┐
                              │  Flask Dashboard  │
                              │  (lambda_         │
                              │   dashboard.py)   │
                              └───────────────────┘
                                        │
                                        ▼
                              ┌───────────────────┐
                              │   Your Browser    │
                              │  (dashboard.html) │
                              └───────────────────┘
```

## 🗂️ S3 Bucket Structure

```
vd-speed-test/                          # Main bucket (Daily aggregations)
├── raw/                                # Raw 15-min test data
│   └── year=2025/
│       └── month=202511/
│           └── day=20251103/
│               └── hour=2025110312/
│                   └── minute=202511031215/
│                       └── test_20251103121532.json
│
└── aggregated/                         # Daily summaries
    └── year=2025/
        └── month=202511/
            └── day=20251103/
                └── speed_test_summary.json

vd-speed-test-hourly-prod/              # Hourly aggregations
└── aggregated/
    └── year=2025/
        └── month=202511/
            └── day=20251103/
                └── hour=2025110312/
                    └── speed_test_summary.json

vd-speed-test-weekly-prod/              # Weekly aggregations
└── aggregated/
    └── year=2025/
        └── week=2025W44/                # ISO week format
            └── speed_test_summary.json

vd-speed-test-monthly-prod/             # Monthly aggregations
└── aggregated/
    └── year=2025/
        └── month=202511/
            └── speed_test_summary.json

vd-speed-test-yearly-prod/              # Yearly aggregations
└── aggregated/
    └── year=2025/
        └── speed_test_summary.json
```

## 📅 Aggregation Timeline Example

```
November 2025 Timeline:

Day 1 (Nov 1)
├── 00:10 - Hourly aggregation (Oct 31 23:00)
├── 01:10 - Hourly aggregation (Nov 1 00:00)
├── 02:00 - Monthly aggregation (October 2025) ← MONTHLY
├── ...
└── 06:00 - Daily aggregation (Oct 31) ← DAILY

Day 2 (Nov 2)
├── 00:10 - Hourly aggregation (Nov 1 23:00)
├── 01:10 - Hourly aggregation (Nov 2 00:00)
├── ...
└── 06:00 - Daily aggregation (Nov 1)

Day 3 (Nov 3, Monday)
├── 00:10 - Hourly aggregation (Nov 2 23:00)
├── 01:10 - Hourly aggregation (Nov 3 00:00)
├── 02:00 - Weekly aggregation (Oct 27 - Nov 2) ← WEEKLY
├── ...
└── 06:00 - Daily aggregation (Nov 2)

...continues...
```

## 🎯 Data Granularity Comparison

```
15-Minute View (mode=minute):
|-|-|-|-|-|-|-|-|-|-|-|-|...  (96 points per day)
Every bar = One 15-min test

Hourly View (mode=hourly):
|---|---|---|---|---|...       (24 points per day)
Every bar = 4 tests averaged

Daily View (mode=daily):
|-------|-------|-------|...   (1 point per day)
Every bar = 24 hours averaged

Weekly View (mode=weekly):
|---------------|--------------|...  (1 point per week)
Every bar = 7 days averaged

Monthly View (mode=monthly):
|------------------------------|...  (1 point per month)
Every bar = ~30 days averaged

Yearly View (mode=yearly):
|------------------------------------------------|...  (1 point per year)
Every bar = 12 months averaged
```

## 🔄 Lambda Functions

```
┌─────────────────────────────────────────────────────────────┐
│                    Lambda Functions                          │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  1. vd-speedtest-daily-aggregator-prod                      │
│     • Trigger: EventBridge schedules + Manual API calls     │
│     • Modes: hourly, daily, weekly, monthly, yearly         │
│     • URL: c5jziahxp5ysapj2ioroeaajfe0qboqs...             │
│                                                               │
│  2. vd-speedtest-dashboard-prod                             │
│     • Trigger: HTTP requests (Function URL)                 │
│     • Purpose: Serve web dashboard + API                    │
│     • Views: All aggregation levels supported               │
│                                                               │
│  3. vd-speedtest-hourly-checker-prod                        │
│     • Trigger: HTTP requests (Function URL)                 │
│     • Purpose: Check data coverage for specific date        │
│     • URL: jlbqijazj3b4c7p57siqls6due0tumve...             │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## 📊 Dashboard View Selector

```
┌────────────────────────────────────────────────────────────┐
│  Internet Speed Overview                                    │
├────────────────────────────────────────────────────────────┤
│                                                              │
│  Mode: [Daily ▼]    Period: [Last 7 days ▼]   [Apply]     │
│         │                     │                              │
│         │                     └─ Adjusts based on mode:     │
│         │                        • Days (minute/hourly/daily)│
│         │                        • Weeks (weekly)           │
│         │                        • Months (monthly)         │
│         │                        • Years (yearly)           │
│         │                                                    │
│         └─ Available modes:                                 │
│            • 15-min  (Raw data every 15 minutes)           │
│            • Hourly  (Aggregated by hour)                  │
│            • Daily   (Aggregated by day) ← Default         │
│            • Weekly  (Aggregated by week)                  │
│            • Monthly (Aggregated by month)                 │
│            • Yearly  (Aggregated by year)                  │
│                                                              │
└────────────────────────────────────────────────────────────┘
```

## 🎬 Usage Scenarios

### Scenario 1: "Is my internet slower this month?"

```
Step 1: Open Dashboard
Step 2: Select Mode: Monthly
Step 3: Select Period: Last 2 months
Step 4: Click Apply
Step 5: Compare avg speeds in chart
```

### Scenario 2: "What time of day has best speeds?"

```
Step 1: Open Dashboard
Step 2: Select Mode: Hourly
Step 3: Select Period: Last 1 day
Step 4: Click Apply
Step 5: Look at hourly pattern in chart
```

### Scenario 3: "Long-term performance over 5 years"

```
Step 1: Open Dashboard
Step 2: Select Mode: Yearly
Step 3: Select Period: Last 5 years
Step 4: Click Apply
Step 5: See year-over-year trends
```

### Scenario 4: "Did I have any tests yesterday?"

```
Step 1: Open Hourly Checker URL
Step 2: Add ?date=2025-11-02
Step 3: View JSON response with hour-by-hour breakdown
```

## 🔍 API Response Examples

### Weekly Aggregation Response
```json
{
  "message": "ok",
  "mode": "weekly",
  "result": {
    "week": "2025W44",
    "week_start": "2025-10-27",
    "week_end": "2025-11-02",
    "avg_download": 185.23,
    "avg_upload": 95.67,
    "avg_ping": 12.34,
    "min_download": 45.12,
    "max_download": 245.67,
    "records_aggregated": 228,
    "days": 7,
    "connection_types": ["Ethernet", "Wi-Fi 5GHz", "Wi-Fi 2.4GHz"],
    "anomalies_count": 3
  }
}
```

### Dashboard API Response (Weekly View)
```json
[
  {
    "date_ist": "2025-10-27",
    "date_ist_str": "2025-10-27 to 2025-11-02",
    "download_avg": 185.23,
    "upload_avg": 95.67,
    "ping_avg": 12.34,
    "days": 7,
    "connection_type": "Ethernet, Wi-Fi 5GHz",
    "below_expected": false
  },
  {
    "date_ist": "2025-11-03",
    "date_ist_str": "2025-11-03 to 2025-11-09",
    "download_avg": 192.45,
    "upload_avg": 98.23,
    "ping_avg": 11.89,
    "days": 5,
    "connection_type": "Ethernet",
    "below_expected": false
  }
]
```

## 🎨 Visual Summary

```
╔═══════════════════════════════════════════════════════════════════╗
║                   YOUR COMPLETE SETUP IS READY!                    ║
╠═══════════════════════════════════════════════════════════════════╣
║                                                                     ║
║  ✅ Raw 15-min data collection                                     ║
║  ✅ Hourly aggregations (every hour)                               ║
║  ✅ Daily aggregations (daily at 06:00 IST)                        ║
║  ✅ Weekly aggregations (Tuesday 02:00 IST)                        ║
║  ✅ Monthly aggregations (1st of month 02:00 IST)                  ║
║  ✅ Yearly aggregations (Jan 1 02:00 IST)                          ║
║  ✅ Dashboard with all views                                       ║
║  ✅ API endpoints for programmatic access                          ║
║  ✅ Hourly checker for data coverage                               ║
║  ✅ S3 buckets with lifecycle policies                             ║
║  ✅ CloudWatch monitoring and alarms                               ║
║                                                                     ║
║  🎯 Just use the mode dropdown in your dashboard!                  ║
║                                                                     ║
╚═══════════════════════════════════════════════════════════════════╝
```
