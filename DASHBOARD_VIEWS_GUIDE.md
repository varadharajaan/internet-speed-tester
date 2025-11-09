# Dashboard Views - Visual Guide

## 🎨 Dashboard UI Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Internet Speed Overview                                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  Mode: [Daily     ▼]  Period: [Last 7 days ▼]  ☑ Show URLs             │
│        └─ Click me!             └─ Adjusts automatically                │
│                                                                           │
│  Expected Speed (Mbps): [200]  [Apply]                                  │
│                                                                           │
├─────────────────────────────────────────────────────────────────────────┤
│  🔍 Advanced Filters                                                     │
│  ┌───────────────┬───────────────┬───────────────┬──────────────────┐  │
│  │ From Date     │ To Date       │ Download (Mbps)│ Upload (Mbps)   │  │
│  │ [2025-11-01]  │ [2025-11-03]  │ [Min] [Max]    │ [Min] [Max]     │  │
│  └───────────────┴───────────────┴───────────────┴──────────────────┘  │
│  ┌───────────────┬───────────────┬───────────────┬──────────────────┐  │
│  │ Connection    │ WiFi Name     │ Server        │ Public IP        │  │
│  │ [All ▼]       │ [All ▼]       │ [All ▼]       │ [All ▼]          │  │
│  └───────────────┴───────────────┴───────────────┴──────────────────┘  │
│  [Apply Filters] [Reset All Filters]                                   │
│                                                                           │
├─────────────────────────────────────────────────────────────────────────┤
│  📊 Summary Stats                                                        │
│  Avg Download: 185.2 Mbps | Avg Upload: 95.6 Mbps | Avg Ping: 12.3 ms │
│  Below Expected: 3 days | Total Days: 7                                 │
│  Best Day: 2025-11-02 | Worst Day: 2025-10-28                          │
│                                                                           │
├─────────────────────────────────────────────────────────────────────────┤
│  📈 Speed Over Time                                                      │
│                                                                           │
│  200 |        ●                ●                                         │
│      |    ●       ●        ●       ●                                     │
│  150 | ●              ●                ●                                 │
│      +───────────────────────────────────────                           │
│        Oct 28  29  30  31  Nov 1  2  3                                  │
│                                                                           │
│  🔍 Chart Filter: Connection Type [All ▼]                               │
│                                                                           │
├─────────────────────────────────────────────────────────────────────────┤
│  📋 Detailed Test Records                                                │
│                                                                           │
│  🔍 Table Filter: Connection Type [All ▼]                               │
│                                                                           │
│  ┌───────────┬──────────┬─────────┬──────┬─────────────┬──────────┐   │
│  │ Date      │ Download │ Upload  │ Ping │ Connection  │ WiFi     │   │
│  ├───────────┼──────────┼─────────┼──────┼─────────────┼──────────┤   │
│  │ Nov 3     │ 192.4 ↑  │ 98.2    │ 11.9 │ Ethernet    │ -        │   │
│  │ Nov 2     │ 185.2    │ 95.6    │ 12.3 │ Wi-Fi 5GHz  │ MyWiFi   │   │
│  │ Nov 1     │ 178.5 ↓  │ 92.3    │ 13.1 │ Wi-Fi 2.4GHz│ MyWiFi   │   │
│  └───────────┴──────────┴─────────┴──────┴─────────────┴──────────┘   │
│                                                                           │
└─────────────────────────────────────────────────────────────────────────┘
```

## 📊 View Comparisons

### 1️⃣ Daily View (Default)
```
What you see: One data point per day
Best for: Week-to-week comparisons, spotting daily trends

Chart shows:
200 |  ●  ●    ●      ●    ●
    | ●    ●  ●  ●  ●  ●  ●
150 |
    +───────────────────────────
     Mon Tue Wed Thu Fri Sat Sun

Table shows:
┌────────────┬──────────┬─────────┐
│ Date       │ Download │ Upload  │
├────────────┼──────────┼─────────┤
│ 2025-11-03 │ 192.4    │ 98.2    │
│ 2025-11-02 │ 185.2    │ 95.6    │
│ 2025-11-01 │ 178.5    │ 92.3    │
└────────────┴──────────┴─────────┘

Good for: "Was yesterday better than today?"
```

### 2️⃣ Weekly View
```
What you see: One data point per week (average of 7 days)
Best for: Monthly comparisons, reducing noise

