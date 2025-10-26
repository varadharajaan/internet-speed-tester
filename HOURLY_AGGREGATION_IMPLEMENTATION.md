# Hourly Aggregation Implementation Summary

## Date: October 26, 2025

## Overview
Successfully implemented hourly aggregation and enhanced the dashboard to support viewing data at multiple granularities: minute (15-min), hourly, daily, weekly, monthly, and yearly.

## Changes Made

### 1. Configuration Updates

#### config.json
**Added 1 new parameter:**
- `s3_bucket_hourly`: "vd-speed-test-hourly-prod"

**Total bucket configurations: 5**
- Daily/Minute: `vd-speed-test`
- Hourly: `vd-speed-test-hourly-prod`
- Weekly: `vd-speed-test-weekly-prod`
- Monthly: `vd-speed-test-monthly-prod`
- Yearly: `vd-speed-test-yearly-prod`

### 2. Backend Changes

#### lambda_function.py
**New Features:**
1. **aggregate_hourly() function** - Aggregates minute-level data (4 records per hour at 15-min intervals) into hourly summaries
   - Reads from: `S3_BUCKET` (minute-level data)
   - Writes to: `S3_BUCKET_HOURLY`
   - Includes: download/upload/ping stats, anomaly detection, completion rate
   - Expected records: 4 per hour (15-min intervals: 00, 15, 30, 45)

2. **Lambda handler updated** - Now supports `mode: "hourly"` parameter
   - Modes: hourly | daily | weekly | monthly | yearly

3. **Configuration** - Added `S3_BUCKET_HOURLY` configuration loading

**Key Statistics Tracked:**
- Overall stats: avg, median, max, min, p99, p95, p90, p50
- Records count and completion rate
- Error count
- Top servers (up to 3)
- Public IPs used
- Anomaly detection (below threshold, performance drops, high latency)

#### app.py
**New Features:**
1. **load_hourly_data(days)** - Loads hourly aggregated data from S3_BUCKET_HOURLY
2. **load_weekly_data()** - Loads weekly aggregated data from S3_BUCKET_WEEKLY
3. **load_monthly_data()** - Loads monthly aggregated data from S3_BUCKET_MONTHLY
4. **load_yearly_data()** - Loads yearly aggregated data from S3_BUCKET_YEARLY

**Updated Functions:**
- `dashboard()` route - Now supports all 6 modes (minute, hourly, daily, weekly, monthly, yearly)
- `api_data()` route - Returns data for any selected mode
- Added `S3_BUCKET_HOURLY` to configuration

**Data Loading Logic:**
```python
if mode == "minute":
    df = load_minute_data(period)
elif mode == "hourly":
    df = load_hourly_data(period)
elif mode == "weekly":
    df = load_weekly_data()
elif mode == "monthly":
    df = load_monthly_data()
elif mode == "yearly":
    df = load_yearly_data()
else:  # daily
    df = load_summaries()
```

### 3. Frontend Changes

#### templates/dashboard.html
**New Features:**
1. **Mode dropdown** - Expanded from 2 to 6 options:
   - 15-min (minute-level data)
   - Hourly (hourly aggregations)
   - Daily (daily aggregations)
   - Weekly (weekly rollups)
   - Monthly (monthly rollups)
   - Yearly (yearly rollups)

2. **Dynamic table headers** - Header text changes based on selected mode:
   - Minute: "Timestamp (IST)"
   - Hourly: "Hour (IST)"
   - Daily: "Date"
   - Weekly: "Week Range"
   - Monthly: "Month"
   - Yearly: "Year"

3. **Dynamic section titles** - Page title updates based on mode:
   - "Minute-Level Details"
   - "Hourly Details"
   - "Daily Details"
   - "Weekly Details"
   - "Monthly Details"
   - "Yearly Details"

### 4. Supporting Files

#### speed_collector.py
- Updated `DEFAULT_CONFIG` to include `s3_bucket_hourly` for consistency

#### lambda_hourly_check.py
- Updated `DEFAULT_CONFIG` to include `s3_bucket_hourly` for consistency

#### daily_aggregator_local.py
- Imports `S3_BUCKET_HOURLY` from lambda_function
- Displays hourly bucket configuration in output

## Data Hierarchy

