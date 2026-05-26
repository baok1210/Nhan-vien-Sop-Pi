import asyncio, random, io, re as _re
from pathlib import Path
from typing import Optional
import httpx
from PIL import Image, ImageEnhance, ImageDraw, ImageFont
from src.utils.logger import setup_logger

logger = setup_logger("image_processor")

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
]


class ImageProcessor:
    def __init__(self, config: dict):
        cfg = config.get("image_processing", {})
        self.output_size = tuple(cfg.get("output_size", [800, 800]))
        self.max_images = cfg.get("max_images_per_product", 9)
        self.use_bg_removal = cfg.get("bg_removal", {}).get("enabled", False)
        self.bg_engine = cfg.get("bg_removal", {}).get("engine", "rembg")
        self.bg_color = cfg.get("bg_removal", {}).get("bg_color", "#FFFFFF")
        self.replace_bg = cfg.get("bg_removal", {}).get("replace_bg", True)
        self.quality = cfg.get("quality", 92)
        self.format = cfg.get("output_format", "jpeg")
        ad = cfg.get("anti_duplication", {})
        self.ad_enabled = ad.get("enabled", True)
        self.ad_flip = ad.get("flip_horizontal", True)
        self.ad_brightness = ad.get("color_jitter", {}).get("brightness", 0.02)
        self.ad_saturation = ad.get("color_jitter", {}).get("saturation", 0.02)
        wm = ad.get("watermark", {})
        self.wm_enabled = wm.get("enabled", True)
        self.wm_image_path = wm.get("image_path", "")
        self.wm_text = wm.get("text", "") or config.get("name", "") or "Shop"
        self.wm_opacity = wm.get("opacity", 80)
        self.wm_size_ratio = wm.get("size_ratio", 0.08)

    def _get_ext(self, url: str) -> str:
        path = url.split("?")[0].split("#")[0]
        dot = path.rfind(".")
        if dot >= 0 and "/" not in path[dot + 1 :]:
            ext = path[dot + 1 :].lower()
            if ext in ("jpg", "jpeg", "png", "webp", "gif", "bmp"):
                return ext
        return "jpg"

    def download_images(
        self, urls: list[str], output_dir: str, product_id: str
    ) -> list[str]:
        return asyncio.run(
            self._download_images_async(urls, output_dir, product_id)
        )

    async def _download_images_async(
        self, urls: list[str], output_dir: str, product_id: str
    ) -> list[str]:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        saved = []
        ua = random.choice(_USER_AGENTS)
        client = httpx.AsyncClient(
            timeout=30, follow_redirects=True,
            headers={"User-Agent": ua},
        )

        tasks = []
        for i, url in enumerate(urls[: self.max_images]):
            ext = self._get_ext(url)
            fname = f"{product_id}_{i:02d}.{ext}"
            tasks.append(self._download_one(client, url, output_dir, fname, saved))

        await asyncio.gather(*tasks)
        await client.aclose()
        logger.info(f"Downloaded {len(saved)}/{len(urls)} images for {product_id}")
        return saved

    async def _download_one(self, client: httpx.AsyncClient, url: str, out_dir: str, fname: str, saved_list: list):
        for attempt in range(3):
            try:
                resp = await client.get(url)
                if resp.status_code == 200 and len(resp.content) > 500:
                    path = Path(out_dir) / fname
                    path.write_bytes(resp.content)
                    saved_list.append(str(path))
                    return
                logger.debug(f"Download {url}: status={resp.status_code}, size={len(resp.content)}")
            except Exception as e:
                logger.debug(f"Download {url} attempt {attempt+1} failed: {e}")
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)

    def process_single(self, input_path: str, output_dir: str) -> Optional[str]:
        try:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            img = Image.open(input_path).convert("RGBA")

            if self.use_bg_removal:
                img = self._remove_background(img)

            if self.replace_bg and img.mode == "RGBA":
                bg = Image.new("RGBA", img.size, self.bg_color)
                img = Image.alpha_composite(bg, img).convert("RGB")
            else:
                img = img.convert("RGB")

            img = self._resize_fit(img, self.output_size)

            if self.ad_enabled:
                if self.ad_flip:
                    img = self._random_flip(img)
                img = self._adjust_color(img)
                if self.wm_enabled and (self.wm_image_path or self.wm_text):
                    img = self._add_watermark(img)
                img = self._strip_exif(img)

            ext = "jpg" if self.format == "jpeg" else self.format
            out_name = f"{Path(input_path).stem}_processed.{ext}"
            out_path = Path(output_dir) / out_name

            img.save(out_path, quality=self.quality, optimize=True)
            return str(out_path)
        except Exception as e:
            logger.error(f"Process {input_path} failed: {e}")
            return None

    def process_batch(self, input_paths: list[str], output_dir: str) -> list[str]:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        results = []
        for path in input_paths:
            result = self.process_single(path, output_dir)
            if result:
                results.append(result)
        logger.info(f"Processed {len(results)}/{len(input_paths)} images")
        return results

    def _remove_background(self, img: Image.Image) -> Image.Image:
        if self.bg_engine == "rembg":
            try:
                from rembg import remove
                return remove(img)
            except ImportError:
                logger.warning("rembg not installed, skip background removal")
        return img

    def _resize_fit(self, img: Image.Image, size: tuple) -> Image.Image:
        img.thumbnail(size, Image.LANCZOS)
        new_img = Image.new("RGB", size, (255, 255, 255))
        x = (size[0] - img.width) // 2
        y = (size[1] - img.height) // 2
        if img.mode == "RGBA":
            new_img.paste(img, (x, y), img)
        else:
            new_img.paste(img, (x, y))
        return new_img

    # ── Anti-duplication ─────────────────────────────────────────

    def _random_flip(self, img: Image.Image) -> Image.Image:
        if random.random() < 0.5:
            return img.transpose(Image.FLIP_LEFT_RIGHT)
        return img

    def _adjust_color(self, img: Image.Image) -> Image.Image:
        b_factor = 1.0 + random.uniform(-self.ad_brightness, self.ad_brightness)
        s_factor = 1.0 + random.uniform(-self.ad_saturation, self.ad_saturation)
        img = ImageEnhance.Brightness(img).enhance(b_factor)
        img = ImageEnhance.Color(img).enhance(s_factor)
        return img

    def _add_watermark(self, img: Image.Image) -> Image.Image:
        wm = None
        if self.wm_image_path and Path(self.wm_image_path).exists():
            try:
                wm = Image.open(self.wm_image_path).convert("RGBA")
            except Exception:
                pass

        if wm is None and self.wm_text:
            font_size = max(12, int(img.width * self.wm_size_ratio))
            try:
                font = ImageFont.truetype("arial.ttf", font_size)
            except (OSError, IOError):
                font = ImageFont.load_default()
            dummy = ImageDraw.Draw(img)
            bbox = dummy.textbbox((0, 0), self.wm_text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            wm = Image.new("RGBA", (tw + 12, th + 8), (0, 0, 0, 0))
            draw = ImageDraw.Draw(wm)
            draw.text((6, 4), self.wm_text, fill=(255, 255, 255, int(255 * self.wm_opacity / 100)), font=font)

        if wm is None:
            return img

        wm.thumbnail((img.width // 4, img.height // 4), Image.LANCZOS)
        corners = [
            (8, 8),
            (img.width - wm.width - 8, 8),
            (8, img.height - wm.height - 8),
            (img.width - wm.width - 8, img.height - wm.height - 8),
        ]
        pos = random.choice(corners)
        img_rgba = img.convert("RGBA")
        img_rgba.paste(wm, pos, wm)
        return img_rgba.convert("RGB")

    def _strip_exif(self, img: Image.Image) -> Image.Image:
        if "exif" in img.info:
            del img.info["exif"]
        if "dpi" in img.info:
            del img.info["dpi"]
        if "icc_profile" in img.info:
            del img.info["icc_profile"]
        return img
