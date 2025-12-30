#!/usr/bin/env python3
"""
Cleanup Aggregation Data
------------------------
Deletes aggregation files from S3 buckets for specific time periods.

Usage:
    python cleanup_aggregations.py --hourly --last 24      # Delete last 24 hours
    python cleanup_aggregations.py --weekly --last 2       # Delete last 2 weeks
    python cleanup_aggregations.py --monthly --last 3      # Delete last 3 months
    python cleanup_aggregations.py --yearly --last 1       # Delete last 1 year
    python cleanup_aggregations.py --all --last 2          # Delete last 2 periods from all levels
    python cleanup_aggregations.py --weekly --all-data     # Delete ALL weekly data
    python cleanup_aggregations.py --dry-run --weekly --last 2  # Preview without deleting
"""
import json
import datetime
import boto3
import os
import argparse
import sys
import pytz

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load config from parent directory
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
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


def list_all_keys(bucket: str, prefix: str = "aggregated/") -> list:
    """List all keys in a bucket with given prefix."""
    paginator = s3.get_paginator("list_objects_v2")
    keys = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def delete_keys(bucket: str, keys: list, dry_run: bool = False) -> int:
    """Delete keys from bucket. Returns count of deleted keys."""
    if not keys:
        return 0
    
    if dry_run:
        for key in keys:
            print(f"  [DRY-RUN] Would delete: s3://{bucket}/{key}")
        return len(keys)
    
    # Delete in batches of 1000 (S3 limit)
    deleted = 0
    for i in range(0, len(keys), 1000):
        batch = keys[i:i+1000]
        delete_objects = [{"Key": k} for k in batch]
        s3.delete_objects(Bucket=bucket, Delete={"Objects": delete_objects})
        deleted += len(batch)
    
    return deleted


def cleanup_hourly(last_n: int, dry_run: bool = False, all_data: bool = False) -> int:
    """Delete hourly aggregations for the last N hours."""
    print(f"\n[HOURLY] Cleaning up {'ALL' if all_data else f'last {last_n}'} hourly aggregations...")
    
    all_keys = list_all_keys(S3_BUCKET_HOURLY)
    if not all_keys:
        print("  No hourly aggregations found.")
        return 0
    
    if all_data:
        keys_to_delete = all_keys
    else:
        # Calculate cutoff
        now = datetime.datetime.now(TIMEZONE)
        cutoff = now - datetime.timedelta(hours=last_n)
        
        keys_to_delete = []
        for key in all_keys:
            # Parse hour from key: aggregated/.../day=20251229/hour=14/...
            try:
                parts = key.split("/")
                day_part = next((p for p in parts if p.startswith("day=")), None)
                hour_part = next((p for p in parts if p.startswith("hour=")), None)
                if day_part and hour_part:
                    day_str = day_part[4:]  # 20251229
                    hour_str = hour_part[5:]  # 14
                    dt = TIMEZONE.localize(datetime.datetime.strptime(f"{day_str}{hour_str}", "%Y%m%d%H"))
                    if dt >= cutoff:
                        keys_to_delete.append(key)
            except:
                continue
    
    if not keys_to_delete:
        print("  No matching hourly aggregations found.")
        return 0
    
    print(f"  Found {len(keys_to_delete)} files to delete.")
    deleted = delete_keys(S3_BUCKET_HOURLY, keys_to_delete, dry_run)
    print(f"  {'Would delete' if dry_run else 'Deleted'}: {deleted} files")
    return deleted


def cleanup_weekly(last_n: int, dry_run: bool = False, all_data: bool = False) -> int:
    """Delete weekly aggregations for the last N weeks."""
    print(f"\n[WEEKLY] Cleaning up {'ALL' if all_data else f'last {last_n}'} weekly aggregations...")
    
    all_keys = list_all_keys(S3_BUCKET_WEEKLY)
    if not all_keys:
        print("  No weekly aggregations found.")
        return 0
    
    if all_data:
        keys_to_delete = all_keys
    else:
        # Calculate cutoff week
        today = datetime.datetime.now(TIMEZONE).date()
        cutoff_monday = today - datetime.timedelta(days=today.weekday()) - datetime.timedelta(weeks=last_n-1)
        
        keys_to_delete = []
        for key in all_keys:
            # Parse week from key: aggregated/year=2025/week=2025W48/...
            try:
                parts = key.split("/")
                week_part = next((p for p in parts if p.startswith("week=")), None)
                if week_part:
                    week_str = week_part[5:]  # 2025W48
                    year = int(week_str[:4])
                    week_num = int(week_str[5:])
                    # Get Monday of that week
                    jan1 = datetime.date(year, 1, 1)
                    week_monday = jan1 + datetime.timedelta(days=-jan1.weekday(), weeks=week_num)
                    if week_monday >= cutoff_monday:
                        keys_to_delete.append(key)
            except:
                continue
    
    if not keys_to_delete:
        print("  No matching weekly aggregations found.")
        return 0
    
    print(f"  Found {len(keys_to_delete)} files to delete.")
    deleted = delete_keys(S3_BUCKET_WEEKLY, keys_to_delete, dry_run)
    print(f"  {'Would delete' if dry_run else 'Deleted'}: {deleted} files")
    return deleted


