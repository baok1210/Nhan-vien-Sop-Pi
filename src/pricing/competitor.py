import json, re, logging, urllib.parse
from pathlib import Path
from typing import Optional

from curl_cffi import requests as curl_requests

from src.utils.exchange_rate import calculate_final_price
from src.utils.logger import setup_logger

logger = setup_logger("competitor_pricing")

COMPETITOR_OFFSET = 1000
MIN_QUERY_LENGTH = 5


def search_shopee_products(
    keyword: str,
    cookies: Optional[dict] = None,
    max_results: int = 10,
) -> list[dict]:
    keyword = keyword.strip()
    if len(keyword) < MIN_QUERY_LENGTH:
        logger.debug(f"Keyword too short ({len(keyword)} chars), skipping")
        return []

    results = _try_cookie_method(keyword, cookies, max_results)
    if results:
        return results

    results = _try_playwright_method(keyword, max_results)
    if results:
        return results

    logger.warning(f"All Shopee search methods failed for '{keyword[:40]}'")
    return []


def _try_cookie_method(keyword: str, cookies: Optional[dict], max_results: int) -> list[dict]:
    if not cookies:
        logger.debug("No Shopee cookies available for cookie method")
        return []

    s = curl_requests.Session()
    s.impersonate = "chrome123"
    for name, value in cookies.items():
        s.cookies.set(name, value, domain="shopee.vn")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": f"https://shopee.vn/search?keyword={urllib.parse.quote(keyword)}",
        "x-requested-with": "XMLHttpRequest",
    }

    url = (
        "https://shopee.vn/api/v4/search/search_items"
        f"?by=relevancy&keyword={urllib.parse.quote(keyword)}"
        f"&limit={max_results}&newest=0&order=desc&page_type=search&version=2"
    )

    try:
        resp = s.get(url, headers=headers, timeout=20)
        if resp.status_code != 200:
            logger.debug(f"Cookie method: HTTP {resp.status_code}")
            return []
        data = resp.json()
        err = data.get("error")
        if err and err != 0:
            logger.debug(f"Cookie method: API error {err}")
            return []
        items = data.get("items", [])
        extracted = []
        for item in items:
            ib = item.get("item_brief", item)
            pm = ib.get("price_min", 0)
            if pm:
                extracted.append({
                    "name": ib.get("name", ""),
                    "price_min": pm / 100000,
                    "price_max": ib.get("price_max", 0) / 100000 if ib.get("price_max") else pm / 100000,
                    "historical_sold": ib.get("historical_sold", 0),
                    "item_id": str(ib.get("itemid", "")),
                    "shop_id": str(ib.get("shopid", "")),
                    "is_ad": False,
                })
        if extracted:
            logger.info(f"Cookie method: {len(extracted)} products found for '{keyword[:40]}'")
        return extracted
    except Exception as e:
        logger.debug(f"Cookie method failed: {e}")
        return []
    finally:
        s.close()


def _try_playwright_method(keyword: str, max_results: int) -> list[dict]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.debug("Playwright not installed")
        return []

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(
                locale="vi-VN",
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
            )
            page = context.new_page()

            search_data = {}

            def on_response(resp):
                if "search_items" in resp.url:
                    try:
                        search_data["body"] = resp.json()
                    except Exception:
                        pass

            page.on("response", on_response)

            page.goto(
                f"https://shopee.vn/search?keyword={urllib.parse.quote(keyword)}",
                timeout=30000,
                wait_until="networkidle",
            )

            if "body" not in search_data:
                logger.debug("Playwright method: no search API response captured")
                browser.close()
                return []

            data = search_data["body"]
            err = data.get("error")
            if err and err != 0:
                logger.debug(f"Playwright method: API error {err}")
                browser.close()
                return []

            items = data.get("items", [])
            extracted = []
            for item in items:
                ib = item.get("item_brief", item)
                pm = ib.get("price_min", 0)
                if pm:
                    extracted.append({
                        "name": ib.get("name", ""),
                        "price_min": pm / 100000,
                        "price_max": ib.get("price_max", 0) / 100000 if ib.get("price_max") else pm / 100000,
                        "historical_sold": ib.get("historical_sold", 0),
                        "item_id": str(ib.get("itemid", "")),
                        "shop_id": str(ib.get("shopid", "")),
                        "is_ad": False,
                    })

            browser.close()
            if extracted:
                logger.info(f"Playwright method: {len(extracted)} products found for '{keyword[:40]}'")
            return extracted

    except Exception as e:
        logger.debug(f"Playwright method failed: {e}")
        return []


def get_lowest_competitor_price(
    keyword: str,
    cookies: Optional[dict] = None,
) -> Optional[float]:
    products = search_shopee_products(keyword, cookies)
    if not products:
        return None

    prices = sorted(
        [p["price_min"] for p in products if p["price_min"] > 0 and not p.get("is_ad")]
    )
    if not prices:
        return None
    return prices[0]


def _calc_pricing_parts(price_cny: float, config: dict, product_id: str):
    """Calculate cost_vnd, floor_price, and current_price from CNY price + config."""
    from src.utils.exchange_rate import calculate_final_price

    niche = config.get("niche", {})
    multiplier = float(niche.get("price_multiplier", 2.5))
    min_margin = float(niche.get("min_margin_percentage", 0.15))

    current_price = calculate_final_price(price_cny, multiplier)
    cost_vnd = calculate_final_price(price_cny, 1.0)
    floor_price = int(cost_vnd * (1 + min_margin))

    logger.info(
        f"[{product_id}] price_cny={price_cny}, cost_vnd={cost_vnd:,.0f}, "
        f"current_price={current_price:,.0f}, min_margin={min_margin*100:.0f}%, "
        f"floor_price={floor_price:,.0f}"
    )
    return current_price, cost_vnd, floor_price


