from textual.screen import Screen
from textual.widgets import Header, Footer, Button, Static, Label, Input
from textual.containers import VerticalScroll, Horizontal

from src.config_manager import load_store, save_store


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
                Button("✅ 1688 BẬT" if sources.get("1688", {}).get("enabled") else "❌ 1688 TẮT",
                       variant="primary" if sources.get("1688", {}).get("enabled") else "default",
                       id="toggle-1688"),
                Button("✅ AliExpress BẬT" if sources.get("aliexpress", {}).get("enabled") else "❌ AliExpress TẮT",
                       variant="primary" if sources.get("aliexpress", {}).get("enabled") else "default",
                       id="toggle-ae"),
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
