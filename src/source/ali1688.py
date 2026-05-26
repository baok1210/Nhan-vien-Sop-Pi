import re, json, time, random, os, sqlite3, shutil, tempfile
from pathlib import Path
from urllib.parse import urlencode
from curl_cffi import requests as curl_requests
from src.models.product import ProductSource
from src.utils.logger import setup_logger

logger = setup_logger("1688_scraper")

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
]


def extract_chrome_cookies(domain="1688.com"):
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    paths = [
        Path(local_app_data) / "Google" / "Chrome" / "User Data" / "Default" / "Network" / "Cookies",
        Path(local_app_data) / "Google" / "Chrome" / "User Data" / "Default" / "Cookies",
    ]
    cookie_path = next((p for p in paths if p.exists()), None)
    if not cookie_path:
        return {}

    tmp = tempfile.mktemp(suffix=".db")
    try:
        shutil.copy2(str(cookie_path), tmp)
        conn = sqlite3.connect(tmp)
        cursor = conn.cursor()
        rows = cursor.execute(
            "SELECT host_key, name, value FROM cookies WHERE host_key LIKE ?",
            (f"%{domain}%",),
        ).fetchall()
        conn.close()
        return {row[1]: row[2] for row in rows if row[2]}
    except Exception:
        return {}
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


