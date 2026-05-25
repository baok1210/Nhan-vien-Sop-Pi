"""Auto-Pilot Customer Care & Review Farmer — automated lifecycle messaging
via Shopee Chat API v2 + LLM for review incentives.

Sends messages at key order lifecycle stages:
1. Thank-you + confirmation (on order placement)
2. In-warehouse notification (when stock arrives in Vietnam)
3. Post-delivery voucher for 5-star review
"""
import json, random
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from src.publisher.shopee import ShopeeClient
from src.utils.logger import setup_logger

logger = setup_logger("customer_care")

MESSAGE_TEMPLATES = {
    "order_confirmed": {
        "vi": "Cảm ơn {customer_name} đã đặt hàng tại shop {shop_name}! "
              "Đơn hàng {order_sn} đang được đóng gói. Shop sẽ gửi thông tin vận đơn sớm nhất. 🎉",
    },
    "in_warehouse": {
        "vi": "Chào {customer_name}, hàng của bạn đã về kho Việt Nam! "
              "Đơn hàng {order_sn} đang được bàn giao cho shipper giao hàng. "
              "Dự kiến nhận hàng trong 2-3 ngày tới. 📦",
    },
    "delivered_review": {
        "vi": "Chào {customer_name}, cảm ơn bạn đã nhận hàng! "
              "Nếu hài lòng với sản phẩm {product_name}, bạn có thể để lại "
              "đánh giá 5 sao để nhận mã giảm giá {discount}% cho đơn sau nhé! "
              "Mã: {voucher_code} 💝",
    },
}