def _decide_final_price(
    lowest_price: float | None,
    current_price: int,
    floor_price: int,
    product_id: str,
) -> int:
    if lowest_price is not None:
        target_price = int(lowest_price - COMPETITOR_OFFSET)
        final_price = max(target_price, floor_price)
        logger.info(
            f"[{product_id}] lowest_competitor={lowest_price:,.0f}, "
            f"target={target_price:,.0f}, final={final_price:,.0f}"
        )
    else:
        final_price = current_price
        logger.info(
            f"[{product_id}] no competitor data, using default_price={final_price:,.0f}"
        )
    return final_price


def apply_dynamic_pricing(
    price_cny: float,
    title_vi: str,
    config: dict,
    product_id: str = "",
) -> int:
    current_price, _, floor_price = _calc_pricing_parts(price_cny, config, product_id)

    niche = config.get("niche", {})
    shopee_cookies = config.get("shopee", {}).get("cookies")
    search_enabled = niche.get("competitor_search_enabled", True)

    lowest_price = None
    if search_enabled and title_vi:
        lowest_price = get_lowest_competitor_price(title_vi, shopee_cookies)

    return _decide_final_price(lowest_price, current_price, floor_price, product_id)


# ── Batch analysis (button-triggered pricing update) ─────────────────


def _load_store_captions(store_id: str) -> tuple[list[dict], dict]:
    captions_path = Path("data") / store_id / "captions.json"
    config_path = Path("config/stores") / f"{store_id}.json"
    if not captions_path.exists():
        raise FileNotFoundError(f"No captions.json found at {captions_path}")
    if not config_path.exists():
        raise FileNotFoundError(f"No store config found at {config_path}")
    with open(captions_path, encoding="utf-8") as f:
        captions = json.load(f)
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)
    return captions, config


def analyze_store_pricing(store_id: str) -> dict:
    captions, config = _load_store_captions(store_id)
    niche = config.get("niche", {})
    shopee_cookies = config.get("shopee", {}).get("cookies")
    multiplier = float(niche.get("price_multiplier", 2.5))
    min_margin = float(niche.get("min_margin_percentage", 0.15))
    search_enabled = niche.get("competitor_search_enabled", True)

    report = []
    total = len(captions)
    profitable_count = 0
    unprofitable_count = 0

    for cap in captions:
        pid = cap.get("product_id", "?")
        price_cny = cap.get("price_cny", 0)
        title_vi = cap.get("title_vi", "")

        current_price = calculate_final_price(price_cny, multiplier)
        cost_vnd = calculate_final_price(price_cny, 1.0)
        floor_price = int(cost_vnd * (1 + min_margin))

        lowest_price = None
        if search_enabled and title_vi and len(title_vi.strip()) >= MIN_QUERY_LENGTH:
            lowest_price = get_lowest_competitor_price(title_vi, shopee_cookies)

        if lowest_price is not None:
            target_price = int(lowest_price - COMPETITOR_OFFSET)
            final_price = max(target_price, floor_price)
            profitable = final_price >= floor_price and final_price > cost_vnd
        else:
            final_price = current_price
            profitable = True

        entry = {
            "product_id": pid, "price_cny": price_cny, "title_vi": title_vi,
            "cost_vnd": cost_vnd, "current_price": current_price,
            "floor_price": floor_price,
            "lowest_competitor_price": lowest_price,
            "target_price": int(lowest_price - COMPETITOR_OFFSET) if lowest_price else None,
            "final_price_vnd": final_price, "profitable": profitable,
        }
        report.append(entry)
        if profitable:
            profitable_count += 1
        else:
            unprofitable_count += 1

    out_path = Path("data") / store_id / "pricing_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    summary = {
        "store_id": store_id, "total": total,
        "profitable": profitable_count, "unprofitable": unprofitable_count,
        "skipped_products": [e["product_id"] for e in report if not e["profitable"]],
        "report_path": str(out_path),
    }
    logger.info(
        f"Pricing analysis done: {profitable_count}/{total} profitable, "
        f"{unprofitable_count} unprofitable"
    )
    return summary


async def async_apply_dynamic_pricing(
    price_cny: float,
    title_vi: str,
    config: dict,
    product_id: str = "",
) -> int:
    from src.utils.exchange_rate import async_calculate_final_price

    niche = config.get("niche", {})
    multiplier = float(niche.get("price_multiplier", 2.5))
    min_margin = float(niche.get("min_margin_percentage", 0.15))

    current_price = await async_calculate_final_price(price_cny, multiplier)
    cost_vnd = await async_calculate_final_price(price_cny, 1.0)
    floor_price = int(cost_vnd * (1 + min_margin))

    logger.info(
        f"[{product_id}] price_cny={price_cny}, cost_vnd={cost_vnd:,.0f}, "
        f"current_price={current_price:,.0f}, min_margin={min_margin*100:.0f}%, "
        f"floor_price={floor_price:,.0f}"
    )

    shopee_cookies = config.get("shopee", {}).get("cookies")
    search_enabled = niche.get("competitor_search_enabled", True)

    lowest_price = None
    if search_enabled and title_vi:
        lowest_price = get_lowest_competitor_price(title_vi, shopee_cookies)

    return _decide_final_price(lowest_price, current_price, floor_price, product_id)
