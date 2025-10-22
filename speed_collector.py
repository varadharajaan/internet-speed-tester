#!/usr/bin/env python3
import datetime, json, os, time, subprocess, boto3, pytz
import socket
import requests

try:
    import speedtest as stlib
except Exception:
    stlib = None

S3_BUCKET = "vd-speed-test"
AWS_REGION = "ap-south-1"
TIMEZONE = pytz.timezone("Asia/Kolkata")
HOSTNAME = socket.gethostname()
print(f"🏠 Hostname: {HOSTNAME}")

s3 = boto3.client("s3", region_name=AWS_REGION)

def round_to_15min(dt):
    minute = (dt.minute // 15) * 15
    return dt.replace(minute=minute, second=0, microsecond=0)

def next_15min_boundary(dt):
    minute = ((dt.minute // 15) + 1) * 15
    if minute >= 60:
        dt = dt.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)
    else:
        dt = dt.replace(minute=minute, second=0, microsecond=0)
    return dt

def get_public_ip():
    try:
        ip = requests.get("https://api.ipify.org").text.strip()
        print(f"🌐 Public IP: {ip}")
        return ip
    except Exception:
        return "Unknown"

def ist_parts(dt_ist):
    return (dt_ist.strftime("%Y"),
            dt_ist.strftime("%Y%m"),
            dt_ist.strftime("%Y%m%d"),
            dt_ist.strftime("%Y%m%d%H"),
            dt_ist.strftime("%Y%m%d%H%M"))

def normalize_record(dl, ul, ping, server_name, server_city, server_country, server_host, server_id, ts_utc=None, ts_ist=None, result_url=""):
    if ts_utc is None:
        ts_utc = datetime.datetime.now(datetime.UTC).replace(tzinfo=pytz.utc)
    if ts_ist is None:
        ts_ist = ts_utc.astimezone(TIMEZONE)
    rec = {
        "timestamp_utc": ts_utc.isoformat(),
        "timestamp_ist": ts_ist.strftime("%Y-%m-%d %H:%M:%S IST"),
        "download_mbps": f"{round(float(dl), 2)} Mbps",
        "upload_mbps": f"{round(float(ul), 2)} Mbps",
        "ping_ms": round(float(ping), 2),
        "server_name": server_name or "",
        "server_city": server_city or "",
        "server_country": server_country or "",
        "server_host": server_host or "",
        "server_id": int(server_id) if str(server_id).isdigit() else (server_id or ""),
    }
    if result_url:
        rec["result_url"] = result_url
    return rec

def run_ookla_cli():
    cmds = [["speedtest", "--format=json"], ["ookla-speedtest", "--format=json"]]
    last_err = None

    # Create startup info to hide the console window
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE


    for cmd in cmds:
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                startupinfo=startupinfo,  # 👈suppresses the window
                creationflags=subprocess.CREATE_NO_WINDOW,  # 👈 ensures no console window
                timeout=180,
            )
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
                dl_bps = float(data.get("download", {}).get("bandwidth", 0.0)) * 8.0
                ul_bps = float(data.get("upload", {}).get("bandwidth", 0.0)) * 8.0
                dl = dl_bps / 1_000_000.0
                ul = ul_bps / 1_000_000.0
                ping = float(data.get("ping", {}).get("latency", 0.0))
                server = data.get("server", {}) or {}
                server_name = server.get("name", "")
                server_city = server.get("location") or server.get("city") or ""
                server_country = server.get("country", "")
                server_host = server.get("host", "")
                server_id = server.get("id", "")
                result_url = data.get("result", {}).get("url", "")
                ts_utc = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
                ts_ist = ts_utc.astimezone(pytz.timezone("Asia/Kolkata"))
                return normalize_record(
                    dl, ul, ping, server_name, server_city,
                    server_country, server_host, server_id,
                    ts_utc, ts_ist, result_url
                )
            else:
                last_err = res.stderr or "Unknown error"
        except Exception as e:
            last_err = str(e)
    raise RuntimeError(f"Ookla CLI failed: {last_err}")

def run_python_speedtest():
    if stlib is None:
        raise RuntimeError("python speedtest-cli not installed (pip install speedtest-cli)")
    st = stlib.Speedtest()
    best = st.get_best_server()
    st.download(); st.upload()
    res = st.results.dict()
    dl = float(res.get("download", 0.0))/1_000_000.0
    ul = float(res.get("upload", 0.0))/1_000_000.0
    ping = float(res.get("ping", 0.0))
    city = (best.get("name") if isinstance(best, dict) else "") or res.get("server", {}).get("name", "")
    sponsor = (best.get("sponsor") if isinstance(best, dict) else "") or res.get("server", {}).get("sponsor", "")
    server_name = (f"{sponsor} {city}".strip() if sponsor else city) or sponsor
    country = (best.get("country") if isinstance(best, dict) else "") or res.get("server", {}).get("country", "")
    host = (best.get("host") if isinstance(best, dict) else "") or res.get("server", {}).get("host", "")
    sid = (best.get("id") if isinstance(best, dict) else "") or res.get("server", {}).get("id", "")
    ts_utc = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
    ts_ist = ts_utc.astimezone(TIMEZONE)
    return normalize_record(dl, ul, ping, server_name, city, country, host, sid, ts_utc, ts_ist)

def upload_to_s3(rec, source_label, rounded_ist):
    year, month, day, hour, minute = ist_parts(rounded_ist)
    key = f"year={year}/month={month}/day={day}/hour={hour}/minute={minute}/speed_data_{source_label}_{minute}_{int(time.time())}.json"
    s3.put_object(Bucket=S3_BUCKET, Key=key, Body=json.dumps(rec, indent=2), ContentType="application/json")
    print(f"Uploaded: s3://{S3_BUCKET}/{key}")

def main():
    print("🚀 Running single speed test collection...")
    rounded_ist = round_to_15min(datetime.datetime.now(TIMEZONE))

    try:
        rec_ookla = run_ookla_cli()
        public_ip = get_public_ip()
        rec_ookla["public_ip"] = public_ip
        upload_to_s3(rec_ookla, "ookla", rounded_ist)
    except Exception as e:
        print(f"⚠️ Ookla test failed: {e}")

    # try:
    #     rec_py = run_python_speedtest()
    #     public_ip = get_public_ip()
    #     rec_py["public_ip"] = public_ip
    #     upload_to_s3(rec_py, "python", rounded_ist)
    # except Exception as e:
    #     print(f"⚠️ Python speedtest test failed: {e}")

    print("✅ Completed speed tests and uploaded to S3.")

if __name__ == "__main__":
    main()