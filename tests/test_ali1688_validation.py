"""Tests for 1688 scraper — validate that missing price/title triggers ValidationError."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import patch, MagicMock
from src.source.ali1688 import Ali1688Scraper
from src.models.product import ProductSource


def _make_product_1688(pid="1", title="测试产品标题", price=45.5, desc=None):
    if desc is None:
        desc = "这是一款高品质的产品，采用优质材料制作，适合日常使用。" * 5
    return ProductSource(
        id=pid, title_cn=title, price_cny=price, original_price_cny=price,
        image_urls=["https://example.com/img.jpg"], description_cn=desc,
        category_name_cn="", platform="1688", is_dropship=True,
    )


def test_parse_products_missing_price(caplog):
    """When price is missing/zero, validation should log error and skip product."""
    scraper = Ali1688Scraper({"max_pages": 1, "delay_seconds": 1, "dropship_filter": False})
    with patch.object(scraper, '_parse_from_html', return_value=[_make_product_1688(price=0.0)]):
        caplog.clear()
        products = scraper._parse_products("<html></html>", keyword="test")
        assert len(products) == 0
        assert "Validation thất bại" in caplog.text


def test_parse_products_missing_title(caplog):
    """When title is missing/empty, validation should log error and skip product."""
    scraper = Ali1688Scraper({"max_pages": 1, "delay_seconds": 1, "dropship_filter": False})
    with patch.object(scraper, '_parse_from_html', return_value=[_make_product_1688(title="")]):
        caplog.clear()
        products = scraper._parse_products("<html></html>", keyword="test")
        assert len(products) == 0
        assert "Validation thất bại" in caplog.text


def test_parse_products_all_valid():
    """Valid products should pass validation."""
    scraper = Ali1688Scraper({"max_pages": 1, "delay_seconds": 1, "dropship_filter": False})
    products_in = [_make_product_1688(pid="1"), _make_product_1688(pid="2")]
    with patch.object(scraper, '_parse_from_html', return_value=products_in):
        products = scraper._parse_products("<html></html>", keyword="test")
        assert len(products) == 2
