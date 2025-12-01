#!/usr/bin/env python3
"""
vd-speed-test aggregator Lambda
- Hourly: aggregates 15-min records into hourly summary, writes to:
    s3://<S3_BUCKET_HOURLY>/aggregated/year=YYYY/month=YYYYMM/day=YYYYMMDD/hour=YYYYMMDDHH/speed_test_summary.json
- Daily: aggregates minute-level results into day summary, writes to:
    s3://<S3_BUCKET>/aggregated/year=YYYY/month=YYYYMM/day=YYYYMMDD/speed_test_summary.json
- Weekly/Monthly/Yearly: roll-ups from daily → weekly/monthly/yearly, writing into:
    s3://<S3_BUCKET_WEEKLY>/aggregated/year=YYYY/week=YYYYWWW/speed_test_summary.json
    s3://<S3_BUCKET_MONTHLY>/aggregated/year=YYYY/month=YYYYMM/speed_test_summary.json
    s3://<S3_BUCKET_YEARLY>/aggregated/year=YYYY/speed_test_summary.json
    
Note: All aggregation levels now use the same filename (speed_test_summary.json) for simplicity.
"""

import boto3
import json
import datetime
import pytz
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from statistics import mean, median
from collections import Counter
from functools import wraps
from calendar import monthrange  # for clean month-end calculation

# --- Configuration from config.json + env vars --------------------------------
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
DEFAULT_CONFIG = {
    "s3_bucket": "vd-speed-test",
    "s3_bucket_hourly": "vd-speed-test-hourly-prod",
    "s3_bucket_weekly": "vd-speed-test-weekly-prod",
    "s3_bucket_monthly": "vd-speed-test-monthly-prod",
    "s3_bucket_yearly": "vd-speed-test-yearly-prod",
    "aws_region": "ap-south-1",
    "timezone": "Asia/Kolkata",
    "expected_speed_mbps": 200,
    "tolerance_percent": 10,
    "connection_type_thresholds": {
        "Wi-Fi 5GHz": 200,
        "Wi-Fi 2.4GHz": 100,
        "Ethernet": 200,
        "Unknown": 150
    },
    "log_level": "INFO",
    "log_max_bytes": 10485760,
    "log_backup_count": 5
}

# Load config
config = DEFAULT_CONFIG.copy()
if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config.update(json.load(f))
    except Exception:
        pass  # Use defaults if config fails to load

S3_BUCKET = os.environ.get("S3_BUCKET", config.get("s3_bucket"))
AWS_REGION1 = os.environ.get("AWS_REGION1", config.get("aws_region"))
TIMEZONE = pytz.timezone(config.get("timezone"))
EXPECTED_SPEED_MBPS = float(os.environ.get("EXPECTED_SPEED_MBPS", str(config.get("expected_speed_mbps"))))
TOLERANCE_PERCENT = float(os.environ.get("TOLERANCE_PERCENT", str(config.get("tolerance_percent"))))

# Load connection type thresholds from environment or config
try:
    conn_type_env = os.environ.get("CONNECTION_TYPE_THRESHOLDS")
    if conn_type_env:
        CONNECTION_TYPE_THRESHOLDS = json.loads(conn_type_env)
    else:
        CONNECTION_TYPE_THRESHOLDS = config.get("connection_type_thresholds", {
            "Wi-Fi 5GHz": 200,
            "Wi-Fi 2.4GHz": 100,
            "Ethernet": 200,
            "Unknown": 150
        })
except (json.JSONDecodeError, ValueError):
    CONNECTION_TYPE_THRESHOLDS = {
        "Wi-Fi 5GHz": 200,
        "Wi-Fi 2.4GHz": 100,
        "Ethernet": 200,
        "Unknown": 150
    }

# Rollup buckets from config.json (with environment variable override)
S3_BUCKET_HOURLY = os.environ.get("S3_BUCKET_HOURLY", config.get("s3_bucket_hourly"))
S3_BUCKET_WEEKLY = os.environ.get("S3_BUCKET_WEEKLY", config.get("s3_bucket_weekly"))
S3_BUCKET_MONTHLY = os.environ.get("S3_BUCKET_MONTHLY", config.get("s3_bucket_monthly"))
S3_BUCKET_YEARLY = os.environ.get("S3_BUCKET_YEARLY", config.get("s3_bucket_yearly"))

