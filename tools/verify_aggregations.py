#!/usr/bin/env python3
"""
Verify Aggregation Data Integrity
---------------------------------
Validates that all aggregated data files have the expected structure,
required fields, and sensible values.

Usage:
    python verify_aggregations.py                    # Verify all buckets
    python verify_aggregations.py --hourly           # Verify hourly only
    python verify_aggregations.py --weekly           # Verify weekly only
    python verify_aggregations.py --monthly          # Verify monthly only
    python verify_aggregations.py --yearly           # Verify yearly only
    python verify_aggregations.py --daily            # Verify daily summaries
    python verify_aggregations.py --verbose          # Show detailed output
    python verify_aggregations.py --sample 5         # Check N random samples per bucket
    python verify_aggregations.py --previous         # Verify only files from last backfill
"""
import json
import datetime
import boto3
import os
import sys
import argparse
import random
from typing import Dict, List, Tuple, Optional
import pytz

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Manifest file path (in tools folder)
BACKFILL_MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "..", "backfill_manifest.json")

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


class ValidationResult:
    """Holds validation results for a single file."""
    def __init__(self, key: str):
        self.key = key
        self.valid = True
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.data: Optional[Dict] = None
    
    def add_error(self, msg: str):
        self.valid = False
        self.errors.append(msg)
    
    def add_warning(self, msg: str):
        self.warnings.append(msg)


# ============================================================================
# SCHEMA DEFINITIONS
# ============================================================================

HOURLY_REQUIRED_FIELDS = {
    "hour_ist": str,
    "records": int,
    "overall": dict,
}

HOURLY_OVERALL_FIELDS = {
    "download_mbps": {"avg", "min", "max"},
    "upload_mbps": {"avg", "min", "max"},
    "ping_ms": {"avg", "min", "max"},
}

DAILY_REQUIRED_FIELDS = {
    "date_ist": str,
    "records": int,
    "overall": dict,
}

DAILY_OVERALL_FIELDS = {
    "download_mbps": {"avg", "median", "max", "min"},
    "upload_mbps": {"avg", "median", "max", "min"},
    "ping_ms": {"avg", "median", "max", "min"},
}

WEEKLY_REQUIRED_FIELDS = {
    "week_start": str,
    "week_end": str,
    "days": int,
    "avg_download": (int, float),
    "avg_upload": (int, float),
    "avg_ping": (int, float),
}

MONTHLY_REQUIRED_FIELDS = {
    "month": str,
    "days": int,
    "avg_download": (int, float),
    "avg_upload": (int, float),
    "avg_ping": (int, float),
}

YEARLY_REQUIRED_FIELDS = {
    "year": int,
    "months_aggregated": int,
    "avg_download": (int, float),
    "avg_upload": (int, float),
    "avg_ping": (int, float),
}


# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================

def validate_numeric_range(value: float, min_val: float, max_val: float, field: str) -> Optional[str]:
    """Check if a numeric value is within expected range."""
    if value < min_val:
        return f"{field}={value} is below minimum {min_val}"
    if value > max_val:
        return f"{field}={value} is above maximum {max_val}"
    return None


def validate_hourly(data: Dict, result: ValidationResult) -> None:
    """Validate hourly aggregation data."""
    # Check required fields
    for field, expected_type in HOURLY_REQUIRED_FIELDS.items():
        if field not in data:
            result.add_error(f"Missing required field: {field}")
        elif not isinstance(data[field], expected_type):
            result.add_error(f"Field {field} has wrong type: expected {expected_type}, got {type(data[field])}")
    
    # Check overall structure
    if "overall" in data and isinstance(data["overall"], dict):
        for metric, required_stats in HOURLY_OVERALL_FIELDS.items():
            if metric not in data["overall"]:
                result.add_error(f"Missing metric in overall: {metric}")
            elif isinstance(data["overall"][metric], dict):
                for stat in required_stats:
                    if stat not in data["overall"][metric]:
                        result.add_error(f"Missing stat {stat} in overall.{metric}")
    
    # Validate numeric ranges
    if "records" in data:
        if data["records"] < 0:
            result.add_error("records cannot be negative")
        if data["records"] == 0:
            result.add_warning("records is 0 - empty aggregation")
        if data["records"] > 4:  # 4 tests per hour (every 15 min)
            result.add_warning(f"records={data['records']} exceeds expected 4 per hour")
    
    # Check speed values
    if "overall" in data and isinstance(data["overall"], dict):
        dl = data["overall"].get("download_mbps", {})
        if isinstance(dl, dict) and "avg" in dl:
            err = validate_numeric_range(dl["avg"], 0, 2000, "download_mbps.avg")
            if err:
                result.add_warning(err)


