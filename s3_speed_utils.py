#!/usr/bin/env python3
"""
Reusable utilities for S3 speed test data operations.

This module provides:
- S3SpeedConfig: Bucket and period configuration
- S3SpeedClient: S3 operations (list, get, delete)
- PeriodMixin: CLI argument parsing for periods
- CountMixin: CLI argument parsing for --last N items

Usage:
    from s3_speed_utils import S3SpeedClient, PeriodMixin, CountMixin
    
    class MyTool(PeriodMixin, CountMixin):
        def __init__(self):
            super().__init__()
            self.client = S3SpeedClient()
"""
import boto3
import json
import re
import argparse
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple
from collections import defaultdict


# ============================================================
# CONFIGURATION
# ============================================================
@dataclass
class PeriodConfig:
    """Configuration for a time period."""
    name: str
    desc: str
    bucket: str
    default_count: int
    key_pattern: str  # Regex pattern to match in S3 key
    exclude_patterns: List[str] = None  # Patterns that must NOT be in the key
    
    def __post_init__(self):
        if self.exclude_patterns is None:
            self.exclude_patterns = []


class S3SpeedConfig:
    """Central configuration for S3 speed test buckets and periods."""
    
    REGION = 'ap-south-1'
    
    # Bucket mappings
    BUCKETS = {
        'raw': 'vd-speed-test',
        'hourly': 'vd-speed-test-hourly-prod',
        'daily': 'vd-speed-test',
        'weekly': 'vd-speed-test-weekly-prod',
        'monthly': 'vd-speed-test-monthly-prod',
        'yearly': 'vd-speed-test-yearly-prod',
    }
    
    # Period configurations
    PERIODS = {
        'latest': PeriodConfig(
            name='latest',
            desc='Most recent speed test(s)',
            bucket='raw',
            default_count=1,
            key_pattern=r'minute=\d+',
        ),
        'minutes': PeriodConfig(
            name='minutes',
            desc='Minute-level raw data',
            bucket='raw',
            default_count=10,
            key_pattern=r'minute=\d+',
        ),
        'hourly': PeriodConfig(
            name='hourly',
            desc='Hourly aggregated data',
            bucket='hourly',
            default_count=24,
            key_pattern=r'hour=\d+',
        ),
        'daily': PeriodConfig(
            name='daily',
            desc='Daily aggregated data',
            bucket='daily',
            default_count=7,
            key_pattern=r'day=\d+',
            exclude_patterns=['hour='],
        ),
        'weekly': PeriodConfig(
            name='weekly',
            desc='Weekly aggregated data',
            bucket='weekly',
            default_count=4,
            key_pattern=r'week=\d+W\d+',
        ),
        'monthly': PeriodConfig(
            name='monthly',
            desc='Monthly aggregated data',
            bucket='monthly',
            default_count=12,
            key_pattern=r'month=\d+',
            exclude_patterns=['day=', 'week='],
        ),
        'yearly': PeriodConfig(
            name='yearly',
            desc='Yearly aggregated data',
            bucket='yearly',
            default_count=5,
            key_pattern=r'year=\d{4}(?:/|$)',
            exclude_patterns=['month='],
        ),
    }
    
    @classmethod
    def get_bucket(cls, period: str) -> str:
        """Get the S3 bucket for a period."""
        config = cls.PERIODS.get(period)
        if config:
            return cls.BUCKETS.get(config.bucket, cls.BUCKETS['raw'])
        return cls.BUCKETS['raw']
    
    @classmethod
    def get_period_config(cls, period: str) -> Optional[PeriodConfig]:
        """Get the configuration for a period."""
        return cls.PERIODS.get(period)
    
    @classmethod
    def period_names(cls) -> List[str]:
        """Get list of all period names."""
        return list(cls.PERIODS.keys())


