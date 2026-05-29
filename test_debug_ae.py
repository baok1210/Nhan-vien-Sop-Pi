"""Debug AliExpress HTML structure"""
import sys, json, re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from src.source.browser import BrowserManager
from src.source.aliexpress import AliExpressScraper

# Use Playwright to get the page
bm = BrowserManager(headless=True)
bm.start()
ctx, page = bm.new_page()

url = "https://www.aliexpress.com/wholesale?SearchText=kitchen+accessories&page=1"
page.goto(url, timeout=60000, wait_until="networkidle")
page.wait_for_timeout(5000)
html = page.content()

# Save raw HTML for inspection
with open('data/debug_ae.html', 'w', encoding='utf-8') as f:
    f.write(html)

print(f"HTML size: {len(html)} bytes")

# Check what extractors find
scraper = AliExpressScraper({"max_pages": 1})

for name in ['_extract_from_window_state', '_extract_from_html_scripts', '_extract_item_list', '_extract_from_inline_json']:
    fn = getattr(scraper, name)
    try:
        data = fn(html)
        if data:
            print(f"\n--- {name} found {len(data)} items ---")
            if data:
                item = data[0]
                print(f"  Keys: {list(item.keys())[:10]}")
                print(f"  productId: {item.get('productId', 'N/A')}")
                print(f"  title: {str(item.get('title', ''))[:80]}")
                print(f"  price: {item.get('price', 'N/A')}")
        else:
            print(f"\n--- {name}: no data ---")
    except Exception as e:
        print(f"\n--- {name}: ERROR {e} ---")

# Also try parsel CSS
try:
    from parsel import Selector
    sel = Selector(text=html)
    for selector in [
        ".search-item-card-wrapper-gallery",
        "[class*='product-item']", 
        "[class*='card']",
        "[class*='list-item']",
        "[class*='item']",
        "div[data-role*='item']",
        "[class*='product']",
    ]:
        cards = sel.css(selector)
        print(f"\nCSS '{selector}': {len(cards)} cards")
        if cards:
            print(f"  First card HTML: {cards[0].get()[:200]}")
except Exception as e:
    print(f"parsel error: {e}")

# Check for JSON-like data
for pattern_name, pattern in [
    ("window state", r'window\.__\w+__\s*='),
    ("JSON script", r'<script[^>]*application/json[^>]*>'),
    ("productId", r'productId'),
    ("itemId", r'itemId'),
]:
    matches = re.findall(pattern, html)
    print(f"\nPattern '{pattern_name}': {len(matches)} matches")
    if matches and pattern_name != "productId":
        print(f"  First: {matches[0][:100]}")

ctx.close()
bm.stop()
