import json
import sys
from pathlib import Path
from src.source.ali1688 import Ali1688Scraper
from src.source.aliexpress import AliExpressScraper
from src.processing.image_processor import ImageProcessor
from src.ai.caption_gen import CaptionGenerator
from src.publisher.shopee import ShopeeClient
from src.models.product import ProductProcessed, ShopeeProduct
from src.utils.exchange_rate import calculate_final_price
from src.utils.logger import setup_logger

logger = setup_logger("pipeline")


def load_config(path: str = "config/config.json") -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_crawl(config: dict):
    logger.info("=== PHASE 1: CRAWL ===")
    all_products = []

    # Source 1: 1688 (needs Chrome cookies)
    src_1688 = config.get("source", {}).get("1688", {})
    if src_1688.get("enabled", True):
        keywords = config.get("niche", {}).get("keywords_cn", [])
        if keywords:
            scraper = Ali1688Scraper(src_1688)
            try:
                all_products.extend(scraper.crawl_by_keywords(keywords))
            finally:
                scraper.close()

    # Source 2: AliExpress
    src_ae = config.get("source", {}).get("aliexpress", {})
    if src_ae.get("enabled", True):
        keywords = config.get("niche", {}).get("keywords_en", [])
        if keywords:
            scraper = AliExpressScraper(src_ae)
            try:
                all_products.extend(scraper.crawl_by_keywords(keywords))
            finally:
                scraper.close()

    data_dir = Path("data/raw")
    data_dir.mkdir(parents=True, exist_ok=True)
    output = []
    for p in all_products:
        output.append({
            "id": p.id,
            "title_cn": p.title_cn,
            "price_cny": p.price_cny,
            "original_price_cny": p.original_price_cny,
            "image_urls": p.image_urls,
            "description_cn": p.description_cn[:500] if p.description_cn else "",
            "category_name_cn": p.category_name_cn,
            "supplier_name": p.supplier_name,
            "supplier_rating": p.supplier_rating,
            "sales_count": p.sales_count,
            "detail_url": p.detail_url,
            "platform": p.platform,
            "is_dropship": p.is_dropship,
        })
    with open(data_dir / "products.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved {len(output)} products to data/raw/products.json")
    return all_products


def run_process_images(config: dict, products: list):
    logger.info("=== PHASE 2: PROCESS IMAGES ===")
    processor = ImageProcessor(config)
    img_dir = Path("data/images")
    img_dir.mkdir(parents=True, exist_ok=True)

    processed = []
    for p in products[:5]:
        local_paths = processor.download_images(
            p.image_urls, str(img_dir / "raw"), p.id
        )
        out_dir = str(img_dir / "processed" / p.id)
        results = processor.process_batch(local_paths, out_dir)
        processed.append((p, results))
    return processed


def run_generate_captions(config: dict, products: list):
    logger.info("=== PHASE 3: GENERATE CAPTIONS ===")
    gen = CaptionGenerator(config)
    niche = config.get("niche", {})
    multiplier = niche.get("price_multiplier", 2.5)
    output = []
    for p in products[:5]:
        price_vnd = calculate_final_price(p.price_cny, multiplier)
        caption = gen.generate(
            title_cn=p.title_cn,
            category=niche.get("name", ""),
            price_cny=p.price_cny,
            features=p.description_cn,
            price_vnd=price_vnd,
        )
        pp = ProductProcessed(
            source=p,
            title_vi=caption.get("title_vi", ""),
            description_vi=caption.get("description", ""),
            bullet_points=caption.get("bullet_points", []),
            hashtags=caption.get("hashtags", []),
            price_vnd=price_vnd,
            status="caption_done",
        )
        output.append(pp)
    return output


def run_publish(config: dict, products: list[ProductProcessed]):
    logger.info("=== PHASE 4: PUBLISH TO SHOPEE ===")
    client = ShopeeClient(config)
    for pp in products[:2]:
        sp = ShopeeProduct(product=pp, category_id=config.get("niche", {}).get("category_shopee_id", 0))
        item_id = client.add_item(sp)
        if item_id:
            logger.info(f"Created Shopee item: {item_id}")
    client.close()


if __name__ == "__main__":
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config/config.json"
    config = load_config(config_path)

    products = run_crawl(config)
    run_process_images(config, products)
    processed = run_generate_captions(config, products)
    run_publish(config, processed)
