#!/usr/bin/env python3
"""
vd-speed-test dashboard
-----------------------
Flask web app to visualize internet speed statistics from S3.
Now includes CloudWatch-compatible JSON logging and local file rotation.

Refactored to use shared/ modules for:
- Configuration (shared/config.py)
- Logging (shared/logging.py)
- AWS clients (shared/aws.py)
- Constants (shared/constants.py)
"""

from flask import Flask, render_template, request, jsonify
import boto3, json, pandas as pd, re
from botocore.config import Config as BotoConfig
import pytz, datetime, os, sys
from functools import wraps
import time
from threading import Lock
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import from shared modules
from shared import get_config, get_logger, get_s3_client
from shared.constants import CACHE_TTL, MAX_CHART_POINTS

# Get configuration and logger
config = get_config()
log = get_logger(__name__)

# --- In-Memory Cache with TTL and Disk Persistence ------------------------------
import pickle
import hashlib

# Use /tmp for Lambda (read-only filesystem), local .cache for development
IS_LAMBDA = os.environ.get("AWS_LAMBDA_FUNCTION_NAME") is not None
CACHE_DIR = "/tmp/.cache" if IS_LAMBDA else os.path.join(os.path.dirname(__file__), ".cache")

class DataCache:
    """In-memory cache with TTL support, manual invalidation, and disk persistence."""
    def __init__(self, default_ttl=120, persist_dir=CACHE_DIR):
        self._cache = {}  # {key: (data, expiry, source)} where source = 'disk' or 'memory'
        self._lock = Lock()
        self.default_ttl = default_ttl
        self.persist_dir = persist_dir
        self._disk_loaded_keys = set()  # Track which keys were loaded from disk
        
        # Create cache directory if it doesn't exist
        if self.persist_dir:
            os.makedirs(self.persist_dir, exist_ok=True)
            self._load_persisted_cache()
    
    def _get_cache_file(self, key):
        """Get the file path for a cache key."""
        # Use hash to create safe filenames
        safe_key = hashlib.md5(key.encode()).hexdigest()
        return os.path.join(self.persist_dir, f"{safe_key}.pkl")
    
    def _load_persisted_cache(self):
        """Load persisted cache entries on startup."""
        if not self.persist_dir or not os.path.exists(self.persist_dir):
            return
        
        loaded = 0
        expired = 0
        for filename in os.listdir(self.persist_dir):
            if filename.endswith('.pkl'):
                filepath = os.path.join(self.persist_dir, filename)
                try:
                    with open(filepath, 'rb') as f:
                        cache_entry = pickle.load(f)
                    key = cache_entry.get('key')
                    data = cache_entry.get('data')
                    expiry = cache_entry.get('expiry', 0)
                    
                    if key and time.time() < expiry:
                        self._cache[key] = (data, expiry)
                        self._disk_loaded_keys.add(key)
                        loaded += 1
                    else:
                        # Expired, delete the file
                        os.remove(filepath)
                        expired += 1
                except Exception:
                    # Corrupted file, remove it
                    try:
                        os.remove(filepath)
                    except:
                        pass
        
        if loaded > 0 or expired > 0:
            print(f"[CACHE STARTUP] Restored {loaded} entries from disk" + (f", purged {expired} expired" if expired else ""))
    
    def get(self, key, return_source=False):
        """Get cached value if not expired. If return_source=True, returns (data, source)."""
        with self._lock:
            if key in self._cache:
                data, expiry = self._cache[key]
                if time.time() < expiry:
                    source = 'disk' if key in self._disk_loaded_keys else 'memory'
                    if return_source:
                        return data, source
                    return data
                del self._cache[key]
                self._disk_loaded_keys.discard(key)
                # Also remove from disk
                self._delete_from_disk(key)
        return (None, None) if return_source else None
    
    def set(self, key, value, ttl=None, persist=True):
        """Cache a value with TTL. persist=True saves to disk for long-TTL items."""
        ttl = ttl or self.default_ttl
        expiry = time.time() + ttl
        with self._lock:
            self._cache[key] = (value, expiry)
        
        # Persist to disk only for longer-lived cache entries (TTL > 5 min)
        if persist and self.persist_dir and ttl >= 300:
            self._save_to_disk(key, value, expiry)
    
    def _save_to_disk(self, key, data, expiry):
        """Save cache entry to disk."""
        try:
            filepath = self._get_cache_file(key)
            with open(filepath, 'wb') as f:
                pickle.dump({'key': key, 'data': data, 'expiry': expiry}, f)
        except Exception:
            pass  # Disk save failure is not critical
    
    def _delete_from_disk(self, key):
        """Delete cache entry from disk."""
        try:
            filepath = self._get_cache_file(key)
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception:
            pass
    
    def invalidate(self, key=None):
        """Invalidate specific key or all keys."""
        with self._lock:
            if key:
                self._cache.pop(key, None)
                self._delete_from_disk(key)
            else:
                self._cache.clear()
                # Clear all persisted cache files
                if self.persist_dir and os.path.exists(self.persist_dir):
                    for f in os.listdir(self.persist_dir):
                        if f.endswith('.pkl'):
                            try:
                                os.remove(os.path.join(self.persist_dir, f))
                            except:
                                pass
    
    def get_stats(self):
        """Get cache statistics."""
        with self._lock:
            valid_count = sum(1 for _, (_, exp) in self._cache.items() if time.time() < exp)
            disk_count = 0
            if self.persist_dir and os.path.exists(self.persist_dir):
                disk_count = len([f for f in os.listdir(self.persist_dir) if f.endswith('.pkl')])
            return {"cached_items": valid_count, "total_keys": len(self._cache), "disk_files": disk_count}

# Global cache instance (2 minute TTL - balances freshness vs performance)
data_cache = DataCache(default_ttl=120)


# --- Chart Data Downsampling (Smart Sampling) -----------------------------------
def downsample_chart_data(chart_data: dict, max_points: int = 200) -> dict:
    """
    Smart downsampling that:
    1. Removes consecutive near-duplicate values (within tolerance)
    2. Applies LTTB (Largest Triangle Three Buckets) to preserve visual shape
    
    Args:
        chart_data: Dict with timestamps, download, upload, ping, connection_types
        max_points: Maximum number of points to keep (default 200)
    
    Returns:
        Downsampled chart_data dict
    """
    timestamps = chart_data.get("timestamps", [])
    download = chart_data.get("download", [])
    upload = chart_data.get("upload", [])
    ping = chart_data.get("ping", [])
    connection_types = chart_data.get("connection_types", [])
    
    n = len(timestamps)
    
    # No downsampling needed if already under limit
    if n <= max_points:
        return chart_data
    
    # Step 1: Remove consecutive near-duplicates (keep significant changes only)
    # A point is "significant" if it differs from the previous kept point by > tolerance%
    def remove_near_duplicates(indices, values, tolerance_pct=5):
        """Keep only points that show significant change from previous kept point."""
        if len(indices) <= 2:
            return indices
        
        kept = [indices[0]]  # Always keep first
        last_kept_idx = indices[0]
        last_kept_val = values[last_kept_idx] if last_kept_idx < len(values) else 0
        
        for i in range(1, len(indices) - 1):
            idx = indices[i]
            val = values[idx] if idx < len(values) else 0
            
            # Calculate percent change from last kept value
            if last_kept_val != 0:
                pct_change = abs(val - last_kept_val) / last_kept_val * 100
            else:
                pct_change = 100 if val != 0 else 0
            
            # Keep if significant change OR if we've skipped too many points
            points_since_last = idx - last_kept_idx
            if pct_change > tolerance_pct or points_since_last > 20:
                kept.append(idx)
                last_kept_idx = idx
                last_kept_val = val
        
        kept.append(indices[-1])  # Always keep last
        return kept
    
    # Step 2: LTTB algorithm for remaining points
    def lttb_indices(values, target_points):
        """Get indices to keep using LTTB algorithm."""
        n = len(values)
        if n <= target_points:
            return list(range(n))
        
        bucket_size = (n - 2) / (target_points - 2)
        indices = [0]
        a = 0
        
        for i in range(target_points - 2):
            bucket_start = int((i + 1) * bucket_size) + 1
            bucket_end = min(int((i + 2) * bucket_size) + 1, n - 1)
            
            next_bucket_start = bucket_end
            next_bucket_end = min(int((i + 3) * bucket_size) + 1, n)
            
            if next_bucket_start < next_bucket_end:
                avg_y = sum(values[next_bucket_start:next_bucket_end]) / (next_bucket_end - next_bucket_start)
            else:
                avg_y = values[next_bucket_start] if next_bucket_start < n else 0
            
            max_area = -1
            max_idx = bucket_start
            
            for j in range(bucket_start, bucket_end):
                # Simplified triangle area using just y-values difference
                area = abs((values[j] - values[a]) + (values[j] - avg_y))
                if area > max_area:
                    max_area = area
                    max_idx = j
            
            indices.append(max_idx)
            a = max_idx
        
        indices.append(n - 1)
        return indices
    
    # Apply LTTB first to get candidate indices
    intermediate_points = min(max_points * 3, n)  # Get 3x target initially
    candidate_indices = lttb_indices(download, intermediate_points)
    
    # Apply near-duplicate removal
    final_indices = remove_near_duplicates(candidate_indices, download, tolerance_pct=3)
    
    # If still too many, apply LTTB again on the filtered data
    if len(final_indices) > max_points:
        # Re-map to final selection
        filtered_download = [download[i] for i in final_indices]
        second_pass = lttb_indices(filtered_download, max_points)
        final_indices = [final_indices[i] for i in second_pass]
    
    # Build result
    return {
        "timestamps": [timestamps[i] for i in final_indices],
        "download": [download[i] for i in final_indices],
        "upload": [upload[i] for i in final_indices] if upload else [],
        "ping": [ping[i] for i in final_indices] if ping else [],
        "connection_types": [connection_types[i] for i in final_indices] if connection_types else [],
        "downsampled": True,
        "original_count": n,
        "sampled_count": len(final_indices)
    }


