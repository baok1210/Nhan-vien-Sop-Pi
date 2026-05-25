import json, sqlite3, time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from src.publisher.shopee import ShopeeClient
from src.utils.logger import setup_logger

logger = setup_logger("order_manager")

ORDERS_DB = Path("data/order_tracking.db")
FULFILLMENT_FILE = Path("data/orders_to_fulfill.json")
PROCESSED_ORDERS_TABLE = "processed_orders"
ORDER_STATUS_FILTER = "READY_TO_SHIP"


def _init_db():
    ORDERS_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(ORDERS_DB))
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {PROCESSED_ORDERS_TABLE} (
            order_sn TEXT PRIMARY KEY,
            store_id TEXT NOT NULL,
            processed_at TEXT NOT NULL,
            item_count INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    return conn


class OrderManager:
    def __init__(self, config: dict, store_id: str):
        self.store_id = store_id
        self.store_dir = Path("data") / store_id
        self.client = ShopeeClient(config) if self._has_creds(config) else None
        self.db_conn = _init_db()
        self.orders: list[dict] = []
        self.fulfillment: list[dict] = []

    def _has_creds(self, config: dict) -> bool:
        s = config.get("shopee", {})
        return bool(s.get("partner_id") and s.get("partner_key") and s.get("shop_id"))

    def _is_processed(self, order_sn: str) -> bool:
        cur = self.db_conn.execute(
            f"SELECT 1 FROM {PROCESSED_ORDERS_TABLE} WHERE order_sn = ?",
            (order_sn,)
        )
        return cur.fetchone() is not None

    def _mark_processed(self, order_sn: str, item_count: int):
        self.db_conn.execute(
            f"INSERT OR REPLACE INTO {PROCESSED_ORDERS_TABLE} (order_sn, store_id, processed_at, item_count) "
            f"VALUES (?, ?, ?, ?)",
            (order_sn, self.store_id, datetime.now().isoformat(), item_count),
        )
        self.db_conn.commit()

    # ── Order fetching ────────────────────────────────────────────

    def fetch_orders(self, days_back: int = 7) -> list[dict]:
        if not self.client:
            logger.warning("Shopee credentials not configured")
            return []

        time_from = int((datetime.now() - timedelta(days=days_back)).timestamp())
        path = "/api/v2/order/get_order_list"
        data = {
            "time_range_field": "create_time",
            "time_from": time_from,
            "time_to": int(time.time()),
            "page_size": 100,
            "cursor": "",
            "order_status": ORDER_STATUS_FILTER,
            "response_optional_fields": "order_sn,order_status,item_list,total_amount,create_time",
        }

        all_orders = []
        while True:
            result = self.client._request("POST", path, data)
            resp = result.get("response", {})
            order_list = resp.get("order_list", [])
            all_orders.extend(order_list)
            cursor = resp.get("next_cursor", "")
            if not resp.get("more", False) or not cursor:
                break
            data["cursor"] = cursor

        # Filter out already-processed
        new_orders = [o for o in all_orders if not self._is_processed(o.get("order_sn", ""))]
        logger.info(f"Orders: {len(all_orders)} total, {len(new_orders)} new")
        self.orders = new_orders
        return new_orders

    def fetch_order_details(self, order_sns: list[str]) -> list[dict]:
        if not self.client or not order_sns:
            return []

        path = "/api/v2/order/get_order_detail"
        data = {
            "order_sn_list": order_sns,
            "response_optional_fields": (
                "order_sn,item_list,order_status,shipping_carrier,"
                "recipient_address,total_amount,estimated_shipping_fee"
            ),
        }
        result = self.client._request("POST", path, data)
        return result.get("response", {}).get("order_list", [])

    # ── Source mapping ────────────────────────────────────────────

    def _load_published_products(self) -> dict[str, dict]:
        path = self.store_dir / "published.json"
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                items = json.load(f)
            if isinstance(items, list):
                return {str(it.get("shopee_item_id", it.get("product_id", ""))): it for it in items}
            return items
        except Exception as e:
            logger.warning(f"Failed to load published.json: {e}")
            return {}

    def _load_product_pool(self) -> dict[str, dict]:
        path = Path("data") / "product_pool.json"
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                items = json.load(f)
            if isinstance(items, list):
                return {it.get("id", ""): it for it in items}
            return items
        except Exception:
            return {}

    def map_orders_to_source(self) -> list[dict]:
        published = self._load_published_products()
        pool = self._load_product_pool()
        fulfillment = []

        for order in self.orders:
            order_sn = order.get("order_sn", "")
            items = order.get("item_list", [])
            if not items:
                continue

            detail = self.fetch_order_details([order_sn])
            detail_map = {}
            if detail:
                for d in detail:
                    if d.get("order_sn") == order_sn:
                        detail_map = d
                        break

            recipient = detail_map.get("recipient_address", {})
            addr_parts = [
                recipient.get("full_address", ""),
                recipient.get("city", ""),
                recipient.get("state", ""),
                recipient.get("zip_code", ""),
            ]
            customer_address = ", ".join(p for p in addr_parts if p)

            for item in items:
                shopee_item_id = str(item.get("item_id", ""))
                model_id = str(item.get("model_id", ""))
                qty = item.get("quantity", 1)

                mapped = published.get(shopee_item_id, {})
                source_id = mapped.get("product_id",
                             mapped.get("source_id", ""))
                source_url = mapped.get("detail_url",
                             mapped.get("source_url", ""))
                source_img = mapped.get("images_processed", [None])[0] or ""
                source_title_cn = mapped.get("title_cn", "")
                variation_name = mapped.get("variation_label",
                                  mapped.get("tier_variation", ""))

                # Try pool fallback
                if not source_id:
                    for pid, pitem in pool.items():
                        if pitem.get("detail_url", "") == source_url:
                            source_id = pid
                            source_title_cn = pitem.get("title_cn", "")
                            source_img = (pitem.get("image_urls") or [None])[0] or ""
                            break

                fulfillment.append({
                    "order_sn": order_sn,
                    "shopee_item_id": shopee_item_id,
                    "model_id": model_id,
                    "quantity": qty,
                    "source_product_id": source_id,
                    "source_url": source_url,
                    "source_image": source_img,
                    "source_title_cn": source_title_cn,
                    "source_variation_name": variation_name,
                    "customer_address": customer_address,
                    "order_total": detail_map.get("total_amount", ""),
                    "shipping_carrier": detail_map.get("shipping_carrier", ""),
                    "created_at": datetime.now().isoformat(),
                })

            self._mark_processed(order_sn, len(items))

        self.fulfillment = fulfillment
        return fulfillment

    # ── Export ────────────────────────────────────────────────────

    def export_fulfillment(self):
        if not self.fulfillment:
            logger.info("No fulfillment data to export")
            return

        FULFILLMENT_FILE.parent.mkdir(parents=True, exist_ok=True)
        existing = []
        if FULFILLMENT_FILE.exists():
            try:
                with open(FULFILLMENT_FILE, encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                pass

        existing_sns = {e["order_sn"] for e in existing}
        merged = existing + [f for f in self.fulfillment if f["order_sn"] not in existing_sns]

        with open(FULFILLMENT_FILE, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        logger.info(f"Exported {len(self.fulfillment)} items to {FULFILLMENT_FILE}")

    # ── Sync entry point ──────────────────────────────────────────

    def sync(self, days_back: int = 7) -> int:
        new_orders = self.fetch_orders(days_back)
        if not new_orders:
            logger.info("No new orders to process")
            return 0
        self.map_orders_to_source()
        self.export_fulfillment()
        return len(self.fulfillment)

    def close(self):
        if self.client:
            self.client.close()
        self.db_conn.close()
