"""Tests for AliExpress scraper — validate that anti-bot HTML or missing data is handled."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import patch, MagicMock
from src.source.aliexpress import AliExpressScraper
from src.models.product import ProductSource, validate_product


def _make_product(pid="1", title="Test product from China for sale online", price=25.0, desc="This is a high quality product with many features and benefits for customers." * 3):
    return ProductSource(
        id=pid, title_cn=title, price_cny=price, original_price_cny=price,
        description_cn=desc, image_urls=["https://example.com/img.jpg"],
        platform="aliexpress", is_dropship=True, category_name_cn="",
    )


def _validate_via_schema(products: list[ProductSource]) -> list[ProductSource]:
    """Replacement for removed _validate_products — uses shared validate_product."""
    validated = []
    for p in products:
        p_dict = {
            "id": p.id, "title_cn": p.title_cn, "price_cny": p.price_cny,
            "original_price_cny": p.original_price_cny,
            "image_urls": p.image_urls, "description_cn": p.description_cn,
            "category_name_cn": p.category_name_cn, "supplier_name": p.supplier_name,
            "supplier_rating": p.supplier_rating, "sales_count": p.sales_count,
            "detail_url": p.detail_url, "platform": p.platform, "is_dropship": p.is_dropship,
        }
        result = validate_product(p_dict)
        if result is not None:
            validated.append(p)
    return validated


def test_validate_products_all_valid():
    products = [_make_product(pid="1"), _make_product(pid="2")]
    validated = _validate_via_schema(products)
    assert len(validated) == 2


def test_validate_products_skips_invalid_price():
    products = [
        _make_product(pid="1", price=0.0),
        _make_product(pid="2"),
    ]
    validated = _validate_via_schema(products)
    assert len(validated) == 1
    assert validated[0].id == "2"


def test_validate_products_skips_empty_title():
    products = [
        _make_product(pid="1", title=""),
        _make_product(pid="2"),
    ]
    validated = _validate_via_schema(products)
    assert len(validated) == 1
    assert validated[0].id == "2"


def test_validate_products_allows_short_desc():
    """description_cn is no longer required to be >=50 chars — empty is accepted."""
    products = [
        _make_product(pid="1", desc="ngắn"),
        _make_product(pid="2"),
    ]
    validated = _validate_via_schema(products)
    assert len(validated) == 2


def test_validate_products_allows_missing_images():
    """image_urls being empty/list is optional, should not fail validation."""
    products = [
        ProductSource(
            id="100", title_cn="Test product for validation", price_cny=50.0,
            original_price_cny=50.0, description_cn="A" * 60,
            image_urls=[], platform="aliexpress", is_dropship=True, category_name_cn="",
        ),
    ]
    validated = _validate_via_schema(products)
    assert len(validated) == 1
