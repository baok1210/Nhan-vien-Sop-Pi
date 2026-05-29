"""
Config Wizard - Công cụ cấu hình tự động cho China Dropship to Shopee
Chạy script này để nhập thông tin một cách dễ dàng.
"""
import json, os, sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "config.json"
STORES_DIR = BASE_DIR / "config" / "stores"
ENV_PATH = BASE_DIR / ".env"


def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")


def print_step(n, text):
    print(f"\n  >> B\u01b0\u1edbc {n}: {text}")


def ask(question, default=""):
    if default:
        prompt = f"  {question} [{default}]: "
    else:
        prompt = f"  {question}: "
    val = input(prompt).strip()
    if not val and default:
        return default
    return val


def ask_yes_no(question, default=True):
    prompt = f"  {question} ({'Y/n' if default else 'y/N'}): "
    val = input(prompt).strip().lower()
    if not val:
        return default
    return val in ("y", "yes", "c\u00f3", "co")


def save_env(env_vars: dict):
    lines = []
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text("utf-8").splitlines():
            key = line.split("=")[0].strip()
            if key and not key.startswith("#") and key in env_vars:
                lines.append(f"{key}={env_vars.pop(key)}")
            else:
                lines.append(line)
    if env_vars:
        lines.extend(f"# {k}\n{k}={v}" if v else f"# {k}=" for k, v in env_vars.items())
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  \u2705 \u0110\u00e3 l\u01b0u b\u00ed m\u1eadt v\u00e0o .env (s\u1ebd kh\u00f4ng b\u1ecb commit l\u00ean Git)")


