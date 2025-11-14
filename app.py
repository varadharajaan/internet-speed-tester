#!/usr/bin/env python3
"""
vd-speed-test dashboard
-----------------------
Flask web app to visualize internet speed statistics from S3.
Now includes CloudWatch-compatible JSON logging and local file rotation.
"""

from flask import Flask, render_template, request, jsonify
import boto3, json, pandas as pd
import pytz, datetime, os, logging, sys
from functools import wraps
from logging.handlers import RotatingFileHandler
import socket

# --- Configuration from config.json --------------------------------------------
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
DEFAULT_CONFIG = {
    "s3_bucket": "vd-speed-test",
    "s3_bucket_hourly": "vd-speed-test-hourly-prod",
    "s3_bucket_weekly": "vd-speed-test-weekly-prod",
    "s3_bucket_monthly": "vd-speed-test-monthly-prod",
    "s3_bucket_yearly": "vd-speed-test-yearly-prod",
    "aws_region": "ap-south-1",
    "timezone": "Asia/Kolkata",
    "log_level": "INFO",
    "log_max_bytes": 10485760,
    "log_backup_count": 5,
    "expected_speed_mbps": 200,
    "tolerance_percent": 10
}

# Load config
config = DEFAULT_CONFIG.copy()
if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config.update(json.load(f))
    except Exception as e:
        print(f"Warning: Failed to load config.json: {e}. Using defaults.")

# Extract configuration values
S3_BUCKET = os.getenv("S3_BUCKET", config.get("s3_bucket"))
S3_BUCKET_HOURLY = os.getenv("S3_BUCKET_HOURLY", config.get("s3_bucket_hourly"))
S3_BUCKET_WEEKLY = os.getenv("S3_BUCKET_WEEKLY", config.get("s3_bucket_weekly"))
S3_BUCKET_MONTHLY = os.getenv("S3_BUCKET_MONTHLY", config.get("s3_bucket_monthly"))
S3_BUCKET_YEARLY = os.getenv("S3_BUCKET_YEARLY", config.get("s3_bucket_yearly"))
AWS_REGION = os.getenv("AWS_REGION", config.get("aws_region"))
TIMEZONE = pytz.timezone(config.get("timezone"))
LOG_FILE_PATH = os.path.join(os.getcwd(), "dashboard.log")
LOG_MAX_BYTES = config.get("log_max_bytes")
LOG_BACKUP_COUNT = config.get("log_backup_count")
LOG_LEVEL = os.getenv("LOG_LEVEL", config.get("log_level")).upper()
HOSTNAME = os.getenv("HOSTNAME", socket.gethostname())
DEFAULT_THRESHOLD = float(config.get("expected_speed_mbps"))
TOLERANCE_PERCENT = float(config.get("tolerance_percent"))

app = Flask(__name__)
s3 = boto3.client("s3", region_name=AWS_REGION)

# --- JSON Logger --------------------------------------------------------------
class CustomLogger:
    def __init__(self, name=__name__, level=LOG_LEVEL):
        self.logger = logging.getLogger(name)
        if not self.logger.handlers:
            formatter = self.JsonFormatter()

            # Console handler (CloudWatch captures this)
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)

            # File handler (only for local dev)
            if not self.is_lambda_environment():
                file_handler = RotatingFileHandler(
                    LOG_FILE_PATH,
                    maxBytes=LOG_MAX_BYTES,
                    backupCount=LOG_BACKUP_COUNT,
                    encoding="utf-8"
                )
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)

        self.logger.setLevel(level)
        self.logger.propagate = False

    class JsonFormatter(logging.Formatter):
        def format(self, record):
            entry = {
                "timestamp": datetime.datetime.now(datetime.UTC).isoformat() + "Z",
                "level": record.levelname,
                "message": record.getMessage(),
                "function": record.funcName,
                "module": record.module,
                "hostname": HOSTNAME,
            }
            if record.exc_info:
                entry["error"] = self.formatException(record.exc_info)
            return json.dumps(entry)

    @staticmethod
    def is_lambda_environment():
        return "AWS_LAMBDA_FUNCTION_NAME" in os.environ

    def info(self, msg, *args): self.logger.info(msg, *args)
    def warning(self, msg, *args): self.logger.warning(msg, *args)
    def error(self, msg, *args): self.logger.error(msg, *args)
    def debug(self, msg, *args): self.logger.debug(msg, *args)
    def exception(self, msg, *args): self.logger.exception(msg, *args)

