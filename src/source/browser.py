"""Browser automation manager using Patchright (Playwright fork with anti-detection).
100% bypass rate on browsers-benchmark (vs 60% plain Playwright, 90% CloakBrowser).
"""
from src.utils.logger import setup_logger

logger = setup_logger("browser")

_pw = None


def _get_pw():
    global _pw
    if _pw is None:
        from patchright.sync_api import sync_playwright
        _pw = sync_playwright().start()
    return _pw


class BrowserManager:
    def __init__(self, headless: bool = True, proxy: str | None = None, cookies: list[dict] | None = None):
        self.headless = headless
        self.proxy = proxy
        self.cookies = cookies or []
        self._browser = None

    def start(self):
        pw = _get_pw()
        launch_opts = {
            "headless": self.headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        }
        if self.proxy:
            launch_opts["proxy"] = {"server": self.proxy}
        self._browser = pw.chromium.launch(**launch_opts)
        logger.info(f"Patchright browser started (headless={self.headless})")
        return self

    def stop(self):
        if self._browser:
            self._browser.close()
            self._browser = None
        logger.info("Browser stopped")

    def new_page(self):
        context = self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )
        if self.cookies:
            context.add_cookies(self.cookies)
        page = context.new_page()
        return context, page
