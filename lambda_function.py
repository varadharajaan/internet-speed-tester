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

import json
import datetime
import pytz
from statistics import mean, median
from collections import Counter

# --- Shared module imports ----------------------------------------------------
from shared import get_config, get_logger, get_s3_client, list_hosts
from shared.logging import log_execution
from shared.constants import CONNECTION_TYPE_THRESHOLDS, ANOMALY_THRESHOLDS

# --- Configuration via shared module ------------------------------------------
config = get_config()
log = get_logger(__name__)
s3 = get_s3_client()

# Convenience aliases for bucket names
S3_BUCKET = config.s3_bucket
S3_BUCKET_HOURLY = config.s3_bucket_hourly
S3_BUCKET_WEEKLY = config.s3_bucket_weekly
S3_BUCKET_MONTHLY = config.s3_bucket_monthly
S3_BUCKET_YEARLY = config.s3_bucket_yearly

TIMEZONE = pytz.timezone(config.timezone)
EXPECTED_SPEED_MBPS = config.expected_speed_mbps
TOLERANCE_PERCENT = config.tolerance_percent


# --- Helpers ------------------------------------------------------------------
def list_objects(prefix: str, bucket: str = None):
    """List all objects with given prefix from specified bucket (default: S3_BUCKET)."""
    target_bucket = bucket or S3_BUCKET
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=target_bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            yield obj["Key"]

def read_json(key: str, bucket: str = None) -> dict:
    """Read and parse JSON from S3."""
    target_bucket = bucket or S3_BUCKET
    obj = s3.get_object(Bucket=target_bucket, Key=key)
    return json.loads(obj["Body"].read().decode("utf-8"))

def get_host_prefix(host_id: str) -> str:
    """Get the S3 prefix for a host. Legacy data has no host prefix."""
    if host_id == "_legacy":
        return ""
    return f"host={host_id}/"

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
def aggregate_for_date(target_dt: datetime.datetime, host_id: str = None):
    """
    Aggregate all speed test results for the given IST date.
    If host_id is provided, only aggregate for that host.
    """
    year = target_dt.strftime("%Y")
    month = target_dt.strftime("%Y%m")
    day = target_dt.strftime("%Y%m%d")
    
    host_prefix = get_host_prefix(host_id) if host_id else ""
    prefix = f"{host_prefix}year={year}/month={month}/day={day}/"
    log.info(f"Scanning prefix: {prefix}" + (f" for host={host_id}" if host_id else " (all hosts)"))

    downloads, uploads, pings = [], [], []
    servers, result_urls = [], []
    ips = set()
    connection_types = []
    hosts_seen = set()
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

            # Track host information
            rec_host = rec.get("host_id", "_legacy")
            hosts_seen.add(rec_host)

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
        log.warning(f"No data found for date {day}" + (f" host={host_id}" if host_id else ""))
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
        "host_id": host_id or "all",
        "hosts_in_data": sorted(list(hosts_seen)),
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

    log.info(f"Aggregated {count} records for {day}" + (f" host={host_id}" if host_id else "") + f" with {len(anomalies)} anomalies")
    return summary

@log_execution
def upload_summary(summary: dict, target_dt: datetime.datetime, host_id: str = None) -> str:
    """Upload the daily summary JSON back to S3, with optional host prefix."""
    year = target_dt.strftime("%Y")
    month = target_dt.strftime("%Y%m")
    day = target_dt.strftime("%Y%m%d")
    
    # Add host prefix for per-host summaries
    if host_id and host_id != "all":
        key = f"aggregated/host={host_id}/year={year}/month={month}/day={day}/speed_test_summary.json"
    else:
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
    Run daily aggregation for all hosts. Creates per-host summaries and a global summary.
    If custom_date (YYYY-MM-DD) is provided, aggregate for that day.
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

    # Discover all hosts and aggregate for each
    hosts = list_hosts()
    all_results = []
    total_records = 0
    
    for host_id in hosts:
        log.info(f"Aggregating daily data for host: {host_id}")
        summary = aggregate_for_date(target_dt, host_id=host_id)
        if summary:
            key = upload_summary(summary, target_dt, host_id=host_id)
            all_results.append({"host_id": host_id, "records": summary["records"], "s3_key": key})
            total_records += summary["records"]
    
    # Also create a global summary across all hosts (for backward compatibility)
    log.info("Creating global summary across all hosts")
    global_summary = aggregate_for_date(target_dt, host_id=None)
    if global_summary:
        global_key = upload_summary(global_summary, target_dt, host_id="all")
        all_results.append({"host_id": "all", "records": global_summary["records"], "s3_key": global_key})
    
    if not all_results:
        log.error("No records found for aggregation across any host")
        return {"message": "No records found", "records": 0}

    result = {
        "message": "Daily aggregation complete",
        "hosts_aggregated": len(hosts),
        "total_records": total_records,
        "host_results": all_results,
    }
    
    # Add global summary stats if available
    if global_summary:
        result.update({
            "avg_download": global_summary["overall"]["download_mbps"]["avg"],
            "avg_upload": global_summary["overall"]["upload_mbps"]["avg"],
            "avg_ping": global_summary["overall"]["ping_ms"]["avg"],
            "anomalies_count": len(global_summary.get("anomalies", [])),
        })
    
    log.info(f"Aggregation summary: {json.dumps(result, indent=2)}")
    emit_success_event("daily")
    return result