def validate_daily(data: Dict, result: ValidationResult) -> None:
    """Validate daily aggregation data."""
    # Check required fields
    for field, expected_type in DAILY_REQUIRED_FIELDS.items():
        if field not in data:
            result.add_error(f"Missing required field: {field}")
        elif not isinstance(data[field], expected_type):
            result.add_error(f"Field {field} has wrong type: expected {expected_type}, got {type(data[field])}")
    
    # Check date format
    if "date_ist" in data:
        try:
            datetime.datetime.strptime(data["date_ist"], "%Y-%m-%d")
        except ValueError:
            result.add_error(f"Invalid date format: {data['date_ist']}, expected YYYY-MM-DD")
    
    # Check overall structure
    if "overall" in data and isinstance(data["overall"], dict):
        for metric, required_stats in DAILY_OVERALL_FIELDS.items():
            if metric not in data["overall"]:
                result.add_error(f"Missing metric in overall: {metric}")
            elif isinstance(data["overall"][metric], dict):
                for stat in required_stats:
                    if stat not in data["overall"][metric]:
                        result.add_warning(f"Missing stat {stat} in overall.{metric}")
    
    # Validate records
    if "records" in data:
        if data["records"] < 0:
            result.add_error("records cannot be negative")
        if data["records"] == 0:
            result.add_warning("records is 0 - empty aggregation")
        if data["records"] > 96:  # 96 tests per day (every 15 min)
            result.add_warning(f"records={data['records']} exceeds expected 96 per day (multi-host?)")
    
    # Check completion rate (can exceed 100% with multiple hosts)
    if "completion_rate" in data:
        if data["completion_rate"] < 0:
            result.add_error(f"completion_rate={data['completion_rate']} cannot be negative")
        if data["completion_rate"] > 100:
            result.add_warning(f"completion_rate={data['completion_rate']}% exceeds 100% (multi-host or frequent tests)")


def validate_weekly(data: Dict, result: ValidationResult) -> None:
    """Validate weekly aggregation data."""
    # Check required fields
    for field, expected_type in WEEKLY_REQUIRED_FIELDS.items():
        if field not in data:
            result.add_error(f"Missing required field: {field}")
        elif not isinstance(data[field], expected_type):
            result.add_error(f"Field {field} has wrong type: expected {expected_type}, got {type(data[field])}")
    
    # Check date formats
    for date_field in ["week_start", "week_end"]:
        if date_field in data:
            try:
                datetime.datetime.strptime(data[date_field], "%Y-%m-%d")
            except ValueError:
                result.add_error(f"Invalid date format: {data[date_field]}")
    
    # Check days is valid
    if "days" in data:
        if data["days"] < 0:
            result.add_error("days cannot be negative")
        if data["days"] > 7:
            result.add_error(f"days={data['days']} exceeds 7 for a week")
        if data["days"] == 0:
            result.add_warning("days is 0 - empty aggregation")
    
    # Check speed values are reasonable
    for field in ["avg_download", "avg_upload"]:
        if field in data:
            err = validate_numeric_range(data[field], 0, 2000, field)
            if err:
                result.add_warning(err)
    
    if "avg_ping" in data:
        err = validate_numeric_range(data["avg_ping"], 0, 1000, "avg_ping")
        if err:
            result.add_warning(err)


def validate_monthly(data: Dict, result: ValidationResult) -> None:
    """Validate monthly aggregation data."""
    # Check required fields
    for field, expected_type in MONTHLY_REQUIRED_FIELDS.items():
        if field not in data:
            result.add_error(f"Missing required field: {field}")
        elif not isinstance(data[field], expected_type):
            result.add_error(f"Field {field} has wrong type: expected {expected_type}, got {type(data[field])}")
    
    # Check month format (YYYYMM)
    if "month" in data:
        if len(data["month"]) != 6 or not data["month"].isdigit():
            result.add_error(f"Invalid month format: {data['month']}, expected YYYYMM")
    
    # Check days is valid
    if "days" in data:
        if data["days"] < 0:
            result.add_error("days cannot be negative")
        if data["days"] > 31:
            result.add_error(f"days={data['days']} exceeds 31 for a month")
        if data["days"] == 0:
            result.add_warning("days is 0 - empty aggregation")
    
    # Check speed values are reasonable
    for field in ["avg_download", "avg_upload"]:
        if field in data:
            err = validate_numeric_range(data[field], 0, 2000, field)
            if err:
                result.add_warning(err)


