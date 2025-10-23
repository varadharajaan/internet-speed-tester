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

# --- Configuration ------------------------------------------------------------
S3_BUCKET = "vd-speed-test"
AWS_REGION = "ap-south-1"
TIMEZONE = pytz.timezone("Asia/Kolkata")

LOG_FILE_PATH = os.path.join(os.getcwd(), "dashboard.log")
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MiB
LOG_BACKUP_COUNT = 5
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
HOSTNAME = os.getenv("HOSTNAME", socket.gethostname())

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

# --- CONFIG LOADING -----------------------------------------------------------
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
DEFAULT_THRESHOLD = 200.0
if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            DEFAULT_THRESHOLD = float(cfg.get("expected_speed_mbps", DEFAULT_THRESHOLD))
        log.info(f"Loaded config.json successfully: threshold={DEFAULT_THRESHOLD}")
    except Exception as e:
        log.warning(f"Failed to load config.json: {e}")

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
    tolerance = float(cfg.get("tolerance_percent", 0)) / 100.0
    df["below_expected"] = df["download_avg"] < (threshold * (1 - tolerance))
    return df

# --- Routes -------------------------------------------------------------------
@app.route("/")
@log_execution
def dashboard():
    period = int(request.args.get("days", 7))
    mode = request.args.get("mode", "daily")
    show_urls = request.args.get("urls", "no").lower() == "yes"
    threshold = request.args.get("threshold")

    try:
        threshold = float(threshold) if threshold not in (None, "") else DEFAULT_THRESHOLD
    except Exception:
        threshold = DEFAULT_THRESHOLD

    df = load_minute_data(period) if mode == "minute" else load_summaries()
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

        if mode == "daily":
            below_count = int(df["below_expected"].sum())
            total_days = int(len(df))
        else:
            daily_below = df.groupby(df["date_ist"].dt.date)["below_expected"].any()
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

        if mode == "daily":
            best_idx = df["download_avg"].idxmax()
            worst_idx = df["download_avg"].idxmin()
            summary.update({
                "best_day": str(df.loc[best_idx, "date_ist"].date()),
                "worst_day": str(df.loc[worst_idx, "date_ist"].date())
            })

    log.info(f"Dashboard summary ready for mode={mode}, days={period}")
    return render_template(
        "dashboard.html",
        data=df.to_dict(orient="records"),
        days=period,
        summary=summary,
        show_urls=show_urls,
        threshold=threshold,
        default_threshold=DEFAULT_THRESHOLD,
        mode=mode
    )

@app.route("/api/data")
@log_execution
def api_data():
    mode = request.args.get("mode", "daily")
    threshold = float(request.args.get("threshold", DEFAULT_THRESHOLD))
    df = load_minute_data(7) if mode == "minute" else load_summaries()
    df = detect_anomalies(df, threshold)
    log.info(f"API returned {len(df)} records in mode={mode}")
    return jsonify(df.to_dict(orient="records"))

# --- Local Run ---------------------------------------------------------------
if __name__ == "__main__":
    log.info("🚀 Starting Flask dashboard locally...")
    app.run(host="0.0.0.0", port=8080, debug=True)