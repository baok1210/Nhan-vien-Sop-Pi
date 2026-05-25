import hashlib
import hmac
import json
import time
from typing import Optional
import httpx
from src.models.product import ShopeeProduct, ProductProcessed
from src.utils.logger import setup_logger

logger = setup_logger("shopee_publisher")


class ShopeeClient:
    BASE_URLS = {
        "uat": "https://partner.test-stable.shopeemobile.com",
        "prod": "https://partner.shopeemobile.com",
    }

    def __init__(self, config: dict):
        s = config.get("shopee", {})
        self.partner_id = int(s.get("partner_id", "0") or "0")
        self.partner_key = s.get("partner_key", "")
        self.redirect_url = s.get("redirect_url", "")
        self.shop_id = int(s.get("shop_id", "0") or "0")
        self.access_token = s.get("access_token", "")
        self.refresh_token = s.get("refresh_token", "")
        self.env = s.get("environment", "uat")
        self.base_url = self.BASE_URLS.get(self.env)
        self.client = httpx.Client(timeout=60)

    def _sign(self, path: str, timestamp: int) -> str:
        base = f"{self.partner_id}{path}{timestamp}"
        if self.access_token:
            base += self.access_token
        if self.shop_id:
            base += str(self.shop_id)
        return hmac.new(
            self.partner_key.encode(),
            base.encode(),
            hashlib.sha256,
        ).hexdigest()

    def _request(self, method: str, path: str, data: Optional[dict] = None) -> dict:
        timestamp = int(time.time())
        sign = self._sign(path, timestamp)

        params = {
            "partner_id": self.partner_id,
            "timestamp": timestamp,
            "sign": sign,
        }
        if self.access_token:
            params["access_token"] = self.access_token
        if self.shop_id:
            params["shop_id"] = self.shop_id

        url = f"{self.base_url}{path}"
        headers = {"Content-Type": "application/json"}

        try:
            if method == "GET":
                resp = self.client.get(url, params=params, headers=headers)
            else:
                resp = self.client.post(url, params=params, json=data, headers=headers)
            resp.raise_for_status()
            result = resp.json()
            if result.get("error"):
                logger.error(f"Shopee API error: {result.get('error')} - {result.get('message')}")
            return result
        except Exception as e:
            logger.error(f"Shopee request failed: {e}")
            return {"error": str(e)}

    def upload_image(self, image_path: str) -> Optional[str]:
        path = "/api/v2/media_space/upload_image"
        try:
            from pathlib import Path
            files = {"image": Path(image_path).read_bytes()}
            timestamp = int(time.time())
            sign = self._sign(path, timestamp)
            params = {
                "partner_id": self.partner_id,
                "timestamp": timestamp,
                "sign": sign,
                "access_token": self.access_token,
                "shop_id": self.shop_id,
            }
            resp = self.client.post(
                f"{self.base_url}{path}",
                params=params,
                files={"image": (Path(image_path).name, files["image"], "image/jpeg")},
            )
            data = resp.json()
            if data.get("response", {}).get("image_id"):
                return data["response"]["image_id"]
            logger.error(f"Upload image failed: {data}")
            return None
        except Exception as e:
            logger.error(f"Upload image error: {e}")
            return None

    def get_categories(self) -> list:
        path = "/api/v2/product/get_category_list"
        result = self._request("GET", path)
        return result.get("response", {}).get("category_list", [])

    def get_attributes(self, category_id: int) -> list:
        path = "/api/v2/product/get_attribute"
        data = {"category_id": category_id}
        result = self._request("POST", path, data)
        return result.get("response", {}).get("attribute_list", [])

    def add_item(self, product: ShopeeProduct) -> Optional[int]:
        path = "/api/v2/product/add_item"
        p = product.product
        data = {
            "item_name": p.title_vi if p else "",
            "description": p.description_vi if p else "",
            "description_type": "extended",
            "category_id": product.category_id,
            "item_sku": str(p.source.id) if p and p.source else "",
            "item_status": "UNLIST",
            "condition": "NEW",
            "original_price": p.price_vnd if p else 0,
            "weight": str(product.weight_kg),
            "dimension": {
                "package_length": product.package_dim_cm[0],
                "package_width": product.package_dim_cm[1],
                "package_height": product.package_dim_cm[2],
            },
            "logistic_info": [
                {
                    "logistic_id": product.logistic_id,
                    "enabled": True,
                    "is_free": False,
                    "shipping_fee": 0,
                }
            ],
            "image": {"image_id_list": product.image_ids},
            "normal_stock": product.stock,
            "pre_order": {
                "is_pre_order": True,
                "days_to_ship": 7,
            },
        }

        if product.tier_variations:
            tier = product.tier_variations
            data["tier_variation"] = tier.get("tier_variation", [])
            data["variation"] = tier.get("variation", [])

        result = self._request("POST", path, data)
        if result.get("error") == 0 or result.get("error") is None:
            item_id = result.get("response", {}).get("item_id")
            logger.info(f"Product created: {item_id}")
            return item_id
        logger.error(f"Create product failed: {result}")
        return None

    def publish_item(self, item_id: int) -> bool:
        path = "/api/v2/product/unlist_item"
        data = {
            "item_id": [item_id],
            "unlist": False,
        }
        result = self._request("POST", path, data)
        success = result.get("error") == 0 or result.get("error") is None
        if success:
            logger.info(f"Product published: {item_id}")
        else:
            logger.error(f"Publish failed: {result}")
        return success

    def close(self):
        self.client.close()
