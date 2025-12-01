# Hourly Aggregation - SAM Template & Schedule Updates

## Date: October 26, 2025

## Summary of Changes

All updates made to support hourly aggregation with EventBridge schedule triggering at **10 minutes past each hour** to aggregate the **previous hour's data**. The system now works with **partial data** (even if only 1 out of 4 expected 15-minute files is found).

---

## 1. template.yaml Changes

### ✅ New Parameter: HourlyScheduleExpression
```yaml
HourlyScheduleExpression:
  Type: String
  Default: cron(10 * * * ? *)  # Every hour at :10
  Description: Cron for hourly aggregation (every hour at :10)
```

**Cron Breakdown:**
- `10` = Minute (10 minutes past the hour)
- `*` = Hour (every hour)
- `*` = Day of month (every day)
- `*` = Month (every month)
- `?` = Day of week (no specific day)
- `*` = Year (every year)

**Result:** Triggers at 00:10, 01:10, 02:10, ..., 23:10 UTC every day

### ✅ New S3 Bucket: HourlyBucket
```yaml
HourlyBucket:
  Type: AWS::S3::Bucket
  Properties:
    BucketName: !Sub 'vd-speed-test-hourly-${Environment}'
    VersioningConfiguration: { Status: Suspended }
    LifecycleConfiguration:
      Rules:
        - Id: HourlyRetention
          Status: Enabled
          ExpirationInDays: 90  # 3 months retention
```

**Bucket Name:** `vd-speed-test-hourly-prod` (or `-dev` based on Environment parameter)

**Retention:** 90 days (can be adjusted based on needs)

### ✅ Updated Global Environment Variables
```yaml
Environment:
  Variables:
    S3_BUCKET: !Ref S3BucketName
    S3_BUCKET_HOURLY: !Sub 'vd-speed-test-hourly-${Environment}'  # NEW
    S3_BUCKET_WEEKLY: !Sub 'vd-speed-test-weekly-${Environment}'
    S3_BUCKET_MONTHLY: !Sub 'vd-speed-test-monthly-${Environment}'
    S3_BUCKET_YEARLY: !Sub 'vd-speed-test-yearly-${Environment}'
```

### ✅ Updated Lambda Permissions
Added S3 access for hourly bucket:
```yaml
Policies:
  - S3CrudPolicy:
      BucketName: !Ref S3BucketName
  - S3CrudPolicy:
      BucketName: !Sub 'vd-speed-test-hourly-${Environment}'  # NEW
  - S3CrudPolicy:
      BucketName: !Sub 'vd-speed-test-weekly-${Environment}'
  - S3CrudPolicy:
      BucketName: !Sub 'vd-speed-test-monthly-${Environment}'
  - S3CrudPolicy:
      BucketName: !Sub 'vd-speed-test-yearly-${Environment}'
```

### ✅ New EventBridge Schedule: HourlyAggregationSchedule
```yaml
HourlyAggregationSchedule:
  Type: AWS::Events::Rule
  Properties:
    Name: !Sub 'vd-speedtest-hourly-schedule-${Environment}'
    Description: Trigger hourly aggregation (every hour at :10)
    ScheduleExpression: !Ref HourlyScheduleExpression
    State: ENABLED
    Targets:
      - Arn: !GetAtt VdSpeedTestAggregator.Arn
        Id: LambdaTargetHourly
        Input: '{"mode":"hourly"}'
        RetryPolicy:
          MaximumRetryAttempts: 2
```

### ✅ New Lambda Permission: PermissionForHourlySchedule
```yaml
PermissionForHourlySchedule:
  Type: AWS::Lambda::Permission
  Properties:
    FunctionName: !Ref VdSpeedTestAggregator
    Action: lambda:InvokeFunction
    Principal: events.amazonaws.com
    SourceArn: !GetAtt HourlyAggregationSchedule.Arn
```

---

## 2. lambda_function.py Changes

### ✅ Updated aggregate_hourly() Function

**Previous Behavior:**
- Required at least 80% of expected records (3 out of 4)
- Logged warning for incomplete data

**New Behavior:**
- ✅ **Works with ANY data (1-4 files)**
- ✅ **Logs info message for partial data** instead of warning
- ✅ **Still calculates completion rate** for monitoring
- ✅ **Proceeds with aggregation** regardless of count

