#!/usr/bin/env python3
"""
vd-speed-test daily aggregator Lambda
-------------------------------------
Aggregates individual minute-level internet speed test results from S3 into a
daily summary, computes statistics, and writes an aggregated JSON file back
to S3 under:

  aggregated/year=YYYY/month=YYYYMM/day=YYYYMMDD/speed_summary_YYYYMMDD.json
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

# --- Configuration ------------------------------------------------------------
S3_BUCKET = "vd-speed-test"
AWS_REGION1 = "ap-south-1"
TIMEZONE = pytz.timezone("Asia/Kolkata")

LOG_FILE_PATH = os.path.join(os.getcwd(), "daily_aggregator.log")
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MiB
LOG_BACKUP_COUNT = 5
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
HOSTNAME = os.getenv("HOSTNAME", os.uname().nodename)

# --- AWS Client ---------------------------------------------------------------
s3 = boto3.client("s3", region_name=AWS_REGION1)

# --- Custom JSON Logger -------------------------------------------------------
class CustomLogger:
    def __init__(self, name=__name__, level=LOG_LEVEL):
        self.logger = logging.getLogger(name)
        if not self.logger.handlers:
            formatter = self.JsonFormatter()

            # Always log to stdout (CloudWatch will capture)
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)

            # Add rotating file handler for local runs
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

# --- Logging Decorator --------------------------------------------------------
def log_execution(func):
    """Decorator to log start, success, and failure of key tasks."""
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

# --- Helper Functions ---------------------------------------------------------
def list_objects(prefix: str):
    """Yield all S3 object keys for the given prefix."""
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            yield obj["Key"]

def read_json(key: str) -> dict:
    """Read a JSON file from S3 and return it as a dict."""
    obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
    return json.loads(obj["Body"].read().decode("utf-8"))

def parse_float(value):
    """Convert strings like '6.58 ms' or '184.52 Mbps' to float."""
    if isinstance(value, str):
        value = value.replace("ms", "").replace("Mbps", "").strip()
    try:
        return float(value)
    except ValueError:
        return None  # or 0 if you prefer
    
def parse_mbps(value_with_suffix):
    """Convert '123.45 Mbps' → 123.45 (float)."""
    try:
        return float(str(value_with_suffix).strip().split()[0])
    except Exception:
        return None

def stats(values):
    """Compute common statistics for a numeric list."""
    if not values:
        return {}
    values_sorted = sorted(values)
    p95_index = int(0.95 * (len(values_sorted) - 1)) if len(values_sorted) > 1 else 0
    p99_index = int(0.99 * (len(values_sorted) - 1)) if len(values_sorted) > 1 else 0
    p90_index = int(0.90 * (len(values_sorted) - 1)) if len(values_sorted) > 1 else 0
    p50_index = int(0.50 * (len(values_sorted) - 1)) if len(values_sorted) > 1 else 0
    return {
        "avg": round(mean(values), 2),
        "median": round(median(values), 2),
        "max": round(max(values), 2),
        "min": round(min(values), 2),
        "p99": round(values_sorted[p99_index], 2),
        "p95": round(values_sorted[p95_index], 2),
        "p90": round(values_sorted[p90_index], 2),
        "p50": round(values_sorted[p50_index], 2),
    }

# --- Core Aggregation ---------------------------------------------------------
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
    count = 0

    for key in list_objects(prefix):
        if not key.endswith(".json"):
            continue
        try:
            rec = read_json(key)
            dl = parse_mbps(rec.get("download_mbps"))
            ul = parse_mbps(rec.get("upload_mbps"))
            ping = parse_float(rec.get("ping_ms"))

            if dl is None or ul is None:
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

        except Exception as e:
            log.warning(f"Skipping {key}: {e}")

    if count == 0:
        log.warning("No records found for given date.")
        return None

    top_servers = [s for s, _ in Counter(servers).most_common(5)]

    summary = {
        "date_ist": target_dt.strftime("%Y-%m-%d"),
        "records": count,
        "overall": {
            "download_mbps": stats(downloads),
            "upload_mbps": stats(uploads),
            "ping_ms": stats(pings),
        },
        "servers_top": top_servers,
        "result_urls": result_urls,
        "public_ips": sorted(list(ips)),
    }

    log.info(f"Aggregated {count} records for {day}")
    return summary

@log_execution
def upload_summary(summary: dict, target_dt: datetime.datetime) -> str:
    """Upload the daily summary JSON back to S3."""
    year = target_dt.strftime("%Y")
    month = target_dt.strftime("%Y%m")
    day = target_dt.strftime("%Y%m%d")
    key = f"aggregated/year={year}/month={month}/day={day}/speed_summary_{day}.json"

    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=json.dumps(summary, indent=2, ensure_ascii=False),
        ContentType="application/json",
    )
    log.info(f"Uploaded aggregated summary to s3://{S3_BUCKET}/{key}")
    return key

# --- Entrypoints --------------------------------------------------------------
@log_execution
def main():
    """Main aggregation logic (run locally or from Lambda)."""
    now_ist = datetime.datetime.now(TIMEZONE)
    target_date = (now_ist - datetime.timedelta(days=1)).date()
    target_dt = datetime.datetime.combine(target_date, datetime.time.min).replace(tzinfo=TIMEZONE)

    log.info(f"📅 Aggregating for {target_dt.strftime('%Y-%m-%d')} IST")

    summary = aggregate_for_date(target_dt)
    if not summary:
        return {"message": "No records found", "records": 0}

    key = upload_summary(summary, target_dt)
    result = {
        "message": "Daily aggregation complete",
        "records": summary["records"],
        "avg_download": summary["overall"]["download_mbps"]["avg"],
        "avg_upload": summary["overall"]["upload_mbps"]["avg"],
        "avg_ping": summary["overall"]["ping_ms"]["avg"],
        "unique_servers": summary.get("servers_top", []),
        "urls_count": len(summary.get("result_urls", [])),
        "unique_ips": summary.get("public_ips", []),
        "s3_key": key,
    }

    log.info(f"Aggregation summary: {json.dumps(result, indent=2)}")
    return result

def lambda_handler(event, context):
    """AWS Lambda handler."""
    log.info("Lambda trigger received for daily aggregation.")
    try:
        result = main()
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(result),
        }
    except Exception as e:
        log.exception(f"Lambda failed: {e}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": str(e)}),
        }

if __name__ == "__main__":
    log.info("Running daily aggregator locally...")
    print(json.dumps(main(), indent=2))