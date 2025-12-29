#!/usr/bin/env python3
"""Quick utility to check the latest speed test upload to S3."""
import boto3
import json
import re
import argparse
from datetime import datetime

s3 = boto3.client('s3', region_name='ap-south-1')
BUCKET = 'vd-speed-test'

def parse_minute(key):
    """Extract minute timestamp from S3 key and convert to readable format."""
    m = re.search(r'minute=(\d+)', key)
    if m and len(m.group(1)) == 12:
        dt = datetime.strptime(m.group(1), '%Y%m%d%H%M')
        return dt.strftime('%Y-%m-%d %H:%M')
    return 'Unknown'

def get_data(key):
    """Fetch and parse JSON data from S3."""
    obj = s3.get_object(Bucket=BUCKET, Key=key)
    return json.loads(obj['Body'].read().decode('utf-8'))

def extract_value(val):
    """Extract numeric part from strings like '191.17 Mbps'."""
    if isinstance(val, str):
        m = re.match(r'([\d.]+)', val)
        return m.group(1) if m else val
    return val

def main():
    parser = argparse.ArgumentParser(description='Check latest speed test uploads')
    parser.add_argument('--last', '--n', type=int, default=1, help='Number of results to show')
    args = parser.parse_args()

    # Get files
    r = s3.list_objects_v2(Bucket=BUCKET, MaxKeys=1000)
    files = [f for f in r.get('Contents', []) if f['Key'].endswith('.json') and 'speed_data' in f['Key']]
    files = sorted(files, key=lambda x: x['LastModified'], reverse=True)[:args.last]

    if not files:
        print("No speed test files found")
        return

    if args.last == 1:
        # Single result - simple format
        data = get_data(files[0]['Key'])
        print(f"Latest: {parse_minute(files[0]['Key'])} IST")
        print(f"Download: {data.get('download_mbps', 'N/A')}")
        print(f"Upload: {data.get('upload_mbps', 'N/A')}")
        print(f"Ping: {data.get('ping_ms', 'N/A')}")
    else:
        # Multiple results - table format
        print(f"{'Time (IST)':<18} {'Download':<12} {'Upload':<12} {'Ping':<10}")
        print("-" * 52)
        for f in files:
            data = get_data(f['Key'])
            time_str = parse_minute(f['Key'])
            dl = extract_value(data.get('download_mbps', 'N/A'))
            ul = extract_value(data.get('upload_mbps', 'N/A'))
            ping = extract_value(data.get('ping_ms', 'N/A'))
            print(f"{time_str:<18} {dl:>8} Mbps {ul:>8} Mbps {ping:>6} ms")

if __name__ == '__main__':
    main()