```python
# Old code (removed)
if count < expected_records * 0.8:
    log.warning(f"Incomplete hour: {count}/{expected_records} records ({completion_rate:.1f}%)")

# New code
if count < expected_records:
    log.info(f"Partial hour data: {count}/{expected_records} records ({completion_rate:.1f}%)")
    # Note: We still aggregate with whatever data is available
```

---

## 3. Schedule Timeline

### Hourly Aggregation Flow

**Example for hour 14:00-15:00:**

| Time (UTC) | Event | Description |
|------------|-------|-------------|
| 14:00 | Speed test runs | First 15-min data point |
| 14:15 | Speed test runs | Second 15-min data point |
| 14:30 | Speed test runs | Third 15-min data point |
| 14:45 | Speed test runs | Fourth 15-min data point |
| **15:10** | **Hourly aggregation** | Aggregates 14:00-14:59 data |

**Why 10 minutes past?**
- Gives 10-minute buffer for last speed test to complete and upload
- Last test at 14:45 + processing/upload time ≈ 14:46-14:47
- By 15:10, all 4 files (14:00, 14:15, 14:30, 14:45) should be available
- Even if delayed, aggregation proceeds with available files

---

## 4. Complete Schedule Matrix

| Aggregation | Frequency | Cron Expression | UTC Time | IST Time | Input |
|-------------|-----------|-----------------|----------|----------|-------|
| **Hourly** | Every hour | `cron(10 * * * ? *)` | Every :10 | Every :40 | `{"mode":"hourly"}` |
| **Daily** | Daily | `cron(0 1 * * ? *)` | Daily 01:00 | 06:30 | `{"mode":"daily"}` |
| **Weekly** | Weekly | `cron(0 1 ? * MON *)` | Mon 01:00 | 06:30 | `{"mode":"weekly"}` |
| **Monthly** | Monthly | `cron(0 1 1 * ? *)` | 1st 01:00 | 1st 06:30 | `{"mode":"monthly"}` |
| **Yearly** | Yearly | `cron(0 1 1 1 ? *)` | Jan 1 01:00 | 06:30 | `{"mode":"yearly"}` |

---

## 5. Deployment Commands

### Validate Template
```bash
sam validate --template template.yaml --lint
```

### Build Application
```bash
sam build
```

### Deploy to AWS
```bash
sam deploy --guided
```

Or with existing config:
```bash
sam deploy
```

### Check Deployment
```bash
# List EventBridge rules
aws events list-rules --name-prefix vd-speedtest-hourly

# Check S3 bucket
aws s3 ls | grep hourly

# Verify Lambda permissions
aws lambda get-policy --function-name vd-speedtest-daily-aggregator-prod
```

---

## 6. Testing

### Manual Trigger (Hourly Aggregation)
```bash
aws lambda invoke \
  --function-name vd-speedtest-daily-aggregator-prod \
  --payload '{"mode": "hourly"}' \
  response.json

cat response.json
```

### Check Hourly Data in S3
```bash
# List hourly summaries
aws s3 ls s3://vd-speed-test-hourly-prod/aggregated/ --recursive

# Download specific hourly summary
aws s3 cp s3://vd-speed-test-hourly-prod/aggregated/year=2025/month=202510/day=20251026/hour=2025102614/hourly_summary_2025102614.json .

# View content
cat hourly_summary_2025102614.json | jq
```

### Monitor EventBridge Invocations
```bash
# Check CloudWatch Logs
aws logs tail /aws/lambda/vd-speedtest-daily-aggregator-prod --follow

# Filter for hourly mode
aws logs filter-log-events \
  --log-group-name /aws/lambda/vd-speedtest-daily-aggregator-prod \
  --filter-pattern '"mode=hourly"' \
  --max-items 10
```

---

## 7. Partial Data Handling

### Scenarios

| Scenario | Files Found | Behavior | Completion Rate |
|----------|-------------|----------|-----------------|
| **Normal** | 4/4 | ✅ Aggregates all data | 100% |
| **Slightly delayed** | 3/4 | ✅ Aggregates available data | 75% |
| **Network issue** | 2/4 | ✅ Aggregates available data | 50% |
| **Collector down** | 1/4 | ✅ Aggregates available data | 25% |
| **No data** | 0/4 | ❌ Returns None, logs warning | 0% |