class CustomerCareBot:
    def __init__(self, config: dict, store_id: str):
        self.store_id = store_id
        self.store_dir = Path("data") / store_id
        self.client = ShopeeClient(config) if self._has_creds(config) else None
        self.shop_name = config.get("name", store_id)
        cc = config.get("customer_care", {})
        self.enabled = cc.get("enabled", True)
        self.review_discount = int(cc.get("review_voucher_discount_pct", 5))
        self.cooldown_hours = int(cc.get("cooldown_between_messages_hours", 48))
        self._sent_log: list[dict] = self._load_sent_log()

    def _has_creds(self, config: dict) -> bool:
        s = config.get("shopee", {})
        return bool(s.get("partner_id") and s.get("partner_key") and s.get("access_token"))

    def _load_sent_log(self) -> list[dict]:
        path = self.store_dir / "customer_care_log.json"
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_sent_log(self):
        path = self.store_dir / "customer_care_log.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._sent_log, f, ensure_ascii=False, indent=2)

    def _already_sent(self, order_sn: str, message_type: str) -> bool:
        cutoff = datetime.now() - timedelta(hours=self.cooldown_hours)
        for entry in self._sent_log:
            if entry["order_sn"] == order_sn and entry["message_type"] == message_type:
                try:
                    if datetime.fromisoformat(entry["sent_at"]) > cutoff:
                        return True
                except ValueError:
                    continue
        return False

    def _log_sent(self, order_sn: str, message_type: str, content: str, customer_name: str):
        self._sent_log.append({
            "order_sn": order_sn,
            "message_type": message_type,
            "content": content[:100],
            "customer_name": customer_name,
            "sent_at": datetime.now().isoformat(),
            "store_id": self.store_id,
        })
        self._save_sent_log()

    # ── Voucher generation ────────────────────────────────────────

    def _generate_voucher_code(self, order_sn: str) -> str:
        """Generate a deterministic pseudo-unique voucher code."""
        suffix = random.randint(1000, 9999)
        return f"REVIEW{order_sn[-6:]}{suffix}"

    # ── LLM message personalization ───────────────────────────────

    def _personalize(
        self, template: str, customer_name: str, order_sn: str,
        product_name: str = "", voucher_code: str = "",
    ) -> str:
        return template.format(
            customer_name=customer_name,
            shop_name=self.shop_name,
            order_sn=order_sn,
            product_name=product_name or "sản phẩm",
            discount=self.review_discount,
            voucher_code=voucher_code,
        )

    def _llm_personalize(self, template: str, context: dict) -> str:
        """Use LLM to personalize message if API key is configured."""
        ai_cfg = context.get("ai", {}).get("caption", {})
        api_key = ai_cfg.get("api_key", "")
        if not api_key:
            return self._personalize(template, **context)
        try:
            import google.genai as genai
            client = genai.Client(api_key=api_key)
            prompt = (
                f"Viết lại tin nhắn chăm sóc khách hàng Shopee sau đây "
                f"bằng tiếng Việt tự nhiên, thân thiện, giữ nguyên các placeholder:\n\n"
                f"Template: {template}\n\n"
                f"Thông tin: tên khách={context.get('customer_name','')}, "
                f"shop={context.get('shop_name','')}, "
                f"mã đơn={context.get('order_sn','')}, "
                f"sản phẩm={context.get('product_name','')}\n\n"
                f"Chỉ trả về tin nhắn, không giải thích."
            )
            resp = client.models.generate_content(
                model=ai_cfg.get("model", "gemini-2.0-flash"),
                contents=prompt,
            )
            return resp.text.strip()
        except Exception as e:
            logger.debug(f"LLM personalization failed: {e}")
            return self._personalize(template, **context)

    # ── Send messages ─────────────────────────────────────────────

    def _send_shopee_message(self, order_sn: str, message: str, customer_name: str) -> bool:
        """Send message via Shopee Chat API v2."""
        if not self.client:
            logger.warning("Shopee client not available, message not sent")
            return False
        try:
            path = "/api/v2/chat/send_message"
            data = {"order_sn": order_sn, "message": message}
            result = self.client._request("POST", path, data)
            success = result.get("error") is None or result.get("error") == 0
            if success:
                logger.info(f"Message sent to {customer_name} (order {order_sn})")
            else:
                logger.error(f"Send message failed: {result}")
            return success
        except Exception as e:
            logger.error(f"Send message error: {e}")
            return False

    # ── Lifecycle triggers ────────────────────────────────────────

    def on_order_confirmed(self, order_sn: str, customer_name: str, config: dict):
        if not self.enabled or self._already_sent(order_sn, "order_confirmed"):
            return False
        template = MESSAGE_TEMPLATES["order_confirmed"]["vi"]
        message = self._llm_personalize(template, {
            "customer_name": customer_name,
            "shop_name": self.shop_name,
            "order_sn": order_sn,
            "product_name": "",
            "voucher_code": "",
            "ai": config.get("ai", {}),
        })
        ok = self._send_shopee_message(order_sn, message, customer_name)
        if ok:
            self._log_sent(order_sn, "order_confirmed", message, customer_name)
        return ok

    def on_warehouse_arrival(self, order_sn: str, customer_name: str, config: dict):
        if not self.enabled or self._already_sent(order_sn, "in_warehouse"):
            return False
        template = MESSAGE_TEMPLATES["in_warehouse"]["vi"]
        message = self._llm_personalize(template, {
            "customer_name": customer_name,
            "shop_name": self.shop_name,
            "order_sn": order_sn,
            "product_name": "",
            "voucher_code": "",
            "ai": config.get("ai", {}),
        })
        ok = self._send_shopee_message(order_sn, message, customer_name)
        if ok:
            self._log_sent(order_sn, "in_warehouse", message, customer_name)
        return ok

    def on_delivery_success(self, order_sn: str, customer_name: str,
                            product_name: str, config: dict):
        if not self.enabled or self._already_sent(order_sn, "delivered_review"):
            return False
        voucher = self._generate_voucher_code(order_sn)
        template = MESSAGE_TEMPLATES["delivered_review"]["vi"]
        message = self._llm_personalize(template, {
            "customer_name": customer_name,
            "shop_name": self.shop_name,
            "order_sn": order_sn,
            "product_name": product_name or "sản phẩm",
            "voucher_code": voucher,
            "ai": config.get("ai", {}),
        })
        ok = self._send_shopee_message(order_sn, message, customer_name)
        if ok:
            self._log_sent(order_sn, "delivered_review", message, customer_name)
        return ok

    # ── Batch: process all orders from fulfillment ────────────────

    def process_fulfillment_orders(self, config: dict) -> dict:
        """Process all orders in orders_to_fulfill.json and send lifecycle messages."""
        if not self.enabled:
            return {"sent": 0, "skipped": 0, "error": "disabled"}

        path = Path("data") / "orders_to_fulfill.json"
        if not path.exists():
            return {"sent": 0, "skipped": 0, "error": "no_fulfillment_data"}

        try:
            with open(path, encoding="utf-8") as f:
                orders = json.load(f)
        except Exception as e:
            return {"sent": 0, "skipped": 0, "error": str(e)}

        sent = 0
        skipped = 0
        for order in orders:
            sn = order.get("order_sn", "")
            customer = order.get("customer_name", "Khách hàng")
            product = order.get("source_title_cn", "")

            if self.on_order_confirmed(sn, customer, config):
                sent += 1
            else:
                skipped += 1

            if self.on_delivery_success(sn, customer, product, config):
                sent += 1
            else:
                skipped += 1

        logger.info(f"Customer care: {sent} sent, {skipped} skipped")
        return {"sent": sent, "skipped": skipped}

    def close(self):
        if self.client:
            self.client.close()
