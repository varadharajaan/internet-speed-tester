#!/usr/bin/env python3
"""Quick utility to check speed test data from S3 with multiple time period views."""
import boto3
import json
import re
import argparse
from datetime import datetime, timedelta
from collections import defaultdict

s3 = boto3.client('s3', region_name='ap-south-1')

# Bucket configuration - different aggregation levels use different buckets
BUCKETS = {
    'raw': 'vd-speed-test',
    'hourly': 'vd-speed-test-hourly-prod',
    'daily': 'vd-speed-test',
    'weekly': 'vd-speed-test-weekly-prod',
    'monthly': 'vd-speed-test-monthly-prod',
    'yearly': 'vd-speed-test-yearly-prod',
}

# Period configurations
# Raw data is in: year=YYYY/month=YYYYMM/day=YYYYMMDD/minute=YYYYMMDDHHmm/ (legacy)
#             or: host=X/year=YYYY/month=YYYYMM/day=YYYYMMDD/minute=YYYYMMDDHHmm/ (new)
# Aggregated data is in: aggregated/year=YYYY/month=YYYYMM/day=YYYYMMDD/ (legacy)
#                    or: aggregated/host=X/year=YYYY/month=YYYYMM/day=YYYYMMDD/ (new)
PERIODS = {
    'latest': {'desc': 'Most recent speed test(s)', 'bucket': 'raw'},
    'minutes': {'desc': 'Minute-level raw data', 'bucket': 'raw'},
    'hourly': {'desc': 'Hourly aggregated data', 'bucket': 'hourly'},
    'daily': {'desc': 'Daily aggregated data', 'bucket': 'daily'},
    'weekly': {'desc': 'Weekly aggregated data', 'bucket': 'weekly'},
    'monthly': {'desc': 'Monthly aggregated data', 'bucket': 'monthly'},
    'yearly': {'desc': 'Yearly aggregated data', 'bucket': 'yearly'},
}

def parse_minute(key):
    """Extract minute timestamp from S3 key and convert to readable format."""
    m = re.search(r'minute=(\d+)', key)
    if m and len(m.group(1)) == 12:
        dt = datetime.strptime(m.group(1), '%Y%m%d%H%M')
        return dt.strftime('%Y-%m-%d %H:%M')
    return 'Unknown'

def parse_period_key(key, period):
    """Extract timestamp from aggregation key based on period type."""
    if period == 'hourly':
        m = re.search(r'hour=(\d+)', key)
        if m and len(m.group(1)) == 10:
            dt = datetime.strptime(m.group(1), '%Y%m%d%H')
            return dt.strftime('%Y-%m-%d %H:00')
    elif period == 'daily':
        m = re.search(r'day=(\d+)', key)
        if m and len(m.group(1)) == 8:
            dt = datetime.strptime(m.group(1), '%Y%m%d')
            return dt.strftime('%Y-%m-%d')
    elif period == 'weekly':
        # Format: week=2025W52 (YYYYWWW pattern)
        m = re.search(r'week=(\d{4})W(\d{1,2})', key)
        if m:
            year = int(m.group(1))
            week = int(m.group(2))
            return f"{year}-W{week:02d}"
    elif period == 'monthly':
        m = re.search(r'month=(\d+)', key)
        if m and len(m.group(1)) == 6:
            dt = datetime.strptime(m.group(1), '%Y%m')
            return dt.strftime('%Y-%m')
    elif period == 'yearly':
        # Match year= but not followed by month=
        m = re.search(r'year=(\d{4})(?:/|$)', key)
        if m:
            return m.group(1)
    return 'Unknown'

def extract_value(val):
    """Extract numeric part from strings like '191.17 Mbps'."""
    if isinstance(val, str):
        m = re.match(r'([\d.]+)', val)
        return m.group(1) if m else val
    return val

def format_value(val, suffix=''):
    """Format a value for display."""
    if val is None or val == 'N/A':
        return 'N/A'
    try:
        return f"{float(val):.2f}{suffix}"
    except (ValueError, TypeError):
        return str(val)

def list_files(prefix, bucket=None, max_keys=1000):
    """List files from S3 with the given prefix(es)."""
    if bucket is None:
        bucket = BUCKETS['raw']
    files = []
    prefixes = prefix if isinstance(prefix, list) else [prefix]
    
    for pfx in prefixes:
        paginator = s3.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=bucket, Prefix=pfx, PaginationConfig={'MaxItems': max_keys}):
            for obj in page.get('Contents', []):
                if obj['Key'].endswith('.json'):
                    files.append(obj)
    return files

def get_data(key, bucket=None):
    """Fetch and parse JSON data from S3."""
    if bucket is None:
        bucket = BUCKETS['raw']
    obj = s3.get_object(Bucket=bucket, Key=key)
    return json.loads(obj['Body'].read().decode('utf-8'))

