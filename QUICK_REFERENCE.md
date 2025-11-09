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
# List all weekly summaries
aws s3 ls s3://vd-speed-test-weekly-prod/aggregated/ --recursive

# Download this week's summary
aws s3 cp s3://vd-speed-test-weekly-prod/aggregated/year=2025/week=2025W44/speed_test_summary.json ./week44.json

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
- **Adjust the "Expected Speed"** threshold per view for different standards

## 📞 Need Help?

- Check CloudWatch Logs: `/aws/lambda/vd-speedtest-daily-aggregator-prod`
- Verify S3 buckets have data: `aws s3 ls s3://vd-speed-test-weekly-prod/aggregated/`
- Trigger manual aggregation: `curl "https://c5jziahxp5ysapj2ioroeaajfe0qboqs.lambda-url.ap-south-1.on.aws/?mode=weekly"`
