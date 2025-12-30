#!/usr/bin/env python3
"""
Cleanup duplicate speed test entries from S3.

Duplicates occur when Task Scheduler triggers catch-up runs, resulting in
multiple files for the same 15-minute bucket.

Usage:
  python cleanup_duplicates.py                       # Scan minutes for duplicates (default)
  python cleanup_duplicates.py --period minutes      # Same as above
  python cleanup_duplicates.py --period hourly       # Check hourly bucket
  python cleanup_duplicates.py --period daily        # Check daily bucket
  python cleanup_duplicates.py --period all          # Check all buckets
  python cleanup_duplicates.py --last 100            # Check only last 100 files
  python cleanup_duplicates.py --delete              # Actually delete duplicates
"""
import argparse
import sys
import os
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from s3_speed_utils import (
    S3SpeedClient,
    S3SpeedConfig,
    KeyParser,
    PeriodMixin,
    CountMixin,
    DryRunMixin,
    DuplicateDetector,
)


class DuplicateCleanup(PeriodMixin, CountMixin, DryRunMixin):
    """Tool to find and remove duplicate speed test entries."""
    
    def __init__(self):
        self.client = S3SpeedClient()
        self.detector = DuplicateDetector(self.client)
        self.parser = KeyParser()
        self.config = S3SpeedConfig
    
    def scan_duplicates(self, period: str, limit: int = None):
        """Scan for duplicates and return stats."""
        bucket = self.config.get_bucket(period)
        print(f"Scanning for duplicates in {period} data (bucket: {bucket})...")
        
        if period in ('minutes', 'latest'):
            files = self.client.list_raw_data_files()
        else:
            files = self.client.list_aggregation_files(period)
        
        if limit:
            # Sort by LastModified descending and take the last N
            files = sorted(files, key=lambda x: x['LastModified'], reverse=True)[:limit]
            print(f"Checking last {len(files)} files")
        else:
            print(f"Checking all {len(files)} files")
        
        duplicates = self.detector.find_duplicates(period, files)
        return duplicates, files, bucket
    
    def scan_all_periods(self):
        """Scan all periods for duplicates."""
        print("Scanning ALL periods for duplicates...\n")
        all_results = {}
        
        for period in ['minutes', 'hourly', 'daily', 'weekly', 'monthly', 'yearly']:
            bucket = self.config.get_bucket(period)
            
            if period == 'minutes':
                files = self.client.list_raw_data_files()
            else:
                files = self.client.list_aggregation_files(period)
            
            duplicates = self.detector.find_duplicates(period, files)
            
            total_files = len(files)
            dupe_buckets = len(duplicates)
            dupe_files = sum(len(v) - 1 for v in duplicates.values())
            
            status = f"⚠ {dupe_files} duplicates" if dupe_files else "✓ clean"
            print(f"{period.capitalize():<10} : {total_files:>5} files, {status}")
            
            if duplicates:
                all_results[period] = {
                    'duplicates': duplicates,
                    'bucket': bucket,
                }
        
        return all_results
    
    def show_duplicates(self, duplicates: dict, period: str):
        """Display duplicate information."""
        if not duplicates:
            print(f"\n✓ No duplicates found in {period} data!")
            return
        
        total_dupes = sum(len(v) - 1 for v in duplicates.values())
        print(f"\n⚠ Found {total_dupes} duplicate files across {len(duplicates)} {period} buckets")
        print(self.detector.format_duplicate_report(duplicates, period))
    
    def delete_duplicates(self, duplicates: dict, bucket: str, period: str, dry_run: bool = True):
        """Delete duplicate files (keeps oldest per bucket)."""
        to_delete = self.detector.get_duplicates_to_delete(duplicates)
        
        if not to_delete:
            print("\nNo duplicates to delete.")
            return
        
        print(f"\n{'[DRY RUN] Would delete' if dry_run else 'Deleting'} {len(to_delete)} duplicate files from {period}...")
        
        if dry_run:
            for f in to_delete[:10]:
                if period in ('minutes', 'latest'):
                    time_str = self.parser.parse_minute(f['Key'])
                else:
                    time_str = self.parser.parse_period_key(f['Key'], period)
                print(f"  Would delete: {time_str} - {f['Key'].split('/')[-1]}")
            if len(to_delete) > 10:
                print(f"  ... and {len(to_delete) - 10} more")
            print("\nRun with --delete to actually remove these files.")
        else:
            # Confirm before deletion
            confirm = input(f"\nAre you sure you want to delete {len(to_delete)} files from {bucket}? (yes/no): ")
            if confirm.lower() != 'yes':
                print("Cancelled.")
                return
            
            keys = [f['Key'] for f in to_delete]
            success, failed = self.client.delete_files(keys, bucket)
            print(f"\n✓ Deleted {success} files, {failed} failed")
    
    def run(self, args):
        """Main execution."""
        period = args.period
        
        if period == 'all':
            # Scan all periods
            all_results = self.scan_all_periods()
            
            if not all_results:
                print("\n✓ All periods are clean - no duplicates found!")
                return
            
            # Show details for each period with duplicates
            for period_name, data in all_results.items():
                print(f"\n{'='*60}")
                print(f"{period_name.upper()} DUPLICATES")
                print('='*60)
                self.show_duplicates(data['duplicates'], period_name)
                self.delete_duplicates(data['duplicates'], data['bucket'], period_name, dry_run=not args.delete)
        else:
            # Scan single period
            duplicates, files, bucket = self.scan_duplicates(period, args.last)
            self.show_duplicates(duplicates, period)
            
            if duplicates:
                self.delete_duplicates(duplicates, bucket, period, dry_run=not args.delete)


def main():
    parser = argparse.ArgumentParser(
        description='Find and remove duplicate speed test entries from S3',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cleanup_duplicates.py                       # Scan minutes (default)
  python cleanup_duplicates.py --period hourly       # Check hourly bucket
  python cleanup_duplicates.py --period daily        # Check daily bucket  
  python cleanup_duplicates.py --period all          # Check ALL buckets
  python cleanup_duplicates.py --last 100            # Check only last 100 files
  python cleanup_duplicates.py --delete              # Delete duplicates (with confirmation)
  python cleanup_duplicates.py --period all --delete # Delete duplicates from all buckets

Strategy:
  For each time bucket with multiple files, the OLDEST file (first upload) is
  kept and all others are marked for deletion. This preserves the original data.
        """
    )
    
    # Add period with 'all' option
    period_choices = S3SpeedConfig.period_names() + ['all']
    parser.add_argument(
        '--period', '-p',
        choices=period_choices,
        default='minutes',
        help='Time period to check (default: minutes). Use "all" to check all buckets.'
    )
    
    CountMixin.add_count_args(parser)
    parser.add_argument(
        '--delete',
        action='store_true',
        help='Actually delete duplicates (default is dry-run/scan only)'
    )
    
    args = parser.parse_args()
    
    cleanup = DuplicateCleanup()
    cleanup.run(args)


if __name__ == '__main__':
    main()
