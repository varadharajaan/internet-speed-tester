#!/usr/bin/env python3
import datetime, json, os, time, subprocess, boto3, pytz, socket, requests, logging, sys
from logging.handlers import RotatingFileHandler
from functools import wraps
import platform
import re

try:
    import speedtest as stlib
except Exception:
    stlib = None

# ===============================
# CONFIGURATION FROM config.json
# ===============================
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
    "speedtest_timeout": 180,
    "public_ip_api": "https://api.ipify.org"
}

# Load config
config = DEFAULT_CONFIG.copy()
if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config.update(json.load(f))
    except Exception as e:
        print(f"Warning: Failed to load config.json: {e}. Using defaults.")

# Extract configuration values (speed_collector only uses daily bucket for minute-level data)
S3_BUCKET = os.getenv("S3_BUCKET", config.get("s3_bucket"))
AWS_REGION = os.getenv("AWS_REGION", config.get("aws_region"))
TIMEZONE = pytz.timezone(config.get("timezone"))
HOSTNAME = socket.gethostname()
LOG_LEVEL = os.getenv("LOG_LEVEL", config.get("log_level")).upper()
LOG_FILE_PATH = os.path.join(os.getcwd(), "speedtest.log")
LOG_MAX_BYTES = config.get("log_max_bytes")
LOG_BACKUP_COUNT = config.get("log_backup_count")
SPEEDTEST_TIMEOUT = config.get("speedtest_timeout")
PUBLIC_IP_API = config.get("public_ip_api")

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
def get_windows_network_type():
    """Detect network type and WiFi SSID on Windows using netsh."""
    try:
        res = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True, text=True, check=False
        )
        out = res.stdout.strip()
        
        # No WiFi interface found = Ethernet
        if not out or "There is no wireless interface" in out:
            return "Ethernet", None
        
        # Check if WiFi is actually connected (not just available)
        state_match = re.search(r"State\s*:\s*(.+)", out)
        if state_match:
            state = state_match.group(1).strip().lower()
            # If WiFi is not connected, assume Ethernet is being used
            if "connected" not in state:
                return "Ethernet", None
        
        # WiFi is connected - extract SSID
        ssid_match = re.search(r"SSID\s*:\s*(.+)", out)
        ssid = ssid_match.group(1).strip() if ssid_match else None
        
        # If no SSID found, WiFi adapter exists but not connected
        if not ssid:
            return "Ethernet", None

        # Extract band information
        radio = re.search(r"Radio type\s*:\s*(.+)", out)
        ch = re.search(r"Channel\s*:\s*(\d+)", out)
        if radio:
            val = radio.group(1).lower()
            if any(x in val for x in ["802.11a", "802.11ac", "802.11ax"]):
                return "Wi-Fi 5GHz", ssid
            if any(x in val for x in ["802.11b", "802.11g", "802.11n"]):
                return "Wi-Fi 2.4GHz", ssid
        if ch:
            c = int(ch.group(1))
            return ("Wi-Fi 5GHz" if c >= 36 else "Wi-Fi 2.4GHz"), ssid
        
        # WiFi is connected but band is unknown - still return WiFi
        return "Wi-Fi (unknown band)", ssid
    except Exception as e:
        log.warning(f"Windows network detection failed: {e}")
        return "Unknown", None


def get_linux_network_type():
    """Detect network type and WiFi SSID on Linux using iwconfig/iproute2."""
    try:
        # Find default route interface
        res = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True)
        iface = re.search(r"default via .* dev (\S+)", res.stdout)
        if not iface:
            return "Unknown", None
        iface = iface.group(1)

        # Check if wireless
        iw = subprocess.run(["iwconfig", iface], capture_output=True, text=True)
        if "no wireless extensions" in iw.stdout.lower():
            return "Ethernet", None

        # Extract SSID
        ssid_match = re.search(r'ESSID:"(.+?)"', iw.stdout)
        ssid = ssid_match.group(1) if ssid_match else None

        # Extract frequency in GHz
        freq_match = re.search(r"Frequency:(\d+\.\d+)", iw.stdout)
        if freq_match:
            freq = float(freq_match.group(1))
            if freq < 3:
                return "Wi-Fi 2.4GHz", ssid
            elif freq < 6:
                return "Wi-Fi 5GHz", ssid
        return "Wi-Fi (unknown band)", ssid
    except FileNotFoundError:
        return "Ethernet or missing iwconfig", None
    except Exception as e:
        log.warning(f"Linux network detection failed: {e}")
        return "Unknown", None


def get_macos_network_type():
    """Detect network type and WiFi SSID on macOS using airport utility."""
    try:
        cmd = ["/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport", "-I"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if not res.stdout:
            return "Ethernet", None
        if "AirPort" not in res.stdout and "SSID" not in res.stdout:
            return "Ethernet", None
        
        # Extract SSID
        ssid_match = re.search(r"SSID:\s*(.+)", res.stdout)
        ssid = ssid_match.group(1).strip() if ssid_match else None
        
        ch = re.search(r"channel:\s*(\d+)", res.stdout)
        if ch:
            c = int(ch.group(1))
            return ("Wi-Fi 5GHz" if c >= 36 else "Wi-Fi 2.4GHz"), ssid
        return "Wi-Fi (unknown band)", ssid
    except Exception as e:
        log.warning(f"macOS network detection failed: {e}")
        return "Unknown", None


def get_connection_type():
    """Auto-detect OS and determine network connection type and WiFi SSID."""
    system = platform.system()
    if system == "Windows":
        return get_windows_network_type()
    elif system == "Linux":
        return get_linux_network_type()
    elif system == "Darwin":
        return get_macos_network_type()
    else:
        return "Unknown", None

def round_to_15min(dt):
    minute = (dt.minute // 15) * 15
    return dt.replace(minute=minute, second=0, microsecond=0)

def get_public_ip():
    try:
        ip = requests.get(PUBLIC_IP_API).text.strip()
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
    # Try local Ookla CLI first (for Windows Task Scheduler), then PATH
    script_dir = os.path.dirname(os.path.abspath(__file__))
    local_speedtest = os.path.join(script_dir, "speedtest.exe")
    
    cmds = []
    if os.path.exists(local_speedtest):
        cmds.append([local_speedtest, "--format=json"])
    cmds.extend([["speedtest", "--format=json"], ["ookla-speedtest", "--format=json"]])
    
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
                timeout=SPEEDTEST_TIMEOUT,
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
    connection_type, wifi_name = get_connection_type()
    log.info(f"Detected connection: {connection_type}" + (f" ({wifi_name})" if wifi_name else ""))
    rounded_ist = round_to_15min(datetime.datetime.now(TIMEZONE))
    try:
        rec_ookla = run_ookla_cli()
        rec_ookla["public_ip"] = get_public_ip()
        rec_ookla["connection_type"] = connection_type
        if wifi_name:
            rec_ookla["wifi_name"] = wifi_name
        upload_to_s3(rec_ookla, "ookla", rounded_ist)
    except Exception as e:
        log.exception(f"Ookla test failed: {e}")

    # Uncomment if you want to run Python speedtest as backup
    # try:
    #     rec_py = run_python_speedtest()
    #     rec_py["public_ip"] = get_public_ip()
    #     rec_py["connection_type"] = connection_type
    #     if wifi_name:
    #         rec_py["wifi_name"] = wifi_name
    #     upload_to_s3(rec_py, "python", rounded_ist)
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
