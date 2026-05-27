#!/usr/bin/env python3
import json, sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.publisher.shopee import ShopeeClient
from src.models.product import ProductSource, ProductProcessed, ShopeeProduct
from src.utils.logger import setup_logger
logger = setup_logger("publish_script")

def load_captions(store_id: str) -> list[dict]:
    p = Path("data") / store_id / "captions.json"
    if not p.exists():
        logger.error(f"No captions found at {p}. Run process_images + generate_captions first.")
        return []
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def load_store_cfg(store_id: str) -> dict:
    p = Path("config/stores") / f"{store_id}.json"
    if not p.exists():
        logger.error(f"Store config not found: {p}")
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def main():
    if len(sys.argv) < 2:
        print("Cách dùng: python scripts/post_to_shopee.py <store_id> [số_lượng]")
        print("  Ví dụ: python scripts/post_to_shopee.py leo-nui")
        print("  Đăng sản phẩm lên Shopee từ captions.json")
        sys.exit(1)

    store_id = sys.argv[1]
    config = load_store_cfg(store_id)
    if not config:
        return

    shopee_cfg = config.get("shopee", {})
    if not shopee_cfg.get("partner_id") or not shopee_cfg.get("partner_key"):
        logger.error("Shopee not configured. Set partner_id, partner_key in store config.")
        return

    captions = load_captions(store_id)
    if not captions:
        return

    client = ShopeeClient(config)
    niche_name = config.get("niche", {}).get("keywords_vn", [store_id])[0]
    max_items = int(sys.argv[2]) if len(sys.argv) > 2 else len(captions)

    # Load pricing report (if any)
    pricing_report_path = Path("data") / store_id / "pricing_report.json"
    pricing_map = {}
    if pricing_report_path.exists():
        try:
            with open(pricing_report_path, encoding="utf-8") as pf:
                for entry in json.load(pf):
                    pricing_map[entry.get("product_id")] = entry
        except Exception:
            pass

    results = []
    try:
        for i, cap in enumerate(captions[:max_items], 1):
            pid = cap.get("product_id", f"item_{i}")
            logger.info(f"[{i}/{min(max_items, len(captions))}] {pid}")

            # Check pricing report: skip unprofitable products
            final_price_vnd = cap.get("price_vnd", 0)
            if pid in pricing_map:
                p_entry = pricing_map[pid]
                if not p_entry.get("profitable", True):
                    logger.warning(f"  Skipping {pid}: không có lợi nhuận (giá đối thủ quá thấp)")
                    results.append({**cap, "shopee_status": "unprofitable",
                                    "shopee_error": "price_too_low"})
                    continue
                final_price_vnd = p_entry.get("final_price_vnd", final_price_vnd)

            # Upload images
            image_ids = []
            for img_path in cap.get("images_processed", [])[:9]:
                if Path(img_path).exists():
                    iid = client.upload_image(img_path)
                    if iid:
                        image_ids.append(iid)

            if not image_ids:
                logger.warning(f"  No images uploaded, skip")
                results.append({**cap, "shopee_status": "no_images"})
                continue

            src = ProductSource(id=pid, title_cn=cap.get("title_cn", ""), price_cny=cap.get("price_cny", 0),
                                original_price_cny=cap.get("price_cny", 0), image_urls=[], description_cn="",
                                category_name_cn=niche_name)
            pp = ProductProcessed(source=src, images_processed=image_ids, title_vi=cap.get("title_vi", ""),
                                  description_vi=cap.get("description", ""), bullet_points=cap.get("bullet_points", []),
                                  hashtags=cap.get("hashtags", []), price_vnd=final_price_vnd)
            sp = ShopeeProduct(product=pp, image_ids=image_ids,
                               category_id=config.get("niche", {}).get("category_shopee_id", 0),
                               logistic_id=shopee_cfg.get("default_logistic_id", 80001))

            item_id = client.add_item(sp)
            if item_id:
                logger.info(f"  Created: {item_id}")
                results.append({**cap, "shopee_status": "created", "shopee_item_id": item_id})
            else:
                logger.error(f"  Failed to create item")
                results.append({**cap, "shopee_status": "failed"})
    finally:
        client.close()

    out = Path("data") / store_id / "published.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    success = sum(1 for r in results if r.get("shopee_status") == "created")
    logger.info(f"Done. {success}/{len(results)} items created. Results saved to {out}")

if __name__ == "__main__":
    main()
