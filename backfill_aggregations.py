#!/usr/bin/env python3
"""
Backfill Historical Aggregations
---------------------------------
Creates hourly, weekly, monthly, and yearly aggregations from historical data.

EXECUTION ORDER (handled automatically by --all):
  1. Hourly  - Raw minute data → Hourly summaries (independent)
  2. Weekly  - Daily summaries → Weekly rollups (requires daily to exist)
  3. Monthly - Daily summaries → Monthly rollups (requires daily to exist)
  4. Yearly  - Monthly summaries → Yearly rollups (requires monthly first)

NOTE: Daily aggregations are created by the Lambda function, not this script.
      This script assumes daily summaries already exist in the main bucket.

Data Flow:
  Raw 15-min data ──┬──> Hourly (vd-speed-test-hourly-prod)
                    │
                    └──> Daily (vd-speed-test/aggregated/) [via Lambda]
                              │
                              ├──> Weekly (vd-speed-test-weekly-prod)
                              │
                              └──> Monthly (vd-speed-test-monthly-prod)
                                        │
                                        └──> Yearly (vd-speed-test-yearly-prod)

Usage:
    python backfill_aggregations.py --all                    # Backfill all aggregation types
    python backfill_aggregations.py --hourly                 # Backfill hourly only
    python backfill_aggregations.py --weekly                 # Backfill weekly only
    python backfill_aggregations.py --monthly                # Backfill monthly only
    python backfill_aggregations.py --yearly                 # Backfill yearly only
    python backfill_aggregations.py --hourly --weekly        # Multiple types
    python backfill_aggregations.py --all --force            # Include incomplete periods
    python backfill_aggregations.py --weekly --last 2        # Backfill only last 2 weeks
    python backfill_aggregations.py --hourly --last 24       # Backfill only last 24 hours
    python backfill_aggregations.py --all --skip-existing    # Skip if already exists in S3
"""
import json, datetime, boto3, os, argparse
from collections import Counter
from statistics import mean
from calendar import monthrange
import pytz

# Load config
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

S3_BUCKET = config.get("s3_bucket", "vd-speed-test")
S3_BUCKET_HOURLY = config.get("s3_bucket_hourly", "vd-speed-test-hourly-prod")
S3_BUCKET_WEEKLY = config.get("s3_bucket_weekly", "vd-speed-test-weekly-prod")
S3_BUCKET_MONTHLY = config.get("s3_bucket_monthly", "vd-speed-test-monthly-prod")
S3_BUCKET_YEARLY = config.get("s3_bucket_yearly", "vd-speed-test-yearly-prod")
AWS_REGION = config.get("aws_region", "ap-south-1")
TIMEZONE = pytz.timezone(config.get("timezone", "Asia/Kolkata"))

s3 = boto3.client("s3", region_name=AWS_REGION)

# Manifest file for tracking backfill output
BACKFILL_MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "backfill_manifest.json")

# Global skip-existing flag (set by args)
SKIP_EXISTING = False


def s3_key_exists(bucket: str, key: str) -> bool:
    """Check if an S3 key already exists."""
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except s3.exceptions.ClientError:
        return False
    except Exception:
        return False


