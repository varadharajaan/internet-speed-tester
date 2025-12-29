# Aggregation Backfill & Verification Guide

## Overview

This document explains the data aggregation pipeline, the correct order for backfilling, and how to verify data integrity.

## Quick Start

```powershell
# Run backfill (creates files and saves manifest)
python backfill_aggregations.py --weekly --monthly

# Verify ONLY the files you just created
python verify_aggregations.py --previous

# Verify ALL files in all buckets
python verify_aggregations.py
```

## Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         RAW DATA (vd-speed-test bucket)                      │
│                     Every 15 minutes: speed test results                      │
│                     Path: year=YYYY/month=YYYYMM/day=YYYYMMDD/*.json          │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
┌───────────────────────────────┐   ┌───────────────────────────────────────┐
│  HOURLY AGGREGATIONS           │   │  DAILY AGGREGATIONS                    │
│  Bucket: vd-speed-test-hourly  │   │  Bucket: vd-speed-test/aggregated/     │
│  Source: Raw minute data       │   │  Source: Raw minute data               │
│  4 records per hour max        │   │  96 records per day max                │
└───────────────────────────────┘   └───────────────────┬───────────────────┘
                                                        │
                    ┌───────────────────────────────────┼───────────────────┐
                    │                                   │                   │
                    ▼                                   ▼                   │
┌───────────────────────────────┐   ┌───────────────────────────────┐       │
│  WEEKLY AGGREGATIONS           │   │  MONTHLY AGGREGATIONS          │       │
│  Bucket: vd-speed-test-weekly  │   │  Bucket: vd-speed-test-monthly │       │
│  Source: Daily summaries       │   │  Source: Daily summaries       │       │
│  7 days per week max           │   │  31 days per month max         │       │
└───────────────────────────────┘   └───────────────────┬───────────────────┘
                                                        │
                                                        ▼
                                    ┌───────────────────────────────────────┐
                                    │  YEARLY AGGREGATIONS                   │
                                    │  Bucket: vd-speed-test-yearly          │
                                    │  Source: Monthly summaries             │
                                    │  12 months per year max                │
                                    └───────────────────────────────────────┘
```

## Correct Backfill Order

**IMPORTANT**: The backfill script must process levels in dependency order!

### Order of Operations:

1. **Hourly** - Aggregates raw minute data -> hourly summaries
   - Source: Raw JSON files in `vd-speed-test` bucket
   - Output: `vd-speed-test-hourly-prod` bucket
   - Independent of other aggregations

2. **Daily** - Already exists from regular Lambda runs
   - Source: Raw JSON files in `vd-speed-test` bucket  
   - Output: `vd-speed-test/aggregated/` (same bucket, different prefix)
   - **Note**: `backfill_aggregations.py` does NOT backfill daily - assumes it exists!

3. **Weekly** - Requires daily summaries first!
   - Source: Daily summaries from `vd-speed-test/aggregated/`
   - Output: `vd-speed-test-weekly-prod` bucket

4. **Monthly** - Requires daily summaries first!
   - Source: Daily summaries from `vd-speed-test/aggregated/`
   - Output: `vd-speed-test-monthly-prod` bucket

5. **Yearly** - Requires monthly summaries first!
   - Source: Monthly summaries from `vd-speed-test-monthly-prod`
   - Output: `vd-speed-test-yearly-prod` bucket

### Backfill Output

When backfill runs, it creates a `backfill_manifest.json` file containing:
- Timestamp of the backfill
- List of all files created (bucket, key, type)
- Total file count

This manifest is used by `verify_aggregations.py --previous` to verify only the newly created files.

### Recommended Backfill Command:

```powershell
# If daily summaries already exist (normal case):
python backfill_aggregations.py --all

# To backfill individual levels in order:
python backfill_aggregations.py --hourly        # Step 1: Raw -> Hourly
# (Daily should already exist from Lambda)
python backfill_aggregations.py --weekly        # Step 2: Daily -> Weekly  
python backfill_aggregations.py --monthly       # Step 3: Daily -> Monthly
python backfill_aggregations.py --yearly        # Step 4: Monthly -> Yearly

# Include current incomplete periods:
python backfill_aggregations.py --all --force
```

## Verification Script

### Basic Usage:

```powershell
# Verify ONLY files from the last backfill (reads backfill_manifest.json)
python verify_aggregations.py --previous

# Verify all aggregations in all buckets
python verify_aggregations.py

# Verify specific levels
python verify_aggregations.py --hourly
python verify_aggregations.py --daily --weekly
python verify_aggregations.py --monthly --yearly

# Check data flow consistency only
python verify_aggregations.py --flow

# Verbose output with sample data
python verify_aggregations.py --verbose

# Quick spot check with random samples
python verify_aggregations.py --sample 10
```

### Verification Modes:

| Flag | Description |
|------|-------------|
| `--previous` | Verify only files from last backfill (uses `backfill_manifest.json`) |
| `--all` | Verify all files in all buckets (default if no flags) |
| `--hourly` | Verify hourly bucket only |
| `--daily` | Verify daily summaries only |
| `--weekly` | Verify weekly bucket only |
| `--monthly` | Verify monthly bucket only |
| `--yearly` | Verify yearly bucket only |
| `--flow` | Check data flow consistency |
| `--sample N` | Random sample N files per bucket |
| `--verbose` | Show detailed output |

### What It Checks:

| Level   | Validations                                                    |
|---------|----------------------------------------------------------------|
| Hourly  | Required fields, overall stats structure, records ≤ 4/hour    |
| Daily   | Date format, records ≤ 96/day, completion rate 0-100%          |
| Weekly  | Date formats, days ≤ 7, speed values reasonable                |
| Monthly | Month format (YYYYMM), days ≤ 31                               |
| Yearly  | Year valid, months_aggregated ≤ 12                             |
| Flow    | Cross-checks that higher levels have data for lower levels     |

### Example Output:

```
============================================================
  AGGREGATION DATA VERIFICATION
============================================================
  Timestamp: 2025-12-29 15:30:00 IST
  Sample size: all files
  Verbose: False

============================================================
  Verifying HOURLY Aggregations
  Bucket: vd-speed-test-hourly-prod
============================================================
  Checking all 347 files

  Results:
  ✅ Valid:    347/347
  ❌ Invalid:  0/347
  ⚠️  Warnings: 12/347

============================================================
  Verifying DATA FLOW Between Levels
============================================================

  Daily summaries: 45 unique dates
  Weekly summaries: 8 weeks
  Monthly summaries: 3 months
  Yearly summaries: 1 years

  ✅ Data flow looks consistent!

============================================================
  VERIFICATION SUMMARY
============================================================
  Hourly     - Valid:  347, Invalid:  0, Warnings: 12
  Daily      - Valid:   45, Invalid:  0, Warnings:  3
  Weekly     - Valid:    8, Invalid:  0, Warnings:  0
  Monthly    - Valid:    3, Invalid:  0, Warnings:  0
  Yearly     - Valid:    1, Invalid:  0, Warnings:  0
  --------------------------------------------------
  TOTAL      - Valid:  404, Invalid:  0, Warnings: 15

  ✅ All aggregations are valid!
============================================================
```

## Troubleshooting

### Issue: Weekly/Monthly/Yearly backfill shows 0 files created

**Cause**: Daily summaries don't exist yet.

**Solution**: 
1. Check if daily summaries exist:
   ```powershell
   aws s3 ls s3://vd-speed-test/aggregated/ --recursive | Select-Object -First 5
   ```
2. If empty, trigger daily aggregation first via Lambda or `daily_aggregator_local.py`

### Issue: "Missing monthly aggregations for..." warning

**Cause**: Some months with daily data don't have monthly rollups.

**Solution**:
```powershell
python backfill_aggregations.py --monthly --force
```

### Issue: Validation shows "records exceeds expected" warnings

**Cause**: Multiple hosts or more frequent testing.

**Note**: This is a warning, not an error. The data is still valid.

## S3 Bucket Structure

```
vd-speed-test/                              # Main bucket
├── year=2025/month=202512/day=20251229/   # Raw minute data
│   └── speedtest_20251229_143000.json
└── aggregated/                             # Daily summaries
    └── year=2025/month=202512/day=20251229/
        └── speed_test_summary.json

vd-speed-test-hourly-prod/                  # Hourly bucket
└── aggregated/
    └── year=2025/month=202512/day=20251229/hour=14/
        └── speed_test_summary.json

vd-speed-test-weekly-prod/                  # Weekly bucket
└── aggregated/
    └── year=2025/week=2025W52/
        └── speed_test_summary.json

vd-speed-test-monthly-prod/                 # Monthly bucket
└── aggregated/
    └── year=2025/month=202512/
        └── speed_test_summary.json

vd-speed-test-yearly-prod/                  # Yearly bucket
└── aggregated/
    └── year=2025/
        └── speed_test_summary.json
```

## Expected File Counts

| Level   | Formula                                           | Example (Oct-Dec 2025)  |
|---------|---------------------------------------------------|-------------------------|
| Hourly  | Days × 24 hours × completion rate                 | ~347 files              |
| Daily   | Number of days with data                          | ~45 files               |
| Weekly  | Number of ISO weeks with data                     | ~8 files (W42-W49)      |
| Monthly | Number of months with data                        | 3 files (Oct, Nov, Dec) |
| Yearly  | Number of years with data                         | 1 file (2025)           |
