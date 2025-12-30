#!/usr/bin/env python3
"""
Weekly Aggregator - Local Runner
---------------------------------
Aggregates daily summaries into weekly summaries and uploads to S3_BUCKET_WEEKLY.
"""
import json
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lambda_function import aggregate_weekly, S3_BUCKET_WEEKLY

def main():
    print("Running weekly aggregation...")
    print(f"  Target bucket: {S3_BUCKET_WEEKLY}")
    
    result = aggregate_weekly()
    
    if not result:
        print("ERROR: No weekly aggregation performed (no data or incomplete week)")
        return
    
    print("\nWeekly aggregation completed successfully!")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