### Log Examples

**Full data (4/4):**
```json
{
  "level": "INFO",
  "message": "Aggregated 4 records for 2025102614 with 0 anomalies"
}
```

**Partial data (2/4):**
```json
{
  "level": "INFO",
  "message": "Partial hour data: 2/4 records (50.0%)"
}
```

**No data (0/4):**
```json
{
  "level": "WARNING",
  "message": "No data found for hour 2025102614"
}
```

---

## 8. S3 Bucket Summary

| Bucket | Purpose | Retention | Size Estimate |
|--------|---------|-----------|---------------|
| `vd-speed-test` | Minute data + daily summaries | User-managed | ~50 MB/day |
| `vd-speed-test-hourly-prod` | Hourly aggregations | 90 days | ~2 MB/day |
| `vd-speed-test-weekly-prod` | Weekly rollups | 730 days (2 years) | ~50 KB/week |
| `vd-speed-test-monthly-prod` | Monthly rollups | 1825 days (5 years) | ~15 KB/month |
| `vd-speed-test-yearly-prod` | Yearly rollups | 3650 days (10 years) | ~5 KB/year |

---

## 9. Resource Updates Summary

| Resource Type | Changes Made | Count |
|---------------|-------------|-------|
| **Parameters** | Added HourlyScheduleExpression | +1 |
| **S3 Buckets** | Added HourlyBucket | +1 |
| **Environment Variables** | Added S3_BUCKET_HOURLY | +1 |
| **Lambda Policies** | Added S3CrudPolicy for hourly bucket | +1 |
| **EventBridge Rules** | Added HourlyAggregationSchedule | +1 |
| **Lambda Permissions** | Added PermissionForHourlySchedule | +1 |

**Total: 6 new resources**

---

## 10. Validation Results

✅ **SAM Template Validation:** PASSED
```
C:\vd-speed-test\template.yaml is a valid SAM Template
```

✅ **Python Syntax Check:** PASSED (no errors)

✅ **Configuration Test:** PASSED
```
Daily: vd-speed-test
Hourly: vd-speed-test-hourly-prod
Weekly: vd-speed-test-weekly-prod
Monthly: vd-speed-test-monthly-prod
Yearly: vd-speed-test-yearly-prod
```

---

## 11. Post-Deployment Verification Checklist

- [ ] S3 bucket created: `vd-speed-test-hourly-prod`
- [ ] EventBridge rule active: `vd-speedtest-hourly-schedule-prod`
- [ ] Lambda has permissions for hourly bucket
- [ ] EventBridge can invoke Lambda
- [ ] First hourly aggregation completed successfully
- [ ] Hourly data visible in S3
- [ ] Dashboard loads hourly data
- [ ] CloudWatch logs show hourly mode execution

---

## 12. Cost Impact

### Additional Resources
- **S3 Bucket:** ~$0.023/month for 90 days of hourly data
- **Lambda Invocations:** 24 additional invocations/day = 720/month
  - Cost: ~$0.0002/month (well within Free Tier)
- **EventBridge:** 720 invocations/month
  - Cost: $0 (Free Tier covers 1M invocations)

**Total Additional Cost:** ~$0.025/month (2.5 cents)

---

## 13. Rollback Plan

If issues occur, disable the hourly schedule:

```bash
# Disable EventBridge rule
aws events disable-rule --name vd-speedtest-hourly-schedule-prod

# Or delete the rule
aws events delete-rule --name vd-speedtest-hourly-schedule-prod

# Delete bucket (if needed)
aws s3 rb s3://vd-speed-test-hourly-prod --force
```

Or revert template.yaml and redeploy:
```bash
git checkout HEAD~ template.yaml lambda_function.py
sam deploy
```

---

## Summary

✅ **EventBridge Schedule:** Triggers at :10 past each hour
✅ **Partial Data Support:** Works with 1-4 files (no longer requires 80%)
✅ **SAM Template:** All resources defined and validated
✅ **Ready for Deployment:** `sam build && sam deploy`

**Next Step:** Run `sam deploy` to create the hourly bucket and activate the schedule!