# --- Hourly rollup (aggregate minute data into hourly summaries) --------------
@log_execution
def aggregate_hourly_for_host(target_hour: datetime.datetime, host_id: str = None):
    """
    Aggregate all minute-level data for a specific hour and optional host.
    """
    year = target_hour.strftime("%Y")
    month = target_hour.strftime("%Y%m")
    day = target_hour.strftime("%Y%m%d")
    hour = target_hour.strftime("%Y%m%d%H")
    
    host_prefix = get_host_prefix(host_id) if host_id else ""
    prefix = f"{host_prefix}year={year}/month={month}/day={day}/hour={hour}/"
    log.info(f"Scanning prefix for hourly aggregation: {prefix}" + (f" host={host_id}" if host_id else ""))

    downloads, uploads, pings = [], [], []
    servers = []
    ips = set()
    connection_types = []
    hosts_seen = set()
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

            rec_host = rec.get("host_id", "_legacy")
            hosts_seen.add(rec_host)

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
        log.warning(f"No data found for hour {hour}" + (f" host={host_id}" if host_id else ""))
        return None

    anomalies = detect_anomalies(downloads, uploads, pings, connection_types)
    
    expected_records = 4
    completion_rate = (count / expected_records) * 100
    if count < expected_records:
        log.info(f"Partial hour data: {count}/{expected_records} records ({completion_rate:.1f}%)")

    top_servers = [s for s, _ in Counter(servers).most_common(3)]
    unique_connection_types = sorted(list(set(connection_types))) if connection_types else []
    
    most_common_conn = Counter(connection_types).most_common(1)[0][0] if connection_types else None
    threshold_used = CONNECTION_TYPE_THRESHOLDS.get(most_common_conn, EXPECTED_SPEED_MBPS)

    summary = {
        "hour_ist": target_hour.strftime("%Y-%m-%d %H:00"),
        "host_id": host_id or "all",
        "hosts_in_data": sorted(list(hosts_seen)),
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

    return summary

@log_execution
def aggregate_hourly():
    """
    Aggregate all minute-level data for the previous hour into hourly summaries.
    Creates per-host summaries and a global summary.
    """
    now_ist = datetime.datetime.now(TIMEZONE)
    target_hour = (now_ist - datetime.timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    
    year = target_hour.strftime("%Y")
    month = target_hour.strftime("%Y%m")
    day = target_hour.strftime("%Y%m%d")
    hour = target_hour.strftime("%Y%m%d%H")
    
    # Discover all hosts and aggregate for each
    hosts = list_hosts()
    all_results = []
    
    for host_id in hosts:
        summary = aggregate_hourly_for_host(target_hour, host_id=host_id)
        if summary:
            # Upload per-host summary
            if host_id and host_id != "all":
                key = f"aggregated/host={host_id}/year={year}/month={month}/day={day}/hour={hour}/speed_test_summary.json"
            else:
                key = f"aggregated/year={year}/month={month}/day={day}/hour={hour}/speed_test_summary.json"
            
            s3.put_object(
                Bucket=S3_BUCKET_HOURLY,
                Key=key,
                Body=json.dumps(summary, indent=2, ensure_ascii=False),
                ContentType="application/json",
            )
            log.info(f"Hourly summary uploaded to s3://{S3_BUCKET_HOURLY}/{key}")
            all_results.append({"host_id": host_id, "records": summary["records"], "s3_key": key})
    
    # Global summary across all hosts
    global_summary = aggregate_hourly_for_host(target_hour, host_id=None)
    if global_summary:
        global_key = f"aggregated/year={year}/month={month}/day={day}/hour={hour}/speed_test_summary.json"
        s3.put_object(
            Bucket=S3_BUCKET_HOURLY,
            Key=global_key,
            Body=json.dumps(global_summary, indent=2, ensure_ascii=False),
            ContentType="application/json",
        )
        log.info(f"Global hourly summary uploaded to s3://{S3_BUCKET_HOURLY}/{global_key}")
    
    emit_success_event("hourly")
    return {"hosts_aggregated": len(hosts), "host_results": all_results, "global_summary": global_summary}

# --- Weekly rollup (last completed Mon..Sun) ----------------------------------
@log_execution
def aggregate_weekly_for_host(this_monday, this_sunday, host_id: str = None):
    """Aggregate weekly data for a specific host."""
    daily_summaries = []
    missing_days = []
    d = this_monday
    while d <= this_sunday:
        y, m, dd = d.strftime("%Y"), d.strftime("%Y%m"), d.strftime("%Y%m%d")
        
        # Use host-prefixed key for per-host aggregation
        if host_id and host_id != "all" and host_id != "_legacy":
            key = f"aggregated/host={host_id}/year={y}/month={m}/day={dd}/speed_test_summary.json"
        else:
            key = f"aggregated/year={y}/month={m}/day={dd}/speed_test_summary.json"
        
        try:
            obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
            daily_summaries.append(json.loads(obj["Body"].read()))
            log.info(f"Loaded daily summary for {dd}" + (f" host={host_id}" if host_id else ""))
        except s3.exceptions.NoSuchKey:
            log.warning(f"Missing daily summary for {dd} (key: {key})")
            missing_days.append(dd)
        except Exception as e:
            log.error(f"Error reading {key}: {e}")
            missing_days.append(dd)
        d += datetime.timedelta(days=1)

    log.info(f"Weekly aggregation: Found {len(daily_summaries)}/7 daily summaries" + (f" for host={host_id}" if host_id else ""))
    
    if not daily_summaries:
        return None

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
        "host_id": host_id or "all",
        "days": len(daily_summaries),
        "avg_download": round(mean([x["overall"]["download_mbps"]["avg"] for x in daily_summaries]), 2),
        "avg_upload": round(mean([x["overall"]["upload_mbps"]["avg"] for x in daily_summaries]), 2),
        "avg_ping": round(mean([x["overall"]["ping_ms"]["avg"] for x in daily_summaries]), 2),
        "connection_types": unique_connection_types,
    }

    return summary

@log_execution
def aggregate_weekly():
    """
    Aggregate the last COMPLETED week (Mon-Sun) for all hosts.
    Creates per-host summaries and a global summary.
    """
    today_ist = datetime.datetime.now(TIMEZONE).date()
    
    current_week_monday = today_ist - datetime.timedelta(days=today_ist.weekday())
    this_monday = current_week_monday - datetime.timedelta(days=7)
    this_sunday = this_monday + datetime.timedelta(days=6)

    log.info(f"Aggregating weekly data for {this_monday} to {this_sunday} (previous completed week)")
    
    # Use ISO week number
    iso_year, iso_week, _ = this_monday.isocalendar()
    week_label = f"{iso_year}W{iso_week:02d}"
    
    # Discover all hosts and aggregate for each
    hosts = list_hosts()
    all_results = []
    
    for host_id in hosts:
        summary = aggregate_weekly_for_host(this_monday, this_sunday, host_id=host_id)
        if summary:
            if host_id and host_id != "all" and host_id != "_legacy":
                key = f"aggregated/host={host_id}/year={this_monday.year}/week={week_label}/speed_test_summary.json"
            else:
                key = f"aggregated/year={this_monday.year}/week={week_label}/speed_test_summary.json"
            
            s3.put_object(
                Bucket=S3_BUCKET_WEEKLY,
                Key=key,
                Body=json.dumps(summary, indent=2),
                ContentType="application/json",
            )
            log.info(f"Weekly summary uploaded to s3://{S3_BUCKET_WEEKLY}/{key}")
            all_results.append({"host_id": host_id, "days": summary["days"], "s3_key": key})
    
    # Global summary (uses global daily summaries which already combine all hosts)
    global_summary = aggregate_weekly_for_host(this_monday, this_sunday, host_id=None)
    if global_summary:
        global_key = f"aggregated/year={this_monday.year}/week={week_label}/speed_test_summary.json"
        s3.put_object(
            Bucket=S3_BUCKET_WEEKLY,
            Key=global_key,
            Body=json.dumps(global_summary, indent=2),
            ContentType="application/json",
        )
        log.info(f"Global weekly summary uploaded to s3://{S3_BUCKET_WEEKLY}/{global_key}")
    
    emit_success_event("weekly")
    return {"week": week_label, "hosts_aggregated": len(hosts), "host_results": all_results, "global_summary": global_summary}

# --- Monthly rollup (previous calendar month) ---------------------------------
@log_execution
def aggregate_monthly_for_host(first_day, last_day, month_tag, host_id: str = None):
    """Aggregate monthly data for a specific host."""
    summaries = []
    missing_days = []
    d = first_day
    while d <= last_day:
        y, m, dd = d.strftime("%Y"), d.strftime("%Y%m"), d.strftime("%Y%m%d")
        
        if host_id and host_id != "all" and host_id != "_legacy":
            key = f"aggregated/host={host_id}/year={y}/month={m}/day={dd}/speed_test_summary.json"
        else:
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

    log.info(f"Monthly aggregation: Found {len(summaries)} daily summaries" + (f" for host={host_id}" if host_id else ""))
    
    if not summaries:
        return None

    # Collect all unique connection types
    all_connection_types = set()
    for ds in summaries:
        conn_types = ds.get("connection_types", [])
        if conn_types:
            all_connection_types.update(conn_types)
    unique_connection_types = sorted(list(all_connection_types)) if all_connection_types else []

    summary = {
        "month": month_tag,
        "host_id": host_id or "all",
        "days": len(summaries),
        "avg_download": round(mean([x["overall"]["download_mbps"]["avg"] for x in summaries]), 2),
        "avg_upload": round(mean([x["overall"]["upload_mbps"]["avg"] for x in summaries]), 2),
        "avg_ping": round(mean([x["overall"]["ping_ms"]["avg"] for x in summaries]), 2),
        "connection_types": unique_connection_types,
    }

    return summary

@log_execution
def aggregate_monthly():
    """Aggregate all daily summaries for the current month up to yesterday for all hosts."""
    today = datetime.datetime.now(TIMEZONE).date()
    yesterday = today - datetime.timedelta(days=1)
    
    first_day = yesterday.replace(day=1)
    last_day = yesterday
    month_tag = first_day.strftime("%Y%m")

    log.info(f"Aggregating monthly data for {month_tag} ({first_day} to {last_day}) - up to yesterday")
    
    # Discover all hosts
    hosts = list_hosts()
    all_results = []
    
    for host_id in hosts:
        summary = aggregate_monthly_for_host(first_day, last_day, month_tag, host_id=host_id)
        if summary:
            if host_id and host_id != "all" and host_id != "_legacy":
                key = f"aggregated/host={host_id}/year={first_day.year}/month={month_tag}/speed_test_summary.json"
            else:
                key = f"aggregated/year={first_day.year}/month={month_tag}/speed_test_summary.json"
            
            s3.put_object(
                Bucket=S3_BUCKET_MONTHLY,
                Key=key,
                Body=json.dumps(summary, indent=2),
                ContentType="application/json",
            )
            log.info(f"Monthly summary uploaded to s3://{S3_BUCKET_MONTHLY}/{key}")
            all_results.append({"host_id": host_id, "days": summary["days"], "s3_key": key})
    
    # Global summary
    global_summary = aggregate_monthly_for_host(first_day, last_day, month_tag, host_id=None)
    if global_summary:
        global_key = f"aggregated/year={first_day.year}/month={month_tag}/speed_test_summary.json"
        s3.put_object(
            Bucket=S3_BUCKET_MONTHLY,
            Key=global_key,
            Body=json.dumps(global_summary, indent=2),
            ContentType="application/json",
        )
        log.info(f"Global monthly summary uploaded to s3://{S3_BUCKET_MONTHLY}/{global_key}")
    
    emit_success_event("monthly")
    return {"month": month_tag, "hosts_aggregated": len(hosts), "host_results": all_results, "global_summary": global_summary}

# --- Yearly rollup (previous calendar year) -----------------------------------
@log_execution
def aggregate_yearly_for_host(current_year, max_month, host_id: str = None):
    """Aggregate yearly data for a specific host."""
    summaries = []

    for m in range(1, max_month + 1):
        month_str = f"{current_year}{m:02d}"
        
        if host_id and host_id != "all" and host_id != "_legacy":
            key = f"aggregated/host={host_id}/year={current_year}/month={month_str}/speed_test_summary.json"
        else:
            key = f"aggregated/year={current_year}/month={month_str}/speed_test_summary.json"
        
        try:
            obj = s3.get_object(Bucket=S3_BUCKET_MONTHLY, Key=key)
            summaries.append(json.loads(obj["Body"].read()))
        except Exception as e:
            log.warning(f"Skipping missing month {month_str}" + (f" for host={host_id}" if host_id else "") + f": {e}")
            continue

    if not summaries:
        return None

    # Collect all unique connection types
    all_connection_types = set()
    for ms in summaries:
        conn_types = ms.get("connection_types", [])
        if conn_types:
            all_connection_types.update(conn_types)
    unique_connection_types = sorted(list(all_connection_types)) if all_connection_types else []

    summary = {
        "year": current_year,
        "host_id": host_id or "all",
        "months_aggregated": len(summaries),
        "avg_download": round(mean([x["avg_download"] for x in summaries]), 2),
        "avg_upload": round(mean([x["avg_upload"] for x in summaries]), 2),
        "avg_ping": round(mean([x["avg_ping"] for x in summaries]), 2),
        "connection_types": unique_connection_types,
    }

    return summary

@log_execution
def aggregate_yearly():
    """Aggregate all monthly summaries for the previous completed year (triggered Jan 1-7)."""
    now_ist = datetime.datetime.now(TIMEZONE).date()
    
    # When triggered in early January, aggregate the PREVIOUS year (which just completed)
    # Otherwise aggregate the current year as YTD
    if now_ist.month == 1 and now_ist.day <= 7:
        # Early January: aggregate the previous year (2025 when triggered on Jan 1-7 2026)
        target_year = now_ist.year - 1
        max_month = 12  # Full year
        log.info(f"Early January trigger - aggregating previous year: {target_year}")
    else:
        # Rest of the year: aggregate current year YTD
        target_year = now_ist.year
        max_month = now_ist.month
        log.info(f"YTD trigger - aggregating current year: {target_year} up to month {max_month}")
    
    # Discover all hosts
    hosts = list_hosts()
    all_results = []
    
    for host_id in hosts:
        summary = aggregate_yearly_for_host(target_year, max_month, host_id=host_id)
        if summary:
            if host_id and host_id != "all" and host_id != "_legacy":
                key = f"aggregated/host={host_id}/year={target_year}/speed_test_summary.json"
            else:
                key = f"aggregated/year={target_year}/speed_test_summary.json"
            
            s3.put_object(
                Bucket=S3_BUCKET_YEARLY,
                Key=key,
                Body=json.dumps(summary, indent=2),
                ContentType="application/json",
            )
            log.info(f"Yearly summary uploaded to s3://{S3_BUCKET_YEARLY}/{key}")
            all_results.append({"host_id": host_id, "months": summary["months_aggregated"], "s3_key": key})
    
    # Global summary
    global_summary = aggregate_yearly_for_host(target_year, max_month, host_id=None)
    if global_summary:
        global_key = f"aggregated/year={target_year}/speed_test_summary.json"
        s3.put_object(
            Bucket=S3_BUCKET_YEARLY,
            Key=global_key,
            Body=json.dumps(global_summary, indent=2),
            ContentType="application/json",
        )
        log.info(f"Global year-to-date summary uploaded to s3://{S3_BUCKET_YEARLY}/{global_key}")
    
    emit_success_event("yearly")
    return {"year": target_year, "hosts_aggregated": len(hosts), "host_results": all_results, "global_summary": global_summary}

# --- Lambda handler -----------------------------------------------------------
# ---------------------------------------------------------------------------
# Extended Lambda Handler (supporting "mode": hourly|daily|weekly|monthly|yearly)
# ---------------------------------------------------------------------------
def lambda_handler(event, context):
    # Support both EventBridge events (event.mode) and Lambda Function URL (queryStringParameters.mode)
    mode = None
    custom_date = None
    
    if isinstance(event, dict):
        # Check for Lambda Function URL query parameters first
        query_params = event.get("queryStringParameters") or {}
        mode = query_params.get("mode") or event.get("mode")
        custom_date = query_params.get("date") or event.get("date")
    
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