class Ali1688Scraper:
    SEARCH_URL = "https://s.1688.com/selloffer/offer_search.htm"

    def __init__(self, config: dict):
        self.max_pages = config.get("max_pages", 3)
        self.delay = config.get("delay_seconds", 3)
        self.dropship_only = config.get("dropship_filter", True)
        self.proxy = config.get("proxy", "")
        self._session = curl_requests.Session()
        self._session.impersonate = "chrome120"
        self._browser_mgr = None

        # Load cookies: config cookies > Chrome cookies
        config_cookies = config.get("cookies", {})
        if config_cookies:
            self._cookies = config_cookies
            logger.info(f"Đã tải {len(self._cookies)} cookie từ config")
            self._session.cookies.update(self._cookies)
        else:
            self._cookies = extract_chrome_cookies()
            if self._cookies:
                logger.info(f"Đã tải {len(self._cookies)} cookie từ Chrome cho 1688")
                self._session.cookies.update(self._cookies)
            else:
                logger.warning(
                    "Không tìm thấy cookie 1688. "
                    "Hãy đăng nhập 1688.com trong Chrome, hoặc đặt cookie trong config."
                )

    def _headers(self, referer=None):
        h = {
            "User-Agent": random.choice(_USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        if referer:
            h["Referer"] = referer
        return h

    def search(self, keyword: str, page: int = 1) -> list[ProductSource]:
        params = {
            "keywords": keyword,
            "n": "y",
            "pageNum": page,
        }
        if self.dropship_only:
            params["isDropship"] = "true"

        url = f"{self.SEARCH_URL}?{urlencode(params)}"
        referer = f"{self.SEARCH_URL}?keywords={urlencode({'': keyword})[1:]}"

        for attempt in range(3):
            try:
                resp = self._session.get(
                    url, headers=self._headers(referer), timeout=30
                )
                resp.raise_for_status()
                html = resp.text
                if len(html) < 5000 or "验证" in html[:2000] or "安全验证" in html[:2000]:
                    logger.warning(f"1688 CAPTCHA/anti-bot cho '{keyword}' (attempt {attempt+1})")
                    if attempt < 2:
                        time.sleep(random.uniform(5, 10) * (attempt + 1))
                        continue
                    return self._search_with_playwright(keyword, page)
                return self._parse_products(html, keyword)
            except Exception as e:
                logger.error(f"1688 lỗi '{keyword}' trang {page} (attempt {attempt+1}): {e}")
                if attempt < 2:
                    time.sleep(random.uniform(5, 10) * (attempt + 1))
                else:
                    if "CAPTCHA" in str(e) or "captcha" in str(e):
                        return self._search_with_playwright(keyword, page)
        return []

    def _search_with_playwright(self, keyword: str, page: int = 1) -> list[ProductSource]:
        try:
            from src.source.browser import BrowserManager
            if self._browser_mgr is None:
                self._browser_mgr = BrowserManager(headless=True, proxy=self.proxy or None)
                self._browser_mgr.start()
            import random as _r
            ctx, page_obj = self._browser_mgr.new_page()

            params = {"keywords": keyword, "n": "y", "pageNum": page}
            url = f"{self.SEARCH_URL}?{urlencode(params)}"
            page_obj.goto(url, timeout=60000, wait_until="domcontentloaded")
            page_obj.wait_for_timeout(random.randint(3000, 5000))
            html = page_obj.content()

            ctx.close()
            return self._parse_products(html, keyword)
        except Exception as e:
            logger.error(f"Playwright 1688 search failed: {e}")
            return []

    def _parse_products(self, html: str, keyword: str = "") -> list[ProductSource]:
        products = []

        json_products = self._extract_json_data(html)
        if json_products:
            for item in json_products:
                try:
                    product = self._parse_json_item(item)
                    if product:
                        products.append(product)
                except Exception as e:
                    logger.warning(f"Parse 1688 JSON item failed: {e}")

        if not products:
            products = self._extract_offer_list(html)

        if not products:
            products = self._parse_from_html(html)

        return products

    def _extract_json_data(self, html: str) -> list[dict] | None:
        # Strategy 1: window.__NUXT__ state
        m = re.search(r'window\.__NUXT__\s*=\s*(\{.*?\});', html, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
                offers = self._deep_find_offers(data)
                if offers:
                    logger.info(f"Tìm thấy {len(offers)} sản phẩm từ __NUXT__")
                    return offers
            except json.JSONDecodeError:
                pass

        # Strategy 2: iDetailData or offerList patterns
        for pattern in [
            r'"offerList"\s*:\s*(\[.*?\])', r'"iDetailData"\s*:\s*(\[.*?\])',
            r'"data"\s*:\s*(\[.*?\])\s*,\s*"page',
            r'"data"\s*:\s*(\[.*?\])\s*}\s*\)',
        ]:
            m = re.search(pattern, html, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(1))
                    if isinstance(data, list) and len(data) > 0:
                        items = [d for d in data if isinstance(d, dict) and ("offerId" in d or "productId" in d)]
                        if items:
                            return items
                except json.JSONDecodeError:
                    continue

        # Strategy 3: broad JSON content search
        for m in re.finditer(r'(?:\[|\{)\s*"[^"]*"(?:\s*:\s*[^,}]+,?\s*){3,}', html[:500000], re.DOTALL):
            try:
                content = json.loads("{" + m.group() + "}")
                if isinstance(content, dict):
                    items = self._deep_find_offers(content)
                    if items:
                        return items
            except (json.JSONDecodeError, ValueError):
                continue

        return None

    def _deep_find_offers(self, obj: dict, depth: int = 0) -> list[dict] | None:
        if depth > 5:
            return None
        if isinstance(obj, dict):
            for key in ("offerList", "iDetailData", "items", "data", "result", "list"):
                val = obj.get(key)
                if isinstance(val, list) and len(val) > 0:
                    sample = val[0]
                    if isinstance(sample, dict) and ("offerId" in sample or "productId" in sample or "subject" in sample):
                        return val
                result = self._deep_find_offers(val, depth + 1) if isinstance(val, dict) else None
                if result:
                    return result
            for key, val in obj.items():
                if isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict):
                    if any(k in val[0] for k in ("offerId", "productId", "subject")):
                        return val
        return None

    def _extract_offer_list(self, html: str) -> list[ProductSource]:
        products = []
        # Parse offer card HTML structure
        import re as _re
        # Look for offer-card patterns in 1688 HTML
        cards = _re.findall(
            r'<div[^>]*class="[^"]*offer-card[^"]*"[^>]*>.*?</div>\s*</div>\s*</div>',
            html[:500000], _re.DOTALL | _re.IGNORECASE
        )
        if not cards:
            cards = _re.findall(
                r'<div[^>]*data-offer-id="(\d+)"[^>]*>.*?</div>\s*</div>',
                html[:500000], _re.DOTALL
            )
            if cards:
                for card_html in cards:
                    pid_m = _re.search(r'data-offer-id="(\d+)"', card_html)
                    title_m = _re.search(r'title="([^"]+)"', card_html)
                    price_m = _re.search(r'price[^"]*"[^>]*>([\d.]+)', card_html)
                    img_m = _re.search(r'<img[^>]+src="([^"]+)"', card_html)
                    products.append(ProductSource(
                        id=pid_m.group(1) if pid_m else "",
                        title_cn=title_m.group(1) if title_m else "",
                        price_cny=float(price_m.group(1)) if price_m else 0,
                        original_price_cny=float(price_m.group(1)) if price_m else 0,
                        image_urls=[img_m.group(1)] if img_m else [],
                        description_cn="", category_name_cn="",
                        platform="1688", is_dropship=self.dropship_only,
                    ))
        return products

    def _parse_json_item(self, item: dict) -> ProductSource | None:
        oid = str(item.get("offerId") or item.get("productId") or "")
        if not oid:
            return None

        title = item.get("subject", item.get("title", ""))
        raw_price = item.get("price", item.get("offerPrice", 0))
        if isinstance(raw_price, str):
            raw_price = _re.sub(r'[^\d.]', '', raw_price)
        try: price = float(raw_price)
        except (TypeError, ValueError): price = 0.0
        raw_orig = item.get("originalPrice", price)
        if isinstance(raw_orig, str):
            raw_orig = _re.sub(r'[^\d.]', '', raw_orig)
        try: orig_price = float(raw_orig)
        except (TypeError, ValueError): orig_price = price

        imgs = item.get("imageList", item.get("images", []))
        if isinstance(imgs, str):
            imgs = [imgs]
        image_urls = []
        for img in imgs[:9]:
            if isinstance(img, dict):
                url = img.get("url", img.get("imgUrl", ""))
            else:
                url = str(img)
            if url:
                if url.startswith("//"):
                    url = "https:" + url
                image_urls.append(url)

        detail_url = item.get("detailUrl", item.get("url", ""))
        if detail_url and not detail_url.startswith("http"):
            detail_url = "https:" + detail_url

        has_ds = bool(item.get("supportDropshipping", item.get("isDropship", False)))

        return ProductSource(
            id=oid,
            title_cn=title,
            price_cny=price,
            original_price_cny=orig_price,
            image_urls=image_urls,
            description_cn=item.get("description", ""),
            category_name_cn=item.get("categoryName", ""),
            supplier_name=item.get("companyName", item.get("supplierName", "")),
            supplier_rating=float(item.get("supplierRating", 0)),
            sales_count=int(item.get("sales", item.get("salesCount", 0))),
            detail_url=detail_url,
            platform="1688",
            is_dropship=has_ds or self.dropship_only,
        )

    def _parse_from_html(self, html: str) -> list[ProductSource]:
        from parsel import Selector

        sel = Selector(text=html)
        products = []

        offer_links = sel.css("a[href*='/offer/']")
        for link in offer_links:
            href = link.attrib.get("href", "")
            id_match = re.search(r"/offer/(\d+)", href)
            if not id_match:
                continue

            text = link.css("::text").get("", "").strip()
            if not text:
                parent = link.root.getparent()
                if parent is not None:
                    text = (parent.text or "").strip()

            price = 0.0
            card_html = link.root.getparent().text_content() if link.root.getparent() is not None else ""
            price_m = _re.search(r'price[^"]*"[^>]*>([\d.]+)', card_html)
            if price_m:
                try: price = float(price_m.group(1))
                except ValueError: pass
            if not price:
                price_m2 = _re.search(r'([\d]+(?:\.[\d]+)?)\s*(?:元|¥)', text + " " + card_html)
                if price_m2:
                    try: price = float(price_m2.group(1))
                    except ValueError: pass

            products.append(ProductSource(
                id=id_match.group(1),
                title_cn=text,
                price_cny=price,
                original_price_cny=price,
                image_urls=[],
                description_cn="",
                category_name_cn="",
                platform="1688",
                is_dropship=self.dropship_only,
                detail_url=href if href.startswith("http") else f"https:{href}",
            ))

        return products

    def crawl_by_keywords(self, keywords: list[str]) -> list[ProductSource]:
        if not self._cookies:
            logger.warning(
                "No 1688 cookies available. "
                "Please login to 1688.com in Chrome, then run again."
            )
            return []

        all_products = []
        for kw in keywords:
            logger.info(f"Crawling 1688: {kw}")
            for page_num in range(1, self.max_pages + 1):
                products = self.search(kw, page_num)
                if not products:
                    logger.info(f"  No products on page {page_num}")
                    break
                all_products.extend(products)
                logger.info(f"  Page {page_num}: {len(products)} products")
                time.sleep(self.delay + random.uniform(1, 3))

        # Filter by supplier score if configured
        cfg = getattr(self, '_store_config', None)
        if cfg:
            try:
                from src.source.supplier_scorer import SupplierCreditScorer
                scorer = SupplierCreditScorer(cfg)
                filtered = scorer.filter_products(all_products)
                if filtered is not all_products:
                    logger.info(f"Supplier filter: {len(all_products)} -> {len(filtered)} products")
                    all_products = filtered
                scorer.close()
            except Exception as e:
                logger.debug(f"Supplier scoring skipped: {e}")

        logger.info(f"1688 total: {len(all_products)} products")
        return all_products

    def close(self):
        if self._session:
            self._session.close()
        if self._browser_mgr:
            try:
                self._browser_mgr.stop()
            except Exception:
                pass
