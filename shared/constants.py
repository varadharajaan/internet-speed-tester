"""
Constants and magic numbers.

Centralizes all hardcoded values for easy maintenance.
All values here can be overridden via config.json or environment variables
where appropriate - this module provides the defaults.

Usage:
    from shared import AWS_REGION, S3_BUCKETS, CACHE_TTL
"""
from dataclasses import dataclass
from typing import Dict


# =============================================================================
# AWS Configuration
# =============================================================================

AWS_REGION = "ap-south-1"

# S3 bucket names (defaults - can be overridden in config.json)
S3_BUCKETS = {
    "raw": "vd-speed-test",
    "hourly": "vd-speed-test-hourly-prod",
    "daily": "vd-speed-test",  # Same as raw, different prefix
    "weekly": "vd-speed-test-weekly-prod",
    "monthly": "vd-speed-test-monthly-prod",
    "yearly": "vd-speed-test-yearly-prod",
}

# CloudWatch Log Groups
LOG_GROUPS = {
    "dashboard": "/aws/lambda/vd-speedtest-dashboard-prod",
    "daily": "/aws/lambda/vd-speedtest-daily-aggregator-prod",
    "hourly": "/aws/lambda/vd-speedtest-hourly-checker-prod",
}


# =============================================================================
# Cache Configuration
# =============================================================================

CACHE_TTL = 120  # seconds (2 minutes)
CACHE_LONG_TTL = 3600  # seconds (1 hour) for weekly/monthly data
DISK_CACHE_MIN_TTL = 300  # Only persist to disk if TTL >= 5 minutes


# =============================================================================
# Aggregation Configuration
# =============================================================================

@dataclass
class AggregationSchedule:
    """Defines when each aggregation type runs."""
    name: str
    cron_utc: str  # Cron expression in UTC
    cron_ist: str  # Human-readable IST time
    description: str


AGGREGATION_SCHEDULES = {
    "hourly": AggregationSchedule(
        name="hourly",
        cron_utc="10 * * * ? *",  # Every hour at :10
        cron_ist="Every hour at :10",
        description="Aggregates 15-min data to hourly summaries",
    ),
    "daily": AggregationSchedule(
        name="daily",
        cron_utc="30 0 * * ? *",  # 00:30 UTC = 06:00 IST
        cron_ist="Daily at 06:00 IST",
        description="Aggregates raw data to daily summaries",
    ),
    "weekly": AggregationSchedule(
        name="weekly",
        cron_utc="30 20 ? * SUN *",  # Sunday 20:30 UTC = Tuesday 02:00 IST
        cron_ist="Tuesday at 02:00 IST",
        description="Aggregates daily data to weekly summaries",
    ),
    "monthly": AggregationSchedule(
        name="monthly",
        cron_utc="30 20 1 * ? *",  # 1st of month 20:30 UTC = 02:00 IST
        cron_ist="1st of month at 02:00 IST",
        description="Aggregates daily data to monthly summaries",
    ),
    "yearly": AggregationSchedule(
        name="yearly",
        cron_utc="30 20 1 1 ? *",  # Jan 1 20:30 UTC = 02:00 IST
        cron_ist="January 1st at 02:00 IST",
        description="Aggregates monthly data to yearly summaries",
    ),
}


# =============================================================================
# Speed Test Thresholds
# =============================================================================

# Default expected speeds by connection type (Mbps)
CONNECTION_TYPE_THRESHOLDS = {
    "Wi-Fi 5GHz": 200,
    "Wi-Fi 2.4GHz": 100,
    "Ethernet": 200,
    "Unknown": 150,
}

# Anomaly detection thresholds
ANOMALY_THRESHOLDS = {
    "download_drop_percent": 30,  # Alert if download drops > 30% from expected
    "upload_drop_percent": 40,    # Alert if upload drops > 40% from expected
    "ping_spike_ms": 100,         # Alert if ping > 100ms
    "jitter_spike_ms": 50,        # Alert if jitter > 50ms
}

# Minimum valid speed test values (to filter out errors)
MIN_VALID_DOWNLOAD_MBPS = 1.0
MIN_VALID_UPLOAD_MBPS = 1.0
MAX_VALID_PING_MS = 5000


# =============================================================================
# Data Limits
# =============================================================================

# Maximum records per period for aggregation
MAX_RECORDS_PER_HOUR = 4     # 15-min intervals: 4 per hour
MAX_RECORDS_PER_DAY = 96     # 15-min intervals: 96 per day
MAX_RECORDS_PER_WEEK = 7     # Days per week
MAX_RECORDS_PER_MONTH = 31   # Max days per month
MAX_RECORDS_PER_YEAR = 12    # Months per year

# Chart data limits
MAX_CHART_POINTS = 200       # Max points for chart rendering (after downsampling)
MAX_TABLE_ROWS = 1000        # Max rows in data table


# =============================================================================
# Parallel Processing
# =============================================================================

PARALLEL_THREADS_DEFAULT = 20
PARALLEL_THREADS_HOURLY = 50
PARALLEL_THREADS_MAX = 100


# =============================================================================
# File Patterns
# =============================================================================

# S3 key patterns for different data types
S3_KEY_PATTERNS = {
    "raw": r"host=([^/]+)/year=(\d{4})/month=(\d{6})/day=(\d{8})/hour=(\d{10})/minute=(\d{2})/",
    "daily": r"aggregated/(host=([^/]+)/)?year=(\d{4})/month=(\d{6})/day=(\d{8})/",
    "hourly": r"aggregated/(host=([^/]+)/)?year=(\d{4})/month=(\d{6})/day=(\d{8})/hour=(\d{10})/",
    "weekly": r"aggregated/(host=([^/]+)/)?year=(\d{4})/week=(\d{4}W\d{2})/",
    "monthly": r"aggregated/(host=([^/]+)/)?year=(\d{4})/month=(\d{6})/",
    "yearly": r"aggregated/(host=([^/]+)/)?year=(\d{4})/",
}

# Summary filename
SUMMARY_FILENAME = "speed_test_summary.json"


# =============================================================================
# HTTP/API Configuration
# =============================================================================

DEFAULT_DASHBOARD_PORT = 8080
API_TIMEOUT_SECONDS = 30
PUBLIC_IP_API = "https://api.ipify.org"


# =============================================================================
# Time Configuration
# =============================================================================

DEFAULT_TIMEZONE = "Asia/Kolkata"
IST_UTC_OFFSET_HOURS = 5.5
