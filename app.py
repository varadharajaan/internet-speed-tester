#!/usr/bin/env python3
"""
vd-speed-test dashboard
-----------------------
Flask web app to visualize internet speed statistics from S3.
Now includes CloudWatch-compatible JSON logging and local file rotation.
"""

from flask import Flask, render_template, request, jsonify
import boto3, json, pandas as pd
from botocore.config import Config as BotoConfig
import pytz, datetime, os, logging, sys
from functools import wraps
from logging.handlers import RotatingFileHandler
import socket
import time
from threading import Lock
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- In-Memory Cache with TTL ---------------------------------------------------
class DataCache:
    """Simple in-memory cache with TTL support and manual invalidation."""
    def __init__(self, default_ttl=120):  # 2 minutes default
        self._cache = {}
        self._lock = Lock()
        self.default_ttl = default_ttl
    
    def get(self, key):
        """Get cached value if not expired."""
        with self._lock:
            if key in self._cache:
                data, expiry = self._cache[key]
                if time.time() < expiry:
                    return data
                del self._cache[key]
        return None
    
    def set(self, key, value, ttl=None):
        """Cache a value with TTL."""
        ttl = ttl or self.default_ttl
        with self._lock:
            self._cache[key] = (value, time.time() + ttl)
    
    def invalidate(self, key=None):
        """Invalidate specific key or all keys."""
        with self._lock:
            if key:
                self._cache.pop(key, None)
            else:
                self._cache.clear()
    
    def get_stats(self):
        """Get cache statistics."""
        with self._lock:
            valid_count = sum(1 for _, (_, exp) in self._cache.items() if time.time() < exp)
            return {"cached_items": valid_count, "total_keys": len(self._cache)}

# Global cache instance (2 minute TTL - balances freshness vs performance)
data_cache = DataCache(default_ttl=120)

# --- Configuration from config.json --------------------------------------------
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
DEFAULT_CONFIG = {
    "s3_bucket": "vd-speed-test",
    "s3_bucket_hourly": "vd-speed-test-hourly-prod",
    "s3_bucket_weekly": "vd-speed-test-weekly-prod",
    "s3_bucket_monthly": "vd-speed-test-monthly-prod",
    "s3_bucket_yearly": "vd-speed-test-yearly-prod",
    "aws_region": "ap-south-1",
    "timezone": "Asia/Kolkata",
    "log_level": "INFO",
    "log_max_bytes": 10485760,
    "log_backup_count": 5,
    "expected_speed_mbps": 200,
    "tolerance_percent": 10
}

# Load config
config = DEFAULT_CONFIG.copy()
if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config.update(json.load(f))
    except Exception as e:
        print(f"Warning: Failed to load config.json: {e}. Using defaults.")

# Extract configuration values
S3_BUCKET = os.getenv("S3_BUCKET", config.get("s3_bucket"))
S3_BUCKET_HOURLY = os.getenv("S3_BUCKET_HOURLY", config.get("s3_bucket_hourly"))
S3_BUCKET_WEEKLY = os.getenv("S3_BUCKET_WEEKLY", config.get("s3_bucket_weekly"))
S3_BUCKET_MONTHLY = os.getenv("S3_BUCKET_MONTHLY", config.get("s3_bucket_monthly"))
S3_BUCKET_YEARLY = os.getenv("S3_BUCKET_YEARLY", config.get("s3_bucket_yearly"))
AWS_REGION = os.getenv("AWS_REGION", config.get("aws_region"))
TIMEZONE = pytz.timezone(config.get("timezone"))
LOG_FILE_PATH = os.path.join(os.getcwd(), "dashboard.log")
LOG_MAX_BYTES = config.get("log_max_bytes")
LOG_BACKUP_COUNT = config.get("log_backup_count")
LOG_LEVEL = os.getenv("LOG_LEVEL", config.get("log_level")).upper()
HOSTNAME = os.getenv("HOSTNAME", socket.gethostname())
DEFAULT_THRESHOLD = float(config.get("expected_speed_mbps"))
TOLERANCE_PERCENT = float(config.get("tolerance_percent"))

app = Flask(__name__)

# Optimized S3 client with connection pooling for faster parallel requests
s3_config = BotoConfig(
    max_pool_connections=100,  # Allow more concurrent connections
    connect_timeout=5,
    read_timeout=10,
    retries={'max_attempts': 2}
)
s3 = boto3.client("s3", region_name=AWS_REGION, config=s3_config)

# --- Multi-host support -------------------------------------------------------
def list_hosts():
    """
    Discover all unique host IDs from the S3 bucket by scanning top-level prefixes.
    Returns a list of host_id strings (e.g., ['home-primary', 'office-backup']).
    Also checks for legacy data without host prefix.
    """
    cache_key = "hosts_list"
    cached = data_cache.get(cache_key)
    if cached:
        return cached
    
    hosts = set()
    
    # Check for host= prefixes (new format)
    try:
        result = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix="host=", Delimiter="/")
        for prefix in result.get("CommonPrefixes", []):
            host_prefix = prefix["Prefix"]
            if host_prefix.startswith("host=") and host_prefix.endswith("/"):
                host_id = host_prefix[5:-1]
                hosts.add(host_id)
    except Exception as e:
        log.warning(f"Error listing host prefixes: {e}")
    
    # Check for legacy data (year= prefix without host)
    try:
        result = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix="year=", Delimiter="/", MaxKeys=1)
        if result.get("CommonPrefixes") or result.get("Contents"):
            hosts.add("_legacy")
    except Exception as e:
        log.warning(f"Error checking legacy data: {e}")
    
    hosts_list = sorted(hosts)
    data_cache.set(cache_key, hosts_list, ttl=300)  # Cache for 5 minutes
    log.info(f"Discovered hosts: {hosts_list}")
    return hosts_list

def get_host_prefix(host_id):
    """Get the S3 prefix for a host. Legacy data has no host prefix."""
    if not host_id or host_id == "all" or host_id == "_legacy":
        return ""
    return f"host={host_id}/"

