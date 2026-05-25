import asyncio, random, subprocess
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import httpx
from src.utils.logger import setup_logger

logger = setup_logger("video_processor")
SUPPORTED_AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}

FPS_LIST = [24, 25, 30]


class VideoProcessor:
    def __init__(self, config: dict):
        cfg = config.get("video_processing", {})
        self.music_dir = Path(cfg.get("music_dir", "assets/background_music"))
        self.volume = float(cfg.get("volume", 0.3))
        self._bgm_cache: list[Path] | None = None
        self._bgm_dur_cache: dict[str, float] = {}

    def _scan_bgm(self) -> list[Path]:
        if self._bgm_cache is not None:
            return self._bgm_cache
        if not self.music_dir.exists():
            logger.warning(f"BGM dir not found: {self.music_dir}")
            self._bgm_cache = []
            return self._bgm_cache
        files = [
            p for p in self.music_dir.iterdir()
            if p.is_file() and p.suffix.lower() in SUPPORTED_AUDIO_EXTS
        ]
        if not files:
            logger.warning(f"No BGM files found in {self.music_dir}")
        self._bgm_cache = files
        return files

    def _select_bgm(self) -> Path | None:
        files = self._scan_bgm()
        if not files:
            return None
        return random.choice(files)

    # ── Metadata (ffprobe, ~10ms, no memory alloc) ────────────────

    def _ffprobe_duration(self, path: str) -> Optional[float]:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
        return None

    def _ffprobe_fps(self, path: str) -> float:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=r_frame_rate",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split("/")
            try:
                return float(parts[0]) / float(parts[1]) if len(parts) == 2 else float(parts[0])
            except (ValueError, ZeroDivisionError):
                pass
        return 30.0

    # ── Download ──────────────────────────────────────────────────

    async def download_video(
        self, url: str, output_dir: str, product_id: str
    ) -> Optional[str]:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        path_part = url.split("?")[0].split("#")[0]
        dot = path_part.rfind(".")
        raw_ext = path_part[dot + 1:] if dot >= 0 and "/" not in path_part[dot + 1:] else "mp4"
        if not raw_ext.startswith("."):
            raw_ext = f".{raw_ext}"
        fname = f"{product_id}{raw_ext}"
        out_path = Path(output_dir) / fname

        if out_path.exists():
            logger.info(f"Video already cached: {out_path}")
            return str(out_path)

        try:
            async with httpx.AsyncClient(
                timeout=120, follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36"
                },
            ) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    logger.error(f"Download failed (HTTP {resp.status_code}): {url}")
                    return None
                out_path.write_bytes(resp.content)
                logger.info(f"Downloaded video: {out_path}")
                return str(out_path)
        except Exception as e:
            logger.error(f"Download error for {url}: {e}")
            return None

    async def download_videos(
        self, items: list[tuple[str, str, str]], output_dir: str
    ) -> list[tuple[str, Optional[str]]]:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(
            timeout=120, follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36"
            },
        ) as client:
            async def _dl(url: str, pid: str) -> tuple[str, Optional[str]]:
                path_part = url.split("?")[0].split("#")[0]
                dot = path_part.rfind(".")
                ext = path_part[dot + 1:] if dot >= 0 and "/" not in path_part[dot + 1:] else "mp4"
                if not ext.startswith("."):
                    ext = f".{ext}"
                out_path = Path(output_dir) / f"{pid}{ext}"
                if out_path.exists():
                    return pid, str(out_path)
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        out_path.write_bytes(resp.content)
                        return pid, str(out_path)
                except Exception:
                    pass
                return pid, None

            tasks = [_dl(url, pid) for url, pid in items]
            return await asyncio.gather(*tasks)

    # ── Core pipeline (ffmpeg subprocess, streamed) ───────────────

    def process_single(self, input_path: str, output_dir: str) -> Optional[str]:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        stem = Path(input_path).stem
        out_path = str(Path(output_dir) / f"{stem}_processed.mp4")

        dur = self._ffprobe_duration(input_path)
        if dur is None:
            logger.error(f"Failed to probe {input_path}")
            return None
        logger.info(f"Probed: {input_path} ({dur:.1f}s)")

        bgm_path = self._select_bgm()
        try:
            if bgm_path is None:
                logger.info("No BGM — exporting muted")
                self._run_ffmpeg_muted(input_path, out_path)
            else:
                self._run_ffmpeg_bgm(input_path, out_path, bgm_path, dur)
            logger.info(f"Exported: {out_path}")
            return out_path
        except subprocess.CalledProcessError as e:
            err = e.stderr.decode("utf-8", errors="replace")[:300] if e.stderr else str(e)
            logger.error(f"FFmpeg failed ({err}) — falling back to muted")
            return self._export_muted(input_path, output_dir, stem)

    def _run_ffmpeg_muted(self, input_path: str, output_path: str):
        subprocess.run(
            ["ffmpeg", "-y",
             "-i", input_path,
             "-c:v", "libx264", "-preset", "medium",
             "-profile:v", "high", "-pix_fmt", "yuv420p",
             "-an",
             output_path],
            check=True, capture_output=True, timeout=600,
        )

    def _run_ffmpeg_bgm(self, input_path: str, output_path: str, bgm_path: Path, duration: float):
        bgm_key = str(bgm_path)
        if bgm_key not in self._bgm_dur_cache:
            bgm_dur = self._ffprobe_duration(bgm_key) or 0
            self._bgm_dur_cache[bgm_key] = bgm_dur
        bgm_dur = self._bgm_dur_cache[bgm_key]

        if bgm_dur <= 0:
            logger.warning(f"BGM has zero duration: {bgm_path}")
            self._run_ffmpeg_muted(input_path, output_path)
            return

        audio_filter = (
            f"[1:a]aloop=loop=-1:size=2e9,"
            f"atrim=duration={duration},"
            f"volume={self.volume}[a]"
        )
        logger.info(
            f"BGM: {bgm_path.name} ({bgm_dur:.1f}s → {duration:.1f}s, vol={self.volume})"
        )
        subprocess.run(
            ["ffmpeg", "-y",
             "-i", input_path,
             "-i", str(bgm_path),
             "-c:v", "libx264", "-preset", "medium",
             "-profile:v", "high", "-pix_fmt", "yuv420p",
             "-filter_complex", audio_filter,
             "-map", "0:v",
             "-map", "[a]",
             "-c:a", "aac",
             "-shortest",
             output_path],
            check=True, capture_output=True, timeout=600,
        )

    def _export_muted(self, input_path: str, output_dir: str, stem: str) -> Optional[str]:
        out_path = str(Path(output_dir) / f"{stem}_muted.mp4")
        try:
            self._run_ffmpeg_muted(input_path, out_path)
            return out_path
        except subprocess.CalledProcessError as e:
            logger.error(f"Muted export failed: {e}")
            return None

    # ── Parallel batch ────────────────────────────────────────────

    def process_batch_parallel(
        self, entries: list[dict], store_id: str, max_workers: int = 3
    ) -> list[dict]:
        base_dir = Path("data") / store_id
        raw_dir = str(base_dir / "videos" / "raw")
        proc_dir = str(base_dir / "videos" / "processed")
        Path(raw_dir).mkdir(parents=True, exist_ok=True)
        Path(proc_dir).mkdir(parents=True, exist_ok=True)

        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {}
            for entry in entries:
                url = entry.get("video_url", "")
                pid = entry.get("id", "unknown")
                if not url:
                    continue
                fut = pool.submit(self._process_one_sync, url, pid, raw_dir, proc_dir)
                futures[fut] = entry

            for fut in as_completed(futures):
                entry = futures[fut]
                try:
                    processed, error = fut.result()
                except Exception as e:
                    processed, error = None, str(e)
                entry["video_processed"] = processed
                if error:
                    entry["video_error"] = error
                else:
                    entry.pop("video_error", None)
                results.append(entry)

        return results

    def _process_one_sync(self, url: str, pid: str, raw_dir: str, proc_dir: str):
        path_part = url.split("?")[0].split("#")[0]
        dot = path_part.rfind(".")
        ext = path_part[dot + 1:] if dot >= 0 and "/" not in path_part[dot + 1:] else "mp4"
        if not ext.startswith("."):
            ext = f".{ext}"
        raw_path = str(Path(raw_dir) / f"{pid}{ext}")

        if not Path(raw_path).exists():
            logger.warning(f"Raw file not found for {pid}, run download first")
            return None, "raw_missing"

        processed = self.process_single(raw_path, proc_dir)
        if processed is None:
            return None, "processing_failed"
        return processed, None

    async def process_batch(
        self, entries: list[dict], store_id: str
    ) -> list[dict]:
        base_dir = Path("data") / store_id
        raw_dir = str(base_dir / "videos" / "raw")
        proc_dir = str(base_dir / "videos" / "processed")
        Path(raw_dir).mkdir(parents=True, exist_ok=True)
        Path(proc_dir).mkdir(parents=True, exist_ok=True)

        results = []
        for entry in entries:
            url = entry.get("video_url", "")
            pid = entry.get("id", "unknown")
            if not url:
                continue

            raw_path = await self.download_video(url, raw_dir, pid)
            if raw_path is None:
                entry["video_processed"] = None
                entry["video_error"] = "download_failed"
                results.append(entry)
                continue

            processed = await asyncio.get_event_loop().run_in_executor(
                None, self.process_single, raw_path, proc_dir
            )
            entry["video_processed"] = processed or entry.get("video_processed")
            if processed is None:
                entry["video_error"] = "processing_failed"
            else:
                entry.pop("video_error", None)
            results.append(entry)

        return results
