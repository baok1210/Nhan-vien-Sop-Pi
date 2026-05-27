from textual.screen import Screen
from textual.widgets import Header, Footer, Button, Static
from textual.containers import Horizontal, Vertical, VerticalScroll

from src.discovery import load_pool
from src.config_manager import list_stores


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
            from .browse_crawl import BrowseCrawlScreen
            self.app.push_screen(BrowseCrawlScreen())
        elif btn_id == "discover":
            from .discovery import DiscoveryScreen
            self.app.push_screen(DiscoveryScreen())
        elif btn_id == "manage-stores":
            from .store_list import StoreListScreen
            self.app.push_screen(StoreListScreen())