# --- JSON Logger --------------------------------------------------------------
class CustomLogger:
    def __init__(self, name=__name__, level=LOG_LEVEL):
        self.logger = logging.getLogger(name)
        if not self.logger.handlers:
            formatter = self.JsonFormatter()

            # Console handler (CloudWatch captures this)
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)

            # File handler (only for local dev)
            if not self.is_lambda_environment():
                file_handler = RotatingFileHandler(
                    LOG_FILE_PATH,
                    maxBytes=LOG_MAX_BYTES,
                    backupCount=LOG_BACKUP_COUNT,
                    encoding="utf-8"
                )
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)

        self.logger.setLevel(level)
        self.logger.propagate = False

    class JsonFormatter(logging.Formatter):
        def format(self, record):
            entry = {
                "timestamp": datetime.datetime.now(datetime.UTC).isoformat() + "Z",
                "level": record.levelname,
                "message": record.getMessage(),
                "function": record.funcName,
                "module": record.module,
                "hostname": HOSTNAME,
            }
            if record.exc_info:
                entry["error"] = self.formatException(record.exc_info)
            return json.dumps(entry)

    @staticmethod
    def is_lambda_environment():
        return "AWS_LAMBDA_FUNCTION_NAME" in os.environ

    def info(self, msg, *args): self.logger.info(msg, *args)
    def warning(self, msg, *args): self.logger.warning(msg, *args)
    def error(self, msg, *args): self.logger.error(msg, *args)
    def debug(self, msg, *args): self.logger.debug(msg, *args)
    def exception(self, msg, *args): self.logger.exception(msg, *args)

log = CustomLogger(__name__)

# --- Decorator for Logging ----------------------------------------------------
def log_execution(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        log.info(f"Executing {func.__name__}")
        start = datetime.datetime.now(datetime.UTC)
        try:
            result = func(*args, **kwargs)
            elapsed = (datetime.datetime.now(datetime.UTC) - start).total_seconds()
            log.info(f"Completed {func.__name__} in {elapsed:.2f}s")
            return result
        except Exception as e:
            log.exception(f"Error in {func.__name__}: {e}")
            raise
    return wrapper

# --- S3 Utility Functions -----------------------------------------------------
@log_execution
def list_summary_files(host_id=None):
    """List daily summary files, optionally filtered by host."""
    if host_id and host_id != "all" and host_id != "_legacy":
        prefix = f"aggregated/host={host_id}/"
    else:
        prefix = "aggregated/"
    
    paginator = s3.get_paginator("list_objects_v2")
    files = []
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            # Filter for daily summaries only (contains /day= and ends with .json)
            if obj["Key"].endswith(".json") and "/day=" in key:
                # Skip host-prefixed files when loading global view, and vice versa
                if host_id and host_id != "all":
                    # We want host-specific, already filtered by prefix
                    files.append(key)
                elif "host=" not in key:
                    # Global view: only include non-host-prefixed files
                    files.append(key)
    log.info(f"Found {len(files)} summary files in {prefix}" + (f" for host={host_id}" if host_id else ""))
    return files

@log_execution
def load_summaries(host_id=None):
    """Load daily summaries using parallel S3 fetches for speed."""
    keys = list_summary_files(host_id)
    if not keys:
        return pd.DataFrame(columns=["date_ist"])
    
    def fetch_one(key):
        """Fetch a single S3 object."""
        try:
            obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
            return json.loads(obj["Body"].read().decode("utf-8"))
        except Exception as e:
            log.warning(f"Failed to fetch {key}: {e}")
            return None
    
    # Parallel fetch with up to 50 threads (optimized for S3 connection pool)
    recs = []
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = {executor.submit(fetch_one, key): key for key in keys}
        for future in as_completed(futures):
            result = future.result()
            if result:
                recs.append(result)
    
    if not recs:
        return pd.DataFrame(columns=["date_ist"])
    
    df = pd.DataFrame(recs)
    df["date_ist"] = pd.to_datetime(df["date_ist"], errors="coerce")
    df["date_ist_str"] = df["date_ist"].dt.strftime("%Y-%m-%d")

    # Extract stats
    df["download_avg"] = df["overall"].apply(lambda x: x.get("download_mbps", {}).get("avg") if isinstance(x, dict) else None)
    df["upload_avg"] = df["overall"].apply(lambda x: x.get("upload_mbps", {}).get("avg") if isinstance(x, dict) else None)
    df["ping_avg"] = df["overall"].apply(lambda x: x.get("ping_ms", {}).get("avg") if isinstance(x, dict) else None)
    df["top_server"] = df["servers_top"].apply(lambda arr: arr[0] if isinstance(arr, list) and arr else "")
    df["result_urls"] = df["result_urls"].apply(lambda x: x if isinstance(x, list) else [])
    df["connection_type"] = df.get("connection_types", pd.Series([[] for _ in range(len(df))])).apply(
        lambda x: ", ".join(x) if isinstance(x, list) and x else "Unknown"
    )
    
    # Add host info
    if "host_id" not in df.columns:
        df["host_id"] = "_legacy"

    if "public_ips" in df.columns:
        df["public_ips"] = df["public_ips"].apply(lambda x: x if isinstance(x, list) else [])
        df["public_ip"] = df["public_ips"].apply(lambda x: x[0] if x else "")
    elif "public_ip" in df.columns:
        df["public_ips"] = df["public_ip"].apply(lambda x: [x] if isinstance(x, str) and x else [])
    else:
        df["public_ips"] = [[] for _ in range(len(df))]
        df["public_ip"] = ""

    log.info(f"Loaded {len(df)} daily summaries from S3" + (f" for host={host_id}" if host_id else ""))
    return df.sort_values("date_ist")

@log_execution
def load_minute_data(days, host_id=None):
    """Load minute-level data using parallel S3 fetches for speed."""
    cutoff = datetime.datetime.now(TIMEZONE) - datetime.timedelta(days=days)
    paginator = s3.get_paginator("list_objects_v2")
    
    # Determine prefix based on host
    if host_id and host_id != "all" and host_id != "_legacy":
        base_prefix = f"host={host_id}/year="
    else:
        base_prefix = "year="
    
    # First, collect all keys that match our criteria
    keys_to_fetch = []
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=base_prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".json") and "aggregated" not in key:
                keys_to_fetch.append(key)
    
    log.info(f"Found {len(keys_to_fetch)} minute-level files to fetch")
    
    def fetch_and_parse(key):
        """Fetch and parse a single S3 object."""
        try:
            data = json.loads(s3.get_object(Bucket=S3_BUCKET, Key=key)["Body"].read())
            ts_str = data.get("timestamp_ist")
            if not ts_str:
                return None
            ts = TIMEZONE.localize(datetime.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S IST"))
            if ts < cutoff:
                return None
            return {
                "timestamp": ts,
                "download_avg": float(str(data.get("download_mbps", "0")).split()[0]),
                "upload_avg": float(str(data.get("upload_mbps", "0")).split()[0]),
                "ping_avg": safe_float(data.get("ping_ms", 0)),
                "top_server": f"{data.get('server_name', '')} – {data.get('server_host', '')} – {data.get('server_city', '')} ({data.get('server_country', '')})".strip(),
                "public_ip": data.get("public_ip", ""),
                "connection_type": data.get("connection_type", "Unknown"),
                "wifi_name": data.get("wifi_name", ""),
                "result_urls": [data.get("result_url")] if data.get("result_url") else [],
                "host_id": data.get("host_id", "_legacy"),
                "host_name": data.get("host_name", ""),
                "host_location": data.get("host_location", ""),
                "host_isp": data.get("host_isp", "")
            }
        except Exception as e:
            log.warning(f"Skip {key}: {e}")
            return None
    
    # Parallel fetch with up to 50 threads for faster loading
    results = []
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = {executor.submit(fetch_and_parse, key): key for key in keys_to_fetch}
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)

    if not results:
        log.warning("No minute-level data found.")
        return pd.DataFrame(columns=["timestamp"])
    df = pd.DataFrame(results)
    df["date_ist"] = df["timestamp"]
    df["date_ist_str"] = df["timestamp"].dt.strftime("%Y-%m-%d %H:%M")
    log.info(f"Loaded {len(df)} minute-level records from S3.")
    return df.sort_values("timestamp")

