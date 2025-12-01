# Dashboard Mode Quick Reference

## 📊 Available Modes

| Mode | Data Source | Bucket | Period Filter | Best For |
|------|-------------|--------|---------------|----------|
| **15-min** | Minute-level raw data | `s3_bucket` | ✅ Yes (1-360 days) | Real-time analysis, troubleshooting |
| **Hourly** | Hourly aggregations | `s3_bucket_hourly` | ✅ Yes (1-360 days) | Intraday trends, hour-by-hour comparison |
| **Daily** | Daily aggregations | `s3_bucket` | ✅ Yes (1-360 days) | Week/month trends, day-to-day comparison |
| **Weekly** | Weekly rollups | `s3_bucket_weekly` | ❌ All data | Long-term trends, week-over-week |
| **Monthly** | Monthly rollups | `s3_bucket_monthly` | ❌ All data | Annual trends, month-to-month |
| **Yearly** | Yearly rollups | `s3_bucket_yearly` | ❌ All data | Multi-year trends, YoY comparison |

## 🔧 Lambda Modes

Trigger different aggregations:

```python
# Hourly (every hour at :05)
{"mode": "hourly"}

# Daily (default, daily at 00:30 UTC)
{"mode": "daily"} or {}

# Weekly (Monday at 01:00 UTC)
{"mode": "weekly"}

# Monthly (1st of month at 01:00 UTC)
{"mode": "monthly"}

# Yearly (Jan 1 at 01:00 UTC)
{"mode": "yearly"}
```

## 📈 Data Points

| Mode | Records | Aggregation | Example |
|------|---------|-------------|---------|
| 15-min | 96/day | None | 2025-10-26 14:15 |
| Hourly | 24/day | 4 → 1 | 2025-10-26 14:00 |
| Daily | 1/day | 96 → 1 | 2025-10-26 |
| Weekly | ~52/year | 7 → 1 | 2025-W43 (Oct 20-26) |
| Monthly | 12/year | ~30 → 1 | 2025-10 |
| Yearly | 1/year | 12 → 1 | 2025 |

## 🌐 Dashboard URLs

```
# View last 7 days (daily)
http://localhost:8080/?mode=daily&days=7

# View last 24 hours (hourly)
http://localhost:8080/?mode=hourly&days=1

# View last 7 days (15-min granularity)
http://localhost:8080/?mode=minute&days=7

# View all weeks
http://localhost:8080/?mode=weekly

# View all months
http://localhost:8080/?mode=monthly

# View all years
http://localhost:8080/?mode=yearly

# With custom threshold
http://localhost:8080/?mode=daily&days=30&threshold=150
```

## 💾 S3 Structure

```
📁 vd-speed-test (daily/minute)
   └── aggregated/year=2025/month=202510/day=20251026/speed_summary_20251026.json
   └── year=2025/month=202510/day=20251026/hour=2025102614/minute=202510261415/speed_data_*.json

📁 vd-speed-test-hourly-prod
   └── aggregated/year=2025/month=202510/day=20251026/hour=2025102614/hourly_summary_2025102614.json

📁 vd-speed-test-weekly-prod
   └── aggregated/year=2025/week=2025W43/weekly_summary_2025W43.json

📁 vd-speed-test-monthly-prod
   └── aggregated/year=2025/month=202510/monthly_summary_202510.json

📁 vd-speed-test-yearly-prod
   └── aggregated/year=2025/yearly_summary_2025.json
```

## ⏱️ EventBridge Schedules

```yaml
# Hourly aggregation
cron(5 * * * ? *)          # Every hour at :05

# Daily aggregation
cron(0 1 * * ? *)          # Daily at 01:00 UTC

# Weekly aggregation
cron(0 1 ? * MON *)        # Mondays at 01:00 UTC

# Monthly aggregation
cron(0 1 1 * ? *)          # 1st of month at 01:00 UTC

# Yearly aggregation
cron(0 1 1 1 ? *)          # Jan 1 at 01:00 UTC
```

## 🎯 Use Cases

### 15-min Mode
- Troubleshooting specific outages
- Monitoring real-time performance
- Identifying exact failure times
- Validating ISP SLA compliance

### Hourly Mode
- Analyzing daily patterns
- Peak/off-peak comparisons
- Hourly performance tracking
- Intraday trending

### Daily Mode
- Weekly/monthly trend analysis
- Day-to-day consistency checks
- Best/worst day identification
- Regular performance monitoring

### Weekly Mode
- Month-over-month comparison
- Identifying weekly patterns
- Long-term trend analysis
- Quarterly reporting

### Monthly Mode
- Annual performance review
- Seasonal pattern analysis
- Budget/planning decisions
- Year-end reporting

### Yearly Mode
- Multi-year trends
- ISP contract renewals
- Historical performance
- Strategic planning

## 🔑 Quick Commands

```bash
# Test configuration
python -c "from lambda_function import S3_BUCKET_HOURLY; print(S3_BUCKET_HOURLY)"

# Run local aggregation
python daily_aggregator_local.py

# Start dashboard
python app.py

# Test lambda locally
python -c "from lambda_function import aggregate_hourly; print(aggregate_hourly())"
```

## 📝 Configuration Priority

1. **Environment Variables** (highest)
2. **config.json**
3. **DEFAULT_CONFIG** (lowest)

Override any bucket:
```bash
export S3_BUCKET_HOURLY="my-custom-hourly-bucket"
```
