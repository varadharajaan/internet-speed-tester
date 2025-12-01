# Speed Test Aggregation Guide

## Overview
Your speed test system already has **full support for weekly/monthly/yearly views**! 🎉

## Dashboard Views

### Accessing Different Time Views

Your dashboard URL: `https://<your-dashboard-lambda-url>/`

**Add these query parameters to switch views:**

1. **15-Minute View** (Raw data every 15 minutes)
   ```
   ?mode=minute&days=7
   ```
   Shows: Last 7 days of 15-minute interval tests

2. **Hourly View** (Aggregated by hour)
   ```
   ?mode=hourly&days=30
   ```
   Shows: Last 30 days, one data point per hour

3. **Daily View** (Default - Aggregated by day)
   ```
   ?mode=daily&days=90
   ```
   Shows: Last 90 days, one data point per day

4. **Weekly View** (Aggregated by week)
   ```
   ?mode=weekly&days=52
   ```
   Shows: Last 52 weeks, one data point per week
   
5. **Monthly View** (Aggregated by month)
   ```
   ?mode=monthly&days=12
   ```
   Shows: Last 12 months, one data point per month

6. **Yearly View** (Aggregated by year)
   ```
   ?mode=yearly&days=10
   ```
   Shows: Last 10 years, one data point per year

### Using the Dashboard UI

The mode selector is already built into your dashboard header:

```
Mode: [Dropdown with: 15-min | Hourly | Daily | Weekly | Monthly | Yearly]
Period: [Dropdown with appropriate periods for selected mode]
```

Simply:
1. Select your desired mode from the dropdown
2. Select the time period (e.g., "Last 52 weeks" for weekly view)
3. Click "Apply"

## API Endpoints

### 1. Aggregator Lambda (Trigger Aggregations)

**URL:** `https://c5jziahxp5ysapj2ioroeaajfe0qboqs.lambda-url.ap-south-1.on.aws/`

**Trigger different aggregations:**

```bash
# Daily aggregation (default)
curl "https://c5jziahxp5ysapj2ioroeaajfe0qboqs.lambda-url.ap-south-1.on.aws/?mode=daily"

# Hourly aggregation
curl "https://c5jziahxp5ysapj2ioroeaajfe0qboqs.lambda-url.ap-south-1.on.aws/?mode=hourly"

# Weekly aggregation
curl "https://c5jziahxp5ysapj2ioroeaajfe0qboqs.lambda-url.ap-south-1.on.aws/?mode=weekly"

# Monthly aggregation
curl "https://c5jziahxp5ysapj2ioroeaajfe0qboqs.lambda-url.ap-south-1.on.aws/?mode=monthly"

# Yearly aggregation
curl "https://c5jziahxp5ysapj2ioroeaajfe0qboqs.lambda-url.ap-south-1.on.aws/?mode=yearly"
```

**Response Example:**
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
    "records_aggregated": 228,
    "days": 7,
    "anomalies_count": 3
  }
}
```

### 2. Hourly Checker Lambda (Check Data Coverage)

**URL:** `https://jlbqijazj3b4c7p57siqls6due0tumve.lambda-url.ap-south-1.on.aws/`

**Check hourly coverage for a specific date:**

```bash
curl "https://jlbqijazj3b4c7p57siqls6due0tumve.lambda-url.ap-south-1.on.aws/?date=2025-11-02"
```

**Response:**
```json
{
  "date": "2025-11-02",
  "total_hours_found": 4,
  "total_records": 19,
  "hours": {
    "2025110217": 4,
    "2025110218": 2,
    "2025110221": 1,
    "2025110222": 2
  }
}
```

### 3. Dashboard API (Get Aggregated Data as JSON)

**URL:** `https://<your-dashboard-url>/api/data`

**Get different aggregation levels:**

```bash
# Last 7 days (daily aggregation)
curl "https://<your-dashboard-url>/api/data?mode=daily&days=7"

# Last 52 weeks (weekly aggregation)
curl "https://<your-dashboard-url>/api/data?mode=weekly&days=52"

# Last 12 months (monthly aggregation)
curl "https://<your-dashboard-url>/api/data?mode=monthly&days=12"

# Last 10 years (yearly aggregation)
curl "https://<your-dashboard-url>/api/data?mode=yearly&days=10"
```

## S3 Bucket Structure

Your aggregated data is stored in separate S3 buckets:

### Daily Aggregations
**Bucket:** `vd-speed-test`
```
s3://vd-speed-test/aggregated/
  year=2025/
    month=202511/
      day=20251102/
        speed_test_summary.json
```

### Hourly Aggregations
**Bucket:** `vd-speed-test-hourly-prod`
```
s3://vd-speed-test-hourly-prod/aggregated/
  year=2025/
    month=202511/
      day=20251102/
        hour=2025110217/
          speed_test_summary.json
```

### Weekly Aggregations
**Bucket:** `vd-speed-test-weekly-prod`
```
s3://vd-speed-test-weekly-prod/aggregated/
  year=2025/
    week=2025W44/
      speed_test_summary.json
```

