#!/usr/bin/env python3
import datetime, json, os, time, subprocess, boto3, pytz, socket, requests, logging, sys
from logging.handlers import RotatingFileHandler
from functools import wraps
import platform

try:
    import speedtest as stlib
except Exception:
    stlib = None

# ===============================
# CONFIGURATION
# ===============================
S3_BUCKET = "vd-speed-test"
AWS_REGION = "ap-south-1"
TIMEZONE = pytz.timezone("Asia/Kolkata")
HOSTNAME = socket.gethostname()
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE_PATH = os.path.join(os.getcwd(), "speedtest.log")
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MiB
LOG_BACKUP_COUNT = 5

s3 = boto3.client("s3", region_name=AWS_REGION)

# ===============================
# CUSTOM LOGGER
# ===============================
class CustomLogger:
    def __init__(self, name=__name__, level=LOG_LEVEL):
        self.logger = logging.getLogger(name)
        if not self.logger.handlers:
            formatter = self.JsonFormatter()

            # Always log to console (CloudWatch captures stdout)
            stream_handler = logging.StreamHandler(sys.stdout)
            stream_handler.setFormatter(formatter)
            self.logger.addHandler(stream_handler)

            # Add file logging only for local runs
            if not self.is_lambda_environment():
                file_handler = RotatingFileHandler(
                    LOG_FILE_PATH, maxBytes=LOG_MAX_BYTES,
                    backupCount=LOG_BACKUP_COUNT, encoding="utf-8"
                )
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)

        self.logger.setLevel(level)
        self.logger.propagate = False

    class JsonFormatter(logging.Formatter):
        def format(self, record):
            entry = {
                "timestamp": datetime.datetime.now(TIMEZONE).strftime("%Y-%m-%d %I:%M:%S %p IST"),
                #"timestamp": datetime.datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S IST"),
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

    def debug(self, msg, *args): self.logger.debug(msg, *args)
    def info(self, msg, *args): self.logger.info(msg, *args)
    def warning(self, msg, *args): self.logger.warning(msg, *args)
    def error(self, msg, *args): self.logger.error(msg, *args)
    def exception(self, msg, *args): self.logger.exception(msg, *args)

log = CustomLogger(__name__)

# ===============================
# DECORATOR: LOG EXECUTION
# ===============================
def log_execution(func):
    """Decorator to log start, success, and failure of scheduled tasks."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        log.info(f"Starting scheduled task: {func.__name__}")
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            duration = round(time.time() - start_time, 2)
            log.info(f"Task {func.__name__} completed in {duration}s")
            return result
        except Exception as e:
            log.exception(f"Task {func.__name__} failed: {e}")
            raise
    return wrapper

# ===============================
# UTILITIES
# ===============================
def round_to_15min(dt):
    minute = (dt.minute // 15) * 15
    return dt.replace(minute=minute, second=0, microsecond=0)

def get_public_ip():
    try:
        ip = requests.get("https://api.ipify.org").text.strip()
        log.info(f"Public IP: {ip}")
        return ip
    except Exception as e:
        log.error(f"Failed to fetch public IP: {e}")
        return "Unknown"

def ist_parts(dt_ist):
    return (
        dt_ist.strftime("%Y"),
        dt_ist.strftime("%Y%m"),
        dt_ist.strftime("%Y%m%d"),
        dt_ist.strftime("%Y%m%d%H"),
        dt_ist.strftime("%Y%m%d%H%M"),
    )

def normalize_record(dl, ul, ping, server_name, server_city, server_country, server_host, server_id, ts_utc=None, ts_ist=None, result_url=""):
    if ts_utc is None:
        ts_utc = datetime.datetime.now(datetime.UTC).replace(tzinfo=pytz.utc)
    if ts_ist is None:
        ts_ist = ts_utc.astimezone(TIMEZONE)
    return {
        "timestamp_utc": ts_utc.isoformat(),
        "timestamp_ist": ts_ist.strftime("%Y-%m-%d %H:%M:%S IST"),
        "download_mbps": f"{round(float(dl), 2)} Mbps",
        "upload_mbps": f"{round(float(ul), 2)} Mbps",
        "ping_ms": f"{round(float(ping), 2)} ms",
        "server_name": server_name or "",
        "server_city": server_city or "",
        "server_country": server_country or "",
        "server_host": server_host or "",
        "server_id": int(server_id) if str(server_id).isdigit() else (server_id or ""),
        "result_url": result_url or "",
    }

# ===============================
# SPEEDTEST RUNNERS
# ===============================

@log_execution
def run_ookla_cli():
    cmds = [["speedtest", "--format=json"], ["ookla-speedtest", "--format=json"]]
    last_err = None

    # --- Windows-specific flags to suppress window ---
    creationflags = 0
    startupinfo = None
    if platform.system() == "Windows":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        creationflags = subprocess.CREATE_NO_WINDOW

    for cmd in cmds:
        try:
            log.info(f"Running Ookla CLI: {' '.join(cmd)}")

            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180,
                startupinfo=startupinfo,
                creationflags=creationflags
            )

            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
                dl_bps = float(data.get("download", {}).get("bandwidth", 0.0)) * 8.0
                ul_bps = float(data.get("upload", {}).get("bandwidth", 0.0)) * 8.0
                dl, ul = dl_bps / 1_000_000.0, ul_bps / 1_000_000.0
                ping = float(data.get("ping", {}).get("latency", 0.0))
                server = data.get("server", {}) or {}
                result_url = data.get("result", {}).get("url", "")
                ts_utc = datetime.datetime.now(datetime.UTC).replace(tzinfo=pytz.utc)
                ts_ist = ts_utc.astimezone(TIMEZONE)
                log.info(f"Ookla result: {dl:.2f} Mbps ↓ / {ul:.2f} Mbps ↑ / {ping:.2f} ms")
                return normalize_record(
                    dl, ul, ping,
                    server.get("name"), server.get("city"),
                    server.get("country"), server.get("host"), server.get("id"),
                    ts_utc, ts_ist, result_url
                )
            else:
                last_err = res.stderr or "Unknown error"

        except Exception as e:
            last_err = str(e)
            log.exception("Ookla CLI execution error")

    raise RuntimeError(f"Ookla CLI failed: {last_err}")

# ===============================
# AWS UPLOAD
# ===============================
def upload_to_s3(rec, source_label, rounded_ist):
    year, month, day, hour, minute = ist_parts(rounded_ist)
    key = f"year={year}/month={month}/day={day}/hour={hour}/minute={minute}/speed_data_{source_label}_{minute}_{int(time.time())}.json"
    s3.put_object(Bucket=S3_BUCKET, Key=key, Body=json.dumps(rec, indent=2), ContentType="application/json")
    log.info(f"Uploaded to s3://{S3_BUCKET}/{key}")

# ===============================
# MAIN TASK
# ===============================
@log_execution
def perform_speedtest():
    rounded_ist = round_to_15min(datetime.datetime.now(TIMEZONE))
    try:
        rec_ookla = run_ookla_cli()
        rec_ookla["public_ip"] = get_public_ip()
        upload_to_s3(rec_ookla, "ookla", rounded_ist)
    except Exception as e:
        log.exception(f"Ookla test failed: {e}")

    # Uncomment if you want to run Python speedtest as backup
    # try:
    #     rec_py = run_python_speedtest()
    #     rec_py["public_ip"] = get_public_ip()
    #     upload_to_s3(rec_py, "python", rounded_ist)
    # except Exception as e:
    #     log.exception(f"Python speedtest failed: {e}")

# ===============================
# ENTRY POINT
# ===============================
if __name__ == "__main__":
    log.info("Starting 15-min scheduled speed test job...")
    perform_speedtest()
    log.info("Speed test job finished successfully.")
