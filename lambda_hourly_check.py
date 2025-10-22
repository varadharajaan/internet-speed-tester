#!/usr/bin/env python3
import boto3
import json
import datetime
import urllib.parse
import os

S3_BUCKET = os.environ.get("S3_BUCKET", "vd-speed-test")
AWS_REGION1 = "ap-south-1"
s3 = boto3.client("s3", region_name=AWS_REGION1)

def list_objects(prefix):
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            yield obj["Key"]

def lambda_handler(event, context):
    # Parse query parameter: ?date=YYYY-MM-DD
    params = event.get("queryStringParameters") or {}
    date_str = params.get("date")

    if not date_str:
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Missing ?date=YYYY-MM-DD parameter"})
        }

    try:
        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Invalid date format. Use YYYY-MM-DD"})
        }

    # Build prefix for that date
    year = date_obj.strftime("%Y")
    month = date_obj.strftime("%Y%m")
    day = date_obj.strftime("%Y%m%d")
    prefix = f"year={year}/month={month}/day={day}/"

    hour_counts = {}

    # Loop through all objects in that day's prefix
    for key in list_objects(prefix):
        parts = key.split("/")
        if len(parts) < 5:
            continue
        # parts like: year=2025/month=202510/day=20251022/hour=2025102201/minute=202510220115/file.json
        hour_part = next((p for p in parts if p.startswith("hour=")), None)
        minute_part = next((p for p in parts if p.startswith("minute=")), None)

        if not hour_part or not minute_part:
            continue

        hour = hour_part.split("=")[1]
        hour_counts.setdefault(hour, set()).add(minute_part.split("=")[1])

    # Summarize counts
    summary = {h: len(minutes) for h, minutes in sorted(hour_counts.items())}

    result = {
        "date": date_str,
        "total_hours_found": len(summary),
        "hours": summary
    }

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(result, indent=2)
    }