log = CustomLogger(__name__)

# --- Decorator for Logging ----------------------------------------------------
def log_execution(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        log.info(f"Executing {func.__name__}")
        start = datetime.datetime.now(datetime.UTC)
        try:
            result = func(*args, **kwargs)
            elapsed = (datetime.datetime.now(datetime.UTC) - start).total_seconds()
            log.info(f"Completed {func.__name__} in {elapsed:.2f}s")
            return result
        except Exception as e:
            log.exception(f"Error in {func.__name__}: {e}")
            raise
    return wrapper

# --- S3 Utility Functions -----------------------------------------------------
@log_execution
def list_summary_files():
    prefix = "aggregated/"
    paginator = s3.get_paginator("list_objects_v2")
    files = []
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".json"):
                files.append(obj["Key"])
    log.info(f"Found {len(files)} summary files in {prefix}")
    return files

@log_execution
def load_summaries():
    recs = []
    for key in list_summary_files():
        obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
        recs.append(json.loads(obj["Body"].read().decode("utf-8")))
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

    if "public_ips" in df.columns:
        df["public_ips"] = df["public_ips"].apply(lambda x: x if isinstance(x, list) else [])
        df["public_ip"] = df["public_ips"].apply(lambda x: x[0] if x else "")
    elif "public_ip" in df.columns:
        df["public_ips"] = df["public_ip"].apply(lambda x: [x] if isinstance(x, str) and x else [])
    else:
        df["public_ips"] = [[] for _ in range(len(df))]
        df["public_ip"] = ""

    log.info(f"Loaded {len(df)} daily summaries from S3")
    return df.sort_values("date_ist")

