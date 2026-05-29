from textual.screen import Screen
from textual.widgets import Button, Static
from textual.containers import Vertical, Horizontal


class ConfirmScreen(Screen):
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
