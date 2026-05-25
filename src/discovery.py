import json
from collections import Counter, defaultdict
from pathlib import Path
from src.classifier import NICHE_CATEGORIES, classify_products
from src.utils.logger import setup_logger

logger = setup_logger("discovery")

POOL_FILE = Path("data/product_pool.json")


def load_pool() -> list[dict]:
    if POOL_FILE.exists():
        with open(POOL_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_pool(products: list[dict]):
    POOL_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(POOL_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)


def add_to_pool(new_products: list[dict]):
    pool = load_pool()
    existing_ids = {p["id"] for p in pool}
    added = 0
    for p in new_products:
        if p["id"] not in existing_ids:
            # Classify on import
            cat, conf = _classify_single(p)
            p["category"] = cat
            p["category_confidence"] = conf
            pool.append(p)
            existing_ids.add(p["id"])
            added += 1
    save_pool(pool)
    logger.info(f"Added {added} new products to pool (total: {len(pool)})")
    return added


def _classify_single(p: dict) -> tuple[str, float]:
    from src.classifier import classify_product
    title = (p.get("title_cn") or "") + " " + (p.get("title_en") or "")
    return classify_product(title, p.get("description_cn", ""))


def discover_niches(min_products: int = 3) -> list[dict]:
    pool = load_pool()
    if not pool:
        return []

    # Re-classify all products in pool
    pool = classify_products(pool)
    save_pool(pool)

    # Group by category
    groups: dict[str, list[dict]] = defaultdict(list)
    for p in pool:
        groups[p["category"]].append(p)

    suggestions = []
    for category, items in groups.items():
        if len(items) < min_products:
            continue

        # Analyze prices
        prices = [p.get("price_cny", 0) for p in items if p.get("price_cny", 0) > 0]
        avg_price = round(sum(prices) / len(prices), 2) if prices else 0

        # Top keywords from titles (English)
        all_words: list[str] = []
        for p in items:
            title = p.get("title_cn", "") or ""
            words = title.split()
            all_words.extend(w for w in words if len(w) > 1)
        top_keywords = [w for w, _ in Counter(all_words).most_common(10)]

        # Best-selling product
        best_seller = max(items, key=lambda x: x.get("sales_count", 0)) if any(p.get("sales_count", 0) for p in items) else items[0]

        niche_info = NICHE_CATEGORIES.get(category, {})
        suggestions.append({
            "category": category,
            "icon": niche_info.get("icon", "📦"),
            "product_count": len(items),
            "products": items[:20],
            "avg_price_cny": avg_price,
            "top_keywords": top_keywords[:5],
            "best_seller": best_seller,
            "total_value_cny": round(sum(p.get("price_cny", 0) for p in items), 2),
        })

    suggestions.sort(key=lambda x: -x["product_count"])
    return suggestions


def create_shop_from_suggestion(suggestion: dict) -> dict:
    """Create a store config from a niche suggestion."""
    name = suggestion["category"]
    store_id = name.lower().replace(" & ", "-").replace(" ", "-")

    # Extract keywords for each language
    items = suggestion["products"]
    cn_keywords = list(set(kw for p in items for kw in p.get("keywords_cn", []) if kw))[:5]
    en_keywords = list(set(kw for p in items for kw in p.get("keywords_en", []) if kw))[:5]

    if not cn_keywords:
        # Generate from top title words
        all_cn = [p.get("title_cn", "") for p in items if p.get("title_cn", "")]
        cn_keywords = [w for w, _ in Counter(" ".join(all_cn).split()).most_common(5)]
    if not en_keywords:
        all_en = [p.get("title_en", "") for p in items if p.get("title_en", "")]
        en_keywords = [w for w, _ in Counter(" ".join(all_en).split()).most_common(5)]

    return {
        "id": store_id,
        "name": f"{suggestion['icon']} {name}",
        "niche": {
            "keywords_cn": cn_keywords or [name],
            "keywords_en": en_keywords or [name.lower()],
            "keywords_vn": [name.lower()],
            "category_shopee_id": 0,
            "max_price_cny": suggestion["avg_price_cny"] * 1.5,
            "min_margin_percent": 30,
        },
        "sources": {
            "1688": {"enabled": True, "dropship_filter": True, "max_pages": 3, "delay_seconds": 3},
            "aliexpress": {"enabled": True, "max_pages": 3, "delay_seconds": 2},
        },
        "supplier_scoring": {"enabled": True, "min_score_to_pass": 0.4},
        "trend_hijacker": {"enabled": True, "spike_threshold": 1.5, "scan_interval_hours": 6, "max_keywords_to_track": 20},
        "virtual_hub": {"hub_name": "default", "auto_map_enabled": True},
        "customer_care": {"enabled": True, "review_voucher_discount_pct": 5, "cooldown_between_messages_hours": 48},
        "order_management": {"enabled": True, "auto_fulfill": False, "fulfillment_buffer_hours": 2},
        "cashflow": {"lead_time_days": 7, "shopee_settlement_days": 3, "buffer_days": 2, "daily_capital_reserve": 500000},
        "shopee": {
            "partner_id": "", "partner_key": "", "shop_id": "",
            "access_token": "", "refresh_token": "",
            "environment": "uat", "default_logistic_id": 80001,
            "pre_order_days": 7, "item_status": "UNLIST",
        },
        "schedule": {"crawl_interval_hours": 24, "post_per_day": 10, "post_interval_minutes": 60},
    }