# --- Configuration (using shared/config.py) -----------------------------------
# Config and log are imported from shared modules at the top
# These variables are kept for backward compatibility with existing code
S3_BUCKET = config.s3_bucket
S3_BUCKET_HOURLY = config.s3_bucket_hourly
S3_BUCKET_WEEKLY = config.s3_bucket_weekly
S3_BUCKET_MONTHLY = config.s3_bucket_monthly
S3_BUCKET_YEARLY = config.s3_bucket_yearly
AWS_REGION = config.aws_region
TIMEZONE = pytz.timezone(config.timezone)
DEFAULT_THRESHOLD = float(config.expected_speed_mbps)
TOLERANCE_PERCENT = float(config.tolerance_percent)

app = Flask(__name__)

# Use shared S3 client
s3 = get_s3_client()

# --- Multi-host support -------------------------------------------------------
def list_hosts():
    """
    Discover all unique host IDs from the S3 bucket by scanning top-level prefixes.
    Returns a list of host_id strings (e.g., ['home-primary', 'office-backup']).
    Also checks for legacy data without host prefix.
    """
    cache_key = "hosts_list"
    cached = data_cache.get(cache_key)
    if cached:
        return cached
    
    hosts = set()
    
    # Check for host= prefixes (new format)
    try:
        result = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix="host=", Delimiter="/")
        for prefix in result.get("CommonPrefixes", []):
            host_prefix = prefix["Prefix"]
            if host_prefix.startswith("host=") and host_prefix.endswith("/"):
                host_id = host_prefix[5:-1]
                hosts.add(host_id)
    except Exception as e:
        log.warning(f"Error listing host prefixes: {e}")
    
    # Check for legacy data (year= prefix without host)
    try:
        result = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix="year=", Delimiter="/", MaxKeys=1)
        if result.get("CommonPrefixes") or result.get("Contents"):
            hosts.add("_legacy")
    except Exception as e:
        log.warning(f"Error checking legacy data: {e}")
    
    hosts_list = sorted(hosts)
    data_cache.set(cache_key, hosts_list, ttl=300)  # Cache for 5 minutes
    log.info(f"Discovered hosts: {hosts_list}")
    return hosts_list

def get_host_prefix(host_id):
    """Get the S3 prefix for a host. Legacy data has no host prefix."""
    if not host_id or host_id == "all" or host_id == "_legacy":
        return ""
    return f"host={host_id}/"


# --- Decorator for Logging (using shared/logging.py) -------------------------
from shared.logging import log_execution

# --- S3 Utility Functions -----------------------------------------------------
@log_execution
def list_summary_files(host_id=None):
    """List daily summary files, optionally filtered by host.
    
    host_id options:
    - None or "all": Include all files (global + host-specific), dedupe by date preferring global
    - "_legacy": Only legacy files (no host= prefix)
    - specific host: Only that host's files
    """
    paginator = s3.get_paginator("list_objects_v2")
    files = []
    files_by_date = {}  # For deduplication: {date: (key, is_global)}
    
    if host_id and host_id not in ("all", "_legacy"):
        # Specific host: only that host's files
        prefix = f"aggregated/host={host_id}/"
        for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith(".json") and "/day=" in key:
                    files.append(key)
    elif host_id == "_legacy":
        # Legacy only: files without host= prefix
        prefix = "aggregated/"
        for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith(".json") and "/day=" in key and "host=" not in key:
                    files.append(key)
    else:
        # All hosts (global view): include everything, dedupe by date
        # Prefer global files over host-specific when both exist for same date
        prefix = "aggregated/"
        for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith(".json") and "/day=" in key:
                    # Extract date from key (day=YYYYMMDD)
                    match = re.search(r'day=(\d{8})', key)
                    if match:
                        date_str = match.group(1)
                        is_global = "host=" not in key
                        
                        if date_str not in files_by_date:
                            files_by_date[date_str] = (key, is_global)
                        elif is_global and not files_by_date[date_str][1]:
                            # Prefer global over host-specific
                            files_by_date[date_str] = (key, is_global)
                        # If current is host-specific and we already have global, keep global
        
        files = [item[0] for item in files_by_date.values()]
    
    log.info(f"Found {len(files)} summary files" + (f" for host={host_id}" if host_id else " (all hosts)"))
    return files

@log_execution
def load_summaries(host_id=None):
    """Load daily summaries using parallel S3 fetches for speed."""
    keys = list_summary_files(host_id)
    if not keys:
        return pd.DataFrame(columns=["date_ist"])
    
    def fetch_one(key):
        """Fetch a single S3 object."""
        try:
            obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
            return json.loads(obj["Body"].read().decode("utf-8"))
        except Exception as e:
            log.warning(f"Failed to fetch {key}: {e}")
            return None
    
    # Parallel fetch with up to 20 threads (reduced to avoid connection drops)
    recs = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(fetch_one, key): key for key in keys}
        for future in as_completed(futures):
            result = future.result()
            if result:
                recs.append(result)
    
    if not recs:
        return pd.DataFrame(columns=["date_ist"])
    
    df = pd.DataFrame(recs)
    df["date_ist"] = pd.to_datetime(df["date_ist"], errors="coerce")
    df["date_ist_str"] = df["date_ist"].dt.strftime("%Y-%m-%d")

    # Extract stats
    df["download_avg"] = df["overall"].apply(lambda x: x.get("download_mbps", {}).get("avg") if isinstance(x, dict) else None)
    df["upload_avg"] = df["overall"].apply(lambda x: x.get("upload_mbps", {}).get("avg") if isinstance(x, dict) else None)
    df["ping_avg"] = df["overall"].apply(lambda x: x.get("ping_ms", {}).get("avg") if isinstance(x, dict) else None)
    df["top_server"] = df["servers_top"].apply(lambda arr: arr[0] if isinstance(arr, list) and arr else "")
    df["result_urls"] = df["result_urls"].apply(lambda x: x if isinstance(x, list) else [])
    df["connection_type"] = df.get("connection_types", pd.Series([[] for _ in range(len(df))])).apply(
        lambda x: ", ".join(x) if isinstance(x, list) and x else "Unknown"
    )
    
    # Add host info
    if "host_id" not in df.columns:
        df["host_id"] = "_legacy"

    if "public_ips" in df.columns:
        df["public_ips"] = df["public_ips"].apply(lambda x: x if isinstance(x, list) else [])
        df["public_ip"] = df["public_ips"].apply(lambda x: x[0] if x else "")
    elif "public_ip" in df.columns:
        df["public_ips"] = df["public_ip"].apply(lambda x: [x] if isinstance(x, str) and x else [])
    else:
        df["public_ips"] = [[] for _ in range(len(df))]
        df["public_ip"] = ""

    log.info(f"Loaded {len(df)} daily summaries from S3" + (f" for host={host_id}" if host_id else ""))
    return df.sort_values("date_ist")

