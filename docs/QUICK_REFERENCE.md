# Speed Test Dashboard - Quick Reference Card

## 🎯 Your URLs

| Service | URL | Purpose |
|---------|-----|---------|
| **Dashboard** | `https://<dashboard-url>/` | Visual web interface |
| **Aggregator** | `https://c5jziahxp5ysapj2ioroeaajfe0qboqs.lambda-url.ap-south-1.on.aws/` | Trigger aggregations |
| **Hourly Checker** | `https://jlbqijazj3b4c7p57siqls6due0tumve.lambda-url.ap-south-1.on.aws/` | Check data coverage |

## 🔄 Dashboard Views

### Using the UI Dropdown

```
Mode: [15-min ▼]  Period: [Last 7 days ▼]  [Apply]
       │                    │
       └─ Select view       └─ Select timeframe
```

### Using URL Parameters

| View | URL Parameter | Shows |
|------|---------------|-------|
| **Raw 15-min** | `?mode=minute&days=7` | Every 15-min test |
| **Hourly** | `?mode=hourly&days=30` | One point per hour |
| **Daily** | `?mode=daily&days=90` | One point per day (default) |
| **Weekly** | `?mode=weekly&days=52` | One point per week |
| **Monthly** | `?mode=monthly&days=12` | One point per month |
| **Yearly** | `?mode=yearly&days=10` | One point per year |

### Multi-Host Filtering

| Filter | URL Parameter | Shows |
|--------|---------------|-------|
| **All Hosts** | (default) | Combined data from all hosts |
| **Specific Host** | `?host=home-primary` | Only data from that host |

**Example:** `?mode=weekly&days=52&host=home-primary`

### Performance Parameters

| Parameter | Example | Effect |
|-----------|---------|--------|
| **Async Load** | `?async=1` | Instant page load, data loads progressively |
| **Force Refresh** | `?force_refresh=1` | Bypass 2-minute cache, get fresh data |
| **Combined** | `?async=1&force_refresh=1` | Both features together |

**Note:** Dashboard caches data for 2 minutes. Use `force_refresh=1` to get latest data immediately.

## 📊 Aggregation Levels Explained

```
Raw Data (15-min intervals)
    ↓
[Hourly Aggregation]  ← 4 tests per hour → One hourly average
    ↓
[Daily Aggregation]   ← 24 hours → One daily average
    ↓
[Weekly Aggregation]  ← 7 days → One weekly average
    ↓
[Monthly Aggregation] ← ~30 days → One monthly average
    ↓
[Yearly Aggregation]  ← 12 months → One yearly average
```

## 🚀 Common Tasks

### View Last Month's Performance
```
Dashboard: ?mode=daily&days=30
```

### Compare Weeks
```
Dashboard: ?mode=weekly&days=8
```
Shows last 8 weeks for comparison

### Check Today's Hourly Coverage
```
Hourly Checker: ?date=2025-11-03
```

### Trigger Weekly Aggregation
```
Aggregator: ?mode=weekly
```

### Get Monthly Data as JSON
```
API: /api/data?mode=monthly&days=12
```

## 📁 S3 Bucket Quick Access

```bash
# List all weekly summaries (global)
aws s3 ls s3://vd-speed-test-weekly-prod/aggregated/year=2025/ --recursive

# List weekly summaries for specific host
aws s3 ls s3://vd-speed-test-weekly-prod/aggregated/host=home-primary/year=2025/ --recursive

# Download this week's summary
aws s3 cp s3://vd-speed-test-weekly-prod/aggregated/year=2025/week=2025W44/speed_test_summary.json ./week44.json

# Download host-specific summary
aws s3 cp s3://vd-speed-test-weekly-prod/aggregated/host=home-primary/year=2025/week=2025W44/speed_test_summary.json ./host-week44.json

# View monthly summaries
aws s3 ls s3://vd-speed-test-monthly-prod/aggregated/ --recursive
```

## ⚡ Quick Examples

### Example 1: Check if Last Week Was Better Than This Week
1. Go to dashboard
2. Select Mode: **Weekly**
3. Select Period: **Last 2 weeks**
4. Click **Apply**
5. Compare the two data points in the chart

### Example 2: Find Worst Performing Month
1. Go to dashboard
2. Select Mode: **Monthly**
3. Select Period: **Last 12 months**
4. Click **Apply**
5. Look at the table sorted by Download Speed

