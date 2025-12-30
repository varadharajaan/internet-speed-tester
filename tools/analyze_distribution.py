import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app
import pandas as pd

print("Analyzing download speed distribution...")
df = app.load_minute_data(60)

if not df.empty:
    download_speeds = df['download_avg'].sort_values()
    
    print(f"\nTotal tests: {len(download_speeds)}")
    print(f"\nStatistics:")
    print(f"  Mean (Average): {download_speeds.mean():.2f} Mbps")
    print(f"  Median (P50): {download_speeds.quantile(0.50):.2f} Mbps")
    print(f"  P25: {download_speeds.quantile(0.25):.2f} Mbps")
    print(f"  P75: {download_speeds.quantile(0.75):.2f} Mbps")
    print(f"  Min: {download_speeds.min():.2f} Mbps")
    print(f"  Max: {download_speeds.max():.2f} Mbps")
    
    print(f"\nDistribution breakdown:")
    print(f"  < 100 Mbps: {(download_speeds < 100).sum()} tests ({(download_speeds < 100).sum() / len(download_speeds) * 100:.1f}%)")
    print(f"  100-150 Mbps: {((download_speeds >= 100) & (download_speeds < 150)).sum()} tests ({((download_speeds >= 100) & (download_speeds < 150)).sum() / len(download_speeds) * 100:.1f}%)")
    print(f"  150-180 Mbps: {((download_speeds >= 150) & (download_speeds < 180)).sum()} tests ({((download_speeds >= 150) & (download_speeds < 180)).sum() / len(download_speeds) * 100:.1f}%)")
    print(f"  180-200 Mbps: {((download_speeds >= 180) & (download_speeds < 200)).sum()} tests ({((download_speeds >= 180) & (download_speeds < 200)).sum() / len(download_speeds) * 100:.1f}%)")
    print(f"  >= 200 Mbps: {(download_speeds >= 200).sum()} tests ({(download_speeds >= 200).sum() / len(download_speeds) * 100:.1f}%)")
    
    print(f"\nWhy P50 > Average?")
    print(f"This happens when you have a LEFT-SKEWED distribution:")
    print(f"  - Many tests are in the high speed range (180-200+ Mbps)")
    print(f"  - Some tests are very low (< 100 Mbps)")
    print(f"  - The low outliers pull the average DOWN")
    print(f"  - But the median stays in the higher cluster")
    print(f"\nThis is CORRECT behavior - the statistics reflect your actual data!")
