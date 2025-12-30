#!/usr/bin/env python3
import datetime
import json
import os
import time
import subprocess
import requests
import platform
import re
import pytz

# --- Shared module imports ----------------------------------------------------
from shared import get_config, get_logger, get_s3_client
from shared.logging import log_execution

# --- Configuration via shared module ------------------------------------------
config = get_config()
log = get_logger(__name__)
s3 = get_s3_client()

# Convenience aliases
S3_BUCKET = config.s3_bucket
TIMEZONE = pytz.timezone(config.timezone)
SPEEDTEST_TIMEOUT = config.speedtest_timeout
PUBLIC_IP_API = config.public_ip_api

# Multi-host configuration (from config or env vars)
HOST_ID = os.getenv("HOST_ID", config.host_id)
HOST_NAME = os.getenv("HOST_NAME", config.host_name)
HOST_LOCATION = os.getenv("HOST_LOCATION", config.host_location)
HOST_ISP = os.getenv("HOST_ISP", config.host_isp)

import socket
HOSTNAME = socket.gethostname()

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
        ip = requests.get(PUBLIC_IP_API, timeout=5).text.strip()
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

    # Always include acceptance flags to prevent interactive blocking
    base_args = ["--format=json", "--accept-license", "--accept-gdpr"]

    cmds = []
    if os.path.exists(local_speedtest):
        cmds.append([local_speedtest, *base_args])
    cmds.extend([
        ["speedtest", *base_args],
        ["ookla-speedtest", *base_args],
    ])

    last_err = None

    # Windows: suppress window
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
                creationflags=creationflags,
                check=False,
            )

            stdout = (res.stdout or "").strip()
            stderr = (res.stderr or "").strip()

            if res.returncode == 0 and stdout:
                data = json.loads(stdout)

                dl_bps = float(data.get("download", {}).get("bandwidth", 0.0)) * 8.0
                ul_bps = float(data.get("upload", {}).get("bandwidth", 0.0)) * 8.0
                dl, ul = dl_bps / 1_000_000.0, ul_bps / 1_000_000.0
                ping = float(data.get("ping", {}).get("latency", 0.0))

                server = data.get("server", {}) or {}
                result_url = (data.get("result", {}) or {}).get("url", "")

                ts_utc = datetime.datetime.now(datetime.UTC).replace(tzinfo=pytz.utc)
                ts_ist = ts_utc.astimezone(TIMEZONE)

                log.info(f"Ookla result: {dl:.2f} Mbps ↓ / {ul:.2f} Mbps ↑ / {ping:.2f} ms")
                return normalize_record(
                    dl, ul, ping,
                    server.get("name"), server.get("city"),
                    server.get("country"), server.get("host"), server.get("id"),
                    ts_utc, ts_ist, result_url
                )

            # Non-zero or empty stdout: log enough context to debug
            last_err = f"rc={res.returncode} stderr={stderr[:500]} stdout={stdout[:200]}"
            log.warning(f"Ookla CLI failed: {last_err}")

        except subprocess.TimeoutExpired:
            # Hard-kill any stuck speedtest.exe on Windows
            if platform.system() == "Windows":
                subprocess.run(["taskkill", "/IM", "speedtest.exe", "/F", "/T"],
                               capture_output=True, text=True)
            last_err = f"Timed out after {SPEEDTEST_TIMEOUT}s"
            log.error(f"Ookla CLI timed out: {' '.join(cmd)}")

        except Exception as e:
            last_err = str(e)
            log.exception("Ookla CLI execution error")

    raise RuntimeError(f"Ookla CLI failed: {last_err}")


# ===============================
# AWS UPLOAD
# ===============================
def check_minute_bucket_exists(rounded_ist):
    """Check if data already exists for this minute bucket (duplicate prevention)."""
    year, month, day, hour, minute = ist_parts(rounded_ist)
    prefix = f"host={HOST_ID}/year={year}/month={month}/day={day}/hour={hour}/minute={minute}/"
    
    try:
        response = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix, MaxKeys=1)
        exists = response.get('KeyCount', 0) > 0
        if exists:
            log.info(f"[{HOST_ID}] Data already exists for minute bucket {minute}, skipping upload")
        return exists
    except Exception as e:
        log.warning(f"Failed to check minute bucket: {e}")
        return False  # On error, allow upload to proceed


def upload_to_s3(rec, source_label, rounded_ist):
    """Upload speed test result to S3 with host-prefixed key structure."""
    year, month, day, hour, minute = ist_parts(rounded_ist)
    
    # Add host metadata to the record
    rec["host_id"] = HOST_ID
    rec["host_name"] = HOST_NAME
    rec["host_location"] = HOST_LOCATION
    rec["host_isp"] = HOST_ISP
    
    # Use host-prefixed S3 key for multi-host support
    key = f"host={HOST_ID}/year={year}/month={month}/day={day}/hour={hour}/minute={minute}/speed_data_{source_label}_{minute}_{int(time.time())}.json"
    s3.put_object(Bucket=S3_BUCKET, Key=key, Body=json.dumps(rec, indent=2), ContentType="application/json")
    log.info(f"[{HOST_ID}] Uploaded to s3://{S3_BUCKET}/{key}")

# ===============================
# MAIN TASK
# ===============================
@log_execution
def perform_speedtest():
    rounded_ist = round_to_15min(datetime.datetime.now(TIMEZONE))
    
    # Check if data already exists for this minute bucket (prevent duplicates from catch-up runs)
    if check_minute_bucket_exists(rounded_ist):
        log.info(f"Skipping speedtest - data already exists for {rounded_ist.strftime('%Y-%m-%d %H:%M')}")
        return
    
    connection_type, wifi_name = get_connection_type()
    log.info(f"Detected connection: {connection_type}" + (f" ({wifi_name})" if wifi_name else ""))
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

LOCK_PATH = os.path.join(os.getcwd(), "collector.lock")

def acquire_lock():
    try:
        fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False

def release_lock():
    try:
        os.remove(LOCK_PATH)
    except FileNotFoundError:
        pass

if __name__ == "__main__":
    if not acquire_lock():
        sys.exit(0)
    try:
        log.info("Starting 15-min scheduled speed test job...")
        perform_speedtest()
        log.info("Speed test job finished successfully.")
    finally:
        release_lock()