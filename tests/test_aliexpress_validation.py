"""Tests for AliExpress scraper — validate that anti-bot HTML or missing data is handled."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import patch, MagicMock
from src.source.aliexpress import AliExpressScraper
from src.models.product import ProductSource


def _make_product(pid="1", title="Test product from China for sale online", price=25.0, desc="This is a high quality product with many features and benefits for customers." * 3):
    return ProductSource(
        id=pid, title_cn=title, price_cny=price, original_price_cny=price,
        description_cn=desc, image_urls=["https://example.com/img.jpg"],
        platform="aliexpress", is_dropship=True, category_name_cn="",
    )


def test_validate_products_all_valid():
    scraper = AliExpressScraper({"max_pages": 1, "delay_seconds": 1})
    products = [_make_product(pid="1"), _make_product(pid="2")]
    validated = scraper._validate_products(products, keyword="test")
    assert len(validated) == 2


def test_validate_products_skips_invalid_price():
    scraper = AliExpressScraper({"max_pages": 1, "delay_seconds": 1})
    products = [
        _make_product(pid="1", price=0.0),
        _make_product(pid="2"),
    ]
    validated = scraper._validate_products(products, keyword="test")
    assert len(validated) == 1
    assert validated[0].id == "2"


def test_validate_products_skips_empty_title():
    scraper = AliExpressScraper({"max_pages": 1, "delay_seconds": 1})
    products = [
        _make_product(pid="1", title=""),
        _make_product(pid="2"),
    ]
    validated = scraper._validate_products(products, keyword="test")
    assert len(validated) == 1
    assert validated[0].id == "2"


def test_validate_products_skips_short_desc():
    scraper = AliExpressScraper({"max_pages": 1, "delay_seconds": 1})
    products = [
        _make_product(pid="1", desc="ngắn"),
        _make_product(pid="2"),
    ]
    validated = scraper._validate_products(products, keyword="test")
    assert len(validated) == 1
    assert validated[0].id == "2"


def test_validate_products_allows_missing_images():
    """image_urls being empty/list is optional, should not fail validation."""
    scraper = AliExpressScraper({"max_pages": 1, "delay_seconds": 1})
    products = [
        ProductSource(
            id="100", title_cn="Test product for validation", price_cny=50.0,
            original_price_cny=50.0, description_cn="A" * 60,
            image_urls=[], platform="aliexpress", is_dropship=True, category_name_cn="",
        ),
    ]
    validated = scraper._validate_products(products, keyword="test")
    assert len(validated) == 1
