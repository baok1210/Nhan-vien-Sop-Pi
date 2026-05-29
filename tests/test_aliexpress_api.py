"""Test AliExpress API client - verifies parsing without real API calls"""
import sys
sys.path.insert(0, r"C:\project\china-dropship-to-shopee")

from src.source.aliexpress_api import AliExpressAPI, _sign


def test_sign_consistency():
    sig = _sign({"app_key": "test", "method": "test"}, "secret")
    assert isinstance(sig, str) and len(sig) == 64


def test_search_mocked(monkeypatch):
    def mock_request(self, method, params):
        return {
            "resp": {
                "products": {
                    "product": [
                        {
                            "product_id": 100500123,
                            "product_title": "Kitchen Knife Set Stainless Steel",
                            "sale_price": "25.50",
                            "product_main_image_url": "https://ae01.alicdn.com/test.jpg",
                            "sales_count": 150,
                            "evaluate_rate": "4.5",
                            "seller_name": "TestStore",
                            "promotion_link": "https://www.aliexpress.com/item/100500123.html",
                        }
                    ]
                }
            }
        }
    monkeypatch.setattr(AliExpressAPI, "_request", mock_request)
    api = AliExpressAPI("test_key", "test_secret")
    items = api.search_products("kitchen knife")
    assert len(items) == 1
    assert items[0]["product_id"] == 100500123


def test_parse_to_product_source():
    api = AliExpressAPI("k", "s")
    item = {
        "product_id": 100500456,
        "product_title": "Phone Case Silicone",
        "sale_price": "3.99",
        "product_main_image_url": "https://ae01.alicdn.com/phone.jpg",
        "sales_count": 9999,
        "evaluate_rate": "4.8",
        "seller_name": "PhoneShop",
        "promotion_link": "https://aliexpress.com/item/100500456.html",
    }
    ps = api.parse_to_product_source(item)
    assert ps is not None
    assert ps.id == "100500456"
    assert ps.title_cn == "Phone Case Silicone"
    assert ps.price_cny == 3.99
    assert len(ps.image_urls) == 1
    assert ps.sales_count == 9999
    assert ps.supplier_rating == 4.8
    assert ps.platform == "aliexpress"


def test_parse_missing_price():
    api = AliExpressAPI("k", "s")
    item = {"product_id": "1", "product_title": "Test"}
    ps = api.parse_to_product_source(item)
    assert ps is not None
    assert ps.price_cny == 0.0


def test_parse_missing_id():
    api = AliExpressAPI("k", "s")
    assert api.parse_to_product_source({}) is None


def test_crawl_by_keywords_mocked(monkeypatch):
    call_count = 0
    def mock_search(self, keyword, **kw):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            return []
        return [
            {"product_id": f"{i}", "product_title": f"Product {i}", "sale_price": f"{i*10}.00"}
            for i in range(1, 4)
        ]
    monkeypatch.setattr(AliExpressAPI, "search_products", mock_search)
    api = AliExpressAPI("k", "s")
    products = api.crawl_by_keywords(["test kw"])
    assert len(products) == 3
    assert products[0].id == "1"
    assert products[0].price_cny == 10.0
