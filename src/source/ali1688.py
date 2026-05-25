import re, json, time, random, os, sqlite3, shutil, tempfile
from pathlib import Path
from urllib.parse import urlencode
from curl_cffi import requests as curl_requests
from src.models.product import ProductSource
from src.utils.logger import setup_logger

logger = setup_logger("1688_scraper")


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

        # Try to load Chrome cookies
        self._cookies = extract_chrome_cookies()
        if self._cookies:
            logger.info(f"Loaded {len(self._cookies)} cookies from Chrome for 1688")
            self._session.cookies.update(self._cookies)
        else:
            logger.warning(
                "No 1688 cookies found in Chrome. "
                "Login to 1688.com in Chrome first, or set cookies manually."
            )

    def _headers(self, referer=None):
        h = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
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

        try:
            resp = self._session.get(
                url, headers=self._headers(referer), timeout=30
            )
            resp.raise_for_status()
            return self._parse_products(resp.text, keyword)
        except Exception as e:
            logger.error(f"Search failed for '{keyword}' page {page}: {e}")
            return []

    def _parse_products(self, html: str, keyword: str = "") -> list[ProductSource]:
        products = []

        # Try embedded JSON data (similar to AliExpress pattern)
        json_products = self._extract_json_data(html)
        if json_products:
            for item in json_products:
                try:
                    product = self._parse_json_item(item)
                    if product:
                        products.append(product)
                except Exception as e:
                    logger.warning(f"Parse 1688 JSON item failed: {e}")

        # Fallback: parse HTML for offer links and basic info
        if not products:
            products = self._parse_from_html(html)

        return products

    def _extract_json_data(self, html: str) -> list[dict] | None:
        for m in re.finditer(r'"content"\s*:\s*(\[.*?\])', html, re.DOTALL):
            snippet = m.group(1)
            if "offerId" not in snippet:
                continue
            try:
                content = json.loads(snippet)
                if isinstance(content, list):
                    items = [c for c in content if "offerId" in c]
                    if items:
                        return items
            except json.JSONDecodeError:
                continue
        return None

    def _parse_json_item(self, item: dict) -> ProductSource | None:
        oid = str(item.get("offerId") or item.get("productId") or "")
        if not oid:
            return None

        title = item.get("subject", item.get("title", ""))
        price = float(item.get("price", item.get("offerPrice", 0)))
        orig_price = float(item.get("originalPrice", price))

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

            products.append(ProductSource(
                id=id_match.group(1),
                title_cn=text,
                price_cny=0,
                original_price_cny=0,
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
