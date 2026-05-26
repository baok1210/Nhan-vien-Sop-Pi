import json, sys, argparse, io
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
from src.source.ali1688 import Ali1688Scraper
from src.source.aliexpress import AliExpressScraper
from src.utils.logger import setup_logger
logger = setup_logger("crawl_script")

def main():
    parser = argparse.ArgumentParser(description="Crawl sản phẩm từ 1688 và AliExpress")
    parser.add_argument("store_id", help="ID của store (VD: dien-gia-dung)")
    parser.add_argument("--max-pages", type=int, default=0, help="Ghi đè số trang crawl")
    parser.add_argument("--no-1688", action="store_true", help="Bỏ qua 1688")
    parser.add_argument("--no-ae", action="store_true", help="Bỏ qua AliExpress")
    parser.add_argument("--output", help="Đường dẫn output (mặc định: data/<store_id>/products.json)")
    args = parser.parse_args()

    cfg_path = Path("config/stores") / f"{args.store_id}.json"
    if not cfg_path.exists():
        logger.error(f"Khong tim thay config: {cfg_path}")
        sys.exit(1)

    with open(cfg_path, encoding="utf-8") as f:
        config = json.load(f)

    all_products = []
    if not args.no_ae:
        ae = config.get("sources", {}).get("aliexpress", {})
        if ae.get("enabled"):
            kw = config.get("niche", {}).get("keywords_en", [])
            if kw:
                if args.max_pages:
                    ae["max_pages"] = args.max_pages
                scraper = AliExpressScraper(ae)
                try:
                    all_products.extend(scraper.crawl_by_keywords(kw))
                finally:
                    scraper.close()

    if not args.no_1688:
        c8 = config.get("sources", {}).get("1688", {})
        if c8.get("enabled"):
            kw = config.get("niche", {}).get("keywords_cn", [])
            if kw:
                if args.max_pages:
                    c8["max_pages"] = args.max_pages
                scraper = Ali1688Scraper(c8)
                try:
                    all_products.extend(scraper.crawl_by_keywords(kw))
                finally:
                    scraper.close()

    if not all_products:
        logger.warning("Khong co san pham nao")
        return

    out = [{
        "id": p.id, "title_cn": p.title_cn, "price_cny": p.price_cny,
        "original_price_cny": p.original_price_cny,
        "image_urls": p.image_urls, "description_cn": p.description_cn[:500] if p.description_cn else "",
        "category_name_cn": p.category_name_cn, "supplier_name": p.supplier_name,
        "supplier_rating": p.supplier_rating, "sales_count": p.sales_count,
        "detail_url": p.detail_url, "platform": p.platform, "is_dropship": p.is_dropship,
    } for p in all_products]

    out_path = args.output or (Path("data") / args.store_id / "products.json")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Da luu {len(out)} san pham vao {out_path}")

if __name__ == "__main__":
    main()