# ============================================================
# S3 CLIENT
# ============================================================
class S3SpeedClient:
    """S3 operations for speed test data."""
    
    def __init__(self, region: str = None):
        self.region = region or S3SpeedConfig.REGION
        self.s3 = boto3.client('s3', region_name=self.region)
        self.config = S3SpeedConfig
    
    def list_files(self, prefix: str, bucket: str = None, max_keys: int = 1000) -> List[Dict]:
        """List files from S3 with the given prefix."""
        if bucket is None:
            bucket = self.config.BUCKETS['raw']
        
        files = []
        prefixes = prefix if isinstance(prefix, list) else [prefix]
        
        for pfx in prefixes:
            paginator = self.s3.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=bucket, Prefix=pfx, PaginationConfig={'MaxItems': max_keys}):
                for obj in page.get('Contents', []):
                    if obj['Key'].endswith('.json'):
                        files.append(obj)
        return files
    
    def get_data(self, key: str, bucket: str = None) -> Dict:
        """Fetch and parse JSON data from S3."""
        if bucket is None:
            bucket = self.config.BUCKETS['raw']
        obj = self.s3.get_object(Bucket=bucket, Key=key)
        return json.loads(obj['Body'].read().decode('utf-8'))
    
    def delete_file(self, key: str, bucket: str = None) -> bool:
        """Delete a file from S3."""
        if bucket is None:
            bucket = self.config.BUCKETS['raw']
        try:
            self.s3.delete_object(Bucket=bucket, Key=key)
            return True
        except Exception as e:
            print(f"Failed to delete {key}: {e}")
            return False
    
    def delete_files(self, keys: List[str], bucket: str = None) -> Tuple[int, int]:
        """Delete multiple files from S3. Returns (success_count, fail_count)."""
        if bucket is None:
            bucket = self.config.BUCKETS['raw']
        
        success, failed = 0, 0
        # S3 delete_objects can handle up to 1000 keys at a time
        for i in range(0, len(keys), 1000):
            batch = keys[i:i+1000]
            try:
                response = self.s3.delete_objects(
                    Bucket=bucket,
                    Delete={'Objects': [{'Key': k} for k in batch]}
                )
                success += len(batch) - len(response.get('Errors', []))
                failed += len(response.get('Errors', []))
            except Exception as e:
                print(f"Batch delete failed: {e}")
                failed += len(batch)
        
        return success, failed
    
    def list_raw_data_files(self, max_keys: int = 10000) -> List[Dict]:
        """List raw speed test files from both legacy and new paths."""
        bucket = self.config.BUCKETS['raw']
        files = []
        # Legacy path: year=YYYY/...
        files.extend(self.list_files('year=', bucket, max_keys))
        # New host-based path: host=X/year=YYYY/...
        files.extend(self.list_files('host=', bucket, max_keys))
        # Filter to only minute-level JSON files
        return [f for f in files if 'minute=' in f['Key'] and f['Key'].endswith('.json')]
    
    def list_aggregation_files(self, period: str, max_keys: int = 1000) -> List[Dict]:
        """List aggregation files for a specific period."""
        config = self.config.get_period_config(period)
        if not config:
            return []
        
        bucket = self.config.get_bucket(period)
        files = self.list_files('aggregated/', bucket, max_keys)
        
        # Filter by period pattern
        result = []
        for f in files:
            key = f['Key']
            if re.search(config.key_pattern, key):
                # Check exclude patterns
                if not any(excl in key for excl in config.exclude_patterns):
                    result.append(f)
        
        return result


# ============================================================
# PARSING UTILITIES
# ============================================================
class KeyParser:
    """Parse S3 keys to extract timestamps and values."""
    
    @staticmethod
    def parse_minute(key: str) -> str:
        """Extract minute timestamp from S3 key."""
        m = re.search(r'minute=(\d+)', key)
        if m and len(m.group(1)) == 12:
            dt = datetime.strptime(m.group(1), '%Y%m%d%H%M')
            return dt.strftime('%Y-%m-%d %H:%M')
        return 'Unknown'
    
    @staticmethod
    def parse_minute_raw(key: str) -> str:
        """Extract raw minute value (YYYYMMDDHHmm) from S3 key."""
        m = re.search(r'minute=(\d+)', key)
        return m.group(1) if m else ''
    
    @staticmethod
    def parse_period_key(key: str, period: str) -> str:
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
            m = re.search(r'year=(\d{4})(?:/|$)', key)
            if m:
                return m.group(1)
        elif period in ('latest', 'minutes'):
            return KeyParser.parse_minute(key)
        return 'Unknown'
    
    @staticmethod
    def extract_value(val: Any) -> str:
        """Extract numeric part from strings like '191.17 Mbps'."""
        if isinstance(val, str):
            m = re.match(r'([\d.]+)', val)
            return m.group(1) if m else val
        return str(val) if val is not None else 'N/A'
    
    @staticmethod
    def format_value(val: Any, suffix: str = '') -> str:
        """Format a value for display."""
        if val is None or val == 'N/A':
            return 'N/A'
        try:
            return f"{float(val):.2f}{suffix}"
        except (ValueError, TypeError):
            return str(val)


# ============================================================
# MIXINS FOR CLI TOOLS
# ============================================================
class PeriodMixin:
    """Mixin to add --period argument to CLI tools."""
    
    @staticmethod
    def add_period_args(parser: argparse.ArgumentParser):
        """Add period-related arguments to parser."""
        parser.add_argument(
            '--period', '-p',
            choices=S3SpeedConfig.period_names(),
            default='minutes',
            help='Time period to operate on (default: minutes)'
        )
    
    @staticmethod
    def get_period_config(period: str) -> PeriodConfig:
        """Get configuration for a period."""
        return S3SpeedConfig.get_period_config(period)


