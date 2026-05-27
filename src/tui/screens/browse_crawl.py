import asyncio, time

from textual.screen import Screen
from textual.widgets import Header, Footer, Button, Static, Log
from textual.containers import VerticalScroll
from textual import work

from src.source.aliexpress import AliExpressScraper
from src.source.ali1688 import Ali1688Scraper
from src.discovery import add_to_pool

BROAD_KEYWORDS = [
    {"en": "hiking shoes", "cn": "登山鞋"},
    {"en": "trekking pole", "cn": "登山杖"},
    {"en": "camping tent", "cn": "帐篷"},
    {"en": "cat toys", "cn": "猫玩具"},
    {"en": "dog leash", "cn": "狗绳"},
    {"en": "pet bed", "cn": "宠物窝"},
    {"en": "phone case", "cn": "手机壳"},
    {"en": "phone holder", "cn": "手机支架"},
    {"en": "makeup brush", "cn": "化妆刷"},
    {"en": "nail art", "cn": "美甲"},
    {"en": "kitchen storage", "cn": "厨房收纳"},
    {"en": "home organizer", "cn": "家居收纳"},
    {"en": "wallet", "cn": "钱包"},
    {"en": "sunglasses", "cn": "太阳镜"},
    {"en": "bluetooth speaker", "cn": "蓝牙音箱"},
    {"en": "usb cable", "cn": "数据线"},
    {"en": "yoga mat", "cn": "瑜伽垫"},
    {"en": "resistance band", "cn": "弹力带"},
    {"en": "puzzle", "cn": "拼图"},
    {"en": "rc car", "cn": "遥控车"},
]


class BrowseCrawlScreen(Screen):
    def compose(self):
        yield Header(show_clock=True)
        yield VerticalScroll(
            Static("🔍 Crawl tổng hợp đa chủ đề", classes="title"),
            Static("Hệ thống sẽ crawl từ nhiều keyword khác nhau để xây dựng kho sản phẩm.", classes="subtitle"),
            Static(f"Số lượng keyword: {len(BROAD_KEYWORDS)}", id="kw-count"),
            Static("", id="crawl-status"),
            Button("▶️ Bắt đầu crawl", variant="success", id="start-crawl"),
            Button("← Quay lại", variant="default", id="back"),
            Log(id="crawl-log"),
            id="crawl-content",
        )
        yield Footer()

    def write_log(self, msg: str):
        self.query_one("#crawl-log").write_line(f"[{time.strftime('%H:%M:%S')}] {msg}")

    @work
    async def do_crawl(self):
        self.write_log("🔄 Bắt đầu crawl...")
        self.write_log("  ⚠️ Cần cookies 1688 từ Chrome để crawl 1688 (nếu chưa có sẽ bỏ qua)")
        total = 0
        for i, kw in enumerate(BROAD_KEYWORDS, 1):
            self.write_log(f"  [{i}/{len(BROAD_KEYWORDS)}] {kw['en']} / {kw['cn']}")
            self.query_one("#crawl-status").update(f"Đang crawl: {kw['en']} ({i}/{len(BROAD_KEYWORDS)})")
            ae = AliExpressScraper({"max_pages": 1, "delay_seconds": 1})
            try:
                products = await asyncio.get_event_loop().run_in_executor(
                    None, ae.crawl_by_keywords, [kw["en"]]
                )
                raw = []
                for p in products:
                    raw.append({
                        "id": f"ae_{p.id}", "title_cn": p.title_cn or kw.get("cn", ""),
                        "title_en": kw["en"], "price_cny": p.price_cny,
                        "image_urls": p.image_urls, "detail_url": p.detail_url,
                        "platform": p.platform, "source_keyword": kw["en"],
                    })
                added = add_to_pool(raw)
                total += len(raw)
                if added:
                    self.write_log(f"    ✅ +{added} sản phẩm (AE)")
            except Exception as exc:
                self.write_log(f"    ⚠️ AE lỗi: {exc}")
            finally:
                ae.close()
            c8 = Ali1688Scraper({"max_pages": 1, "delay_seconds": 1, "dropship_filter": True})
            try:
                products = await asyncio.get_event_loop().run_in_executor(
                    None, c8.crawl_by_keywords, [kw["cn"]]
                )
                raw = []
                for p in products:
                    raw.append({
                        "id": f"1688_{p.id}", "title_cn": p.title_cn or kw.get("cn", ""),
                        "title_en": kw["en"], "price_cny": p.price_cny,
                        "image_urls": p.image_urls, "detail_url": p.detail_url,
                        "platform": p.platform, "source_keyword": kw["cn"],
                    })
                added = add_to_pool(raw)
                total += len(raw)
                if added:
                    self.write_log(f"    ✅ +{added} sản phẩm (1688)")
            except Exception as exc:
                self.write_log(f"    ⚠️ 1688 lỗi: {exc}")
            finally:
                c8.close()
            await asyncio.sleep(1)
        self.query_one("#crawl-status").update(f"✅ Hoàn thành! Tổng: {total} sản phẩm")
        self.write_log(f"✅ Crawl xong! {total} sản phẩm được thêm vào pool.")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "back":
            self.app.pop_screen()
        elif event.button.id == "start-crawl":
            self.do_crawl()
