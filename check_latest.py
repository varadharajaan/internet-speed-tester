#!/usr/bin/env python3
"""
Quick utility to check speed test data from S3 with multiple time period views.

Usage:
  python check_latest.py                    # Show latest result
  python check_latest.py --period minutes --last 20   # Last 20 minute readings
  python check_latest.py --period daily --last 7      # Last 7 days
  python check_latest.py --period weekly --last 4     # Last 4 weeks
  python check_latest.py --summary                    # Show data summary
"""
import argparse
from collections import defaultdict

from s3_speed_utils import (
    S3SpeedClient,
    S3SpeedConfig,
    KeyParser,
    PeriodMixin,
    CountMixin,
)


class SpeedDataViewer(PeriodMixin, CountMixin):
    """View speed test data from S3."""
    
    def __init__(self):
        self.client = S3SpeedClient()
        self.parser = KeyParser()
        self.config = S3SpeedConfig
    
    def show_latest(self, count: int = 1):
        """Show latest speed test results."""
        files = self.client.list_raw_data_files()
        files = sorted(files, key=lambda x: x['LastModified'], reverse=True)[:count]
        
        if not files:
            print("No speed test files found")
            return
        
        if count == 1:
            data = self.client.get_data(files[0]['Key'])
            print(f"\n=== LATEST SPEED TEST (Raw/Minute Data) ===\n")
            print(f"Time:     {self.parser.parse_minute(files[0]['Key'])} IST")
            print(f"Download: {data.get('download_mbps', 'N/A')}")
            print(f"Upload:   {data.get('upload_mbps', 'N/A')}")
            print(f"Ping:     {data.get('ping_ms', 'N/A')}")
            print(f"\nThis is the most recent individual speed test result.")
            print(f"Use --period <minutes|hourly|daily|weekly|monthly|yearly> for aggregated views")
        else:
            print(f"\n=== LATEST {count} SPEED TESTS (Raw/Minute Data) ===")
            print(f"Individual speed test results, most recent first:")
            self._print_minute_table(files)
    
    def show_minutes(self, count: int = 10):
        """Show minute-level raw data."""
        files = self.client.list_raw_data_files()
        files = sorted(files, key=lambda x: x['LastModified'], reverse=True)[:count]
        
        if not files:
            print("No minute-level data found")
            return
        
        print(f"\n=== RAW MINUTE-LEVEL DATA (Last {count}) ===")
        print(f"Individual speed test results (not aggregated):")
        self._print_minute_table(files)
    
    def _print_minute_table(self, files: list):
        """Print minute-level data in table format."""
        print(f"\n{'Time (IST)':<18} {'Download':<12} {'Upload':<12} {'Ping':<10}")
        print("-" * 54)
        for f in files:
            data = self.client.get_data(f['Key'])
            time_str = self.parser.parse_minute(f['Key'])
            dl = self.parser.extract_value(data.get('download_mbps', 'N/A'))
            ul = self.parser.extract_value(data.get('upload_mbps', 'N/A'))
            ping = self.parser.extract_value(data.get('ping_ms', 'N/A'))
            print(f"{time_str:<18} {dl:>8} Mbps {ul:>8} Mbps {ping:>6} ms")
    
    def show_aggregation(self, period: str, count: int = 10):
        """Show aggregated data for a specific period."""
        bucket = self.config.get_bucket(period)
        files = self.client.list_aggregation_files(period)
        
        # Deduplicate by date (prefer non-host-specific entries if both exist)
        seen_dates = {}
        for f in files:
            date_key = self.parser.parse_period_key(f['Key'], period)
            is_host_specific = 'host=' in f['Key']
            if date_key not in seen_dates or (not is_host_specific and 'host=' in seen_dates[date_key]['Key']):
                seen_dates[date_key] = f
        
        # Sort by date key (descending) rather than file path
        sorted_dates = sorted(seen_dates.keys(), reverse=True)[:count]
        files = [(seen_dates[d], bucket) for d in sorted_dates]
        
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
                data = self.client.get_data(f['Key'], f_bucket)
                time_str = self.parser.parse_period_key(f['Key'], period)
                
                # Handle different data formats based on period type
                overall = data.get('overall', {})
                if overall:
                    avg_dl = overall.get('download_mbps', {}).get('avg') or overall.get('avg_download_mbps')
                    avg_ul = overall.get('upload_mbps', {}).get('avg') or overall.get('avg_upload_mbps')
                    avg_ping = overall.get('ping_ms', {}).get('avg') or overall.get('avg_ping_ms')
                else:
                    avg_dl = (data.get('avg_download') or data.get('avg_download_mbps') or 
                              data.get('download_mbps', 'N/A'))
                    avg_ul = (data.get('avg_upload') or data.get('avg_upload_mbps') or 
                              data.get('upload_mbps', 'N/A'))
                    avg_ping = (data.get('avg_ping') or data.get('avg_ping_ms') or 
                                data.get('ping_ms', 'N/A'))
                
                count_val = data.get('days', data.get('records', data.get('count', data.get('sample_count', '-'))))
                
                dl_str = self.parser.format_value(avg_dl, ' Mbps')
                ul_str = self.parser.format_value(avg_ul, ' Mbps')
                ping_str = self.parser.format_value(avg_ping, ' ms')
                
                print(f"{time_str:<{time_width}} {dl_str:<12} {ul_str:<12} {ping_str:<10} {count_val:<8}")
            except Exception as e:
                print(f"Error reading {f['Key']}: {e}")
    
    def show_summary(self):
        """Show a summary of available data across all periods."""
        print("\n=== SPEED TEST DATA SUMMARY ===\n")
        
        # Raw data
        raw_files = self.client.list_raw_data_files()
        print(f"{'Minutes':<10} : {len(raw_files)} records (Raw speed test data)")
        
        # Aggregated data
        for period in ['hourly', 'daily', 'weekly', 'monthly', 'yearly']:
            files = self.client.list_aggregation_files(period)
            config = self.config.get_period_config(period)
            print(f"{period.capitalize():<10} : {len(files)} records ({config.desc})")
        
        # Show date ranges
        if raw_files:
            raw_sorted = sorted(raw_files, key=lambda x: x['Key'])
            first_date = self.parser.parse_minute(raw_sorted[0]['Key'])
            last_date = self.parser.parse_minute(raw_sorted[-1]['Key'])
            print(f"\nRaw data range: {first_date} to {last_date}")
        
        daily_files = self.client.list_aggregation_files('daily')
        if daily_files:
            daily_sorted = sorted(daily_files, key=lambda x: x['Key'])
            first_day = self.parser.parse_period_key(daily_sorted[0]['Key'], 'daily')
            last_day = self.parser.parse_period_key(daily_sorted[-1]['Key'], 'daily')
            print(f"Daily aggregation range: {first_day} to {last_day}")
        
        print("\nUse --period <period> to view specific data")
    
    def run(self, period: str, count: int, summary: bool = False):
        """Main execution."""
        if summary:
            self.show_summary()
            return
        
        if period == 'latest':
            self.show_latest(count)
        elif period == 'minutes':
            self.show_minutes(count)
        else:
            self.show_aggregation(period, count)


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
    
    PeriodMixin.add_period_args(parser)
    CountMixin.add_count_args(parser)
    parser.add_argument('--summary', '-s', action='store_true',
                        help='Show summary of available data')
    
    # Override default period to 'latest' for this tool
    parser.set_defaults(period='latest')
    
    args = parser.parse_args()
    count = CountMixin.get_count(args, args.period)
    
    viewer = SpeedDataViewer()
    viewer.run(args.period, count, args.summary)


if __name__ == '__main__':
    main()