def main():
    print_header("CHINA DROPSHIP TO SHOPEE - C\u00c0I \u0110\u1eb6T")
    print("C\u00f4ng c\u1ee5 n\u00e0y s\u1ebd gi\u00fap b\u1ea1n c\u1ea5u h\u00ecnh ph\u1ea7n m\u1ec1m ch\u1ec9 trong v\u00e0i ph\u00fat.")
    print("C\u00f3 th\u1ec3 b\u1ecf qua c\u00e1c b\u01b0\u1edbc v\u00e0 \u0111\u1ec3 tr\u1ed1ng n\u1ebfu ch\u01b0a c\u00f3 th\u00f4ng tin.")
    input("\n  Nh\u1ea5n Enter \u0111\u1ec3 b\u1eaft \u0111\u1ea7u...")

    config = {}
    if CONFIG_PATH.exists():
        try:
            config = json.loads(CONFIG_PATH.read_text("utf-8"))
            print(f"\n  \u2705 \u0110\u00e3 t\u1ea3i c\u1ea5u h\u00ecnh hi\u1ec7n t\u1ea1i")
        except Exception:
            config = {}

    env_vars = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text("utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env_vars[k.strip()] = v.strip().strip("\"'")

    # === Bước 1: Thông tin cửa hàng ===
    print_step(1, "Th\u00f4ng tin c\u1eeda h\u00e0ng")
    store_name = ask("T\u00ean c\u1eeda h\u00e0ng Shopee (VD: Ph\u1ee5 ki\u1ec7n ABC)", default=config.get("niche", {}).get("name", "C\u1eeda h\u00e0ng c\u1ee7a t\u00f4i"))
    store_id = store_name.lower().replace(" ", "-").replace("\u0111", "d").replace(" ", "")[:30]

    niche = config.get("niche", {})
    niche["name"] = store_name

    cn_kw = ask("T\u1eeb kh\u00f3a ti\u1ebfng Trung (c\u00e1ch nhau b\u1eb1ng d\u1ea5u ph\u1ea9y)", default=", ".join(niche.get("keywords_cn", ["\u624b\u673a\u914d\u4ef6", "\u65f6\u5c1a\u9970\u54c1"])))
    niche["keywords_cn"] = [k.strip() for k in cn_kw.split(",") if k.strip()]

    en_kw = ask("T\u1eeb kh\u00f3a ti\u1ebfng Anh", default=", ".join(niche.get("keywords_en", ["phone accessories", "fashion accessories"])))
    niche["keywords_en"] = [k.strip() for k in en_kw.split(",") if k.strip()]

    vn_kw = ask("T\u1eeb kh\u00f3a ti\u1ebfng Vi\u1ec7t", default=", ".join(niche.get("keywords_vn", ["ph\u1ee5 ki\u1ec7n \u0111i\u1ec7n tho\u1ea1i", "ph\u1ee5 ki\u1ec7n th\u1eddi trang"])))
    niche["keywords_vn"] = [k.strip() for k in vn_kw.split(",") if k.strip()]

    mp = ask("Gi\u00e1 nh\u1eadp t\u1ed1i \u0111a (CNY) - m\u1eb7c \u0111\u1ecbnh 50", default=str(niche.get("max_price_cny", 50)))
    niche["max_price_cny"] = float(mp) if mp else 50

    mult = ask("H\u1ec7 s\u1ed1 gi\u00e1 (VD: 2.5 = b\u00e1n g\u1ea5p 2.5 l\u1ea7n gi\u00e1 nh\u1eadp)", default=str(niche.get("price_multiplier", 2.5)))
    niche["price_multiplier"] = float(mult) if mult else 2.5
    config["niche"] = niche

    # === Bước 2: Google Gemini (caption tự động) ===
    print_step(2, "Google Gemini API Key - t\u1ea1o caption t\u1ef1 \u0111\u1ed9ng")
    print("  \u2192 \u0110\u0103ng k\u00fd MI\u1ec4N PH\u00cd: https://aistudio.google.com/apikey")
    print("  \u2192 C\u00f3 60 request/ph\u00fat, kh\u00f4ng t\u1ed1n ph\u00ed")
    gemini_key = ask("Nh\u1eadp Google Gemini API Key (\u0111\u1ec3 tr\u1ed1ng n\u1ebfu ch\u01b0a c\u00f3)", default=env_vars.get("GEMINI_API_KEY", config.get("ai", {}).get("caption", {}).get("api_key", "")))
    if gemini_key:
        env_vars["GEMINI_API_KEY"] = gemini_key
        ai_cfg = config.setdefault("ai", {})
        caption_cfg = ai_cfg.setdefault("caption", {})
        caption_cfg["provider"] = "google_gemini"
        caption_cfg["api_key"] = gemini_key
        caption_cfg["model"] = ask("Model Gemini (m\u1eb7c \u0111\u1ecbnh: gemini-2.0-flash)", default=caption_cfg.get("model", "gemini-2.0-flash"))
        ai_cfg["caption"] = caption_cfg
        ai_cfg.setdefault("translation", {})["provider"] = "google_gemini"
        ai_cfg["translation"]["api_key"] = gemini_key

    # === Bước 3: AliExpress API (tìm kiếm sản phẩm) ===
    print_step(3, "AliExpress API - t\u00ecm ki\u1ebfm s\u1ea3n ph\u1ea9m t\u1eeb Trung Qu\u1ed1c")
    print("  \u2192 \u0110\u0103ng k\u00fd: https://openservice.aliexpress.com")
    print("  \u2192 T\u1ea1o App -> l\u1ea5y App Key + App Secret")
    print("  \u2192 N\u1ebfu kh\u00f4ng c\u00f3, ph\u1ea7n m\u1ec1m s\u1ebd d\u00f9ng web scraper (d\u1ec5 b\u1ecb ch\u1eb7n)")
    ae_key = ask("AliExpress App Key", default=env_vars.get("ALIEXPRESS_APP_KEY", config.get("source", {}).get("aliexpress", {}).get("app_key", "")))
    ae_secret = ask("AliExpress App Secret", default=env_vars.get("ALIEXPRESS_APP_SECRET", config.get("source", {}).get("aliexpress", {}).get("app_secret", "")))
    if ae_key:
        env_vars["ALIEXPRESS_APP_KEY"] = ae_key
        env_vars["ALIEXPRESS_APP_SECRET"] = ae_secret
        src = config.setdefault("source", {}).setdefault("aliexpress", {})
        src["app_key"] = ae_key
        src["app_secret"] = ae_secret
        src["method"] = "api"

    # === Bước 4: 1688.com (crawl từ 1688) ===
    print_step(4, "1688.com - ngu\u1ed3n h\u00e0ng Trung Qu\u1ed1c")
    print("  \u2192 1688 l\u00e0 ch\u1ee3 \u0111\u1ea7u m\u1ed1i l\u1edbn nh\u1ea5t Trung Qu\u1ed1c")
    print("  \u2192 Ch\u1ec9 c\u1ea7n \u0111\u0103ng nh\u1eadp 1688.com trong Chrome l\u00e0 xong")
    print("  \u2192 Cookie t\u1ef1 \u0111\u1ed9ng \u0111\u01b0\u1ee3c tr\u00edch xu\u1ea5t t\u1eeb Chrome")
    use_1688 = ask_yes_no("B\u1eadt crawl t\u1eeb 1688.com?", default=config.get("source", {}).get("1688", {}).get("enabled", True))
    src_1688 = config.setdefault("source", {}).setdefault("1688", {})
    src_1688["enabled"] = use_1688
    src_1688["method"] = "cookie"
    src_1688["dropship_filter"] = ask_yes_no("Ch\u1ec9 l\u1ea5y s\u1ea3n ph\u1ea9m h\u1ed7 tr\u1ee3 dropship?", default=src_1688.get("dropship_filter", True))
    src_1688["max_pages"] = int(ask("S\u1ed1 trang t\u1ed1i \u0111a (1-5)", default=str(src_1688.get("max_pages", 3))))

    # === Bước 5: Shopee API ===
    print_step(5, "Shopee API - \u0111\u0103ng s\u1ea3n ph\u1ea9m l\u00ean Shopee")
    print("  \u2192 \u0110\u0103ng k\u00fd: https://open.shopee.com")
    print("  \u2192 T\u1ea1o App -> l\u1ea5y Partner ID + Key")
    use_shopee = ask_yes_no("B\u1ea1n mu\u1ed1n \u0111\u0103ng s\u1ea3n ph\u1ea9m l\u00ean Shopee?", default=False)
    shopee_cfg = config.setdefault("shopee", {})
    if use_shopee:
        for env_key, cfg_key, label in [
            ("SHOPEE_PARTNER_ID", "partner_id", "Partner ID"),
            ("SHOPEE_PARTNER_KEY", "partner_key", "Partner Key"),
            ("SHOPEE_SHOP_ID", "shop_id", "Shop ID"),
            ("SHOPEE_ACCESS_TOKEN", "access_token", "Access Token"),
            ("SHOPEE_REFRESH_TOKEN", "refresh_token", "Refresh Token"),
        ]:
            val = ask(label, default=env_vars.get(env_key, shopee_cfg.get(cfg_key, "")))
            if val:
                env_vars[env_key] = val
                shopee_cfg[cfg_key] = val
        env = ask("M\u00f4i tr\u01b0\u1eddng (uat=th\u1eed nghi\u1ec7m, prod=th\u1eadt)", default=shopee_cfg.get("environment", "uat"))
        shopee_cfg["environment"] = env if env in ("uat", "prod") else "uat"
    else:
        print("  B\u1ecf qua. C\u00f3 th\u1ec3 c\u1ea5u h\u00ecnh sau trong .env")

    # === Bước 6: Lưu ===
    print_step(6, "L\u01b0u c\u1ea5u h\u00ecnh")
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  \u2705 \u0110\u00e3 l\u01b0u c\u1ea5u h\u00ecnh v\u00e0o config/config.json")

    if env_vars:
        save_env(env_vars)

    print_header("HO\u00c0N T\u1ea4T!")
    print("  B\u1ea1n c\u00f3 th\u1ec3 ch\u1ea1y ph\u1ea7n m\u1ec1m ngay b\u00e2y gi\u1edd!")
    print(f"\n  \u25b6\uFE0F python scripts/run.py          (Giao di\u1ec7n \u0111\u1ed3 h\u1ecda)")
    print(f"  \u25b6\uFE0F python src/main.py              (Pipeline t\u1ef1 \u0111\u1ed9ng)")
    print(f"\n  C\u1ea7n ch\u1ec9nh s\u1eeda sau? M\u1edf file:")
    print(f"    - \u0110\u1ed5i th\u00f4ng tin:  config/config.json")
    print(f"    - \u0110\u1ed5i API key:    .env (KH\u00d4NG commit l\u00ean Git)")
    print("\n  C\u1ea3m \u01a1n b\u1ea1n \u0111\u00e3 s\u1eed d\u1ee5ng China Dropship to Shopee!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  \u274c \u0110\u00e3 h\u1ee7y. C\u1ea5u h\u00ecnh ch\u01b0a \u0111\u01b0\u1ee3c l\u01b0u.")
        sys.exit(0)
