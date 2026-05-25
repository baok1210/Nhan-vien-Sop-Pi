#!/usr/bin/env python3
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ai.caption_gen import CaptionGenerator
from src.seo.title_scorer import generate_and_score
from src.utils.exchange_rate import calculate_final_price
from src.utils.logger import setup_logger
logger = setup_logger("caption_script")

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/generate_captions.py <store_id> [max_products]")
        print("  Generate Vietnamese captions for products in data/<store_id>/products_with_images.json")
        sys.exit(1)

    store_id = sys.argv[1]
    max_items = int(sys.argv[2]) if len(sys.argv) > 2 else 999
    store_dir = Path("data") / store_id

    # Prefer products_with_images.json, fallback to products.json
    prod_path = store_dir / "products_with_images.json"
    if not prod_path.exists():
        prod_path = store_dir / "products.json"
    if not prod_path.exists():
        logger.error(f"No products found at {store_dir}")
        return

    with open(prod_path, encoding="utf-8") as f:
        products = json.load(f)

    cfg_path = Path("config/stores") / f"{store_id}.json"
    config = {}
    if cfg_path.exists():
        with open(cfg_path, encoding="utf-8") as f:
            config = json.load(f)

    gen = CaptionGenerator(config)
    niche = config.get("niche", {})
    niche_name = niche.get("keywords_vn", [store_id])[0]
    multiplier = niche.get("price_multiplier", 2.5)

    captions = []
    for i, prod in enumerate(products[:max_items], 1):
        price_cny = prod.get("price_cny", 0)
        price_vnd = calculate_final_price(price_cny, multiplier)

        caption = gen.generate(
            title_cn=prod.get("title_cn", ""),
            category=niche_name,
            price_cny=price_cny,
            features=prod.get("description_cn", ""),
            price_vnd=price_vnd,
        )

        title_vi_raw = caption.get("title_vi", "")
        seo_result = generate_and_score(
            title_vi=title_vi_raw,
            category=niche_name,
            features=prod.get("description_cn", ""),
            keywords=niche.get("keywords_vn", []),
        )
        caption["title_vi"] = seo_result["title_vi"]
        caption["title_variants"] = seo_result["all_titles"]
        caption["best_title_style"] = seo_result["best_style"]
        caption["best_title_score"] = seo_result["best_score"]

        entry = {
            "product_id": prod.get("id"),
            "title_cn": prod.get("title_cn", ""),
            "price_cny": price_cny,
            "price_vnd": int(price_vnd),
            "images_processed": prod.get("images_processed", []),
            "image_ids": [],
            **caption,
        }
        captions.append(entry)
        logger.info(
            f"[{i}/{len(products)}] {prod.get('id')}: "
            f"{caption.get('title_vi', '')[:50]}... "
            f"(score={seo_result['best_score']:.3f}, style={seo_result['best_style']})"
        )

    out_path = store_dir / "captions.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(captions, f, ensure_ascii=False, indent=2)
    logger.info(f"Done. {len(captions)} captions saved to {out_path}")

if __name__ == "__main__":
    main()
