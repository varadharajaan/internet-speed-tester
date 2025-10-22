#!/usr/bin/env python3
from flask import Flask, render_template, request, jsonify
import boto3, json, pandas as pd
import pytz, datetime, os

S3_BUCKET = "vd-speed-test"
AWS_REGION = "ap-south-1"
TIMEZONE = pytz.timezone("Asia/Kolkata")

app = Flask(__name__)
s3 = boto3.client("s3", region_name=AWS_REGION)

# --- CONFIG LOADING ---
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
DEFAULT_THRESHOLD = 200.0
if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            DEFAULT_THRESHOLD = float(cfg.get("expected_speed_mbps", DEFAULT_THRESHOLD))
    except Exception:
        pass


# --- DAILY AGGREGATED DATA ---
def list_summary_files():
    prefix = "aggregated/"
    paginator = s3.get_paginator("list_objects_v2")
    files = []
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".json"):
                files.append(obj["Key"])
    return files


def load_summaries():
    recs = []
    for key in list_summary_files():
        obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
        recs.append(json.loads(obj["Body"].read().decode("utf-8")))
    if not recs:
        return pd.DataFrame(columns=["date_ist"])
    
    df = pd.DataFrame(recs)

    # Parse date safely
    df["date_ist"] = pd.to_datetime(df["date_ist"], errors="coerce")
    df["date_ist_str"] = df["date_ist"].dt.strftime("%Y-%m-%d")

    # Extract stats from 'overall'
    df["download_avg"] = df["overall"].apply(lambda x: x.get("download_mbps", {}).get("avg") if isinstance(x, dict) else None)
    df["upload_avg"] = df["overall"].apply(lambda x: x.get("upload_mbps", {}).get("avg") if isinstance(x, dict) else None)
    df["ping_avg"] = df["overall"].apply(lambda x: x.get("ping_ms", {}).get("avg") if isinstance(x, dict) else None)

    # Servers and URLs
    df["top_server"] = df["servers_top"].apply(lambda arr: arr[0] if isinstance(arr, list) and arr else "")
    df["result_urls"] = df["result_urls"].apply(lambda x: x if isinstance(x, list) else [])

    # Preserve both 'public_ips' and single 'public_ip'
    if "public_ips" in df.columns:
        df["public_ips"] = df["public_ips"].apply(lambda x: x if isinstance(x, list) else [])
        df["public_ip"] = df["public_ips"].apply(lambda x: x[0] if x else "")
    elif "public_ip" in df.columns:
        df["public_ips"] = df["public_ip"].apply(lambda x: [x] if isinstance(x, str) and x else [])
    else:
        df["public_ips"] = [[] for _ in range(len(df))]
        df["public_ip"] = ""

    return df.sort_values("date_ist")


def load_summaries_bk():
    recs = []
    for key in list_summary_files():
        obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
        recs.append(json.loads(obj["Body"].read().decode("utf-8")))
    if not recs:
        return pd.DataFrame(columns=["date_ist"])
    df = pd.DataFrame(recs)
    df["date_ist"] = pd.to_datetime(df["date_ist"], errors="coerce")
    df["download_avg"] = df["overall"].apply(lambda x: x["download_mbps"]["avg"] if isinstance(x, dict) else None)
    df["upload_avg"] = df["overall"].apply(lambda x: x["upload_mbps"]["avg"] if isinstance(x, dict) else None)
    df["ping_avg"] = df["overall"].apply(lambda x: x["ping_ms"]["avg"] if isinstance(x, dict) else None)
    df["top_server"] = df["servers_top"].apply(lambda arr: (arr[0] if (isinstance(arr, list) and len(arr) > 0) else ""))
    df["result_urls"] = df["result_urls"].apply(lambda x: x if isinstance(x, list) else [])
    df["public_ip"] = df["public_ips"].apply(lambda x: x[0] if isinstance(x, list) and x else "") if "public_ips" in df.columns else df.get("public_ip", "")
    df["date_ist_str"] = df["date_ist"].dt.strftime("%Y-%m-%d")
    return df.sort_values("date_ist")


# --- DETAILED (15-MIN) DATA ---
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
                    "ping_avg": float(data.get("ping_ms", 0)),
                    "top_server": f"{data.get('server_name', '')} – {data.get('server_host', '')} – {data.get('server_city', '')} ({data.get('server_country', '')})".strip(),
                    "public_ip": data.get("public_ip", ""),
                    "result_urls": [data.get("result_url")] if data.get("result_url") else []
                })
            except Exception as e:
                print(f"Skip {key}: {e}")

    if not results:
        return pd.DataFrame(columns=["timestamp"])
    df = pd.DataFrame(results)
    df["date_ist"] = df["timestamp"]
    df["date_ist_str"] = df["timestamp"].dt.strftime("%Y-%m-%d %H:%M")
    return df.sort_values("timestamp")


# --- ANOMALY DETECTION ---
def detect_anomalies(df, threshold):
    if df.empty:
        df["download_anomaly"] = []
        df["ping_anomaly"] = []
        df["below_expected"] = []
        return df
    dl_mean = df["download_avg"].mean()
    ping_mean = df["ping_avg"].mean()
    df["download_anomaly"] = df["download_avg"] < (0.7 * dl_mean)
    df["ping_anomaly"] = df["ping_avg"] > (1.5 * ping_mean)
    df["below_expected"] = df["download_avg"] < threshold
    return df


# --- DASHBOARD ROUTE ---
@app.route("/")
def dashboard():
    period = int(request.args.get("days", 7))
    mode = request.args.get("mode", "daily")
    show_urls = request.args.get("urls", "no").lower() == "yes"
    threshold = request.args.get("threshold")

    try:
        threshold = float(threshold) if threshold not in (None, "") else DEFAULT_THRESHOLD
    except Exception:
        threshold = DEFAULT_THRESHOLD

    if mode == "minute":
        df = load_minute_data(period)
    else:
        df = load_summaries()

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
            # minute mode: aggregate to per-day level
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
def api_data():
    mode = request.args.get("mode", "daily")
    threshold = float(request.args.get("threshold", DEFAULT_THRESHOLD))
    df = load_minute_data(7) if mode == "minute" else load_summaries()
    df = detect_anomalies(df, threshold)
    return jsonify(df.to_dict(orient="records"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)