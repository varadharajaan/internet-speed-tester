#!/usr/bin/env python3
"""
vd-speed-test hourly coverage Lambda
------------------------------------
Summarizes how many minute-level internet speed test records
exist per hour for a given date (?date=YYYY-MM-DD).
"""

import json
import datetime

# --- Shared module imports ----------------------------------------------------
from shared import get_config, get_logger, get_s3_client
from shared.logging import log_execution

# --- Configuration via shared module ------------------------------------------
config = get_config()
log = get_logger(__name__)
s3 = get_s3_client()

# Convenience alias
S3_BUCKET = config.s3_bucket

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