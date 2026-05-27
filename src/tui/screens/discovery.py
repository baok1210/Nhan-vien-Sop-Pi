import asyncio

from textual.screen import Screen
from textual.widgets import Header, Footer, Button, Static
from textual.containers import Container
from textual.containers import VerticalScroll
from textual import work

from src.discovery import load_pool, discover_niches, create_shop_from_suggestion
from src.config_manager import list_stores, save_store


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
