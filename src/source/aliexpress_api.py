"""AliExpress Open Platform API client - official product search without web scraping"""
import hashlib, hmac, json, time, urllib.parse
from typing import Any
from src.models.product import ProductSource
from src.utils.logger import setup_logger

logger = setup_logger("aliexpress_api")

API_ENDPOINT = "https://open-api.aliexpress.com/rest"


class AliExpressAPIError(Exception):
    pass


def _sign(params: dict, app_secret: str) -> str:
    keys = sorted(params.keys())
    qs = "".join(f"{k}{params[k]}" for k in keys)
    payload = app_secret + qs + app_secret
    return hmac.new(app_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest().upper()


class AliExpressAPI:
    def __init__(self, app_key: str, app_secret: str, tracking_id: str = ""):
        self.app_key = app_key
        self.app_secret = app_secret
        self.tracking_id = tracking_id
        self._session = None

    def _request(self, method: str, api_params: dict) -> dict:
        import requests as req
        params = {
            "app_key": self.app_key,
            "timestamp": str(int(time.time() * 1000)),
            "format": "json",
            "v": "2.0",
            "sign_method": "sha256",
            "method": method,
        }
        params.update(api_params)
        params["sign"] = _sign(params, self.app_secret)

        resp = req.post(API_ENDPOINT, data=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        err_key = f"{method.replace('.', '_')}_response"
        result = data.get(err_key, data)

        if "error_response" in data:
            err = data["error_response"]
            raise AliExpressAPIError(f"{err.get('code', '?')}: {err.get('msg', '?')}")

        return result

    def search_products(self, keyword: str, page: int = 1, page_size: int = 20, max_price: float = 0, min_price: float = 0) -> list[dict]:
        params = {
            "keywords": keyword,
            "page_no": page,
            "page_size": min(page_size, 50),
            "sort": "SALE_PRICE_ASC",
            "target_currency": "CNY",
            "target_language": "ZH",
        }
        if max_price > 0:
            params["max_sale_price"] = max_price
        if min_price > 0:
            params["min_sale_price"] = min_price

        resp = self._request("aliexpress.affiliate.product.query", params)
        products = []
        resp_list = resp
        for key in ("resp", "result", "products", "product", "list"):
            if isinstance(resp_list, dict):
                resp_list = resp_list.get(key, resp_list)
        if isinstance(resp_list, dict):
            for key in ("products", "product", "list"):
                val = resp_list.get(key, [])
                if isinstance(val, list):
                    resp_list = val
                    break
        if isinstance(resp_list, list):
            products = resp_list
        return products

    def parse_to_product_source(self, item: dict) -> ProductSource | None:
        pid = str(item.get("product_id") or item.get("productId") or "")
        if not pid:
            return None
        title = item.get("product_title", item.get("subject", ""))
        price = 0.0
        raw = item.get("sale_price", item.get("price", item.get("min_sale_price", "0")))
        if isinstance(raw, str):
            raw = raw.replace(",", "").strip()
            try:
                parts = raw.split("-")
                price = float(parts[0])
            except ValueError:
                price = 0.0
        elif isinstance(raw, (int, float)):
            price = float(raw)
        img = item.get("product_main_image_url", item.get("image_urls", ""))
        if isinstance(img, str):
            images = [img] if img else []
        elif isinstance(img, list):
            images = img[:9]
        else:
            images = []
        detail_url = item.get("promotion_link", item.get("detail_url", ""))
        if not detail_url:
            detail_url = f"https://www.aliexpress.com/item/{pid}.html"
        sales = int(item.get("sales_count", item.get("sales", 0)))
        rating_text = item.get("evaluate_rate", item.get("rating", "0"))
        try:
            rating = float(rating_text) if rating_text else 0.0
        except (ValueError, TypeError):
            rating = 0.0
        supplier = item.get("seller_name", item.get("shop_name", item.get("store_name", "")))
        desc = item.get("product_detail", item.get("description", ""))

        return ProductSource(
            id=pid, title_cn=title, price_cny=price, original_price_cny=price,
            image_urls=images, description_cn=desc if isinstance(desc, str) else "",
            category_name_cn=item.get("category_name", item.get("category_id", "")),
            supplier_name=supplier, supplier_rating=rating,
            sales_count=sales, detail_url=detail_url,
            platform="aliexpress", is_dropship=True,
        )

    def crawl_by_keywords(self, keywords: list[str], max_price: float = 0) -> list[ProductSource]:
        all_products = []
        for kw in keywords:
            logger.info(f"AliExpress API: searching '{kw}'")
            for page in range(1, 3):
                try:
                    items = self.search_products(kw, page=page, max_price=max_price)
                    if not items:
                        break
                    for item in items:
                        ps = self.parse_to_product_source(item)
                        if ps:
                            all_products.append(ps)
                    logger.info(f"  Page {page}: {len(items)} products")
                except AliExpressAPIError as e:
                    logger.error(f"AliExpress API error: {e}")
                    break
        logger.info(f"AliExpress API total: {len(all_products)} products")
        return all_products
