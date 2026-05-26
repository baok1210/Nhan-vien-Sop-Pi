import asyncio, json, time, io
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, Button, Static, Label, Input, Log, ListView, ListItem
from textual.containers import Horizontal, Vertical, VerticalScroll, Container
from textual import work

from src.config_manager import list_stores, load_store, save_store, create_store, delete_store
from src.source.aliexpress import AliExpressScraper
from src.source.ali1688 import Ali1688Scraper
from src.discovery import load_pool, add_to_pool, discover_niches, create_shop_from_suggestion
from src.processing.image_processor import ImageProcessor
from src.processing.video_processor import VideoProcessor
from src.ai.caption_gen import CaptionGenerator
from src.publisher.shopee import ShopeeClient
from src.publisher.order_manager import OrderManager
from src.publisher.flash_sale import FlashSaleManager
from src.publisher.cashflow_planner import CashFlowPlanner
from src.publisher.virtual_hub import VirtualHub
from src.publisher.customer_care import CustomerCareBot
from src.trends.trend_hijacker import TrendDetector
from src.source.supplier_scorer import SupplierCreditScorer
from src.utils.exchange_rate import async_calculate_final_price
from src.utils.logger import setup_logger

logger = setup_logger("tui")

# ── Broad keywords để crawl discovery ──────────────────────────
BROAD_KEYWORDS = [
    # Climbing & Hiking
    {"en": "hiking shoes", "cn": "登山鞋"},
    {"en": "trekking pole", "cn": "登山杖"},
    {"en": "camping tent", "cn": "帐篷"},
    # Pet
    {"en": "cat toys", "cn": "猫玩具"},
    {"en": "dog leash", "cn": "狗绳"},
    {"en": "pet bed", "cn": "宠物窝"},
    # Phone
    {"en": "phone case", "cn": "手机壳"},
    {"en": "phone holder", "cn": "手机支架"},
    # Beauty
    {"en": "makeup brush", "cn": "化妆刷"},
    {"en": "nail art", "cn": "美甲"},
    # Home & Kitchen
    {"en": "kitchen storage", "cn": "厨房收纳"},
    {"en": "home organizer", "cn": "家居收纳"},
    # Fashion
    {"en": "wallet", "cn": "钱包"},
    {"en": "sunglasses", "cn": "太阳镜"},
    # Electronics
    {"en": "bluetooth speaker", "cn": "蓝牙音箱"},
    {"en": "usb cable", "cn": "数据线"},
    # Sports
    {"en": "yoga mat", "cn": "瑜伽垫"},
    {"en": "resistance band", "cn": "弹力带"},
    # Toys
    {"en": "puzzle", "cn": "拼图"},
    {"en": "rc car", "cn": "遥控车"},
]


# ── CONFIRM SCREEN ──────────────────────────────────────────────
class ConfirmScreen(Screen):
    """Simple yes/no confirmation before running a pipeline step."""
    def __init__(self, title: str, message: str, confirm_id: str):
        super().__init__()
        self.confirm_title = title
        self.message = message
        self.confirm_id = confirm_id

    def compose(self):
        yield Vertical(
            Static(f"⚠️ {self.confirm_title}", classes="title"),
            Static(self.message, classes="subtitle"),
            Horizontal(
                Button("✅ Xác nhận", variant="success", id=f"confirm-{self.confirm_id}"),
                Button("❌ Hủy", variant="default", id="confirm-cancel"),
            ),
            id="confirm-content",
        )

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "confirm-cancel":
            self.app.pop_screen()
            self.dismiss(False)
        elif event.button.id and event.button.id.startswith("confirm-"):
            self.app.pop_screen()
            self.dismiss(True)


# ── MAIN MENU ───────────────────────────────────────────────────
class MainMenuScreen(Screen):
    def compose(self):
        yield Header(show_clock=True)
        yield VerticalScroll(
            Static("🚀 Shopee Dropship Pipeline", classes="title"),
            Static("Chọn chức năng:", classes="subtitle"),
            Vertical(
                Button("🔍 Crawl sản phẩm (build data)", variant="primary", id="crawl-broad"),
                Button("💡 Khám phá shop gợi ý", variant="primary", id="discover"),
                Button("🏪 Quản lý store", variant="primary", id="manage-stores"),
                Static("", id="discovery-summary"),
                Static("", classes="subtitle"),
                Static("💡 Mới bắt đầu? Bấm 'Crawl' → 'Khám phá' → tạo shop tự động", classes="info", id="help-text"),
                Static("Hoặc vào 'Quản lý store' để tạo/thêm shop có sẵn", classes="info"),
                id="menu-buttons",
            ),
            id="main-content",
        )
        yield Footer()

    def on_mount(self):
        pool = load_pool()
        pool_count = len(pool)
        stores = list_stores()
        summary = f"📊 Pool: {pool_count} sản phẩm | Store: {len(stores)} shop"
        self.query_one("#discovery-summary").update(summary)

    def on_button_pressed(self, event: Button.Pressed):
        btn_id = event.button.id or ""
        if btn_id == "crawl-broad":
            self.app.push_screen(BrowseCrawlScreen())
        elif btn_id == "discover":
            self.app.push_screen(DiscoveryScreen())
        elif btn_id == "manage-stores":
            self.app.push_screen(StoreListScreen())