Chart shows:
200 |         ●       ●
    |   ●           ●
150 | ●
    +─────────────────────
      W40  W41  W42  W43  W44

Table shows:
┌──────────────────┬──────────┬─────────┬──────┐
│ Week Range       │ Download │ Upload  │ Days │
├──────────────────┼──────────┼─────────┼──────┤
│ 10/27 - 11/02    │ 185.2    │ 95.6    │ 7    │
│ 10/20 - 10/26    │ 178.5    │ 92.3    │ 7    │
│ 10/13 - 10/19    │ 192.4    │ 98.2    │ 7    │
└──────────────────┴──────────┴─────────┴──────┘

Good for: "Is this week better than last week?"
```

### 3️⃣ Monthly View
```
What you see: One data point per month (average of ~30 days)
Best for: Yearly trends, seasonal patterns

Chart shows:
200 |      ●       ●     ●
    |  ●       ●     ●
150 |
    +─────────────────────────
      Aug  Sep  Oct  Nov  Dec

Table shows:
┌─────────┬──────────┬─────────┬──────┐
│ Month   │ Download │ Upload  │ Days │
├─────────┼──────────┼─────────┼──────┤
│ 2025-11 │ 192.4    │ 98.2    │ 3    │
│ 2025-10 │ 185.2    │ 95.6    │ 31   │
│ 2025-09 │ 178.5    │ 92.3    │ 30   │
└─────────┴──────────┴─────────┴──────┘

Good for: "Which month had the best speeds?"
```

### 4️⃣ Yearly View
```
What you see: One data point per year (average of 12 months)
Best for: Long-term trends, service provider comparisons

Chart shows:
200 |             ●
    |         ●
150 |     ●
    +─────────────────
      2023  2024  2025

Table shows:
┌──────┬──────────┬─────────┬────────┐
│ Year │ Download │ Upload  │ Months │
├──────┼──────────┼─────────┼────────┤
│ 2025 │ 192.4    │ 98.2    │ 11     │
│ 2024 │ 185.2    │ 95.6    │ 12     │
│ 2023 │ 178.5    │ 92.3    │ 12     │
└──────┴──────────┴─────────┴────────┘

Good for: "Are speeds improving year over year?"
```

### 5️⃣ Hourly View
```
What you see: One data point per hour
Best for: Finding peak/off-peak patterns, debugging issues

Chart shows:
200 |    ●                    ●
    | ●    ●              ●    ●
150 |        ●  ●  ●  ●            ●
    +─────────────────────────────────
      12a 4a 8a 12p 4p 8p 12a

Table shows:
┌──────────────────┬──────────┬─────────┐
│ Time             │ Download │ Upload  │
├──────────────────┼──────────┼─────────┤
│ 2025-11-03 12:00 │ 192.4    │ 98.2    │
│ 2025-11-03 11:00 │ 185.2    │ 95.6    │
│ 2025-11-03 10:00 │ 178.5    │ 92.3    │
└──────────────────┴──────────┴─────────┘

Good for: "What time of day has best speeds?"
```

### 6️⃣ 15-Min View (Raw)
```
What you see: Every single test (15-min intervals)
Best for: Detailed debugging, anomaly investigation

Chart shows:
200 | ● ●   ● ●   ● ● ●   ●
    |   ● ●   ● ●   ●   ● ●
150 |
    +─────────────────────────
      (96 data points per day)

Table shows:
┌───────────────────┬──────────┬─────────┐
│ Timestamp         │ Download │ Upload  │
├───────────────────┼──────────┼─────────┤
│ 2025-11-03 12:15  │ 192.4    │ 98.2    │
│ 2025-11-03 12:00  │ 185.2    │ 95.6    │
│ 2025-11-03 11:45  │ 178.5    │ 92.3    │
└───────────────────┴──────────┴─────────┘

Good for: "What exactly happened at 3:45 PM?"
```

## 🎯 When to Use Each View

```
┌─────────────────────────────────────────────────────────────┐
│                    View Selection Guide                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Use Case                          → Recommended View        │
│  ────────────────────────────────────────────────────────   │
│                                                               │
│  "Is today slower than usual?"      → Daily (last 30 days)  │
│  "This week vs last week"           → Weekly (last 8 weeks) │
│  "Winter vs summer speeds"          → Monthly (last 12)     │
│  "Am I getting faster over time?"   → Yearly (last 5 years) │
│  "What time should I schedule?"     → Hourly (last 7 days)  │
│  "Why did it drop at 3 PM?"         → 15-min (that day)     │
│  "Long-term ISP comparison"         → Monthly/Yearly        │
│  "Find peak usage times"            → Hourly (last 30 days) │
│  "Document for ISP complaint"       → Daily (specific week) │
│  "Executive summary report"         → Monthly (last year)   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## 🔄 Switching Between Views

