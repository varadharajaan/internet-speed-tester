#!/usr/bin/env python3
"""
vd-speed-test aggregator Lambda
- Daily: aggregates minute-level results into day summary, writes to:
    s3://<S3_BUCKET>/aggregated/year=YYYY/month=YYYYMM/day=YYYYMMDD/speed_summary_YYYYMMDD.json
- Weekly/Monthly/Yearly: roll-ups from daily → weekly/monthly/yearly, writing into:
    s3://<S3_BUCKET_WEEKLY>/aggregated/...
    s3://<S3_BUCKET_MONTHLY>/aggregated/...
    s3://<S3_BUCKET_YEARLY>/aggregated/...
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

# --- Configuration ------------------------------------------------------------
S3_BUCKET = os.environ.get("S3_BUCKET", "vd-speed-test")
AWS_REGION1 = os.environ.get("AWS_REGION1", "ap-south-1")
TIMEZONE = pytz.timezone("Asia/Kolkata")
EXPECTED_SPEED_MBPS = float(os.environ.get("EXPECTED_SPEED_MBPS", "200"))
TOLERANCE_PERCENT = float(os.environ.get("TOLERANCE_PERCENT", "10"))

# Rollup buckets (match template names with -${Environment})
ENVIRONMENT = os.environ.get("ENVIRONMENT", "prod")
S3_BUCKET_WEEKLY = os.environ.get("S3_BUCKET_WEEKLY", f"vd-speed-test-weekly-{ENVIRONMENT}")
S3_BUCKET_MONTHLY = os.environ.get("S3_BUCKET_MONTHLY", f"vd-speed-test-monthly-{ENVIRONMENT}")
S3_BUCKET_YEARLY = os.environ.get("S3_BUCKET_YEARLY", f"vd-speed-test-yearly-{ENVIRONMENT}")

LOG_FILE_PATH = os.path.join(os.getcwd(), "aggregator.log")
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MiB
LOG_BACKUP_COUNT = 5
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
HOSTNAME = os.getenv("HOSTNAME", os.uname().nodename)
events = boto3.client("events", region_name=AWS_REGION1)


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

def detect_anomalies(downloads, uploads, pings):
    anomalies = []
    if downloads:
        avg_dl = mean(downloads)
        min_dl = min(downloads)
        threshold_dl = EXPECTED_SPEED_MBPS * (1 - TOLERANCE_PERCENT/100)

        if avg_dl < threshold_dl:
            anomalies.append(f"Below threshold: avg download {avg_dl:.2f} Mbps < {threshold_dl:.2f} Mbps")
            log.warning(f"Below threshold: avg download {avg_dl:.2f} Mbps < {threshold_dl:.2f} Mbps")

        if min_dl < (threshold_dl * 0.5):
            anomalies.append(f"Severe degradation: min download {min_dl:.2f} Mbps")
            log.warning(f"Severe degradation detected: min download {min_dl:.2f} Mbps")

        if avg_dl < 100:
            anomalies.append(f"Performance drop: avg download {avg_dl:.2f} Mbps < 100 Mbps")
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

        except Exception as e:
            log.warning(f"Skipping {key}: {e}")
            errors_count += 1

    if count == 0:
        log.warning(f"No data found for date {day}")
        return None

    anomalies = detect_anomalies(downloads, uploads, pings)

    expected_records = 96  # 15-min intervals
    completion_rate = (count / expected_records) * 100
    if count < expected_records * 0.8:
        log.warning(f"Low data completion: {count}/{expected_records} records ({completion_rate:.1f}%)")
        anomalies.append(f"Low completion rate: {completion_rate:.1f}%")

    if errors_count > 5:
        log.warning(f"High error rate: {errors_count} failed records")

    top_servers = [s for s, _ in Counter(servers).most_common(5)]

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
        "anomalies": anomalies,
        "threshold_mbps": EXPECTED_SPEED_MBPS,
    }

    log.info(f"Aggregated {count} records for {day} with {len(anomalies)} anomalies")
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

# --- Weekly rollup (last completed Mon..Sun) ----------------------------------
@log_execution
def aggregate_weekly():
    """
    Aggregate all available daily summaries for the current or last completed week (Mon–Sun).
    """
    today_ist = datetime.datetime.now(TIMEZONE).date()
    this_monday = today_ist - datetime.timedelta(days=today_ist.weekday())  # Monday of this week
    this_sunday = this_monday + datetime.timedelta(days=6)

    # Optionally, if today is Monday, fallback to the previous week
    if today_ist == this_monday:
        last_monday = this_monday - datetime.timedelta(days=7)
        this_sunday = last_monday + datetime.timedelta(days=6)
        this_monday = last_monday

    daily_summaries = []
    d = this_monday
    while d <= this_sunday:
        y, m, dd = d.strftime("%Y"), d.strftime("%Y%m"), d.strftime("%Y%m%d")
        key = f"aggregated/year={y}/month={m}/day={dd}/speed_summary_{dd}.json"
        try:
            obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
            daily_summaries.append(json.loads(obj["Body"].read()))
        except s3.exceptions.NoSuchKey:
            log.warning(f"Missing daily summary for {dd}")
        except Exception as e:
            log.warning(f"Error reading {key}: {e}")
        d += datetime.timedelta(days=1)

    if not daily_summaries:
        log.warning("No daily summaries found for this week")
        return None

    summary = {
        "week_start": str(this_monday),
        "week_end": str(this_sunday),
        "days": len(daily_summaries),
        "avg_download": round(mean([x["overall"]["download_mbps"]["avg"] for x in daily_summaries]), 2),
        "avg_upload": round(mean([x["overall"]["upload_mbps"]["avg"] for x in daily_summaries]), 2),
        "avg_ping": round(mean([x["overall"]["ping_ms"]["avg"] for x in daily_summaries]), 2),
    }

    week_label = f"{this_monday.strftime('%YW%W')}"
    key = f"aggregated/year={this_monday.year}/week={week_label}/weekly_summary_{week_label}.json"
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
    """Aggregate all daily summaries for the current month so far."""
    today = datetime.datetime.now(TIMEZONE).date()
    first_day = today.replace(day=1)
    _, last_day_num = monthrange(today.year, today.month)
    last_day = today  # up to today (or first_day + last_day_num for full month)
    month_tag = today.strftime("%Y%m")

    summaries = []
    d = first_day
    while d <= last_day:
        y, m, dd = d.strftime("%Y"), d.strftime("%Y%m"), d.strftime("%Y%m%d")
        key = f"aggregated/year={y}/month={m}/day={dd}/speed_summary_{dd}.json"
        try:
            obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
            summaries.append(json.loads(obj["Body"].read()))
        except Exception:
            pass
        d += datetime.timedelta(days=1)

    if not summaries:
        log.warning(f"No daily summaries found for month {month_tag}")
        return None

    summary = {
        "month": month_tag,
        "days": len(summaries),
        "avg_download": round(mean([x["overall"]["download_mbps"]["avg"] for x in summaries]), 2),
        "avg_upload": round(mean([x["overall"]["upload_mbps"]["avg"] for x in summaries]), 2),
        "avg_ping": round(mean([x["overall"]["ping_ms"]["avg"] for x in summaries]), 2),
    }

    key = f"aggregated/year={first_day.year}/month={month_tag}/monthly_summary_{month_tag}.json"
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
        key = f"aggregated/year={current_year}/month={month_str}/monthly_summary_{month_str}.json"
        try:
            obj = s3.get_object(Bucket=S3_BUCKET_MONTHLY, Key=key)
            summaries.append(json.loads(obj["Body"].read()))
        except Exception as e:
            log.warning(f"Skipping missing month {month_str}: {e}")
            continue

    if not summaries:
        log.warning(f"No monthly summaries found for {current_year}")
        return None

    summary = {
        "year": current_year,
        "months_aggregated": len(summaries),
        "avg_download": round(mean([x["avg_download"] for x in summaries]), 2),
        "avg_upload": round(mean([x["avg_upload"] for x in summaries]), 2),
        "avg_ping": round(mean([x["avg_ping"] for x in summaries]), 2),
    }

    key = f"aggregated/year={current_year}/yearly_summary_{current_year}.json"
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
# 🔀 Extended Lambda Handler (supporting "mode": daily|weekly|monthly|yearly)
# ---------------------------------------------------------------------------
def lambda_handler(event, context):
    mode = (event or {}).get("mode") if isinstance(event, dict) else None
    log.info(f"Lambda trigger — mode={mode or 'daily'}")
    try:
        if mode == "weekly":
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
    # print(json.dumps(aggregate_weekly(), indent=2))
    # print(json.dumps(aggregate_monthly(), indent=2))
    # print(json.dumps(aggregate_yearly(), indent=2))
    pass