@log_execution
def load_minute_data(days, host_id=None, force_reload=False):
    """Load minute-level data with smart caching.
    
    - Historical days (before today): cached for 1 hour
    - Today's data older than 15 min: cached for 15 minutes (won't change)
    - Today's data from last 15 min: fetched fresh
    - force_reload=True: clears all caches and fetches everything fresh
    """
    now = datetime.datetime.now(TIMEZONE)
    today = now.date()
    cutoff = now - datetime.timedelta(days=days)
    recent_cutoff = now - datetime.timedelta(minutes=15)  # Data older than 15 min is "past"
    paginator = s3.get_paginator("list_objects_v2")
    
    # Determine which hosts to query
    if host_id and host_id != "all":
        # Single host mode
        hosts_to_query = [host_id]
        host_key = host_id
    else:
        # All hosts mode - query all discovered hosts
        discovered_hosts = list_hosts()
        hosts_to_query = discovered_hosts if discovered_hosts else ["_legacy"]
        host_key = "_all"
    
    # Force reload: clear all minute caches for this host
    if force_reload:
        log.info(f"[FORCE RELOAD] Clearing all minute caches for host={host_key}")
        # Clear day-level caches
        current_date = cutoff.date()
        while current_date <= today:
            date_str = current_date.strftime("%Y-%m-%d")
            data_cache.invalidate(f"minute_day_{date_str}_{host_key}")
            data_cache.invalidate(f"minute_day_{date_str}_{host_key}_past")
            current_date += datetime.timedelta(days=1)
    
    def fetch_and_parse(key):
        """Fetch and parse a single S3 object."""
        try:
            data = json.loads(s3.get_object(Bucket=S3_BUCKET, Key=key)["Body"].read())
            ts_str = data.get("timestamp_ist")
            if not ts_str:
                return None
            ts = TIMEZONE.localize(datetime.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S IST"))
            return {
                "timestamp": ts,
                "download_avg": float(str(data.get("download_mbps", "0")).split()[0]),
                "upload_avg": float(str(data.get("upload_mbps", "0")).split()[0]),
                "ping_avg": safe_float(data.get("ping_ms", 0)),
                "top_server": f"{data.get('server_name', '')} – {data.get('server_host', '')} – {data.get('server_city', '')} ({data.get('server_country', '')})".strip(),
                "public_ip": data.get("public_ip", ""),
                "connection_type": data.get("connection_type", "Unknown"),
                "wifi_name": data.get("wifi_name", ""),
                "result_urls": [data.get("result_url")] if data.get("result_url") else [],
                "host_id": data.get("host_id", "_legacy"),
                "host_name": data.get("host_name", ""),
                "host_location": data.get("host_location", ""),
                "host_isp": data.get("host_isp", "")
            }
        except Exception as e:
            log.warning(f"Skip {key}: {e}")
            return None
    
    def fetch_day_data(date_obj, host_to_query, only_recent=False):
        """Fetch minute data for a specific date from a specific host.
        
        only_recent=True: only fetch files from last 15 minutes (for today's fresh data)
        """
        # Build the S3 prefix based on host
        if host_to_query == "_legacy":
            base_prefix = ""  # Legacy data is at root level
        else:
            base_prefix = f"host={host_to_query}/"
        
        year = date_obj.year
        # S3 path uses YYYYMM and YYYYMMDD format
        month_str = date_obj.strftime("%Y%m")  # e.g., "202512"
        day_str = date_obj.strftime("%Y%m%d")  # e.g., "20251229"
        prefix = f"{base_prefix}year={year}/month={month_str}/day={day_str}/"
        
        keys = []
        try:
            for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    if key.endswith(".json") and "aggregated" not in key:
                        # For recent-only mode, filter by LastModified
                        if only_recent:
                            last_modified = obj.get("LastModified")
                            if last_modified and last_modified.replace(tzinfo=None) < recent_cutoff.replace(tzinfo=None):
                                continue
                        keys.append(key)
        except Exception as e:
            log.warning(f"Error listing {prefix}: {e}")
            return []
        
        if not keys:
            return []
        
        # Parallel fetch for this day (reduced workers to avoid connection drops)
        results = []
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(fetch_and_parse, key) for key in keys]
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)
        return results
    
    # Process each day with smart caching
    all_results = []
    current_date = cutoff.date()
    
    while current_date <= today:
        date_str = current_date.strftime("%Y-%m-%d")
        cache_key = f"minute_day_{date_str}_{host_key}"
        
        if current_date < today:
            # Historical day - cache for 1 hour (data is fixed)
            cached, source = data_cache.get(cache_key, return_source=True)
            if cached is not None:
                log.info(f"[CACHE HIT] {date_str}: {len(cached)} records (from {source})")
                all_results.extend(cached)
            else:
                log.info(f"[S3 FETCH] {date_str} from {len(hosts_to_query)} hosts...")
                day_results = []
                for h in hosts_to_query:
                    day_results.extend(fetch_day_data(current_date, h))
                data_cache.set(cache_key, day_results, ttl=3600)  # 1 hour
                log.info(f"[S3 DONE] {date_str}: {len(day_results)} records → cached (TTL=1h)")
                all_results.extend(day_results)
        else:
            # Today - split into "past" (>15 min old) and "recent" (<15 min old)
            past_cache_key = f"{cache_key}_past"
            
            # Get cached "past" data (data older than 15 min)
            cached_past, source = data_cache.get(past_cache_key, return_source=True)
            if cached_past is not None:
                log.info(f"[CACHE HIT] Today's past: {len(cached_past)} records (from {source})")
                all_results.extend(cached_past)
            else:
                # Fetch all of today's data, split into past and recent
                log.info(f"[S3 FETCH] Today's data from {len(hosts_to_query)} hosts...")
                all_today = []
                for h in hosts_to_query:
                    all_today.extend(fetch_day_data(current_date, h))
                
                # Split into past (>15 min) and recent (<15 min)
                past_data = [r for r in all_today if r["timestamp"] < recent_cutoff]
                recent_data = [r for r in all_today if r["timestamp"] >= recent_cutoff]
                
                # Cache past data for 15 minutes
                if past_data:
                    data_cache.set(past_cache_key, past_data, ttl=900)  # 15 min
                    log.info(f"[S3 DONE] Today's past: {len(past_data)} records → cached (TTL=15m)")
                
                all_results.extend(past_data)
                all_results.extend(recent_data)
                log.info(f"[S3 DONE] Today: {len(past_data)} past + {len(recent_data)} recent (fresh)")
        
        current_date += datetime.timedelta(days=1)
    
    log.info(f"Total minute records: {len(all_results)} for {days} days")

    if not all_results:
        log.warning("No minute-level data found.")
        return pd.DataFrame(columns=["timestamp"])
    
    df = pd.DataFrame(all_results)
    # Filter by cutoff time (for partial days)
    df = df[df["timestamp"] >= cutoff]
    df["date_ist"] = df["timestamp"]
    df["date_ist_str"] = df["timestamp"].dt.strftime("%Y-%m-%d %H:%M")
    log.info(f"Returning {len(df)} minute-level records after time filter.")
    return df.sort_values("timestamp")