@log_execution
def load_hourly_data(days, host_id=None):
    """Load hourly aggregated data from S3_BUCKET_HOURLY using parallel fetches."""
    cutoff = datetime.datetime.now(TIMEZONE) - datetime.timedelta(days=days)
    paginator = s3.get_paginator("list_objects_v2")
    
    # Determine prefix based on host
    if host_id and host_id != "all" and host_id != "_legacy":
        prefix = f"aggregated/host={host_id}/"
    else:
        prefix = "aggregated/"
    
    # Collect all keys first
    keys_to_fetch = []
    for page in paginator.paginate(Bucket=S3_BUCKET_HOURLY, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".json"):
                # For global view, skip host-prefixed files
                if not host_id or host_id == "all":
                    if "host=" not in key:
                        keys_to_fetch.append(key)
                else:
                    keys_to_fetch.append(key)
    
    log.info(f"Found {len(keys_to_fetch)} hourly files to fetch" + (f" for host={host_id}" if host_id else ""))
    
    def fetch_and_parse(key):
        """Fetch and parse a single hourly file."""
        try:
            data = json.loads(s3.get_object(Bucket=S3_BUCKET_HOURLY, Key=key)["Body"].read())
            hour_str = data.get("hour_ist")
            if not hour_str:
                return None
            ts = TIMEZONE.localize(datetime.datetime.strptime(hour_str, "%Y-%m-%d %H:%M"))
            if ts < cutoff:
                return None
            return {
                "timestamp": ts,
                "date_ist": ts,
                "date_ist_str": ts.strftime("%Y-%m-%d %H:00"),
                "download_avg": data["overall"]["download_mbps"]["avg"],
                "upload_avg": data["overall"]["upload_mbps"]["avg"],
                "ping_avg": data["overall"]["ping_ms"]["avg"],
                "top_server": data.get("servers_top", [""])[0] if data.get("servers_top") else "",
                "public_ips": data.get("public_ips", []),
                "public_ip": data.get("public_ips", [""])[0] if data.get("public_ips") else "",
                "connection_type": ", ".join(data.get("connection_types", [])) if data.get("connection_types") else "Unknown",
                "wifi_name": "",
                "result_urls": [],
                "records": data.get("records", 0),
                "completion_rate": data.get("completion_rate", 0),
                "host_id": data.get("host_id", "_legacy")
            }
        except Exception as e:
            log.warning(f"Skip {key}: {e}")
            return None
    
    # Parallel fetch with up to 30 threads
    results = []
    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = {executor.submit(fetch_and_parse, key): key for key in keys_to_fetch}
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)

    if not results:
        log.warning("No hourly data found.")
        return pd.DataFrame(columns=["timestamp"])
    df = pd.DataFrame(results)
    log.info(f"Loaded {len(df)} hourly records from S3" + (f" for host={host_id}" if host_id else "") + ".")
    return df.sort_values("timestamp")

@log_execution
def load_weekly_data(weeks=52, host_id=None):
    """Load weekly aggregated data from S3_BUCKET_WEEKLY using parallel fetches."""
    paginator = s3.get_paginator("list_objects_v2")
    cutoff_date = datetime.datetime.now(TIMEZONE).date() - datetime.timedelta(weeks=weeks)

    # Determine prefix based on host
    if host_id and host_id != "all" and host_id != "_legacy":
        prefix = f"aggregated/host={host_id}/"
    else:
        prefix = "aggregated/"

    # Collect all keys first
    keys_to_fetch = []
    for page in paginator.paginate(Bucket=S3_BUCKET_WEEKLY, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".json"):
                # For global view, skip host-prefixed files
                if not host_id or host_id == "all":
                    if "host=" not in key:
                        keys_to_fetch.append(key)
                else:
                    keys_to_fetch.append(key)
    
    log.info(f"Found {len(keys_to_fetch)} weekly files to fetch" + (f" for host={host_id}" if host_id else ""))
    
    def fetch_and_parse(key):
        """Fetch and parse a single weekly file."""
        try:
            data = json.loads(s3.get_object(Bucket=S3_BUCKET_WEEKLY, Key=key)["Body"].read())
            week_start = datetime.datetime.strptime(data["week_start"], "%Y-%m-%d").date()
            if week_start < cutoff_date:
                return None
            return {
                "date_ist": week_start,
                "date_ist_str": f"{data['week_start']} to {data['week_end']}",
                "download_avg": data["avg_download"],
                "upload_avg": data["avg_upload"],
                "ping_avg": data["avg_ping"],
                "days": data.get("days", 0),
                "connection_type": ", ".join(data.get("connection_types", [])) if data.get("connection_types") else "Unknown",
                "top_server": "",
                "public_ips": [],
                "public_ip": "",
                "result_urls": [],
                "host_id": data.get("host_id", "_legacy")
            }
        except Exception as e:
            log.warning(f"Skip {key}: {e}")
            return None
    
    # Parallel fetch with up to 20 threads
    results = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(fetch_and_parse, key): key for key in keys_to_fetch}
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)

    if not results:
        log.warning(f"No weekly data found for last {weeks} weeks.")
        return pd.DataFrame(columns=["date_ist"])
    df = pd.DataFrame(results)
    log.info(f"Loaded {len(df)} weekly records from S3 (last {weeks} weeks)" + (f" for host={host_id}" if host_id else "") + ".")
    return df.sort_values("date_ist")

