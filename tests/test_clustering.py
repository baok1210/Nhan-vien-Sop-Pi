"""Unit tests for clustering — empty titles, edge cases."""
import json, sys, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.clustering import cluster_products, niche_suggestions_from_clusters


def test_cluster_empty_titles_returns_empty():
    """All titles empty → no crash, returns []."""
    products = [
        {"id": "1", "title_cn": "", "title_en": "", "price_cny": 10},
        {"id": "2", "title_cn": "", "title_en": "", "price_cny": 20},
    ]
    result = cluster_products(products, min_cluster_size=1, max_clusters=2)
    assert result == []


def test_cluster_mixed_empty_and_valid():
    """Mix of empty and valid titles → clusters only the valid ones."""
    products = [
        {"id": "1", "title_cn": "手机壳 iPhone 15", "price_cny": 10},
        {"id": "2", "title_cn": "", "price_cny": 20},
        {"id": "3", "title_cn": "手机壳 Samsung", "price_cny": 15},
        {"id": "4", "title_cn": "手机膜", "price_cny": 5},
        {"id": "5", "title_cn": "", "price_cny": 30},
    ]
    result = cluster_products(products, min_cluster_size=1, max_clusters=5)
    assert len(result) >= 1
    # Only non-empty titles should be clustered
    all_ids = set()
    for cluster in result:
        for p in cluster.get("products", []):
            all_ids.add(p.get("id", ""))
    assert "2" not in all_ids
    assert "5" not in all_ids


def test_niche_suggestions_empty_pool():
    """Empty product pool → returns [] without crash."""
    from src.discovery import load_pool, save_pool
    old_pool = load_pool()
    save_pool([])
    try:
        result = niche_suggestions_from_clusters()
        assert result == []
    finally:
        save_pool(old_pool)


if __name__ == "__main__":
    test_cluster_empty_titles_returns_empty()
    test_cluster_mixed_empty_and_valid()
    test_niche_suggestions_empty_pool()
    print("ALL PASS")
