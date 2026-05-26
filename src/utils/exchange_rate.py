import asyncio, time, sqlite3, json
from pathlib import Path
from src.utils.logger import setup_logger

logger = setup_logger("exchange_rate")

FALLBACK_RATE = 3500
API_URL = "https://open.er-api.com/v6/latest/CNY"
CACHE_TTL_SECONDS = 12 * 3600  # 12 hours
CACHE_DB = Path("data/exchange_rate_cache.db")


def _init_cache():
    CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CACHE_DB))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS rate_cache ("
        "  currency TEXT PRIMARY KEY,"
        "  rate REAL,"
        "  updated_at REAL"
        ")"
    )
    conn.commit()
    return conn


def _read_cache() -> float | None:
    try:
        conn = _init_cache()
        row = conn.execute(
            "SELECT rate, updated_at FROM rate_cache WHERE currency = 'VND'"
        ).fetchone()
        conn.close()
        if row and (time.time() - row[1]) < CACHE_TTL_SECONDS:
            logger.info(f"Using cached rate: {row[0]:.2f} VND/CNY")
            return row[0]
    except Exception as e:
        logger.debug(f"Cache read failed: {e}")
    return None


def _write_cache(rate: float):
    try:
        conn = _init_cache()
        conn.execute(
            "REPLACE INTO rate_cache (currency, rate, updated_at) VALUES (?, ?, ?)",
            ("VND", rate, time.time()),
        )
        conn.commit()
        conn.close()
        logger.info(f"Cached rate: {rate:.2f} VND/CNY")
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
    Falls back to cached rate, then FALLBACK_RATE if fetch fails.
    """
    try:
        loop = asyncio.get_running_loop()
        # Already in an async context — can't asyncio.run(), try cache
        cached = _read_cache()
        rate = cached if cached is not None else FALLBACK_RATE
    except RuntimeError:
        # No running loop — safe to use asyncio.run()
        rate = asyncio.run(get_cny_vnd_rate())
    return _round_price(cny_price * rate * multiplier)
