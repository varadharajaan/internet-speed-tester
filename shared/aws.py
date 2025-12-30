"""
AWS client factories and helpers.

Provides:
- Singleton S3 and CloudWatch Logs clients
- Common S3 operations (list hosts, list files)
- Thread-safe client access

Usage:
    from shared import get_s3_client, list_hosts
    s3 = get_s3_client()
    hosts = list_hosts()
"""
import boto3
from botocore.config import Config as BotoConfig
from functools import lru_cache
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import get_config
from .logging import get_logger

log = get_logger(__name__)


@lru_cache(maxsize=1)
def get_s3_client():
    """
    Get a singleton S3 client with retry configuration.
    
    Uses adaptive retry mode for better resilience.
    """
    config = get_config()
    boto_config = BotoConfig(
        retries={"max_attempts": 3, "mode": "adaptive"},
        connect_timeout=5,
        read_timeout=30,
    )
    return boto3.client("s3", region_name=config.aws_region, config=boto_config)


@lru_cache(maxsize=1)
def get_logs_client():
    """
    Get a singleton CloudWatch Logs client.
    """
    config = get_config()
    return boto3.client("logs", region_name=config.aws_region)


def list_hosts(bucket: Optional[str] = None) -> List[str]:
    """
    Discover all hosts that have uploaded data.
    
    Scans S3 bucket for host= prefixes and also handles
    legacy data (no host prefix) as "_legacy".
    
    Returns:
        List of host IDs (e.g., ["_legacy", "home-primary", "office-main"])
    """
    config = get_config()
    s3 = get_s3_client()
    bucket = bucket or config.s3_bucket
    
    hosts = set()
    
    try:
        # Check for host= prefixed folders
        response = s3.list_objects_v2(
            Bucket=bucket,
            Prefix="host=",
            Delimiter="/",
        )
        for prefix in response.get("CommonPrefixes", []):
            # Extract host ID from "host=xxx/"
            host_prefix = prefix["Prefix"]
            if host_prefix.startswith("host=") and host_prefix.endswith("/"):
                host_id = host_prefix[5:-1]  # Remove "host=" and trailing "/"
                hosts.add(host_id)
        
        # Check for legacy data (year= at root level, no host prefix)
        legacy_response = s3.list_objects_v2(
            Bucket=bucket,
            Prefix="year=",
            Delimiter="/",
            MaxKeys=1,
        )
        if legacy_response.get("CommonPrefixes"):
            hosts.add("_legacy")
        
    except Exception as e:
        log.error(f"Error listing hosts: {e}")
    
    return sorted(hosts)


def list_aggregation_files(
    period: str,
    bucket: Optional[str] = None,
    host: Optional[str] = None,
) -> List[dict]:
    """
    List aggregation files for a given period.
    
    Args:
        period: "daily", "weekly", "monthly", "yearly", "hourly"
        bucket: Override bucket name
        host: Filter by host ID (None = all, "_legacy" = no host prefix)
    
    Returns:
        List of S3 object metadata dicts
    """
    config = get_config()
    s3 = get_s3_client()
    bucket = bucket or config.get_bucket(period)
    
    # Build prefix based on host filter
    if host == "_legacy" or host is None:
        prefix = "aggregated/"
    else:
        prefix = f"aggregated/host={host}/"
    
    files = []
    paginator = s3.get_paginator("list_objects_v2")
    
    try:
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                # Filter for summary files
                if key.endswith(".json") and "summary" in key.lower():
                    files.append({
                        "Key": key,
                        "LastModified": obj["LastModified"],
                        "Size": obj["Size"],
                    })
    except Exception as e:
        log.error(f"Error listing {period} files: {e}")
    
    return files


def get_json_from_s3(bucket: str, key: str) -> Optional[dict]:
    """
    Fetch and parse a JSON file from S3.
    
    Returns None if file doesn't exist or is invalid JSON.
    """
    s3 = get_s3_client()
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        return __import__("json").loads(response["Body"].read().decode("utf-8"))
    except s3.exceptions.NoSuchKey:
        return None
    except Exception as e:
        log.error(f"Error fetching s3://{bucket}/{key}: {e}")
        return None


def parallel_fetch_json(
    bucket: str,
    keys: List[str],
    max_workers: int = 20,
) -> List[dict]:
    """
    Fetch multiple JSON files from S3 in parallel.
    
    Args:
        bucket: S3 bucket name
        keys: List of S3 keys to fetch
        max_workers: Thread pool size
    
    Returns:
        List of parsed JSON objects (excludes failures)
    """
    results = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_key = {
            executor.submit(get_json_from_s3, bucket, key): key
            for key in keys
        }
        
        for future in as_completed(future_to_key):
            data = future.result()
            if data is not None:
                results.append(data)
    
    return results


def delete_s3_objects(bucket: str, keys: List[str], dry_run: bool = True) -> int:
    """
    Delete multiple S3 objects.
    
    Args:
        bucket: S3 bucket name
        keys: List of S3 keys to delete
        dry_run: If True, only log what would be deleted
    
    Returns:
        Number of objects deleted (or would be deleted in dry_run)
    """
    if not keys:
        return 0
    
    s3 = get_s3_client()
    count = len(keys)
    
    if dry_run:
        log.info(f"[DRY RUN] Would delete {count} objects from {bucket}")
        return count
    
    # S3 delete_objects accepts max 1000 keys per call
    deleted = 0
    for i in range(0, len(keys), 1000):
        batch = keys[i:i + 1000]
        try:
            s3.delete_objects(
                Bucket=bucket,
                Delete={"Objects": [{"Key": k} for k in batch]},
            )
            deleted += len(batch)
        except Exception as e:
            log.error(f"Error deleting batch: {e}")
    
    log.info(f"Deleted {deleted} objects from {bucket}")
    return deleted