@log_execution
def load_monthly_data(months=12, host_id=None):
    """Load monthly aggregated data from S3_BUCKET_MONTHLY using parallel fetches."""
    paginator = s3.get_paginator("list_objects_v2")
    cutoff_date = datetime.datetime.now(TIMEZONE).date().replace(day=1)
    cutoff_date = cutoff_date - datetime.timedelta(days=30 * months)

    # Determine prefix based on host
    if host_id and host_id != "all" and host_id != "_legacy":
        prefix = f"aggregated/host={host_id}/"
    else:
        prefix = "aggregated/"

    # Collect all keys with their last_modified for deduplication
    keys_with_meta = []
    for page in paginator.paginate(Bucket=S3_BUCKET_MONTHLY, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".json"):
                # For global view, skip host-prefixed files
                if not host_id or host_id == "all":
                    if "host=" not in key:
                        keys_with_meta.append((key, obj.get("LastModified")))
                else:
                    keys_with_meta.append((key, obj.get("LastModified")))
    
    log.info(f"Found {len(keys_with_meta)} monthly files to fetch" + (f" for host={host_id}" if host_id else ""))
    
    def fetch_and_parse(key_meta):
        """Fetch and parse a single monthly file."""
        key, last_modified = key_meta
        try:
            data = json.loads(s3.get_object(Bucket=S3_BUCKET_MONTHLY, Key=key)["Body"].read())
            month_str = data["month"]
            month_date = datetime.datetime.strptime(month_str, "%Y%m").date()
            if month_date < cutoff_date:
                return None
            return (month_str, data, last_modified)
        except Exception as e:
            log.warning(f"Skip {key}: {e}")
            return None
    
    # Parallel fetch
    fetched_data = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(fetch_and_parse, km): km for km in keys_with_meta}
        for future in as_completed(futures):
            result = future.result()
            if result:
                fetched_data.append(result)
    
    # Deduplicate: keep only most recent file for each month
    monthly_data = {}
    for month_str, data, last_modified in fetched_data:
        if month_str not in monthly_data or (last_modified and last_modified > monthly_data[month_str][1]):
            monthly_data[month_str] = (data, last_modified)

    # Convert to results list
    results = []
    for month_str, (data, _) in monthly_data.items():
        month_date = datetime.datetime.strptime(month_str, "%Y%m").date()
        results.append({
            "date_ist": month_date,
            "date_ist_str": month_date.strftime("%Y-%m"),
            "download_avg": data["avg_download"],
            "upload_avg": data["avg_upload"],
            "ping_avg": data["avg_ping"],
            "days": data.get("days", 0),
            "connection_type": ", ".join(data.get("connection_types", [])) if data.get("connection_types") else "Unknown",
            "top_server": "",
            "public_ips": [],
            "public_ip": "",
            "result_urls": [],
            "host_id": data.get("host_id", "_legacy")
        })

    if not results:
        log.warning(f"No monthly data found for last {months} months.")
        return pd.DataFrame(columns=["date_ist"])
    df = pd.DataFrame(results)
    log.info(f"Loaded {len(df)} unique monthly records from S3 (last {months} months)" + (f" for host={host_id}" if host_id else "") + ".")
    return df.sort_values("date_ist")

@log_execution
def load_yearly_data(years=10, host_id=None):
    """Load yearly aggregated data from S3_BUCKET_YEARLY using parallel fetches."""
    paginator = s3.get_paginator("list_objects_v2")
    cutoff_year = datetime.datetime.now(TIMEZONE).year - years

    # Determine prefix based on host
    if host_id and host_id != "all" and host_id != "_legacy":
        prefix = f"aggregated/host={host_id}/"
    else:
        prefix = "aggregated/"

    # Collect all keys first
    keys_to_fetch = []
    for page in paginator.paginate(Bucket=S3_BUCKET_YEARLY, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".json"):
                # For global view, skip host-prefixed files
                if not host_id or host_id == "all":
                    if "host=" not in key:
                        keys_to_fetch.append(key)
                else:
                    keys_to_fetch.append(key)
    
    log.info(f"Found {len(keys_to_fetch)} yearly files to fetch" + (f" for host={host_id}" if host_id else ""))
    
    def fetch_and_parse(key):
        """Fetch and parse a single yearly file."""
        try:
            data = json.loads(s3.get_object(Bucket=S3_BUCKET_YEARLY, Key=key)["Body"].read())
            year = data["year"]
            if year < cutoff_year:
                return None
            year_date = datetime.datetime(year, 1, 1).date()
            return {
                "date_ist": year_date,
                "date_ist_str": str(year),
                "download_avg": data["avg_download"],
                "upload_avg": data["avg_upload"],
                "ping_avg": data["avg_ping"],
                "months": data.get("months_aggregated", 0),
                "connection_type": ", ".join(data.get("connection_types", [])) if data.get("connection_types") else "Unknown",
                "top_server": "",
                "public_ips": [],
                "public_ip": "",
                "result_urls": [],
                "host_id": data.get("host_id", "_legacy")
            }
        except Exception as e:
            log.warning(f"Skip {key}: {e}")
            return None
    
    # Parallel fetch
    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_and_parse, key): key for key in keys_to_fetch}
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)

    if not results:
        log.warning(f"No yearly data found for last {years} years.")
        return pd.DataFrame(columns=["date_ist"])
    df = pd.DataFrame(results)
    log.info(f"Loaded {len(df)} yearly records from S3 (last {years} years)" + (f" for host={host_id}" if host_id else "") + ".")
    return df.sort_values("date_ist")

def safe_float(value):
    """Convert values like '184.52 Mbps' or '6.58 ms' safely to float."""
    if isinstance(value, str):
        value = (
            value.replace("Mbps", "")
                 .replace("Mbit/s", "")
                 .replace("mbps", "")
                 .replace("ms", "")
                 .strip()
        )
        # If there's still a space, take first token
        value = value.split()[0]
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0
    
# --- Anomaly Detection --------------------------------------------------------
def detect_anomalies(df):
    """
    Detect anomalies in speed test data using connection-aware thresholds.
    Uses connection-specific thresholds from config for accurate performance assessment.
    """
    if df.empty:
        return df
    
    # Statistical anomalies (relative to dataset mean)
    dl_mean = df["download_avg"].mean()
    ping_mean = df["ping_avg"].mean()
    df["download_anomaly"] = df["download_avg"] < (0.7 * dl_mean)
    df["ping_anomaly"] = df["ping_avg"] > (1.5 * ping_mean)
    
    # Connection-aware threshold anomalies
    connection_thresholds = config.get("connection_type_thresholds", {
        "Wi-Fi 5GHz": 200,
        "Wi-Fi 2.4GHz": 100,
        "Ethernet": 200,
        "Unknown": 150
    })
    
    tolerance = TOLERANCE_PERCENT / 100.0
    
    def is_below_expected(row):
        """Check if download speed is below expected for connection type."""
        conn_type = str(row.get("connection_type", "Unknown"))
        # Extract primary connection type (in case of comma-separated values)
        primary_conn = conn_type.split(",")[0].strip() if conn_type else "Unknown"
        
        # Find matching threshold
        threshold = connection_thresholds.get("Unknown", 150)  # default
        for key, value in connection_thresholds.items():
            if key.lower() in primary_conn.lower():
                threshold = value
                break
        
        return row["download_avg"] < (threshold * (1 - tolerance))
    
    df["below_expected"] = df.apply(is_below_expected, axis=1)
    
    return df

