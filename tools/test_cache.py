#!/usr/bin/env python3
"""Test caching functionality."""
import requests
import time

BASE_URL = "http://127.0.0.1:8080"

def test_api(url, description):
    """Test an API endpoint and measure time."""
    print(f"\n{description}")
    print("-" * 50)
    start = time.time()
    try:
        resp = requests.get(url, timeout=180)
        elapsed = time.time() - start
        if resp.status_code == 200:
            data = resp.json()
            print(f"  Status: {resp.status_code}")
            print(f"  Time: {elapsed:.2f}s")
            print(f"  Records: {data.get('record_count', 'N/A')}")
            return elapsed
        else:
            print(f"  Error: {resp.status_code}")
            return None
    except Exception as e:
        print(f"  Error: {e}")
        return None

print("=" * 60)
print("CACHE TESTING")
print("=" * 60)

# Test 1: Daily mode (fast)
t1 = test_api(f"{BASE_URL}/api/data?mode=daily&days=7", "TEST 1: Daily mode (first request)")

# Test 2: Daily again (should be cached)
t2 = test_api(f"{BASE_URL}/api/data?mode=daily&days=7", "TEST 2: Daily mode (cached)")

# Test 3: Minute mode (slow first time)
t3 = test_api(f"{BASE_URL}/api/data?mode=minute&days=1", "TEST 3: Minute mode (first request - SLOW)")

# Test 4: Minute again (should be cached)
t4 = test_api(f"{BASE_URL}/api/data?mode=minute&days=1", "TEST 4: Minute mode (cached - FAST)")

# Test 5: Force reload
t5 = test_api(f"{BASE_URL}/api/data?mode=minute&days=1&force-reload=true", "TEST 5: Minute mode (force reload - SLOW)")

print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
if t1 and t2:
    print(f"Daily: {t1:.2f}s -> {t2:.2f}s (speedup: {t1/t2:.1f}x)")
if t3 and t4:
    print(f"Minute: {t3:.2f}s -> {t4:.2f}s (speedup: {t3/t4:.1f}x)")
if t4 and t5:
    print(f"Force reload: {t4:.2f}s -> {t5:.2f}s")
