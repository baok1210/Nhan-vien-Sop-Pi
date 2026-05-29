from textual.screen import Screen
from textual.widgets import Header, Footer, Button, Static, Label, Input
from textual.containers import VerticalScroll, Horizontal

from src.config_manager import create_store


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
                store_id = name.lower().replace(" ", "-").replace("đ", "d")
            create_store(store_id, name)
            self.app.pop_screen()
            from .store_edit import StoreEditScreen
            self.app.push_screen(StoreEditScreen(store_id))
