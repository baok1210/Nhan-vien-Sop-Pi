"""Virtual Hub & Cross-Docking Optimizer — maps China domestic tracking numbers
to Shopee Vietnam tracking numbers for warehouse re-labeling.

Supports batch tracking number import from 1688, mapping to Shopee orders,
and generating re-labeling manifests.
"""
import json, re, csv, io
from pathlib import Path
from datetime import datetime
from typing import Optional
from src.utils.logger import setup_logger

logger = setup_logger("virtual_hub")

TRACKING_DB = Path("data/tracking_map.json")


class VirtualHub:
    def __init__(self, config: dict, store_id: str):
        self.store_id = store_id
        self.store_dir = Path("data") / store_id
        hub_cfg = config.get("virtual_hub", {})
        self.hub_name = hub_cfg.get("hub_name", "default")
        self.auto_map = hub_cfg.get("auto_map_enabled", True)
        self._mappings: list[dict] = self._load_mappings()

    def _load_mappings(self) -> list[dict]:
        if TRACKING_DB.exists():
            try:
                with open(TRACKING_DB, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_mappings(self):
        TRACKING_DB.parent.mkdir(parents=True, exist_ok=True)
        with open(TRACKING_DB, "w", encoding="utf-8") as f:
            json.dump(self._mappings, f, ensure_ascii=False, indent=2)

    # ── Import China tracking numbers ─────────────────────────────

    def import_tracking_csv(self, csv_content: str) -> int:
        """Import tracking numbers from CSV (1688 export format).
        Expected columns: order_id, tracking_number, carrier, product_name, quantity
        """
        imported = 0
        reader = csv.DictReader(io.StringIO(csv_content))
        for row in reader:
            cn_tracking = row.get("tracking_number", "").strip()
            if not cn_tracking:
                continue
            if any(m["cn_tracking"] == cn_tracking for m in self._mappings):
                continue  # already exists
            self._mappings.append({
                "cn_tracking": cn_tracking,
                "cn_carrier": row.get("carrier", "未知快递"),
                "source_order_id": row.get("order_id", ""),
                "product_name": row.get("product_name", ""),
                "quantity": int(row.get("quantity", 1)),
                "store_id": self.store_id,
                "imported_at": datetime.now().isoformat(),
                "shopee_tracking": "",
                "shopee_order_sn": "",
                "status": "pending",
            })
            imported += 1

        if imported:
            self._save_mappings()
            logger.info(f"Imported {imported} China tracking numbers")
        return imported

    def import_tracking_json(self, tracking_list: list[dict]) -> int:
        """Import tracking data from structured JSON (from 1688 API/webhook)."""
        imported = 0
        for item in tracking_list:
            cn_tracking = item.get("tracking_number", "").strip()
            if not cn_tracking:
                continue
            if any(m["cn_tracking"] == cn_tracking for m in self._mappings):
                continue
            self._mappings.append({
                "cn_tracking": cn_tracking,
                "cn_carrier": item.get("carrier", "unknown"),
                "source_order_id": item.get("source_order_id", ""),
                "product_name": item.get("product_name", ""),
                "quantity": int(item.get("quantity", 1)),
                "store_id": self.store_id,
                "imported_at": datetime.now().isoformat(),
                "shopee_tracking": "",
                "shopee_order_sn": "",
                "status": "pending",
            })
            imported += 1

        if imported:
            self._save_mappings()
            logger.info(f"Imported {imported} tracking records from JSON")
        return imported

    # ── Map to Shopee orders ──────────────────────────────────────

    def load_fulfillment_orders(self) -> list[dict]:
        path = Path("data") / "orders_to_fulfill.json"
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def auto_map_tracking(self) -> int:
        """Auto-map pending China tracking to Shopee orders by matching
        source_order_id or product name."""
        if not self.auto_map:
            return 0

        fulfillment = self.load_fulfillment_orders()
        pending = [m for m in self._mappings if m["status"] == "pending"]
        mapped = 0

        for p in pending:
            src_order = p.get("source_order_id", "").strip()
            for order in fulfillment:
                # Match by source product ID
                if src_order and src_order == order.get("source_product_id", ""):
                    p["shopee_order_sn"] = order.get("order_sn", "")
                    p["shopee_tracking"] = order.get("shipping_carrier", "") + "_" + order.get("order_sn", "")
                    p["status"] = "mapped"
                    p["mapped_at"] = datetime.now().isoformat()
                    p["customer_address"] = order.get("customer_address", "")
                    mapped += 1
                    logger.info(f"Mapped: {p['cn_tracking']} → {p['shopee_order_sn']}")
                    break
                # Fallback: match by product name keyword
                elif p.get("product_name") and order.get("source_title_cn"):
                    pn_keywords = re.findall(r"[\u4e00-\u9fff]{2,}", p["product_name"])
                    src_keywords = re.findall(r"[\u4e00-\u9fff]{2,}", order.get("source_title_cn", ""))
                    common = set(pn_keywords) & set(src_keywords)
                    if len(common) >= 2:
                        p["shopee_order_sn"] = order.get("order_sn", "")
                        p["shopee_tracking"] = order.get("shipping_carrier", "") + "_" + order.get("order_sn", "")
                        p["status"] = "mapped"
                        p["mapped_at"] = datetime.now().isoformat()
                        p["customer_address"] = order.get("customer_address", "")
                        p["match_method"] = "keyword_fuzzy"
                        mapped += 1
                        logger.info(f"Mapped (fuzzy): {p['cn_tracking']} → {p['shopee_order_sn']}")
                        break

        if mapped:
            self._save_mappings()
        return mapped

    def manual_map(self, cn_tracking: str, shopee_order_sn: str) -> bool:
        """Manually map a China tracking number to a Shopee order."""
        for m in self._mappings:
            if m["cn_tracking"] == cn_tracking:
                m["shopee_order_sn"] = shopee_order_sn
                m["shopee_tracking"] = f"manual_{shopee_order_sn}"
                m["status"] = "mapped"
                m["mapped_at"] = datetime.now().isoformat()
                self._save_mappings()
                logger.info(f"Manual map: {cn_tracking} → {shopee_order_sn}")
                return True
        return False

    # ── Re-labeling manifest ──────────────────────────────────────

    def generate_manifest(self, status_filter: str = "mapped") -> list[dict]:
        """Generate re-labeling manifest for warehouse workers.
        Each entry includes: cn_tracking, shopee_tracking, customer_address,
        store_id, product_name, quantity.
        """
        items = [m for m in self._mappings if m["status"] == status_filter]
        manifest = []
        for m in items:
            manifest.append({
                "cn_tracking": m["cn_tracking"],
                "shopee_tracking": m["shopee_tracking"],
                "shopee_order_sn": m["shopee_order_sn"],
                "customer_address": m.get("customer_address", ""),
                "store_id": m.get("store_id", ""),
                "product_name": m.get("product_name", ""),
                "quantity": m.get("quantity", 1),
                "status": m["status"],
            })

        if manifest:
            path = self.store_dir / f"relabel_manifest_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            logger.info(f"Manifest: {len(manifest)} items → {path}")

        return manifest

    def generate_label_csv(self, manifest: list[dict]) -> str:
        """Generate CSV for label printer (barcode scanner format)."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["CN Tracking", "Shopee Tracking", "Customer", "Store", "Product", "Qty"])
        for m in manifest:
            writer.writerow([
                m["cn_tracking"],
                m["shopee_tracking"],
                m.get("customer_address", "")[:50],
                m["store_id"],
                m.get("product_name", "")[:30],
                m["quantity"],
            ])
        return output.getvalue()

    # ── Status dashboard ──────────────────────────────────────────

    def status_summary(self) -> dict:
        total = len(self._mappings)
        pending = sum(1 for m in self._mappings if m["status"] == "pending")
        mapped = sum(1 for m in self._mappings if m["status"] == "mapped")
        return {
            "total": total,
            "pending": pending,
            "mapped": mapped,
            "hub": self.hub_name,
        }