@log_execution
def load_hourly_data(days, host_id=None):
    """Load hourly aggregated data from S3_BUCKET_HOURLY using parallel fetches."""
    cutoff = datetime.datetime.now(TIMEZONE) - datetime.timedelta(days=days)
    paginator = s3.get_paginator("list_objects_v2")
    
    # Determine prefix based on host
    if host_id and host_id != "all" and host_id != "_legacy":
        prefix = f"aggregated/host={host_id}/"
    else:
        prefix = "aggregated/"
    
    # Collect all keys first
    keys_to_fetch = []
    for page in paginator.paginate(Bucket=S3_BUCKET_HOURLY, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".json"):
                # For global view, skip host-prefixed files
                if not host_id or host_id == "all":
                    if "host=" not in key:
                        keys_to_fetch.append(key)
                else:
                    keys_to_fetch.append(key)
    
    log.info(f"Found {len(keys_to_fetch)} hourly files to fetch" + (f" for host={host_id}" if host_id else ""))
    
    def fetch_and_parse(key):
        """Fetch and parse a single hourly file."""
        try:
            data = json.loads(s3.get_object(Bucket=S3_BUCKET_HOURLY, Key=key)["Body"].read())
            hour_str = data.get("hour_ist")
            if not hour_str:
                return None
            ts = TIMEZONE.localize(datetime.datetime.strptime(hour_str, "%Y-%m-%d %H:%M"))
            if ts < cutoff:
                return None
            return {
                "timestamp": ts,
                "date_ist": ts,
                "date_ist_str": ts.strftime("%Y-%m-%d %H:00"),
                "download_avg": data["overall"]["download_mbps"]["avg"],
                "upload_avg": data["overall"]["upload_mbps"]["avg"],
                "ping_avg": data["overall"]["ping_ms"]["avg"],
                "top_server": data.get("servers_top", [""])[0] if data.get("servers_top") else "",
                "public_ips": data.get("public_ips", []),
                "public_ip": data.get("public_ips", [""])[0] if data.get("public_ips") else "",
                "connection_type": ", ".join(data.get("connection_types", [])) if data.get("connection_types") else "Unknown",
                "wifi_name": "",
                "result_urls": [],
                "records": data.get("records", 0),
                "completion_rate": data.get("completion_rate", 0),
                "host_id": data.get("host_id", "_legacy")
            }
        except Exception as e:
            log.warning(f"Skip {key}: {e}")
            return None
    
    # Parallel fetch with up to 20 threads (reduced to avoid connection drops)
    results = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(fetch_and_parse, key): key for key in keys_to_fetch}
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)

    if not results:
        log.warning("No hourly data found.")
        return pd.DataFrame(columns=["timestamp"])
    df = pd.DataFrame(results)
    log.info(f"Loaded {len(df)} hourly records from S3" + (f" for host={host_id}" if host_id else "") + ".")
    return df.sort_values("timestamp")

@log_execution
def load_weekly_data(weeks=52, host_id=None):
    """Load weekly aggregated data from S3_BUCKET_WEEKLY using parallel fetches."""
    paginator = s3.get_paginator("list_objects_v2")
    cutoff_date = datetime.datetime.now(TIMEZONE).date() - datetime.timedelta(weeks=weeks)

    # Determine prefix based on host
    if host_id and host_id != "all" and host_id != "_legacy":
        prefix = f"aggregated/host={host_id}/"
    else:
        prefix = "aggregated/"

    # Collect all keys first
    keys_to_fetch = []
    for page in paginator.paginate(Bucket=S3_BUCKET_WEEKLY, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".json"):
                # For global view, skip host-prefixed files
                if not host_id or host_id == "all":
                    if "host=" not in key:
                        keys_to_fetch.append(key)
                else:
                    keys_to_fetch.append(key)
    
    log.info(f"Found {len(keys_to_fetch)} weekly files to fetch" + (f" for host={host_id}" if host_id else ""))
    
    def fetch_and_parse(key):
        """Fetch and parse a single weekly file."""
        try:
            data = json.loads(s3.get_object(Bucket=S3_BUCKET_WEEKLY, Key=key)["Body"].read())
            week_start = datetime.datetime.strptime(data["week_start"], "%Y-%m-%d").date()
            if week_start < cutoff_date:
                return None
            return {
                "date_ist": week_start,
                "date_ist_str": f"{data['week_start']} to {data['week_end']}",
                "download_avg": data["avg_download"],
                "upload_avg": data["avg_upload"],
                "ping_avg": data["avg_ping"],
                "days": data.get("days", 0),
                "connection_type": ", ".join(data.get("connection_types", [])) if data.get("connection_types") else "Unknown",
                "top_server": "",
                "public_ips": [],
                "public_ip": "",
                "result_urls": [],
                "host_id": data.get("host_id", "_legacy")
            }
        except Exception as e:
            log.warning(f"Skip {key}: {e}")
            return None
    
    # Parallel fetch with up to 20 threads
    results = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(fetch_and_parse, key): key for key in keys_to_fetch}
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)

    if not results:
        log.warning(f"No weekly data found for last {weeks} weeks.")
        return pd.DataFrame(columns=["date_ist"])
    df = pd.DataFrame(results)
    log.info(f"Loaded {len(df)} weekly records from S3 (last {weeks} weeks)" + (f" for host={host_id}" if host_id else "") + ".")
    return df.sort_values("date_ist")

@log_execution
def load_monthly_data(months=12, host_id=None):
    """Load monthly aggregated data from S3_BUCKET_MONTHLY using parallel fetches."""
    paginator = s3.get_paginator("list_objects_v2")
    cutoff_date = datetime.datetime.now(TIMEZONE).date().replace(day=1)
    cutoff_date = cutoff_date - datetime.timedelta(days=30 * months)

    # Determine prefix based on host
    if host_id and host_id != "all" and host_id != "_legacy":
        prefix = f"aggregated/host={host_id}/"
    else:
        prefix = "aggregated/"

    # Collect all keys with their last_modified for deduplication
    keys_with_meta = []
    for page in paginator.paginate(Bucket=S3_BUCKET_MONTHLY, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".json"):
                # For global view, skip host-prefixed files
                if not host_id or host_id == "all":
                    if "host=" not in key:
                        keys_with_meta.append((key, obj.get("LastModified")))
                else:
                    keys_with_meta.append((key, obj.get("LastModified")))
    
    log.info(f"Found {len(keys_with_meta)} monthly files to fetch" + (f" for host={host_id}" if host_id else ""))
    
    def fetch_and_parse(key_meta):
        """Fetch and parse a single monthly file."""
        key, last_modified = key_meta
        try:
            data = json.loads(s3.get_object(Bucket=S3_BUCKET_MONTHLY, Key=key)["Body"].read())
            month_str = data["month"]
            month_date = datetime.datetime.strptime(month_str, "%Y%m").date()
            if month_date < cutoff_date:
                return None
            return (month_str, data, last_modified)
        except Exception as e:
            log.warning(f"Skip {key}: {e}")
            return None
    
    # Parallel fetch
    fetched_data = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(fetch_and_parse, km): km for km in keys_with_meta}
        for future in as_completed(futures):
            result = future.result()
            if result:
                fetched_data.append(result)
    
    # Deduplicate: keep only most recent file for each month
    monthly_data = {}
    for month_str, data, last_modified in fetched_data:
        if month_str not in monthly_data or (last_modified and last_modified > monthly_data[month_str][1]):
            monthly_data[month_str] = (data, last_modified)

    # Convert to results list
    results = []
    for month_str, (data, _) in monthly_data.items():
        month_date = datetime.datetime.strptime(month_str, "%Y%m").date()
        results.append({
            "date_ist": month_date,
            "date_ist_str": month_date.strftime("%Y-%m"),
            "download_avg": data["avg_download"],
            "upload_avg": data["avg_upload"],
            "ping_avg": data["avg_ping"],
            "days": data.get("days", 0),
            "connection_type": ", ".join(data.get("connection_types", [])) if data.get("connection_types") else "Unknown",
            "top_server": "",
            "public_ips": [],
            "public_ip": "",
            "result_urls": [],
            "host_id": data.get("host_id", "_legacy")
        })

    if not results:
        log.warning(f"No monthly data found for last {months} months.")
        return pd.DataFrame(columns=["date_ist"])
    df = pd.DataFrame(results)
    log.info(f"Loaded {len(df)} unique monthly records from S3 (last {months} months)" + (f" for host={host_id}" if host_id else "") + ".")
    return df.sort_values("date_ist")