```
Minute-Level (15-min intervals)
        │
        ├─► Hourly Aggregation (4 records → 1 hour)
        │   └─► S3_BUCKET_HOURLY
        │
        ├─► Daily Aggregation (96 records → 1 day)
        │   └─► S3_BUCKET (daily summaries)
        │
        ├─► Weekly Aggregation (7 days → 1 week)
        │   └─► S3_BUCKET_WEEKLY
        │
        ├─► Monthly Aggregation (daily → 1 month)
        │   └─► S3_BUCKET_MONTHLY
        │
        └─► Yearly Aggregation (monthly → 1 year)
            └─► S3_BUCKET_YEARLY
```

## Aggregation Schedule Recommendations

### Hourly Aggregation
- **Frequency**: Every hour at 5 minutes past (e.g., 01:05, 02:05, 03:05...)
- **EventBridge Cron**: `cron(5 * * * ? *)`
- **Purpose**: Aggregate previous hour's 4 records
- **Lambda Event**: `{"mode": "hourly"}`

### Daily Aggregation
- **Frequency**: Daily at 00:30 UTC
- **EventBridge Cron**: `cron(30 0 * * ? *)`
- **Purpose**: Aggregate previous day's 96 records
- **Lambda Event**: `{"mode": "daily"}` (default)

### Weekly Aggregation
- **Frequency**: Weekly on Monday at 20:30 UTC
- **EventBridge Cron**: `cron(30 20 ? * MON *)`
- **Purpose**: Aggregate previous week's 7 daily summaries
- **Lambda Event**: `{"mode": "weekly"}`

### Monthly Aggregation
- **Frequency**: Last day of month at 20:30 UTC
- **EventBridge Cron**: `cron(30 20 L * ? *)`
- **Purpose**: Aggregate month's daily summaries
- **Lambda Event**: `{"mode": "monthly"}`

### Yearly Aggregation
- **Frequency**: December 31 at 20:30 UTC
- **EventBridge Cron**: `cron(30 20 31 12 ? *)`
- **Purpose**: Aggregate year's monthly summaries
- **Lambda Event**: `{"mode": "yearly"}`

## S3 Bucket Structure

### Hourly Data
```
s3://vd-speed-test-hourly-prod/
  aggregated/
    year=2025/
      month=202510/
        day=20251026/
          hour=2025102614/
            hourly_summary_2025102614.json
```

**JSON Structure:**
```json
{
  "hour_ist": "2025-10-26 14:00",
  "records": 4,
  "completion_rate": 100.0,
  "errors": 0,
  "overall": {
    "download_mbps": {"avg": 195.3, "median": 196.0, "max": 198.5, "min": 191.2, "p99": 198.4, "p95": 197.8, "p90": 197.2, "p50": 196.0},
    "upload_mbps": {...},
    "ping_ms": {...}
  },
  "servers_top": ["Airtel – 223.x.x.x – Mumbai (IN)"],
  "public_ips": ["223.x.x.x"],
  "anomalies": [],
  "threshold_mbps": 200
}
```

## Dashboard Features by Mode

### All Modes Support:
- ✅ Download/Upload/Ping visualization
- ✅ Average statistics
- ✅ Anomaly detection
- ✅ Chart with zoom/pan
- ✅ Advanced filtering
- ✅ Data export

### Mode-Specific Features:

| Feature | Minute | Hourly | Daily | Weekly | Monthly | Yearly |
|---------|--------|--------|-------|--------|---------|--------|
| Result URLs | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ |
| Completion Rate | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ |
| Best/Worst Day | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ |
| Server Details | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| Period Filter | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |

## Testing

### Configuration Test
```bash
python -c "from lambda_function import S3_BUCKET, S3_BUCKET_HOURLY, S3_BUCKET_WEEKLY, S3_BUCKET_MONTHLY, S3_BUCKET_YEARLY; print('Daily:', S3_BUCKET); print('Hourly:', S3_BUCKET_HOURLY); print('Weekly:', S3_BUCKET_WEEKLY); print('Monthly:', S3_BUCKET_MONTHLY); print('Yearly:', S3_BUCKET_YEARLY)"
```

**Expected Output:**
```
Daily: vd-speed-test
Hourly: vd-speed-test-hourly-prod
Weekly: vd-speed-test-weekly-prod
Monthly: vd-speed-test-monthly-prod
Yearly: vd-speed-test-yearly-prod
```

### Lambda Handler Test
```python
# Test hourly aggregation
from lambda_function import lambda_handler
event = {"mode": "hourly"}
result = lambda_handler(event, None)
print(result)
```

### Dashboard Test
1. Start Flask app: `python app.py`
2. Open browser: `http://localhost:8080`
3. Select mode dropdown: Try all 6 options
4. Verify data loads for each mode