def cleanup_monthly(last_n: int, dry_run: bool = False, all_data: bool = False) -> int:
    """Delete monthly aggregations for the last N months."""
    print(f"\n[MONTHLY] Cleaning up {'ALL' if all_data else f'last {last_n}'} monthly aggregations...")
    
    all_keys = list_all_keys(S3_BUCKET_MONTHLY)
    if not all_keys:
        print("  No monthly aggregations found.")
        return 0
    
    if all_data:
        keys_to_delete = all_keys
    else:
        # Calculate cutoff month
        today = datetime.datetime.now(TIMEZONE).date()
        cutoff_year = today.year
        cutoff_month = today.month - last_n + 1
        while cutoff_month <= 0:
            cutoff_month += 12
            cutoff_year -= 1
        cutoff = cutoff_year * 100 + cutoff_month  # YYYYMM format
        
        keys_to_delete = []
        for key in all_keys:
            # Parse month from key: aggregated/year=2025/month=202511/...
            try:
                parts = key.split("/")
                month_part = next((p for p in parts if p.startswith("month=") and len(p) == 12), None)
                if month_part:
                    month_str = month_part[6:]  # 202511
                    month_val = int(month_str)
                    if month_val >= cutoff:
                        keys_to_delete.append(key)
            except:
                continue
    
    if not keys_to_delete:
        print("  No matching monthly aggregations found.")
        return 0
    
    print(f"  Found {len(keys_to_delete)} files to delete.")
    deleted = delete_keys(S3_BUCKET_MONTHLY, keys_to_delete, dry_run)
    print(f"  {'Would delete' if dry_run else 'Deleted'}: {deleted} files")
    return deleted


def cleanup_yearly(last_n: int, dry_run: bool = False, all_data: bool = False) -> int:
    """Delete yearly aggregations for the last N years."""
    print(f"\n[YEARLY] Cleaning up {'ALL' if all_data else f'last {last_n}'} yearly aggregations...")
    
    all_keys = list_all_keys(S3_BUCKET_YEARLY)
    if not all_keys:
        print("  No yearly aggregations found.")
        return 0
    
    if all_data:
        keys_to_delete = all_keys
    else:
        # Calculate cutoff year
        current_year = datetime.datetime.now(TIMEZONE).year
        cutoff_year = current_year - last_n + 1
        
        keys_to_delete = []
        for key in all_keys:
            # Parse year from key: aggregated/year=2025/...
            try:
                parts = key.split("/")
                year_part = next((p for p in parts if p.startswith("year=") and len(p) == 9), None)
                if year_part:
                    year = int(year_part[5:])
                    if year >= cutoff_year:
                        keys_to_delete.append(key)
            except:
                continue
    
    if not keys_to_delete:
        print("  No matching yearly aggregations found.")
        return 0
    
    print(f"  Found {len(keys_to_delete)} files to delete.")
    deleted = delete_keys(S3_BUCKET_YEARLY, keys_to_delete, dry_run)
    print(f"  {'Would delete' if dry_run else 'Deleted'}: {deleted} files")
    return deleted


def main():
    parser = argparse.ArgumentParser(
        description="Cleanup aggregation data from S3 buckets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cleanup_aggregations.py --hourly --last 24        # Delete last 24 hours
  python cleanup_aggregations.py --weekly --last 2         # Delete last 2 weeks
  python cleanup_aggregations.py --monthly --last 3        # Delete last 3 months
  python cleanup_aggregations.py --yearly --last 1         # Delete last 1 year
  python cleanup_aggregations.py --all --last 2            # Delete last 2 periods from all
  python cleanup_aggregations.py --weekly --all-data       # Delete ALL weekly data
  python cleanup_aggregations.py --dry-run --weekly --last 2  # Preview without deleting
        """
    )
    
    parser.add_argument("--hourly", action="store_true", help="Cleanup hourly aggregations")
    parser.add_argument("--weekly", action="store_true", help="Cleanup weekly aggregations")
    parser.add_argument("--monthly", action="store_true", help="Cleanup monthly aggregations")
    parser.add_argument("--yearly", action="store_true", help="Cleanup yearly aggregations")
    parser.add_argument("--all", action="store_true", help="Cleanup all aggregation levels")
    parser.add_argument("--last", type=int, help="Number of periods to cleanup (e.g., --last 2 for last 2 periods)")
    parser.add_argument("--all-data", action="store_true", help="Delete ALL data (ignores --last)")
    parser.add_argument("--dry-run", action="store_true", help="Preview what would be deleted without actually deleting")
    
    args = parser.parse_args()
    
    # Validate arguments
    if not any([args.hourly, args.weekly, args.monthly, args.yearly, args.all]):
        parser.error("Must specify at least one of: --hourly, --weekly, --monthly, --yearly, --all")
    
    if not args.all_data and not args.last:
        parser.error("Must specify --last N or --all-data")
    
    if args.all:
        args.hourly = args.weekly = args.monthly = args.yearly = True
    
    print("=" * 60)
    print("  CLEANUP AGGREGATION DATA")
    print("=" * 60)
    print(f"  Timestamp: {datetime.datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"  Mode: {'DRY-RUN (no changes will be made)' if args.dry_run else 'LIVE (files will be deleted)'}")
    if args.all_data:
        print(f"  Target: ALL DATA")
    else:
        print(f"  Target: Last {args.last} period(s)")
    print("=" * 60)
    
    total_deleted = 0
    
    if args.hourly:
        total_deleted += cleanup_hourly(args.last or 0, args.dry_run, args.all_data)
    
    if args.weekly:
        total_deleted += cleanup_weekly(args.last or 0, args.dry_run, args.all_data)
    
    if args.monthly:
        total_deleted += cleanup_monthly(args.last or 0, args.dry_run, args.all_data)
    
    if args.yearly:
        total_deleted += cleanup_yearly(args.last or 0, args.dry_run, args.all_data)
    
    print("\n" + "=" * 60)
    print(f"  CLEANUP COMPLETE!")
    print(f"  Total files {'to delete' if args.dry_run else 'deleted'}: {total_deleted}")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    exit(main())
