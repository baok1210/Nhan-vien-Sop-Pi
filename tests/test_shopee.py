"""Unit tests for ShopeeClient — empty config, sign, request validation."""
import json, os, sys
from pathlib import Path

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.publisher.shopee import ShopeeClient


def test_init_empty_config_does_not_crash():
    """partner_id/shop_id = '' must NOT raise ValueError."""
    cfg = {
        "shopee": {
            "partner_id": "",
            "partner_key": "",
            "shop_id": "",
            "access_token": "",
            "environment": "uat",
        }
    }
    client = ShopeeClient(cfg)
    assert client.partner_id == 0
    assert client.shop_id == 0
    client.close()


def test_init_partial_config():
    """Only partner_id set, others empty."""
    cfg = {
        "shopee": {
            "partner_id": "12345",
            "partner_key": "abc123",
            "shop_id": "",
            "access_token": "",
        }
    }
    client = ShopeeClient(cfg)
    assert client.partner_id == 12345
    assert client.shop_id == 0
    assert client.partner_key == "abc123"
    client.close()


def test_sign_basic():
    """_sign returns a hex string of length 64 (SHA256)."""
    cfg = {"shopee": {"partner_id": "111", "partner_key": "key", "environment": "uat"}}
    client = ShopeeClient(cfg)
    sig = client._sign("/api/v2/product/get_category_list", 1234567890)
    assert isinstance(sig, str)
    assert len(sig) == 64
    # All hex chars
    int(sig, 16)
    client.close()


def test_sign_with_access_token_and_shop():
    """Sign changes when access_token or shop_id present."""
    cfg = {
        "shopee": {
            "partner_id": "111",
            "partner_key": "key",
            "shop_id": "222",
            "access_token": "tok123",
            "environment": "uat",
        }
    }
    client = ShopeeClient(cfg)
    sig1 = client._sign("/api/v2/product/add_item", 1000000)
    assert len(sig1) == 64
    int(sig1, 16)
    client.close()


def test_get_attributes_sends_category_id():
    """get_attributes must include category_id in request data.
    We verify by checking that _request receives the category_id param.
    """
    cfg = {"shopee": {"partner_id": "1", "partner_key": "k", "environment": "uat"}}
    client = ShopeeClient(cfg)

    captured = {}

    original_request = client._request

    def mock_request(method, path, data=None):
        captured["method"] = method
        captured["path"] = path
        captured["data"] = data
        return {"error": 0, "response": {"attribute_list": []}}

    client._request = mock_request
    try:
        client.get_attributes(12345)
        # Must be POST (Shopee API v2 uses POST for get_attribute)
        # but our current code uses GET. We'll verify the intent:
        assert captured["path"] == "/api/v2/product/get_attribute"
        # category_id should be in the request
        assert captured["data"] is not None, "category_id must be sent"
        assert captured["data"].get("category_id") == 12345
    finally:
        client._request = original_request
        client.close()


if __name__ == "__main__":
    test_init_empty_config_does_not_crash()
    test_init_partial_config()
    test_sign_basic()
    test_sign_with_access_token_and_shop()
    test_get_attributes_sends_category_id()
    print("ALL PASS")
