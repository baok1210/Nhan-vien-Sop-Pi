import json, sys, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.processing.image_processor import ImageProcessor
from src.utils.logger import setup_logger
logger = setup_logger("images_script")

def main():
    parser = argparse.ArgumentParser(description="Tai va xu ly anh san pham")
    parser.add_argument("store_id", help="ID cua store")
    parser.add_argument("--limit", type=int, default=0, help="Gioi han so sp xu ly")
    parser.add_argument("--no-download", action="store_true", help="Bo qua tai anh, chi xu ly")
    args = parser.parse_args()

    cfg_path = Path("config/stores") / f"{args.store_id}.json"
    config = {}
    if cfg_path.exists():
        config = json.loads(cfg_path.read_text(encoding="utf-8"))

    data_dir = Path("data") / args.store_id
    prod_path = data_dir / "products.json"
    if not prod_path.exists():
        logger.error(f"Khong tim thay {prod_path}. Chay crawl truoc.")
        sys.exit(1)

    products = json.loads(prod_path.read_text(encoding="utf-8"))
    if args.limit:
        products = products[:args.limit]

    processor = ImageProcessor(config)
    raw_dir = str(data_dir / "images" / "raw")
    proc_dir = str(data_dir / "images" / "processed")
    ok = 0

    for prod in products:
        pid = prod.get("id", "")
        urls = prod.get("image_urls", [])
        if not urls:
            continue
        if not args.no_download:
            saved = processor.download_images(urls, raw_dir, pid)
        else:
            saved = [str(p) for p in Path(raw_dir).glob(f"{pid}_*")]
        if saved:
            results = processor.process_batch(saved, f"{proc_dir}/{pid}")
            prod["images_local"] = saved
            prod["images_processed"] = results
            prod["image_count"] = len(results)
            ok += 1

    out_path = data_dir / "products_with_images.json"
    out_path.write_text(json.dumps(products, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Xong! {ok}/{len(products)} sp da xu ly anh")

if __name__ == "__main__":
    main()
