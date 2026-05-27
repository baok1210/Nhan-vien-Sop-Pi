import json, os
import sys
from pathlib import Path
from src.source.ali1688 import Ali1688Scraper
from src.source.aliexpress import AliExpressScraper
from src.source.aliexpress_api import AliExpressAPI
from src.processing.image_processor import ImageProcessor
from src.ai.caption_gen import CaptionGenerator
from src.publisher.shopee import ShopeeClient
from src.models.product import ProductProcessed, ShopeeProduct
from src.utils.exchange_rate import calculate_final_price
from src.utils.logger import setup_logger

logger = setup_logger("pipeline")


def _load_dotenv(path: str = ".env") -> dict:
    """Load .env file, return dict of key=value pairs."""
    env_file = Path(path)
    if not env_file.exists():
        return {}
    envs = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        envs[key.strip()] = val.strip().strip("\"'")
    return envs


_ENV_MAP = {
    "GEMINI_API_KEY": ("ai", "caption", "api_key"),
    "ALIEXPRESS_APP_KEY": ("source", "aliexpress", "app_key"),
    "ALIEXPRESS_APP_SECRET": ("source", "aliexpress", "app_secret"),
    "ALIEXPRESS_TRACKING_ID": ("source", "aliexpress", "tracking_id"),
    "SHOPEE_PARTNER_ID": ("shopee", "partner_id"),
    "SHOPEE_PARTNER_KEY": ("shopee", "partner_key"),
    "SHOPEE_SHOP_ID": ("shopee", "shop_id"),
    "SHOPEE_ACCESS_TOKEN": ("shopee", "access_token"),
    "SHOPEE_REFRESH_TOKEN": ("shopee", "refresh_token"),
    "TELEGRAM_BOT_TOKEN": ("notification", "telegram_bot_token"),
    "TELEGRAM_CHAT_ID": ("notification", "telegram_chat_id"),
}


def _merge_env(config: dict, envs: dict):
    """Overwrite config values with .env secrets."""
    for env_key, json_path in _ENV_MAP.items():
        val = envs.get(env_key)
        if val:
            target = config
            for key in json_path[:-1]:
                target = target.setdefault(key, {})
            target[json_path[-1]] = val


def load_config(path: str = "config/config.json") -> dict:
    with open(path, encoding="utf-8") as f:
        config = json.load(f)
    _merge_env(config, _load_dotenv())
    return config


def validate_config(config: dict) -> list[str]:
    """Check config, return list of warnings/issues."""
    warnings = []

    niche = config.get("niche", {})
    if not niche.get("keywords_cn") and not niche.get("keywords_en"):
        warnings.append("Chưa có từ khóa tìm kiếm (keywords_cn / keywords_en) trong config")

    src_1688 = config.get("source", {}).get("1688", {})
    if src_1688.get("enabled", True):
        pass

    src_ae = config.get("source", {}).get("aliexpress", {})
    if src_ae.get("enabled", True):
        if not src_ae.get("app_key") or not src_ae.get("app_secret"):
            warnings.append(
                "AliExpress: chưa có API key -> sẽ dùng web scraper (dễ bị chặn). "
                "Tạo App Key tại https://openservice.aliexpress.com"
            )

    ai_cfg = config.get("ai", {}).get("caption", {})
    if not ai_cfg.get("api_key"):
        warnings.append(
            "Gemini API: chưa có key -> sẽ dùng template dịch (chất lượng thấp). "
            "Lấy key miễn phí tại https://aistudio.google.com/apikey"
        )

    shopee_cfg = config.get("shopee", {})
    if shopee_cfg.get("environment") == "prod":
        if not shopee_cfg.get("partner_id") or not shopee_cfg.get("partner_key"):
            warnings.append(
                "Shopee: environment=prod nhưng thiếu Partner ID/Key. "
                "Đăng ký tại https://open.shopee.com"
            )

    return warnings


def run_crawl(config: dict):
    logger.info("=== GIAI ĐOẠN 1: CRAWL SẢN PHẨM ===")
    all_products = []

    src_1688 = config.get("source", {}).get("1688", {})
    if src_1688.get("enabled", True):
        keywords = config.get("niche", {}).get("keywords_cn", [])
        if keywords:
            scraper = Ali1688Scraper(src_1688)
            try:
                all_products.extend(scraper.crawl_by_keywords(keywords))
            finally:
                scraper.close()

    src_ae = config.get("source", {}).get("aliexpress", {})
    if src_ae.get("enabled", True):
        keywords = config.get("niche", {}).get("keywords_en", [])
        if keywords:
            api_key = src_ae.get("app_key", "")
            api_secret = src_ae.get("app_secret", "")
            if api_key and api_secret:
                logger.info("AliExpress: using Open Platform API")
                api = AliExpressAPI(api_key, api_secret, src_ae.get("tracking_id", ""))
                all_products.extend(api.crawl_by_keywords(keywords))
            else:
                logger.info("AliExpress: no API credentials, falling back to web scraper")
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
    logger.info(f"Đã lưu {len(output)} sản phẩm vào data/raw/products.json")
    return all_products


def run_process_images(config: dict, products: list):
    logger.info("=== GIAI ĐOẠN 2: XỬ LÝ ẢNH ===")
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
    logger.info("=== GIAI ĐOẠN 3: TẠO CAPTION TIẾNG VIỆT ===")
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
    shopee_cfg = config.get("shopee", {})
    if not shopee_cfg.get("partner_id") or not shopee_cfg.get("partner_key"):
        logger.warning("⚠️ BỎ QUA đăng Shopee: Chưa cấu hình Partner ID/Key. Chạy config_wizard.py để nhập.")
        return
    logger.info("=== GIAI ĐOẠN 4: ĐĂNG LÊN SHOPEE ===")
    client = ShopeeClient(config)
    for pp in products[:2]:
        sp = ShopeeProduct(product=pp, category_id=config.get("niche", {}).get("category_shopee_id", 0))
        item_id = client.add_item(sp)
        if item_id:
            logger.info(f"Đã tạo Shopee item: {item_id}")
    client.close()


if __name__ == "__main__":
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config/config.json"
    print("=" * 60)
    print("  CHINA DROPSHIP TO SHOPEE - Pipeline tự động")
    print("=" * 60)

    if not Path(config_path).exists():
        print(f"\n\u274c Không tìm thấy file cấu hình: {config_path}")
        print("   Chạy lệnh sau để tạo cấu hình:")
        print("   \u2592 python scripts/config_wizard.py")
        sys.exit(1)

    config = load_config(config_path)

    warnings = validate_config(config)
    if warnings:
        print("\n=== KIỂM TRA CẤU HÌNH ===")
        for w in warnings:
            print(f"  \u26a0\ufe0f {w}")
        print()

    products = run_crawl(config)
    if products:
        run_process_images(config, products)
        processed = run_generate_captions(config, products)
        run_publish(config, processed)
    else:
        logger.warning("Không có sản phẩm nào. Kiểm tra cookies 1688 và kết nối mạng.")
