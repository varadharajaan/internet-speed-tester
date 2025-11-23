import app

print("Testing load_minute_data function...")
try:
    df = app.load_minute_data(60)
    print(f"Loaded {len(df)} rows")
    if not df.empty:
        print(f"Avg download: {df['download_avg'].mean():.2f}")
        print(f"P50 download: {df['download_avg'].quantile(0.50):.2f}")
    else:
        print("DataFrame is empty!")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
