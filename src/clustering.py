"""Automated niche discovery via TF-IDF clustering + K-means.
Discovers product groups from raw pool data without predefined categories.
"""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from src.utils.logger import setup_logger

logger = setup_logger("clustering")

POOL_FILE = Path("data/product_pool.json")
RAW_FILE = Path("data/raw/products.json")


def load_products() -> list[dict]:
    products = []
    if POOL_FILE.exists():
        with open(POOL_FILE, encoding="utf-8") as f:
            products = json.load(f)
        logger.info(f"Loaded {len(products)} products from pool")
    elif RAW_FILE.exists():
        with open(RAW_FILE, encoding="utf-8") as f:
            products = json.load(f)
        logger.info(f"Loaded {len(products)} products from raw")
    else:
        logger.warning("No product data found. Run crawl first.")
    return products


def _combine_title(p: dict) -> str:
    cn = p.get("title_cn", "") or ""
    en = p.get("title_en", "") or ""
    return f"{cn} {en}".strip()


def _find_optimal_k(X, k_range: range) -> tuple[int, float]:
    best_k = 2
    best_score = -1
    for k in k_range:
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = km.fit_predict(X)
        score = silhouette_score(X, labels) if len(set(labels)) > 1 else -1
        if score > best_score:
            best_k = k
            best_score = score
    return best_k, best_score


def cluster_products(
    products: list[dict],
    min_cluster_size: int = 3,
    max_clusters: int = 12,
) -> list[dict]:
    if len(products) < min_cluster_size:
        logger.warning(f"Too few products ({len(products)}) for clustering")
        return []

    # Filter out products with empty titles (scrape failures, blocked sources)
    valid = [p for p in products if _combine_title(p)]
    if len(valid) < min_cluster_size:
        logger.warning(f"Too few valid titles ({len(valid)}/{len(products)}) for clustering")
        return []
    products = valid

    titles = [_combine_title(p) for p in products]

    vec = TfidfVectorizer(
        analyzer="char",
        ngram_range=(2, 4),
        max_features=500,
        min_df=1,
        lowercase=True,
    )
    X = vec.fit_transform(titles)
    feature_names = vec.get_feature_names_out()
    n_docs = X.shape[0]

    max_k = min(max_clusters, n_docs // 2)
    k_range = range(2, max(2, max_k + 1))
    if len(k_range) <= 1:
        k_range = range(2, min(4, n_docs) + 1)

    try:
        best_k, best_score = _find_optimal_k(X, k_range)
    except ValueError:
        best_k = 2
        best_score = -1
    logger.info(f"Optimal k={best_k}, silhouette={best_score:.3f}")

    km = KMeans(n_clusters=best_k, random_state=42, n_init=10)
    labels = km.fit_predict(X)

    clusters = defaultdict(list)
    for label, prod in zip(labels, products):
        clusters[int(label)].append(prod)

    results = []
    for label, items in clusters.items():
        if len(items) < min_cluster_size:
            continue

        cluster_titles = [titles[i] for i, lbl in enumerate(labels) if lbl == label]
        all_words = " ".join(cluster_titles)

        # Top TF-IDF terms for this cluster
        center = km.cluster_centers_[label]
        top_indices = center.argsort()[::-1][:15]
        top_terms = [feature_names[i] for i in top_indices if center[i] > 0.05]

        # Keyword extraction: most common meaningful n-grams
        cn_words = Counter()
        en_words = Counter()
        for t in cluster_titles:
            for w in t.split():
                if re.search(r"[\u4e00-\u9fff]", w):
                    cn_words[w] += 1
                elif len(w) > 2 and w.isalpha():
                    en_words[w.lower()] += 1

        prices = [p.get("price_cny", 0) for p in items if p.get("price_cny", 0) > 0]
        avg_price = round(sum(prices) / len(prices), 2) if prices else 0

        total_sales = sum(p.get("sales_count", 0) for p in items)
        best_seller = (
            max(items, key=lambda x: x.get("sales_count", 0))
            if any(p.get("sales_count", 0) for p in items)
            else items[0]
        )

        results.append({
            "cluster_id": int(label),
            "method": "tfidf_kmeans",
            "product_count": len(items),
            "products": items[:20],
            "avg_price_cny": avg_price,
            "total_sales": total_sales,
            "best_seller": best_seller,
            "top_terms": top_terms[:8],
            "keywords_cn": [w for w, _ in cn_words.most_common(8)],
            "keywords_en": [w for w, _ in en_words.most_common(8)],
            "silhouette_score": round(best_score, 3) if len(clusters) > 1 else 0,
        })

    results.sort(key=lambda x: -x["product_count"])
    return results


def niche_suggestions_from_clusters(
    min_products: int = 3,
    max_clusters: int = 12,
) -> list[dict]:
    """Full pipeline: load → cluster → format as niche suggestions."""
    products = load_products()
    if not products:
        return []

    clusters = cluster_products(products, min_products, max_clusters)
    if not clusters:
        logger.info("No viable clusters found")
        return []

    suggestions = []
    for c in clusters:
        top_cn = c["keywords_cn"][:3] if c["keywords_cn"] else c["top_terms"][:3]
        top_en = c["keywords_en"][:3] if c["keywords_en"] else c["top_terms"][:3]

        # Generate a name from top keywords
        name_words = top_cn[:2] if top_cn else top_en[:2]
        name = " & ".join(name_words) if name_words else f"cluster_{c['cluster_id']}"

        suggestions.append({
            "category": name,
            "icon": "🔬",
            "method": "tfidf_kmeans",
            "product_count": c["product_count"],
            "products": c["products"],
            "avg_price_cny": c["avg_price_cny"],
            "total_sales": c["total_sales"],
            "top_keywords": (c["keywords_en"] or c["keywords_cn"] or c["top_terms"])[:5],
            "best_seller": c["best_seller"],
            "keywords_cn": c["keywords_cn"][:5],
            "keywords_en": c["keywords_en"][:5],
            "total_value_cny": round(
                sum(p.get("price_cny", 0) for p in c["products"]), 2
            ),
        })

    return suggestions