### Monthly Aggregations
**Bucket:** `vd-speed-test-monthly-prod`
```
s3://vd-speed-test-monthly-prod/aggregated/
  year=2025/
    month=202511/
      speed_test_summary.json
```

### Yearly Aggregations
**Bucket:** `vd-speed-test-yearly-prod`
```
s3://vd-speed-test-yearly-prod/aggregated/
  year=2025/
    speed_test_summary.json
```

## Accessing S3 Data Directly

### Using AWS CLI

```bash
# List all weekly aggregations
aws s3 ls s3://vd-speed-test-weekly-prod/aggregated/ --recursive

# Download a specific weekly summary
aws s3 cp s3://vd-speed-test-weekly-prod/aggregated/year=2025/week=2025W44/speed_test_summary.json ./

# List all monthly aggregations
aws s3 ls s3://vd-speed-test-monthly-prod/aggregated/ --recursive

# Download a specific monthly summary
aws s3 cp s3://vd-speed-test-monthly-prod/aggregated/year=2025/month=202511/speed_test_summary.json ./
```

### Using Python (boto3)

```python
import boto3
import json

s3 = boto3.client('s3', region_name='ap-south-1')

# Get weekly summary
response = s3.get_object(
    Bucket='vd-speed-test-weekly-prod',
    Key='aggregated/year=2025/week=2025W44/speed_test_summary.json'
)
weekly_data = json.loads(response['Body'].read())
print(json.dumps(weekly_data, indent=2))

# Get monthly summary
response = s3.get_object(
    Bucket='vd-speed-test-monthly-prod',
    Key='aggregated/year=2025/month=202511/speed_test_summary.json'
)
monthly_data = json.loads(response['Body'].read())
print(json.dumps(monthly_data, indent=2))
```

## Automated Schedules

Your aggregations run automatically via EventBridge:

| Aggregation | Schedule | Time (IST) | Description |
|-------------|----------|------------|-------------|
| **Hourly** | Every hour at :10 | XX:10 IST | Aggregates last hour's 15-min data |
| **Daily** | Daily at 01:00 UTC | 06:30 IST | Aggregates yesterday's minute-level data |
| **Weekly** | Monday at 01:00 UTC | 06:30 IST | Aggregates last Mon-Sun week |
| **Monthly** | 1st at 01:00 UTC | 1st 06:30 IST | Aggregates previous month |
| **Yearly** | Jan 1 at 01:00 UTC | 06:30 IST | Aggregates last year |

## Data Retention Policies

| Aggregation | Retention Period |
|-------------|------------------|
| **Hourly** | 90 days |
| **Weekly** | 730 days (2 years) |
| **Monthly** | 1,825 days (5 years) |
| **Yearly** | 3,650 days (10 years) |

## Example Use Cases

### 1. Compare This Week vs Last Week

```bash
# Trigger weekly aggregation to ensure latest data
curl "https://c5jziahxp5ysapj2ioroeaajfe0qboqs.lambda-url.ap-south-1.on.aws/?mode=weekly"

# View in dashboard
# Navigate to: ?mode=weekly&days=2
```

### 2. See Monthly Trends Over the Year

```bash
# View last 12 months
# Navigate to: ?mode=monthly&days=12
```

### 3. Check Long-Term Performance

```bash
# View yearly trends
# Navigate to: ?mode=yearly&days=5
```

### 4. Detailed Analysis of a Specific Day

```bash
# Check hourly coverage
curl "https://jlbqijazj3b4c7p57siqls6due0tumve.lambda-url.ap-south-1.on.aws/?date=2025-11-02"

# View hourly breakdown in dashboard
# Navigate to: ?mode=hourly&days=1
```

## Troubleshooting

### No Weekly/Monthly/Yearly Data?

1. **Trigger aggregations manually:**
   ```bash
   curl "https://c5jziahxp5ysapj2ioroeaajfe0qboqs.lambda-url.ap-south-1.on.aws/?mode=weekly"
   curl "https://c5jziahxp5ysapj2ioroeaajfe0qboqs.lambda-url.ap-south-1.on.aws/?mode=monthly"
   ```

2. **Check if daily data exists:**
   ```bash
   aws s3 ls s3://vd-speed-test/aggregated/ --recursive
   ```

3. **Check CloudWatch logs:**
   ```bash
   aws logs tail /aws/lambda/vd-speedtest-daily-aggregator-prod --follow
   ```

### Dashboard Shows Empty Chart?

- Ensure you've collected enough data for the selected period
- Try switching to a shorter period (e.g., "Last 7 days" instead of "Last 30 days")
- Check if aggregations have run (see CloudWatch logs)

## Summary

✅ **Your dashboard already supports all aggregation levels!**
✅ **No additional code needed - just use the mode selector**
✅ **API endpoints available for programmatic access**
✅ **Automated schedules keep data fresh**
✅ **Direct S3 access for custom analysis**

Navigate to your dashboard and try switching between modes! 🚀
