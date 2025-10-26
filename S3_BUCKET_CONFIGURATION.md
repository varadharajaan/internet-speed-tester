# S3 Bucket Configuration

## Overview

The project now uses separate S3 buckets for different aggregation levels, allowing for better data organization and lifecycle management.

## Bucket Structure

| Aggregation Level | Config Key | Default Value | Purpose |
|------------------|------------|---------------|---------|
| **Daily/Minute** | `s3_bucket` | `vd-speed-test` | Stores minute-level raw data and daily aggregations |
| **Weekly** | `s3_bucket_weekly` | `vd-speed-test-weekly-prod` | Stores weekly rollup summaries |
| **Monthly** | `s3_bucket_monthly` | `vd-speed-test-monthly-prod` | Stores monthly rollup summaries |
| **Yearly** | `s3_bucket_yearly` | `vd-speed-test-yearly-prod` | Stores yearly rollup summaries |

## Configuration Priority

For all bucket configurations, the system follows this priority order:
1. **Environment Variables** (highest priority)
2. **config.json** values
3. **Default hardcoded values** (fallback)

## Environment Variable Overrides

You can override any bucket configuration using environment variables:

```bash
# Windows PowerShell
$env:S3_BUCKET = "my-custom-bucket"
$env:S3_BUCKET_WEEKLY = "my-weekly-bucket"
$env:S3_BUCKET_MONTHLY = "my-monthly-bucket"
$env:S3_BUCKET_YEARLY = "my-yearly-bucket"

# Linux/Mac
export S3_BUCKET="my-custom-bucket"
export S3_BUCKET_WEEKLY="my-weekly-bucket"
export S3_BUCKET_MONTHLY="my-monthly-bucket"
export S3_BUCKET_YEARLY="my-yearly-bucket"
```

## File-Specific Usage

### Files Using All Bucket Configurations

**1. lambda_function.py**
- Uses `S3_BUCKET` for reading daily data and writing daily aggregations
- Uses `S3_BUCKET_WEEKLY` for writing weekly rollup summaries
- Uses `S3_BUCKET_MONTHLY` for writing monthly rollup summaries
- Uses `S3_BUCKET_YEARLY` for writing yearly rollup summaries

**2. app.py (Dashboard)**
- Uses `S3_BUCKET` for loading daily summaries and minute-level data
- Configured to support `S3_BUCKET_WEEKLY`, `S3_BUCKET_MONTHLY`, `S3_BUCKET_YEARLY` for future dashboard enhancements

**3. daily_aggregator_local.py**
- Imports bucket configurations from `lambda_function.py`
- Displays all bucket names for verification
- Uses `S3_BUCKET` for daily aggregation uploads

### Files Using Only Daily Bucket

**4. speed_collector.py**
- Uses only `S3_BUCKET` (minute-level data collection)
- Doesn't need weekly/monthly/yearly buckets

**5. lambda_hourly_check.py**
- Uses only `S3_BUCKET` (hourly coverage verification)
- Only checks minute-level data availability

## config.json Example

```json
{
  "expected_speed_mbps": 200,
  "tolerance_percent": 10,
  "s3_bucket": "vd-speed-test",
  "s3_bucket_weekly": "vd-speed-test-weekly-prod",
  "s3_bucket_monthly": "vd-speed-test-monthly-prod",
  "s3_bucket_yearly": "vd-speed-test-yearly-prod",
  "aws_region": "ap-south-1",
  "timezone": "Asia/Kolkata",
  "log_level": "INFO",
  "log_max_bytes": 10485760,
  "log_backup_count": 5,
  "speedtest_timeout": 180,
  "public_ip_api": "https://api.ipify.org"
}
```

## Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    Data Collection Layer                     │
│  speed_collector.py → S3_BUCKET (minute-level data)         │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                  Daily Aggregation Layer                     │
│  lambda_function.py → S3_BUCKET (daily summaries)           │
└──────────────────────┬──────────────────────────────────────┘
                       │
            ┌──────────┴──────────┬──────────────┐
            ▼                     ▼              ▼
   ┌─────────────────┐   ┌─────────────┐   ┌──────────────┐
   │ S3_BUCKET_WEEKLY│   │S3_BUCKET_   │   │ S3_BUCKET_   │
   │                 │   │MONTHLY      │   │ YEARLY       │
   │ Weekly Rollup   │   │Monthly      │   │Yearly Rollup │
   └─────────────────┘   │Rollup       │   └──────────────┘
                         └─────────────┘
```

## Lambda Handler Modes

The `lambda_function.py` Lambda handler supports different modes for aggregation:

```python
# Daily aggregation (default)
event = {"mode": "daily"}

# Weekly aggregation
event = {"mode": "weekly"}

# Monthly aggregation
event = {"mode": "monthly"}

# Yearly aggregation
event = {"mode": "yearly"}
```

Each mode writes to its respective bucket as configured.

## Benefits of Separate Buckets

1. **Lifecycle Management**: Apply different retention policies per aggregation level
2. **Cost Optimization**: Transition older data to cheaper storage classes independently
3. **Access Control**: Grant different permissions per bucket
4. **Monitoring**: Track usage and costs per aggregation level
5. **Backup Strategy**: Implement different backup policies per data importance

## Migration from Old Configuration

Previous configuration used environment-based bucket naming:
- Old: `f"vd-speed-test-weekly-{ENVIRONMENT}"`
- New: Explicit configuration per bucket

To maintain compatibility with existing deployments:
1. Update `config.json` with your current bucket names
2. Or set environment variables with your bucket names
3. Old ENVIRONMENT variable is no longer used for bucket naming

## Troubleshooting

### Issue: Lambda can't find weekly/monthly/yearly buckets

**Solution**: Ensure the buckets are created in your AWS account or update `config.json`/environment variables to match existing bucket names.

### Issue: Permission errors

**Solution**: Verify IAM roles have permissions for all four buckets:
- `S3_BUCKET`
- `S3_BUCKET_WEEKLY`
- `S3_BUCKET_MONTHLY`
- `S3_BUCKET_YEARLY`

### Issue: Config not loading

**Solution**: Verify `config.json` exists in the same directory as your Python files and is valid JSON.

## Testing Configuration

Run this to verify your configuration:

```python
from lambda_function import S3_BUCKET, S3_BUCKET_WEEKLY, S3_BUCKET_MONTHLY, S3_BUCKET_YEARLY

print(f"Daily bucket: {S3_BUCKET}")
print(f"Weekly bucket: {S3_BUCKET_WEEKLY}")
print(f"Monthly bucket: {S3_BUCKET_MONTHLY}")
print(f"Yearly bucket: {S3_BUCKET_YEARLY}")
```

Or run:
```bash
python daily_aggregator_local.py
```

This will display all bucket configurations before running aggregation.
