import re, json, time, random
from urllib.parse import urlencode
from curl_cffi import requests as curl_requests
from src.models.product import ProductSource
from src.utils.logger import setup_logger

logger = setup_logger("aliexpress_scraper")


class AliExpressScraper:
    SEARCH_URL = "https://www.aliexpress.com/wholesale"

    def __init__(self, config: dict):
        self.max_pages = config.get("max_pages", 3)
        self.delay = config.get("delay_seconds", 2)
        self.proxy = config.get("proxy")
        self._session = curl_requests.Session()
        self._session.impersonate = "chrome120"

    def _headers(self):
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
        }

    def search(self, keyword: str, page: int = 1) -> list[ProductSource]:
        params = {kw: v for kw, v in {"SearchText": keyword, "page": page}.items() if v}
        url = f"{self.SEARCH_URL}?{urlencode(params)}"

        try:
            resp = self._session.get(url, headers=self._headers(), timeout=30)
            resp.raise_for_status()
            html = resp.text
            # Detect x5sec punishment page (typically ~2KB of redirect JS)
            if len(html) < 10000:
                logger.warning(f"AliExpress returned anti-bot page (x5sec) for '{keyword}'")
                return []
            return self._parse_products(html)
        except Exception as e:
            logger.error(f"Search failed for '{keyword}' page {page}: {e}")
            return []

    def _parse_products(self, html: str) -> list[ProductSource]:
        products = []
        script_data = self._extract_item_list(html)
        if script_data:
            for item in script_data:
                try:
                    product = self._parse_item(item)
                    if product:
                        products.append(product)
                except Exception as e:
                    logger.warning(f"Parse item failed: {e}")

        if not products:
            products = self._parse_from_html(html)

        return products

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
        prices_data = item.get("prices", item.get("pricing", {}))
        if isinstance(prices_data, dict):
            price = float(prices_data.get("minPrice", {}).get("value", 0))
        elif isinstance(prices_data, list) and prices_data:
            price = float(prices_data[0].get("value", 0))

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
        for selector in [".search-item-card-wrapper-gallery", "[class*='product-item']", "[class*='card']", "[class*='list-item']"]:
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
                    price_match = re.search(r'[\d,.]+', price_text.replace(",", ""))
                    if price_match:
                        try:
                            price = float(price_match.group().replace(",", ""))
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
                        if isinstance(prices, dict):
                            mp = prices.get("minPrice", prices.get("min_price", {}))
                            if isinstance(mp, dict):
                                price = float(mp.get("value", 0))
                        elif isinstance(prices, list) and prices:
                            price = float(prices[0].get("value", 0))
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

    def crawl_by_keywords(self, keywords: list[str]) -> list[ProductSource]:
        all_products = []
        for kw in keywords:
            logger.info(f"Crawling AliExpress: {kw}")
            for page_num in range(1, self.max_pages + 1):
                products = self.search(kw, page_num)
                if not products:
                    break
                all_products.extend(products)
                logger.info(f"  Page {page_num}: {len(products)} products")
                time.sleep(self.delay + random.uniform(0.5, 1.5))
        logger.info(f"AliExpress total: {len(all_products)} products")
        return all_products

    def close(self):
        if self._session:
            self._session.close()