@log_execution
def load_yearly_data(years=10, host_id=None):
    """Load yearly aggregated data from S3_BUCKET_YEARLY using parallel fetches."""
    paginator = s3.get_paginator("list_objects_v2")
    cutoff_year = datetime.datetime.now(TIMEZONE).year - years

    # Determine prefix based on host
    if host_id and host_id != "all" and host_id != "_legacy":
        prefix = f"aggregated/host={host_id}/"
    else:
        prefix = "aggregated/"

    # Collect all keys first
    keys_to_fetch = []
    for page in paginator.paginate(Bucket=S3_BUCKET_YEARLY, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".json"):
                # For global view, skip host-prefixed files
                if not host_id or host_id == "all":
                    if "host=" not in key:
                        keys_to_fetch.append(key)
                else:
                    keys_to_fetch.append(key)
    
    log.info(f"Found {len(keys_to_fetch)} yearly files to fetch" + (f" for host={host_id}" if host_id else ""))
    
    def fetch_and_parse(key):
        """Fetch and parse a single yearly file."""
        try:
            data = json.loads(s3.get_object(Bucket=S3_BUCKET_YEARLY, Key=key)["Body"].read())
            year = data["year"]
            if year < cutoff_year:
                return None
            year_date = datetime.datetime(year, 1, 1).date()
            return {
                "date_ist": year_date,
                "date_ist_str": str(year),
                "download_avg": data["avg_download"],
                "upload_avg": data["avg_upload"],
                "ping_avg": data["avg_ping"],
                "months": data.get("months_aggregated", 0),
                "connection_type": ", ".join(data.get("connection_types", [])) if data.get("connection_types") else "Unknown",
                "top_server": "",
                "public_ips": [],
                "public_ip": "",
                "result_urls": [],
                "host_id": data.get("host_id", "_legacy")
            }
        except Exception as e:
            log.warning(f"Skip {key}: {e}")
            return None
    
    # Parallel fetch
    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_and_parse, key): key for key in keys_to_fetch}
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)

    if not results:
        log.warning(f"No yearly data found for last {years} years.")
        return pd.DataFrame(columns=["date_ist"])
    df = pd.DataFrame(results)
    log.info(f"Loaded {len(df)} yearly records from S3 (last {years} years)" + (f" for host={host_id}" if host_id else "") + ".")
    return df.sort_values("date_ist")

def safe_float(value):
    """Convert values like '184.52 Mbps' or '6.58 ms' safely to float."""
    if isinstance(value, str):
        value = (
            value.replace("Mbps", "")
                 .replace("Mbit/s", "")
                 .replace("mbps", "")
                 .replace("ms", "")
                 .strip()
        )
        # If there's still a space, take first token
        value = value.split()[0]
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0
    
# --- Anomaly Detection --------------------------------------------------------
def detect_anomalies(df):
    """
    Detect anomalies in speed test data using connection-aware thresholds.
    Uses connection-specific thresholds from config for accurate performance assessment.
    """
    if df.empty:
        return df
    
    # Statistical anomalies (relative to dataset mean)
    dl_mean = df["download_avg"].mean()
    ping_mean = df["ping_avg"].mean()
    df["download_anomaly"] = df["download_avg"] < (0.7 * dl_mean)
    df["ping_anomaly"] = df["ping_avg"] > (1.5 * ping_mean)
    
    # Connection-aware threshold anomalies
    connection_thresholds = config.connection_type_thresholds
    
    tolerance = TOLERANCE_PERCENT / 100.0
    
    def is_below_expected(row):
        """Check if download speed is below expected for connection type."""
        conn_type = str(row.get("connection_type", "Unknown"))
        # Extract primary connection type (in case of comma-separated values)
        primary_conn = conn_type.split(",")[0].strip() if conn_type else "Unknown"
        
        # Find matching threshold
        threshold = connection_thresholds.get("Unknown", 150)  # default
        for key, value in connection_thresholds.items():
            if key.lower() in primary_conn.lower():
                threshold = value
                break
        
        return row["download_avg"] < (threshold * (1 - tolerance))
    
    df["below_expected"] = df.apply(is_below_expected, axis=1)
    
    return df

