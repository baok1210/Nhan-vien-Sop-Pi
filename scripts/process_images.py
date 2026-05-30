#!/usr/bin/env python3
import argparse, json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.processing.image_processor import ImageProcessor
from src.utils.logger import setup_logger
logger = setup_logger("image_script")

def main():
    parser = argparse.ArgumentParser(description="Download and process images for a store")
    parser.add_argument("store_id", help="ID cua store (vi du: leo-nui)")
    parser.add_argument("max_products", nargs="?", type=int, default=999,
                        help="So luong san pham toi da (mac dinh: 999)")
    args = parser.parse_args()

    store_id = args.store_id
    max_items = args.max_products
    store_dir = Path("data") / store_id
    prod_path = store_dir / "products.json"

    if not prod_path.exists():
        logger.error(f"No products.json found at {prod_path}")
        return

    with open(prod_path, encoding="utf-8") as f:
        products = json.load(f)

    cfg_path = Path("config/stores") / f"{store_id}.json"
    config = {}
    if cfg_path.exists():
        with open(cfg_path, encoding="utf-8") as f:
            config = json.load(f)

    processor = ImageProcessor(config)
    raw_dir = str(store_dir / "images" / "raw")
    proc_dir = str(store_dir / "images" / "processed")

    total_ok = 0
    for i, prod in enumerate(products[:max_items], 1):
        pid = prod.get("id", f"p{i}")
        urls = prod.get("image_urls", [])
        if not urls:
            continue

        saved = processor.download_images(urls, raw_dir, pid)
        if saved:
            out_dir = f"{proc_dir}/{pid}"
            results = processor.process_batch(saved, out_dir)
            prod["images_local"] = saved
            prod["images_processed"] = results
            prod["image_count"] = len(results)
            total_ok += 1
            logger.info(f"[{i}/{len(products)}] {pid}: {len(results)} images")

    out_path = store_dir / "products_with_images.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    logger.info(f"Done. {total_ok}/{len(products)} products with images saved to {out_path}")

if __name__ == "__main__":
    main()
