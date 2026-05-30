import json, math, urllib.parse, time, random
from pathlib import Path
from datetime import datetime
from collections import Counter
from src.utils.logger import setup_logger

logger = setup_logger("market_research")

RESEARCH_CACHE = Path("data/research_cache.json")
POOL_FILE = Path("data/product_pool.json")
SHOPEE_COOKIE_FILE = Path("data/shopee_cookies.json")


def _load_shopee_cookies() -> dict | None:
    if SHOPEE_COOKIE_FILE.exists():
        try:
            raw = json.loads(SHOPEE_COOKIE_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                return {c["name"]: c["value"] for c in raw if "name" in c and "value" in c}
        except Exception:
            pass
    return None


SHOPEE_CATEGORIES = [
    {"id": 1, "name": "Điện thoại & Phụ kiện", "icon": "📱"},
    {"id": 2, "name": "Thiết bị điện tử", "icon": "💻"},
    {"id": 3, "name": "Máy tính & Laptop", "icon": "🖥️"},
    {"id": 4, "name": "Mẹ & Bé", "icon": "👶"},
    {"id": 5, "name": "Thời trang nữ", "icon": "👗"},
    {"id": 6, "name": "Thời trang nam", "icon": "👔"},
    {"id": 7, "name": "Giày dép nữ", "icon": "👠"},
    {"id": 8, "name": "Giày dép nam", "icon": "👞"},
    {"id": 9, "name": "Túi xách & Phụ kiện", "icon": "👜"},
    {"id": 10, "name": "Đồng hồ & Trang sức", "icon": "⌚"},
    {"id": 11, "name": "Sức khỏe & Làm đẹp", "icon": "💄"},
    {"id": 12, "name": "Nhà cửa & Đời sống", "icon": "🏠"},
    {"id": 13, "name": "Thể thao & Du lịch", "icon": "⚽"},
    {"id": 14, "name": "Ô tô & Xe máy", "icon": "🚗"},
    {"id": 15, "name": "Sách & Văn phòng phẩm", "icon": "📚"},
    {"id": 16, "name": "Đồ chơi & Thú cưng", "icon": "🧸"},
    {"id": 17, "name": "Thực phẩm & Đồ uống", "icon": "🍎"},
    {"id": 18, "name": "Sản phẩm khác", "icon": "📦"},
]

SHOPEE_SEARCH_KEYWORDS = {
    "Điện thoại & Phụ kiện": "ốp điện thoại, sạc dự phòng, cáp sạc, tai nghe, giá đỡ điện thoại",
    "Thiết bị điện tử": "loa bluetooth, đồng hồ thông minh, máy ảnh kỹ thuật số, thiết bị thông minh",
    "Máy tính & Laptop": "chuột máy tính, bàn phím, túi laptop, lót chuột, webcam",
    "Mẹ & Bé": "đồ chơi trẻ em, bỉm tã, bình sữa, quần áo trẻ em, xe đẩy",
    "Thời trang nữ": "váy đầm, áo sơ mi nữ, quần jean nữ, đồ bộ nữ, chân váy",
    "Thời trang nam": "áo thun nam, quần jean nam, áo sơ mi nam, quần short nam, đồ thể thao nam",
    "Giày dép nữ": "giày cao gót, giày thể thao nữ, sandal nữ, dép nữ, bốt nữ",
    "Giày dép nam": "giày thể thao nam, giày da nam, giày tây, dép nam, sandal nam",
    "Túi xách & Phụ kiện": "túi xách nữ, balo, ví da, thắt lưng, kính mát",
    "Đồng hồ & Trang sức": "đồng hồ nam, đồng hồ nữ, vòng tay, nhẫn, bông tai",
    "Sức khỏe & Làm đẹp": "mỹ phẩm, dưỡng da, son môi, kem chống nắng, mặt nạ",
    "Nhà cửa & Đời sống": "đồ gia dụng, nội thất phòng ngủ, dụng cụ nhà bếp, đèn trang trí, thảm trải sàn",
    "Thể thao & Du lịch": "dụng cụ thể thao, balo du lịch, lều cắm trại, túi ngủ, giày thể thao",
    "Ô tô & Xe máy": "phụ kiện xe hơi, mũ bảo hiểm, đồ chơi ô tô, gương xe máy, bọc ghế",
    "Sách & Văn phòng phẩm": "sách, bút, vở, sticker, đồ dùng văn phòng",
    "Đồ chơi & Thú cưng": "đồ chơi cho mèo, phụ kiện chó, đồ chơi thông minh, bóng đá mini",
    "Thực phẩm & Đồ uống": "trà, cà phê, đồ ăn vặt, gia vị, thực phẩm chức năng",
    "Sản phẩm khác": "quà tặng, đồ trang trí, handmade, quà lưu niệm",
}

SOURCE_CONFIG_FIELDS = {
    "min_price": {"label": "Giá tối thiểu (₫)", "type": "number", "default": 10000, "min": 0, "max": 100000000},
    "max_price": {"label": "Giá tối đa (₫)", "type": "number", "default": 2000000, "min": 0, "max": 100000000},
    "category_ids": {"label": "ID ngành hàng (phân cách bằng dấu phẩy)", "type": "text", "default": "", "help": "Để trống để quét tất cả ngành hàng"},
}

RANKING_WEIGHTS = {
    "margin_potential": 0.35,
    "competition_quality": 0.30,
    "demand": 0.20,
    "entry_barrier": 0.15,
}


def _load_cached() -> dict | None:
    if RESEARCH_CACHE.exists():
        try:
            data = json.loads(RESEARCH_CACHE.read_text(encoding="utf-8"))
            age = time.time() - data.get("scanned_at", 0)
            if age < 86400:
                return data
        except Exception:
            pass
    return None


def _save_cache(data: dict):
    RESEARCH_CACHE.parent.mkdir(parents=True, exist_ok=True)
    data["scanned_at"] = time.time()
    RESEARCH_CACHE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _search_shopee_category(keyword: str, max_results: int = 30) -> list[dict]:
    cookies = _load_shopee_cookies()
    cookie_str = "; ".join(f"{k}={v}" for k, v in (cookies or {}).items()) if cookies else ""

    try:
        from curl_cffi import requests as curl_requests
    except ImportError:
        logger.warning("curl_cffi not installed, fallback to httpx")
        return _search_shopee_httpx(keyword, max_results, cookie_str)

    s = curl_requests.Session()
    s.impersonate = "chrome123"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": f"https://shopee.vn/search?keyword={urllib.parse.quote(keyword)}",
    }
    if cookie_str:
        headers["Cookie"] = cookie_str
    url = (
        "https://shopee.vn/api/v4/search/search_items"
        f"?by=relevancy&keyword={urllib.parse.quote(keyword)}"
        f"&limit={max_results}&newest=0&order=desc&page_type=search&version=2"
    )
    try:
        resp = s.get(url, headers=headers, timeout=20)
        if resp.status_code != 200:
            return _search_shopee_playwright(keyword, max_results) if resp.status_code == 403 else []
        data = resp.json()
        if data.get("error") not in (None, 0):
            return _search_shopee_playwright(keyword, max_results)
        items = data.get("items", [])
        extracted = _parse_shopee_items(items)
        if extracted:
            return extracted
        return _search_shopee_playwright(keyword, max_results)
    except Exception as e:
        logger.debug(f"Shopee search failed for '{keyword[:30]}': {e}")
        return _search_shopee_playwright(keyword, max_results)
    finally:
        s.close()