def list_raw_data_files(max_keys=1000):
    """List raw speed test files from both legacy and new paths."""
    bucket = BUCKETS['raw']
    files = []
    # Legacy path: year=YYYY/...
    files.extend(list_files('year=', bucket, max_keys))
    # New host-based path: host=X/year=YYYY/...
    files.extend(list_files('host=', bucket, max_keys))
    # Filter to only minute-level JSON files
    return [f for f in files if 'minute=' in f['Key'] and f['Key'].endswith('.json')]

def show_latest(count=1):
    """Show latest speed test results."""
    files = list_raw_data_files()
    files = sorted(files, key=lambda x: x['LastModified'], reverse=True)[:count]
    
    if not files:
        print("No speed test files found")
        return
    
    if count == 1:
        data = get_data(files[0]['Key'])
        print(f"\n=== LATEST SPEED TEST (Raw/Minute Data) ===\n")
        print(f"Time:     {parse_minute(files[0]['Key'])} IST")
        print(f"Download: {data.get('download_mbps', 'N/A')}")
        print(f"Upload:   {data.get('upload_mbps', 'N/A')}")
        print(f"Ping:     {data.get('ping_ms', 'N/A')}")
        print(f"\nThis is the most recent individual speed test result.")
        print(f"Use --period <minutes|hourly|daily|weekly|monthly|yearly> for aggregated views")
    else:
        print(f"\n=== LATEST {count} SPEED TESTS (Raw/Minute Data) ===")
        print(f"Individual speed test results, most recent first:")
        print_minute_table(files)

def show_minutes(count=10):
    """Show minute-level raw data."""
    files = list_raw_data_files()
    files = sorted(files, key=lambda x: x['LastModified'], reverse=True)[:count]
    
    if not files:
        print("No minute-level data found")
        return
    
    print(f"\n=== RAW MINUTE-LEVEL DATA (Last {count}) ===")
    print(f"Individual speed test results (not aggregated):")
    print_minute_table(files)

def print_minute_table(files):
    """Print minute-level data in table format."""
    print(f"\n{'Time (IST)':<18} {'Download':<12} {'Upload':<12} {'Ping':<10}")
    print("-" * 54)
    for f in files:
        data = get_data(f['Key'])
        time_str = parse_minute(f['Key'])
        dl = extract_value(data.get('download_mbps', 'N/A'))
        ul = extract_value(data.get('upload_mbps', 'N/A'))
        ping = extract_value(data.get('ping_ms', 'N/A'))
        print(f"{time_str:<18} {dl:>8} Mbps {ul:>8} Mbps {ping:>6} ms")

def show_aggregation(period, count=10):
    """Show aggregated data for a specific period."""
    # Get the correct bucket for this period
    bucket = BUCKETS.get(period, BUCKETS['raw'])
    
    # Get aggregated files from the appropriate bucket
    files = list_files('aggregated/', bucket)
    
    # Filter based on period type
    if period == 'hourly':
        files = [f for f in files if 'hour=' in f['Key']]
    elif period == 'daily':
        # Daily: has day= but not hour=, also skip host-specific if global exists
        files = [f for f in files if 'day=' in f['Key'] and 'hour=' not in f['Key']]
    elif period == 'weekly':
        files = [f for f in files if 'week=' in f['Key']]
    elif period == 'monthly':
        files = [f for f in files if 'month=' in f['Key'] and 'day=' not in f['Key'] and 'week=' not in f['Key']]
    elif period == 'yearly':
        files = [f for f in files if 'year=' in f['Key'] and 'month=' not in f['Key']]
    
    # Deduplicate by date (prefer non-host-specific entries if both exist)
    seen_dates = {}
    for f in files:
        date_key = parse_period_key(f['Key'], period)
        is_host_specific = 'host=' in f['Key']
        if date_key not in seen_dates or (not is_host_specific and 'host=' in seen_dates[date_key]['Key']):
            seen_dates[date_key] = f
    
    # Sort by date key (descending) rather than file path
    sorted_dates = sorted(seen_dates.keys(), reverse=True)[:count]
    files = [(seen_dates[d], bucket) for d in sorted_dates]  # Include bucket with each file
    
    if not files:
        print(f"No {period} aggregation data found")
        print(f"Hint: Aggregations may need to be generated first.")
        print(f"Bucket: {bucket}")
        return
    
    # Determine column widths based on period
    time_width = {'hourly': 16, 'daily': 12, 'weekly': 10, 'monthly': 8, 'yearly': 6}.get(period, 18)
    
    print(f"\n=== {period.upper()} AGGREGATIONS (Last {len(files)}) ===")
    print(f"Averaged data per {period} period:")
    print(f"\n{'Period':<{time_width}} {'Avg DL':<12} {'Avg UL':<12} {'Avg Ping':<10} {'Samples':<8}")
    print("-" * (time_width + 44))
    
    for f, f_bucket in files:
        try:
            data = get_data(f['Key'], f_bucket)
            time_str = parse_period_key(f['Key'], period)
            
            # Handle different data formats based on period type
            overall = data.get('overall', {})
            if overall:
                # Daily aggregation nested format
                avg_dl = overall.get('download_mbps', {}).get('avg') or overall.get('avg_download_mbps')
                avg_ul = overall.get('upload_mbps', {}).get('avg') or overall.get('avg_upload_mbps')
                avg_ping = overall.get('ping_ms', {}).get('avg') or overall.get('avg_ping_ms')
            else:
                # Weekly/Monthly/Yearly use flat format: avg_download, avg_upload, avg_ping
                avg_dl = (data.get('avg_download') or data.get('avg_download_mbps') or 
                          data.get('download_mbps', 'N/A'))
                avg_ul = (data.get('avg_upload') or data.get('avg_upload_mbps') or 
                          data.get('upload_mbps', 'N/A'))
                avg_ping = (data.get('avg_ping') or data.get('avg_ping_ms') or 
                            data.get('ping_ms', 'N/A'))
            
            count_val = data.get('days', data.get('records', data.get('count', data.get('sample_count', '-'))))
            
            dl_str = format_value(avg_dl, ' Mbps')
            ul_str = format_value(avg_ul, ' Mbps')
            ping_str = format_value(avg_ping, ' ms')
            
            print(f"{time_str:<{time_width}} {dl_str:<12} {ul_str:<12} {ping_str:<10} {count_val:<8}")
        except Exception as e:
            print(f"Error reading {f['Key']}: {e}")