### Example 3: See Today's Hourly Pattern
1. Go to dashboard
2. Select Mode: **Hourly**
3. Select Period: **Last 1 day**
4. Click **Apply**
5. Chart shows hourly breakdown

### Example 4: Compare Performance Across Hosts
1. Go to dashboard
2. Select Host: **home-primary** (or any host)
3. Select Mode: **Daily**
4. Select Period: **Last 7 days**
5. Click **Apply**
6. Switch to different host and compare

## 🔔 Automated Schedules

| When | What Happens |
|------|--------------|
| **Every hour at :10** | Hourly aggregation runs |
| **Daily at 06:00 IST** | Daily aggregation runs |
| **Tuesday 02:00 IST** | Weekly aggregation runs |
| **1st of month 02:00 IST** | Monthly aggregation runs |
| **Jan 1 02:00 IST** | Yearly aggregation runs |

## 💡 Pro Tips

- **Use Weekly view** to spot trends without overwhelming detail
- **Use Monthly view** to compare seasonal variations
- **Use Hourly view** to debug specific problem days
- **Filter by connection type** in any view to compare Ethernet vs WiFi
- **Filter by host** to isolate performance issues on specific machines
- **Use "All Hosts"** to see overall network performance
- **Use `async=1`** for instant page load with progressive data loading
- **Adjust the "Expected Speed"** threshold per view for different standards

## �️ Developer Tools

### Tail Lambda Logs
Monitor Lambda function logs in real-time:
```bash
# Tail dashboard logs (default)
python tail_logs.py

# Tail specific Lambda
python tail_logs.py --lambda dashboard    # Dashboard Lambda
python tail_logs.py --lambda daily        # Daily aggregator
python tail_logs.py --lambda hourly       # Hourly checker
python tail_logs.py --lambda all          # All Lambdas

# Control time range
python tail_logs.py --since 30m           # Last 30 minutes
python tail_logs.py --since 1h            # Last 1 hour
python tail_logs.py --since 2d            # Last 2 days

# One-shot (no follow)
python tail_logs.py --since 10m --no-follow
```

### Check Latest Data
View speed test data from S3 with multi-period support:
```bash
# Latest entries
python check_latest.py                    # Last 5 minute entries
python check_latest.py --last 10          # Last 10 entries

# By period
python check_latest.py --period daily --last 7     # Last 7 days
python check_latest.py --period weekly --last 4    # Last 4 weeks
python check_latest.py --period monthly --last 12  # Last 12 months
python check_latest.py --period hourly --last 24   # Last 24 hours
python check_latest.py --period yearly             # Yearly data
```

### Cleanup Duplicates
Find and remove duplicate entries caused by Task Scheduler catch-up runs:
```bash
# Scan for duplicates (dry-run)
python cleanup_duplicates.py                       # Minutes bucket (default)
python cleanup_duplicates.py --period all          # All buckets
python cleanup_duplicates.py --period hourly       # Hourly bucket
python cleanup_duplicates.py --last 100            # Last 100 files only

# Delete duplicates
python cleanup_duplicates.py --delete              # Delete from minutes
python cleanup_duplicates.py --period all --delete # Delete from all buckets
```

### Shared Utilities (s3_speed_utils.py)
Reusable module for S3 speed test operations:
- `S3SpeedConfig` - Centralized bucket and period configuration
- `S3SpeedClient` - S3 operations (list, get, delete)
- `PeriodMixin` - CLI argument parsing for `--period` flag
- `CountMixin` - CLI argument parsing for `--last N` items
- `DryRunMixin` - CLI argument parsing for `--delete` flag
- `DuplicateDetector` - Find duplicates across periods
- `KeyParser` - Parse S3 keys to extract date/time components

## 📞 Need Help?

- **Tail logs in real-time**: `python tail_logs.py --lambda all --since 30m`
- Check CloudWatch Logs: `/aws/lambda/vd-speedtest-daily-aggregator-prod`
- Verify S3 buckets have data: `aws s3 ls s3://vd-speed-test-weekly-prod/aggregated/`
- Trigger manual aggregation: `curl "https://c5jziahxp5ysapj2ioroeaajfe0qboqs.lambda-url.ap-south-1.on.aws/?mode=weekly"`
