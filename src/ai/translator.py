import asyncio
from src.utils.logger import setup_logger

logger = setup_logger("ai_translator")

_CN_VI_DICT = {
    "手机壳": "ốp lưng điện thoại", "手机": "điện thoại", "壳": "ốp lưng",
    "钢化膜": "kính cường lực", "膜": "miếng dán",
    "充电器": "bộ sạc", "充电宝": "sạc dự phòng", "充电线": "cáp sạc",
    "数据线": "cáp dữ liệu", "线": "cáp",
    "耳机": "tai nghe", "蓝牙耳机": "tai nghe bluetooth", "音箱": "loa",
    "支架": "giá đỡ", "手机支架": "giá đỡ điện thoại",
    "厨房用具": "đồ dùng nhà bếp", "厨房": "nhà bếp", "厨具": "dụng cụ nấu ăn",
    "空气炸锅": "nồi chiên không dầu", "锅": "nồi",
    "收纳": "cất giữ", "收纳盒": "hộp đựng đồ",
    "保温杯": "bình giữ nhiệt", "水杯": "cốc nước",
    "包": "túi", "背包": "ba lô", "钱包": "ví",
    "鞋": "giày", "运动鞋": "giày thể thao", "帽": "mũ",
    "衣": "áo", "裤": "quần", "袜": "vớ/tất",
    "项链": "dây chuyền", "手链": "vòng tay", "戒指": "nhẫn",
    "耳环": "bông tai", "手表": "đồng hồ",
    "鼠标": "chuột máy tính", "键盘": "bàn phím",
    "口红": "son môi", "化妆刷": "cọ trang điểm",
    "宠物": "thú cưng", "猫": "mèo", "狗": "chó",
    "玩具": "đồ chơi", "积木": "xếp hình", "拼图": "ghép hình",
    "户外": "ngoài trời", "登山": "leo núi", "帐篷": "lều trại",
    "一件代发": "dropship", "新款": "mẫu mới", "热销": "bán chạy",
    "包邮": "miễn phí vận chuyển", "批发": "bán buôn",
}

_FALLBACK_TEMPLATES = {
    "default": {
        "title": "Sản phẩm chất lượng cao - Giá tốt nhất thị trường",
        "description": "Sản phẩm được nhập khẩu trực tiếp, đảm bảo chất lượng và giá cả cạnh tranh. Liên hệ ngay để được tư vấn!",
        "bullet_points": ["Chất lượng cao", "Giá cả cạnh tranh", "Giao hàng nhanh", "Bảo hành đầy đủ", "Hỗ trợ đổi trả"],
        "hashtags": ["sanphamchatluong", "banchay", "giaca canhtranh", "dropship", "shopee"],
    }
}


class Translator:
    def __init__(self, config: dict | None = None):
        self.config = config or {}
        ai_cfg = self.config.get("ai", {}).get("translation", {}) or {}
        caption_cfg = self.config.get("ai", {}).get("caption", {}) or {}
        self.api_key = ai_cfg.get("api_key", "") or caption_cfg.get("api_key", "")
        self.provider = ai_cfg.get("provider", "google_gemini")
        self._gemini_failed = False

    def translate(self, text: str, target: str = "vi") -> str:
        if not text or not text.strip():
            return self._fallback_text()

        dict_result = self._translate_dict(text)
        if dict_result != text:
            logger.info(f"  Dịch [dict]: '{text[:30]}...' → '{dict_result[:30]}...'")
            return dict_result

        ai_result = self._translate_ai(text, target)
        if ai_result and ai_result != text:
            logger.info(f"  Dịch [AI]: '{text[:30]}...' → '{ai_result[:30]}...'")
            return ai_result

        logger.warning(f"  Dịch [template]: '{text[:30]}...' (cả dict + AI đều thất bại)")
        return self._fallback_text()

    async def translate_async(self, text: str, target: str = "vi") -> str:
        return await asyncio.to_thread(self.translate, text, target)

    def _translate_dict(self, text: str) -> str:
        result = text
        for cn, vi in sorted(_CN_VI_DICT.items(), key=lambda x: -len(x[0])):
            if cn in result:
                result = result.replace(cn, vi)
        return result

    def _translate_ai(self, text: str, target: str) -> str | None:
        if not self.api_key or self._gemini_failed:
            return None
        try:
            if self.provider == "google_gemini":
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                model = genai.GenerativeModel("gemini-2.0-flash")
                prompt = (
                    f"Dịch đoạn sau sang tiếng Việt (chỉ trả về bản dịch, không giải thích):\n{text}"
                )
                resp = model.generate_content(prompt, generation_config={"max_output_tokens": 200})
                result = resp.text.strip()
                if result and result != text:
                    return result
            elif self.provider == "openai":
                from openai import OpenAI
                client = OpenAI(api_key=self.api_key)
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": f"Dịch sang tiếng Việt:\n{text}"}],
                    max_tokens=200,
                )
                result = resp.choices[0].message.content.strip()
                if result and result != text:
                    return result
        except Exception as e:
            logger.debug(f"AI translation failed: {e}")
            self._gemini_failed = True
        return None

    def _fallback_text(self) -> str:
        return _FALLBACK_TEMPLATES["default"]["title"]
