# 🚀 vd-speed-test — Internet Speed Logger & Dashboard

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue)]()
[![AWS](https://img.shields.io/badge/AWS-Lambda%20%7C%20S3%20%7C%20CloudWatch-orange)]()
[![Windows](https://img.shields.io/badge/Windows-Compatible-lightgrey)]()
[![License](https://img.shields.io/badge/License-MIT-green)]()

Measure your internet speed **every 15 minutes**, store it in **Amazon S3**, **aggregate daily at 6:00 AM IST** with **AWS Lambda**, monitor with **CloudWatch Logs Insights**, and explore historical trends on a **powerful interactive Flask dashboard** with advanced filtering, accessible **locally** or **via Lambda Function URLs**.

---

## 📦 What's Inside

```
vd-speed-test/
├── 📊 COLLECTION & AGGREGATION
│   ├── speed_collector.py            # Local 15-min collector (Ookla + Python speedtest)
│   ├── daily_aggregator_local.py     # Manual daily aggregator for local testing
│   ├── lambda_function.py            # Daily aggregator Lambda (Function URL + EventBridge)
│   └── lambda_hourly_check.py        # Hourly coverage checker Lambda
│
├── 🌐 DASHBOARD & VISUALIZATION
│   ├── app.py                        # Flask dashboard backend with JSON logging
│   ├── lambda_dashboard.py           # Flask dashboard Lambda wrapper (via Mangum)
│   └── templates/dashboard.html      # Interactive UI with advanced filtering
│
├── ☁️ AWS DEPLOYMENT & MONITORING
│   ├── template.yaml                 # AWS SAM template (3 Lambdas + CloudWatch)
│   ├── lambda-endpoints.md           # API documentation with live URLs
│   └── samconfig.toml                # SAM deployment configuration
│
├── 🔧 CONFIGURATION & AUTOMATION
│   ├── config.json                   # Speed thresholds and tolerance settings
│   ├── requirements.txt              # Python dependencies
│   ├── speed_collector_autostart.xml # Windows Task Scheduler config
│   └── speedtest.exe                 # Ookla speedtest CLI (Windows)
│
└── 📄 DOCUMENTATION
    ├── README.md                     # This comprehensive guide
    └── vd-speed-test-architecture.png # Architecture diagram
```

---

## 🧭 Architecture

![Architecture](vd-speed-test-architecture.png)

```
Local PC (Windows)
  └─ speed_collector.py  ──every 15m──▶  S3 (vd-speed-test)
                                           ├─ minute-level JSONs
                                           └─ aggregated/
AWS Lambda Ecosystem
  ├─ lambda_function.py      ──daily 06:00 IST──▶  aggregated/day=YYYYMMDD/
  ├─ lambda_hourly_check.py  ──on-demand────────▶  hour-by-hour coverage reports
  └─ CloudWatch Logs         ──monitoring──────▶  JSON structured logging
      └─ Logs Insights       ──saved queries───▶  anomaly detection & analysis

Dashboard (local or serverless)
  └─ app.py / lambda_dashboard.py ◀──── reads ─── aggregated/ summaries from S3
      └─ Enhanced UI with filters, zoom, anomaly highlighting
```

---

## 🧠 How It Works

| Component | Description |
|------------|-------------|
| 🖥️ **speed_collector.py** | Runs locally every 15 minutes (aligned to IST quarter-hour). Collects Ookla + Python speedtest results, adds Mbps suffix, and uploads to S3 with JSON logging. |
| ☁️ **lambda_function.py** | Triggered daily at 6:00 AM IST (00:30 UTC). Aggregates previous day's results and writes a summary JSON to `/aggregated/` with comprehensive metrics. |
| ⏱️ **lambda_hourly_check.py** | On-demand Lambda to check hourly coverage for any date. Returns how many 15-min intervals were captured per hour. |
| 🧮 **daily_aggregator_local.py** | Local version of the Lambda aggregator for quick testing and manual runs. |
| 🌐 **app.py** | Flask dashboard with JSON logging, visualizing aggregated speed data, anomalies, and advanced filtering capabilities. |
| ☁️ **lambda_dashboard.py** | Wrapper for running `app.py` on AWS Lambda via Function URL (uses `Mangum` adapter). |
| 🧱 **template.yaml** | Deploys 3 Lambda functions + EventBridge rule + CloudWatch Logs Insights queries in one stack. |
| 🪟 **speed_collector_autostart.xml** | Task Scheduler config to auto-run collector at login or every 15 mins. |
| 📊 **Enhanced Dashboard** | Interactive UI with date filters, speed range filters, provider filters, quick filter checkboxes, chart zoom/pan. |
| 📈 **CloudWatch Integration** | JSON structured logging, saved Logs Insights queries for anomaly detection, metric filters. |

---

## ⚙️ Local Setup (Windows or Mac/Linux)

### 1️⃣ Install Python & Dependencies
```bash
python -m venv .venv && .venv\Scripts\activate  # on Windows
pip install -r requirements.txt
```

### 2️⃣ Configure AWS Credentials
```bash
aws configure
```

Enter:
```
AWS Access Key ID [None]: <your-key>
AWS Secret Access Key [None]: <your-secret>
Default region name [None]: ap-south-1
Default output format [None]: json
```

Verify:
```bash
aws sts get-caller-identity
```

---

### 3️⃣ Run the Collector
```bash
python speed_collector.py
```

Uploads JSON to:
```
s3://vd-speed-test/year=2025/month=202510/day=20251022/...
```

Each JSON includes:
- download/upload speeds (with Mbps suffix)
- ping
- server info
- result URL
- public IP

---

### 4️⃣ Automate with Windows Task Scheduler

Use `speed_collector_autostart.xml`:
1. Edit `<Command>`, `<Arguments>`, and `<WorkingDirectory>` with your path.  
2. Import in **Task Scheduler → Import Task**.  
3. Under **General**, check ✅ “Run with highest privileges.”  
4. Save → Test Run → Verify.  

💡 Use `pythonw.exe` instead of `python.exe` to suppress console windows.

---

### 5️⃣ Run the Enhanced Dashboard Locally

Start the Flask server:
```bash
python app.py
```

Open ➡ [http://localhost:8080](http://localhost:8080)

**New Dashboard Features:**

| Feature | Description |
|---------|-------------|
| 🔍 **Advanced Filters** | Date range, download/upload/ping ranges, server/provider search, IP filtering |
| ⚡ **Quick Filter Checkboxes** | Below threshold, performance drops, high ping, provider-specific filters |
| 📊 **Interactive Charts** | Zoom, pan, toggle between short/full timestamps, threshold line overlay |
| 📈 **Real-time Filter Stats** | Shows "X of Y results" with filter indicators |
| 🎯 **Anomaly Highlighting** | Red points for below-threshold speeds, visual anomaly indicators |
| 📱 **Responsive Design** | Works on desktop, tablet, and mobile devices |

**API Endpoints:**

| Endpoint | Method | Description |
|-----------|--------|-------------|
| `/` | `GET` | Full dashboard UI with enhanced filtering (renders `dashboard.html`) |
| `/data?days=30` | `GET` | JSON data for the last N days (default 30) |
| `/api/data?mode=minute&threshold=150` | `GET` | API endpoint with mode and threshold parameters |
| `/summary` | `GET` | Summary JSON (avg download/upload/ping, anomalies) |
| `/config` | `GET` | Returns configured threshold from `config.json` |
| `/reload` | `POST` | Optional endpoint to refresh cached S3 data |

---

## ☁️ AWS Lambda Deployment (3 Functions + CloudWatch Monitoring)

### 1️⃣ Install SAM CLI
```bash
pip install aws-sam-cli
# or on Windows:
choco install aws-sam-cli
```

### 2️⃣ From project root
```bash
sam build
sam deploy --guided
```

### 3️⃣ When prompted
```
Stack Name: vd-speedtest-stack
AWS Region: ap-south-1
Confirm changes before deploy: Y
Parameter S3BucketName: vd-speed-test
Parameter Environment: prod
```

✅ This deploys:
- **vd-speedtest-daily-aggregator** (daily 6 AM IST aggregation)
- **vd-speedtest-dashboard** (Flask dashboard via Function URL)
- **vd-speedtest-hourly-checker** (coverage verification)
- **CloudWatch Logs Insights** saved queries for monitoring
- **Metric filters** for automated anomaly detection

---

### 4️⃣ Access the Lambda Function URLs

| Lambda | Purpose | URL Example |
|---------|----------|-------------|
| `vd-speedtest-daily-aggregator` | Daily summary aggregator | `https://ra7ljtnqfpehcfaaafy4mvanqi0mxoqv.lambda-url.ap-south-1.on.aws/` |
| `vd-speedtest-dashboard` | Enhanced Flask dashboard served via Lambda | `https://b33l2r7iro5prfqvuppgsbgasy0jivyt.lambda-url.ap-south-1.on.aws/` |
| `vd-speedtest-hourly-checker` | Hourly coverage checker | `https://7mpxatwdutexv7r2azovb7a6uq0fgzai.lambda-url.ap-south-1.on.aws/` |

Open the enhanced dashboard in any browser:
```
https://b33l2r7iro5prfqvuppgsbgasy0jivyt.lambda-url.ap-south-1.on.aws/
```

✅ Same powerful Flask dashboard — now serverless, powered by AWS Lambda with all advanced filtering features.

---

### 5️⃣ Test All Lambda Functions

**Daily Aggregator:**
```bash
curl.exe -X POST https://ra7ljtnqfpehcfaaafy4mvanqi0mxoqv.lambda-url.ap-south-1.on.aws/
```

**Hourly Coverage Checker:**
```bash
curl.exe "https://7mpxatwdutexv7r2azovb7a6uq0fgzai.lambda-url.ap-south-1.on.aws/?date=2025-10-23"
```

**Sample Aggregator Response:**
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
  "s3_key": "aggregated/year=2025/month=202510/day=20251023/speed_summary_20251023.json"
}
```

**Sample Hourly Checker Response:**
```json
{
  "date": "2025-10-23",
  "total_hours_found": 12,
  "total_records": 48,
  "hours": {
    "2025102300": 4,
    "2025102301": 4,
    "2025102302": 4,
    "2025102303": 3
  }
}
```

---

## 🕓 How EventBridge Works

**Cron:**
```
cron(30 0 * * ? *)
```
🕛 00:30 UTC → 06:00 IST  
Runs daily → aggregates previous day → uploads summary to `/aggregated/`

---

## 📊 Enhanced Dashboard Highlights

### 🎯 Filtering & Search Capabilities
- � **Date Range Filters**: Start/end date pickers for custom time periods
- 🚀 **Speed Range Filters**: Min/max download, upload, and ping filters
- 🔍 **Provider/Server Search**: Filter by ISP (Airtel, ACT, RailTel) with autocomplete
- 🌐 **IP Address Filtering**: Search by public IP address patterns
- ⚡ **Quick Filter Checkboxes**: 
  - Below threshold speeds
  - Performance drops (<100 Mbps)
  - High ping (>20ms)
  - Provider-specific filters

### 📈 Interactive Visualization
- 📊 **Zoomable Charts**: Mouse wheel zoom and pan with Chart.js
- 🎨 **Anomaly Highlighting**: Red data points for below-threshold speeds
- 🕒 **Flexible Time Labels**: Toggle between short (HH:MM) and full timestamps
- 📏 **Threshold Line**: Visual red line showing expected speed threshold
- 📱 **Responsive Design**: Works seamlessly on desktop, tablet, and mobile

### 📋 Data Views & Exports
- 🗓️ **Daily vs 15-minute modes**: Switch between aggregated daily summaries and granular 15-min data
- 🔗 **Result URLs**: Optional display of speedtest.net result links
- 📊 **Real-time Filter Statistics**: Shows filtered vs total results
- 🎯 **Performance Metrics**: Average speeds, ping statistics, anomaly counts
- 🏆 **Server Analytics**: Most used servers, IP diversity tracking

---

## 🔍 CloudWatch Logs Insights Integration

The deployment includes **pre-configured CloudWatch Logs Insights queries**:

### 📈 Saved Queries Available

| Query Name | Purpose | Example Use Case |
|------------|---------|------------------|
| **Aggregator Warnings and Anomalies** | Detect performance issues, missing data | Monitor daily aggregation health |
| **Hourly Checker Missing Files** | Find data collection gaps | Verify collector uptime |
| **Dashboard Errors** | Flask application errors | Debug dashboard issues |
| **All Functions Errors** | Cross-function error overview | System-wide monitoring |
| **Aggregator Performance** | Memory usage, execution duration | Optimize Lambda performance |

### 🔧 Access CloudWatch Logs Insights
1. Open AWS Console → CloudWatch → Logs → Insights
2. Select log groups: `/aws/lambda/vd-speedtest-*`
3. Use saved queries or create custom ones
4. Monitor anomalies in real-time

### 📊 Example CloudWatch Queries

**Find Speed Anomalies:**
```sql
fields @timestamp, @message
| filter level in ["ERROR","WARNING"] or message like /Below|Performance Drop|Latency Spike/
| sort @timestamp desc
| limit 100
```

**Monitor Data Collection Gaps:**
```sql
fields @timestamp, @message
| filter @message like /missing|not found|delayed|No data|zero files/
| sort @timestamp desc
| limit 100
```  

---

## 📁 S3 Structure

```
vd-speed-test/
├── year=2025/month=202510/day=20251022/hour=2025102211/minute=202510221115/
│   ├── speed_data_ookla_202510221115_*.json
│   └── speed_data_python_202510221115_*.json
└── aggregated/year=2025/month=202510/day=20251022/speed_summary_20251022.json
```

---

## 🛡️ Monitoring & Automation Extras

| Component | Description | Benefits |
|-----------|-------------|----------|
| **JSON Structured Logging** | All Lambda functions output CloudWatch-compatible JSON logs | Easy querying, automated parsing, metric extraction |
| **Metric Filters** | Automatic CloudWatch metrics from log patterns | Real-time alerting on anomalies, missing data |
| **Rotating File Logs** | Local log files with 10MB rotation, 5 backup files | Debugging without AWS costs, offline analysis |
| **Function URL CORS** | Cross-origin requests enabled for dashboard access | API access from any domain, mobile apps |
| **EventBridge Scheduling** | Reliable daily aggregation with retry policies | No cron job maintenance, automatic error handling |
| **IAM Least Privilege** | Separate read/write permissions per Lambda | Enhanced security, audit compliance |
| **Environment Parameters** | Configurable S3 bucket, regions, log levels | Easy deployment across environments |

### 🧰 Deployment Management

| File | Description |
|------|------------|
| **speed_collector_autostart.xml** | Runs collector every 15 mins silently via Task Scheduler |
| **lambda_dashboard.py** | Flask → AWS Lambda adapter using Mangum |
| **template.yaml** | SAM template to deploy 3 Lambdas + monitoring |
| **lambda-endpoints.md** | Live API documentation with current URLs |
| **samconfig.toml** | Pre-configured deployment settings |
| **config.json** | Speed thresholds and tolerance configuration |

### 📋 Quick Commands Reference

**Local Development:**
```bash
python speed_collector.py          # Run single speed test
python daily_aggregator_local.py   # Test daily aggregation
python app.py                      # Start dashboard locally
```

**AWS Deployment:**
```bash
sam validate                       # Validate template
sam build                         # Build deployment package
sam deploy --guided               # Interactive deployment
sam logs -n vd-speedtest-dashboard-prod --tail  # Stream logs
```

**API Testing:**
```bash
# Test aggregator
curl.exe -X POST https://[aggregator-url]/

# Test hourly checker
curl.exe "https://[checker-url]/?date=2025-10-23"

# View dashboard
start https://[dashboard-url]/
```

---

## 🛡️ Notes & Tips

- Use `pythonw.exe` to suppress CLI window on Windows.
- SAM supports Python 3.12 runtime (set in `template.yaml`).
- For Windows, move project out of `Downloads\Compressed` before building.
- Rotate AWS credentials regularly and use IAM roles where possible.
- Use `curl.exe` (not PowerShell's `curl`) to test Function URLs.
- **CloudWatch Logs retention**: Set to 7-14 days to control costs.
- **Dashboard filtering**: Combine multiple filters for precise analysis.
- **JSON logging**: Enables structured queries in CloudWatch Logs Insights.
- **Threshold tuning**: Adjust in `config.json` for your internet plan.
- **Mobile access**: Dashboard URL works on smartphones for remote monitoring.

### 🚨 Troubleshooting Common Issues

| Issue | Solution |
|-------|----------|
| **Collector not running** | Check Task Scheduler, verify AWS credentials, check `speedtest.log` |
| **Dashboard shows no data** | Verify S3 permissions, check aggregated/ folder exists |
| **Lambda timeout** | Increase timeout in `template.yaml`, check CloudWatch logs |
| **Missing hourly data** | Use hourly checker Lambda to identify gaps |
| **High CloudWatch costs** | Reduce log retention, optimize log level settings |
| **Slow dashboard loading** | Reduce days parameter, use daily mode for large datasets |

### 🔧 Configuration Files

**config.json example:**
```json
{
  "expected_speed_mbps": 200,
  "tolerance_percent": 5,
  "log_level": "INFO"
}
```

**Custom dashboard URLs:**
```
# 15-minute detail for last 2 days
?mode=minute&days=2&threshold=150

# Performance issues only
?mode=minute&days=7&threshold=100

# With result URLs for investigation
?mode=daily&days=30&urls=yes&threshold=200
```

---

## 📝 License

MIT — free to use, modify, and share.  
Contributions welcome!

---

**Made with ❤️ for reliable, human-friendly internet monitoring with enterprise-grade observability.**

## 🚀 Latest Updates

- ✅ **Enhanced Interactive Dashboard** with advanced filtering and real-time statistics
- ✅ **CloudWatch Logs Insights** integration with pre-configured monitoring queries  
- ✅ **Hourly Coverage Checker** Lambda for data completeness verification
- ✅ **JSON Structured Logging** across all components for better observability
- ✅ **Metric Filters & Automated Monitoring** for proactive issue detection
- ✅ **Mobile-Responsive UI** that works seamlessly on all devices
- ✅ **Provider-Specific Filtering** for ISP performance analysis
- ✅ **Chart Zoom & Pan** capabilities for detailed trend analysis
- ✅ **Real-time Filter Statistics** showing current view vs total data
- ✅ **Comprehensive API Documentation** with live endpoint examples