def show_summary():
    """Show a summary of available data across all periods."""
    print("\n=== SPEED TEST DATA SUMMARY ===\n")
    
    # Raw data
    raw_files = list_raw_data_files()
    print(f"{'Minutes':<10} : {len(raw_files)} records (Raw speed test data)")
    
    # Aggregated data from each bucket
    hourly_files = list_files('aggregated/', BUCKETS['hourly'])
    hourly = [f for f in hourly_files if 'hour=' in f['Key']]
    
    daily_files = list_files('aggregated/', BUCKETS['daily'])
    daily = [f for f in daily_files if 'day=' in f['Key'] and 'hour=' not in f['Key']]
    
    weekly_files = list_files('aggregated/', BUCKETS['weekly'])
    weekly = [f for f in weekly_files if 'week=' in f['Key']]
    
    monthly_files = list_files('aggregated/', BUCKETS['monthly'])
    monthly = [f for f in monthly_files if 'month=' in f['Key'] and 'day=' not in f['Key']]
    
    yearly_files = list_files('aggregated/', BUCKETS['yearly'])
    yearly = [f for f in yearly_files if 'year=' in f['Key'] and 'month=' not in f['Key']]
    
    print(f"{'Hourly':<10} : {len(hourly)} records (Hourly aggregated)")
    print(f"{'Daily':<10} : {len(daily)} records (Daily aggregated)")
    print(f"{'Weekly':<10} : {len(weekly)} records (Weekly aggregated)")
    print(f"{'Monthly':<10} : {len(monthly)} records (Monthly aggregated)")
    print(f"{'Yearly':<10} : {len(yearly)} records (Yearly aggregated)")
    
    # Show date ranges
    if raw_files:
        raw_sorted = sorted(raw_files, key=lambda x: x['Key'])
        first_date = parse_minute(raw_sorted[0]['Key'])
        last_date = parse_minute(raw_sorted[-1]['Key'])
        print(f"\nRaw data range: {first_date} to {last_date}")
    
    if daily:
        daily_sorted = sorted(daily, key=lambda x: x['Key'])
        first_day = parse_period_key(daily_sorted[0]['Key'], 'daily')
        last_day = parse_period_key(daily_sorted[-1]['Key'], 'daily')
        print(f"Daily aggregation range: {first_day} to {last_day}")
    
    print("\nUse --period <period> to view specific data")

def main():
    parser = argparse.ArgumentParser(
        description='Check speed test data from S3',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python check_latest.py                    # Show latest result
  python check_latest.py --period latest    # Same as above
  python check_latest.py --period minutes --last 20   # Last 20 minute readings
  python check_latest.py --period daily --last 7      # Last 7 days
  python check_latest.py --period weekly --last 4     # Last 4 weeks
  python check_latest.py --period monthly --last 12   # Last 12 months
  python check_latest.py --period yearly             # Yearly data
  python check_latest.py --summary                   # Show data summary
        """
    )
    parser.add_argument('--period', '-p', choices=list(PERIODS.keys()), default='latest',
                        help='Time period to view (default: latest)')
    parser.add_argument('--last', '-n', type=int, default=None,
                        help='Number of results to show')
    parser.add_argument('--summary', '-s', action='store_true',
                        help='Show summary of available data')
    args = parser.parse_args()
    
    if args.summary:
        show_summary()
        return
    
    # Set default counts based on period
    default_counts = {
        'latest': 1,
        'minutes': 10,
        'hourly': 24,
        'daily': 7,
        'weekly': 4,
        'monthly': 12,
        'yearly': 5,
    }
    count = args.last if args.last else default_counts.get(args.period, 10)
    
    if args.period == 'latest':
        show_latest(count)
    elif args.period == 'minutes':
        show_minutes(count)
    else:
        show_aggregation(args.period, count)

if __name__ == '__main__':
    main()
