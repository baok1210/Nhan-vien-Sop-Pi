"""Tests for image_processor URL parsing and basic logic."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.processing.image_processor import ImageProcessor


def test_get_ext_jpg():
    p = ImageProcessor({})
    assert p._get_ext("https://example.com/photo.jpg") == "jpg"
    assert p._get_ext("https://example.com/photo.jpeg?v=123") == "jpeg"
    assert p._get_ext("https://example.com/photo.png#fragment") == "png"


def test_get_ext_webp():
    p = ImageProcessor({})
    assert p._get_ext("https://example.com/image.webp") == "webp"


def test_get_ext_no_ext():
    p = ImageProcessor({})
    assert p._get_ext("https://example.com/photo") == "jpg"


def test_get_ext_query_params():
    p = ImageProcessor({})
    url = "https://example.com/image.jpg?x-oss-process=image/resize,m_fixed"
    assert p._get_ext(url) == "jpg"


def test_get_ext_gif():
    p = ImageProcessor({})
    assert p._get_ext("https://example.com/animated.gif") == "gif"


def test_get_ext_bmp():
    p = ImageProcessor({})
    assert p._get_ext("https://example.com/logo.bmp") == "bmp"


if __name__ == "__main__":
    test_get_ext_jpg()
    test_get_ext_webp()
    test_get_ext_no_ext()
    test_get_ext_query_params()
    test_get_ext_gif()
    test_get_ext_bmp()
    print("ALL PASS")
