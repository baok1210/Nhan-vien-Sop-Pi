import asyncio
from typing import Optional
from src.utils.logger import setup_logger

logger = setup_logger("translator")

_SIMPLE_DICT = {
    "手机": "điện thoại", "壳": "ốp lưng", "膜": "miếng dán", "钢化": "cường lực",
    "充电": "sạc", "线": "cáp", "耳机": "tai nghe", "蓝牙": "bluetooth",
    "支架": "giá đỡ", "包": "túi", "袋": "túi", "箱": "thùng", "盒": "hộp",
    "绳": "dây", "带": "dây đeo", "扣": "khóa", "环": "vòng", "夹": "kẹp",
    "灯": "đèn", "器": "thiết bị", "机": "máy", "锅": "nồi", "碗": "bát",
    "杯": "ly/cốc", "壶": "ấm", "刀": "dao", "板": "thớt/bảng",
    "鞋": "giày", "帽": "mũ", "衣": "áo", "裤": "quần",
    "表": "đồng hồ", "链": "dây chuyền", "戒": "nhẫn", "镯": "vòng tay",
    "玩具": "đồ chơi", "娃娃": "búp bê", "汽车": "xe hơi", "工具": "dụng cụ",
}


class TextTranslator:
    def __init__(self, config: dict):
        self.enabled = True

    def translate(self, text: str, target: str = "vi") -> str:
        if not text:
            return ""
        try:
            loop = asyncio.get_running_loop()
            return self._fallback_translate(text)
        except RuntimeError:
            pass
        try:
            result = asyncio.run(self._translate_async(text, target))
            if result and result != text:
                return result
            return self._fallback_translate(text)
        except Exception as e:
            logger.debug(f"Translation failed: {e}")
            return self._fallback_translate(text)

    async def translate_async(self, text: str, target: str = "vi") -> str:
        if not text:
            return ""
        try:
            result = await self._translate_async(text, target)
            if result and result != text:
                return result
            return self._fallback_translate(text)
        except Exception as e:
            logger.debug(f"Translation async failed: {e}")
            return self._fallback_translate(text)

    async def _translate_async(self, text: str, target: str) -> str:
        from googletrans import Translator as GTranslator
        t = GTranslator()
        result = await t.translate(text, dest=target)
        return result.text or text

    def _fallback_translate(self, text: str) -> str:
        result = text
        for cn, vi in _SIMPLE_DICT.items():
            if cn in result:
                result = result.replace(cn, vi)
        return result if result != text else text
