#!/usr/bin/env python3
"""
vd-speed-test hourly coverage Lambda
------------------------------------
Summarizes how many minute-level internet speed test records
exist per hour for a given date (?date=YYYY-MM-DD).
"""

import boto3
import json
import datetime
import os
import sys
import logging
from functools import wraps
from logging.handlers import RotatingFileHandler

# --- Configuration from config.json --------------------------------------------
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
DEFAULT_CONFIG = {
    "s3_bucket": "vd-speed-test",
    "s3_bucket_hourly": "vd-speed-test-hourly-prod",
    "s3_bucket_weekly": "vd-speed-test-weekly-prod",
    "s3_bucket_monthly": "vd-speed-test-monthly-prod",
    "s3_bucket_yearly": "vd-speed-test-yearly-prod",
    "aws_region": "ap-south-1",
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

# Extract configuration values (hourly_check only uses daily bucket for minute-level data)
S3_BUCKET = os.environ.get("S3_BUCKET", config.get("s3_bucket"))
AWS_REGION1 = os.getenv("AWS_REGION1", config.get("aws_region"))
LOG_FILE_PATH = os.path.join(os.getcwd(), "hourly_summary.log")
LOG_MAX_BYTES = config.get("log_max_bytes")
LOG_BACKUP_COUNT = config.get("log_backup_count")
LOG_LEVEL = os.getenv("LOG_LEVEL", config.get("log_level")).upper()
try:
    HOSTNAME = os.getenv("HOSTNAME", os.uname().nodename)
except AttributeError:
    HOSTNAME = os.getenv("HOSTNAME", "unknown-host")

s3 = boto3.client("s3", region_name=AWS_REGION1)

# --- Custom JSON Logger -------------------------------------------------------
class CustomLogger:
    def __init__(self, name=__name__, level=LOG_LEVEL):
        self.logger = logging.getLogger(name)
        if not self.logger.handlers:
            formatter = self.JsonFormatter()

            # CloudWatch logs (stdout)
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)

            # Local file rotation (only for local runs)
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
    """Decorator to log Lambda function execution."""
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

# --- S3 Helper Functions ------------------------------------------------------
def list_objects(prefix):
    """Yield all S3 object keys for the given prefix."""
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            yield obj["Key"]

# --- Core Lambda Logic --------------------------------------------------------
@log_execution
def summarize_hourly(date_str: str):
    """Summarize per-hour coverage for given date (YYYY-MM-DD)."""
    try:
        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Invalid date format. Use YYYY-MM-DD")

    year = date_obj.strftime("%Y")
    month = date_obj.strftime("%Y%m")
    day = date_obj.strftime("%Y%m%d")
    prefix = f"year={year}/month={month}/day={day}/"
    log.info(f"Scanning S3 prefix: {prefix}")

    hour_counts = {}
    count = 0

    for key in list_objects(prefix):
        if not key.endswith(".json"):
            continue
        parts = key.split("/")
        if len(parts) < 5:
            continue

        hour_part = next((p for p in parts if p.startswith("hour=")), None)
        minute_part = next((p for p in parts if p.startswith("minute=")), None)

        if not hour_part or not minute_part:
            continue

        hour = hour_part.split("=")[1]
        minute = minute_part.split("=")[1]
        hour_counts.setdefault(hour, set()).add(minute)
        count += 1

    summary = {h: len(minutes) for h, minutes in sorted(hour_counts.items())}
    result = {
        "date": date_str,
        "total_hours_found": len(summary),
        "total_records": count,
        "hours": summary,
    }
    log.info(f"Hourly summary computed for {date_str}: {len(summary)} hours found.")
    return result

# --- Lambda Handler -----------------------------------------------------------
@log_execution
def lambda_handler(event, context):
    """AWS Lambda entrypoint."""
    log.info("Lambda triggered for hourly summary check.")

    params = event.get("queryStringParameters") or {}
    date_str = params.get("date")

    if not date_str:
        log.warning("Missing ?date=YYYY-MM-DD parameter.")
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Missing ?date=YYYY-MM-DD parameter"})
        }

    try:
        result = summarize_hourly(date_str)
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(result, indent=2)
        }
    except ValueError as ve:
        log.error(f"Invalid input: {ve}")
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": str(ve)})
        }
    except Exception as e:
        log.exception(f"Unexpected error: {e}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": str(e)})
        }

# --- Local Test Entrypoint ----------------------------------------------------
if __name__ == "__main__":
    log.info("Running hourly summary Lambda locally...")
    test_event = {"queryStringParameters": {"date": datetime.date.today().isoformat()}}
    print(json.dumps(lambda_handler(test_event, None), indent=2))