LOG_FILE_PATH = os.path.join(os.getcwd(), "aggregator.log")
LOG_MAX_BYTES = config.get("log_max_bytes")
LOG_BACKUP_COUNT = config.get("log_backup_count")
LOG_LEVEL = os.getenv("LOG_LEVEL", config.get("log_level")).upper()
try:
    HOSTNAME = os.getenv("HOSTNAME", os.uname().nodename)
except AttributeError:
    HOSTNAME = os.getenv("HOSTNAME", "unknown-host")


# --- AWS Client ---------------------------------------------------------------
s3 = boto3.client("s3", region_name=AWS_REGION1)

# --- Custom JSON Logger -------------------------------------------------------
class CustomLogger:
    def __init__(self, name=__name__, level=LOG_LEVEL):
        self.logger = logging.getLogger(name)
        if not self.logger.handlers:
            formatter = self.JsonFormatter()

            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)

            if not self.is_lambda_environment():
                file_handler = RotatingFileHandler(
                    LOG_FILE_PATH, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT, encoding="utf-8"
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

# --- Decorator ----------------------------------------------------------------
def log_execution(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        log.info(f"Starting: {func.__name__}")
        start = datetime.datetime.now(datetime.UTC)
        try:
            result = func(*args, **kwargs)
            duration = (datetime.datetime.now(datetime.UTC) - start).total_seconds()
            log.info(f"Completed: {func.__name__} in {duration:.2f}s")
            return result
        except Exception as e:
            log.exception(f"Error in {func.__name__}: {e}")
            raise
    return wrapper

# --- Helpers ------------------------------------------------------------------
def list_objects(prefix: str):
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            yield obj["Key"]

def read_json(key: str) -> dict:
    obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
    return json.loads(obj["Body"].read().decode("utf-8"))

def parse_float(value):
    if isinstance(value, str):
        value = value.replace("ms", "").replace("Mbps", "").strip()
    try:
        return float(value)
    except (ValueError, TypeError):
        return None

def parse_mbps(value_with_suffix):
    try:
        return float(str(value_with_suffix).strip().split()[0])
    except Exception:
        return None

def stats(values):
    if not values:
        return {}
    values_sorted = sorted(values)
    idx = lambda p: int(p * (len(values_sorted) - 1)) if len(values_sorted) > 1 else 0
    return {
        "avg": round(mean(values), 2),
        "median": round(median(values), 2),
        "max": round(max(values), 2),
        "min": round(min(values), 2),
        "p99": round(values_sorted[idx(0.99)], 2),
        "p95": round(values_sorted[idx(0.95)], 2),
        "p90": round(values_sorted[idx(0.90)], 2),
        "p50": round(values_sorted[idx(0.50)], 2),
    }

def detect_anomalies(downloads, uploads, pings, connection_types=None):
    """
    Detect anomalies in speed test data using connection-type-specific thresholds.
    
    Args:
        downloads: List of download speeds
        uploads: List of upload speeds
        pings: List of ping latencies
        connection_types: List of connection types (optional, for smarter thresholding)
    
    Returns:
        List of anomaly descriptions
    """
    anomalies = []
    
    if downloads:
        avg_dl = mean(downloads)
        min_dl = min(downloads)
        
        # Determine threshold based on connection type
        if connection_types:
            # Get most common connection type
            most_common_conn = Counter(connection_types).most_common(1)[0][0] if connection_types else None
            # Get threshold for this connection type, fallback to default
            expected_speed = CONNECTION_TYPE_THRESHOLDS.get(most_common_conn, EXPECTED_SPEED_MBPS)
        else:
            expected_speed = EXPECTED_SPEED_MBPS
        
        threshold_dl = expected_speed * (1 - TOLERANCE_PERCENT/100)

        if avg_dl < threshold_dl:
            anomalies.append(f"Below threshold: avg download {avg_dl:.2f} Mbps < {threshold_dl:.2f} Mbps")
            log.warning(f"Below threshold: avg download {avg_dl:.2f} Mbps < {threshold_dl:.2f} Mbps")

        if min_dl < (threshold_dl * 0.5):
            anomalies.append(f"Severe degradation: min download {min_dl:.2f} Mbps")
            log.warning(f"Severe degradation detected: min download {min_dl:.2f} Mbps")

        # Connection-type-aware performance check
        if expected_speed == 100 and avg_dl < 80:  # Wi-Fi 2.4GHz
            anomalies.append(f"Performance drop: avg download {avg_dl:.2f} Mbps < 80 Mbps (2.4GHz threshold)")
            log.warning(f"Performance drop detected: avg download {avg_dl:.2f} Mbps")
        elif expected_speed >= 200 and avg_dl < 150:  # Wi-Fi 5GHz / Ethernet
            anomalies.append(f"Performance drop: avg download {avg_dl:.2f} Mbps < 150 Mbps")
            log.warning(f"Performance drop detected: avg download {avg_dl:.2f} Mbps")

    if pings:
        avg_ping = mean(pings)
        max_ping = max(pings)

        if avg_ping > 20:
            anomalies.append(f"High latency: avg ping {avg_ping:.2f} ms")
            log.warning(f"High latency detected: avg ping {avg_ping:.2f} ms")

        if max_ping > 50:
            anomalies.append(f"Latency spike: max ping {max_ping:.2f} ms")
            log.warning(f"Latency spike detected: max ping {max_ping:.2f} ms")

    return anomalies

def emit_success_event(mode: str, date: str = None):
    """Send a success signal to EventBridge when aggregation completes."""
    detail = {"status": "success", "mode": mode}
    # if date:
    #     detail["date"] = date
    # events.put_events(
    #     Entries=[
    #         {
    #             "Source": "vd-speed-test.aggregator",
    #             "DetailType": "AggregationComplete",
    #             "Detail": json.dumps(detail),
    #             "EventBusName": "default"
    #         }
    #     ]
    # )
    log.info(f" Emitted success event for mode={mode}")

# --- Daily aggregation ---------------------------------------------------------
@log_execution
def aggregate_for_date(target_dt: datetime.datetime):
    """Aggregate all speed test results for the given IST date."""
    year = target_dt.strftime("%Y")
    month = target_dt.strftime("%Y%m")
    day = target_dt.strftime("%Y%m%d")
    prefix = f"year={year}/month={month}/day={day}/"
    log.info(f"Scanning prefix: {prefix}")

    downloads, uploads, pings = [], [], []
    servers, result_urls = [], []
    ips = set()
    connection_types = []
    count = 0
    errors_count = 0

    for key in list_objects(prefix):
        if not key.endswith(".json"):
            continue
        try:
            rec = read_json(key)
            dl = parse_mbps(rec.get("download_mbps"))
            ul = parse_mbps(rec.get("upload_mbps"))
            ping = parse_float(rec.get("ping_ms"))

            if dl is None or ul is None:
                errors_count += 1
                continue

            downloads.append(dl)
            uploads.append(ul)
            pings.append(ping)
            count += 1

            s_name = (rec.get("server_name") or "").strip()
            s_host = (rec.get("server_host") or "").strip()
            s_city = (rec.get("server_city") or "").strip()
            s_country = (rec.get("server_country") or "").strip()
            parts = [p for p in [s_name, s_host, s_city] if p]
            label = " – ".join(parts)
            if s_country:
                label += f" ({s_country})"
            servers.append(label)

            url = rec.get("result_url")
            if isinstance(url, str) and url.startswith("http"):
                result_urls.append(url)

            ip = rec.get("public_ip")
            if isinstance(ip, str) and ip:
                ips.add(ip)
            
            conn_type = rec.get("connection_type")
            if conn_type:
                connection_types.append(conn_type)

        except Exception as e:
            log.warning(f"Skipping {key}: {e}")
            errors_count += 1

    if count == 0:
        log.warning(f"No data found for date {day}")
        return None

    anomalies = detect_anomalies(downloads, uploads, pings, connection_types)

    expected_records = 96  # 15-min intervals
    completion_rate = (count / expected_records) * 100
    if count < expected_records * 0.8:
        log.warning(f"Low data completion: {count}/{expected_records} records ({completion_rate:.1f}%)")
        anomalies.append(f"Low completion rate: {completion_rate:.1f}%")

    if errors_count > 5:
        log.warning(f"High error rate: {errors_count} failed records")

    top_servers = [s for s, _ in Counter(servers).most_common(5)]
    top_connection_types = [ct for ct, _ in Counter(connection_types).most_common(3)]
    
    # Get the threshold for the most common connection type
    most_common_conn = top_connection_types[0] if top_connection_types else None
    threshold_used = CONNECTION_TYPE_THRESHOLDS.get(most_common_conn, EXPECTED_SPEED_MBPS)

    summary = {
        "date_ist": target_dt.strftime("%Y-%m-%d"),
        "records": count,
        "completion_rate": round(completion_rate, 1),
        "errors": errors_count,
        "overall": {
            "download_mbps": stats(downloads),
            "upload_mbps": stats(uploads),
            "ping_ms": stats(pings),
        },
        "servers_top": top_servers,
        "result_urls": result_urls,
        "public_ips": sorted(list(ips)),
        "connection_types": top_connection_types,
        "anomalies": anomalies,
        "threshold_mbps": threshold_used,
        "connection_type_thresholds": CONNECTION_TYPE_THRESHOLDS,
    }

    log.info(f"Aggregated {count} records for {day} with {len(anomalies)} anomalies")
    return summary

@log_execution
def upload_summary(summary: dict, target_dt: datetime.datetime) -> str:
    """Upload the daily summary JSON back to S3."""
    year = target_dt.strftime("%Y")
    month = target_dt.strftime("%Y%m")
    day = target_dt.strftime("%Y%m%d")
    key = f"aggregated/year={year}/month={month}/day={day}/speed_test_summary.json"

    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=json.dumps(summary, indent=2, ensure_ascii=False),
        ContentType="application/json",
    )
    log.info(f"Uploaded aggregated summary to s3://{S3_BUCKET}/{key}")
    return key

@log_execution
def run_daily(custom_date: str = None):
    """
    Run daily aggregation. If custom_date (YYYY-MM-DD) is provided, aggregate for that day.
    Otherwise, aggregate for the previous IST day.
    """
    if custom_date:
        try:
            target_date = datetime.datetime.strptime(custom_date, "%Y-%m-%d").date()
            log.info(f"Running manual backfill for date {custom_date}")
        except ValueError:
            log.error(f"Invalid date format: {custom_date}, expected YYYY-MM-DD")
            return {"message": f"Invalid date: {custom_date}", "records": 0}
    else:
        now_ist = datetime.datetime.now(TIMEZONE)
        target_date = (now_ist - datetime.timedelta(days=1)).date()

    target_dt = datetime.datetime.combine(target_date, datetime.time.min).replace(tzinfo=TIMEZONE)
    log.info(f"Aggregating for {target_dt.strftime('%Y-%m-%d')} IST")

    summary = aggregate_for_date(target_dt)
    if not summary:
        log.error("No records found for aggregation")
        return {"message": "No records found", "records": 0}

    key = upload_summary(summary, target_dt)
    result = {
        "message": "Daily aggregation complete",
        "records": summary["records"],
        "completion_rate": summary["completion_rate"],
        "errors": summary["errors"],
        "avg_download": summary["overall"]["download_mbps"]["avg"],
        "avg_upload": summary["overall"]["upload_mbps"]["avg"],
        "avg_ping": summary["overall"]["ping_ms"]["avg"],
        "unique_servers": summary.get("servers_top", []),
        "urls_count": len(summary.get("result_urls", [])),
        "unique_ips": summary.get("public_ips", []),
        "anomalies_count": len(summary.get("anomalies", [])),
        "s3_key": key,
    }
    log.info(f"Aggregation summary: {json.dumps(result, indent=2)}")
    emit_success_event("daily")      # at end of run_daily
    return result

# --- Hourly rollup (aggregate minute data into hourly summaries) --------------
@log_execution
def aggregate_hourly():
    """
    Aggregate all minute-level data for the previous hour into an hourly summary.
    """
    now_ist = datetime.datetime.now(TIMEZONE)
    # Target the previous completed hour
    target_hour = (now_ist - datetime.timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    
    year = target_hour.strftime("%Y")
    month = target_hour.strftime("%Y%m")
    day = target_hour.strftime("%Y%m%d")
    hour = target_hour.strftime("%Y%m%d%H")
    
    prefix = f"year={year}/month={month}/day={day}/hour={hour}/"
    log.info(f"Scanning prefix for hourly aggregation: {prefix}")

    downloads, uploads, pings = [], [], []
    servers = []
    ips = set()
    connection_types = []
    count = 0
    errors_count = 0

    for key in list_objects(prefix):
        if not key.endswith(".json"):
            continue
        try:
            rec = read_json(key)
            dl = parse_mbps(rec.get("download_mbps"))
            ul = parse_mbps(rec.get("upload_mbps"))
            ping = parse_float(rec.get("ping_ms"))

            if dl is None or ul is None:
                errors_count += 1
                continue

            downloads.append(dl)
            uploads.append(ul)
            pings.append(ping)
            count += 1

            s_name = (rec.get("server_name") or "").strip()
            s_host = (rec.get("server_host") or "").strip()
            s_city = (rec.get("server_city") or "").strip()
            s_country = (rec.get("server_country") or "").strip()
            parts = [p for p in [s_name, s_host, s_city] if p]
            label = " – ".join(parts)
            if s_country:
                label += f" ({s_country})"
            servers.append(label)

            ip = rec.get("public_ip")
            if isinstance(ip, str) and ip:
                ips.add(ip)
            
            conn_type = rec.get("connection_type")
            if conn_type:
                connection_types.append(conn_type)

        except Exception as e:
            log.warning(f"Skipping {key}: {e}")
            errors_count += 1

    if count == 0:
        log.warning(f"No data found for hour {hour}")
        return None

    anomalies = detect_anomalies(downloads, uploads, pings, connection_types)
    
    # Expect 4 records per hour (15-min intervals: 00, 15, 30, 45)
    # But proceed with partial data (1-4 files) as they become available
    expected_records = 4
    completion_rate = (count / expected_records) * 100
    if count < expected_records:
        log.info(f"Partial hour data: {count}/{expected_records} records ({completion_rate:.1f}%)")
        # Note: We still aggregate with whatever data is available

    top_servers = [s for s, _ in Counter(servers).most_common(3)]
    
    # Collect all unique connection types from the hour
    unique_connection_types = sorted(list(set(connection_types))) if connection_types else []
    
    # Get the threshold for the most common connection type
    most_common_conn = Counter(connection_types).most_common(1)[0][0] if connection_types else None
    threshold_used = CONNECTION_TYPE_THRESHOLDS.get(most_common_conn, EXPECTED_SPEED_MBPS)

    summary = {
        "hour_ist": target_hour.strftime("%Y-%m-%d %H:00"),
        "records": count,
        "completion_rate": round(completion_rate, 1),
        "errors": errors_count,
        "overall": {
            "download_mbps": stats(downloads),
            "upload_mbps": stats(uploads),
            "ping_ms": stats(pings),
        },
        "servers_top": top_servers,
        "public_ips": sorted(list(ips)),
        "connection_types": unique_connection_types,
        "anomalies": anomalies,
        "threshold_mbps": threshold_used,
        "connection_type_thresholds": CONNECTION_TYPE_THRESHOLDS,
    }

    # Upload to hourly bucket
    key = f"aggregated/year={year}/month={month}/day={day}/hour={hour}/speed_test_summary.json"
    s3.put_object(
        Bucket=S3_BUCKET_HOURLY,
        Key=key,
        Body=json.dumps(summary, indent=2, ensure_ascii=False),
        ContentType="application/json",
    )
    log.info(f"Hourly summary uploaded to s3://{S3_BUCKET_HOURLY}/{key}")
    emit_success_event("hourly")
    return summary

# --- Weekly rollup (last completed Mon..Sun) ----------------------------------
@log_execution
def aggregate_weekly():
    """
    Aggregate the last COMPLETED week (Mon-Sun). 
    Always aggregates the previous week to ensure all 7 days of data are available.
    """
    today_ist = datetime.datetime.now(TIMEZONE).date()
    
    # Always go back to the previous completed week
    # Find Monday of current week, then go back 7 days to get previous Monday
    current_week_monday = today_ist - datetime.timedelta(days=today_ist.weekday())
    this_monday = current_week_monday - datetime.timedelta(days=7)
    this_sunday = this_monday + datetime.timedelta(days=6)

    log.info(f"Aggregating weekly data for {this_monday} to {this_sunday} (previous completed week)")
    
    daily_summaries = []
    missing_days = []
    d = this_monday
    while d <= this_sunday:
        y, m, dd = d.strftime("%Y"), d.strftime("%Y%m"), d.strftime("%Y%m%d")
        key = f"aggregated/year={y}/month={m}/day={dd}/speed_test_summary.json"
        try:
            obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
            daily_summaries.append(json.loads(obj["Body"].read()))
            log.info(f"Loaded daily summary for {dd}")
        except s3.exceptions.NoSuchKey:
            log.warning(f"Missing daily summary for {dd} (key: {key})")
            missing_days.append(dd)
        except Exception as e:
            log.error(f"Error reading {key}: {e}")
            missing_days.append(dd)
        d += datetime.timedelta(days=1)

    log.info(f"Weekly aggregation: Found {len(daily_summaries)}/7 daily summaries, missing {len(missing_days)} days: {missing_days}")
    
    if not daily_summaries:
        log.error(f"Weekly aggregation failed: No daily summaries found for week {this_monday} to {this_sunday}")
        return None
    
    if len(daily_summaries) < 3:
        log.warning(f"Weekly aggregation: Only {len(daily_summaries)} days available, but proceeding with partial data")
    
    log.info(f"Proceeding with weekly aggregation using {len(daily_summaries)} daily summaries")

    # Collect all unique connection types from the week
    all_connection_types = set()
    for ds in daily_summaries:
        conn_types = ds.get("connection_types", [])
        if conn_types:
            all_connection_types.update(conn_types)
    unique_connection_types = sorted(list(all_connection_types)) if all_connection_types else []

    summary = {
        "week_start": str(this_monday),
        "week_end": str(this_sunday),
        "days": len(daily_summaries),
        "avg_download": round(mean([x["overall"]["download_mbps"]["avg"] for x in daily_summaries]), 2),
        "avg_upload": round(mean([x["overall"]["upload_mbps"]["avg"] for x in daily_summaries]), 2),
        "avg_ping": round(mean([x["overall"]["ping_ms"]["avg"] for x in daily_summaries]), 2),
        "connection_types": unique_connection_types,
    }

    # Use ISO week number (Monday-based, 1-53)
    iso_year, iso_week, _ = this_monday.isocalendar()
    week_label = f"{iso_year}W{iso_week:02d}"
    key = f"aggregated/year={this_monday.year}/week={week_label}/speed_test_summary.json"
    
    log.info(f"Uploading weekly summary to {key} (avg_download: {summary['avg_download']} Mbps)")
    
    s3.put_object(
        Bucket=S3_BUCKET_WEEKLY,
        Key=key,
        Body=json.dumps(summary, indent=2),
        ContentType="application/json",
    )
    log.info(f"Weekly summary uploaded to s3://{S3_BUCKET_WEEKLY}/{key}")
    emit_success_event("weekly")     # at end of aggregate_weekly
    return summary

# --- Monthly rollup (previous calendar month) ---------------------------------
@log_execution
def aggregate_monthly():
    """Aggregate all daily summaries for the current month up to yesterday (last completed day)."""
    today = datetime.datetime.now(TIMEZONE).date()
    yesterday = today - datetime.timedelta(days=1)
    
    # Aggregate the month that just completed (yesterday's month)
    first_day = yesterday.replace(day=1)
    last_day = yesterday
    month_tag = first_day.strftime("%Y%m")

    log.info(f"Aggregating monthly data for {month_tag} ({first_day} to {last_day}) - up to yesterday")
    
    summaries = []
    missing_days = []
    d = first_day
    while d <= last_day:
        y, m, dd = d.strftime("%Y"), d.strftime("%Y%m"), d.strftime("%Y%m%d")
        key = f"aggregated/year={y}/month={m}/day={dd}/speed_test_summary.json"
        try:
            obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
            summaries.append(json.loads(obj["Body"].read()))
        except s3.exceptions.NoSuchKey:
            log.warning(f"Missing daily summary for {dd}")
            missing_days.append(dd)
        except Exception as e:
            log.error(f"Error reading {key}: {e}")
            missing_days.append(dd)
        d += datetime.timedelta(days=1)

    log.info(f"Monthly aggregation: Found {len(summaries)} daily summaries, missing {len(missing_days)} days")
    
    if not summaries:
        log.error(f"Monthly aggregation failed: No daily summaries found for month {month_tag}")
        return None
    
    if len(missing_days) > len(summaries):
        log.warning(f"Monthly aggregation: More days missing ({len(missing_days)}) than available ({len(summaries)}), but proceeding")
    
    log.info(f"Proceeding with monthly aggregation using {len(summaries)} daily summaries")

    # Collect all unique connection types from the month
    all_connection_types = set()
    for ds in summaries:
        conn_types = ds.get("connection_types", [])
        if conn_types:
            all_connection_types.update(conn_types)
    unique_connection_types = sorted(list(all_connection_types)) if all_connection_types else []

    summary = {
        "month": month_tag,
        "days": len(summaries),
        "avg_download": round(mean([x["overall"]["download_mbps"]["avg"] for x in summaries]), 2),
        "avg_upload": round(mean([x["overall"]["upload_mbps"]["avg"] for x in summaries]), 2),
        "avg_ping": round(mean([x["overall"]["ping_ms"]["avg"] for x in summaries]), 2),
        "connection_types": unique_connection_types,
    }

    key = f"aggregated/year={first_day.year}/month={month_tag}/speed_test_summary.json"
    
    log.info(f"Uploading monthly summary to {key} (avg_download: {summary['avg_download']} Mbps, days: {summary['days']})")
    
    s3.put_object(
        Bucket=S3_BUCKET_MONTHLY,
        Key=key,
        Body=json.dumps(summary, indent=2),
        ContentType="application/json",
    )
    log.info(f"Monthly summary uploaded to s3://{S3_BUCKET_MONTHLY}/{key}")
    emit_success_event("monthly")     # at end of aggregate_monthly
    return summary

# --- Yearly rollup (previous calendar year) -----------------------------------
@log_execution
def aggregate_yearly():
    """Aggregate all monthly summaries for the current year (YTD)."""
    now_ist = datetime.datetime.now(TIMEZONE).date()
    current_year = now_ist.year
    summaries = []

    # Look for all monthly summaries from Jan up to current month
    for m in range(1, now_ist.month + 1):
        month_str = f"{current_year}{m:02d}"
        key = f"aggregated/year={current_year}/month={month_str}/speed_test_summary.json"
        try:
            obj = s3.get_object(Bucket=S3_BUCKET_MONTHLY, Key=key)
            summaries.append(json.loads(obj["Body"].read()))
        except Exception as e:
            log.warning(f"Skipping missing month {month_str}: {e}")
            continue

    if not summaries:
        log.warning(f"No monthly summaries found for {current_year}")
        return None

    # Collect all unique connection types from the year
    all_connection_types = set()
    for ms in summaries:
        conn_types = ms.get("connection_types", [])
        if conn_types:
            all_connection_types.update(conn_types)
    unique_connection_types = sorted(list(all_connection_types)) if all_connection_types else []

    summary = {
        "year": current_year,
        "months_aggregated": len(summaries),
        "avg_download": round(mean([x["avg_download"] for x in summaries]), 2),
        "avg_upload": round(mean([x["avg_upload"] for x in summaries]), 2),
        "avg_ping": round(mean([x["avg_ping"] for x in summaries]), 2),
        "connection_types": unique_connection_types,
    }

    key = f"aggregated/year={current_year}/speed_test_summary.json"
    s3.put_object(
        Bucket=S3_BUCKET_YEARLY,
        Key=key,
        Body=json.dumps(summary, indent=2),
        ContentType="application/json",
    )
    log.info(f"Year-to-date summary uploaded to s3://{S3_BUCKET_YEARLY}/{key}")
    emit_success_event("yearly")     # at end of aggregate_yearly
    return summary

# --- Lambda handler -----------------------------------------------------------
# ---------------------------------------------------------------------------
# 🔀 Extended Lambda Handler (supporting "mode": hourly|daily|weekly|monthly|yearly)
# ---------------------------------------------------------------------------
def lambda_handler(event, context):
    mode = (event or {}).get("mode") if isinstance(event, dict) else None
    log.info(f"Lambda trigger - mode={mode or 'daily'}")
    try:
        if mode == "hourly":
            result = aggregate_hourly()
        elif mode == "weekly":
            result = aggregate_weekly()
        elif mode == "monthly":
            result = aggregate_monthly()
        elif mode == "yearly":
            result = aggregate_yearly()
        else:
            custom_date = (event or {}).get("date")
            result = run_daily(custom_date)


        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"message": "ok", "mode": mode or "daily", "result": result}, indent=2),
        }
    except Exception as e:
        log.exception(f"Lambda failed in {mode or 'daily'} mode: {e}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": str(e)}),
        }

if __name__ == "__main__":
    # Local quick tests (uncomment the one you want)
    # print(json.dumps(run_daily(), indent=2))
    # print(json.dumps(aggregate_hourly(), indent=2))
    # print(json.dumps(aggregate_weekly(), indent=2))
    # print(json.dumps(aggregate_monthly(), indent=2))
    # print(json.dumps(aggregate_yearly(), indent=2))
    pass

