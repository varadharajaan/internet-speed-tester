# Quick Reference: Configuration Management

## ✅ Changes Completed

All hardcoded variables have been migrated to `config.json`. The following files were updated:

1. ✅ **config.json** - Enhanced with 10 configuration parameters
2. ✅ **speed_collector.py** - Now loads all settings from config
3. ✅ **app.py** - Now loads all settings from config
4. ✅ **lambda_function.py** - Now loads all settings from config
5. ✅ **lambda_hourly_check.py** - Now loads all settings from config

## 📝 Configuration File: config.json

```json
{
  "expected_speed_mbps": 200,
  "tolerance_percent": 10,
  "s3_bucket": "vd-speed-test",
  "aws_region": "ap-south-1",
  "timezone": "Asia/Kolkata",
  "log_level": "INFO",
  "log_max_bytes": 10485760,
  "log_backup_count": 5,
  "speedtest_timeout": 180,
  "public_ip_api": "https://api.ipify.org"
}
```

## 🔧 How to Use

### Option 1: Edit config.json (Recommended for local development)
```bash
# Open config.json and modify any value
notepad config.json

# Example: Change expected speed
{
  "expected_speed_mbps": 500,  # Changed from 200 to 500
  ...
}

# Run your script - it will use the new value
python speed_collector.py
```

### Option 2: Use Environment Variables (Recommended for Lambda)
```bash
# Windows PowerShell
$env:EXPECTED_SPEED_MBPS="500"
$env:S3_BUCKET="my-custom-bucket"
python speed_collector.py

# Linux/Mac
export EXPECTED_SPEED_MBPS=500
export S3_BUCKET=my-custom-bucket
python speed_collector.py
```

### Option 3: Lambda Environment Variables (AWS Console)
1. Go to Lambda function configuration
2. Environment variables section
3. Add: `EXPECTED_SPEED_MBPS` = `500`
4. The function will use this value, overriding config.json

## 🎯 Priority Order

Settings are loaded in this order (highest to lowest priority):

1. **Environment Variables** ← Highest priority
2. **config.json file**
3. **Default values** ← Lowest priority

Example:
- If `S3_BUCKET` environment variable is set → Uses environment variable
- Else if `config.json` has `s3_bucket` → Uses config.json value
- Else → Uses default value "vd-speed-test"

## 🧪 Testing

Run the test script to verify everything works:
```bash
python test_config.py
```

Expected output:
```
✅ All configuration tests completed!
```

## 📋 Common Scenarios

### Scenario 1: Change Speed Threshold
```json
{
  "expected_speed_mbps": 500,  // Changed from 200
  "tolerance_percent": 5        // Changed from 10
}
```

### Scenario 2: Use Different S3 Bucket
```json
{
  "s3_bucket": "my-speedtest-data"
}
```

### Scenario 3: Change Timezone
```json
{
  "timezone": "America/New_York"  // Changed from Asia/Kolkata
}
```

### Scenario 4: Enable Debug Logging
```json
{
  "log_level": "DEBUG"  // Changed from INFO
}
```

### Scenario 5: Increase Speedtest Timeout
```json
{
  "speedtest_timeout": 300  // Changed from 180 (3 minutes to 5 minutes)
}
```

## ⚠️ Important Notes

1. **Restart Required**: After changing config.json, restart your scripts
2. **JSON Syntax**: config.json must be valid JSON (no trailing commas)
3. **Case Sensitive**: Parameter names are case-sensitive
4. **Lambda**: For Lambda functions, environment variables are preferred
5. **Backup**: Keep a backup of config.json before making changes

## 🔍 Troubleshooting

### Config not loading?
```bash
# Check if config.json exists
ls config.json

# Validate JSON syntax
python -c "import json; json.load(open('config.json'))"
```

### Which value is being used?
Add this to your Python script temporarily:
```python
print(f"Using S3_BUCKET: {S3_BUCKET}")
print(f"Using EXPECTED_SPEED_MBPS: {EXPECTED_SPEED_MBPS}")
```

### Reset to defaults
Delete or rename config.json, and the scripts will use built-in defaults.

## 📚 Documentation

- **Full details**: See `CONFIG_MIGRATION_SUMMARY.md`
- **Test script**: Run `python test_config.py`
- **Repository**: Check README.md for overall project info

## ✅ Benefits of This Change

✔️ No code changes needed for configuration updates
✔️ Single source of truth for all settings
✔️ Environment-specific configurations (dev/prod/local)
✔️ Easy to version control
✔️ Backward compatible with environment variables
✔️ Safe fallback to defaults

---

**Last Updated**: October 26, 2025
**Status**: ✅ All changes tested and verified
