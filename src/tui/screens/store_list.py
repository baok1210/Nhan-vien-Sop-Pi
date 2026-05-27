from textual.screen import Screen
from textual.widgets import Header, Footer, Button, Static
from textual.containers import Container
from textual.containers import VerticalScroll, Horizontal

from src.config_manager import list_stores, load_store


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
            from .store_form import StoreFormScreen
            self.app.push_screen(StoreFormScreen())
        elif btn_id.startswith("crawl-"):
            sid = btn_id.replace("crawl-", "")
            from .store_detail import StoreDetailScreen
            self.app.push_screen(StoreDetailScreen(sid, run_crawl=True))
        elif btn_id.startswith("detail-"):
            sid = btn_id.replace("detail-", "")
            from .store_detail import StoreDetailScreen
            self.app.push_screen(StoreDetailScreen(sid))
        elif btn_id.startswith("edit-"):
            sid = btn_id.replace("edit-", "")
            from .store_edit import StoreEditScreen
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
