import json
from pathlib import Path

STORES_DIR = Path("config/stores")


def list_stores() -> list[str]:
    """Return list of store IDs (filenames without .json)."""
    if not STORES_DIR.exists():
        STORES_DIR.mkdir(parents=True)
    return sorted(f.stem for f in STORES_DIR.glob("*.json"))


def load_store(store_id: str) -> dict | None:
    path = STORES_DIR / f"{store_id}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_store(store_id: str, data: dict):
    path = STORES_DIR / f"{store_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def delete_store(store_id: str):
    path = STORES_DIR / f"{store_id}.json"
    if path.exists():
        path.unlink()


def create_store(store_id: str, name: str) -> dict:
    data = {
        "id": store_id,
        "name": name,
        "niche": {
            "keywords_cn": [],
            "keywords_en": [],
            "keywords_vn": [],
            "category_shopee_id": 0,
            "max_price_cny": 50,
            "min_margin_percent": 30,
            "min_margin_percentage": 0.15,
            "price_multiplier": 2.5,
            "competitor_search_enabled": True,
        },
        "sources": {
            "1688": {"enabled": True, "dropship_filter": True, "max_pages": 3, "delay_seconds": 3},
            "aliexpress": {"enabled": True, "max_pages": 3, "delay_seconds": 2},
        },
        "supplier_scoring": {
            "enabled": True, "min_score_to_pass": 0.4,
        },
        "trend_hijacker": {
            "enabled": True, "spike_threshold": 1.5,
            "scan_interval_hours": 6, "max_keywords_to_track": 20,
        },
        "virtual_hub": {
            "hub_name": "default", "auto_map_enabled": True,
        },
        "customer_care": {
            "enabled": True, "review_voucher_discount_pct": 5,
            "cooldown_between_messages_hours": 48,
        },
        "order_management": {
            "enabled": True, "auto_fulfill": False, "fulfillment_buffer_hours": 2,
        },
        "cashflow": {
            "lead_time_days": 7, "shopee_settlement_days": 3,
            "buffer_days": 2, "daily_capital_reserve": 500000,
        },
        "shopee": {
            "partner_id": "", "partner_key": "", "shop_id": "",
            "access_token": "", "refresh_token": "",
            "environment": "uat", "default_logistic_id": 80001,
            "pre_order_days": 7, "item_status": "UNLIST",
            "cookies": {},
        },
        "schedule": {
            "crawl_interval_hours": 24, "post_per_day": 10, "post_interval_minutes": 60,
        },
    }
    save_store(store_id, data)
    return data
