import json, random
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from src.publisher.shopee import ShopeeClient
from src.utils.logger import setup_logger

logger = setup_logger("flash_sale")

FLASH_SALE_PATHS = {
    "time_slots": "/api/v2/shop_flash_sale/get_flash_sale_time_slot",
    "register": "/api/v2/shop_flash_sale/register_flash_sale",
    "add_items": "/api/v2/shop_flash_sale/add_flash_sale_items",
}


class FlashSaleManager:
    def __init__(self, config: dict, store_id: str):
        self.store_id = store_id
        self.store_dir = Path("data") / store_id
        self.client = ShopeeClient(config) if self._has_creds(config) else None
        fs = config.get("flash_sale", {})
        self.discount_pct = float(fs.get("discount_percentage", 15))
        self.slots_per_day = int(fs.get("slots_per_day", 2))
        self.min_discount = float(fs.get("min_discount_percentage", 10))
        self.max_discount = float(fs.get("max_discount_percentage", 20))
        self.campaigns: list[dict] = []

    def _has_creds(self, config: dict) -> bool:
        s = config.get("shopee", {})
        return bool(s.get("partner_id") and s.get("partner_key") and s.get("shop_id"))

    # ── Time slots ────────────────────────────────────────────────

    def get_available_slots(self) -> list[dict]:
        if not self.client:
            logger.warning("Shopee credentials not configured")
            return []
        result = self.client._request("POST", FLASH_SALE_PATHS["time_slots"], {})
        slots = result.get("response", {}).get("time_slot_list", [])
        logger.info(f"Available flash sale slots: {len(slots)}")
        return slots[: self.slots_per_day]

    # ── Profitable product selection ──────────────────────────────

    def load_pricing_report(self) -> list[dict]:
        path = self.store_dir / "pricing_report.json"
        if not path.exists():
            logger.warning(f"No pricing report at {path}")
            return []
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            products = data if isinstance(data, list) else data.get("products", [])
            return [p for p in products if p.get("profitable", False)]
        except Exception as e:
            logger.error(f"Failed to load pricing report: {e}")
            return []

    def load_published(self) -> dict[str, str]:
        path = self.store_dir / "published.json"
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                items = json.load(f)
            if isinstance(items, list):
                return {it.get("product_id", ""): str(it.get("shopee_item_id", "")) for it in items if it.get("shopee_item_id")}
            return {}
        except Exception:
            return {}

    def load_captions(self) -> list[dict]:
        path = self.store_dir / "captions.json"
        if not path.exists():
            return []
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _calc_flash_price(
        self, original_price_vnd: float, floor_price: float
    ) -> tuple[float, float]:
        discount = random.uniform(self.min_discount, self.max_discount) / 100
        discounted = original_price_vnd * (1 - discount)
        flash_price = max(discounted, floor_price)
        actual_discount_pct = (1 - flash_price / original_price_vnd) * 100
        return round(flash_price, -3), round(actual_discount_pct, 1)

    def select_candidates(self, max_items: int = 20) -> list[dict]:
        pricing = self.load_pricing_report()
        captions = self.load_captions()
        published_map = self.load_published()
        caption_map = {c.get("product_id", ""): c for c in captions}

        candidates = []
        for p in pricing:
            pid = p.get("product_id", "")
            cap = caption_map.get(pid, {})
            shopee_item_id = published_map.get(pid, "")
            flash_price, actual_pct = self._calc_flash_price(
                p.get("final_price_vnd", p.get("current_price", 0)),
                p.get("floor_price", 0),
            )
            candidates.append({
                "product_id": pid,
                "shopee_item_id": shopee_item_id,
                "title_vi": cap.get("title_vi", ""),
                "original_price": int(p.get("final_price_vnd", 0)),
                "floor_price": int(p.get("floor_price", 0)),
                "flash_sale_price": int(flash_price),
                "discount_percentage": actual_pct,
                "stock": 50,
                "purchase_limit": 2,
            })

        candidates.sort(key=lambda x: -x["discount_percentage"])
        selected = candidates[:max_items]
        if selected:
            min_d = min(c["discount_percentage"] for c in selected)
            max_d = max(c["discount_percentage"] for c in selected)
            logger.info(
                f"Selected {len(selected)}/{len(candidates)} candidates "
                f"for flash sale (discount range: {min_d:.1f}% - {max_d:.1f}%)"
            )
        else:
            logger.info(f"No candidates selected (0/{len(candidates)})")
        return selected

    # ── Campaign creation ─────────────────────────────────────────

    def create_campaign(self, slot_id: int, slot_name: str) -> Optional[str]:
        if not self.client:
            return None
        data = {
            "time_slot_id": slot_id,
            "campaign_name": f"Flash Sale {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        }
        result = self.client._request("POST", FLASH_SALE_PATHS["register"], data)
        campaign_id = result.get("response", {}).get("campaign_id")
        if campaign_id:
            logger.info(f"Campaign created: {campaign_id} (slot={slot_name})")
        else:
            logger.error(f"Campaign creation failed: {result}")
        return str(campaign_id) if campaign_id else None

    def add_items(self, campaign_id: str, items: list[dict]) -> bool:
        if not self.client or not items:
            return False
        item_list = []
        for it in items:
            entry = {
                "item_id": int(it.get("shopee_item_id", it.get("product_id", 0))),
                "flash_sale_price": it.get("flash_sale_price", 0),
                "flash_sale_stock": it.get("stock", 50),
                "purchase_limit": it.get("purchase_limit", 2),
            }
            item_list.append(entry)

        data = {
            "campaign_id": int(campaign_id),
            "item_list": item_list,
        }
        result = self.client._request("POST", FLASH_SALE_PATHS["add_items"], data)
        error = result.get("error")
        if not error or error == 0:
            logger.info(f"Added {len(item_list)} items to campaign {campaign_id}")
            return True
        logger.error(f"Add items failed: {result}")
        return False

    # ── Full run ──────────────────────────────────────────────────

    def run(self, max_items: int = 20) -> list[dict]:
        if not self.client:
            logger.warning("Flash sale skipped: no Shopee credentials")
            return []

        slots = self.get_available_slots()
        if not slots:
            logger.warning("No available flash sale time slots")
            return []

        candidates = self.select_candidates(max_items)
        if not candidates:
            logger.warning("No profitable candidates for flash sale")
            return []

        results = []
        for slot in slots[: self.slots_per_day]:
            slot_id = slot.get("time_slot_id", slot.get("id", 0))
            slot_name = slot.get("display_name", str(slot_id))
            campaign_id = self.create_campaign(slot_id, slot_name)
            if not campaign_id:
                continue

            ok = self.add_items(campaign_id, candidates)
            entry = {
                "campaign_id": campaign_id,
                "slot_id": slot_id,
                "slot_name": slot_name,
                "item_count": len(candidates),
                "success": ok,
                "created_at": datetime.now().isoformat(),
            }
            results.append(entry)
            logger.info(
                f"Flash sale campaign {campaign_id}: "
                f"{len(candidates)} items, "
                f"discount {candidates[0]['discount_percentage']:.1f}% - "
                f"{candidates[-1]['discount_percentage']:.1f}%"
                if candidates else ""
            )

        self.campaigns = results
        self._save_results(results)
        return results

    def _save_results(self, results: list[dict]):
        path = self.store_dir / "flash_sale_campaigns.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(results)} campaigns to {path}")

    def close(self):
        if self.client:
            self.client.close()
