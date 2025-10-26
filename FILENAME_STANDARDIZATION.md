# Standardized Filename Implementation

## Date: October 26, 2025

## Change Summary

**Standardized all aggregation output files to use the same filename: `speed_test_summary.json`**

### Before (Mixed Naming)
```
Hourly:  hourly_summary_{hour}.json
Daily:   speed_summary_{day}.json
Weekly:  weekly_summary_{week_label}.json
Monthly: monthly_summary_{month_tag}.json
Yearly:  yearly_summary_{year}.json
```

### After (Standardized)
```
Hourly:  speed_test_summary.json
Daily:   speed_test_summary.json
Weekly:  speed_test_summary.json
Monthly: speed_test_summary.json
Yearly:  speed_test_summary.json
```

## Why This Works

Each aggregation level stores files in **different S3 directory paths**, so using the same filename is safe and simplifies code:

```
Hourly:  s3://vd-speed-test-hourly-prod/aggregated/year=2025/month=202510/day=20251026/hour=2025102614/speed_test_summary.json
Daily:   s3://vd-speed-test/aggregated/year=2025/month=202510/day=20251026/speed_test_summary.json
Weekly:  s3://vd-speed-test-weekly-prod/aggregated/year=2025/week=2025W43/speed_test_summary.json
Monthly: s3://vd-speed-test-monthly-prod/aggregated/year=2025/month=202510/speed_test_summary.json
Yearly:  s3://vd-speed-test-yearly-prod/aggregated/year=2025/speed_test_summary.json
```

## Benefits

✅ **Simpler Code**: No need to remember different filename patterns  
✅ **Consistent**: All aggregation levels follow same convention  
✅ **Easier Maintenance**: One pattern to understand  
✅ **Better Automation**: Scripts can use same filename logic  
✅ **Clear Separation**: Directory structure indicates aggregation level, not filename  

## Files Changed

### lambda_function.py (8 changes)

1. **Header comment** - Updated documentation with new structure
2. **aggregate_hourly()** - Write path changed
3. **upload_summary()** - Daily write path changed  
4. **aggregate_weekly()** - Read daily paths + write weekly path changed
5. **aggregate_monthly()** - Read daily paths + write monthly path changed
6. **aggregate_yearly()** - Read monthly paths + write yearly path changed

### app.py (0 changes)

✅ **No changes needed!** - The dashboard already reads files generically using `.endswith(".json")` without caring about specific filenames.

## Testing Commands

### 1. Test Hourly Aggregation
```bash
aws lambda invoke \
  --function-name vd-speedtest-daily-aggregator-prod \
  --payload '{"mode":"hourly"}' \
  out-hourly.json --cli-binary-format raw-in-base64-out

# Check the output file
cat out-hourly.json | jq

# Verify S3 file
aws s3 ls s3://vd-speed-test-hourly-prod/aggregated/ --recursive | grep speed_test_summary
```

### 2. Test Daily Aggregation
```bash
aws lambda invoke \
  --function-name vd-speedtest-daily-aggregator-prod \
  --payload '{"mode":"daily"}' \
  out-daily.json --cli-binary-format raw-in-base64-out

# Verify S3 file
aws s3 ls s3://vd-speed-test/aggregated/ --recursive | grep speed_test_summary
```

### 3. Test Weekly Aggregation
```bash
aws lambda invoke \
  --function-name vd-speedtest-daily-aggregator-prod \
  --payload '{"mode":"weekly"}' \
  out-weekly.json --cli-binary-format raw-in-base64-out

# Verify S3 file
aws s3 ls s3://vd-speed-test-weekly-prod/aggregated/ --recursive | grep speed_test_summary
```

### 4. Test Monthly Aggregation
```bash
aws lambda invoke \
  --function-name vd-speedtest-daily-aggregator-prod \
  --payload '{"mode":"monthly"}' \
  out-monthly.json --cli-binary-format raw-in-base64-out

# Verify S3 file
aws s3 ls s3://vd-speed-test-monthly-prod/aggregated/ --recursive | grep speed_test_summary
```

### 5. Test Yearly Aggregation
```bash
aws lambda invoke \
  --function-name vd-speedtest-daily-aggregator-prod \
  --payload '{"mode":"yearly"}' \
  out-yearly.json --cli-binary-format raw-in-base64-out

# Verify S3 file
aws s3 ls s3://vd-speed-test-yearly-prod/aggregated/ --recursive | grep speed_test_summary
```

### 6. Test Dashboard
```bash
# Local testing
python app.py
# Visit: http://localhost:8080

# Test all modes
http://localhost:8080/?mode=minute&days=7
http://localhost:8080/?mode=hourly&days=7
http://localhost:8080/?mode=daily&days=30
http://localhost:8080/?mode=weekly&days=12
http://localhost:8080/?mode=monthly&days=6
http://localhost:8080/?mode=yearly&days=3
```

## Deployment

```bash
# Build
sam build

# Deploy
sam deploy
```

## Backwards Compatibility

⚠️ **Note**: After deployment, old files with different names will still exist in S3:
- Old daily files: `speed_summary_20251026.json`
- Old weekly files: `weekly_summary_2025W43.json`
- Old monthly files: `monthly_summary_202510.json`
- Old yearly files: `yearly_summary_2025.json`

**These old files will NOT be read after deployment** because the Lambda now writes to and reads from the new standardized filename.

### Migration Options

**Option 1: Clean Start** (Recommended)
- Let EventBridge schedules generate new files naturally
- Old files will eventually expire based on lifecycle policies
- No data loss - just natural transition

**Option 2: Rename Existing Files**
```bash
# Example: Rename daily files
aws s3 ls s3://vd-speed-test/aggregated/ --recursive | grep speed_summary_ | while read -r line; do
    key=$(echo $line | awk '{print $4}')
    newkey=$(echo $key | sed 's/speed_summary_[0-9]*.json/speed_test_summary.json/')
    aws s3 mv s3://vd-speed-test/$key s3://vd-speed-test/$newkey
done

# Repeat for weekly, monthly, yearly buckets
```

**Option 3: Keep Both**
- Keep old files for historical reference
- New aggregations use new naming
- Query old files manually if needed

## Example S3 Structure After Deployment

```
s3://vd-speed-test/
└── aggregated/
    └── year=2025/
        └── month=202510/
            ├── day=20251025/
            │   └── speed_test_summary.json  (new)
            └── day=20251026/
                └── speed_test_summary.json  (new)

s3://vd-speed-test-hourly-prod/
└── aggregated/
    └── year=2025/
        └── month=202510/
            └── day=20251026/
                ├── hour=2025102614/
                │   └── speed_test_summary.json  (new)
                └── hour=2025102615/
                    └── speed_test_summary.json  (new)

s3://vd-speed-test-weekly-prod/
└── aggregated/
    └── year=2025/
        └── week=2025W43/
            └── speed_test_summary.json  (new)

s3://vd-speed-test-monthly-prod/
└── aggregated/
    └── year=2025/
        └── month=202510/
            └── speed_test_summary.json  (new)

s3://vd-speed-test-yearly-prod/
└── aggregated/
    └── year=2025/
        └── speed_test_summary.json  (new)
```

## Rollback Plan

If issues occur, revert lambda_function.py changes:

```bash
# Check git history
git log --oneline lambda_function.py

# Revert to previous commit
git checkout <commit-hash> lambda_function.py

# Redeploy
sam build
sam deploy
```

Or manually restore the old filename patterns in the 8 locations identified above.
