"""Trending Keyword Hijacker — detects search volume spikes and auto-triggers crawl.

Periodically scans Shopee Vietnam top searches and 1688 bestsellers.
When a keyword or category shows a significant volume spike, activates
the crawl pipeline for that niche on matching stores.
"""
import json, time, re
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional
from curl_cffi import requests as curl_requests
from src.utils.logger import setup_logger

logger = setup_logger("trend_hijacker")

SPIKE_THRESHOLD = 1.5       # 50% increase over baseline triggers action
SCAN_INTERVAL_HOURS = 6     # how often to re-scan
HISTORY_FILE = Path("data/trend_history.json")
TRIGGERED_FILE = Path("data/trend_triggers.json")


class TrendDetector:
    def __init__(self, config: dict):
        th = config.get("trend_hijacker", {})
        self.enabled = th.get("enabled", True)
        self.spike_threshold = float(th.get("spike_threshold", SPIKE_THRESHOLD))
        self.interval_hours = int(th.get("scan_interval_hours", SCAN_INTERVAL_HOURS))
        self.max_keywords = int(th.get("max_keywords_to_track", 20))
        self._history: dict[str, list[float]] = self._load_history()
        self._session = curl_requests.Session()
        self._session.impersonate = "chrome120"

    # ── History persistence ───────────────────────────────────────

    def _load_history(self) -> dict[str, list[float]]:
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_history(self):
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(self._history, f, ensure_ascii=False, indent=2)

    def _record_snapshot(self, keyword: str, volume: float):
        if keyword not in self._history:
            self._history[keyword] = []
        self._history[keyword].append(volume)
        # Keep last 30 days of snapshots at SCAN_INTERVAL_HOURS granularity
        max_snapshots = int(30 * 24 / self.interval_hours) + 1
        if len(self._history[keyword]) > max_snapshots:
            self._history[keyword] = self._history[keyword][-max_snapshots:]
        self._save_history()

    # ── Shopee top search scanner ──────────────────────────────────

    def scan_shopee_top_searches(self) -> list[dict]:
        """Scrape Shopee Vietnam hot search keywords."""
        trends = []
        try:
            resp = self._session.get(
                "https://shopee.vn/api/v4/search/search_hint",
                params={"keyword": "", "limit": self.max_keywords},
                timeout=15,
            )
            data = resp.json()
            for item in data.get("data", {}).get("keywords", []):
                keyword = item.get("keyword", "")
                volume = float(item.get("score", item.get("search_count", 1)))
                trends.append({"keyword": keyword, "volume": volume, "source": "shopee_vn"})
        except Exception as e:
            logger.debug(f"Shopee top search scan failed: {e}")
        return trends

    def scan_1688_bestsellers(self) -> list[dict]:
        """Scrape 1688 trending/hot categories."""
        trends = []
        try:
            resp = self._session.get(
                "https://re.1688.com/api/promotion/bestSellerCategory.htm",
                timeout=15,
            )
            data = resp.json()
            for cat in data.get("content", []):
                name = cat.get("name", "")
                count = float(cat.get("itemCount", cat.get("sellCount", 1)))
                trends.append({"keyword": name, "volume": count, "source": "1688_bestseller"})
        except Exception:
            pass
        return trends

    # ── Spike detection ──────────────────────────────────────────

    def detect_spikes(self, trends: list[dict]) -> list[dict]:
        spikes = []
        for t in trends:
            kw = t["keyword"]
            vol = t["volume"]
            self._record_snapshot(kw, vol)
            history = self._history.get(kw, [vol])
            if len(history) < 3:
                continue
            baseline = sum(history[:-1]) / len(history[:-1])
            if baseline <= 0:
                continue
            ratio = vol / baseline
            if ratio >= self.spike_threshold:
                spikes.append({**t, "ratio": round(ratio, 2), "baseline": round(baseline, 1)})
                logger.info(f"Trend spike: '{kw}' ({ratio:.1f}x baseline)")

        spikes.sort(key=lambda x: -x["ratio"])
        return spikes

    # ── Auto-trigger ─────────────────────────────────────────────

    def _load_triggers(self) -> list[dict]:
        if TRIGGERED_FILE.exists():
            try:
                with open(TRIGGERED_FILE, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_triggers(self, triggers: list[dict]):
        TRIGGERED_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TRIGGERED_FILE, "w", encoding="utf-8") as f:
            json.dump(triggers, f, ensure_ascii=False, indent=2)

    def _already_triggered(self, keyword: str, cooldown_hours: int = 48) -> bool:
        triggers = self._load_triggers()
        cutoff = datetime.now() - timedelta(hours=cooldown_hours)
        for t in triggers:
            if t["keyword"] == keyword:
                try:
                    t_time = datetime.fromisoformat(t["triggered_at"])
                    if t_time > cutoff:
                        return True
                except ValueError:
                    continue
        return False

    def _trigger_crawl(self, spike: dict):
        trigger = {
            "keyword": spike["keyword"],
            "volume": spike["volume"],
            "ratio": spike["ratio"],
            "source": spike.get("source", "unknown"),
            "triggered_at": datetime.now().isoformat(),
            "status": "pending",
        }
        triggers = self._load_triggers()
        triggers.append(trigger)
        self._save_triggers(triggers)
        logger.info(f"Triggered crawl for: {spike['keyword']} ({spike['ratio']}x)")

        # Write actionable trigger file for crawler
        action_file = Path("data") / f"trend_trigger_{spike['keyword'][:20].replace(' ', '_')}.json"
        cn_keyword = spike.get("keyword", "")
        with open(action_file, "w", encoding="utf-8") as f:
            json.dump({
                "type": "trend_spike",
                "keyword": spike["keyword"],
                "keyword_cn": cn_keyword,
                "ratio": spike["ratio"],
                "triggered_at": trigger["triggered_at"],
                "action": "crawl_and_post",
            }, f, ensure_ascii=False, indent=2)

    # ── Full scan cycle ──────────────────────────────────────────

    def scan_and_trigger(self) -> list[dict]:
        if not self.enabled:
            logger.info("Trend hijacker disabled")
            return []

        trends = []
        try:
            trends.extend(self.scan_shopee_top_searches())
        except Exception as e:
            logger.warning(f"Shopee scan failed: {e}")

        try:
            trends.extend(self.scan_1688_bestsellers())
        except Exception as e:
            logger.warning(f"1688 scan failed: {e}")

        if not trends:
            logger.info("No trends scanned")
            return []

        spikes = self.detect_spikes(trends)
        new_triggers = []
        for s in spikes:
            if not self._already_triggered(s["keyword"]):
                self._trigger_crawl(s)
                new_triggers.append(s)

        logger.info(f"Trend scan: {len(trends)} trends, {len(spikes)} spikes, {len(new_triggers)} new triggers")
        return spikes

    def close(self):
        if self._session:
            self._session.close()
