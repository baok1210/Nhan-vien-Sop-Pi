"""A/B title variant generation + scoring for Shopee SEO.

Generates 3 title styles (utility, promotional, technical) and scores
each based on keyword density, length, spec presence, and engagement.
"""
import re
from typing import Optional
from src.utils.logger import setup_logger

logger = setup_logger("title_scorer")

# ── Variant style templates ──────────────────────────────────────

UTILITY_PREFIXES = [
    "Giải pháp", "Tiện lợi", "Thông minh", "Hiệu quả", "Đa năng",
]
PROMO_PREFIXES = [
    "SỐC!", "HOT!", "GIÁ RẺ", "SIÊU ƯU ĐÃI", "MUA NGAY",
]
PROMO_SUFFIXES = [
    "giá tốt nhất thị trường", "giảm thêm khi mua online",
    "miễn phí vận chuyển", "ưu đãi đặc biệt hôm nay",
]
TECH_ANCHORS = [
    "Chất liệu", "Tương thích", "Kích thước", "Công suất", "Phiên bản",
]


def generate_variants(
    title_vi: str,
    category: str = "",
    features: str = "",
) -> list[dict]:
    base = title_vi.strip().rstrip(".,!;")
    variants = []

    # Utility
    prefix_u = UTILITY_PREFIXES[hash(base) % len(UTILITY_PREFIXES)]
    util = _build_variant(base, prefix=prefix_u, suffix="cho cuộc sống tiện nghi hơn")
    variants.append({"style": "utility", "title": util, "id": "A"})

    # Promotional
    prefix_p = PROMO_PREFIXES[hash(base + "promo") % len(PROMO_PREFIXES)]
    suffix_p = PROMO_SUFFIXES[hash(base + "suffix") % len(PROMO_SUFFIXES)]
    promo = _build_variant(base, prefix=prefix_p, suffix=suffix_p, uppercase=True)
    variants.append({"style": "promotional", "title": promo, "id": "B"})

    # Technical
    anchor = TECH_ANCHORS[hash(base + "tech") % len(TECH_ANCHORS)]
    spec_words = _extract_specs(features)
    tech_suffix = f"— {anchor} {' | '.join(spec_words[:3])}" if spec_words else ""
    tech = _build_variant(base, suffix=tech_suffix)
    variants.append({"style": "technical", "title": tech, "id": "C"})

    return variants


def _build_variant(
    base: str,
    prefix: str = "",
    suffix: str = "",
    uppercase: bool = False,
) -> str:
    parts = []
    if prefix:
        parts.append(prefix)
    parts.append(base)
    if suffix:
        parts.append(suffix)
    title = " ".join(parts)
    if uppercase:
        title = title.upper()
    if len(title) > 120:
        title = title[: title.rfind(" ", 0, 120)]
    return title.strip()


def _extract_specs(features: str) -> list[str]:
    specs = []
    for token in features.replace(",", " ").replace(";", " ").split():
        t = token.strip()
        if re.search(r"\d+", t) and len(t) > 1:
            specs.append(t)
        elif re.search(r"(cm|mm|kg|g|v|a|w|mAh|inch|%)", t, re.IGNORECASE):
            specs.append(t)
    return specs[:5]


# ── Title scoring ────────────────────────────────────────────────


def score_title(title: str, keywords: list[str] = None) -> float:
    if not title or len(title) < 10:
        return 0.0

    total = 0.0

    # 1. Keyword density (weight 0.35)
    kw_score = _score_keywords(title, keywords or [])
    total += kw_score * 0.35

    # 2. Length score (weight 0.25) — optimal 60-100 chars
    length = len(title)
    if 60 <= length <= 100:
        len_score = 1.0
    elif 40 <= length < 60 or 100 < length <= 120:
        len_score = 0.6
    elif length > 120:
        len_score = 0.2
    else:
        len_score = 0.3
    total += len_score * 0.25

    # 3. Number presence (weight 0.15) — specs, price credibility
    num_score = 0.3 if re.search(r"\d+", title) else 0.0
    if re.search(r"\d{2,}", title):
        num_score = 1.0
    elif re.search(r"\d", title):
        num_score = 0.6
    total += num_score * 0.15

    # 4. Engagement punctuation (weight 0.15)
    punct_score = 0.0
    if "!" in title:
        punct_score += 0.5
    if "-" in title or "—" in title:
        punct_score += 0.3
    if "?" in title:
        punct_score += 0.2
    total += min(punct_score, 1.0) * 0.15

    # 5. Generic word penalty (weight 0.10)
    generic_words = ["giá rẻ", "chất lượng", "uy tín", "nhiều", "đẹp"]
    penalty = 0
    for gw in generic_words:
        if gw in title.lower():
            penalty += 0.2
    total += max(0, 1.0 - min(penalty, 1.0)) * 0.10

    return round(total, 3)


def _score_keywords(title: str, keywords: list[str]) -> float:
    if not keywords:
        return 0.5
    title_lower = title.lower()
    matched = sum(1 for kw in keywords if kw.lower() in title_lower)
    ratio = matched / len(keywords)
    return min(ratio, 1.0)


# ── Main API ─────────────────────────────────────────────────────


def generate_and_score(
    title_vi: str,
    category: str = "",
    features: str = "",
    keywords: list[str] = None,
) -> dict:
    variants = generate_variants(title_vi, category, features)
    scored = []
    for v in variants:
        score = score_title(v["title"], keywords)
        scored.append({**v, "score": score})

    scored.sort(key=lambda x: -x["score"])
    best = scored[0]

    labels = " ".join(f"{v['id']}={v['score']:.3f}" for v in scored)
    logger.info(f"Title variants: {labels} → best={best['id']} ({best['style']})")

    return {
        "title_vi": best["title"],
        "all_titles": scored,
        "best_style": best["style"],
        "best_score": best["score"],
    }
