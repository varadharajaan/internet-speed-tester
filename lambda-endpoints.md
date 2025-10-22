# 🧪 Lambda Function URLs — API & Dashboard Access

Your deployment created **three Lambda Function URLs**:

| Function | Purpose | URL |
|-----------|----------|-----|
| **Daily Aggregator** | Aggregates 15-minute results into daily summaries and uploads to S3 | 🔗 [AggregatorFunctionUrl](https://ra7ljtnqfpehcfaaafy4mvanqi0mxoqv.lambda-url.ap-south-1.on.aws/) |
| **Dashboard (Flask)** | Interactive HTML dashboard (daily & 15-min trend visualization) | 🔗 [DashboardFunctionUrl](https://b33l2r7iro5prfqvuppgsbgasy0jivyt.lambda-url.ap-south-1.on.aws/) |
| **Hourly Checker** | Returns hourly/minute folder counts for a given date | 🔗 [HourlyCheckerFunctionUrl](https://7mpxatwdutexv7r2azovb7a6uq0fgzai.lambda-url.ap-south-1.on.aws/) |

---

## 🌅 1. Daily Aggregator Lambda

**Purpose:**  
Triggered daily at **06:00 AM IST (00:30 UTC)** via EventBridge,  
but you can invoke it manually to force aggregation.

### ➤ Browser
Just open:
```
https://ra7ljtnqfpehcfaaafy4mvanqi0mxoqv.lambda-url.ap-south-1.on.aws/
```

### ➤ Linux/macOS (curl)
```bash
curl -X POST https://ra7ljtnqfpehcfaaafy4mvanqi0mxoqv.lambda-url.ap-south-1.on.aws/
```

### ➤ PowerShell (Windows)
```powershell
Invoke-WebRequest -Uri "https://ra7ljtnqfpehcfaaafy4mvanqi0mxoqv.lambda-url.ap-south-1.on.aws/" -Method POST
```

**Sample JSON Response**
```json
{
  "message": "Daily aggregation complete",
  "records": 96,
  "avg_download": 154.83,
  "avg_upload": 36.12,
  "avg_ping": 10.54,
  "unique_servers": ["Airtel Mumbai – speedtest.mumbai.airtel.in – Mumbai (India)"],
  "urls_count": 84,
  "unique_ips": ["223.178.80.250"],
  "s3_key": "aggregated/year=2025/month=202510/day=20251022/speed_summary_20251022.json"
}
```

---

## 📊 2. Dashboard (Flask + Chart.js)

**Purpose:**  
Visualizes your daily or 15-minute data interactively with anomaly highlighting and zooming.

### ➤ Browser
Open directly:
```
https://b33l2r7iro5prfqvuppgsbgasy0jivyt.lambda-url.ap-south-1.on.aws/
```

### Supported Query Parameters

| Parameter | Default | Description |
|------------|----------|-------------|
| `days` | `7` | Number of days of data to show |
| `mode` | `daily` | `daily` = 1 row per day, `minute` = 15-min granularity |
| `urls` | `no` | `yes` = show Speedtest result URLs |
| `threshold` | `200` | Mbps threshold for anomaly detection |

### Example URLs

| Use Case | URL |
|-----------|-----|
| **Daily summary (7 days)** | [link](https://b33l2r7iro5prfqvuppgsbgasy0jivyt.lambda-url.ap-south-1.on.aws/?days=7) |
| **15-minute detail (2 days)** | [link](https://b33l2r7iro5prfqvuppgsbgasy0jivyt.lambda-url.ap-south-1.on.aws/?mode=minute&days=2) |
| **With URLs & custom threshold** | [link](https://b33l2r7iro5prfqvuppgsbgasy0jivyt.lambda-url.ap-south-1.on.aws/?mode=minute&days=7&urls=yes&threshold=150) |

---

## ⏱️ 3. Hourly Checker Lambda

**Purpose:**  
Inspects the raw minute-level folders for a given date and reports  
how many **hours** and **15-min intervals** were captured.

### ➤ Browser
```
https://7mpxatwdutexv7r2azovb7a6uq0fgzai.lambda-url.ap-south-1.on.aws/?date=2025-10-23
```

### ➤ Linux/macOS (curl)
```bash
curl "https://7mpxatwdutexv7r2azovb7a6uq0fgzai.lambda-url.ap-south-1.on.aws/?date=2025-10-23"
```

### ➤ PowerShell (Windows)
```powershell
Invoke-WebRequest -Uri "https://7mpxatwdutexv7r2azovb7a6uq0fgzai.lambda-url.ap-south-1.on.aws/?date=2025-10-23"
```

**Sample JSON Response**
```json
{
  "date": "2025-10-23",
  "hours_found": 12,
  "hourly_breakdown": {
    "00": 4,
    "01": 4,
    "02": 4,
    "03": 3,
    "04": 4,
    "05": 2
  },
  "total_files": 21
}
```

---

## 🧠 Notes & Recommendations

- **EventBridge** triggers the Aggregator daily at **06:00 AM IST**  
  (`cron(30 0 * * ? *)`)
- **Dashboard** can be opened from anywhere — public URL, no auth.  
- **Hourly Checker** is handy for verifying collector uptime & S3 data completeness.
- **PowerShell tip:** avoid `curl -X`; use `Invoke-WebRequest` instead.
- **IAM Policies:**  
  - Aggregator → `S3FullAccessPolicy`  
  - Dashboard & Checker → `S3ReadPolicy`