def _parse_shopee_items(items: list) -> list[dict]:
    extracted = []
    for item in items:
        ib = item.get("item_brief", item)
        pm = ib.get("price_min", 0)
        if pm:
            extracted.append({
                "name": ib.get("name", ""),
                "price_min": pm / 100000,
                "price_max": (ib.get("price_max", pm) or pm) / 100000,
                "historical_sold": ib.get("historical_sold", 0),
                "shopid": str(ib.get("shopid", "")),
                "itemid": str(ib.get("itemid", "")),
                "rating": ib.get("item_rating", {}).get("rating_star", 0) if isinstance(ib.get("item_rating"), dict) else 0,
            })
    return extracted


def _search_shopee_playwright(keyword: str, max_results: int = 30) -> list[dict]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("playwright not installed, skip playwright search")
        return []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
                locale="vi-VN",
            )
            cookies = _load_shopee_cookies()
            if cookies:
                from playwright.sync_api import Cookie
                ctx.add_cookies([
                    {"name": k, "value": v, "domain": ".shopee.vn", "path": "/"}
                    for k, v in cookies.items()
                ])
            page = ctx.new_page()
            page.goto(
                f"https://shopee.vn/search?keyword={urllib.parse.quote(keyword)}",
                timeout=30000, wait_until="domcontentloaded"
            )
            page.wait_for_timeout(5000)
            items = page.query_selector_all("[data-sqe='item']")
            if not items:
                items = page.query_selector_all(".shopee-search-item-result__item")
            extracted = []
            for el in items[:max_results]:
                try:
                    name_el = el.query_selector("div[data-sqe='name'] a")
                    if not name_el:
                        name_el = el.query_selector("a")
                    name = name_el.inner_text().strip() if name_el else ""
                    price_str = el.inner_text()
                    import re
                    prices = re.findall(r'[\d,.]+', price_str.replace(".", "").replace(",", "."))
                    price_min = float(prices[0]) if prices else 0
                    extracted.append({
                        "name": name,
                        "price_min": price_min,
                        "price_max": price_min,
                        "historical_sold": 0,
                        "shopid": "",
                        "itemid": "",
                        "rating": 0,
                    })
                except Exception:
                    continue
            browser.close()
            return extracted
    except Exception as e:
        logger.debug(f"Playwright search failed for '{keyword[:30]}': {e}")
        return []