# --- Routes -------------------------------------------------------------------
@app.route("/", methods=["GET", "POST"])
@app.route("/dashboard", methods=["GET", "POST"])
@log_execution
def dashboard():
    # Primary controls from GET parameters (mode, days, host)
    mode = request.args.get("mode", "daily")
    days_param = int(request.args.get("days", 7))
    host_id = request.args.get("host", None)  # None = all hosts (global view)
    force_refresh = request.args.get("refresh", "0") == "1"
    async_mode = request.args.get("async", "0") == "1"
    
    # Get list of available hosts for the dropdown
    available_hosts = list_hosts()
    
    # Advanced filters from POST body (if any)
    params = request.form if request.method == "POST" else request.args

    # ASYNC MODE: Return skeleton template immediately, JS will fetch data
    if async_mode:
        log.info(f"Async mode: returning skeleton for mode={mode}, days={days_param}, host={host_id}")
        return render_template(
            "dashboard_modern.html",
            async_mode=True,
            data=[],
            days=days_param,
            summary={},
            stats={"avg_download": 0, "avg_upload": 0, "avg_ping": 0, "total_tests": 0},
            percentiles={},
            trends={},
            historical_records={},
            connection_stats={},
            chart_data={"timestamps": [], "download": [], "upload": [], "ping": [], "connection_types": []},
            quick_filters={"below_threshold": 0, "performance_drops": 0, "high_ping": 0, "isps": [], "connection_types": []},
            last_update="Loading...",
            view_mode=mode,
            date_from="", date_to="", time_from="", time_to="",
            min_download="", max_download="", min_upload="", max_upload="",
            min_ping="", max_ping="", connection_type="", isp="",
            default_threshold=DEFAULT_THRESHOLD,
            tolerance_percent=TOLERANCE_PERCENT,
            connection_type_thresholds=config.get("connection_type_thresholds", {}),
            mode=mode,
            available_hosts=available_hosts,
            selected_host=host_id
        )

    # Convert days parameter to appropriate units based on mode
    if mode == "weekly":
        period = days_param // 7  # Convert days to weeks
    elif mode == "monthly":
        period = days_param // 30  # Convert days to months (approximate)
    elif mode == "yearly":
        period = days_param // 365  # Convert days to years
    else:
        period = days_param  # Use days as-is for minute, hourly, daily modes

    # Cache key based on mode, period, and host
    host_key = host_id or "all"
    cache_key = f"dashboard_{mode}_{period}_{host_key}"
    
    # Invalidate cache if force refresh requested
    if force_refresh:
        data_cache.invalidate(cache_key)
        data_cache.invalidate(f"minute_data_{period}_{host_key}")  # Also invalidate raw data cache
        log.info(f"Cache invalidated for {cache_key} (force refresh)")
    
    # Check cache first
    cached_df = data_cache.get(cache_key)
    if cached_df is not None:
        log.info(f"Cache HIT for {cache_key}")
        df = cached_df
    else:
        log.info(f"Cache MISS for {cache_key} - loading from S3")
        # Load data based on mode (with host filtering)
        if mode == "minute":
            df = load_minute_data(period, host_id=host_id)
        elif mode == "hourly":
            df = load_hourly_data(period, host_id=host_id)
        elif mode == "weekly":
            df = load_weekly_data(period, host_id=host_id)  # period = weeks
        elif mode == "monthly":
            df = load_monthly_data(period, host_id=host_id)  # period = months
        elif mode == "yearly":
            df = load_yearly_data(period, host_id=host_id)  # period = years
        else:  # daily
            df = load_summaries(host_id=host_id)  # daily mode loads all and filters
        
        # Cache the loaded data
        data_cache.set(cache_key, df)
    
    df = detect_anomalies(df)

    summary = {}
    if not df.empty:
        top_server_over_period = df["top_server"].mode()[0] if not df["top_server"].mode().empty else "N/A"
        public_ips = sorted({
            ip.strip()
            for vals in df.get("public_ips", [])
            if isinstance(vals, list)
            for ip in vals
            if isinstance(ip, str) and ip.strip() and ip.strip().lower() not in ('unknown', 'n/a', '')
        })
        
        # Calculate CIDR ranges for public IPs
        cidr_ranges = []
        if public_ips:
            try:
                import ipaddress
                # Group IPs by /16 network first (larger aggregation)
                networks_16 = {}
                networks_24 = {}
                
                for ip_str in public_ips:
                    try:
                        ip = ipaddress.ip_address(ip_str)
                        # Get /16 network (e.g., 223.178.0.0/16)
                        network_16 = ipaddress.ip_network(f"{ip}/16", strict=False)
                        network_16_str = str(network_16)
                        if network_16_str not in networks_16:
                            networks_16[network_16_str] = []
                        networks_16[network_16_str].append(ip_str)
                        
                        # Also track /24 networks for single IP cases
                        network_24 = ipaddress.ip_network(f"{ip}/24", strict=False)
                        network_24_str = str(network_24)
                        if network_24_str not in networks_24:
                            networks_24[network_24_str] = []
                        networks_24[network_24_str].append(ip_str)
                    except ValueError:
                        continue
                
                # Use /16 if multiple /24 blocks exist in same /16, otherwise use /24
                cidr_info = []
                for cidr_16, ips_16 in networks_16.items():
                    # Count how many different /24 blocks are in this /16
                    unique_24_blocks = set()
                    for ip_str in ips_16:
                        ip = ipaddress.ip_address(ip_str)
                        network_24 = ipaddress.ip_network(f"{ip}/24", strict=False)
                        unique_24_blocks.add(str(network_24))
                    
                    # If 3+ different /24 blocks in same /16, show as /16
                    if len(unique_24_blocks) >= 3:
                        cidr_info.append({
                            "cidr": cidr_16,
                            "count": len(ips_16),
                            "ips": ips_16
                        })
                    else:
                        # Show individual /24 blocks
                        for block_24 in unique_24_blocks:
                            cidr_info.append({
                                "cidr": block_24,
                                "count": len(networks_24[block_24]),
                                "ips": networks_24[block_24]
                            })
                
                # Sort by IP count (descending)
                cidr_ranges = sorted(cidr_info, key=lambda x: x['count'], reverse=True)
                
            except Exception as e:
                log.warning(f"Failed to calculate CIDR ranges: {e}")
                cidr_ranges = []

        if mode in ["daily", "hourly"]:
            below_count = int(df["below_expected"].sum())
            total_days = int(len(df))
        else:
            daily_below = df.groupby(df["date_ist"].dt.date if hasattr(df["date_ist"].iloc[0], 'date') else df["date_ist"])["below_expected"].any()
            below_count = int(daily_below.sum())
            total_days = int(daily_below.size)

        # Use the already-loaded aggregated data for all statistics
        # No need to load minute data separately - aggregated data has all the stats we need!
        # This eliminates the slow S3 fetches that were causing 2-minute page loads
        
        # Calculate averages directly from the already-loaded df
        avg_download = round(df["download_avg"].mean(), 2)
        avg_upload = round(df["upload_avg"].mean(), 2)
        avg_ping = round(df["ping_avg"].mean(), 2)

        summary = {
            "avg_download": avg_download,
            "avg_upload": avg_upload,
            "avg_ping": avg_ping,
            "below_expected": below_count,
            "total_days": total_days,
            "top_server_over_period": top_server_over_period,
            "public_ips": public_ips,
            "cidr_ranges": cidr_ranges,
        }

        if mode in ["daily", "hourly"]:
            best_idx = df["download_avg"].idxmax()
            worst_idx = df["download_avg"].idxmin()
            summary.update({
                "best_day": str(df.loc[best_idx, "date_ist"].date() if hasattr(df.loc[best_idx, "date_ist"], 'date') else df.loc[best_idx, "date_ist"]),
                "worst_day": str(df.loc[worst_idx, "date_ist"].date() if hasattr(df.loc[worst_idx, "date_ist"], 'date') else df.loc[worst_idx, "date_ist"])
            })

    log.info(f"Dashboard summary ready for mode={mode}, days={period}")
    
    # Calculate percentile statistics from the already-loaded aggregated data
    # No separate minute data fetch needed - df already has all the stats
    percentiles = {}
    if not df.empty:
        percentiles = {
            "download_p50": round(df["download_avg"].quantile(0.50), 2),
            "download_p95": round(df["download_avg"].quantile(0.95), 2),
            "download_p99": round(df["download_avg"].quantile(0.99), 2),
            "upload_p50": round(df["upload_avg"].quantile(0.50), 2),
            "upload_p95": round(df["upload_avg"].quantile(0.95), 2),
            "upload_p99": round(df["upload_avg"].quantile(0.99), 2),
            "ping_p50": round(df["ping_avg"].quantile(0.50), 2),
            "ping_p95": round(df["ping_avg"].quantile(0.95), 2),
            "ping_p99": round(df["ping_avg"].quantile(0.99), 2),
        }
    
    # Calculate trend indicators (compare with previous period)
    trends = {}
    if not df.empty and len(df) > 1:
        # Split data in half to compare current vs previous period
        mid_point = len(df) // 2
        df_sorted = df.sort_values("date_ist")
        current_period = df_sorted.iloc[mid_point:]
        previous_period = df_sorted.iloc[:mid_point]
        
        if not current_period.empty and not previous_period.empty:
            curr_down = current_period["download_avg"].mean()
            prev_down = previous_period["download_avg"].mean()
            curr_up = current_period["upload_avg"].mean()
            prev_up = previous_period["upload_avg"].mean()
            curr_ping = current_period["ping_avg"].mean()
            prev_ping = previous_period["ping_avg"].mean()
            
            trends = {
                "download_change": round(((curr_down - prev_down) / prev_down * 100) if prev_down > 0 else 0, 1),
                "upload_change": round(((curr_up - prev_up) / prev_up * 100) if prev_up > 0 else 0, 1),
                "ping_change": round(((curr_ping - prev_ping) / prev_ping * 100) if prev_ping > 0 else 0, 1),
                "tests_change": round(((len(current_period) - len(previous_period)) / len(previous_period) * 100) if len(previous_period) > 0 else 0, 1)
            }
    
    # Calculate historical best/worst records
    historical_records = {}
    if not df.empty:
        best_download_idx = df["download_avg"].idxmax()
        worst_download_idx = df["download_avg"].idxmin()
        best_upload_idx = df["upload_avg"].idxmax()
        lowest_ping_idx = df["ping_avg"].idxmin()
        
        historical_records = {
            "best_download": {
                "value": round(df.loc[best_download_idx, "download_avg"], 2),
                "date": str(df.loc[best_download_idx, "date_ist"]),
                "server": df.loc[best_download_idx, "top_server"] if "top_server" in df.columns else "N/A"
            },
            "worst_download": {
                "value": round(df.loc[worst_download_idx, "download_avg"], 2),
                "date": str(df.loc[worst_download_idx, "date_ist"])
            },
            "best_upload": {
                "value": round(df.loc[best_upload_idx, "upload_avg"], 2),
                "date": str(df.loc[best_upload_idx, "date_ist"])
            },
            "lowest_ping": {
                "value": round(df.loc[lowest_ping_idx, "ping_avg"], 2),
                "date": str(df.loc[lowest_ping_idx, "date_ist"])
            }
        }
    
    # Calculate connection type statistics
    connection_stats = {}
    connection_thresholds = {
        "Ethernet": {"threshold": 200, "min_threshold": 180},
        "Wi-Fi 5GHz": {"threshold": 200, "min_threshold": 180},
        "Wi-Fi 2.4GHz": {"threshold": 100, "min_threshold": 90},
        "Unknown": {"threshold": 150, "min_threshold": 135}
    }
    
    if not df.empty and "connection_type" in df.columns:
        # Parse connection types from comma-separated values
        for conn_type_key in connection_thresholds.keys():
            # Filter rows that contain this connection type
            mask = df["connection_type"].str.contains(conn_type_key, case=False, na=False)
            conn_df = df[mask]
            
            if not conn_df.empty:
                conn_avg = conn_df["download_avg"].mean()
                conn_count = len(conn_df)
                min_threshold = connection_thresholds[conn_type_key]["min_threshold"]
                below_min = (conn_df["download_avg"] < min_threshold).sum()
                below_pct = (below_min / conn_count * 100) if conn_count > 0 else 0
                
                connection_stats[conn_type_key] = {
                    "count": conn_count,
                    "avg": round(conn_avg, 1),
                    "threshold": connection_thresholds[conn_type_key]["threshold"],
                    "min_threshold": min_threshold,
                    "below_min": below_min,
                    "below_pct": round(below_pct, 1)
                }
    
    # Prepare chart data for ECharts
    if not df.empty and "date_ist" in df.columns:
        try:
            timestamps = df["date_ist"].dt.strftime("%Y-%m-%d %H:%M").tolist()
        except:
            timestamps = [str(x) for x in df["date_ist"].tolist()]
    else:
        timestamps = []
    
    # Extract dynamic quick filter options
    quick_filters = {
        "below_threshold": 0,
        "performance_drops": 0,
        "high_ping": 0,
        "isps": [],
        "connection_types": []
    }
    
    if not df.empty:
        # Count performance categories
        # Below threshold uses conservative 200 Mbps (shows all potentially poor connections)
        quick_filters["below_threshold"] = int((df["download_avg"] < 200).sum())
        quick_filters["performance_drops"] = int((df["download_avg"] < 100).sum())
        quick_filters["high_ping"] = int((df["ping_avg"] > 20).sum())
        
        # Extract unique ISPs
        if "isp" in df.columns:
            unique_isps = df["isp"].dropna().unique()
            isp_counts = df["isp"].value_counts().to_dict()
            quick_filters["isps"] = [
                {"name": isp, "count": isp_counts.get(isp, 0)} 
                for isp in sorted(unique_isps) if isp
            ]
        
        # Extract unique connection types
        if "connection_type" in df.columns:
            # Handle comma-separated connection types
            all_conn_types = set()
            for conn_str in df["connection_type"].dropna():
                if isinstance(conn_str, str):
                    types = [t.strip() for t in conn_str.split(",")]
                    all_conn_types.update(types)
            
            # Filter out "Wi-Fi (unknown band)"
            all_conn_types = {ct for ct in all_conn_types if ct and ct != "Wi-Fi (unknown band)"}
            
            # Count occurrences
            conn_counts = {}
            for conn_type in all_conn_types:
                count = df["connection_type"].str.contains(conn_type, case=False, na=False).sum()
                conn_counts[conn_type] = count
            
            quick_filters["connection_types"] = [
                {"name": ct, "count": conn_counts[ct]} 
                for ct in sorted(all_conn_types) if ct
            ]
    
    chart_data = {
        "timestamps": timestamps,
        "download": df["download_avg"].fillna(0).tolist() if not df.empty and "download_avg" in df.columns else [],
        "upload": df["upload_avg"].fillna(0).tolist() if not df.empty and "upload_avg" in df.columns else [],
        "ping": df["ping_avg"].fillna(0).tolist() if not df.empty and "ping_avg" in df.columns else [],
        "connection_types": df["connection_type"].fillna("Unknown").tolist() if not df.empty and "connection_type" in df.columns else []
    }
    
    # Stats summary with total_tests
    stats = {
        "avg_download": summary.get("avg_download", 0),
        "avg_upload": summary.get("avg_upload", 0),
        "avg_ping": summary.get("avg_ping", 0),
        "total_tests": len(df) if not df.empty else 0
    }
    
    # Get current datetime for last_update
    import datetime as dt
    last_update = dt.datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S IST")
    
    # Sort data by date in descending order (newest first)
    if not df.empty and "date_ist" in df.columns:
        df = df.sort_values("date_ist", ascending=False)
    
    # Get connection type thresholds from config
    connection_type_thresholds = config.get("connection_type_thresholds", {
        "Wi-Fi 5GHz": 200,
        "Wi-Fi 2.4GHz": 100,
        "Ethernet": 200,
        "Unknown": 150
    })
    
    return render_template(
        "dashboard_modern.html",
        data=df.to_dict(orient="records"),
        days=days_param,
        summary=summary,
        stats=stats,
        percentiles=percentiles,
        trends=trends,
        historical_records=historical_records,
        connection_stats=connection_stats,
        chart_data=chart_data,
        quick_filters=quick_filters,
        last_update=last_update,
        view_mode=mode,
        date_from=params.get("date_from", ""),
        date_to=params.get("date_to", ""),
        time_from=params.get("time_from", ""),
        time_to=params.get("time_to", ""),
        min_download=params.get("min_download", ""),
        max_download=params.get("max_download", ""),
        min_upload=params.get("min_upload", ""),
        max_upload=params.get("max_upload", ""),
        min_ping=params.get("min_ping", ""),
        max_ping=params.get("max_ping", ""),
        connection_type=params.get("connection_type", ""),
        isp=params.get("isp", ""),
        default_threshold=DEFAULT_THRESHOLD,
        tolerance_percent=TOLERANCE_PERCENT,
        connection_type_thresholds=connection_type_thresholds,
        mode=mode,
        available_hosts=available_hosts,
        selected_host=host_id
    )

