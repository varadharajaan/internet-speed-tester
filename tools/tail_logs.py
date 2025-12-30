#!/usr/bin/env python3
"""
Tail AWS Lambda logs in real-time.

Usage:
  python tail_logs.py                     # Dashboard logs (default)
  python tail_logs.py --lambda dashboard  # Dashboard logs
  python tail_logs.py --lambda daily      # Daily aggregator logs
  python tail_logs.py --lambda hourly     # Hourly checker logs
  python tail_logs.py --lambda all        # All Lambda logs
  python tail_logs.py --since 30m         # Last 30 minutes
  python tail_logs.py --since 1h          # Last 1 hour
"""
import boto3
import argparse
import time
import re
from datetime import datetime, timedelta, timezone

# Lambda log group mappings
LOG_GROUPS = {
    'dashboard': '/aws/lambda/vd-speedtest-dashboard-prod',
    'daily': '/aws/lambda/vd-speedtest-daily-aggregator-prod',
    'hourly': '/aws/lambda/vd-speedtest-hourly-checker-prod',
}

def parse_since(since_str: str) -> int:
    """Parse since string (e.g., '30m', '1h', '2d') to milliseconds timestamp."""
    match = re.match(r'(\d+)([mhd])', since_str.lower())
    if not match:
        return int((datetime.now(timezone.utc) - timedelta(minutes=5)).timestamp() * 1000)
    
    value, unit = int(match.group(1)), match.group(2)
    if unit == 'm':
        delta = timedelta(minutes=value)
    elif unit == 'h':
        delta = timedelta(hours=value)
    elif unit == 'd':
        delta = timedelta(days=value)
    else:
        delta = timedelta(minutes=5)
    
    return int((datetime.now(timezone.utc) - delta).timestamp() * 1000)


def format_log_event(event: dict, log_group: str) -> str:
    """Format a log event for display."""
    timestamp = datetime.fromtimestamp(event['timestamp'] / 1000)
    message = event['message'].strip()
    
    # Extract lambda name from log group
    lambda_name = log_group.split('/')[-1].replace('vd-speedtest-', '').replace('-prod', '')
    
    # Color coding based on content
    prefix = f"[{timestamp.strftime('%H:%M:%S')}] [{lambda_name}]"
    
    # Skip START, END, REPORT lines for cleaner output
    if message.startswith(('START ', 'END ', 'REPORT ')):
        return None
    
    # Highlight errors
    if 'ERROR' in message or 'Error' in message or 'exception' in message.lower():
        return f"\033[91m{prefix} {message}\033[0m"  # Red
    elif 'WARNING' in message or 'WARN' in message:
        return f"\033[93m{prefix} {message}\033[0m"  # Yellow
    elif 'INFO' in message:
        return f"\033[92m{prefix} {message}\033[0m"  # Green
    
    return f"{prefix} {message}"


def tail_logs(log_groups: list, since: str = '5m', follow: bool = True):
    """Tail logs from specified log groups."""
    client = boto3.client('logs', region_name='ap-south-1')
    start_time = parse_since(since)
    
    print(f"📋 Tailing logs from: {', '.join(log_groups)}")
    print(f"⏰ Since: {since} ago")
    print(f"{'🔄 Following...' if follow else ''}")
    print("-" * 60)
    
    seen_events = set()
    
    try:
        while True:
            for log_group in log_groups:
                try:
                    response = client.filter_log_events(
                        logGroupName=log_group,
                        startTime=start_time,
                        limit=100,
                        interleaved=True
                    )
                    
                    for event in response.get('events', []):
                        event_id = event['eventId']
                        if event_id not in seen_events:
                            seen_events.add(event_id)
                            formatted = format_log_event(event, log_group)
                            if formatted:
                                print(formatted)
                            # Update start time to avoid re-fetching
                            start_time = max(start_time, event['timestamp'] + 1)
                
                except client.exceptions.ResourceNotFoundException:
                    print(f"⚠️  Log group not found: {log_group}")
                except Exception as e:
                    print(f"❌ Error fetching {log_group}: {e}")
            
            if not follow:
                break
            
            time.sleep(2)  # Poll every 2 seconds
    
    except KeyboardInterrupt:
        print("\n\n✅ Stopped tailing logs.")


def main():
    parser = argparse.ArgumentParser(
        description='Tail AWS Lambda logs in real-time',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tail_logs.py                     # Dashboard logs (default)
  python tail_logs.py -l dashboard        # Dashboard logs
  python tail_logs.py -l daily            # Daily aggregator logs
  python tail_logs.py -l hourly           # Hourly checker logs
  python tail_logs.py -l all              # All Lambda logs
  python tail_logs.py --since 30m         # Last 30 minutes
  python tail_logs.py --since 1h          # Last 1 hour
  python tail_logs.py --no-follow         # Don't follow, just show recent
        """
    )
    
    parser.add_argument(
        '--lambda', '-l',
        dest='lambda_name',
        choices=['dashboard', 'daily', 'hourly', 'all'],
        default='dashboard',
        help='Which Lambda to tail (default: dashboard)'
    )
    parser.add_argument(
        '--since', '-s',
        default='5m',
        help='How far back to start (e.g., 5m, 30m, 1h, 2d). Default: 5m'
    )
    parser.add_argument(
        '--no-follow', '-n',
        action='store_true',
        help='Don\'t follow logs, just show recent entries'
    )
    
    args = parser.parse_args()
    
    # Determine which log groups to tail
    if args.lambda_name == 'all':
        log_groups = list(LOG_GROUPS.values())
    else:
        log_groups = [LOG_GROUPS[args.lambda_name]]
    
    tail_logs(log_groups, args.since, follow=not args.no_follow)


if __name__ == '__main__':
    main()