### Method 1: Use Dropdown (Recommended)
```
1. Click "Mode" dropdown in header
2. Select your desired view
3. Period automatically updates with relevant options
4. Click "Apply"
```

### Method 2: Use URL (For Bookmarks)
```
Daily:    http://localhost:8080/?mode=daily&days=30
Weekly:   http://localhost:8080/?mode=weekly&days=52
Monthly:  http://localhost:8080/?mode=monthly&days=12
Yearly:   http://localhost:8080/?mode=yearly&days=10
```

### Method 3: Combine with Filters
```
Weekly view, Ethernet only, last 26 weeks:
http://localhost:8080/?mode=weekly&days=26&connection=Ethernet

Monthly view, last 6 months, show URLs:
http://localhost:8080/?mode=monthly&days=6&urls=yes
```

## 🎨 Color Coding

```
📊 In Charts:
● Green     → Above expected speed
● Red       → Below expected speed (anomaly)
● Blue      → Connection type indicator

📋 In Tables:
↑ Green     → Better than average
↓ Red       → Worse than average
⚠️ Yellow    → Warning (near threshold)
```

## 💡 Pro Tips

### Tip 1: Start Wide, Zoom In
```
1. Start with Yearly view (big picture)
2. Spot a problem year → Switch to Monthly
3. Find problem month → Switch to Daily
4. Identify problem day → Switch to Hourly
5. Pinpoint exact issue → Switch to 15-min
```

### Tip 2: Compare Apples to Apples
```
Weekly view + Connection Type filter "Ethernet"
  vs
Weekly view + Connection Type filter "Wi-Fi 5GHz"

Opens in two browser tabs to compare side-by-side
```

### Tip 3: Create Analysis Dashboards
```
Bookmark these URLs for instant access:

"This Week's Performance"
→ ?mode=daily&days=7

"Monthly Trends"
→ ?mode=monthly&days=12

"Weekend vs Weekday"
→ ?mode=hourly&days=7
(Then filter in UI)
```

### Tip 4: Export for Reports
```
# Get data as JSON for Excel/PowerBI
curl "http://localhost:8080/api/data?mode=monthly&days=12" > monthly_report.json

# Or weekly for management meeting
curl "http://localhost:8080/api/data?mode=weekly&days=52" > yearly_weekly_report.json
```

## 📱 Mobile/Tablet View

The dashboard is responsive! All views work on:
- 📱 Mobile phones (stacked layout)
- 📱 Tablets (2-column layout)
- 💻 Desktop (full layout)

## 🎓 Quick Start Tutorial

### Scenario: "I want to see if my internet is getting worse"

```
Step 1: Open dashboard
Step 2: Select Mode: "Monthly"
Step 3: Select Period: "Last 12 months"
Step 4: Click "Apply"
Step 5: Look at the chart
        ↓
   Is the trend going down? → You have proof!
        ↓
   Click the lowest month to see details
        ↓
   Switch to "Daily" view for that month
        ↓
   Find the worst days
        ↓
   Screenshot and send to ISP!
```

### Scenario: "What's the best time to download large files?"

```
Step 1: Open dashboard
Step 2: Select Mode: "Hourly"
Step 3: Select Period: "Last 7 days"
Step 4: Click "Apply"
Step 5: Look at the pattern
        ↓
   Identify peak speed hours (usually 2-6 AM)
        ↓
   Schedule downloads for those times!
```

## 🎉 You're All Set!

Your dashboard has **six powerful views** ready to use:

1. ⏱️ **15-Minute** - Ultra detailed (raw data)
2. 🕐 **Hourly** - Daily patterns
3. 📅 **Daily** - Week-to-week trends
4. 📊 **Weekly** - Month-to-month comparison
5. 📈 **Monthly** - Yearly overview
6. 📉 **Yearly** - Long-term trends

**Just open http://localhost:8080 and start exploring!** 🚀