def validate_yearly(data: Dict, result: ValidationResult) -> None:
    """Validate yearly aggregation data."""
    # Check required fields
    for field, expected_type in YEARLY_REQUIRED_FIELDS.items():
        if field not in data:
            result.add_error(f"Missing required field: {field}")
        elif not isinstance(data[field], expected_type):
            result.add_error(f"Field {field} has wrong type: expected {expected_type}, got {type(data[field])}")
    
    # Check year is reasonable
    if "year" in data:
        current_year = datetime.datetime.now().year
        if data["year"] < 2020 or data["year"] > current_year + 1:
            result.add_error(f"year={data['year']} seems invalid")
    
    # Check months_aggregated is valid
    if "months_aggregated" in data:
        if data["months_aggregated"] < 0:
            result.add_error("months_aggregated cannot be negative")
        if data["months_aggregated"] > 12:
            result.add_error(f"months_aggregated={data['months_aggregated']} exceeds 12")
        if data["months_aggregated"] == 0:
            result.add_warning("months_aggregated is 0 - empty aggregation")
    
    # Check speed values are reasonable
    for field in ["avg_download", "avg_upload"]:
        if field in data:
            err = validate_numeric_range(data[field], 0, 2000, field)
            if err:
                result.add_warning(err)


# ============================================================================
# BUCKET SCANNING
# ============================================================================

def list_aggregation_files(bucket: str, prefix: str = "aggregated/") -> List[str]:
    """List all aggregation files in a bucket."""
    paginator = s3.get_paginator("list_objects_v2")
    keys = []
    
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".json"):
                keys.append(key)
    
    return keys


def read_json_from_s3(bucket: str, key: str) -> Tuple[Optional[Dict], Optional[str]]:
    """Read and parse JSON from S3."""
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        data = json.loads(response["Body"].read())
        return data, None
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON: {e}"
    except Exception as e:
        return None, f"Error reading file: {e}"


def load_backfill_manifest() -> Optional[Dict]:
    """Load the backfill manifest from previous run."""
    if not os.path.exists(BACKFILL_MANIFEST_PATH):
        return None
    try:
        with open(BACKFILL_MANIFEST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"WARNING: Could not load manifest: {e}")
        return None


def verify_manifest_files(manifest: Dict, verbose: bool = False) -> Dict:
    """Verify only files listed in the backfill manifest."""
    print(f"\n{'='*60}")
    print(f"  Verifying PREVIOUS BACKFILL Files")
    print(f"  Manifest timestamp: {manifest.get('timestamp', 'unknown')}")
    print(f"  Files to verify: {manifest.get('files_created', 0)}")
    print(f"{'='*60}")
    
    files = manifest.get("files", [])
    if not files:
        print("  WARNING: No files in manifest!")
        return {"total": 0, "valid": 0, "invalid": 0, "warnings": 0}
    
    # Group files by type for appropriate validation
    validators = {
        "hourly": validate_hourly,
        "weekly": validate_weekly,
        "monthly": validate_monthly,
        "yearly": validate_yearly,
    }
    
    valid_count = 0
    invalid_count = 0
    warning_count = 0
    results_by_type = {}
    
    for file_info in files:
        bucket = file_info.get("bucket")
        key = file_info.get("key")
        file_type = file_info.get("type", "unknown")
        
        result = ValidationResult(f"s3://{bucket}/{key}")
        
        # Read and parse
        data, error = read_json_from_s3(bucket, key)
        if error:
            result.add_error(error)
        else:
            result.data = data
            validator = validators.get(file_type)
            if validator:
                validator(data, result)
            else:
                result.add_warning(f"Unknown file type: {file_type}")
        
        if file_type not in results_by_type:
            results_by_type[file_type] = {"valid": 0, "invalid": 0, "warnings": 0, "files": []}
        
        if result.valid:
            valid_count += 1
            results_by_type[file_type]["valid"] += 1
            if result.warnings:
                warning_count += 1
                results_by_type[file_type]["warnings"] += 1
        else:
            invalid_count += 1
            results_by_type[file_type]["invalid"] += 1
            results_by_type[file_type]["files"].append(result)
    
    # Print results by type
    print(f"\n  Results by type:")
    for file_type, stats in sorted(results_by_type.items()):
        print(f"    {file_type:10} - Valid: {stats['valid']:3}, Invalid: {stats['invalid']:2}, Warnings: {stats['warnings']:2}")
    
    print(f"\n  Overall:")
    print(f"    [OK]      Valid:    {valid_count}/{len(files)}")
    print(f"    [ERROR]   Invalid:  {invalid_count}/{len(files)}")
    print(f"    [WARN]    Warnings: {warning_count}/{len(files)}")
    
    # Show invalid files
    for file_type, stats in results_by_type.items():
        if stats["files"]:
            print(f"\n  Invalid {file_type} files:")
            for r in stats["files"][:5]:
                print(f"    [ERROR] {r.key}")
                for err in r.errors[:2]:
                    print(f"       - {err}")
    
    return {
        "total": len(files),
        "valid": valid_count,
        "invalid": invalid_count,
        "warnings": warning_count,
        "by_type": results_by_type,
    }


