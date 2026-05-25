"""Supplier Credit Scorer — evaluates supplier trustworthiness from 1688/AliExpress.

Scrapes supplier profile metrics (years active, response rate, delivery speed,
repeat purchase rate) and assigns a composite score. Products from low-scoring
suppliers are filtered out during crawl.
"""
import re, json, time, random
from pathlib import Path
from typing import Optional
from curl_cffi import requests as curl_requests
from src.models.product import ProductSource
from src.utils.logger import setup_logger

logger = setup_logger("supplier_scorer")

# Scoring weights
WEIGHTS = {
    "years_active": 0.20,
    "response_rate": 0.25,
    "delivery_speed": 0.20,
    "repeat_purchase": 0.25,
    "rating": 0.10,
}

MIN_SCORE_TO_PASS = 0.40  # below this → product filtered out


class SupplierCreditScorer:
    def __init__(self, config: dict):
        sc = config.get("supplier_scoring", {})
        self.enabled = sc.get("enabled", True)
        self.min_score = float(sc.get("min_score_to_pass", MIN_SCORE_TO_PASS))
        self.weights = {**WEIGHTS, **sc.get("weights", {})}
        self._session = curl_requests.Session()
        self._session.impersonate = "chrome120"
        self._profile_cache: dict[str, dict] = {}

    # ── Profile fetching ──────────────────────────────────────────

    def fetch_supplier_profile(self, supplier_name: str, platform: str) -> dict:
        cache_key = f"{platform}::{supplier_name}"
        if cache_key in self._profile_cache:
            return self._profile_cache[cache_key]

        profile = {"name": supplier_name, "platform": platform}
        if platform == "1688":
            profile = self._fetch_1688_profile(supplier_name)
        elif platform == "aliexpress":
            profile = self._fetch_ae_profile(supplier_name)

        self._profile_cache[cache_key] = profile
        return profile

    def _fetch_1688_profile(self, supplier_name: str) -> dict:
        """Search 1688 supplier page for credibility metrics."""
        url = f"https://s.1688.com/company/company_search.htm?keywords={supplier_name}"
        try:
            resp = self._session.get(url, timeout=15)
            html = resp.text
            return self._parse_1688_profile(html, supplier_name)
        except Exception as e:
            logger.debug(f"1688 profile fetch failed for {supplier_name}: {e}")
        return self._default_profile(supplier_name, "1688")

    def _parse_1688_profile(self, html: str, name: str) -> dict:
        profile = self._default_profile(name, "1688")

        # Years active — look for 年 (year) patterns
        years_matches = re.findall(r"(\d+)\s*年", html)
        if years_matches:
            profile["years_active"] = max(int(y) for y in years_matches)

        # Response rate — look for percentage
        resp_matches = re.findall(r"(\d{2,3})\s*%", html)
        if resp_matches:
            profile["response_rate"] = min(max(int(r) for r in resp_matches) / 100, 1.0)

        # Delivery speed — look for 发货 (delivery) + number of days
        delivery = re.search(r"(\d+)\s*天内发货", html)
        if delivery:
            days = int(delivery.group(1))
            profile["delivery_speed"] = max(0, 1.0 - days / 30)

        # Repeat purchase rate — look for 复购率
        repeat = re.search(r"复购率[：:]\s*(\d+\.?\d*)%?", html)
        if repeat:
            profile["repeat_purchase_rate"] = min(float(repeat.group(1)) / 100, 1.0)

        # Overall rating
        rating = re.search(r"综合评分[：:]\s*(\d+\.?\d*)", html)
        if rating:
            profile["rating"] = min(float(rating.group(1)) / 5.0, 1.0)

        return profile

    def _fetch_ae_profile(self, supplier_name: str) -> dict:
        profile = self._default_profile(supplier_name, "aliexpress")
        try:
            url = f"https://www.aliexpress.com/store/all-wholesale-products/{supplier_name}.html"
            resp = self._session.get(url, timeout=15)
            html = resp.text

            rating = re.search(r'"storePositiveRating"\s*[=:]\s*"(\d+\.?\d*)"', html)
            if rating:
                profile["rating"] = min(float(rating.group(1)) / 100, 1.0)

            yrs = re.search(r'"openYear"\s*[=:]\s*(\d{4})', html)
            if yrs:
                profile["years_active"] = max(1, 2026 - int(yrs.group(1)))
        except Exception as e:
            logger.debug(f"AE profile fetch failed for {supplier_name}: {e}")
        return profile

    def _default_profile(self, name: str, platform: str) -> dict:
        return {
            "name": name,
            "platform": platform,
            "years_active": 1,
            "response_rate": 0.5,
            "delivery_speed": 0.5,
            "repeat_purchase_rate": 0.3,
            "rating": 0.5,
        }

    # ── Scoring ───────────────────────────────────────────────────

    def calculate_score(self, profile: dict) -> float:
        score = 0.0
        score += min(profile.get("years_active", 1) / 10, 1.0) * self.weights.get("years_active", 0.20)
        score += profile.get("response_rate", 0.5) * self.weights.get("response_rate", 0.25)
        score += profile.get("delivery_speed", 0.5) * self.weights.get("delivery_speed", 0.20)
        score += profile.get("repeat_purchase_rate", 0.3) * self.weights.get("repeat_purchase", 0.25)
        score += profile.get("rating", 0.5) * self.weights.get("rating", 0.10)
        return round(score, 3)

    def score_supplier(self, supplier_name: str, platform: str) -> dict:
        profile = self.fetch_supplier_profile(supplier_name, platform)
        score = self.calculate_score(profile)
        passed = score >= self.min_score
        return {
            **profile,
            "score": score,
            "passed": passed,
            "min_score": self.min_score,
        }

    # ── Product filtering ─────────────────────────────────────────

    def filter_products(
        self, products: list[ProductSource]
    ) -> list[ProductSource]:
        if not self.enabled:
            return products

        passed = []
        filtered = 0
        for p in products:
            supplier = p.supplier_name or p.platform
            result = self.score_supplier(supplier, p.platform)
            if result["passed"]:
                passed.append(p)
            else:
                filtered += 1
                logger.info(
                    f"Filtered {p.id}: {supplier} score={result['score']:.3f} "
                    f"(below {self.min_score})"
                )

        if filtered:
            logger.info(f"Supplier filter: {filtered} products removed, {len(passed)} kept")
        return passed

    def close(self):
        if self._session:
            self._session.close()