class CountMixin:
    """Mixin to add --last N argument to CLI tools."""
    
    @staticmethod
    def add_count_args(parser: argparse.ArgumentParser):
        """Add count-related arguments to parser."""
        parser.add_argument(
            '--last', '-n',
            type=int,
            default=None,
            help='Number of results to process'
        )
    
    @staticmethod
    def get_count(args, period: str) -> int:
        """Get the count, using default for period if not specified."""
        if args.last:
            return args.last
        config = S3SpeedConfig.get_period_config(period)
        return config.default_count if config else 10


class DryRunMixin:
    """Mixin to add --dry-run argument to CLI tools."""
    
    @staticmethod
    def add_dry_run_args(parser: argparse.ArgumentParser):
        """Add dry-run argument to parser."""
        parser.add_argument(
            '--dry-run', '-d',
            action='store_true',
            help='Show what would be done without making changes'
        )


# ============================================================
# DUPLICATE DETECTION
# ============================================================
class DuplicateDetector:
    """Detect duplicate speed test entries in S3."""
    
    def __init__(self, client: S3SpeedClient):
        self.client = client
        self.parser = KeyParser()
        self.config = S3SpeedConfig
    
    def find_duplicates(self, period: str = 'minutes', files: List[Dict] = None) -> Dict[str, List[Dict]]:
        """
        Find files with the same time bucket for the given period.
        Returns dict: {time_key: [list of files]}
        Only includes buckets with more than one file.
        """
        if files is None:
            if period in ('minutes', 'latest'):
                files = self.client.list_raw_data_files()
            else:
                files = self.client.list_aggregation_files(period)
        
        # Group by period key
        by_period = defaultdict(list)
        for f in files:
            if period in ('minutes', 'latest'):
                period_key = self.parser.parse_minute_raw(f['Key'])
            else:
                period_key = self.parser.parse_period_key(f['Key'], period)
            if period_key and period_key != 'Unknown':
                by_period[period_key].append(f)
        
        # Return only duplicates
        return {k: v for k, v in by_period.items() if len(v) > 1}
    
    def find_duplicates_by_minute(self, files: List[Dict] = None) -> Dict[str, List[Dict]]:
        """Legacy method - use find_duplicates('minutes') instead."""
        return self.find_duplicates('minutes', files)
    
    def get_duplicates_to_delete(self, duplicates: Dict[str, List[Dict]]) -> List[Dict]:
        """
        For each bucket with duplicates, keep the oldest (first upload) and mark rest for deletion.
        Returns list of files to delete.
        """
        to_delete = []
        for period_key, files in duplicates.items():
            # Sort by LastModified, keep the first one
            sorted_files = sorted(files, key=lambda x: x['LastModified'])
            # Mark all except the first for deletion
            to_delete.extend(sorted_files[1:])
        return to_delete
    
    def format_duplicate_report(self, duplicates: Dict[str, List[Dict]], period: str = 'minutes') -> str:
        """Format a report of duplicates found."""
        if not duplicates:
            return "No duplicates found."
        
        total_dupes = sum(len(v) - 1 for v in duplicates.values())
        period_label = 'minute' if period in ('minutes', 'latest') else period
        lines = [f"Found {len(duplicates)} {period_label} buckets with {total_dupes} duplicates:\n"]
        
        for period_key in sorted(duplicates.keys(), reverse=True)[:20]:  # Show latest 20
            files = duplicates[period_key]
            
            # Format time string based on period
            if period in ('minutes', 'latest'):
                try:
                    dt = datetime.strptime(period_key, '%Y%m%d%H%M')
                    time_str = dt.strftime('%Y-%m-%d %H:%M')
                except:
                    time_str = period_key
            else:
                time_str = period_key
            
            lines.append(f"\n{time_str} ({len(files)} files):")
            for f in sorted(files, key=lambda x: x['LastModified']):
                mod_time = f['LastModified'].strftime('%H:%M:%S')
                lines.append(f"  - {mod_time}: {f['Key'].split('/')[-1]}")
        
        if len(duplicates) > 20:
            lines.append(f"\n... and {len(duplicates) - 20} more {period_label} buckets with duplicates")
        
        return '\n'.join(lines)
    
    def scan_all_periods(self) -> Dict[str, Dict[str, List[Dict]]]:
        """
        Scan all periods for duplicates.
        Returns dict: {period: {time_key: [files]}}
        """
        results = {}
        for period in self.config.period_names():
            if period == 'latest':
                continue  # Skip, same as minutes
            duplicates = self.find_duplicates(period)
            if duplicates:
                results[period] = duplicates
        return results
