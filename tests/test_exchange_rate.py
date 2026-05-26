"""Tests for exchange_rate module."""
import sys, time, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.exchange_rate import (
    FALLBACK_RATE, _round_price, _read_cache, _write_cache, calculate_final_price
)


def test_fallback_rate():
    assert FALLBACK_RATE == 3500


def test_round_price():
    assert _round_price(1000) == 1000
    assert _round_price(1001) == 2000
    assert _round_price(1500) == 2000
    assert _round_price(0) == 0


def test_cache():
    _write_cache(3600.0)
    cached = _read_cache()
    assert cached == 3600.0


def test_cache_expired():
    cache_file = Path("data/exchange_rate_cache.json")
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    old = time.time() - 86400 * 2
    cache_file.write_text(json.dumps({"rate": 999.0, "updated_at": old}), encoding="utf-8")
    cached = _read_cache()
    assert cached is None


def test_calculate_final_price():
    price = calculate_final_price(10, 2.5)
    assert price > 0
    assert price % 1000 == 0


if __name__ == "__main__":
    test_fallback_rate()
    test_round_price()
    test_cache()
    test_cache_expired()
    test_calculate_final_price()
    print("ALL PASS")