def verify_bucket(
    bucket: str,
    validator_func,
    level_name: str,
    sample_size: Optional[int] = None,
    verbose: bool = False
) -> Dict:
    """Verify all files in a bucket."""
    print(f"\n{'='*60}")
    print(f"  Verifying {level_name.upper()} Aggregations")
    print(f"  Bucket: {bucket}")
    print(f"{'='*60}")
    
    keys = list_aggregation_files(bucket)
    total_files = len(keys)
    
    if total_files == 0:
        print(f"  WARNING: No files found in bucket!")
        return {"total": 0, "valid": 0, "invalid": 0, "warnings": 0}
    
    # Sample if requested
    if sample_size and sample_size < total_files:
        keys = random.sample(keys, sample_size)
        print(f"  Sampling {sample_size} of {total_files} files")
    else:
        print(f"  Checking all {total_files} files")
    
    valid_count = 0
    invalid_count = 0
    warning_count = 0
    results: List[ValidationResult] = []
    
    for key in keys:
        result = ValidationResult(key)
        
        # Read and parse
        data, error = read_json_from_s3(bucket, key)
        if error:
            result.add_error(error)
        else:
            result.data = data
            validator_func(data, result)
        
        results.append(result)
        
        if result.valid:
            valid_count += 1
            if result.warnings:
                warning_count += 1
        else:
            invalid_count += 1
    
    # Print results
    print(f"\n  Results:")
    print(f"  [OK]      Valid:    {valid_count}/{len(keys)}")
    print(f"  [ERROR]   Invalid:  {invalid_count}/{len(keys)}")
    print(f"  [WARN]    Warnings: {warning_count}/{len(keys)}")
    
    # Show details for invalid files
    invalid_results = [r for r in results if not r.valid]
    if invalid_results:
        print(f"\n  Invalid files:")
        for r in invalid_results[:10]:  # Show first 10
            print(f"    [ERROR] {r.key}")
            for err in r.errors[:3]:  # Show first 3 errors
                print(f"       - {err}")
    
    # Show warnings if verbose
    if verbose:
        warning_results = [r for r in results if r.valid and r.warnings]
        if warning_results:
            print(f"\n  Files with warnings:")
            for r in warning_results[:10]:
                print(f"    [WARN] {r.key}")
                for warn in r.warnings[:2]:
                    print(f"       - {warn}")
    
    # Show sample valid data
    valid_results = [r for r in results if r.valid and r.data]
    if valid_results and verbose:
        sample = random.choice(valid_results)
        print(f"\n  Sample valid data from: {sample.key}")
        print(f"    {json.dumps(sample.data, indent=4)[:500]}...")
    
    return {
        "total": total_files,
        "checked": len(keys),
        "valid": valid_count,
        "invalid": invalid_count,
        "warnings": warning_count,
    }


# ============================================================================
# DATA FLOW VERIFICATION
# ============================================================================