# ── BROWSE CRAWL ────────────────────────────────────────────────
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

            # AliExpress
            ae = AliExpressScraper({"max_pages": 1, "delay_seconds": 1})
            try:
                products = await asyncio.get_event_loop().run_in_executor(
                    None, ae.crawl_by_keywords, [kw["en"]]
                )
                raw = []
                for p in products:
                    raw.append({
                        "id": f"ae_{p.id}",
                        "title_cn": p.title_cn or kw.get("cn", ""),
                        "title_en": kw["en"],
                        "price_cny": p.price_cny,
                        "image_urls": p.image_urls,
                        "detail_url": p.detail_url,
                        "platform": p.platform,
                        "source_keyword": kw["en"],
                    })
                added = add_to_pool(raw)
                total += len(raw)
                if added:
                    self.write_log(f"    ✅ +{added} sản phẩm (AE)")
            except Exception as exc:
                self.write_log(f"    ⚠️ AE lỗi: {exc}")
            finally:
                ae.close()

            # 1688
            c8 = Ali1688Scraper({"max_pages": 1, "delay_seconds": 1, "dropship_filter": True})
            try:
                products = await asyncio.get_event_loop().run_in_executor(
                    None, c8.crawl_by_keywords, [kw["cn"]]
                )
                raw = []
                for p in products:
                    raw.append({
                        "id": f"1688_{p.id}",
                        "title_cn": p.title_cn or kw.get("cn", ""),
                        "title_en": kw["en"],
                        "price_cny": p.price_cny,
                        "image_urls": p.image_urls,
                        "detail_url": p.detail_url,
                        "platform": p.platform,
                        "source_keyword": kw["cn"],
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


# ── DISCOVERY ───────────────────────────────────────────────────
class DiscoveryScreen(Screen):
    def compose(self):
        yield Header(show_clock=True)
        yield VerticalScroll(
            Static("💡 Khám phá shop gợi ý", classes="title"),
            Static("Hệ thống sẽ phân loại sản phẩm và gợi ý các shop phù hợp.", classes="subtitle"),
            Button("🔍 Phân tích theo danh mục", variant="primary", id="run-discovery"),
            Button("🔬 Phân cụm tự động (TF-IDF)", variant="warning", id="run-cluster"),
            Container(id="suggestions-list"),
            Button("← Quay lại", variant="default", id="back"),
            id="discovery-content",
        )
        yield Footer()

    def on_mount(self):
        pool = load_pool()
        if pool:
            self.query_one("#suggestions-list").mount(Static(f"📊 Pool hiện có: {len(pool)} sản phẩm"))

    @work
    async def do_discovery(self):
        container = self.query_one("#suggestions-list")
        container.remove_children()
        container.mount(Static("🔄 Đang phân tích theo danh mục..."))

        suggestions = await asyncio.get_event_loop().run_in_executor(None, discover_niches)

        container.remove_children()
        if not suggestions:
            container.mount(Static("⚠️ Chưa đủ sản phẩm để gợi ý shop. Hãy crawl thêm trước."))
            return

        container.mount(Static(f"🎯 Tìm thấy {len(suggestions)} cụm sản phẩm:\n"))
        existing_stores = set(list_stores())
        for s in suggestions:
            store_id = s["category"].lower().replace(" & ", "-").replace(" ", "-")
            already_exists = store_id in existing_stores
            card = SuggestionCard(s, already_exists)
            container.mount(card)

    @work
    async def do_cluster_discovery(self):
        container = self.query_one("#suggestions-list")
        container.remove_children()
        container.mount(Static("🔄 Đang phân cụm tự động bằng TF-IDF..."))

        from src.clustering import niche_suggestions_from_clusters

        suggestions = await asyncio.get_event_loop().run_in_executor(
            None, lambda: niche_suggestions_from_clusters()
        )

        container.remove_children()
        if not suggestions:
            container.mount(Static("⚠️ Không tìm thấy cụm sản phẩm nào. Cần crawl thêm dữ liệu."))
            return

        container.mount(Static(f"🔬 Phát hiện {len(suggestions)} cụm sản phẩm (TF-IDF):\n"))
        existing_stores = set(list_stores())
        for s in suggestions:
            store_id = s["category"].lower().replace(" & ", "-").replace(" ", "-")
            already_exists = store_id in existing_stores
            card = SuggestionCard(s, already_exists)
            container.mount(card)

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "back":
            self.app.pop_screen()
        elif event.button.id == "run-discovery":
            self.do_discovery()
        elif event.button.id == "run-cluster":
            self.do_cluster_discovery()
        elif event.button.id and event.button.id.startswith("create-shop-"):
            category = event.button.id.replace("create-shop-", "")
            # Find the suggestion data
            for child in self.query("#suggestions-list").children():
                if isinstance(child, SuggestionCard) and child.suggestion["category"] == category:
                    suggestion = child.suggestion
                    break
            else:
                self.query_one("#suggestions-list").mount(Static("⚠️ Không tìm thấy dữ liệu cụm này"))
                return
            store_id = category.lower().replace(" & ", "-").replace(" ", "-")
            config = create_shop_from_suggestion(suggestion)
            config["id"] = store_id
            save_store(store_id, config)
            self.query_one("#suggestions-list").mount(
                Static(f"✅ Đã tạo store '{store_id}'! Vào 'Quản lý store' để xem.")
            )
            self.query_one("#run-discovery").focus()


class SuggestionCard(Static):
    def __init__(self, suggestion: dict, already_exists: bool = False):
        super().__init__()
        self.suggestion = suggestion
        self.already_exists = already_exists

    def compose(self):
        s = self.suggestion
        kw = ", ".join(s.get("top_keywords", []))
        yield Static(
            f"{s['icon']} {s['category']}\n"
            f"  📦 {s['product_count']} sản phẩm"
            f"  |  💰 TB: {s['avg_price_cny']:.0f}¥"
            f"  |  📝 Từ khóa: {kw}",
            classes="suggestion-info",
        )
        btn_id = f"create-shop-{s['category']}"
        if self.already_exists:
            yield Button("✅ Đã tồn tại", variant="default", id=btn_id, disabled=True)
        else:
            yield Button("➕ Tạo shop từ cụm này", variant="success", id=btn_id)


# ── STORE LIST ──────────────────────────────────────────────────
class StoreListScreen(Screen):
    def compose(self):
        yield Header(show_clock=True)
        yield VerticalScroll(
            Static("🏪 Quản lý store", classes="title"),
            Static("Các shop đang có:", classes="subtitle"),
            Container(id="store-list"),
            Button("+ Thêm store mới", variant="success", id="add-store"),
            Button("← Quay lại", variant="default", id="back"),
            id="main-content",
        )
        yield Footer()

    def on_mount(self):
        self.refresh_stores()

    def refresh_stores(self):
        container = self.query_one("#store-list")
        container.remove_children()
        for sid in list_stores():
            data = load_store(sid)
            if data:
                container.mount(StoreCard(sid, data.get("name", sid)))
        if not list_stores():
            container.mount(Static("(Chưa có store nào)"))

    def on_button_pressed(self, event: Button.Pressed):
        btn_id = event.button.id or ""
        if btn_id == "back":
            self.app.pop_screen()
        elif btn_id == "add-store":
            self.app.push_screen(StoreFormScreen())
        elif btn_id.startswith("crawl-"):
            sid = btn_id.replace("crawl-", "")
            self.app.push_screen(StoreDetailScreen(sid, run_crawl=True))
        elif btn_id.startswith("detail-"):
            sid = btn_id.replace("detail-", "")
            self.app.push_screen(StoreDetailScreen(sid))
        elif btn_id.startswith("edit-"):
            sid = btn_id.replace("edit-", "")
            self.app.push_screen(StoreEditScreen(sid))


class StoreCard(Static):
    def __init__(self, store_id: str, name: str, **kwargs):
        super().__init__(**kwargs)
        self.store_id = store_id
        self.store_name = name

    def compose(self):
        yield Horizontal(
            Static(f"  {self.store_name}", classes="store-name"),
            Button("Chạy crawl", variant="primary", id=f"crawl-{self.store_id}"),
            Button("Chi tiết", variant="default", id=f"detail-{self.store_id}"),
            Button("Sửa config", variant="default", id=f"edit-{self.store_id}"),
            classes="store-card",
        )


class StoreFormScreen(Screen):
    def compose(self):
        yield Header(show_clock=True)
        yield VerticalScroll(
            Static("➕ Thêm store mới", classes="title"),
            Label("Tên store (VD: Đồ leo núi)"),
            Input(placeholder="Nhập tên store...", id="input-name"),
            Label("ID (VD: leo-nui)"),
            Input(placeholder="Để trống auto-sinh từ tên", id="input-id"),
            Horizontal(
                Button("💾 Lưu", variant="success", id="save"),
                Button("Hủy", variant="default", id="cancel"),
            ),
            id="form-content",
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "cancel":
            self.app.pop_screen()
        elif event.button.id == "save":
            name = self.query_one("#input-name").value.strip()
            if not name:
                return
            store_id = self.query_one("#input-id").value.strip()
            if not store_id:
                store_id = name.lower().replace(" ", "-").replace("\u0111", "d")
            create_store(store_id, name)
            self.app.pop_screen()
            self.app.push_screen(StoreEditScreen(store_id))


# ── STORE EDIT ──────────────────────────────────────────────────
class StoreEditScreen(Screen):
    def __init__(self, store_id: str):
        super().__init__()
        self.store_id = store_id

    def compose(self):
        data = load_store(self.store_id) or {}
        niche = data.get("niche", {})
        shopee = data.get("shopee", {})
        sources = data.get("sources", {})

        yield Header(show_clock=True)
        yield VerticalScroll(
            Static(f"⚙️ Cấu hình: {data.get('name', store_id)}", classes="title"),
            Static("Từ khóa tìm kiếm", classes="section-title"),
            Label("Từ khóa tiếng Trung (1688) — nhập cách nhau bằng dấu phẩy"),
            Input(value=", ".join(niche.get("keywords_cn", [])), placeholder="VD: 登山鞋, 登山杖", id="edit-kw-cn"),
            Label("Từ khóa tiếng Anh (AliExpress) — nhập cách nhau bằng dấu phẩy"),
            Input(value=", ".join(niche.get("keywords_en", [])), placeholder="VD: hiking shoes, trekking pole", id="edit-kw-en"),
            Label("Từ khóa tiếng Việt (Shopee) — nhập cách nhau bằng dấu phẩy"),
            Input(value=", ".join(niche.get("keywords_vn", [])), placeholder="VD: giày leo núi, gậy trekking", id="edit-kw-vn"),
            Label("Shopee Category ID"),
            Input(value=str(niche.get("category_shopee_id", 0)), placeholder="VD: 12345", id="edit-cat-id"),
            Static("", classes="section-title"),
            Static("Shopee API Credentials", classes="section-title"),
            Label("Partner ID"),
            Input(value=str(shopee.get("partner_id", "")), placeholder="VD: 123456", id="edit-partner-id"),
            Label("Partner Key"),
            Input(value=str(shopee.get("partner_key", "")), placeholder="VD: abc123...", id="edit-partner-key", password=True),
            Label("Shop ID"),
            Input(value=str(shopee.get("shop_id", "")), placeholder="VD: 789012", id="edit-shop-id"),
            Label("Access Token"),
            Input(value=str(shopee.get("access_token", "")), placeholder="Token từ Shopee", id="edit-access-token", password=True),
            Label("Refresh Token"),
            Input(value=str(shopee.get("refresh_token", "")), placeholder="Refresh token", id="edit-refresh-token", password=True),
            Label("Môi trường"),
            Input(value=str(shopee.get("environment", "uat")), placeholder="uat hoặc prod", id="edit-env"),
            Static("", classes="section-title"),
            Static("Nguồn hàng", classes="section-title"),
            Horizontal(
                Button(
                    "✅ 1688 BẬT" if sources.get("1688", {}).get("enabled") else "❌ 1688 TẮT",
                    variant="primary" if sources.get("1688", {}).get("enabled") else "default",
                    id="toggle-1688",
                ),
                Button(
                    "✅ AliExpress BẬT" if sources.get("aliexpress", {}).get("enabled") else "❌ AliExpress TẮT",
                    variant="primary" if sources.get("aliexpress", {}).get("enabled") else "default",
                    id="toggle-ae",
                ),
            ),
            Horizontal(
                Button("💾 Lưu", variant="success", id="edit-save"),
                Button("Hủy", variant="default", id="edit-cancel"),
            ),
            id="edit-content",
        )
        yield Footer()

    def _toggle_source(self, source_key: str):
        data = load_store(self.store_id) or {}
        sources = data.setdefault("sources", {})
        src = sources.setdefault(source_key, {"enabled": True})
        src["enabled"] = not src.get("enabled", True)
        save_store(self.store_id, data)
        # Rebuild screen
        self.app.pop_screen()
        self.app.push_screen(StoreEditScreen(self.store_id))

    def on_button_pressed(self, event: Button.Pressed):
        btn_id = event.button.id or ""
        if btn_id in ("edit-cancel",):
            self.app.pop_screen()
        elif btn_id == "toggle-1688":
            self._toggle_source("1688")
        elif btn_id == "toggle-ae":
            self._toggle_source("aliexpress")
        elif btn_id == "edit-save":
            data = load_store(self.store_id) or {}
            # Read inputs
            kw_cn = [w.strip() for w in self.query_one("#edit-kw-cn").value.split(",") if w.strip()]
            kw_en = [w.strip() for w in self.query_one("#edit-kw-en").value.split(",") if w.strip()]
            kw_vn = [w.strip() for w in self.query_one("#edit-kw-vn").value.split(",") if w.strip()]
            cat_id = self.query_one("#edit-cat-id").value.strip()
            partner_id = self.query_one("#edit-partner-id").value.strip()
            partner_key = self.query_one("#edit-partner-key").value.strip()
            shop_id = self.query_one("#edit-shop-id").value.strip()
            access_token = self.query_one("#edit-access-token").value.strip()
            refresh_token = self.query_one("#edit-refresh-token").value.strip()
            env = self.query_one("#edit-env").value.strip() or "uat"

            data["niche"]["keywords_cn"] = kw_cn
            data["niche"]["keywords_en"] = kw_en
            data["niche"]["keywords_vn"] = kw_vn
            try:
                data["niche"]["category_shopee_id"] = int(cat_id) if cat_id else 0
            except ValueError:
                pass
            shopee = data.setdefault("shopee", {})
            shopee["partner_id"] = partner_id
            shopee["partner_key"] = partner_key
            shopee["shop_id"] = shop_id
            shopee["access_token"] = access_token
            shopee["refresh_token"] = refresh_token
            shopee["environment"] = env

            save_store(self.store_id, data)
            self.app.pop_screen()


# ── STORE DETAIL ────────────────────────────────────────────────
class StoreDetailScreen(Screen):
    def __init__(self, store_id: str, run_crawl: bool = False):
        super().__init__()
        self.store_id = store_id
        self.should_run_crawl = run_crawl

    @property
    def _data_dir(self) -> Path:
        return Path("data") / self.store_id

    @property
    def _store_cfg(self) -> dict:
        return load_store(self.store_id) or {}

    def compose(self):
        data = self._store_cfg
        name = data.get("name", self.store_id)
        yield Header(show_clock=True)
        yield VerticalScroll(
            Static(f"📋 {name}", classes="title"),
            Static("", id="store-info"),
            Vertical(
                Button("1️⃣ Crawl sản phẩm", variant="primary", id="run-crawl"),
                Button("2️⃣ Xử lý ảnh", variant="primary", id="run-images", disabled=True),
                Button("🎬 Xử lý video", variant="primary", id="run-video", disabled=True),
                Button("3️⃣ Tạo caption", variant="primary", id="run-caption", disabled=True),
                Button("📊 Cập nhật giá", variant="warning", id="run-pricing", disabled=True),
                Button("4️⃣ Đăng Shopee", variant="primary", id="run-publish", disabled=True),
                Static("", classes="section-title"),
                Static("📦 Hậu mãi & Vận hành", classes="section-title"),
                Button("🔄 Đồng bộ đơn hàng", variant="warning", id="run-orders", disabled=True),
                Button("⚡ Flash Sale", variant="warning", id="run-flashsale", disabled=True),
                Button("💰 Dòng tiền", variant="warning", id="run-cashflow", disabled=True),
                Button("📈 Trend Hijack", variant="warning", id="run-trends", disabled=True),
                Button("🏭 Virtual Hub", variant="warning", id="run-virtualhub", disabled=True),
                Button("💬 Auto Care", variant="warning", id="run-customercare", disabled=True),
                Button("▶️ Chạy toàn bộ", variant="success", id="run-all", disabled=True),
                id="pipeline-buttons",
            ),
            Static("📝 Nhật ký:", classes="section-title"),
            Log(id="log"),
            Static("", classes="section-title"),
            Static("🛠 Công cụ", classes="section-title"),
            Button("🍪 Xuất cookies 1688", variant="default", id="export-cookies"),
            Button("🔌 Kiểm tra Shopee API", variant="default", id="check-shopee"),
            Button("← Quay lại", variant="default", id="back"),
            id="detail-content",
        )
        yield Footer()

    def on_mount(self):
        self.refresh_info()
        self.refresh_buttons()
        if self.should_run_crawl:
            self.run_crawl()

    def refresh_info(self):
        data = self._store_cfg
        if not data:
            return
        niche = data.get("niche", {})
        sources = data.get("sources", {})
        kw_cn = ", ".join(niche.get("keywords_cn", [])[:5])
        kw_en = ", ".join(niche.get("keywords_en", [])[:5])
        ae = "\u2705" if sources.get("aliexpress", {}).get("enabled") else "\u274c"
        c8 = "\u2705" if sources.get("1688", {}).get("enabled") else "\u274c"
        self.query_one("#store-info").update(
            f"T\u1eeb kh\xf3a CN: {kw_cn}\nT\u1eeb kh\xf3a EN: {kw_en}\nAE: {ae} | 1688: {c8}"
        )

    def refresh_buttons(self):
        """Enable pipeline buttons based on available data."""
        products_file = self._data_dir / "products.json"
        products_with_images = self._data_dir / "products_with_images.json"
        captions_file = self._data_dir / "captions.json"
        published_file = self._data_dir / "published.json"
        fulfillment_file = Path("data") / "orders_to_fulfill.json"

        has_products = products_file.exists()
        has_images = False
        if products_with_images.exists():
            try:
                with open(products_with_images, encoding="utf-8") as f:
                    data = json.load(f)
                has_images = any(p.get("images_processed") for p in data)
            except (json.JSONDecodeError, OSError):
                pass
        has_captions = captions_file.exists()
        has_published = published_file.exists()
        has_fulfillment = fulfillment_file.exists()

        self.query_one("#run-images").disabled = not has_products
        self.query_one("#run-video").disabled = not has_images
        self.query_one("#run-caption").disabled = not has_images
        self.query_one("#run-pricing").disabled = not has_captions
        self.query_one("#run-publish").disabled = not has_captions
        self.query_one("#run-orders").disabled = not has_published
        self.query_one("#run-flashsale").disabled = not has_published
        self.query_one("#run-cashflow").disabled = not has_fulfillment
        self.query_one("#run-trends").disabled = False
        self.query_one("#run-virtualhub").disabled = not has_fulfillment
        self.query_one("#run-customercare").disabled = not has_fulfillment
        self.query_one("#run-all").disabled = not has_products

    def write_log(self, msg: str):
        self.query_one("#log").write_line(f"[{time.strftime('%H:%M:%S')}] {msg}")

    def _load_products(self) -> list[dict]:
        path = self._data_dir / "products.json"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save_json(self, name: str, data: list):
        path = self._data_dir / name
        self._data_dir.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @work
    async def run_crawl(self):
        self.write_log("Crawl s\u1ea3n ph\u1ea9m...")
        data = self._store_cfg
        if not data:
            return
        all_products = []
        ae_cfg = data.get("sources", {}).get("aliexpress", {})
        if ae_cfg.get("enabled"):
            self.write_log("  AliExpress...")
            scraper = AliExpressScraper(ae_cfg)
            try:
                products = await asyncio.get_event_loop().run_in_executor(
                    None, scraper.crawl_by_keywords, data.get("niche", {}).get("keywords_en", [])
                )
                all_products.extend(products)
                self.write_log(f"  +{len(products)} s\u1ea3n ph\u1ea9m AE")
            finally:
                scraper.close()
        c8_cfg = data.get("sources", {}).get("1688", {})
        if c8_cfg.get("enabled"):
            self.write_log("  1688...")
            scraper = Ali1688Scraper(c8_cfg)
            scraper._store_config = data  # for supplier scoring
            try:
                products = await asyncio.get_event_loop().run_in_executor(
                    None, scraper.crawl_by_keywords, data.get("niche", {}).get("keywords_cn", [])
                )
                all_products.extend(products)
                self.write_log(f"  +{len(products)} s\u1ea3n ph\u1ea9m 1688")
            finally:
                scraper.close()
        if all_products:
            out = []
            for p in all_products:
                out.append({
                    "id": p.id, "title_cn": p.title_cn, "price_cny": p.price_cny,
                    "image_urls": p.image_urls, "detail_url": p.detail_url,
                    "platform": p.platform, "is_dropship": p.is_dropship,
                    "description_cn": p.description_cn[:500] if p.description_cn else "",
                    "supplier_name": p.supplier_name,
                    "sales_count": p.sales_count,
                })
            self._save_json("products.json", out)
            self.write_log(f"Xong! {len(out)} sp -> data/{self.store_id}/products.json")
        else:
            self.write_log("Kh\u00f4ng crawl \u0111\u01b0\u1ee3c sp n\u00e0o")
        self.refresh_buttons()

    @work
    async def run_images(self):
        self.write_log("X\u1eed l\u00fd \u1ea3nh...")
        products = self._load_products()
        if not products:
            self.write_log("Kh\u00f4ng c\u00f3 s\u1ea3n ph\u1ea9m \u0111\u1ec3 x\u1eed l\u00fd \u1ea3nh")
            return

        processor = ImageProcessor(self._store_cfg)
        raw_dir = str(self._data_dir / "images" / "raw")
        proc_dir = str(self._data_dir / "images" / "processed")

        total_ok = 0
        for i, prod in enumerate(products, 1):
            pid = prod.get("id", f"p{i}")
            urls = prod.get("image_urls", [])
            if not urls:
                self.write_log(f"  [{i}/{len(products)}] {pid}: Kh\u00f4ng c\u00f3 URL \u1ea3nh")
                continue

            saved = await processor.download_images(urls, raw_dir, pid)
            if saved:
                out_dir = f"{proc_dir}/{pid}"
                results = processor.process_batch(saved, out_dir)
                prod["images_local"] = saved
                prod["images_processed"] = results
                prod["image_count"] = len(results)
                total_ok += 1
                self.write_log(f"  [{i}/{len(products)}] {pid}: {len(results)} \u1ea3nh")
            else:
                self.write_log(f"  [{i}/{len(products)}] {pid}: T\u1ea3i \u1ea3nh th\u1ea5t b\u1ea1i")

        self._save_json("products_with_images.json", products)
        self.write_log(f"Xong! {total_ok}/{len(products)} sp c\u00f3 \u1ea3nh")
        self.refresh_buttons()

    @work
    async def run_video(self):
        self.write_log("Xử lý video...")
        # Check BGM availability
        bgm_dir = Path("assets/background_music")
        mp3s = list(bgm_dir.glob("*.mp3")) if bgm_dir.exists() else []
        if not mp3s:
            self.write_log("  ⚠️ Không tìm thấy file .mp3 trong assets/background_music/")
            self.write_log("  Video sẽ xuất ở chế độ không âm thanh (muted)")
        products_path = self._data_dir / "products_with_images.json"
        if not products_path.exists():
            self.write_log("Không có sản phẩm để xử lý video")
            return

        with open(products_path, encoding="utf-8") as f:
            products = json.load(f)

        processor = VideoProcessor(self._store_cfg)
        raw_dir = str(self._data_dir / "videos" / "raw")
        proc_dir = str(self._data_dir / "videos" / "processed")

        # Step 1: parallel download
        dl_items = []
        prod_index = {}
        for i, prod in enumerate(products, 1):
            url = prod.get("video_url", "") or prod.get("video", "")
            pid = prod.get("id", f"p{i}")
            if not url:
                continue
            dl_items.append((url, pid))
            prod_index[pid] = (i, prod)

        if dl_items:
            self.write_log(f"  Tải {len(dl_items)} video song song...")
            results = await processor.download_videos(dl_items, raw_dir)
            dl_map = {pid: path for pid, path in results}
            for pid, (i, prod) in prod_index.items():
                path = dl_map.get(pid)
                if path:
                    self.write_log(f"  [{i}/{len(products)}] {pid}: đã tải")
                else:
                    self.write_log(f"  [{i}/{len(products)}] {pid}: tải thất bại")
        else:
            dl_map = {}

        # Step 2: parallel processing via ThreadPoolExecutor
        ok = fail = 0
        to_process = [(pid, dl_map[pid]) for pid in sorted(dl_map) if dl_map[pid]]
        if to_process:
            self.write_log(f"  Xử lý {len(to_process)} video song song...")
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor(max_workers=3) as pool:
                futs = {}
                for pid, rpath in to_process:
                    fut = loop.run_in_executor(pool, processor.process_single, rpath, proc_dir)
                    futs[fut] = pid
                for fut in asyncio.as_completed(futs):
                    pid = futs[fut]
                    try:
                        processed = await fut
                    except Exception:
                        processed = None
                    i, prod = prod_index[pid]
                    prod["video_processed"] = processed
                    if processed:
                        ok += 1
                        self.write_log(f"  [{i}/{len(products)}] {pid}: OK")
                    else:
                        fail += 1
                        self.write_log(f"  [{i}/{len(products)}] {pid}: FAIL (muted)")

        # Count products without URL
        no_url = sum(1 for p in products if not (p.get("video_url") or p.get("video")))
        fail += no_url

        self._save_json("products_with_images.json", products)
        self.write_log(f"Xong! {ok} ok, {fail} fail ({no_url} không có URL)")
        self.refresh_buttons()

    @work
    async def run_caption(self):
        self.write_log("T\u1ea1o caption...")
        products_path = self._data_dir / "products_with_images.json"
        if not products_path.exists():
            products_path = self._data_dir / "products.json"
        if not products_path.exists():
            self.write_log("Kh\u00f4ng c\u00f3 s\u1ea3n ph\u1ea9m \u0111\u1ec3 t\u1ea1o caption")
            return

        with open(products_path, encoding="utf-8") as f:
            products = json.load(f)

        gen = CaptionGenerator(self._store_cfg)
        niche = self._store_cfg.get("niche", {})
        niche_name = niche.get("keywords_vn", [self.store_id])[0]
        multiplier = niche.get("price_multiplier", 2.5)

        captions = []
        for i, prod in enumerate(products, 1):
            price_cny = prod.get("price_cny", 0)
            price_vnd = await async_calculate_final_price(price_cny, multiplier)
            title_cn = prod.get("title_cn", "")

            caption = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda t=title_cn, n=niche_name, p=price_cny, d=prod.get("description_cn", ""), v=price_vnd:
                    gen.generate(t, n, p, d, v),
            )

            # A/B title scoring
            from src.seo.title_scorer import generate_and_score
            seo_result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda t=caption.get("title_vi", ""), c=niche_name,
                       f=prod.get("description_cn", ""), kw=niche.get("keywords_vn", []):
                    generate_and_score(t, c, f, kw),
            )
            caption["title_vi"] = seo_result["title_vi"]
            caption["title_variants"] = seo_result["all_titles"]
            caption["best_title_style"] = seo_result["best_style"]
            caption["best_title_score"] = seo_result["best_score"]

            entry = {
                "product_id": prod.get("id"),
                "price_cny": price_cny,
                "price_vnd": int(price_vnd),
                "images_processed": prod.get("images_processed", []),
                "image_ids": [],
                **caption,
            }
            captions.append(entry)
            self.write_log(
                f"  [{i}/{len(products)}] {prod.get('id')}: "
                f"{caption.get('title_vi', '')[:50]}... "
                f"(score={seo_result['best_score']:.3f}, {seo_result['best_style']})"
            )

        self._save_json("captions.json", captions)
        self.write_log(f"Xong! {len(captions)} caption -> data/{self.store_id}/captions.json")
        self.refresh_buttons()

    @work
    async def run_pricing(self):
        self.write_log("📊 Đang cập nhật giá cạnh tranh...")
        cap_path = self._data_dir / "captions.json"
        if not cap_path.exists():
            self.write_log("Chưa có caption. Chạy bước 3 trước.")
            return

        try:
            from src.pricing.competitor import async_analyze_store_pricing
            summary = await async_analyze_store_pricing(self.store_id)
            profitable = summary["profitable"]
            unprofitable = summary["unprofitable"]
            total = summary["total"]
            self.write_log(f"✅ {profitable}/{total} sản phẩm có lợi nhuận")
            if unprofitable > 0:
                self.write_log(f"⏭️ {unprofitable} sản phẩm sẽ bị tạm ẩn (không đủ lợi nhuận):")
                for pid in summary["skipped_products"]:
                    self.write_log(f"   - {pid}")
            self.write_log(f"📄 Báo cáo lưu tại: {summary['report_path']}")
        except FileNotFoundError as e:
            self.write_log(f"❌ {e}")
        except Exception as e:
            self.write_log(f"❌ Lỗi phân tích giá: {e}")
        self.refresh_buttons()

    @work
    async def run_publish(self):
        self.write_log("\u0110\u0103ng Shopee...")
        cap_path = self._data_dir / "captions.json"
        if not cap_path.exists():
            self.write_log("Ch\u01b0a c\u00f3 caption. Ch\u1ea1y b\u01b0\u1edbc 3 tr\u01b0\u1edbc.")
            return

        with open(cap_path, encoding="utf-8") as f:
            captions = json.load(f)

        store_cfg = self._store_cfg
        shopee_cfg = store_cfg.get("shopee", {})
        if not shopee_cfg.get("partner_id") or not shopee_cfg.get("partner_key"):
            self.write_log(
                "⚠️ Shopee ch\u01b0a \u0111\u01b0\u1ee3c c\u1ea5u h\u00ecnh. "
                "V\u00e0o Store List -> Chi ti\u1ebft -> s\u1eeda th\u00f4ng tin Shopee."
            )
            return

        # Run variant manager to detect split/merge needs
        products_path = self._data_dir / "products_with_images.json"
        variant_tier_map: dict[str, dict] = {}
        if products_path.exists():
            try:
                from src.processing.variant_manager import VariantManager
                from dataclasses import asdict
                with open(products_path, encoding="utf-8") as f:
                    raw_products = json.load(f)
                vm = VariantManager(store_cfg, self.store_id)
                processed = await asyncio.get_event_loop().run_in_executor(
                    None, vm.process_products, raw_products, self.store_id
                )
                # Build map: product_id -> tier_variations from variant groups
                groups_path = self._data_dir / "variant_groups.json"
                if groups_path.exists():
                    with open(groups_path, encoding="utf-8") as gf:
                        groups = json.load(gf)
                    for g in groups:
                        parent_id = g.get("parent_source_id", "")
                        if g.get("products"):
                            options = []
                            variations = []
                            for idx, prod in enumerate(g["products"]):
                                label = prod.get("variation_label", f"Option {idx}")
                                sku = prod.get("variation_sku", f"sku_{idx}")
                                price = prod.get("price_vnd") or prod["source"].get("price_cny", 0) * 3500 * 2.5
                                if label not in options:
                                    options.append(label)
                                variations.append({
                                    "tier_index": [options.index(label)],
                                    "variation_sku": sku,
                                    "variation_stock": 999,
                                    "variation_price": int(price),
                                })
                            variant_tier_map[parent_id] = {
                                "tier_variation": [{"name": "Phân loại", "option_list": options}],
                                "variation": variations,
                            }
                self.write_log(f"  🔀 Variant: {len(variant_tier_map)} groups detected")
            except Exception as e:
                self.write_log(f"  ⚠️ Variant manager skipped: {e}")

        client = ShopeeClient(store_cfg)
        niche_name = store_cfg.get("niche", {}).get("keywords_vn", [self.store_id])[0]

        # Load pricing report (if any)
        pricing_report_path = self._data_dir / "pricing_report.json"
        pricing_map = {}
        if pricing_report_path.exists():
            try:
                with open(pricing_report_path, encoding="utf-8") as pf:
                    for entry in json.load(pf):
                        pricing_map[entry.get("product_id")] = entry
            except Exception:
                pass

        results = []
        try:
            for i, cap in enumerate(captions, 1):
                self.write_log(f"  [{i}/{len(captions)}] \u0110ang x\u1eed l\u00fd {cap.get('product_id')}...")

                # Check pricing report for profitability
                price_vnd = cap.get("price_vnd", 0)
                pid_check = cap.get("product_id", "")
                if pid_check in pricing_map:
                    p_entry = pricing_map[pid_check]
                    if not p_entry.get("profitable", True):
                        self.write_log(f"    ⏭️ {pid_check}: không lợi nhuận, bỏ qua")
                        results.append({**cap, "shopee_status": "unprofitable",
                                        "shopee_error": "price_too_low"})
                        continue
                    price_vnd = p_entry.get("final_price_vnd", price_vnd)

                # Upload images
                image_ids = []
                for img_path in cap.get("images_processed", [])[:9]:
                    if Path(img_path).exists():
                        iid = await asyncio.get_event_loop().run_in_executor(None, client.upload_image, img_path)
                        if iid:
                            image_ids.append(iid)

                if not image_ids:
                    self.write_log(f"    ⚠️ Không upload được ảnh, bỏ qua")
                    results.append({**cap, "shopee_status": "no_images", "shopee_error": ""})
                    continue

                # Create Shopee item
                from src.models.product import ProductSource, ProductProcessed
                src = ProductSource(
                    id=cap.get("product_id", ""),
                    title_cn=cap.get("title_cn", ""),
                    price_cny=cap.get("price_cny", 0),
                    original_price_cny=cap.get("price_cny", 0),
                    image_urls=[],
                    description_cn="",
                    category_name_cn=niche_name,
                )
                pp = ProductProcessed(
                    source=src,
                    images_processed=image_ids,
                    title_vi=cap.get("title_vi", ""),
                    description_vi=cap.get("description", ""),
                    bullet_points=cap.get("bullet_points", []),
                    hashtags=cap.get("hashtags", []),
                    price_vnd=price_vnd,
                )
                sp = ShopeeProduct(
                    product=pp,
                    image_ids=image_ids,
                    category_id=store_cfg.get("niche", {}).get("category_shopee_id", 0),
                    logistic_id=shopee_cfg.get("default_logistic_id", 80001),
                    tier_variations=variant_tier_map.get(pid_check, {}),
                )

                item_id = client.add_item(sp)
                if item_id:
                    self.write_log(f"    ✅ Item: {item_id}")
                    results.append({**cap, "shopee_status": "created", "shopee_item_id": item_id})
                else:
                    self.write_log(f"    ❌ T\u1ea1o item th\u1ea5t b\u1ea1i")
                    results.append({**cap, "shopee_status": "failed", "shopee_error": "create_item_failed"})

            self._save_json("published.json", results)
            success = sum(1 for r in results if r.get("shopee_status") == "created")
            self.write_log(f"Xong! {success}/{len(results)} s\u1ea3n ph\u1ea9m \u0111\u00e3 \u0111\u0103ng")
        finally:
            client.close()

    @work
    async def run_orders(self):
        self.write_log("🔄 Đồng bộ đơn hàng Shopee...")
        store_cfg = self._store_cfg
        try:
            mgr = OrderManager(store_cfg, self.store_id)
            count = await asyncio.get_event_loop().run_in_executor(None, mgr.sync)
            self.write_log(f"  {count} đơn hàng mới -> data/orders_to_fulfill.json")
            mgr.close()
        except Exception as e:
            self.write_log(f"❌ Lỗi đồng bộ đơn: {e}")
        self.refresh_buttons()

    @work
    async def run_flashsale(self):
        self.write_log("⚡ Đăng ký Flash Sale...")
        store_cfg = self._store_cfg
        shopee_cfg = store_cfg.get("shopee", {})
        if not shopee_cfg.get("partner_id") or not shopee_cfg.get("partner_key"):
            self.write_log("⚠️ Shopee chưa được cấu hình. Bỏ qua Flash Sale.")
            return
        try:
            mgr = FlashSaleManager(store_cfg, self.store_id)
            report_path = self._data_dir / "pricing_report.json"
            pricing = []
            if report_path.exists():
                with open(report_path, encoding="utf-8") as f:
                    pricing = json.load(f)
            results = await asyncio.get_event_loop().run_in_executor(
                None, lambda: mgr.run(max_items=20)
            )
            self.write_log(f"  ✅ Đã đăng ký {len(results)} đợt Flash Sale")
            mgr.close()
        except Exception as e:
            self.write_log(f"❌ Lỗi Flash Sale: {e}")

    @work
    async def run_cashflow(self):
        self.write_log("💰 Phân tích dòng tiền...")
        try:
            planner = CashFlowPlanner(self._store_cfg, self.store_id)
            report = await asyncio.get_event_loop().run_in_executor(None, planner.run)
            summary = report.get("summary", {})
            forecast = report.get("forecast", {})
            self.write_log(
                f"  Đơn chờ: {summary.get('pending_orders', 0)} | "
                f"Chi phí: {summary.get('total_pending_cost_vnd', 0):,.0f} VND"
            )
            self.write_log(
                f"  Doanh thu: {summary.get('total_receivable_vnd', 0):,.0f} VND | "
                f"Lãi: {summary.get('estimated_profit_vnd', 0):,.0f} VND"
            )
            peak = forecast.get("peak_capital_needed_vnd", 0)
            if peak:
                self.write_log(f"  📊 Vốn đỉnh: {peak:,.0f} VND vào {forecast.get('peak_capital_day')}")
            if report.get("warning"):
                self.write_log(f"  ⚠️ {report['warning']}")
        except Exception as e:
            self.write_log(f"❌ Lỗi phân tích dòng tiền: {e}")

    @work
    async def run_trends(self):
        self.write_log("📈 Quét xu hướng thị trường...")
        try:
            detector = TrendDetector(self._store_cfg)
            spikes = await asyncio.get_event_loop().run_in_executor(
                None, detector.scan_and_trigger
            )
            if spikes:
                self.write_log(f"  📈 Phát hiện {len(spikes)} từ khóa nóng:")
                for s in spikes[:5]:
                    self.write_log(f"    - {s['keyword']} ({s['ratio']}x spike)")
            else:
                self.write_log("  ✅ Không phát hiện spike mới")
            detector.close()
        except Exception as e:
            self.write_log(f"❌ Lỗi quét xu hướng: {e}")

    @work
    async def run_virtualhub(self):
        self.write_log("🏭 Virtual Hub: Mapping tracking...")
        try:
            hub = VirtualHub(self._store_cfg, self.store_id)
            # Auto-map pending tracking numbers to Shopee orders
            mapped = await asyncio.get_event_loop().run_in_executor(
                None, hub.auto_map_tracking
            )
            status = await asyncio.get_event_loop().run_in_executor(
                None, hub.status_summary
            )
            self.write_log(
                f"  Tổng: {status['total']} | "
                f"Đã map: {status['mapped']} | "
                f"Chờ: {status['pending']}"
            )
            if mapped:
                self.write_log(f"  ✅ Tự động map {mapped} tracking mới")
                manifest = await asyncio.get_event_loop().run_in_executor(
                    None, hub.generate_manifest
                )
                if manifest:
                    self.write_log(f"  📋 Manifest: {len(manifest)} mục (data/{self.store_id}/relabel_manifest_*.json)")
        except Exception as e:
            self.write_log(f"❌ Lỗi Virtual Hub: {e}")

    @work
    async def run_customercare(self):
        self.write_log("💬 Gửi tin nhắn chăm sóc khách hàng...")
        store_cfg = self._store_cfg
        shopee_cfg = store_cfg.get("shopee", {})
        if not shopee_cfg.get("partner_id") or not shopee_cfg.get("partner_key"):
            self.write_log("⚠️ Shopee chưa được cấu hình. Bỏ qua Auto Care.")
            return
        try:
            bot = CustomerCareBot(store_cfg, self.store_id)
            result = await asyncio.get_event_loop().run_in_executor(
                None, bot.process_fulfillment_orders, store_cfg
            )
            self.write_log(f"  {result.get('sent', 0)} tin đã gửi, {result.get('skipped', 0)} bỏ qua")
        except Exception as e:
            self.write_log(f"❌ Lỗi Auto Care: {e}")

    def do_export_cookies(self):
        self.write_log("🍪 Xuất cookies 1688 từ Chrome...")
        try:
            from src.source.ali1688 import extract_chrome_cookies
            cookies = extract_chrome_cookies()
            if cookies:
                self.write_log(f"  ✅ Đã xuất {len(cookies)} cookies (domain: 1688.com)")
                import json
                cookie_path = Path("config") / "1688_cookies.json"
                with open(cookie_path, "w", encoding="utf-8") as f:
                    json.dump(cookies, f, ensure_ascii=False, indent=2)
                self.write_log(f"  💾 Đã lưu vào {cookie_path}")
            else:
                self.write_log("  ⚠️ Không tìm thấy cookies 1688 trong Chrome.")
                self.write_log("  Hãy đăng nhập 1688.com trong Chrome trước, hoặc dùng scripts/export_cookies.py")
        except Exception as e:
            self.write_log(f"  ❌ Lỗi: {e}")

    def do_check_shopee(self):
        self.write_log("🔌 Kiểm tra kết nối Shopee API...")
        store_cfg = self._store_cfg
        shopee_cfg = store_cfg.get("shopee", {})
        pid = shopee_cfg.get("partner_id", "")
        key = shopee_cfg.get("partner_key", "")
        token = shopee_cfg.get("access_token", "")
        shop_id = shopee_cfg.get("shop_id", "")
        if not pid or not key:
            self.write_log("  ⚠️ Partner ID hoặc Partner Key chưa được cấu hình.")
            self.write_log("  Vào Sửa config để nhập thông tin Shopee.")
            return
        self.write_log(f"  Partner ID: {pid}")
        self.write_log(f"  Shop ID: {shop_id or '(trống)'}")
        self.write_log(f"  Access Token: {'...' + token[-8:] if len(token) > 8 else '(trống)'}")
        try:
            client = ShopeeClient(store_cfg)
            result = client._request("GET", "/api/v2/shop/get_shop_info", {})
            if result.get("error") is None or result.get("error") == 0:
                shop_name = result.get("response", {}).get("shop_name", "unknown")
                self.write_log(f"  ✅ Kết nối thành công! Shop: {shop_name}")
            else:
                self.write_log(f"  ❌ Kết nối thất bại: {result.get('message', str(result))}")
            client.close()
        except Exception as e:
            self.write_log(f"  ❌ Lỗi kết nối: {e}")

    @work
    async def run_all(self):
        self.write_log("▶️ Chạy toàn bộ pipeline...")
        await self.run_crawl()
        await self.run_images()
        await self.run_video()
        await self.run_caption()
        await self.run_publish()
        await self.run_cashflow()
        self.write_log("✅ Pipeline hoàn tất! Dùng các nút Hậu mãi cho bước tiếp theo.")

    def on_button_pressed(self, event: Button.Pressed):
        btn_id = event.button.id or ""
        if btn_id == "back":
            self.app.pop_screen()
        elif btn_id == "run-crawl":
            self.app.push_screen(
                ConfirmScreen("Xác nhận crawl", f"Crawl sản phẩm từ AliExpress/1688 cho store này?", "crawl"),
                lambda ok: self.run_crawl() if ok else None,
            )
        elif btn_id == "run-images":
            self.run_images()
        elif btn_id == "run-video":
            self.app.push_screen(
                ConfirmScreen("Xác nhận xử lý video", "Tải video gốc, xóa âm thanh và chèn nhạc nền?", "video"),
                lambda ok: self.run_video() if ok else None,
            )
        elif btn_id == "run-caption":
            self.run_caption()
        elif btn_id == "run-pricing":
            self.app.push_screen(
                ConfirmScreen("Xác nhận cập nhật giá", "So sánh giá với đối thủ trên Shopee?\nSản phẩm không lợi nhuận sẽ bị tạm ẩn.", "pricing"),
                lambda ok: self.run_pricing() if ok else None,
            )
        elif btn_id == "run-publish":
            self.app.push_screen(
                ConfirmScreen("Xác nhận đăng Shopee", f"Đăng sản phẩm lên Shopee thật? Cần có Partner ID hợp lệ.", "publish"),
                lambda ok: self.run_publish() if ok else None,
            )
        elif btn_id == "run-orders":
            self.app.push_screen(
                ConfirmScreen("Đồng bộ đơn hàng", "Đồng bộ đơn Shopee sang dữ liệu fulfillment?", "orders"),
                lambda ok: self.run_orders() if ok else None,
            )
        elif btn_id == "run-flashsale":
            self.app.push_screen(
                ConfirmScreen("Flash Sale", "Đăng ký Flash Sale cho sản phẩm có lợi nhuận?", "flashsale"),
                lambda ok: self.run_flashsale() if ok else None,
            )
        elif btn_id == "run-cashflow":
            self.app.push_screen(
                ConfirmScreen("Phân tích dòng tiền", "Dự báo vốn lưu động cho tuần tới?", "cashflow"),
                lambda ok: self.run_cashflow() if ok else None,
            )
        elif btn_id == "run-trends":
            self.app.push_screen(
                ConfirmScreen("Quét xu hướng", "Quét Shopee và 1688 để phát hiện từ khóa nóng?", "trends"),
                lambda ok: self.run_trends() if ok else None,
            )
        elif btn_id == "run-virtualhub":
            self.app.push_screen(
                ConfirmScreen("Virtual Hub", "Map tracking 1688 sang Shopee và tạo manifest?", "virtualhub"),
                lambda ok: self.run_virtualhub() if ok else None,
            )
        elif btn_id == "run-customercare":
            self.app.push_screen(
                ConfirmScreen("Auto Care", "Gửi tin nhắn chăm sóc cho đơn hàng?", "customercare"),
                lambda ok: self.run_customercare() if ok else None,
            )
        elif btn_id == "export-cookies":
            self.app.push_screen(
                ConfirmScreen("Xuất cookies 1688", "Đọc cookies 1688 từ Chrome và lưu vào config?", "cookies"),
                lambda ok: self.do_export_cookies() if ok else None,
            )
        elif btn_id == "check-shopee":
            self.do_check_shopee()
        elif btn_id == "run-all":
            self.app.push_screen(
                ConfirmScreen("Xác nhận pipeline", f"Chạy toàn bộ: Crawl → Ảnh → Video → Caption → Đăng Shopee?", "all"),
                lambda ok: self.run_all() if ok else None,
            )


# ── APP ─────────────────────────────────────────────────────────
class PipelineApp(App):
    TITLE = "Shopee Dropship Pipeline"
    CSS = """
    Screen { background: #1a1b26; }
    .title { text-style: bold; color: #7aa2f7; padding: 1; text-align: center; }
    .subtitle { padding: 0 1; color: #a9b1d6; }
    .section-title { padding: 1 0 0 0; color: #c0caf5; text-style: bold; }
    .store-name { padding: 1; color: #c0caf5; }
    .store-card { height: 3; border: solid #3b4261; margin: 0 1; }
    .store-card Button { margin: 0 1; }
    .info { color: #9ece6a; padding: 0 1; }
    .error { color: #f7768e; }
    .suggestion-info { padding: 1 0 0 0; color: #c0caf5; }
    #store-list, #suggestions-list, #menu-buttons { height: auto; min-height: 5; }
    #log { height: 8; border: solid #3b4261; margin: 0 1; }
    #crawl-log { height: 8; border: solid #3b4261; margin: 0 1; }
    #main-content, #detail-content, #form-content, #edit-content, #crawl-content, #discovery-content, #confirm-content {
        padding: 1 2; }
    Button { margin: 1 0; }
    #edit-content Input { margin: 0 1 0 1; }
    #edit-content Label { padding: 0 1; margin-top: 1; }
    Input { margin: 0 1 1 1; }
    Label { padding: 0 1; color: #a9b1d6; }
    """

    def on_mount(self):
        self.push_screen(MainMenuScreen())
