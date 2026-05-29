#!/usr/bin/env python3
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.source.ali1688 import Ali1688Scraper
from src.source.aliexpress import AliExpressScraper
from src.utils.logger import setup_logger
logger = setup_logger("crawl_script")

def main():
    if len(sys.argv) < 2:
        print("Cách dùng: python scripts/crawl_products.py <store_id>")
        print("  Ví dụ: python scripts/crawl_products.py leo-nui")
        print("  Crawl sản phẩm từ 1688 và/hoặc AliExpress cho store.")
        sys.exit(1)

    store_id = sys.argv[1]
    cfg_path = Path("config/stores") / f"{store_id}.json"
    if not cfg_path.exists():
        logger.error(f"Không tìm thấy cấu hình store: {cfg_path}")
        return

    with open(cfg_path, encoding="utf-8") as f:
        config = json.load(f)

    all_products = []

    ae_cfg = config.get("sources", {}).get("aliexpress", {})
    if ae_cfg.get("enabled"):
        keywords = config.get("niche", {}).get("keywords_en", [])
        if keywords:
            scraper = AliExpressScraper(ae_cfg)
            try:
                all_products.extend(scraper.crawl_by_keywords(keywords))
            finally:
                scraper.close()

    c8_cfg = config.get("sources", {}).get("1688", {})
    if c8_cfg.get("enabled"):
        keywords = config.get("niche", {}).get("keywords_cn", [])
        if keywords:
            scraper = Ali1688Scraper(c8_cfg)
            try:
                all_products.extend(scraper.crawl_by_keywords(keywords))
            finally:
                scraper.close()

    if not all_products:
        logger.warning("Không crawl được sản phẩm nào. Kiểm tra cookies 1688 và kết nối mạng.")
        return

    out = []
    for p in all_products:
        out.append({
            "id": p.id, "title_cn": p.title_cn, "price_cny": p.price_cny,
            "original_price_cny": p.original_price_cny,
            "image_urls": p.image_urls, "description_cn": p.description_cn[:500] if p.description_cn else "",
            "category_name_cn": p.category_name_cn, "supplier_name": p.supplier_name,
            "supplier_rating": p.supplier_rating, "sales_count": p.sales_count,
            "detail_url": p.detail_url, "platform": p.platform, "is_dropship": p.is_dropship,
        })

    data_dir = Path("data") / store_id
    data_dir.mkdir(parents=True, exist_ok=True)
    out_path = data_dir / "products.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    logger.info(f"Đã lưu {len(out)} sản phẩm vào {out_path}")

if __name__ == "__main__":
    main()