def verify_data_flow(verbose: bool = False) -> Dict:
    """
    Verify that the data flows correctly between aggregation levels.
    
    Expected flow:
      Raw minute data → Hourly (hourly bucket)
      Raw minute data → Daily (main bucket)
      Daily → Weekly (weekly bucket)
      Daily → Monthly (monthly bucket)
      Monthly → Yearly (yearly bucket)
    """
    print(f"\n{'='*60}")
    print(f"  Verifying DATA FLOW Between Levels")
    print(f"{'='*60}")
    
    issues = []
    
    # 1. Check if daily summaries exist (source for weekly/monthly)
    daily_keys = list_aggregation_files(S3_BUCKET)
    daily_dates = set()
    for key in daily_keys:
        # Extract date from path like aggregated/year=2025/month=202510/day=20251022/...
        parts = key.split("/")
        for part in parts:
            if part.startswith("day="):
                daily_dates.add(part[4:])  # e.g., "20251022"
    
    print(f"\n  Daily summaries: {len(daily_dates)} unique dates")
    
    # 2. Check weekly aggregations cover the date range
    weekly_keys = list_aggregation_files(S3_BUCKET_WEEKLY)
    weekly_weeks = set()
    for key in weekly_keys:
        parts = key.split("/")
        for part in parts:
            if part.startswith("week="):
                weekly_weeks.add(part[5:])  # e.g., "2025W42"
    
    print(f"  Weekly summaries: {len(weekly_weeks)} weeks")
    
    # 3. Check monthly aggregations
    monthly_keys = list_aggregation_files(S3_BUCKET_MONTHLY)
    monthly_months = set()
    for key in monthly_keys:
        parts = key.split("/")
        for part in parts:
            if part.startswith("month="):
                monthly_months.add(part[6:])  # e.g., "202510"
    
    print(f"  Monthly summaries: {len(monthly_months)} months")
    
    # 4. Check yearly aggregations
    yearly_keys = list_aggregation_files(S3_BUCKET_YEARLY)
    yearly_years = set()
    for key in yearly_keys:
        parts = key.split("/")
        for part in parts:
            if part.startswith("year=") and len(part) == 9:  # year=2025
                yearly_years.add(part[5:])
    
    print(f"  Yearly summaries: {len(yearly_years)} years")
    
    # 5. Cross-check: monthly should exist for months with daily data
    daily_months = set()
    for date_str in daily_dates:
        if len(date_str) >= 6:
            daily_months.add(date_str[:6])  # YYYYMM
    
    missing_monthly = daily_months - monthly_months
    if missing_monthly:
        # Check if it's just the current month (expected to be missing)
        current_month = datetime.datetime.now(TIMEZONE).strftime("%Y%m")
        missing_monthly.discard(current_month)
        if missing_monthly:
            issues.append(f"Missing monthly aggregations for: {sorted(missing_monthly)}")
    
    # 6. Cross-check: yearly should exist for years with monthly data
    monthly_years = set()
    for month_str in monthly_months:
        if len(month_str) >= 4:
            monthly_years.add(month_str[:4])
    
    current_year = str(datetime.datetime.now(TIMEZONE).year)
    missing_yearly = monthly_years - yearly_years
    missing_yearly.discard(current_year)  # Current year may be incomplete
    if missing_yearly:
        issues.append(f"Missing yearly aggregations for: {sorted(missing_yearly)}")
    
    # Print summary
    if issues:
        print(f"\n  [WARN] Data flow issues detected:")
        for issue in issues:
            print(f"     - {issue}")
    else:
        print(f"\n  [OK] Data flow looks consistent!")
    
    return {
        "daily_dates": len(daily_dates),
        "weekly_weeks": len(weekly_weeks),
        "monthly_months": len(monthly_months),
        "yearly_years": len(yearly_years),
        "issues": issues,
    }


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Verify aggregation data integrity",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python verify_aggregations.py                    # Verify all buckets
  python verify_aggregations.py --hourly --weekly  # Verify specific levels
  python verify_aggregations.py --verbose          # Show detailed output
  python verify_aggregations.py --sample 10        # Check 10 random samples per bucket
  python verify_aggregations.py --flow             # Check data flow only
        """
    )
    
    parser.add_argument("--all", action="store_true", help="Verify all aggregation levels")
    parser.add_argument("--hourly", action="store_true", help="Verify hourly aggregations")
    parser.add_argument("--daily", action="store_true", help="Verify daily aggregations")
    parser.add_argument("--weekly", action="store_true", help="Verify weekly aggregations")
    parser.add_argument("--monthly", action="store_true", help="Verify monthly aggregations")
    parser.add_argument("--yearly", action="store_true", help="Verify yearly aggregations")
    parser.add_argument("--flow", action="store_true", help="Verify data flow between levels")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    parser.add_argument("--sample", type=int, help="Number of random samples to check per bucket")
    parser.add_argument("--previous", action="store_true", help="Verify only files from last backfill (reads backfill_manifest.json)")
    
    args = parser.parse_args()
    
    # Handle --previous flag
    if args.previous:
        manifest = load_backfill_manifest()
        if not manifest:
            print("ERROR: No backfill_manifest.json found!")
            print("       Run backfill_aggregations.py first to create a manifest.")
            return 1
        
        print("=" * 60)
        print("  AGGREGATION DATA VERIFICATION (Previous Backfill)")
        print("=" * 60)
        print(f"  Timestamp: {datetime.datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print(f"  Verbose: {args.verbose}")
        
        result = verify_manifest_files(manifest, verbose=args.verbose)
        
        print("\n" + "=" * 60)
        print("  VERIFICATION SUMMARY")
        print("=" * 60)
        print(f"  Previous backfill: {manifest.get('timestamp', 'unknown')}")
        print(f"  Files checked: {result['total']}")
        print(f"  Valid: {result['valid']}, Invalid: {result['invalid']}, Warnings: {result['warnings']}")
        
        if result['invalid'] == 0:
            print(f"\n  [OK] All backfilled files are valid!")
        else:
            print(f"\n  [ERROR] Found {result['invalid']} invalid files")
        
        print("=" * 60)
        return 0 if result['invalid'] == 0 else 1
    
    # If no flags specified, do everything
    if not any([args.all, args.hourly, args.daily, args.weekly, args.monthly, args.yearly, args.flow]):
        args.all = True
    
    if args.all:
        args.hourly = args.daily = args.weekly = args.monthly = args.yearly = args.flow = True
    
    print("=" * 60)
    print("  AGGREGATION DATA VERIFICATION")
    print("=" * 60)
    print(f"  Timestamp: {datetime.datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"  Sample size: {args.sample if args.sample else 'all files'}")
    print(f"  Verbose: {args.verbose}")
    
    results = {}
    
    if args.hourly:
        results["hourly"] = verify_bucket(
            S3_BUCKET_HOURLY, validate_hourly, "Hourly",
            sample_size=args.sample, verbose=args.verbose
        )
    
    if args.daily:
        results["daily"] = verify_bucket(
            S3_BUCKET, validate_daily, "Daily",
            sample_size=args.sample, verbose=args.verbose
        )
    
    if args.weekly:
        results["weekly"] = verify_bucket(
            S3_BUCKET_WEEKLY, validate_weekly, "Weekly",
            sample_size=args.sample, verbose=args.verbose
        )
    
    if args.monthly:
        results["monthly"] = verify_bucket(
            S3_BUCKET_MONTHLY, validate_monthly, "Monthly",
            sample_size=args.sample, verbose=args.verbose
        )
    
    if args.yearly:
        results["yearly"] = verify_bucket(
            S3_BUCKET_YEARLY, validate_yearly, "Yearly",
            sample_size=args.sample, verbose=args.verbose
        )
    
    if args.flow:
        results["flow"] = verify_data_flow(verbose=args.verbose)
    
    # Final summary
    print("\n" + "=" * 60)
    print("  VERIFICATION SUMMARY")
    print("=" * 60)
    
    total_valid = 0
    total_invalid = 0
    total_warnings = 0
    
    for level, stats in results.items():
        if level == "flow":
            continue
        total_valid += stats.get("valid", 0)
        total_invalid += stats.get("invalid", 0)
        total_warnings += stats.get("warnings", 0)
        print(f"  {level.capitalize():10} - Valid: {stats.get('valid', 0):4}, Invalid: {stats.get('invalid', 0):2}, Warnings: {stats.get('warnings', 0):2}")
    
    print(f"  {'-'*50}")
    print(f"  {'TOTAL':10} - Valid: {total_valid:4}, Invalid: {total_invalid:2}, Warnings: {total_warnings:2}")
    
    if total_invalid == 0:
        print(f"\n  [OK] All aggregations are valid!")
    else:
        print(f"\n  [ERROR] Found {total_invalid} invalid aggregation files")
    
    print("=" * 60)
    
    return 0 if total_invalid == 0 else 1


if __name__ == "__main__":
    exit(main())
