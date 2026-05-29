"""Test script — test discovery features"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.discovery import add_to_pool, load_pool, discover_niches

pool = load_pool()
print(f"Pool before: {len(pool)}")

suggestions = discover_niches(min_products=2)
print(f"Suggestions: {len(suggestions)}")
for s in suggestions:
    print(f'  {s["icon"]} {s["category"]}: {s["product_count"]} products')
