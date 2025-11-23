"""
Simple explanation: Why Average and Median can be different
"""

print("=" * 70)
print("SIMPLE EXAMPLE: 7 people's salaries")
print("=" * 70)

# Example: 7 people's annual salaries
salaries = [30000, 35000, 40000, 45000, 50000, 55000, 500000]

print("\nSalaries:")
for i, salary in enumerate(salaries, 1):
    print(f"  Person {i}: ${salary:,}")

# Calculate average
average = sum(salaries) / len(salaries)
print(f"\nAverage (Mean): ${average:,.2f}")

# Calculate median (middle value when sorted)
sorted_salaries = sorted(salaries)
median = sorted_salaries[len(sorted_salaries) // 2]
print(f"Median (P50):   ${median:,}")

print("\n" + "=" * 70)
print("EXPLANATION:")
print("=" * 70)
print(f"""
The MEDIAN is ${median:,} because:
  - It's the MIDDLE value when sorted
  - 3 people earn less, 3 people earn more
  - Represents "typical" salary

The AVERAGE is ${average:,.2f} because:
  - It's the sum of all salaries divided by 7
  - The CEO earning $500,000 PULLS the average UP
  - But it doesn't affect the median!

Which is more representative of a "typical" salary?
  → MEDIAN! Because most people earn $30-55k, not $107k
""")

print("=" * 70)
print("YOUR INTERNET SPEED DATA (Same concept!)")
print("=" * 70)

# Your actual speed data (simplified)
speeds = [
    # 172 tests below 100 Mbps (27.2%)
    *[50] * 172,  # Representing low-speed tests
    # 58 tests 100-150 Mbps (9.2%)
    *[125] * 58,
    # 49 tests 150-180 Mbps (7.7%)
    *[165] * 49,
    # 285 tests 180-200 Mbps (45.0%)
    *[190] * 285,  # MOST of your tests!
    # 69 tests above 200 Mbps (10.9%)
    *[205] * 69,
]

avg_speed = sum(speeds) / len(speeds)
median_speed = sorted(speeds)[len(speeds) // 2]

print(f"\n633 total speed tests:")
print(f"  Average:  {avg_speed:.2f} Mbps")
print(f"  Median:   {median_speed:.2f} Mbps")

print(f"""
Why is Median HIGHER than Average?

1. MOST tests (45%) are in the 180-200 Mbps range
   → This is where the MEDIAN sits (typical performance)

2. BUT you have 172 tests (27%) below 100 Mbps
   → These LOW outliers pull the AVERAGE down

3. The median doesn't care about HOW LOW the slow tests are
   → It only cares about the MIDDLE position

Think of it this way:
  - Your connection TYPICALLY runs at ~187 Mbps (median)
  - But occasional poor performance drags average to ~154 Mbps
  - Average is affected by extremes, median is NOT
""")

print("\n" + "=" * 70)
print("VISUAL REPRESENTATION")
print("=" * 70)

# Create a simple histogram
bins = [
    ("< 100 Mbps", 172, 27.2),
    ("100-150", 58, 9.2),
    ("150-180", 49, 7.7),
    ("180-200", 285, 45.0),  # ← MEDIAN is here!
    (">= 200", 69, 10.9),
]

for label, count, pct in bins:
    bar = "█" * int(pct / 2)  # Scale for display
    arrow = " ← MEDIAN is here (middle test #317)" if "180-200" in label else ""
    print(f"{label:>12}: {bar} {count} tests ({pct:.1f}%){arrow}")

print(f"\nAverage is pulled down by the 172 low-speed tests")
print(f"Median sits in the largest cluster (180-200 Mbps)")

print("\n" + "=" * 70)
print("BOTTOM LINE")
print("=" * 70)
print("""
Your statistics are CORRECT!

- Median (187 Mbps) = Your TYPICAL speed (most common performance)
- Average (154 Mbps) = Mathematical mean (affected by poor tests)

This is NORMAL and happens when you have:
  ✓ A cluster of good performance (180-200 Mbps)
  ✓ Some bad outliers (< 100 Mbps)
  ✓ The bad tests pull average down, but don't move median much
""")
