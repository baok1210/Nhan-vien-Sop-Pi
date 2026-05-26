import json, sys, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.ai.caption_gen import CaptionGenerator
from src.utils.exchange_rate import calculate_final_price
from src.utils.logger import setup_logger
logger = setup_logger("caption_script")

def main():
    parser = argparse.ArgumentParser(description="Tao caption tieng Viet cho san pham")
    parser.add_argument("store_id", help="ID cua store")
    parser.add_argument("--limit", type=int, default=0, help="Gioi han so sp")
    parser.add_argument("--force", action="store_true", help="Ghi de caption cu")
    args = parser.parse_args()

    cfg_path = Path("config/stores") / f"{args.store_id}.json"
    config = {}
    if cfg_path.exists():
        config = json.loads(cfg_path.read_text(encoding="utf-8"))

    store_dir = Path("data") / args.store_id
    prod_path = store_dir / "products_with_images.json"
    if not prod_path.exists():
        prod_path = store_dir / "products.json"
    if not prod_path.exists():
        logger.error(f"Khong tim thay san pham tai {store_dir}")
        sys.exit(1)

    products = json.loads(prod_path.read_text(encoding="utf-8"))
    if args.limit:
        products = products[:args.limit]

    cap_path = store_dir / "captions.json"
    if cap_path.exists() and not args.force:
        logger.info(f"Caption da ton tai tai {cap_path}. Them --force de ghi de.")
        return

    gen = CaptionGenerator(config)
    niche = config.get("niche", {})
    niche_name = niche.get("keywords_vn", [args.store_id])[0]
    multiplier = niche.get("price_multiplier", 2.5)

    captions = []
    for i, prod in enumerate(products, 1):
        price_cny = prod.get("price_cny", 0)
        price_vnd = calculate_final_price(price_cny, multiplier)
        caption = gen.generate(
            title_cn=prod.get("title_cn", ""),
            category=niche_name,
            price_cny=price_cny,
            features=prod.get("description_cn", ""),
            price_vnd=price_vnd,
        )
        captions.append({
            "product_id": prod.get("id"), "title_cn": prod.get("title_cn", ""),
            "price_cny": price_cny, "price_vnd": int(price_vnd),
            "images_processed": prod.get("images_processed", []), "image_ids": [],
            **caption,
        })

    cap_path.write_text(json.dumps(captions, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Xong! {len(captions)} caption da tao tai {cap_path}")

if __name__ == "__main__":
    main()