# --- Routes -------------------------------------------------------------------
@app.route("/", methods=["GET", "POST"])
@app.route("/dashboard", methods=["GET", "POST"])
@log_execution
def dashboard():
    import time
    start_time = time.time()
    
    # Primary controls from GET parameters (mode, days, host)
    mode = request.args.get("mode", "daily")
    days_param = int(request.args.get("days", 7))
    host_id = request.args.get("host", None)  # None = all hosts (global view)
    force_refresh = request.args.get("refresh", "0") == "1" or request.args.get("force-reload", "").lower() == "true"
    async_mode = request.args.get("async", "0") == "1"
    
    # Get list of available hosts for the dropdown
    available_hosts = list_hosts()
    
    # Advanced filters from POST body (if any)
    params = request.form if request.method == "POST" else request.args

    # Theme selection: ?theme=classic for old UI, default is modern
    theme = request.args.get("theme", "modern")
    template_name = "dashboard.html" if theme == "classic" else "dashboard_modern.html"

    # ASYNC MODE: Return skeleton template immediately, JS will fetch data
    if async_mode:
        log.info(f"Async mode: returning skeleton for mode={mode}, days={days_param}, host={host_id}, theme={theme}")
        load_time = round((time.time() - start_time) * 1000, 1)  # ms
        return render_template(
            template_name,
            async_mode=True,
            data=[],
            days=days_param,
            summary={},
            stats={"avg_download": 0, "avg_upload": 0, "avg_ping": 0, "total_tests": 0},
            percentiles={},
            trends={},
            historical_records={},
            connection_stats={},
            chart_data={"timestamps": [], "download": [], "upload": [], "ping": [], "connection_types": []},
            quick_filters={"below_threshold": 0, "performance_drops": 0, "high_ping": 0, "isps": [], "connection_types": []},
            last_update="Loading...",
            view_mode=mode,
            date_from="", date_to="", time_from="", time_to="",
            min_download="", max_download="", min_upload="", max_upload="",
            min_ping="", max_ping="", connection_type="", isp="",
            threshold=DEFAULT_THRESHOLD,  # For classic dashboard compatibility
            default_threshold=DEFAULT_THRESHOLD,
            tolerance_percent=TOLERANCE_PERCENT,
            connection_type_thresholds=config.connection_type_thresholds,
            mode=mode,
            available_hosts=available_hosts,
            selected_host=host_id,
            load_time_ms=load_time
        )

    # Convert days parameter to appropriate units based on mode
    if mode == "weekly":
        period = days_param // 7  # Convert days to weeks
    elif mode == "monthly":
        period = days_param // 30  # Convert days to months (approximate)
    elif mode == "yearly":
        period = days_param // 365  # Convert days to years
    else:
        period = days_param  # Use days as-is for minute, hourly, daily modes

    # Cache key based on mode, period, and host
    host_key = host_id or "all"
    cache_key = f"dashboard_{mode}_{period}_{host_key}"
    
    # Invalidate cache if force refresh requested
    if force_refresh:
        data_cache.invalidate(cache_key)
        # Clear all related caches for this mode/period/host
        data_cache.invalidate(f"minute_data_{period}_{host_key}")
        data_cache.invalidate(f"api_{mode}_{period}_{host_key}")
        data_cache.invalidate(f"dashboard_api_{mode}_{period}_{host_key}")
        log.info(f"[FORCE RELOAD] All caches invalidated for mode={mode}, period={period}, host={host_key}")
    
    # Check cache first
    cached_df = data_cache.get(cache_key)
    if cached_df is not None:
        log.info(f"Cache HIT (memory) for {cache_key}")
        df = cached_df
    else:
        log.info(f"Cache MISS for {cache_key} - loading from S3")
        # Load data based on mode (with host filtering)
        if mode == "minute":
            df = load_minute_data(period, host_id=host_id, force_reload=force_refresh)
        elif mode == "hourly":
            df = load_hourly_data(period, host_id=host_id)
        elif mode == "weekly":
            df = load_weekly_data(period, host_id=host_id)  # period = weeks
        elif mode == "monthly":
            df = load_monthly_data(period, host_id=host_id)  # period = months
        elif mode == "yearly":
            df = load_yearly_data(period, host_id=host_id)  # period = years
        else:  # daily
            df = load_summaries(host_id=host_id)  # daily mode loads all and filters
        
        # Cache the loaded data with mode-specific TTL
        # Minute data is expensive to fetch, so cache longer
        cache_ttl = 600 if mode == "minute" else 120  # 10 min for minute, 2 min for others
        data_cache.set(cache_key, df, ttl=cache_ttl)
        log.info(f"Cached {cache_key} with TTL={cache_ttl}s")
    
    df = detect_anomalies(df)

    summary = {
        "avg_download": 0,
        "avg_upload": 0,
        "avg_ping": 0,
        "below_expected": 0,
        "total_days": 0,
        "top_server_over_period": "N/A",
        "public_ips": [],
        "cidr_ranges": [],
    }
    if not df.empty:
        top_server_over_period = df["top_server"].mode()[0] if not df["top_server"].mode().empty else "N/A"
        public_ips = sorted({
            ip.strip()
            for vals in df.get("public_ips", [])
            if isinstance(vals, list)
            for ip in vals
            if isinstance(ip, str) and ip.strip() and ip.strip().lower() not in ('unknown', 'n/a', '')
        })
        
        # Calculate CIDR ranges for public IPs
        cidr_ranges = []
        if public_ips:
            try:
                import ipaddress
                # Group IPs by /16 network first (larger aggregation)
                networks_16 = {}
                networks_24 = {}
                
                for ip_str in public_ips:
                    try:
                        ip = ipaddress.ip_address(ip_str)
                        # Get /16 network (e.g., 223.178.0.0/16)
                        network_16 = ipaddress.ip_network(f"{ip}/16", strict=False)
                        network_16_str = str(network_16)
                        if network_16_str not in networks_16:
                            networks_16[network_16_str] = []
                        networks_16[network_16_str].append(ip_str)
                        
                        # Also track /24 networks for single IP cases
                        network_24 = ipaddress.ip_network(f"{ip}/24", strict=False)
                        network_24_str = str(network_24)
                        if network_24_str not in networks_24:
                            networks_24[network_24_str] = []
                        networks_24[network_24_str].append(ip_str)
                    except ValueError:
                        continue
                
                # Use /16 if multiple /24 blocks exist in same /16, otherwise use /24
                cidr_info = []
                for cidr_16, ips_16 in networks_16.items():
                    # Count how many different /24 blocks are in this /16
                    unique_24_blocks = set()
                    for ip_str in ips_16:
                        ip = ipaddress.ip_address(ip_str)
                        network_24 = ipaddress.ip_network(f"{ip}/24", strict=False)
                        unique_24_blocks.add(str(network_24))
                    
                    # If 3+ different /24 blocks in same /16, show as /16
                    if len(unique_24_blocks) >= 3:
                        cidr_info.append({
                            "cidr": cidr_16,
                            "count": len(ips_16),
                            "ips": ips_16
                        })
                    else:
                        # Show individual /24 blocks
                        for block_24 in unique_24_blocks:
                            cidr_info.append({
                                "cidr": block_24,
                                "count": len(networks_24[block_24]),
                                "ips": networks_24[block_24]
                            })
                
                # Sort by IP count (descending)
                cidr_ranges = sorted(cidr_info, key=lambda x: x['count'], reverse=True)
                
            except Exception as e:
                log.warning(f"Failed to calculate CIDR ranges: {e}")
                cidr_ranges = []

        if mode in ["daily", "hourly"]:
            below_count = int(df["below_expected"].sum())
            total_days = int(len(df))
        else:
            daily_below = df.groupby(df["date_ist"].dt.date if hasattr(df["date_ist"].iloc[0], 'date') else df["date_ist"])["below_expected"].any()
            below_count = int(daily_below.sum())
            total_days = int(daily_below.size)

        # Use the already-loaded aggregated data for all statistics
        # No need to load minute data separately - aggregated data has all the stats we need!
        # This eliminates the slow S3 fetches that were causing 2-minute page loads
        
        # Calculate averages directly from the already-loaded df
        avg_download = round(df["download_avg"].mean(), 2)
        avg_upload = round(df["upload_avg"].mean(), 2)
        avg_ping = round(df["ping_avg"].mean(), 2)

        summary = {
            "avg_download": avg_download,
            "avg_upload": avg_upload,
            "avg_ping": avg_ping,
            "below_expected": below_count,
            "total_days": total_days,
            "top_server_over_period": top_server_over_period,
            "public_ips": public_ips,
            "cidr_ranges": cidr_ranges,
        }

        if mode in ["daily", "hourly"]:
            best_idx = df["download_avg"].idxmax()
            worst_idx = df["download_avg"].idxmin()
            summary.update({
                "best_day": str(df.loc[best_idx, "date_ist"].date() if hasattr(df.loc[best_idx, "date_ist"], 'date') else df.loc[best_idx, "date_ist"]),
                "worst_day": str(df.loc[worst_idx, "date_ist"].date() if hasattr(df.loc[worst_idx, "date_ist"], 'date') else df.loc[worst_idx, "date_ist"])
            })

    log.info(f"Dashboard summary ready for mode={mode}, days={period}")
    
    # Calculate percentile statistics from the already-loaded aggregated data
    # No separate minute data fetch needed - df already has all the stats
    percentiles = {}
    if not df.empty:
        percentiles = {
            "download_p50": round(df["download_avg"].quantile(0.50), 2),
            "download_p95": round(df["download_avg"].quantile(0.95), 2),
            "download_p99": round(df["download_avg"].quantile(0.99), 2),
            "upload_p50": round(df["upload_avg"].quantile(0.50), 2),
            "upload_p95": round(df["upload_avg"].quantile(0.95), 2),
            "upload_p99": round(df["upload_avg"].quantile(0.99), 2),
            "ping_p50": round(df["ping_avg"].quantile(0.50), 2),
            "ping_p95": round(df["ping_avg"].quantile(0.95), 2),
            "ping_p99": round(df["ping_avg"].quantile(0.99), 2),
        }
    
    # Calculate trend indicators (compare with previous period)
    trends = {}
    if not df.empty and len(df) > 1:
        # Split data in half to compare current vs previous period
        mid_point = len(df) // 2
        df_sorted = df.sort_values("date_ist")
        current_period = df_sorted.iloc[mid_point:]
        previous_period = df_sorted.iloc[:mid_point]
        
        if not current_period.empty and not previous_period.empty:
            curr_down = current_period["download_avg"].mean()
            prev_down = previous_period["download_avg"].mean()
            curr_up = current_period["upload_avg"].mean()
            prev_up = previous_period["upload_avg"].mean()
            curr_ping = current_period["ping_avg"].mean()
            prev_ping = previous_period["ping_avg"].mean()
            
            trends = {
                "download_change": round(((curr_down - prev_down) / prev_down * 100) if prev_down > 0 else 0, 1),
                "upload_change": round(((curr_up - prev_up) / prev_up * 100) if prev_up > 0 else 0, 1),
                "ping_change": round(((curr_ping - prev_ping) / prev_ping * 100) if prev_ping > 0 else 0, 1),
                "tests_change": round(((len(current_period) - len(previous_period)) / len(previous_period) * 100) if len(previous_period) > 0 else 0, 1)
            }
    
    # Calculate historical best/worst records
    historical_records = {}
    if not df.empty:
        best_download_idx = df["download_avg"].idxmax()
        worst_download_idx = df["download_avg"].idxmin()
        best_upload_idx = df["upload_avg"].idxmax()
        lowest_ping_idx = df["ping_avg"].idxmin()
        
        historical_records = {
            "best_download": {
                "value": round(df.loc[best_download_idx, "download_avg"], 2),
                "date": str(df.loc[best_download_idx, "date_ist"]),
                "server": df.loc[best_download_idx, "top_server"] if "top_server" in df.columns else "N/A"
            },
            "worst_download": {
                "value": round(df.loc[worst_download_idx, "download_avg"], 2),
                "date": str(df.loc[worst_download_idx, "date_ist"])
            },
            "best_upload": {
                "value": round(df.loc[best_upload_idx, "upload_avg"], 2),
                "date": str(df.loc[best_upload_idx, "date_ist"])
            },
            "lowest_ping": {
                "value": round(df.loc[lowest_ping_idx, "ping_avg"], 2),
                "date": str(df.loc[lowest_ping_idx, "date_ist"])
            }
        }
    
    # Calculate connection type statistics
    connection_stats = {}
    connection_thresholds = {
        "Ethernet": {"threshold": 200, "min_threshold": 180},
        "Wi-Fi 5GHz": {"threshold": 200, "min_threshold": 180},
        "Wi-Fi 2.4GHz": {"threshold": 100, "min_threshold": 90},
        "Unknown": {"threshold": 150, "min_threshold": 135}
    }
    
    if not df.empty and "connection_type" in df.columns:
        # Parse connection types from comma-separated values
        for conn_type_key in connection_thresholds.keys():
            # Filter rows that contain this connection type
            mask = df["connection_type"].str.contains(conn_type_key, case=False, na=False)
            conn_df = df[mask]
            
            if not conn_df.empty:
                conn_avg = conn_df["download_avg"].mean()
                conn_count = len(conn_df)
                min_threshold = connection_thresholds[conn_type_key]["min_threshold"]
                below_min = (conn_df["download_avg"] < min_threshold).sum()
                below_pct = (below_min / conn_count * 100) if conn_count > 0 else 0
                
                connection_stats[conn_type_key] = {
                    "count": conn_count,
                    "avg": round(conn_avg, 1),
                    "threshold": connection_thresholds[conn_type_key]["threshold"],
                    "min_threshold": min_threshold,
                    "below_min": below_min,
                    "below_pct": round(below_pct, 1)
                }
    
    # Prepare chart data for ECharts
    if not df.empty and "date_ist" in df.columns:
        try:
            timestamps = df["date_ist"].dt.strftime("%Y-%m-%d %H:%M").tolist()
        except:
            timestamps = [str(x) for x in df["date_ist"].tolist()]
    else:
        timestamps = []
    
    # Extract dynamic quick filter options
    quick_filters = {
        "below_threshold": 0,
        "performance_drops": 0,
        "high_ping": 0,
        "isps": [],
        "connection_types": []
    }
    
    if not df.empty:
        # Count performance categories
        # Below threshold uses conservative 200 Mbps (shows all potentially poor connections)
        quick_filters["below_threshold"] = int((df["download_avg"] < 200).sum())
        quick_filters["performance_drops"] = int((df["download_avg"] < 100).sum())
        quick_filters["high_ping"] = int((df["ping_avg"] > 20).sum())
        
        # Extract unique ISPs
        if "isp" in df.columns:
            unique_isps = df["isp"].dropna().unique()
            isp_counts = df["isp"].value_counts().to_dict()
            quick_filters["isps"] = [
                {"name": isp, "count": isp_counts.get(isp, 0)} 
                for isp in sorted(unique_isps) if isp
            ]
        
        # Extract unique connection types
        if "connection_type" in df.columns:
            # Handle comma-separated connection types
            all_conn_types = set()
            for conn_str in df["connection_type"].dropna():
                if isinstance(conn_str, str):
                    types = [t.strip() for t in conn_str.split(",")]
                    all_conn_types.update(types)
            
            # Filter out "Wi-Fi (unknown band)"
            all_conn_types = {ct for ct in all_conn_types if ct and ct != "Wi-Fi (unknown band)"}
            
            # Count occurrences
            conn_counts = {}
            for conn_type in all_conn_types:
                count = df["connection_type"].str.contains(conn_type, case=False, na=False).sum()
                conn_counts[conn_type] = count
            
            quick_filters["connection_types"] = [
                {"name": ct, "count": conn_counts[ct]} 
                for ct in sorted(all_conn_types) if ct
            ]
    
    chart_data = {
        "timestamps": timestamps,
        "download": df["download_avg"].fillna(0).tolist() if not df.empty and "download_avg" in df.columns else [],
        "upload": df["upload_avg"].fillna(0).tolist() if not df.empty and "upload_avg" in df.columns else [],
        "ping": df["ping_avg"].fillna(0).tolist() if not df.empty and "ping_avg" in df.columns else [],
        "connection_types": df["connection_type"].fillna("Unknown").tolist() if not df.empty and "connection_type" in df.columns else []
    }
    
    # Downsample chart data if too many points
    # Use mode-appropriate limits: minute data needs more aggressive downsampling
    if mode == "minute":
        max_chart_points = 200  # More aggressive for minute data
    elif mode == "hourly":
        max_chart_points = 300
    else:
        max_chart_points = 500  # Daily/weekly/monthly can have more points
    
    if len(chart_data.get("timestamps", [])) > max_chart_points:
        original_count = len(chart_data["timestamps"])
        chart_data = downsample_chart_data(chart_data, max_points=max_chart_points)
        log.info(f"Chart data downsampled: {original_count} -> {len(chart_data['timestamps'])} points")
    
    # Stats summary with total_tests
    stats = {
        "avg_download": summary.get("avg_download", 0),
        "avg_upload": summary.get("avg_upload", 0),
        "avg_ping": summary.get("avg_ping", 0),
        "total_tests": len(df) if not df.empty else 0
    }
    
    # Get current datetime for last_update
    import datetime as dt
    last_update = dt.datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S IST")
    
    # Sort data by date in descending order (newest first)
    if not df.empty and "date_ist" in df.columns:
        df = df.sort_values("date_ist", ascending=False)
    
    # Get connection type thresholds from config
    connection_type_thresholds = config.connection_type_thresholds
    
    # Calculate load time
    load_time = round((time.time() - start_time) * 1000, 1)  # ms
    
    return render_template(
        template_name,
        data=df.to_dict(orient="records"),
        days=days_param,
        summary=summary,
        stats=stats,
        percentiles=percentiles,
        trends=trends,
        historical_records=historical_records,
        connection_stats=connection_stats,
        chart_data=chart_data,
        quick_filters=quick_filters,
        last_update=last_update,
        view_mode=mode,
        date_from=params.get("date_from", ""),
        date_to=params.get("date_to", ""),
        time_from=params.get("time_from", ""),
        time_to=params.get("time_to", ""),
        min_download=params.get("min_download", ""),
        max_download=params.get("max_download", ""),
        min_upload=params.get("min_upload", ""),
        max_upload=params.get("max_upload", ""),
        min_ping=params.get("min_ping", ""),
        max_ping=params.get("max_ping", ""),
        connection_type=params.get("connection_type", ""),
        isp=params.get("isp", ""),
        threshold=DEFAULT_THRESHOLD,  # For classic dashboard compatibility
        default_threshold=DEFAULT_THRESHOLD,
        tolerance_percent=TOLERANCE_PERCENT,
        connection_type_thresholds=connection_type_thresholds,
        mode=mode,
        available_hosts=available_hosts,
        selected_host=host_id,
        load_time_ms=load_time
    )