@app.route("/api/data")
@log_execution
def api_data():
    mode = request.args.get("mode", "daily")
    days_param = int(request.args.get("days", 7))
    host_id = request.args.get("host", None)  # None = all hosts
    force_refresh = request.args.get("refresh", "0") == "1"
    
    # Convert days parameter to appropriate units based on mode
    if mode == "weekly":
        period = days_param // 7  # Convert days to weeks
    elif mode == "monthly":
        period = days_param // 30  # Convert days to months (approximate)
    elif mode == "yearly":
        period = days_param // 365  # Convert days to years
    else:
        period = days_param  # Use days as-is for minute, hourly, daily modes
    
    # Cache key for API (include host)
    host_key = host_id or "all"
    cache_key = f"api_{mode}_{period}_{host_key}"
    
    # Handle force refresh
    if force_refresh:
        data_cache.invalidate(cache_key)
        log.info(f"API cache invalidated for {cache_key}")
    
    # Check cache
    cached_df = data_cache.get(cache_key)
    if cached_df is not None:
        log.info(f"API cache HIT for {cache_key}")
        df = cached_df
    else:
        log.info(f"API cache MISS for {cache_key}")
        # Load data based on mode (with host filtering)
        if mode == "minute":
            df = load_minute_data(period, host_id=host_id)
        elif mode == "hourly":
            df = load_hourly_data(period, host_id=host_id)
        elif mode == "weekly":
            df = load_weekly_data(period, host_id=host_id)
        elif mode == "monthly":
            df = load_monthly_data(period, host_id=host_id)
        elif mode == "yearly":
            df = load_yearly_data(period, host_id=host_id)
        else:  # daily
            df = load_summaries(host_id=host_id)
        
        data_cache.set(cache_key, df)
    
    df = detect_anomalies(df)
    log.info(f"API returned {len(df)} records in mode={mode}, host={host_id}")
    return jsonify(df.to_dict(orient="records"))

