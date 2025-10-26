# Configuration Migration Summary

## Overview
All hardcoded configuration values have been migrated to `config.json` for centralized configuration management. This allows easy customization without modifying code.

## Enhanced config.json Structure

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

## Configuration Parameters

| Parameter | Description | Default Value | Used In |
|-----------|-------------|---------------|---------|
| `expected_speed_mbps` | Expected download speed for anomaly detection | 200 | app.py, lambda_function.py |
| `tolerance_percent` | Tolerance percentage for speed variations | 10 | app.py, lambda_function.py |
| `s3_bucket` | S3 bucket name for data storage | vd-speed-test | All files |
| `aws_region` | AWS region for services | ap-south-1 | All files |
| `timezone` | Timezone for timestamp conversion | Asia/Kolkata | All files |
| `log_level` | Logging verbosity (DEBUG/INFO/WARNING/ERROR) | INFO | All files |
| `log_max_bytes` | Maximum log file size in bytes | 10485760 (10 MB) | All files |
| `log_backup_count` | Number of log backup files to keep | 5 | All files |
| `speedtest_timeout` | Timeout for speedtest CLI in seconds | 180 | speed_collector.py |
| `public_ip_api` | API endpoint for fetching public IP | https://api.ipify.org | speed_collector.py |

## Files Modified

### 1. config.json
- **Added** 8 new configuration parameters
- Expanded from 2 to 10 configurable values

### 2. speed_collector.py
**Changes:**
- Added config.json loader with fallback defaults
- Replaced hardcoded values:
  - `S3_BUCKET = "vd-speed-test"` → loaded from config
  - `AWS_REGION = "ap-south-1"` → loaded from config
  - `TIMEZONE = pytz.timezone("Asia/Kolkata")` → loaded from config
  - `LOG_MAX_BYTES = 10 * 1024 * 1024` → loaded from config
  - `LOG_BACKUP_COUNT = 5` → loaded from config
  - `timeout=180` → `timeout=SPEEDTEST_TIMEOUT` from config
  - `requests.get("https://api.ipify.org")` → `requests.get(PUBLIC_IP_API)` from config

### 3. app.py (Dashboard)
**Changes:**
- Added config.json loader with fallback defaults
- Replaced hardcoded values:
  - `S3_BUCKET = "vd-speed-test"` → loaded from config
  - `AWS_REGION = "ap-south-1"` → loaded from config
  - `TIMEZONE = pytz.timezone("Asia/Kolkata")` → loaded from config
  - `LOG_MAX_BYTES = 10 * 1024 * 1024` → loaded from config
  - `LOG_BACKUP_COUNT = 5` → loaded from config
  - `DEFAULT_THRESHOLD = 200.0` → loaded from config as `expected_speed_mbps`
  - Removed duplicate config loading logic
  - `cfg.get("tolerance_percent")` → `TOLERANCE_PERCENT` from config

### 4. lambda_function.py (Aggregator)
**Changes:**
- Added config.json loader with fallback defaults
- Replaced hardcoded values:
  - `S3_BUCKET` default from "vd-speed-test" → loaded from config
  - `AWS_REGION1` default from "ap-south-1" → loaded from config
  - `TIMEZONE = pytz.timezone("Asia/Kolkata")` → loaded from config
  - `EXPECTED_SPEED_MBPS` default from "200" → loaded from config
  - `TOLERANCE_PERCENT` default from "10" → loaded from config
  - `LOG_MAX_BYTES = 10 * 1024 * 1024` → loaded from config
  - `LOG_BACKUP_COUNT = 5` → loaded from config

### 5. lambda_hourly_check.py
**Changes:**
- Added config.json loader with fallback defaults
- Replaced hardcoded values:
  - `S3_BUCKET` default from "vd-speed-test" → loaded from config
  - `AWS_REGION1 = "ap-south-1"` → loaded from config
  - `LOG_MAX_BYTES = 10 * 1024 * 1024` → loaded from config
  - `LOG_BACKUP_COUNT = 5` → loaded from config

## Configuration Priority

The configuration loading follows this priority order:
1. **Environment Variables** (highest priority) - set via Lambda environment or system environment
2. **config.json file** - local configuration file
3. **Default values** (lowest priority) - hardcoded fallbacks

Example:
```python
S3_BUCKET = os.getenv("S3_BUCKET", config.get("s3_bucket"))
```

This allows:
- Local development using `config.json`
- Lambda deployment using environment variables
- Safe fallback to defaults if neither is available

## Benefits

✅ **Centralized Configuration**: All settings in one JSON file
✅ **No Code Changes**: Modify behavior without changing Python code
✅ **Environment Flexibility**: Override via environment variables in Lambda
✅ **Version Control Friendly**: Separate config from code
✅ **Easy Deployment**: Copy config.json to different environments with different values
✅ **Backward Compatible**: Falls back to defaults if config is missing

## Usage Examples

### Local Development
1. Edit `config.json` with your preferred values
2. Run any Python script - it will automatically use your config

### Lambda Deployment
- Environment variables in `template.yaml` override config.json
- Config.json provides defaults for local testing
- No need to modify code for different environments

### Testing Different Speeds
```json
{
  "expected_speed_mbps": 500,
  "tolerance_percent": 15
}
```

### Using Different S3 Bucket
```json
{
  "s3_bucket": "my-custom-speedtest-bucket"
}
```

### Changing Timezone
```json
{
  "timezone": "America/New_York"
}
```

## Migration Checklist

- [x] Create enhanced config.json with all parameters
- [x] Update speed_collector.py to use config
- [x] Update app.py to use config
- [x] Update lambda_function.py to use config
- [x] Update lambda_hourly_check.py to use config
- [x] Maintain environment variable override capability
- [x] Add fallback defaults for safety
- [x] Document all configuration parameters

## Testing

Test the configuration migration:

```bash
# Test speed collector
python speed_collector.py

# Test dashboard
python app.py

# Test aggregator locally
python lambda_function.py

# Verify all scripts load config successfully
```

Check logs for messages like:
```
Loaded config.json successfully: threshold=200
```

---

**Note**: All files maintain backward compatibility. If `config.json` is missing or has errors, the system will use default values and log a warning.