def load_all_minute_data():
    """Load all minute-level data from S3."""
    print("Loading all minute-level data from S3...")
    paginator = s3.get_paginator("list_objects_v2")
    minute_records = []
    
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix="year="):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith(".json") or "aggregated" in key:
                continue
            
            try:
                data = json.loads(s3.get_object(Bucket=S3_BUCKET, Key=key)["Body"].read())
                ts_str = data.get("timestamp_ist")
                if not ts_str:
                    continue
                ts = TIMEZONE.localize(datetime.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S IST"))
                
                minute_records.append({
                    "timestamp": ts,
                    "download_mbps": float(str(data.get("download_mbps", "0")).split()[0]),
                    "upload_mbps": float(str(data.get("upload_mbps", "0")).split()[0]),
                    "ping_ms": float(str(data.get("ping_ms", "0")).split()[0]) if data.get("ping_ms") else 0.0,
                    "connection_type": data.get("connection_type", "Unknown"),
                    "public_ip": data.get("public_ip", ""),
                    "server_name": data.get("server_name", ""),
                    "server_host": data.get("server_host", ""),
                })
            except Exception as e:
                print(f"WARNING: Skip {key}: {e}")
    
    print(f"Loaded {len(minute_records)} minute-level records")
    return minute_records

def load_all_daily_summaries():
    """Load all daily summaries from S3."""
    print("Loading all daily summaries from S3...")
    paginator = s3.get_paginator("list_objects_v2")
    summaries = {}
    
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix="aggregated/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith("speed_test_summary.json"):
                continue
            if "/day=" not in key:
                continue
            
            try:
                data = json.loads(s3.get_object(Bucket=S3_BUCKET, Key=key)["Body"].read())
                date_str = data.get("date_ist")
                if date_str:
                    date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                    summaries[date] = data
            except Exception as e:
                print(f"WARNING: Skip {key}: {e}")
    
    print(f"Loaded {len(summaries)} daily summaries")
    return summaries

def get_week_bounds(date):
    """Get Monday and Sunday for the week containing the given date."""
    monday = date - datetime.timedelta(days=date.weekday())
    sunday = monday + datetime.timedelta(days=6)
    return monday, sunday

def aggregate_week(daily_summaries, monday, sunday):
    """Aggregate daily summaries for a specific week."""
    week_data = []
    current = monday
    while current <= sunday:
        if current in daily_summaries:
            week_data.append(daily_summaries[current])
        current += datetime.timedelta(days=1)
    
    if not week_data:
        return None
    
    # Collect all unique connection types from the week
    all_connection_types = set()
    for ds in week_data:
        conn_types = ds.get("connection_types", [])
        if conn_types:
            all_connection_types.update(conn_types)
    unique_connection_types = sorted(list(all_connection_types)) if all_connection_types else []
    
    return {
        "week_start": str(monday),
        "week_end": str(sunday),
        "days": len(week_data),
        "avg_download": round(mean([x["overall"]["download_mbps"]["avg"] for x in week_data]), 2),
        "avg_upload": round(mean([x["overall"]["upload_mbps"]["avg"] for x in week_data]), 2),
        "avg_ping": round(mean([x["overall"]["ping_ms"]["avg"] for x in week_data]), 2),
        "connection_types": unique_connection_types,
    }

def aggregate_month(daily_summaries, year, month):
    """Aggregate daily summaries for a specific month."""
    first_day = datetime.date(year, month, 1)
    _, last_day_num = monthrange(year, month)
    last_day = datetime.date(year, month, last_day_num)
    
    month_data = []
    current = first_day
    while current <= last_day:
        if current in daily_summaries:
            month_data.append(daily_summaries[current])
        current += datetime.timedelta(days=1)
    
    if not month_data:
        return None
    
    # Collect all unique connection types from the month
    all_connection_types = set()
    for ds in month_data:
        conn_types = ds.get("connection_types", [])
        if conn_types:
            all_connection_types.update(conn_types)
    unique_connection_types = sorted(list(all_connection_types)) if all_connection_types else []
    
    month_tag = f"{year}{month:02d}"
    return {
        "month": month_tag,
        "days": len(month_data),
        "avg_download": round(mean([x["overall"]["download_mbps"]["avg"] for x in month_data]), 2),
        "avg_upload": round(mean([x["overall"]["upload_mbps"]["avg"] for x in month_data]), 2),
        "avg_ping": round(mean([x["overall"]["ping_ms"]["avg"] for x in month_data]), 2),
        "connection_types": unique_connection_types,
    }

def backfill_weekly(daily_summaries, force=False, last_n=None):
    """Create weekly aggregations for all weeks that have data.
    
    Args:
        daily_summaries: Dict of daily summaries keyed by date
        force: Include incomplete current week
        last_n: Only backfill last N weeks (None = all)
    """
    print(f"\nBackfilling weekly aggregations{' (last ' + str(last_n) + ')' if last_n else ''}...")
    created_files = []
    
    if not daily_summaries:
        print("ERROR: No daily summaries to process")
        return []
    
    dates = sorted(daily_summaries.keys())
    min_date = dates[0]
    max_date = dates[-1]
    
    # Get current week
    today = datetime.datetime.now(TIMEZONE).date()
    current_week_monday, _ = get_week_bounds(today)
    
    # Get the Monday of the first week
    first_monday, _ = get_week_bounds(min_date)
    last_monday, _ = get_week_bounds(max_date)
    
    # If --last is specified, limit to only last N weeks
    if last_n is not None:
        cutoff_monday = current_week_monday - datetime.timedelta(weeks=last_n)
        first_monday = max(first_monday, cutoff_monday)
    
    current_monday = first_monday
    weeks_created = 0
    weeks_skipped = 0
    weeks_existed = 0
    
    while current_monday <= last_monday:
        _, sunday = get_week_bounds(current_monday)
        
        # Skip current incomplete week unless --force is used
        if not force and current_monday >= current_week_monday:
            weeks_skipped += 1
            current_monday += datetime.timedelta(days=7)
            continue
        
        # Build key first to check if exists
        week_label = f"{current_monday.strftime('%YW%W')}"
        key = f"aggregated/year={current_monday.year}/week={week_label}/speed_test_summary.json"
        
        # Skip if already exists and --skip-existing is set
        if SKIP_EXISTING and s3_key_exists(S3_BUCKET_WEEKLY, key):
            weeks_existed += 1
            current_monday += datetime.timedelta(days=7)
            continue
        
        # Aggregate this week
        week_summary = aggregate_week(daily_summaries, current_monday, sunday)
        
        if week_summary:
            s3.put_object(
                Bucket=S3_BUCKET_WEEKLY,
                Key=key,
                Body=json.dumps(week_summary, indent=2),
                ContentType="application/json",
            )
            
            weeks_created += 1
            created_files.append({"bucket": S3_BUCKET_WEEKLY, "key": key, "type": "weekly"})
            print(f"SUCCESS: {current_monday} to {sunday} ({week_summary['days']} days) -> s3://{S3_BUCKET_WEEKLY}/{key}")
        
        current_monday += datetime.timedelta(days=7)
    
    if weeks_skipped > 0:
        print(f"Skipped {weeks_skipped} incomplete week(s). Use --force to include them.")
    if weeks_existed > 0:
        print(f"Skipped {weeks_existed} week(s) that already exist.")
    print(f"\nCreated {weeks_created} weekly aggregations")
    return created_files

def aggregate_hour(minute_records, target_hour):
    """Aggregate minute records for a specific hour."""
    hour_data = [r for r in minute_records if r["timestamp"].replace(minute=0, second=0, microsecond=0) == target_hour]
    
    if not hour_data:
        return None
    
    # Collect all unique connection types from the hour
    all_connection_types = set([r["connection_type"] for r in hour_data if r["connection_type"]])
    unique_connection_types = sorted(list(all_connection_types)) if all_connection_types else []
    
    all_public_ips = list(set([r["public_ip"] for r in hour_data if r["public_ip"]]))
    all_servers = [f"{r['server_name']} – {r['server_host']}" for r in hour_data if r["server_name"]]
    top_servers = [s for s, _ in Counter(all_servers).most_common(3)] if all_servers else []
    
    return {
        "hour_ist": target_hour.strftime("%Y-%m-%d %H:%M"),
        "records": len(hour_data),
        "completion_rate": round((len(hour_data) / 4) * 100, 1),  # Expected 4 records per hour
        "overall": {
            "download_mbps": {
                "avg": round(mean([r["download_mbps"] for r in hour_data]), 2),
                "min": round(min([r["download_mbps"] for r in hour_data]), 2),
                "max": round(max([r["download_mbps"] for r in hour_data]), 2),
            },
            "upload_mbps": {
                "avg": round(mean([r["upload_mbps"] for r in hour_data]), 2),
                "min": round(min([r["upload_mbps"] for r in hour_data]), 2),
                "max": round(max([r["upload_mbps"] for r in hour_data]), 2),
            },
            "ping_ms": {
                "avg": round(mean([r["ping_ms"] for r in hour_data]), 2),
                "min": round(min([r["ping_ms"] for r in hour_data]), 2),
                "max": round(max([r["ping_ms"] for r in hour_data]), 2),
            },
        },
        "connection_types": unique_connection_types,
        "public_ips": all_public_ips,
        "servers_top": top_servers,
    }

def backfill_hourly(minute_records, force=False, last_n=None):
    """Create hourly aggregations for all hours that have data.
    
    Args:
        minute_records: List of minute-level data records
        force: Include incomplete current hour
        last_n: Only backfill last N hours (None = all)
    """
    print(f"\nBackfilling hourly aggregations{' (last ' + str(last_n) + ')' if last_n else ''}...")
    created_files = []
    
    if not minute_records:
        print("ERROR: No minute records to process")
        return []
    
    # Get current time
    now = datetime.datetime.now(TIMEZONE)
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    
    # Group by hour
    hours = set()
    for record in minute_records:
        hour = record["timestamp"].replace(minute=0, second=0, microsecond=0)
        hours.add(hour)
    
    hours = sorted(hours)
    
    # If --last is specified, limit to only last N hours
    if last_n is not None:
        cutoff_hour = current_hour - datetime.timedelta(hours=last_n)
        hours = [h for h in hours if h >= cutoff_hour]
    
    hours_created = 0
    hours_skipped = 0
    hours_existed = 0
    
    for hour in hours:
        # Skip current incomplete hour unless --force is used
        if not force and hour >= current_hour:
            hours_skipped += 1
            continue
        
        year = hour.year
        month = hour.strftime("%Y%m")
        day = hour.strftime("%Y%m%d")
        hour_str = hour.strftime("%H")
        key = f"aggregated/year={year}/month={month}/day={day}/hour={hour_str}/speed_test_summary.json"
        
        # Skip if already exists and --skip-existing is set
        if SKIP_EXISTING and s3_key_exists(S3_BUCKET_HOURLY, key):
            hours_existed += 1
            continue
        
        hour_summary = aggregate_hour(minute_records, hour)
        
        if hour_summary:
            s3.put_object(
                Bucket=S3_BUCKET_HOURLY,
                Key=key,
                Body=json.dumps(hour_summary, indent=2),
                ContentType="application/json",
            )
            
            hours_created += 1
            created_files.append({"bucket": S3_BUCKET_HOURLY, "key": key, "type": "hourly"})
            if hours_created % 20 == 0:  # Progress indicator
                print(f"   ... {hours_created} hours processed")
    
    if hours_skipped > 0:
        print(f"Skipped {hours_skipped} incomplete hour(s). Use --force to include them.")
    if hours_existed > 0:
        print(f"Skipped {hours_existed} hour(s) that already exist.")
    print(f"\nCreated {hours_created} hourly aggregations")
    return created_files

def backfill_monthly(daily_summaries, force=False, last_n=None):
    """Create monthly aggregations for all months that have data.
    
    Args:
        daily_summaries: Dict of daily summaries keyed by date
        force: Include incomplete current month
        last_n: Only backfill last N months (None = all)
    """
    print(f"\nBackfilling monthly aggregations{' (last ' + str(last_n) + ')' if last_n else ''}...")
    created_files = []
    
    if not daily_summaries:
        print("ERROR: No daily summaries to process")
        return []
    
    dates = sorted(daily_summaries.keys())
    
    # Get current month
    today = datetime.datetime.now(TIMEZONE).date()
    current_year = today.year
    current_month = today.month
    
    # Get all unique year-month combinations
    months = set()
    for date in dates:
        months.add((date.year, date.month))
    
    months = sorted(months)
    
    # If --last is specified, limit to only last N months
    if last_n is not None:
        cutoff_year = current_year
        cutoff_month = current_month - last_n
        while cutoff_month <= 0:
            cutoff_month += 12
            cutoff_year -= 1
        months = [(y, m) for y, m in months if (y * 100 + m) >= (cutoff_year * 100 + cutoff_month)]
    
    months_created = 0
    months_skipped = 0
    months_existed = 0
    
    for year, month in months:
        # Skip current incomplete month unless --force is used
        if not force and year == current_year and month == current_month:
            months_skipped += 1
            continue
        
        month_tag = f"{year}{month:02d}"
        key = f"aggregated/year={year}/month={month_tag}/speed_test_summary.json"
        
        # Skip if already exists and --skip-existing is set
        if SKIP_EXISTING and s3_key_exists(S3_BUCKET_MONTHLY, key):
            months_existed += 1
            continue
        
        month_summary = aggregate_month(daily_summaries, year, month)
        
        if month_summary:
            s3.put_object(
                Bucket=S3_BUCKET_MONTHLY,
                Key=key,
                Body=json.dumps(month_summary, indent=2),
                ContentType="application/json",
            )
            
            months_created += 1
            created_files.append({"bucket": S3_BUCKET_MONTHLY, "key": key, "type": "monthly"})
            print(f"SUCCESS: {year}-{month:02d} ({month_summary['days']} days) -> s3://{S3_BUCKET_MONTHLY}/{key}")
    
    if months_skipped > 0:
        print(f"Skipped {months_skipped} incomplete month(s). Use --force to include them.")
    if months_existed > 0:
        print(f"Skipped {months_existed} month(s) that already exist.")
    print(f"\nCreated {months_created} monthly aggregations")
    return created_files


def backfill_yearly(monthly_summaries, force=False, last_n=None):
    """Create yearly aggregations from monthly data.
    
    Args:
        monthly_summaries: Dict of monthly summaries keyed by (year, month)
        force: Include incomplete current year
        last_n: Only backfill last N years (None = all)
    """
    print(f"\nBackfilling yearly aggregations{' (last ' + str(last_n) + ')' if last_n else ''}...")
    created_files = []
    
    if not monthly_summaries:
        print("ERROR: No monthly summaries to process")
        return []
    
    # Get current year
    today = datetime.datetime.now(TIMEZONE).date()
    current_year = today.year
    
    # Group by year
    years = {}
    for (year, month), data in monthly_summaries.items():
        if year not in years:
            years[year] = []
        years[year].append(data)
    
    # If --last is specified, limit to only last N years
    if last_n is not None:
        cutoff_year = current_year - last_n + 1
        years = {y: d for y, d in years.items() if y >= cutoff_year}
    
    years_created = 0
    years_skipped = 0
    years_existed = 0
    
    for year, year_data in sorted(years.items()):
        if not year_data:
            continue
        
        # Skip current incomplete year unless --force is used
        if not force and year == current_year:
            years_skipped += 1
            continue
        
        key = f"aggregated/year={year}/speed_test_summary.json"
        
        # Skip if already exists and --skip-existing is set
        if SKIP_EXISTING and s3_key_exists(S3_BUCKET_YEARLY, key):
            years_existed += 1
            continue
        
        all_connection_types = []
        for ms in year_data:
            all_connection_types.extend(ms.get("connection_types", []))
        top_connection_types = [ct for ct, _ in Counter(all_connection_types).most_common(3)] if all_connection_types else []
        
        year_summary = {
            "year": year,
            "months_aggregated": len(year_data),
            "avg_download": round(mean([x["avg_download"] for x in year_data]), 2),
            "avg_upload": round(mean([x["avg_upload"] for x in year_data]), 2),
            "avg_ping": round(mean([x["avg_ping"] for x in year_data]), 2),
            "connection_types": top_connection_types,
        }
        
        s3.put_object(
            Bucket=S3_BUCKET_YEARLY,
            Key=key,
            Body=json.dumps(year_summary, indent=2),
            ContentType="application/json",
        )
        
        years_created += 1
        created_files.append({"bucket": S3_BUCKET_YEARLY, "key": key, "type": "yearly"})
        print(f"SUCCESS: {year} ({year_summary['months_aggregated']} months) -> s3://{S3_BUCKET_YEARLY}/{key}")
    
    if years_skipped > 0:
        print(f"Skipped {years_skipped} incomplete year(s). Use --force to include them.")
    if years_existed > 0:
        print(f"Skipped {years_existed} year(s) that already exist.")
    print(f"\nCreated {years_created} yearly aggregations")
    return created_files

def main():
    global SKIP_EXISTING
    
    parser = argparse.ArgumentParser(
        description="Backfill historical aggregations from existing data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python backfill_aggregations.py --all
  python backfill_aggregations.py --hourly --weekly
  python backfill_aggregations.py --monthly --yearly
  python backfill_aggregations.py --all --force           # Include incomplete periods
  python backfill_aggregations.py --weekly --last 2       # Backfill only last 2 weeks
  python backfill_aggregations.py --hourly --last 24      # Backfill only last 24 hours
  python backfill_aggregations.py --monthly --last 3      # Backfill only last 3 months
  python backfill_aggregations.py --all --skip-existing   # Skip if already exists in S3
        """
    )
    
    parser.add_argument("--all", action="store_true", help="Backfill all aggregation types")
    parser.add_argument("--hourly", action="store_true", help="Backfill hourly aggregations from minute data")
    parser.add_argument("--weekly", action="store_true", help="Backfill weekly aggregations from daily data")
    parser.add_argument("--monthly", action="store_true", help="Backfill monthly aggregations from daily data")
    parser.add_argument("--yearly", action="store_true", help="Backfill yearly aggregations from monthly data")
    parser.add_argument("--force", action="store_true", help="Include incomplete periods (current hour/week/month/year)")
    parser.add_argument("--last", type=int, metavar="N", help="Only backfill last N periods (e.g., --last 2 for last 2 weeks/months)")
    parser.add_argument("--skip-existing", action="store_true", help="Skip periods that already have data in S3")
    
    args = parser.parse_args()
    
    # Set global skip-existing flag
    SKIP_EXISTING = args.skip_existing
    
    # If no flags specified or --all, do everything
    if args.all or not (args.hourly or args.weekly or args.monthly or args.yearly):
        args.hourly = args.weekly = args.monthly = args.yearly = True
    
    print("=" * 80)
    print("  BACKFILL HISTORICAL AGGREGATIONS")
    print("=" * 80)
    print(f"  Daily bucket:   {S3_BUCKET}")
    if args.hourly:
        print(f"  Hourly bucket:  {S3_BUCKET_HOURLY}")
    if args.weekly:
        print(f"  Weekly bucket:  {S3_BUCKET_WEEKLY}")
    if args.monthly:
        print(f"  Monthly bucket: {S3_BUCKET_MONTHLY}")
    if args.yearly:
        print(f"  Yearly bucket:  {S3_BUCKET_YEARLY}")
    if args.last:
        print(f"  Limiting to:    Last {args.last} period(s)")
    if args.skip_existing:
        print(f"  Skip existing:  Yes (will not overwrite)")
    print("=" * 80)
    
    minute_records = None
    daily_summaries = None
    monthly_summaries = None
    all_created_files = []
    
    # Hourly aggregations
    if args.hourly:
        print("\n[HOURLY] Backfilling hourly aggregations...")
        minute_records = load_all_minute_data()
        if minute_records:
            hourly_files = backfill_hourly(minute_records, force=args.force, last_n=args.last)
            all_created_files.extend(hourly_files if hourly_files else [])
        else:
            print("WARNING: No minute data found, skipping hourly aggregations")
    
    # Weekly aggregations
    if args.weekly:
        print("\n[WEEKLY] Backfilling weekly aggregations...")
        if daily_summaries is None:
            daily_summaries = load_all_daily_summaries()
        if daily_summaries:
            weekly_files = backfill_weekly(daily_summaries, force=args.force, last_n=args.last)
            all_created_files.extend(weekly_files if weekly_files else [])
        else:
            print("WARNING: No daily summaries found, skipping weekly aggregations")
    
    # Monthly aggregations
    if args.monthly:
        print("\n[MONTHLY] Backfilling monthly aggregations...")
        if daily_summaries is None:
            daily_summaries = load_all_daily_summaries()
        
        if daily_summaries:
            monthly_files = backfill_monthly(daily_summaries, force=args.force, last_n=args.last)
            all_created_files.extend(monthly_files if monthly_files else [])
            
            # Build monthly_summaries dict for yearly (if needed later)
            if args.yearly:
                today = datetime.datetime.now(TIMEZONE).date()
                current_year = today.year
                current_month = today.month
                dates = sorted(daily_summaries.keys())
                months = set()
                for date in dates:
                    months.add((date.year, date.month))
                monthly_summaries = {}
                for year, month in sorted(months):
                    if not args.force and year == current_year and month == current_month:
                        continue
                    month_summary = aggregate_month(daily_summaries, year, month)
                    if month_summary:
                        monthly_summaries[(year, month)] = month_summary
        else:
            print("WARNING: No daily summaries found, skipping monthly aggregations")
    
    # Yearly aggregations
    if args.yearly:
        print("\n[YEARLY] Backfilling yearly aggregations...")
        
        # Load monthly summaries if not already loaded
        if monthly_summaries is None:
            print("Loading existing monthly summaries from S3...")
            monthly_summaries = {}
            paginator = s3.get_paginator("list_objects_v2")
            
            for page in paginator.paginate(Bucket=S3_BUCKET_MONTHLY, Prefix="aggregated/"):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    if not key.endswith("speed_test_summary.json"):
                        continue
                    
                    try:
                        data = json.loads(s3.get_object(Bucket=S3_BUCKET_MONTHLY, Key=key)["Body"].read())
                        month_str = data.get("month")
                        if month_str and len(month_str) == 6:
                            year = int(month_str[:4])
                            month = int(month_str[4:6])
                            monthly_summaries[(year, month)] = data
                    except Exception as e:
                        print(f"WARNING: Skip {key}: {e}")
            
            print(f"Loaded {len(monthly_summaries)} monthly summaries")
        
        if monthly_summaries:
            yearly_files = backfill_yearly(monthly_summaries, force=args.force, last_n=args.last)
            all_created_files.extend(yearly_files if yearly_files else [])
        else:
            print("WARNING: No monthly summaries found, skipping yearly aggregations")
    
    # Save manifest of created files
    manifest = {
        "timestamp": datetime.datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "files_created": len(all_created_files),
        "files": all_created_files,
    }
    with open(BACKFILL_MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    
    print("\n" + "=" * 80)
    print(f"  BACKFILL COMPLETE! Created {len(all_created_files)} files.")
    print(f"  Manifest saved to: {BACKFILL_MANIFEST_PATH}")
    print("=" * 80)

if __name__ == "__main__":
    main()