@app.route("/api/data")
@log_execution
def api_data():
    mode = request.args.get("mode", "daily")
    days_param = int(request.args.get("days", 7))
    host_id = request.args.get("host", None)  # None = all hosts
    force_refresh = request.args.get("refresh", "0") == "1" or request.args.get("force-reload", "").lower() == "true"
    
    # Convert days parameter to appropriate units based on mode
    if mode == "weekly":
        period = days_param // 7  # Convert days to weeks
    elif mode == "monthly":
        period = days_param // 30  # Convert days to months (approximate)
    elif mode == "yearly":
        period = days_param // 365  # Convert days to years
    else:
        period = days_param  # Use days as-is for minute, hourly, daily modes
    
    # Cache key for API (include host)
    host_key = host_id or "all"
    cache_key = f"api_{mode}_{period}_{host_key}"
    
    # Handle force refresh - clear all related caches
    if force_refresh:
        data_cache.invalidate(cache_key)
        data_cache.invalidate(f"dashboard_{mode}_{period}_{host_key}")
        data_cache.invalidate(f"dashboard_api_{mode}_{period}_{host_key}")
        log.info(f"[FORCE RELOAD] All caches invalidated for mode={mode}, period={period}, host={host_key}")
    
    # Check cache
    cached_df = data_cache.get(cache_key)
    if cached_df is not None:
        log.info(f"API cache HIT (memory) for {cache_key}")
        df = cached_df
    else:
        log.info(f"API cache MISS for {cache_key}")
        # Load data based on mode (with host filtering)
        if mode == "minute":
            df = load_minute_data(period, host_id=host_id, force_reload=force_refresh)
        elif mode == "hourly":
            df = load_hourly_data(period, host_id=host_id)
        elif mode == "weekly":
            df = load_weekly_data(period, host_id=host_id)
        elif mode == "monthly":
            df = load_monthly_data(period, host_id=host_id)
        elif mode == "yearly":
            df = load_yearly_data(period, host_id=host_id)
        else:  # daily
            df = load_summaries(host_id=host_id)
        
        data_cache.set(cache_key, df)
    
    df = detect_anomalies(df)
    log.info(f"API returned {len(df)} records in mode={mode}, host={host_id}")
    return jsonify(df.to_dict(orient="records"))

