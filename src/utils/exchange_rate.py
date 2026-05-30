import asyncio, time, json
from pathlib import Path
from src.utils.logger import setup_logger

logger = setup_logger("exchange_rate")

FALLBACK_RATE = 3500
API_URL = "https://open.er-api.com/v6/latest/CNY"
CACHE_TTL_SECONDS = 12 * 3600
CACHE_FILE = Path("data/exchange_rate_cache.json")


def _read_cache() -> float | None:
    try:
        if not CACHE_FILE.exists():
            return None
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        if time.time() - data.get("updated_at", 0) < CACHE_TTL_SECONDS:
            return data.get("rate")
    except Exception as e:
        logger.debug(f"Cache read failed: {e}")
    return None


def _write_cache(rate: float):
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps({"rate": rate, "updated_at": time.time()}), encoding="utf-8")
    except Exception as e:
        logger.debug(f"Cache write failed: {e}")


async def fetch_cny_vnd_rate() -> float:
    """Fetch live CNY→VND rate from API. Returns FALLBACK_RATE on failure."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(API_URL)
            resp.raise_for_status()
            data = resp.json()
            rate = data.get("rates", {}).get("VND")
            if rate is None:
                logger.warning("VND rate not found in API response, using fallback")
                return FALLBACK_RATE
            logger.info(f"Live rate: 1 CNY = {rate:.2f} VND")
            return float(rate)
    except httpx.TimeoutException:
        logger.warning("Exchange rate API timeout, using fallback")
    except httpx.RequestError as e:
        logger.warning(f"Exchange rate API error: {e}, using fallback")
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning(f"Exchange rate parse error: {e}, using fallback")
    return FALLBACK_RATE


async def get_cny_vnd_rate() -> float:
    cached = _read_cache()
    if cached is not None:
        return cached
    rate = await fetch_cny_vnd_rate()
    _write_cache(rate)
    return rate


def _round_price(raw: float) -> int:
    return int((raw + 999) // 1000 * 1000)


async def async_calculate_final_price(cny_price: float, multiplier: float = 2.5) -> int:
    """Async version: calculate final VND price using live rate + multiplier."""
    rate = await get_cny_vnd_rate()
    return _round_price(cny_price * rate * multiplier)


def calculate_final_price(cny_price: float, multiplier: float = 2.5) -> int:
    """Sync version: calculate final VND price using live rate + multiplier.
    Rounds up to nearest 1000 VND.
    Falls back to cached rate, then fetches live rate if no cache.
    """
    cached = _read_cache()
    if cached is not None:
        return _round_price(cny_price * cached * multiplier)
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            rate = FALLBACK_RATE
        else:
            rate = asyncio.run(get_cny_vnd_rate())
    except RuntimeError:
        rate = asyncio.run(get_cny_vnd_rate())
    return _round_price(cny_price * rate * multiplier)