def _search_shopee_httpx(keyword: str, max_results: int = 30, cookie_str: str = "") -> list[dict]:
    try:
        import httpx
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }
        if cookie_str:
            headers["Cookie"] = cookie_str
        url = (
            "https://shopee.vn/api/v4/search/search_items"
            f"?by=relevancy&keyword={urllib.parse.quote(keyword)}"
            f"&limit={max_results}&newest=0&order=desc&page_type=search&version=2"
        )
        resp = httpx.get(url, headers=headers, timeout=20, follow_redirects=True)
        if resp.status_code != 200:
            return _search_shopee_playwright(keyword, max_results) if resp.status_code == 403 else []
        data = resp.json()
        if data.get("error") not in (None, 0):
            return _search_shopee_playwright(keyword, max_results)
        items = data.get("items", [])
        extracted = _parse_shopee_items(items)
        if extracted:
            return extracted
        return _search_shopee_playwright(keyword, max_results)
    except Exception as e:
        logger.debug(f"HTTPS search failed for '{keyword[:30]}': {e}")
        return _search_shopee_playwright(keyword, max_results)


def _load_pool_products() -> list[dict]:
    if POOL_FILE.exists():
        try:
            return json.loads(POOL_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _estimate_margin(avg_price_vnd: float, source_data: list[dict], cat_name: str) -> dict:
    cat_lower = cat_name.lower()
    matching = [p for p in source_data if cat_lower in (p.get("category", "") or "").lower() or cat_lower in (p.get("category_name_cn", "") or "").lower()]
    if not matching:
        matching = source_data[:50]

    source_prices = [p.get("price_cny", 0) for p in matching if p.get("price_cny", 0) > 0]
    if not source_prices:
        avg_source_cny = None
        estimated_cost_vnd = None
        margin_pct = None
    else:
        avg_source_cny = sum(source_prices) / len(source_prices)
        estimated_cost_vnd = avg_source_cny * 3500
        if avg_price_vnd > 0 and estimated_cost_vnd > 0:
            margin_pct = round((avg_price_vnd - estimated_cost_vnd) / avg_price_vnd * 100, 1)
        else:
            margin_pct = None
    return {
        "avg_source_cny": round(avg_source_cny, 2) if avg_source_cny else None,
        "estimated_cost_vnd": int(estimated_cost_vnd) if estimated_cost_vnd else None,
        "estimated_margin_pct": margin_pct,
        "matching_source_products": len(matching),
    }


def _calc_opportunity_score(avg_price: float, product_count: int, total_sold: int, unique_shops: int, margin_pct: float | None) -> float:
    scores = {}

    if avg_price >= 500000:
        scores["margin_potential"] = 1.0
    elif avg_price >= 200000:
        scores["margin_potential"] = 0.8
    elif avg_price >= 100000:
        scores["margin_potential"] = 0.6
    elif avg_price >= 50000:
        scores["margin_potential"] = 0.4
    elif avg_price >= 20000:
        scores["margin_potential"] = 0.2
    else:
        scores["margin_potential"] = 0.0

    if margin_pct is not None:
        if margin_pct >= 60:
            scores["margin_potential"] = min(1.0, scores["margin_potential"] + 0.15)
        elif margin_pct >= 40:
            scores["margin_potential"] = min(1.0, scores["margin_potential"] + 0.05)
        elif margin_pct <= 15:
            scores["margin_potential"] = max(0.0, scores["margin_potential"] - 0.2)

    if product_count == 0:
        scores["competition_quality"] = 0.0
    elif product_count < 10:
        scores["competition_quality"] = 0.3
    elif product_count < 50:
        scores["competition_quality"] = 0.7
    elif product_count < 200:
        scores["competition_quality"] = 0.9
    elif product_count < 500:
        scores["competition_quality"] = 0.7
    elif product_count < 1000:
        scores["competition_quality"] = 0.5
    else:
        scores["competition_quality"] = 0.3

    if total_sold > 0 and product_count > 0:
        avg_sold_per_product = total_sold / product_count
        if avg_sold_per_product >= 500:
            scores["demand"] = 1.0
        elif avg_sold_per_product >= 100:
            scores["demand"] = 0.8
        elif avg_sold_per_product >= 50:
            scores["demand"] = 0.6
        elif avg_sold_per_product >= 10:
            scores["demand"] = 0.4
        elif avg_sold_per_product >= 1:
            scores["demand"] = 0.2
        else:
            scores["demand"] = 0.0
    else:
        scores["demand"] = 0.2

    if avg_price >= 1000000:
        scores["entry_barrier"] = 0.2
    elif avg_price >= 500000:
        scores["entry_barrier"] = 0.4
    elif avg_price >= 200000:
        scores["entry_barrier"] = 0.6
    elif avg_price >= 50000:
        scores["entry_barrier"] = 0.8
    else:
        scores["entry_barrier"] = 0.9

    if product_count > 0 and unique_shops > 0:
        products_per_shop = product_count / unique_shops
        if products_per_shop < 3:
            scores["competition_quality"] = min(1.0, scores["competition_quality"] + 0.1)
        elif products_per_shop > 20:
            scores["competition_quality"] = max(0.0, scores["competition_quality"] - 0.2)

    total = (
        scores["margin_potential"] * RANKING_WEIGHTS["margin_potential"]
        + scores["competition_quality"] * RANKING_WEIGHTS["competition_quality"]
        + scores["demand"] * RANKING_WEIGHTS["demand"]
        + scores["entry_barrier"] * RANKING_WEIGHTS["entry_barrier"]
    )
    return round(total, 3)


def _describe_level(score: float) -> tuple[str, str]:
    if score >= 0.8:
        return "Rất tốt", "green"
    if score >= 0.6:
        return "Tốt", "#2e7d32"
    if score >= 0.4:
        return "Trung bình", "#f57f17"
    if score >= 0.2:
        return "Khó", "#e65100"
    return "Không nên", "red"


def scan_categories(min_price: int = 0, max_price: int = 0, category_ids: str = "") -> dict:
    cached = _load_cached()
    if cached:
        logger.info("Using cached research data")
        return cached

    source_data = _load_pool_products()
    results = []

    logger.info("Scanning Shopee categories...")
    for cat in SHOPEE_CATEGORIES:
        cat_name = cat["name"]
        keywords = SHOPEE_SEARCH_KEYWORDS.get(cat_name, cat_name)
        kw_list = [k.strip() for k in keywords.split(",")]

        all_products = []
        seen_items = set()
        for kw in kw_list[:3]:
            products = _search_shopee_category(kw, max_results=20)
            for p in products:
                pid = p.get("itemid", "")
                if pid and pid not in seen_items:
                    seen_items.add(pid)
                    prices = [p.get("price_min", 0), p.get("price_max", 0)]
                    if min_price > 0 or max_price > 0:
                        avg_p = sum(prices) / len(prices) if prices else 0
                        if min_price > 0 and avg_p < min_price:
                            continue
                        if max_price > 0 and avg_p > max_price:
                            continue
                    all_products.append(p)

            if products:
                time.sleep(random.uniform(0.5, 1.5))

        if not all_products:
            results.append({
                "category_id": cat["id"],
                "category_name": cat_name,
                "icon": cat["icon"],
                "avg_price": 0,
                "product_count": 0,
                "total_sold": 0,
                "unique_shops": 0,
                "avg_rating": 0,
                "estimated_margin": None,
                "opportunity_score": 0,
                "level": "Không có dữ liệu",
                "level_color": "gray",
                "recommendation": "Không đủ dữ liệu",
                "trending_keywords": [],
            })
            continue

        prices = [(p.get("price_min", 0) + p.get("price_max", 0)) / 2 for p in all_products if p.get("price_min", 0) > 0]
        avg_price = sum(prices) / len(prices) if prices else 0
        total_sold = sum(p.get("historical_sold", 0) for p in all_products)
        unique_shops = len(set(p.get("shopid", "") for p in all_products if p.get("shopid")))
        avg_rating = sum(p.get("rating", 0) for p in all_products if p.get("rating", 0) > 0)
        avg_rating = round(avg_rating / max(len([p for p in all_products if p.get("rating", 0) > 0]), 1), 2)

        margin_info = _estimate_margin(avg_price, source_data, cat_name)
        margin_pct = margin_info.get("estimated_margin_pct")

        score = _calc_opportunity_score(avg_price, len(all_products), total_sold, unique_shops, margin_pct)
        level, level_color = _describe_level(score)

        all_names = [p.get("name", "") for p in all_products if p.get("name")]
        all_words = []
        for n in all_names:
            words = n.lower().split()
            all_words.extend(w for w in words if len(w) > 3)
        trending = [w for w, c in Counter(all_words).most_common(8) if c >= 2][:5]

        results.append({
            "category_id": cat["id"],
            "category_name": cat_name,
            "icon": cat["icon"],
            "avg_price": int(avg_price),
            "product_count": len(all_products),
            "total_sold": total_sold,
            "unique_shops": unique_shops,
            "avg_rating": avg_rating,
            "estimated_margin": margin_info,
            "opportunity_score": score,
            "level": level,
            "level_color": level_color,
            "recommendation": _recommend_action(score, avg_price, len(all_products), margin_pct),
            "trending_keywords": trending,
        })
        logger.info(f"  {cat['icon']} {cat_name}: score={score} ({level})")

    results.sort(key=lambda r: -r["opportunity_score"])

    output = {
        "scanned_at": time.time(),
        "scanned_at_str": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "categories": results,
        "summary": {
            "total_categories": len(results),
            "top_opportunities": [r for r in results if r["opportunity_score"] >= 0.6],
            "avg_score": round(sum(r["opportunity_score"] for r in results) / max(len(results), 1), 3),
        },
    }
    _save_cache(output)
    return output


def _recommend_action(score: float, avg_price: float, product_count: int, margin_pct: float | None) -> str:
    if score >= 0.8:
        return "✅ Rất nên vào! Biên lợi nhuận tốt, cạnh tranh vừa phải."
    if score >= 0.6:
        parts = []
        if margin_pct is not None and margin_pct >= 40:
            parts.append("biên LN tốt")
        elif margin_pct is not None and margin_pct >= 20:
            parts.append("biên LN khá")
        if product_count < 100:
            parts.append("ít đối thủ")
        if product_count < 300:
            parts.append("còn chỗ trống")
        return f"👍 Nên cân nhắc. {', '.join(parts)}." if parts else "👍 Có tiềm năng."
    if score >= 0.4:
        return "⚠️ Cạnh tranh cao. Cần lợi thế riêng (giá tốt, sản phẩm độc đáo)."
    return "❌ Không khuyến nghị. Thị trường quá cạnh tranh hoặc biên LN thấp."