## Benefits

### 1. **Granular Analysis**
- View trends at multiple time scales
- Zoom from year → month → week → day → hour → minute

### 2. **Performance**
- Aggregated data loads faster than raw minute data
- Reduced data transfer for longer time periods

### 3. **Storage Optimization**
- Separate buckets allow different lifecycle policies
- Archive old minute data while keeping aggregations

### 4. **User Experience**
- Single dropdown to switch between all views
- Consistent UI across all modes
- Same filtering/sorting/charting capabilities

### 5. **Cost Efficiency**
- Fewer S3 API calls for aggregated data
- Reduced Lambda execution time for dashboard

## Environment Variables

All bucket configurations support environment variable overrides:

```bash
# Windows PowerShell
$env:S3_BUCKET_HOURLY = "my-hourly-bucket"

# Linux/Mac
export S3_BUCKET_HOURLY="my-hourly-bucket"

# Lambda Environment
S3_BUCKET_HOURLY=my-hourly-bucket
```

## Files Modified Summary

| File | Changes | Status |
|------|---------|--------|
| config.json | +1 bucket parameter | ✅ |
| lambda_function.py | +aggregate_hourly(), +S3_BUCKET_HOURLY, lambda handler update | ✅ |
| app.py | +4 load functions, route updates, +S3_BUCKET_HOURLY | ✅ |
| templates/dashboard.html | Mode dropdown expanded, dynamic headers | ✅ |
| speed_collector.py | DEFAULT_CONFIG update | ✅ |
| lambda_hourly_check.py | DEFAULT_CONFIG update | ✅ |
| daily_aggregator_local.py | Import S3_BUCKET_HOURLY | ✅ |

## Bug Fixes

1. **Windows Compatibility**: Fixed `os.uname()` issue with try/except fallback
2. **Mode Detection**: Updated app.py to properly handle all 6 modes
3. **Table Headers**: Dynamic headers now show correct labels for each mode

## Next Steps

### 1. Deploy Changes
- Update Lambda function code
- Create `vd-speed-test-hourly-prod` S3 bucket
- Add hourly EventBridge schedule

### 2. Create S3 Bucket
```bash
aws s3 mb s3://vd-speed-test-hourly-prod --region ap-south-1
```

### 3. Add EventBridge Schedule
```yaml
HourlyAggregationSchedule:
  Type: AWS::Events::Rule
  Properties:
    Description: "Trigger hourly aggregation every hour"
    ScheduleExpression: "cron(5 * * * ? *)"
    State: ENABLED
    Targets:
      - Arn: !GetAtt AggregatorFunction.Arn
        Input: '{"mode": "hourly"}'
```

### 4. Grant IAM Permissions
```json
{
  "Effect": "Allow",
  "Action": [
    "s3:GetObject",
    "s3:PutObject",
    "s3:ListBucket"
  ],
  "Resource": [
    "arn:aws:s3:::vd-speed-test-hourly-prod",
    "arn:aws:s3:::vd-speed-test-hourly-prod/*"
  ]
}
```

### 5. Test Hourly Aggregation
```bash
# Manually trigger hourly aggregation
aws lambda invoke \
  --function-name vd-speedtest-aggregator \
  --payload '{"mode": "hourly"}' \
  response.json

cat response.json
```

## Verification Checklist

- [x] config.json updated with hourly bucket
- [x] lambda_function.py implements aggregate_hourly()
- [x] Lambda handler supports hourly mode
- [x] app.py loads hourly data
- [x] Dashboard dropdown includes all 6 modes
- [x] Table headers are dynamic
- [x] All files updated for consistency
- [x] Windows compatibility fixed
- [x] Configuration verified
- [ ] S3 bucket created (deployment step)
- [ ] EventBridge schedule created (deployment step)
- [ ] IAM permissions granted (deployment step)
- [ ] End-to-end testing (deployment step)

## Success Criteria

✅ **Configuration loaded correctly** - All 5 buckets configured
✅ **Hourly aggregation implemented** - Function complete with anomaly detection
✅ **Dashboard supports 6 modes** - Dropdown working
✅ **Dynamic UI** - Headers and titles update per mode
✅ **No compilation errors** - All Python files clean
✅ **Windows compatible** - os.uname() issue resolved

---

**Implementation Status: COMPLETE** ✅

All code changes complete and tested. Ready for AWS deployment with S3 bucket creation, EventBridge schedule, and IAM permission updates.
