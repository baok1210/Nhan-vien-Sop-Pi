#!/usr/bin/env python3
import json, sys, asyncio, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.processing.video_processor import VideoProcessor
from src.utils.logger import setup_logger
logger = setup_logger("video_script")


async def _process_one(processor, prod, store_dir, pid):
    url = prod.get("video_url", "") or prod.get("video", "")
    raw_dir = str(store_dir / "videos" / "raw")
    proc_dir = str(store_dir / "videos" / "processed")

    if not url:
        return "skip"
    raw_path = await processor.download_video(url, raw_dir, pid)
    if raw_path is None:
        return "download_fail"
    processed = processor.process_single(raw_path, proc_dir)
    prod["video_processed"] = processed
    return "ok" if processed else "process_fail"


def main():
    parser = argparse.ArgumentParser(description="Xu ly video product (download + resize)")
    parser.add_argument("store_id", help="ID cua store")
    parser.add_argument("--limit", type=int, default=999, help="Gioi han so sp xu ly")
    args = parser.parse_args()

    store_id = args.store_id
    max_items = args.limit
    store_dir = Path("data") / store_id

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

    processor = VideoProcessor(config)

    async def run_batch():
        ok = 0
        fail = 0
        skip = 0
        for i, prod in enumerate(products[:max_items], 1):
            pid = prod.get("id", f"p{i}")
            result = await _process_one(processor, prod, store_dir, pid)
            if result == "skip":
                skip += 1
                logger.info(f"[{i}/{len(products)}] {pid}: skip (no URL)")
            elif result == "download_fail":
                fail += 1
                logger.warning(f"[{i}/{len(products)}] {pid}: download failed")
            elif result == "process_fail":
                fail += 1
                logger.warning(f"[{i}/{len(products)}] {pid}: processing failed (muted fallback)")
            else:
                ok += 1
                logger.info(f"[{i}/{len(products)}] {pid}: OK")
        return ok, fail, skip

    ok, fail, skip = asyncio.run(run_batch())

    out_path = store_dir / "products_with_images.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    logger.info(f"Done. {ok} ok, {fail} fail, {skip} skip — saved to {out_path}")


if __name__ == "__main__":
    main()