@log_execution
def load_minute_data(days):
    cutoff = datetime.datetime.now(TIMEZONE) - datetime.timedelta(days=days)
    paginator = s3.get_paginator("list_objects_v2")
    results = []

    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix="year="):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith(".json") or "aggregated" in key:
                continue
            try:
                data = json.loads(s3.get_object(Bucket=S3_BUCKET, Key=key)["Body"].read())
                ts_str = data.get("timestamp_ist")
                if not ts_str:
                    continue
                ts = TIMEZONE.localize(datetime.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S IST"))
                if ts < cutoff:
                    continue
                results.append({
                    "timestamp": ts,
                    "download_avg": float(str(data.get("download_mbps", "0")).split()[0]),
                    "upload_avg": float(str(data.get("upload_mbps", "0")).split()[0]),
                    "ping_avg": safe_float(data.get("ping_ms", 0)),
                    "top_server": f"{data.get('server_name', '')} – {data.get('server_host', '')} – {data.get('server_city', '')} ({data.get('server_country', '')})".strip(),
                    "public_ip": data.get("public_ip", ""),
                    "connection_type": data.get("connection_type", "Unknown"),
                    "wifi_name": data.get("wifi_name", ""),
                    "result_urls": [data.get("result_url")] if data.get("result_url") else []
                })
            except Exception as e:
                log.warning(f"Skip {key}: {e}")

    if not results:
        log.warning("No minute-level data found.")
        return pd.DataFrame(columns=["timestamp"])
    df = pd.DataFrame(results)
    df["date_ist"] = df["timestamp"]
    df["date_ist_str"] = df["timestamp"].dt.strftime("%Y-%m-%d %H:%M")
    log.info(f"Loaded {len(df)} minute-level records from S3.")
    return df.sort_values("timestamp")

@log_execution
def load_hourly_data(days):
    """Load hourly aggregated data from S3_BUCKET_HOURLY."""
    cutoff = datetime.datetime.now(TIMEZONE) - datetime.timedelta(days=days)
    paginator = s3.get_paginator("list_objects_v2")
    results = []

    for page in paginator.paginate(Bucket=S3_BUCKET_HOURLY, Prefix="aggregated/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith(".json"):
                continue
            try:
                data = json.loads(s3.get_object(Bucket=S3_BUCKET_HOURLY, Key=key)["Body"].read())
                hour_str = data.get("hour_ist")
                if not hour_str:
                    continue
                # Parse "2025-10-26 14:00"
                ts = TIMEZONE.localize(datetime.datetime.strptime(hour_str, "%Y-%m-%d %H:%M"))
                if ts < cutoff:
                    continue
                results.append({
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
                    "completion_rate": data.get("completion_rate", 0)
                })
            except Exception as e:
                log.warning(f"Skip {key}: {e}")

    if not results:
        log.warning("No hourly data found.")
        return pd.DataFrame(columns=["timestamp"])
    df = pd.DataFrame(results)
    log.info(f"Loaded {len(df)} hourly records from S3.")
    return df.sort_values("timestamp")

@log_execution
def load_weekly_data(weeks=52):
    """Load weekly aggregated data from S3_BUCKET_WEEKLY, filtered by number of weeks."""
    paginator = s3.get_paginator("list_objects_v2")
    results = []
    cutoff_date = datetime.datetime.now(TIMEZONE).date() - datetime.timedelta(weeks=weeks)

    for page in paginator.paginate(Bucket=S3_BUCKET_WEEKLY, Prefix="aggregated/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith(".json"):
                continue
            try:
                data = json.loads(s3.get_object(Bucket=S3_BUCKET_WEEKLY, Key=key)["Body"].read())
                week_start = datetime.datetime.strptime(data["week_start"], "%Y-%m-%d").date()
                
                # Filter by weeks parameter
                if week_start < cutoff_date:
                    continue
                    
                results.append({
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
                    "result_urls": []
                })
            except Exception as e:
                log.warning(f"Skip {key}: {e}")

    if not results:
        log.warning(f"No weekly data found for last {weeks} weeks.")
        return pd.DataFrame(columns=["date_ist"])
    df = pd.DataFrame(results)
    log.info(f"Loaded {len(df)} weekly records from S3 (last {weeks} weeks).")
    return df.sort_values("date_ist")

@log_execution
def load_monthly_data(months=12):
    """Load monthly aggregated data from S3_BUCKET_MONTHLY, filtered by number of months."""
    paginator = s3.get_paginator("list_objects_v2")
    results = []
    cutoff_date = datetime.datetime.now(TIMEZONE).date().replace(day=1)
    cutoff_date = cutoff_date - datetime.timedelta(days=30 * months)  # Approximate months back

    for page in paginator.paginate(Bucket=S3_BUCKET_MONTHLY, Prefix="aggregated/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith(".json"):
                continue
            try:
                data = json.loads(s3.get_object(Bucket=S3_BUCKET_MONTHLY, Key=key)["Body"].read())
                month_str = data["month"]  # Format: YYYYMM
                month_date = datetime.datetime.strptime(month_str, "%Y%m").date()
                
                # Filter by months parameter
                if month_date < cutoff_date:
                    continue
                    
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
                    "result_urls": []
                })
            except Exception as e:
                log.warning(f"Skip {key}: {e}")

    if not results:
        log.warning(f"No monthly data found for last {months} months.")
        return pd.DataFrame(columns=["date_ist"])
    df = pd.DataFrame(results)
    log.info(f"Loaded {len(df)} monthly records from S3 (last {months} months).")
    return df.sort_values("date_ist")

@log_execution
def load_yearly_data(years=10):
    """Load yearly aggregated data from S3_BUCKET_YEARLY, filtered by number of years."""
    paginator = s3.get_paginator("list_objects_v2")
    results = []
    cutoff_year = datetime.datetime.now(TIMEZONE).year - years

    for page in paginator.paginate(Bucket=S3_BUCKET_YEARLY, Prefix="aggregated/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith(".json"):
                continue
            try:
                data = json.loads(s3.get_object(Bucket=S3_BUCKET_YEARLY, Key=key)["Body"].read())
                year = data["year"]
                
                # Filter by years parameter
                if year < cutoff_year:
                    continue
                    
                year_date = datetime.datetime(year, 1, 1).date()
                results.append({
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
                    "result_urls": []
                })
            except Exception as e:
                log.warning(f"Skip {key}: {e}")

    if not results:
        log.warning(f"No yearly data found for last {years} years.")
        return pd.DataFrame(columns=["date_ist"])
    df = pd.DataFrame(results)
    log.info(f"Loaded {len(df)} yearly records from S3 (last {years} years).")
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
def detect_anomalies(df, threshold):
    if df.empty:
        return df
    dl_mean = df["download_avg"].mean()
    ping_mean = df["ping_avg"].mean()
    df["download_anomaly"] = df["download_avg"] < (0.7 * dl_mean)
    df["ping_anomaly"] = df["ping_avg"] > (1.5 * ping_mean)
    tolerance = TOLERANCE_PERCENT / 100.0
    df["below_expected"] = df["download_avg"] < (threshold * (1 - tolerance))
    return df

# --- Routes -------------------------------------------------------------------
@app.route("/", methods=["GET", "POST"])
@app.route("/dashboard", methods=["GET", "POST"])
@log_execution
def dashboard():
    # Get parameters from either GET (query string) or POST (form data)
    params = request.form if request.method == "POST" else request.args
    
    period = int(params.get("days", 7))
    mode = params.get("mode", "daily")
    show_urls = params.get("urls", "no").lower() == "yes"
    threshold = params.get("threshold")

    try:
        threshold = float(threshold) if threshold not in (None, "") else DEFAULT_THRESHOLD
    except Exception:
        threshold = DEFAULT_THRESHOLD

    # Load data based on mode
    if mode == "minute":
        df = load_minute_data(period)
    elif mode == "hourly":
        df = load_hourly_data(period)
    elif mode == "weekly":
        df = load_weekly_data(period)  # period = weeks
    elif mode == "monthly":
        df = load_monthly_data(period)  # period = months
    elif mode == "yearly":
        df = load_yearly_data(period)  # period = years
    else:  # daily
        df = load_summaries()  # daily mode loads all and filters in load_summaries
    
    df = detect_anomalies(df, threshold)

    summary = {}
    if not df.empty:
        top_server_over_period = df["top_server"].mode()[0] if not df["top_server"].mode().empty else "N/A"
        public_ips = sorted({
            ip.strip()
            for vals in df.get("public_ips", [])
            if isinstance(vals, list)
            for ip in vals
            if isinstance(ip, str) and ip.strip()
        })

        if mode in ["daily", "hourly"]:
            below_count = int(df["below_expected"].sum())
            total_days = int(len(df))
        else:
            daily_below = df.groupby(df["date_ist"].dt.date if hasattr(df["date_ist"].iloc[0], 'date') else df["date_ist"])["below_expected"].any()
            below_count = int(daily_below.sum())
            total_days = int(daily_below.size)

        summary = {
            "avg_download": round(df["download_avg"].mean(), 2),
            "avg_upload": round(df["upload_avg"].mean(), 2),
            "avg_ping": round(df["ping_avg"].mean(), 2),
            "below_expected": below_count,
            "total_days": total_days,
            "top_server_over_period": top_server_over_period,
            "public_ips": public_ips,
        }

        if mode in ["daily", "hourly"]:
            best_idx = df["download_avg"].idxmax()
            worst_idx = df["download_avg"].idxmin()
            summary.update({
                "best_day": str(df.loc[best_idx, "date_ist"].date() if hasattr(df.loc[best_idx, "date_ist"], 'date') else df.loc[best_idx, "date_ist"]),
                "worst_day": str(df.loc[worst_idx, "date_ist"].date() if hasattr(df.loc[worst_idx, "date_ist"], 'date') else df.loc[worst_idx, "date_ist"])
            })

    log.info(f"Dashboard summary ready for mode={mode}, days={period}")
    
    # Calculate percentile statistics (industry standard)
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
        quick_filters["below_threshold"] = int((df["download_avg"] < threshold).sum())
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
    
    return render_template(
        "dashboard_modern.html",
        data=df.to_dict(orient="records"),
        days=period,
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
        show_urls=show_urls,
        threshold=threshold,
        default_threshold=DEFAULT_THRESHOLD,
        tolerance_percent=TOLERANCE_PERCENT,
        mode=mode
    )

@app.route("/api/data")
@log_execution
def api_data():
    mode = request.args.get("mode", "daily")
    period = int(request.args.get("days", 7))
    threshold = float(request.args.get("threshold", DEFAULT_THRESHOLD))
    
    # Load data based on mode
    if mode == "minute":
        df = load_minute_data(period)
    elif mode == "hourly":
        df = load_hourly_data(period)
    elif mode == "weekly":
        df = load_weekly_data(period)  # period = weeks
    elif mode == "monthly":
        df = load_monthly_data(period)  # period = months
    elif mode == "yearly":
        df = load_yearly_data(period)  # period = years
    else:  # daily
        df = load_summaries()  # daily mode loads all and filters in load_summaries
    
    df = detect_anomalies(df, threshold)
    log.info(f"API returned {len(df)} records in mode={mode}")
    return jsonify(df.to_dict(orient="records"))

# --- Local Run ---------------------------------------------------------------
if __name__ == "__main__":
    log.info("🚀 Starting Flask dashboard locally...")
    app.run(host="0.0.0.0", port=8080, debug=True)