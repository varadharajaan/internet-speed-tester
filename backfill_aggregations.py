#!/usr/bin/env python3
"""
Backfill Historical Aggregations
---------------------------------
Creates hourly, weekly, monthly, and yearly aggregations from historical data.

Usage:
    python backfill_aggregations.py --all                    # Backfill all aggregation types
    python backfill_aggregations.py --hourly                 # Backfill hourly only
    python backfill_aggregations.py --weekly                 # Backfill weekly only
    python backfill_aggregations.py --monthly                # Backfill monthly only
    python backfill_aggregations.py --yearly                 # Backfill yearly only
    python backfill_aggregations.py --hourly --weekly        # Multiple types
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

def load_all_minute_data():
    """Load all minute-level data from S3."""
    print("📥 Loading all minute-level data from S3...")
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
    print("📥 Loading all daily summaries from S3...")
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
                print(f"⚠️  Skip {key}: {e}")
    
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

def backfill_weekly(daily_summaries, force=False):
    """Create weekly aggregations for all weeks that have data."""
    print("\n📅 Backfilling weekly aggregations...")
    
    if not daily_summaries:
        print("❌ No daily summaries to process")
        return
    
    dates = sorted(daily_summaries.keys())
    min_date = dates[0]
    max_date = dates[-1]
    
    # Get current week
    today = datetime.datetime.now(TIMEZONE).date()
    current_week_monday, _ = get_week_bounds(today)
    
    # Get the Monday of the first week
    first_monday, _ = get_week_bounds(min_date)
    last_monday, _ = get_week_bounds(max_date)
    
    current_monday = first_monday
    weeks_created = 0
    weeks_skipped = 0
    
    while current_monday <= last_monday:
        _, sunday = get_week_bounds(current_monday)
        
        # Skip current incomplete week unless --force is used
        if not force and current_monday >= current_week_monday:
            weeks_skipped += 1
            current_monday += datetime.timedelta(days=7)
            continue
        
        # Aggregate this week
        week_summary = aggregate_week(daily_summaries, current_monday, sunday)
        
        if week_summary:
            # Upload to S3
            week_label = f"{current_monday.strftime('%YW%W')}"
            key = f"aggregated/year={current_monday.year}/week={week_label}/speed_test_summary.json"
            
            s3.put_object(
                Bucket=S3_BUCKET_WEEKLY,
                Key=key,
                Body=json.dumps(week_summary, indent=2),
                ContentType="application/json",
            )
            
            weeks_created += 1
            print(f"SUCCESS: {current_monday} to {sunday} ({week_summary['days']} days) -> s3://{S3_BUCKET_WEEKLY}/{key}")
        
        current_monday += datetime.timedelta(days=7)
    
    if weeks_skipped > 0:
        print(f"⏭️  Skipped {weeks_skipped} incomplete week(s). Use --force to include them.")
    print(f"\n🎉 Created {weeks_created} weekly aggregations")

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

def backfill_hourly(minute_records, force=False):
    """Create hourly aggregations for all hours that have data."""
    print("\n📅 Backfilling hourly aggregations...")
    
    if not minute_records:
        print("❌ No minute records to process")
        return
    
    # Get current time
    now = datetime.datetime.now(TIMEZONE)
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    
    # Group by hour
    hours = set()
    for record in minute_records:
        hour = record["timestamp"].replace(minute=0, second=0, microsecond=0)
        hours.add(hour)
    
    hours = sorted(hours)
    hours_created = 0
    hours_skipped = 0
    
    for hour in hours:
        # Skip current incomplete hour unless --force is used
        if not force and hour >= current_hour:
            hours_skipped += 1
            continue
        
        hour_summary = aggregate_hour(minute_records, hour)
        
        if hour_summary:
            year = hour.year
            month = hour.strftime("%Y%m")
            day = hour.strftime("%Y%m%d")
            hour_str = hour.strftime("%H")
            
            key = f"aggregated/year={year}/month={month}/day={day}/hour={hour_str}/speed_test_summary.json"
            
            s3.put_object(
                Bucket=S3_BUCKET_HOURLY,
                Key=key,
                Body=json.dumps(hour_summary, indent=2),
                ContentType="application/json",
            )
            
            hours_created += 1
            if hours_created % 20 == 0:  # Progress indicator
                print(f"   ... {hours_created} hours processed")
    
    if hours_skipped > 0:
        print(f"⏭️  Skipped {hours_skipped} incomplete hour(s). Use --force to include them.")
    print(f"\n🎉 Created {hours_created} hourly aggregations")

def backfill_monthly(daily_summaries, force=False):
    """Create monthly aggregations for all months that have data."""
    print("\n📅 Backfilling monthly aggregations...")
    
    if not daily_summaries:
        print("❌ No daily summaries to process")
        return
    
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
    months_created = 0
    months_skipped = 0
    
    for year, month in months:
        # Skip current incomplete month unless --force is used
        if not force and year == current_year and month == current_month:
            months_skipped += 1
            continue
        
        month_summary = aggregate_month(daily_summaries, year, month)
        
        if month_summary:
            month_tag = month_summary["month"]
            key = f"aggregated/year={year}/month={month_tag}/speed_test_summary.json"
            
            s3.put_object(
                Bucket=S3_BUCKET_MONTHLY,
                Key=key,
                Body=json.dumps(month_summary, indent=2),
                ContentType="application/json",
            )
            
            months_created += 1
            print(f"SUCCESS: {year}-{month:02d} ({month_summary['days']} days) -> s3://{S3_BUCKET_MONTHLY}/{key}")
    
    if months_skipped > 0:
        print(f"Skipped {months_skipped} incomplete month(s). Use --force to include them.")
    print(f"\nCreated {months_created} monthly aggregations")

def backfill_yearly(monthly_summaries, force=False):
    """Create yearly aggregations from monthly data."""
    print("\nBackfilling yearly aggregations...")
    
    if not monthly_summaries:
        print("❌ No monthly summaries to process")
        return
    
    # Get current year
    today = datetime.datetime.now(TIMEZONE).date()
    current_year = today.year
    
    # Group by year
    years = {}
    for (year, month), data in monthly_summaries.items():
        if year not in years:
            years[year] = []
        years[year].append(data)
    
    years_created = 0
    years_skipped = 0
    
    for year, year_data in sorted(years.items()):
        if not year_data:
            continue
        
        # Skip current incomplete year unless --force is used
        if not force and year == current_year:
            years_skipped += 1
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
        
        key = f"aggregated/year={year}/speed_test_summary.json"
        
        s3.put_object(
            Bucket=S3_BUCKET_YEARLY,
            Key=key,
            Body=json.dumps(year_summary, indent=2),
            ContentType="application/json",
        )
        
        years_created += 1
        print(f"SUCCESS: {year} ({year_summary['months_aggregated']} months) -> s3://{S3_BUCKET_YEARLY}/{key}")
    
    if years_skipped > 0:
        print(f"⏭️  Skipped {years_skipped} incomplete year(s). Use --force to include them.")
    print(f"\n🎉 Created {years_created} yearly aggregations")

def main():
    parser = argparse.ArgumentParser(
        description="Backfill historical aggregations from existing data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python backfill_aggregations.py --all
  python backfill_aggregations.py --hourly --weekly
  python backfill_aggregations.py --monthly --yearly
  python backfill_aggregations.py --all --force  # Include incomplete periods
        """
    )
    
    parser.add_argument("--all", action="store_true", help="Backfill all aggregation types")
    parser.add_argument("--hourly", action="store_true", help="Backfill hourly aggregations from minute data")
    parser.add_argument("--weekly", action="store_true", help="Backfill weekly aggregations from daily data")
    parser.add_argument("--monthly", action="store_true", help="Backfill monthly aggregations from daily data")
    parser.add_argument("--yearly", action="store_true", help="Backfill yearly aggregations from monthly data")
    parser.add_argument("--force", action="store_true", help="Include incomplete periods (current hour/week/month/year)")
    
    args = parser.parse_args()
    
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
    print("=" * 80)
    
    minute_records = None
    daily_summaries = None
    monthly_summaries = None
    
    # Hourly aggregations
    if args.hourly:
        print("\n[HOURLY] Backfilling hourly aggregations...")
        minute_records = load_all_minute_data()
        if minute_records:
            backfill_hourly(minute_records, force=args.force)
        else:
            print("⚠️  No minute data found, skipping hourly aggregations")
    
    # Weekly aggregations
    if args.weekly:
        print("\n[WEEKLY] Backfilling weekly aggregations...")
        if daily_summaries is None:
            daily_summaries = load_all_daily_summaries()
        if daily_summaries:
            backfill_weekly(daily_summaries, force=args.force)
        else:
            print("⚠️  No daily summaries found, skipping weekly aggregations")
    
    # Monthly aggregations
    if args.monthly:
        print("\n[MONTHLY] Backfilling monthly aggregations...")
        if daily_summaries is None:
            daily_summaries = load_all_daily_summaries()
        
        if daily_summaries:
            # Get current month info
            today = datetime.datetime.now(TIMEZONE).date()
            current_year = today.year
            current_month = today.month
            
            dates = sorted(daily_summaries.keys())
            months = set()
            for date in dates:
                months.add((date.year, date.month))
            
            monthly_summaries = {}
            for year, month in sorted(months):
                # Skip current incomplete month unless --force is used
                if not args.force and year == current_year and month == current_month:
                    continue
                
                month_summary = aggregate_month(daily_summaries, year, month)
                if month_summary:
                    monthly_summaries[(year, month)] = month_summary
                    month_tag = month_summary["month"]
                    key = f"aggregated/year={year}/month={month_tag}/speed_test_summary.json"
                    
                    s3.put_object(
                        Bucket=S3_BUCKET_MONTHLY,
                        Key=key,
                        Body=json.dumps(month_summary, indent=2),
                        ContentType="application/json",
                    )
                    print(f"SUCCESS: {year}-{month:02d} ({month_summary['days']} days) -> s3://{S3_BUCKET_MONTHLY}/{key}")
            
            print(f"\nCreated {len(monthly_summaries)} monthly aggregations")
        else:
            print("WARNING: No daily summaries found, skipping monthly aggregations")
    
    # Yearly aggregations
    if args.yearly:
        print("\n[YEARLY] Backfilling yearly aggregations...")
        
        # Load monthly summaries if not already loaded
        if monthly_summaries is None:
            print("📥 Loading existing monthly summaries from S3...")
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
                        print(f"⚠️  Skip {key}: {e}")
            
            print(f"Loaded {len(monthly_summaries)} monthly summaries")
        
        if monthly_summaries:
            backfill_yearly(monthly_summaries, force=args.force)
        else:
            print("⚠️  No monthly summaries found, skipping yearly aggregations")
    
    print("\n" + "=" * 80)
    print("  BACKFILL COMPLETE!")
    print("=" * 80)

if __name__ == "__main__":
    main()
