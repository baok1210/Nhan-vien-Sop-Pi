"""Tests for Pydantic ProductSchema validation."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from pydantic import ValidationError
from src.models.product import ProductSchema, validate_product


def test_valid_product():
    data = {
        "id": "123",
        "title_cn": "测试产品标题",
        "price_cny": 45.5,
        "original_price_cny": 50.0,
        "description_cn": "这是一款高品质的产品，采用优质材料制作，适合日常使用，经久耐用，颜色款式多样。" * 2,
        "image_urls": ["https://example.com/img.jpg"],
        "platform": "1688",
    }
    schema = ProductSchema(**data)
    assert schema.id == "123"
    assert schema.price_cny == 45.5
    assert schema.title_cn == "测试产品标题"


def test_zero_price():
    data = {
        "id": "456",
        "title_cn": "产品名称",
        "price_cny": 0,
        "original_price_cny": 0,
        "description_cn": "这是一款高品质的产品，采用优质材料制作，适合日常使用，经久耐用，颜色款式多样。" * 2,
    }
    with pytest.raises(ValidationError, match="price_cny.*> 0"):
        ProductSchema(**data)


def test_negative_price():
    data = {
        "id": "789",
        "title_cn": "产品",
        "price_cny": -10,
        "original_price_cny": 0,
        "description_cn": "优质产品，材料上乘，工艺精湛，品质保证。" * 10,
    }
    with pytest.raises(ValidationError, match="price_cny.*> 0"):
        ProductSchema(**data)


def test_empty_title():
    data = {
        "id": "101",
        "title_cn": "",
        "price_cny": 25.0,
        "original_price_cny": 30.0,
        "description_cn": "优质产品，材料上乘，工艺精湛，品质保证。" * 10,
    }
    with pytest.raises(ValidationError, match="title_cn"):
        ProductSchema(**data)


def test_whitespace_title():
    data = {
        "id": "102",
        "title_cn": "   ",
        "price_cny": 25.0,
        "original_price_cny": 30.0,
        "description_cn": "优质产品，材料上乘，工艺精湛，品质保证。" * 10,
    }
    with pytest.raises(ValidationError, match="title_cn"):
        ProductSchema(**data)


def test_short_description():
    data = {
        "id": "103",
        "title_cn": "产品名称",
        "price_cny": 25.0,
        "original_price_cny": 30.0,
        "description_cn": "ngắn",
    }
    with pytest.raises(ValidationError, match="description_cn.*50"):
        ProductSchema(**data)


def test_validate_product_valid():
    data = {
        "id": "200",
        "title_cn": "优质产品",
        "price_cny": 99.0,
        "original_price_cny": 120.0,
        "description_cn": "优质产品，采用环保材料，安全无毒，适合家庭使用，品质保证。" * 3,
    }
    result = validate_product(data, source_label="test")
    assert result is not None
    assert result.price_cny == 99.0


def test_validate_product_invalid(caplog):
    data = {
        "id": "201",
        "title_cn": "",
        "price_cny": 0,
        "original_price_cny": 0,
        "description_cn": "",
    }
    result = validate_product(data, source_label="test_invalid")
    assert result is None
    assert "Validation thất bại" in caplog.text