@app.route("/api/dashboard")
@log_execution
def api_dashboard():
    """
    Full dashboard data API for async loading.
    Returns all data needed to populate the dashboard via JavaScript.
    """
    mode = request.args.get("mode", "daily")
    days_param = int(request.args.get("days", 7))
    host_id = request.args.get("host", None)  # None = all hosts
    force_refresh = request.args.get("refresh", "0") == "1"
    
    # Convert days parameter to appropriate units based on mode
    if mode == "weekly":
        period = days_param // 7
    elif mode == "monthly":
        period = days_param // 30
    elif mode == "yearly":
        period = days_param // 365
    else:
        period = days_param

    # Cache key (include host)
    host_key = host_id or "all"
    cache_key = f"dashboard_api_{mode}_{period}_{host_key}"
    
    # Handle force refresh
    if force_refresh:
        data_cache.invalidate(cache_key)
        data_cache.invalidate(f"dashboard_{mode}_{period}_{host_key}")
        log.info(f"Dashboard API cache invalidated for {cache_key}")
    
    # Check cache for pre-computed dashboard response
    cached_response = data_cache.get(cache_key)
    if cached_response is not None:
        log.info(f"Dashboard API cache HIT for {cache_key}")
        return jsonify(cached_response)
    
    log.info(f"Dashboard API cache MISS for {cache_key} - computing...")
    
    # Load data based on mode (with host filtering)
    if mode == "minute":
        df = load_minute_data(period, host_id=host_id)
    elif mode == "hourly":
        df = load_hourly_data(period, host_id=host_id)
    elif mode == "weekly":
        df = load_weekly_data(period, host_id=host_id)
    elif mode == "monthly":
        df = load_monthly_data(period, host_id=host_id)
    elif mode == "yearly":
        df = load_yearly_data(period, host_id=host_id)
    else:
        df = load_summaries(host_id=host_id)
    
    df = detect_anomalies(df)
    
    # Build response data
    summary = {}
    percentiles = {}
    trends = {}
    historical_records = {}
    connection_stats = {}
    
    if not df.empty:
        # Calculate summary stats
        avg_download = round(df["download_avg"].mean(), 2)
        avg_upload = round(df["upload_avg"].mean(), 2)
        avg_ping = round(df["ping_avg"].mean(), 2)
        
        top_server = df["top_server"].mode()[0] if not df["top_server"].mode().empty else "N/A"
        
        below_count = int(df["below_expected"].sum()) if "below_expected" in df.columns else 0
        total_days = len(df)
        
        summary = {
            "avg_download": avg_download,
            "avg_upload": avg_upload,
            "avg_ping": avg_ping,
            "below_expected": below_count,
            "total_days": total_days,
            "top_server_over_period": top_server,
        }
        
        # Percentiles
        percentiles = {
            "download_p50": round(df["download_avg"].quantile(0.50), 2),
            "download_p95": round(df["download_avg"].quantile(0.95), 2),
            "download_p99": round(df["download_avg"].quantile(0.99), 2),
            "upload_p50": round(df["upload_avg"].quantile(0.50), 2),
            "upload_p95": round(df["upload_avg"].quantile(0.95), 2),
            "upload_p99": round(df["upload_avg"].quantile(0.99), 2),
            "ping_p50": round(df["ping_avg"].quantile(0.50), 2),
            "ping_p95": round(df["ping_avg"].quantile(0.95), 2),
            "ping_p99": round(df["ping_avg"].quantile(0.99), 2),
        }
        
        # Trends
        if len(df) > 1:
            mid_point = len(df) // 2
            df_sorted = df.sort_values("date_ist")
            current_period = df_sorted.iloc[mid_point:]
            previous_period = df_sorted.iloc[:mid_point]
            
            if not current_period.empty and not previous_period.empty:
                curr_down = current_period["download_avg"].mean()
                prev_down = previous_period["download_avg"].mean()
                curr_up = current_period["upload_avg"].mean()
                prev_up = previous_period["upload_avg"].mean()
                curr_ping = current_period["ping_avg"].mean()
                prev_ping = previous_period["ping_avg"].mean()
                
                trends = {
                    "download_change": round(((curr_down - prev_down) / prev_down * 100) if prev_down > 0 else 0, 1),
                    "upload_change": round(((curr_up - prev_up) / prev_up * 100) if prev_up > 0 else 0, 1),
                    "ping_change": round(((curr_ping - prev_ping) / prev_ping * 100) if prev_ping > 0 else 0, 1),
                }
        
        # Historical records
        best_download_idx = df["download_avg"].idxmax()
        worst_download_idx = df["download_avg"].idxmin()
        
        historical_records = {
            "best_download": {
                "value": round(df.loc[best_download_idx, "download_avg"], 2),
                "date": str(df.loc[best_download_idx, "date_ist"]),
            },
            "worst_download": {
                "value": round(df.loc[worst_download_idx, "download_avg"], 2),
                "date": str(df.loc[worst_download_idx, "date_ist"]),
            },
        }
    
    # Chart data
    if not df.empty and "date_ist" in df.columns:
        try:
            timestamps = df["date_ist"].dt.strftime("%Y-%m-%d %H:%M").tolist()
        except:
            timestamps = [str(x) for x in df["date_ist"].tolist()]
    else:
        timestamps = []
    
    chart_data = {
        "timestamps": timestamps,
        "download": df["download_avg"].fillna(0).tolist() if not df.empty else [],
        "upload": df["upload_avg"].fillna(0).tolist() if not df.empty else [],
        "ping": df["ping_avg"].fillna(0).tolist() if not df.empty else [],
    }
    
    stats = {
        "avg_download": summary.get("avg_download", 0),
        "avg_upload": summary.get("avg_upload", 0),
        "avg_ping": summary.get("avg_ping", 0),
        "total_tests": len(df) if not df.empty else 0
    }
    
    import datetime as dt
    last_update = dt.datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S IST")
    
    # Build complete response
    response = {
        "success": True,
        "stats": stats,
        "summary": summary,
        "percentiles": percentiles,
        "trends": trends,
        "historical_records": historical_records,
        "chart_data": chart_data,
        "last_update": last_update,
        "mode": mode,
        "days": days_param,
        "record_count": len(df),
    }
    
    # Cache the response
    data_cache.set(cache_key, response)
    log.info(f"Dashboard API response cached for {cache_key}")
    
    return jsonify(response)

# --- Local Run ---------------------------------------------------------------
if __name__ == "__main__":
    log.info("Starting Flask dashboard locally...")
    app.run(host="0.0.0.0", port=8080, debug=True)