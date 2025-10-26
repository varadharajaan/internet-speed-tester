# S3 Bucket Configuration Quick Reference

## 📦 Bucket Names (Default)

```
Daily:   vd-speed-test
Weekly:  vd-speed-test-weekly-prod
Monthly: vd-speed-test-monthly-prod
Yearly:  vd-speed-test-yearly-prod
```

## 🔧 Override via Environment Variables

### Windows PowerShell
```powershell
$env:S3_BUCKET = "my-bucket"
$env:S3_BUCKET_WEEKLY = "my-weekly"
$env:S3_BUCKET_MONTHLY = "my-monthly"
$env:S3_BUCKET_YEARLY = "my-yearly"
```

### Linux/Mac
```bash
export S3_BUCKET="my-bucket"
export S3_BUCKET_WEEKLY="my-weekly"
export S3_BUCKET_MONTHLY="my-monthly"
export S3_BUCKET_YEARLY="my-yearly"
```

## 📝 config.json Example

```json
{
  "s3_bucket": "vd-speed-test",
  "s3_bucket_weekly": "vd-speed-test-weekly-prod",
  "s3_bucket_monthly": "vd-speed-test-monthly-prod",
  "s3_bucket_yearly": "vd-speed-test-yearly-prod"
}
```

## 🧪 Test Configuration

```bash
# Run test suite
python test_s3_buckets.py

# Or check in Python
python -c "from lambda_function import S3_BUCKET, S3_BUCKET_WEEKLY, S3_BUCKET_MONTHLY, S3_BUCKET_YEARLY; print(f'Daily: {S3_BUCKET}\nWeekly: {S3_BUCKET_WEEKLY}\nMonthly: {S3_BUCKET_MONTHLY}\nYearly: {S3_BUCKET_YEARLY}')"
```

## 📊 Bucket Usage Matrix

| Component | Daily | Weekly | Monthly | Yearly |
|-----------|:-----:|:------:|:-------:|:------:|
| speed_collector.py | ✅ | - | - | - |
| lambda_function.py | ✅ | ✅ | ✅ | ✅ |
| app.py | ✅ | ⚠️ | ⚠️ | ⚠️ |
| lambda_hourly_check.py | ✅ | - | - | - |

✅ = Active  
⚠️ = Configured but not yet used  
\- = Not applicable

## 🔄 Priority Order

1. **Environment Variables** ← Highest
2. **config.json**
3. **Default Values** ← Lowest

## 📚 Full Documentation

See: `S3_BUCKET_CONFIGURATION.md`
