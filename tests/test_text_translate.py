"""Tests for text_translate dictionary-based translation."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.processing.text_translate import TextTranslator


def test_dict_translate_phone_case():
    t = TextTranslator({})
    result = t.translate("手机壳 iPhone 15")
    assert "ốp lưng điện thoại" in result


def test_dict_translate_charger():
    t = TextTranslator({})
    result = t.translate("无线充电器")
    assert "sạc không dây" in result or "sạc" in result


def test_dict_translate_empty():
    t = TextTranslator({})
    assert t.translate("") == ""


def test_dict_translate_no_match():
    t = TextTranslator({})
    result = t.translate("something completely unrelated")
    assert result == "something completely unrelated"


def test_dict_translate_kitchen():
    t = TextTranslator({})
    result = t.translate("厨房用具套装")
    assert "nhà bếp" in result or "dụng cụ nấu ăn" in result


def test_dict_translate_pet():
    t = TextTranslator({})
    result = t.translate("宠物玩具 猫 狗")
    assert "thú cưng" in result
    assert "mèo" in result
    assert "chó" in result


def test_async_translate():
    import asyncio
    t = TextTranslator({})
    result = asyncio.run(t.translate_async("蓝牙耳机"))
    assert "tai nghe bluetooth" in result or "bluetooth" in result


if __name__ == "__main__":
    test_dict_translate_phone_case()
    test_dict_translate_charger()
    test_dict_translate_empty()
    test_dict_translate_no_match()
    test_dict_translate_kitchen()
    test_dict_translate_pet()
    test_async_translate()
    print("ALL PASS")
