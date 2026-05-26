import asyncio, re
from typing import Optional
from src.utils.logger import setup_logger

logger = setup_logger("translator")

_CN_VI_DICT = {
    # Điện thoại & phụ kiện
    "手机壳": "ốp lưng điện thoại", "手机": "điện thoại", "壳": "ốp lưng",
    "钢化膜": "kính cường lực", "膜": "miếng dán", "钢化": "cường lực",
    "充电器": "bộ sạc", "充电宝": "sạc dự phòng", "充电线": "cáp sạc",
    "充电": "sạc", "数据线": "cáp dữ liệu", "线": "cáp",
    "无线充": "sạc không dây", "耳机": "tai nghe", "蓝牙耳机": "tai nghe bluetooth",
    "蓝牙": "bluetooth", "音箱": "loa", "支架": "giá đỡ",
    "手机支架": "giá đỡ điện thoại", "车载支架": "giá đỡ ô tô",
    # Nhà bếp & gia dụng
    "厨房用具": "đồ dùng nhà bếp", "厨房": "nhà bếp", "厨具": "dụng cụ nấu ăn", "锅": "nồi",
    "空气炸锅": "nồi chiên không dầu", "炸锅": "nồi chiên",
    "碗": "bát", "杯": "ly/cốc", "壶": "ấm", "刀": "dao",
    "板": "thớt", "收纳": "cất giữ", "收纳盒": "hộp đựng đồ",
    "储物": "lưu trữ", "置物架": "kệ để đồ", "挂钩": "móc treo",
    "保温": "giữ nhiệt", "保温杯": "bình giữ nhiệt", "水杯": "cốc nước",
    "便当盒": "hộp cơm", "保鲜": "bảo quản tươi", "保鲜盒": "hộp bảo quản",
    "餐具": "bộ đồ ăn", "用具": "đồ dùng", "用品": "đồ dùng", "配件": "phụ kiện",
    "筷子": "đũa", "勺子": "thìa",
    # Thời trang & phụ kiện
    "包": "túi", "背包": "ba lô", "手提包": "túi xách tay",
    "钱包": "ví", "斜挎包": "túi đeo chéo", "双肩包": "ba lô 2 quai",
    "袋": "túi", "箱": "thùng/vali", "行李箱": "vali",
    "鞋": "giày", "运动鞋": "giày thể thao", "帽": "mũ",
    "衣": "áo", "衣服": "quần áo", "裤": "quần",
    "袜": "vớ/tất", "围巾": "khăn quàng", "手套": "găng tay",
    "腰带": "thắt lưng", "领带": "cà vạt", "扣": "khóa/móc",
    # Trang sức
    "项链": "dây chuyền", "链": "dây chuyền", "手链": "vòng tay",
    "戒": "nhẫn", "戒指": "nhẫn", "镯子": "vòng tay",
    "耳环": "bông tai", "耳钉": "bông tai", "手镯": "vòng tay",
    "手表": "đồng hồ đeo tay", "表": "đồng hồ",
    # Điện tử
    "充电器": "bộ sạc", "充电宝": "sạc dự phòng",
    "转换器": "bộ chuyển đổi", "适配器": "bộ chuyển đổi",
    "鼠标": "chuột máy tính", "键盘": "bàn phím", "摄像头": "webcam",
    "U盘": "USB", "硬盘": "ổ cứng",
    # Làm đẹp
    "化妆品": "mỹ phẩm", "化妆": "trang điểm", "护肤品": "sản phẩm dưỡng da",
    "美容": "làm đẹp", "口红": "son môi", "唇膏": "son dưỡng môi",
    "粉底": "kem nền", "睫毛": "lông mi", "眼影": "phấn mắt",
    "指甲": "móng tay", "指甲油": "sơn móng tay",
    "刷子": "cọ", "化妆刷": "cọ trang điểm",
    # Thú cưng
    "宠物": "thú cưng", "宠物用品": "đồ dùng thú cưng",
    "猫": "mèo", "狗": "chó",
    "猫粮": "thức ăn cho mèo", "狗粮": "thức ăn cho chó",
    "猫砂": "cát vệ sinh cho mèo", "猫窝": "ổ cho mèo",
    "狗绳": "dây dắt chó", "狗窝": "ổ cho chó",
    "宠物玩具": "đồ chơi thú cưng",
    # Đồ chơi
    "玩具": "đồ chơi", "娃娃": "búp bê",
    "遥控": "điều khiển từ xa", "遥控车": "xe điều khiển",
    "积木": "xếp hình", "拼图": "ghép hình",
    # Thể thao ngoài trời
    "户外": "ngoài trời", "登山": "leo núi", "徒步": "đi bộ đường dài",
    "露营": "cắm trại", "帐篷": "lều trại", "睡袋": "túi ngủ",
    "背包": "ba lô", "登山杖": "gậy leo núi",
    # Xe hơi
    "汽车": "xe hơi", "车载": "trên xe", "车充": "sạc ô tô",
    # Khác
    "绳": "dây", "带": "dây đeo", "环": "vòng", "夹": "kẹp",
    "灯": "đèn", "LED": "đèn LED", "器": "thiết bị",
    "机": "máy", "盒": "hộp", "套装": "bộ sản phẩm",
    "新款": "mẫu mới", "热销": "bán chạy", "包邮": "miễn phí vận chuyển",
    "批发": "bán buôn", "一件代发": "dropship", "跨境": "xuyên biên giới",
    "工具": "dụng cụ", "清洁": "vệ sinh", "防护": "bảo vệ",
}


class TextTranslator:
    def __init__(self, config: dict):
        ai_cfg = config.get("ai", {}).get("translation", {}) if config else {}
        self.api_key = ai_cfg.get("api_key", "") or (config.get("ai", {}).get("caption", {}).get("api_key", "") if config else "")
        self.provider = ai_cfg.get("provider", "google_gemini") if config else ""
        self._gemini_failed = False

    def translate(self, text: str, target: str = "vi") -> str:
        if not text:
            return ""
        dict_result = self._dict_translate(text)
        if dict_result != text:
            return dict_result
        ai_result = self._ai_translate(text, target)
        if ai_result and ai_result != text:
            return ai_result
        return dict_result

    async def translate_async(self, text: str, target: str = "vi") -> str:
        if not text:
            return ""
        dict_result = self._dict_translate(text)
        if dict_result != text:
            return dict_result
        return await self._ai_translate_async(text, target) or dict_result

    def _dict_translate(self, text: str) -> str:
        result = text
        for cn, vi in sorted(_CN_VI_DICT.items(), key=lambda x: -len(x[0])):
            if cn in result:
                result = result.replace(cn, vi)
        return result

    def _ai_translate(self, text: str, target: str) -> str:
        if not self.api_key or self._gemini_failed:
            return text
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel("gemini-2.0-flash")
            prompt = f"Dịch đoạn sau sang tiếng Việt (chỉ trả về bản dịch, không giải thích):\n{text}"
            resp = model.generate_content(prompt, generation_config={"max_output_tokens": 200})
            result = resp.text.strip()
            if result and result != text:
                return result
        except Exception as e:
            logger.debug(f"AI translation failed: {e}")
            self._gemini_failed = True
        return text

    async def _ai_translate_async(self, text: str, target: str) -> str:
        return await asyncio.to_thread(self._ai_translate, text, target)
