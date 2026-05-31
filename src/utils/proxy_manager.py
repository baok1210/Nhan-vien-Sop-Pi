import random, time
from src.utils.logger import setup_logger

logger = setup_logger("proxy_manager")


class ProxyManager:
    def __init__(self, proxy_list: list[str] | None = None):
        self._all = proxy_list or []
        self._blacklist: set[int] = set()
        self._index = 0
        self._current = None

    @classmethod
    def from_config(cls, config: dict, source: str = "1688"):
        proxies = config.get("sources", {}).get(source, {}).get("proxies", [])
        if isinstance(proxies, str):
            proxies = [p.strip() for p in proxies.replace("\n", ",").split(",") if p.strip()]
        return cls(proxies if proxies else None)

    @property
    def available(self) -> list[str]:
        return [p for i, p in enumerate(self._all) if i not in self._blacklist]

    @property
    def has_proxy(self) -> bool:
        return len(self.available) > 0

    def get(self) -> str | None:
        if not self._all:
            return None
        available = self.available
        if not available:
            self._blacklist.clear()
            available = self._all
        proxy = random.choice(available)
        self._index = self._all.index(proxy)
        self._current = proxy
        return proxy

    def mark_failed(self, proxy: str | None = None):
        if proxy is None:
            proxy = self._current
        if proxy and proxy in self._all:
            idx = self._all.index(proxy)
            self._blacklist.add(idx)
            logger.info(f"  Proxy thất bại, blacklist: {len(self._blacklist)}/{len(self._all)}")
            if len(self._blacklist) >= len(self._all):
                logger.warning("  Hết proxy, reset blacklist — thử lại từ đầu")
                self._blacklist.clear()
                time.sleep(5)

    def next_on_fail(self) -> str | None:
        self.mark_failed()
        return self.get()

    def test_all(self) -> list[tuple[str, bool, float]]:
        import subprocess, time, urllib.request
        results = []
        for proxy in self._all:
            t0 = time.time()
            ok = False
            try:
                handler = urllib.request.ProxyHandler({
                    "http": proxy, "https": proxy
                })
                opener = urllib.request.build_opener(handler)
                opener.open("https://httpbin.org/ip", timeout=10)
                ok = True
            except:
                pass
            elapsed = round(time.time() - t0, 2)
            results.append((proxy, ok, elapsed))
            status = "✅" if ok else "❌"
            logger.info(f"  {status} {proxy} ({elapsed}s)")
        return results