@app.route("/api/dashboard")
@log_execution
def api_dashboard():
    """
    Full dashboard data API for async loading.
    Returns all data needed to populate the dashboard via JavaScript.
    """
    mode = request.args.get("mode", "daily")
    days_param = int(request.args.get("days", 7))
    host_id = request.args.get("host", None)  # None = all hosts
    force_refresh = request.args.get("refresh", "0") == "1" or request.args.get("force-reload", "").lower() == "true"
    
    # Convert days parameter to appropriate units based on mode
    if mode == "weekly":
        period = days_param // 7
    elif mode == "monthly":
        period = days_param // 30
    elif mode == "yearly":
        period = days_param // 365
    else:
        period = days_param

    # Cache key (include host)
    host_key = host_id or "all"
    cache_key = f"dashboard_api_{mode}_{period}_{host_key}"
    
    # Handle force refresh - clear all related caches
    if force_refresh:
        data_cache.invalidate(cache_key)
        data_cache.invalidate(f"dashboard_{mode}_{period}_{host_key}")
        data_cache.invalidate(f"api_{mode}_{period}_{host_key}")
        log.info(f"[FORCE RELOAD] All caches invalidated for mode={mode}, period={period}, host={host_key}")
    
    # Check cache for pre-computed dashboard response
    cached_response = data_cache.get(cache_key)
    if cached_response is not None:
        log.info(f"Dashboard API cache HIT (memory) for {cache_key}")
        return jsonify(cached_response)
    
    log.info(f"Dashboard API cache MISS for {cache_key} - computing...")
    
    # Load data based on mode (with host filtering)
    if mode == "minute":
        df = load_minute_data(period, host_id=host_id, force_reload=force_refresh)
    elif mode == "hourly":
        df = load_hourly_data(period, host_id=host_id)
    elif mode == "weekly":
        df = load_weekly_data(period, host_id=host_id)
    elif mode == "monthly":
        df = load_monthly_data(period, host_id=host_id)
    elif mode == "yearly":
        df = load_yearly_data(period, host_id=host_id)
    else:
        df = load_summaries(host_id=host_id)
    
    df = detect_anomalies(df)
    
    # Build response data
    summary = {
        "avg_download": 0,
        "avg_upload": 0,
        "avg_ping": 0,
        "below_expected": 0,
        "total_days": 0,
        "top_server_over_period": "N/A",
    }
    percentiles = {}
    trends = {}
    historical_records = {}
    connection_stats = {}
    
    if not df.empty:
        # Calculate summary stats
        avg_download = round(df["download_avg"].mean(), 2)
        avg_upload = round(df["upload_avg"].mean(), 2)
        avg_ping = round(df["ping_avg"].mean(), 2)
        
        top_server = df["top_server"].mode()[0] if not df["top_server"].mode().empty else "N/A"
        
        below_count = int(df["below_expected"].sum()) if "below_expected" in df.columns else 0
        total_days = len(df)
        
        summary = {
            "avg_download": avg_download,
            "avg_upload": avg_upload,
            "avg_ping": avg_ping,
            "below_expected": below_count,
            "total_days": total_days,
            "top_server_over_period": top_server,
        }
        
        # Percentiles
        percentiles = {
            "download_p50": round(df["download_avg"].quantile(0.50), 2),
            "download_p95": round(df["download_avg"].quantile(0.95), 2),
            "download_p99": round(df["download_avg"].quantile(0.99), 2),
            "upload_p50": round(df["upload_avg"].quantile(0.50), 2),
            "upload_p95": round(df["upload_avg"].quantile(0.95), 2),
            "upload_p99": round(df["upload_avg"].quantile(0.99), 2),
            "ping_p50": round(df["ping_avg"].quantile(0.50), 2),
            "ping_p95": round(df["ping_avg"].quantile(0.95), 2),
            "ping_p99": round(df["ping_avg"].quantile(0.99), 2),
        }
        
        # Trends
        if len(df) > 1:
            mid_point = len(df) // 2
            df_sorted = df.sort_values("date_ist")
            current_period = df_sorted.iloc[mid_point:]
            previous_period = df_sorted.iloc[:mid_point]
            
            if not current_period.empty and not previous_period.empty:
                curr_down = current_period["download_avg"].mean()
                prev_down = previous_period["download_avg"].mean()
                curr_up = current_period["upload_avg"].mean()
                prev_up = previous_period["upload_avg"].mean()
                curr_ping = current_period["ping_avg"].mean()
                prev_ping = previous_period["ping_avg"].mean()
                
                trends = {
                    "download_change": round(((curr_down - prev_down) / prev_down * 100) if prev_down > 0 else 0, 1),
                    "upload_change": round(((curr_up - prev_up) / prev_up * 100) if prev_up > 0 else 0, 1),
                    "ping_change": round(((curr_ping - prev_ping) / prev_ping * 100) if prev_ping > 0 else 0, 1),
                }
        
        # Historical records
        best_download_idx = df["download_avg"].idxmax()
        worst_download_idx = df["download_avg"].idxmin()
        
        historical_records = {
            "best_download": {
                "value": round(df.loc[best_download_idx, "download_avg"], 2),
                "date": str(df.loc[best_download_idx, "date_ist"]),
            },
            "worst_download": {
                "value": round(df.loc[worst_download_idx, "download_avg"], 2),
                "date": str(df.loc[worst_download_idx, "date_ist"]),
            },
        }
    
    # Chart data
    if not df.empty and "date_ist" in df.columns:
        try:
            timestamps = df["date_ist"].dt.strftime("%Y-%m-%d %H:%M").tolist()
        except:
            timestamps = [str(x) for x in df["date_ist"].tolist()]
    else:
        timestamps = []
    
    chart_data = {
        "timestamps": timestamps,
        "download": df["download_avg"].fillna(0).tolist() if not df.empty else [],
        "upload": df["upload_avg"].fillna(0).tolist() if not df.empty else [],
        "ping": df["ping_avg"].fillna(0).tolist() if not df.empty else [],
    }
    
    # Downsample chart data if too many points (keeps max 500 points using LTTB algorithm)
    if len(chart_data.get("timestamps", [])) > 500:
        chart_data = downsample_chart_data(chart_data, max_points=500)
    
    stats = {
        "avg_download": summary.get("avg_download", 0),
        "avg_upload": summary.get("avg_upload", 0),
        "avg_ping": summary.get("avg_ping", 0),
        "total_tests": len(df) if not df.empty else 0
    }
    
    import datetime as dt
    last_update = dt.datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S IST")
    
    # Build complete response
    response = {
        "success": True,
        "stats": stats,
        "summary": summary,
        "percentiles": percentiles,
        "trends": trends,
        "historical_records": historical_records,
        "chart_data": chart_data,
        "last_update": last_update,
        "mode": mode,
        "days": days_param,
        "record_count": len(df),
    }
    
    # Cache the response
    data_cache.set(cache_key, response)
    log.info(f"Dashboard API response cached for {cache_key}")
    
    return jsonify(response)

# --- Local Run ---------------------------------------------------------------
if __name__ == "__main__":
    log.info("Starting Flask dashboard locally...")
    app.run(host="0.0.0.0", port=8080, debug=True)