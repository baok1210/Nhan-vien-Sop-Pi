import re, json, time, random
from urllib.parse import urlencode
from curl_cffi import requests as curl_requests
from src.models.product import ProductSource
from src.utils.logger import setup_logger

logger = setup_logger("aliexpress_scraper")

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
]


class AliExpressScraper:
    SEARCH_URL = "https://www.aliexpress.com/wholesale"

    def __init__(self, config: dict):
        self.max_pages = config.get("max_pages", 3)
        self.delay = config.get("delay_seconds", 2)
        self.proxy = config.get("proxy")
        self.cookies = config.get("cookies")
        self._session = self._new_session()
        self._browser_mgr = None

    def _new_session(self):
        s = curl_requests.Session()
        s.impersonate = random.choice(["chrome120", "chrome110", "chrome107", "chrome99"])
        if self.proxy:
            s.proxies = {"http": self.proxy, "https": self.proxy}
        if self.cookies:
            for c in self.cookies if isinstance(self.cookies, list) else [self.cookies]:
                if isinstance(c, dict) and "name" in c and "value" in c:
                    s.cookies.set(c["name"], c["value"])
        return s

    def _headers(self):
        return {
            "User-Agent": random.choice(_USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": random.choice(["en-US,en;q=0.9", "zh-CN,zh;q=0.9", "vi-VN,vi;q=0.9"]),
        }

    def search(self, keyword: str, page: int = 1) -> list[ProductSource]:
        params = {kw: v for kw, v in {"SearchText": keyword, "page": page}.items() if v}
        url = f"{self.SEARCH_URL}?{urlencode(params)}"

        for attempt in range(3):
            try:
                if attempt > 0:
                    delay = random.uniform(5.0 * attempt, 10.0 * attempt)
                    logger.info(f"  Retry {attempt+1}/3 sau {delay:.0f}s...")
                    time.sleep(delay)
                    self._session = self._new_session()
                resp = self._session.get(url, headers=self._headers(), timeout=30)
                resp.raise_for_status()
                html = resp.text

                anti_bot_signals = [
                    len(html) < 10000,
                    "x5sec" in html[:5000],
                    "verify" in html[:3000].lower(),
                    "机器人" in html[:3000],
                    "captcha" in html[:3000].lower(),
                ]
                if any(anti_bot_signals):
                    logger.warning(f"AliExpress anti-bot (attempt {attempt+1}) cho '{keyword}'")
                    continue

                products = self._parse_products(html)
                if products:
                    logger.info(f"AliExpress: {len(products)} sp từ '{keyword}' trang {page}")
                    return products
                return []
            except Exception as e:
                logger.error(f"AliExpress lỗi '{keyword}' trang {page} (attempt {attempt+1}): {e}")
        logger.warning(f"curl_cffi failed, trying Playwright cho '{keyword}'...")
        return self._search_with_playwright(keyword, page)

    def _parse_products(self, html: str) -> list[ProductSource]:
        products = []

        extractors = [
            self._extract_from_window_state,
            self._extract_from_html_scripts,
            self._extract_item_list,
            self._extract_from_inline_json,
        ]

        for extractor in extractors:
            try:
                data = extractor(html)
                if data:
                    for item in data:
                        try:
                            product = self._parse_item(item)
                            if product:
                                products.append(product)
                        except Exception as e:
                            logger.warning(f"Parse item failed: {e}")
                    if products:
                        break
            except Exception:
                continue

        if not products:
            products = self._parse_from_html(html)

        return products

    def _extract_from_window_state(self, html: str) -> list[dict] | None:
        """Extract product list from window.__INITIAL_STATE__ or __RENDER_DATA__."""
        for pattern in [
            r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});',
            r'window\.__RENDER_DATA__\s*=\s*(\{.*?\});',
            r'window\.__NUXT__\s*=\s*(\{.*?\});',
        ]:
            m = re.search(pattern, html, re.DOTALL)
            if not m:
                continue
            try:
                state = json.loads(m.group(1))
                # Navigate common paths to find product listing
                for path in [
                    ["listing", "items", "product"],
                    ["productList", "items"],
                    ["data", "items"],
                    ["props", "pageProps", "items"],
                    ["items"],
                ]:
                    obj = state
                    for key in path:
                        if isinstance(obj, dict):
                            obj = obj.get(key, {})
                        else:
                            break
                    if isinstance(obj, list) and len(obj) > 0:
                        items = [i for i in obj if i.get("productId") or i.get("itemId")]
                        if items:
                            logger.info(f"Found {len(items)} products via window state ({pattern[:30]}...)")
                            return items
            except (json.JSONDecodeError, ValueError, TypeError):
                continue
        return None

    def _extract_from_html_scripts(self, html: str) -> list[dict] | None:
        """Extract from <script type=\"application/json\"> tags or data: JSON blocks."""
        # Try <script type="application/json"> tags
        for m in re.finditer(
            r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>',
            html, re.DOTALL,
        ):
            try:
                data = json.loads(m.group(1).strip())
                if isinstance(data, list):
                    items = [i for i in data if i.get("productId") or i.get("itemId")]
                    if items:
                        logger.info(f"Found {len(items)} products via JSON script tags")
                        return items
                elif isinstance(data, dict):
                    # Search nested for product arrays
                    items = self._find_product_list(data)
                    if items:
                        return items
            except (json.JSONDecodeError, ValueError):
                continue

        # Try galite data (AliExpress analytics embed)
        for m in re.finditer(r'galite\s*=\s*(\{.*?\})\s*;', html, re.DOTALL):
            try:
                data = json.loads(m.group(1))
                items = self._find_product_list(data)
                if items:
                    logger.info(f"Found {len(items)} products via galite data")
                    return items
            except (json.JSONDecodeError, ValueError):
                continue

        return None

    def _find_product_list(self, obj: dict) -> list[dict] | None:
        """Recursively search a nested dict for arrays of products."""
        if isinstance(obj, dict):
            for key, val in obj.items():
                if isinstance(val, list) and len(val) > 0:
                    sample = val[0]
                    if isinstance(sample, dict) and ("productId" in sample or "itemId" in sample):
                        return val
                result = self._find_product_list(val) if isinstance(val, dict) else None
                if result:
                    return result
        return None

    def _extract_item_list(self, html: str) -> list[dict] | None:
        """Extract product data from embedded JSON in script tags."""
        for m in re.finditer(r'"content"\s*:\s*(\[.*?\])', html, re.DOTALL):
            snippet = m.group(1)
            if "productId" not in snippet:
                continue
            try:
                content = json.loads(snippet)
                if isinstance(content, list):
                    items = [c for c in content if "productId" in c and "title" in c]
                    if items:
                        return items
            except json.JSONDecodeError:
                continue
        return None

    def _parse_item(self, item: dict) -> ProductSource | None:
        pid = str(item.get("productId") or item.get("redirectedId") or "")
        if not pid:
            return None

        title = ""
        title_data = item.get("title", {})
        if isinstance(title_data, dict):
            title = title_data.get("displayTitle", title_data.get("title", ""))
        elif isinstance(title_data, str):
            title = title_data

        image_url = ""
        img_data = item.get("image", {})
        if isinstance(img_data, dict):
            image_url = img_data.get("imgUrl", "")

        price = 0.0
        # Try flat price keys first
        try:
            raw = item.get("price") or item.get("minPrice") or item.get("salePrice") or item.get("originalPrice")
            if raw:
                price = float(re.sub(r'[^\d.]', '', str(raw)))
        except (TypeError, ValueError, AttributeError): pass
        if not price:
            prices_data = item.get("prices", item.get("pricing", {}))
            if isinstance(prices_data, dict):
                mp = prices_data.get("minPrice", prices_data.get("min_price", {}))
                if isinstance(mp, dict):
                    price = float(mp.get("value", 0))
                else:
                    try: price = float(mp)
                    except (TypeError, ValueError): pass
            elif isinstance(prices_data, list) and prices_data:
                p0 = prices_data[0]
                if isinstance(p0, dict):
                    price = float(p0.get("value") or p0.get("price") or 0)
                else:
                    try: price = float(p0)
                    except (TypeError, ValueError): pass

        sales_count = 0
        trade = item.get("trade", item.get("sales", {}))
        if isinstance(trade, dict):
            sales_count = int(trade.get("sales", trade.get("salesCount", 0)))

        rating = 0.0
        rating_data = item.get("rating", item.get("evaluation", {}))
        if isinstance(rating_data, dict):
            rating = float(rating_data.get("rating", rating_data.get("score", 0)))

        supplier = ""
        store = item.get("store", item.get("shop", {}))
        if isinstance(store, dict):
            supplier = store.get("name", store.get("storeName", ""))

        item_url = item.get("itemUrl", "")
        if item_url and not item_url.startswith("http"):
            item_url = "https:" + item_url

        images = [f"https:{image_url}"] if image_url and not image_url.startswith("http") else [image_url] if image_url else []

        return ProductSource(
            id=pid,
            title_cn=title,
            price_cny=price,
            original_price_cny=price,
            image_urls=images,
            description_cn="",
            category_name_cn="",
            supplier_name=supplier,
            supplier_rating=rating,
            sales_count=sales_count,
            detail_url=item_url,
            platform="aliexpress",
            is_dropship=True,
        )

    def _parse_from_html(self, html: str) -> list[ProductSource]:
        from parsel import Selector
        sel = Selector(text=html)
        products = []

        # Try multiple card selectors (AliExpress changes class names frequently)
        cards = []
        for selector in [
            ".search-item-card-wrapper-gallery",
            "[class*='product-item']",
            "[class*='card']",
            "[class*='list-item']",
            "[class*='item']",
            "div[data-role*='item']",
            "[class*='product']",
        ]:
            cards = sel.css(selector)
            if cards:
                break

        for card in cards:
            link = card.css("a[href*='/item/']")
            href = link.attrib.get("href", "") if link else ""
            if not href:
                continue

            pid_match = re.search(r'/item/(\d+)', href)
            pid = pid_match.group(1) if pid_match else ""

            # Image: try multiple attributes
            img_el = card.css("img")
            img_src = ""
            if img_el:
                img_src = img_el.attrib.get("src", "") or img_el.attrib.get("data-src", "")

            # Title: try multiple selectors
            title = ""
            for ts in ["[class*='title']", "[class*='name']", "h2", "h3"]:
                title_el = card.css(ts)
                if title_el:
                    title = "".join(title_el.css("*::text").getall()).strip()
                    if title:
                        break

            # Price: try to find price text
            price = 0.0
            for ps in ["[class*='price']", "[class*='cost']"]:
                price_el = card.css(ps)
                if price_el:
                    price_text = "".join(price_el.css("*::text").getall()).strip()
                    price_match = re.search(r'[\d]+(?:[\.,]\d+)?', price_text.replace(",", ""))
                    if price_match:
                        try:
                            price = float(price_match.group())
                        except ValueError:
                            pass
                        break

            if not href.startswith("http"):
                href = "https:" + href
            if img_src and not img_src.startswith("http"):
                img_src = "https:" + img_src

            products.append(ProductSource(
                id=pid,
                title_cn=title,
                price_cny=price,
                original_price_cny=price,
                image_urls=[img_src] if img_src else [],
                description_cn="",
                category_name_cn="",
                platform="aliexpress",
                is_dropship=True,
            ))

        # Try extracting from inline JSON if CSS parsing got nothing
        if not products:
            products = self._extract_from_inline_json(html)

        return products

    def _extract_from_inline_json(self, html: str) -> list[ProductSource]:
        """Try to extract product data from inline JSON anywhere in HTML."""
        products = []
        # Look for JSON arrays containing productId
        for m in re.finditer(r'\[\s*\{.*?"productId".*?\}\s*\]', html, re.DOTALL):
            snippet = m.group()
            if "title" not in snippet:
                continue
            try:
                data = json.loads(snippet)
                if isinstance(data, list):
                    for item in data:
                        pid = str(item.get("productId") or item.get("redirectedId") or "")
                        if not pid:
                            continue
                        title_data = item.get("title", {})
                        title = ""
                        if isinstance(title_data, dict):
                            title = title_data.get("displayTitle", title_data.get("title", ""))
                        elif isinstance(title_data, str):
                            title = title_data
                        image_data = item.get("image", {})
                        img_url = ""
                        if isinstance(image_data, dict):
                            img_url = image_data.get("imgUrl", "")
                            if img_url and not img_url.startswith("http"):
                                img_url = "https:" + img_url
                        prices = item.get("prices", item.get("pricing", {}))
                        price = 0.0
                        # Try flat price keys first
                        try:
                            raw = item.get("price") or item.get("minPrice") or item.get("salePrice") or item.get("originalPrice")
                            if raw:
                                price = float(re.sub(r'[^\d.]', '', str(raw)))
                        except (TypeError, ValueError, AttributeError): pass
                        if not price:
                            if isinstance(prices, dict):
                                mp = prices.get("minPrice", prices.get("min_price", {}))
                                if isinstance(mp, dict):
                                    price = float(mp.get("value", 0))
                                else:
                                    try: price = float(mp)
                                    except (TypeError, ValueError): pass
                            elif isinstance(prices, list) and prices:
                                p0 = prices[0]
                                if isinstance(p0, dict):
                                    price = float(p0.get("value") or p0.get("price") or 0)
                                else:
                                    try: price = float(p0)
                                    except (TypeError, ValueError): pass
                        products.append(ProductSource(
                            id=pid, title_cn=title, price_cny=price,
                            original_price_cny=price, image_urls=[img_url] if img_url else [],
                            description_cn="", category_name_cn="", platform="aliexpress", is_dropship=True,
                        ))
                    if products:
                        return products
            except (json.JSONDecodeError, ValueError):
                continue
        return products

    def _search_with_playwright(self, keyword: str, page: int = 1) -> list[ProductSource]:
        try:
            from src.source.browser import BrowserManager
            if self._browser_mgr is None:
                self._browser_mgr = BrowserManager(headless=True, proxy=self.proxy or None)
                self._browser_mgr.start()
            ctx, page_obj = self._browser_mgr.new_page()
            params = {"SearchText": keyword, "page": page}
            url = f"{self.SEARCH_URL}?{urlencode(params)}"
            logger.info(f"Playwright loading {url}")
            page_obj.goto(url, timeout=60000, wait_until="networkidle")
            page_obj.wait_for_timeout(random.randint(3000, 5000))
            html = page_obj.content()
            ctx.close()
            if len(html) > 10000:
                logger.info(f"Playwright success: {len(html)} bytes")
                return self._parse_products(html)
            return []
        except Exception as e:
            logger.error(f"Playwright AliExpress failed: {e}")
            return []

    def crawl_by_keywords(self, keywords: list[str]) -> list[ProductSource]:
        all_products = []
        for kw in keywords:
            logger.info(f"Đang crawl AliExpress: {kw}")
            for page_num in range(1, self.max_pages + 1):
                products = self.search(kw, page_num)
                if not products:
                    logger.info(f"  Hết sản phẩm ở trang {page_num}")
                    break
                all_products.extend(products)
                logger.info(f"  Trang {page_num}: {len(products)} sản phẩm")
                wait = self.delay + random.uniform(2, 5)
                logger.info(f"  Chờ {wait:.0f}s trước request tiếp theo...")
                time.sleep(wait)
        logger.info(f"AliExpress tổng cộng: {len(all_products)} sản phẩm")
        return all_products

    def close(self):
        if self._session:
            self._session.close()
        if self._browser_mgr:
            try:
                self._browser_mgr.stop()
            except Exception:
                pass
