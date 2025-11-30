#!/usr/bin/env python3
import json, datetime, pytz
from lambda_function import aggregate_for_date, upload_summary, TIMEZONE, S3_BUCKET, S3_BUCKET_HOURLY, S3_BUCKET_WEEKLY, S3_BUCKET_MONTHLY, S3_BUCKET_YEARLY

def main():
    now_ist = datetime.datetime.now(TIMEZONE)
    target_date = (now_ist - datetime.timedelta(days=1)).date()
    target_dt = datetime.datetime.combine(target_date, datetime.time.min).replace(tzinfo=TIMEZONE)
    print(f"[LOCAL] Aggregating for {target_dt.strftime('%Y-%m-%d')} IST")
    print(f"  Daily bucket:   {S3_BUCKET}")
    print(f"  Hourly bucket:  {S3_BUCKET_HOURLY}")
    print(f"  Weekly bucket:  {S3_BUCKET_WEEKLY}")
    print(f"  Monthly bucket: {S3_BUCKET_MONTHLY}")
    print(f"  Yearly bucket:  {S3_BUCKET_YEARLY}")
    summary = aggregate_for_date(target_dt)
    if not summary:
        print("No records found."); return
    key = upload_summary(summary, target_dt)
    print(json.dumps({"uploaded": key, "records": summary["records"], "public_ips": summary.get("public_ips", []), "urls": len(summary.get("result_urls", []))}, indent=2))
    print(f"Uploaded to s3://{S3_BUCKET}/{key}")

if __name__ == "__main__":
    main()
