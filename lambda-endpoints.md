# 🧪 Lambda Function URLs — API & Dashboard Access

Your deployment created the following **Lambda Function URLs and log groups**:

| Function | Purpose | URL / Log Group |
|-----------|----------|----------------|
| **Dashboard (Flask)** | Interactive HTML dashboard (daily & 15-min trend visualization) | 🔗 [DashboardFunctionUrl](https://cdmrtrsdbh5pg4w7iymqgkycv40rglcc.lambda-url.ap-south-1.on.aws/) |
| **Hourly Checker** | Returns hourly/minute folder counts for a given date | 🪵 Log group → `/aws/lambda/vd-speedtest-hourly-checker-prod` |
| **Logs Insights Console** | View saved queries in CloudWatch | 🔗 [CloudWatch Logs Insights](https://console.aws.amazon.com/cloudwatch/home?region=ap-south-1#logsV2:logs-insights) |

---

## 📊 Dashboard (Flask + Chart.js)

**Purpose:**  
Visualizes your daily or 15-minute data interactively with anomaly highlighting and zooming.

### ➤ Browser
Open directly:
```
  https://cdmrtrsdbh5pg4w7iymqgkycv40rglcc.lambda-url.ap-south-1.on.aws/
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
| **Daily summary (7 days)** | [link](https://cdmrtrsdbh5pg4w7iymqgkycv40rglcc.lambda-url.ap-south-1.on.aws/?days=7) |
| **15-minute detail (2 days)** | [link](https://cdmrtrsdbh5pg4w7iymqgkycv40rglcc.lambda-url.ap-south-1.on.aws/?mode=minute&days=2) |
| **With URLs & custom threshold** | [link](https://cdmrtrsdbh5pg4w7iymqgkycv40rglcc.lambda-url.ap-south-1.on.aws/?mode=minute&days=7&urls=yes&threshold=150) |

---

## ⏱️ Hourly Checker Lambda

**Purpose:**  
Checks raw minute-level folders for a given date and reports how many **hours** and **15-minute intervals** were captured.

### Log Group
```
/aws/lambda/vd-speedtest-hourly-checker-prod
```

### ➤ Example Query
```
https://cdmrtrsdbh5pg4w7iymqgkycv40rglcc.lambda-url.ap-south-1.on.aws/?date=2025-10-23
```

### ➤ Linux/macOS (curl)
```
curl "https://cdmrtrsdbh5pg4w7iymqgkycv40rglcc.lambda-url.ap-south-1.on.aws/?date=2025-10-23"
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

## 📋 CloudWatch Logs & Monitoring

### Log Groups
- **Dashboard** → `/aws/lambda/vd-speedtest-dashboard-prod`
- **Hourly Checker** → `/aws/lambda/vd-speedtest-hourly-checker-prod`

### Saved Queries in CloudWatch Logs Insights
Access all saved queries here:  
🔗 [CloudWatch Logs Insights Console](https://console.aws.amazon.com/cloudwatch/home?region=ap-south-1#logsV2:logs-insights)

Look for:
- `vd-speedtest/Aggregator Warnings and Anomalies (prod)`
- `vd-speedtest/Hourly Checker Missing Files (prod)`
- `vd-speedtest/Dashboard Errors (prod)`
- `vd-speedtest/All Functions Errors (prod)`
- `vd-speedtest/Aggregator Performance (prod)`

---

## 🧠 Notes & Recommendations

- **Dashboard** is public — accessible without authentication.
- **Hourly Checker** helps confirm S3 ingestion completeness.
- **Logs Insights** lets you review anomalies, missing S3 data, and error counts.
- **PowerShell Tip:** Use `Invoke-WebRequest` for testing POST/GET requests.
- **IAM Policies:**
  - Dashboard → `S3ReadPolicy`
  - Hourly Checker → `S3ReadPolicy` + List access

### Quick Commands
```bash
# View live logs
sam logs -n vd-speedtest-dashboard-prod --stack-name vd-speedtest-stack --tail
sam logs -n vd-speedtest-hourly-checker-prod --stack-name vd-speedtest-stack --tail

# View stack outputs
aws cloudformation describe-stacks --stack-name vd-speedtest-stack --query 'Stacks[0].Outputs'
```
