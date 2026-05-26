"""
Config Wizard - Công cụ cấu hình tự động cho China Dropship to Shopee
Chạy script này để nhập API keys và thông tin Shopee một cách dễ dàng.
"""
import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "config.json"
STORES_DIR = BASE_DIR / "config" / "stores"


def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")


def print_step(n, text):
    print(f"\n>>> Bước {n}: {text}")


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
    return val in ("y", "yes", "có")


def main():
    print_header("CHINA DROPSHIP TO SHOPEE - CONFIG WIZARD")
    print("Công cụ này sẽ giúp bạn cấu hình phần mềm một cách dễ dàng.")
    print("Bạn có thể bỏ qua các bước và để trống nếu chưa có thông tin.")
    input("\nNhấn Enter để bắt đầu...")

    config = {}
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                config = json.load(f)
            print(f"\nĐã tải cấu hình hiện tại từ {CONFIG_PATH}")
        except Exception:
            config = {}

    # === Bước 1: Tên cửa hàng ===
    print_step(1, "Thông tin cửa hàng")
    store_name = ask("Tên cửa hàng của bạn trên Shopee", default=config.get("niche", {}).get("name", "Cửa hàng của tôi"))
    store_id = store_name.lower().replace(" ", "-").replace("đ", "d").replace(" ", "")[:30]

    niche = config.get("niche", {})
    niche["name"] = store_name

    cn_keywords_str = ask("Từ khóa tìm kiếm tiếng Trung (cách nhau bằng dấu phẩy)", default=", ".join(niche.get("keywords_cn", ["手机配件", "时尚饰品"])))
    niche["keywords_cn"] = [k.strip() for k in cn_keywords_str.split(",") if k.strip()]

    en_keywords_str = ask("Từ khóa tìm kiếm tiếng Anh (cách nhau bằng dấu phẩy)", default=", ".join(niche.get("keywords_en", ["phone accessories", "fashion accessories"])))
    niche["keywords_en"] = [k.strip() for k in en_keywords_str.split(",") if k.strip()]

    vn_keywords_str = ask("Từ khóa tìm kiếm tiếng Việt (cách nhau bằng dấu phẩy)", default=", ".join(niche.get("keywords_vn", ["phụ kiện điện thoại", "phụ kiện thời trang"])))
    niche["keywords_vn"] = [k.strip() for k in vn_keywords_str.split(",") if k.strip()]

    max_price = ask("Giá tối đa (CNY) - mặc định 50", default=str(niche.get("max_price_cny", 50)))
    niche["max_price_cny"] = float(max_price) if max_price else 50

    multiplier = ask("Hệ số giá (VD: 2.5 = giá bán gấp 2.5 lần giá nhập)", default=str(niche.get("price_multiplier", 2.5)))
    niche["price_multiplier"] = float(multiplier) if multiplier else 2.5

    config["niche"] = niche

    # === Bước 2: Google Gemini API Key ===
    print_step(2, "Google Gemini API Key (MIỄN PHÍ)")
    print("  Đây là API dùng để tạo caption tiếng Việt tự động.")
    print("  Nếu không có, phần mềm sẽ dùng template (chất lượng thấp hơn).")
    print("  Đăng ký tại: https://aistudio.google.com/apikey")
    print("  (Google Gemini có 60 request/phút miễn phí)")
    ai_cfg = config.get("ai", {})
    caption_cfg = ai_cfg.get("caption", {})
    gemini_key = ask("Nhập Google Gemini API Key (để trống nếu chưa có)", default=caption_cfg.get("api_key", ""))
    caption_cfg["provider"] = "google_gemini" if gemini_key else caption_cfg.get("provider", "google_gemini")
    caption_cfg["api_key"] = gemini_key
    caption_cfg["model"] = ask("Model Gemini (mặc định: gemini-2.0-flash)", default=caption_cfg.get("model", "gemini-2.0-flash"))
    ai_cfg["caption"] = caption_cfg

    trans_cfg = ai_cfg.get("translation", {})
    if gemini_key:
        trans_cfg["provider"] = "google_gemini"
        trans_cfg["api_key"] = gemini_key
    ai_cfg["translation"] = trans_cfg
    config["ai"] = ai_cfg

    # === Bước 3: Shopee API ===
    print_step(3, "Shopee Developer API")
    print("  Để đăng sản phẩm lên Shopee, bạn cần đăng ký App tại:")
    print("  https://open.shopee.com -> Đăng ký App")
    print("  Nếu chưa có, phần mềm vẫn chạy các bước crawl, xử lý ảnh, tạo caption")
    print("  nhưng BỎ QUA bước đăng bán.")
    use_shopee = ask_yes_no("Bạn đã có Shopee Developer App?", default=False)

    shopee_cfg = config.get("shopee", {})
    if use_shopee:
        shopee_cfg["partner_id"] = ask("Partner ID", default=shopee_cfg.get("partner_id", ""))
        shopee_cfg["partner_key"] = ask("Partner Key", default=shopee_cfg.get("partner_key", ""))
        shopee_cfg["shop_id"] = ask("Shop ID", default=shopee_cfg.get("shop_id", ""))
        shopee_cfg["access_token"] = ask("Access Token (để trống nếu chưa có)", default=shopee_cfg.get("access_token", ""))
        shopee_cfg["refresh_token"] = ask("Refresh Token (để trống nếu chưa có)", default=shopee_cfg.get("refresh_token", ""))
        env = ask("Môi trường (uat = thử nghiệm, prod = thật)", default=shopee_cfg.get("environment", "uat"))
        shopee_cfg["environment"] = env if env in ("uat", "prod") else "uat"
    else:
        print("  Bỏ qua cấu hình Shopee. Bạn có thể cấu hình sau trong file config/config.json")
    config["shopee"] = shopee_cfg

    # === Bước 4: Nguồn hàng ===
    print_step(4, "Nguồn hàng")
    print("  Mặc định phần mềm crawl từ 1688.com và AliExpress.")
    print("  Bạn có thể tắt/bật từng nguồn.")
    source_cfg = config.get("source", {})
    src_1688 = source_cfg.get("1688", {})
    src_1688["enabled"] = ask_yes_no("Bật crawl từ 1688.com?", default=src_1688.get("enabled", True))
    src_1688["method"] = "cookie"
    src_1688["dropship_filter"] = ask_yes_no("Chỉ lấy sản phẩm hỗ trợ dropship?", default=src_1688.get("dropship_filter", True))
    src_1688["max_pages"] = int(ask("Số trang tối đa (1-5)", default=str(src_1688.get("max_pages", 3))))
    source_cfg["1688"] = src_1688

    src_ae = source_cfg.get("aliexpress", {})
    src_ae["enabled"] = ask_yes_no("Bật crawl từ AliExpress?", default=src_ae.get("enabled", True))
    src_ae["max_pages"] = int(ask("Số trang tối đa (1-5)", default=str(src_ae.get("max_pages", 3))))
    source_cfg["aliexpress"] = src_ae
    config["source"] = source_cfg

    # === Bước 5: Xử lý ảnh ===
    print_step(5, "Xử lý ảnh")
    img_cfg = config.get("image_processing", {})
    img_cfg["output_format"] = ask("Định dạng ảnh đầu ra (jpeg/png)", default=img_cfg.get("output_format", "jpeg"))
    img_cfg["quality"] = int(ask("Chất lượng ảnh (1-100)", default=str(img_cfg.get("quality", 92))))

    bg_removal = img_cfg.get("bg_removal", {})
    use_bg = ask_yes_no("Bật xóa nền ảnh? (cần thư viện rembg)", default=bg_removal.get("enabled", False))
    bg_removal["enabled"] = use_bg
    if use_bg:
        bg_removal["bg_color"] = ask("Màu nền thay thế (mã HEX, VD: #FFFFFF)", default=bg_removal.get("bg_color", "#FFFFFF"))
    img_cfg["bg_removal"] = bg_removal
    config["image_processing"] = img_cfg

    # === Lưu config ===
    print_step(6, "Lưu cấu hình")
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print(f"  Đã lưu cấu hình vào: {CONFIG_PATH}")

    # === Tạo store config ===
    if use_shopee and shopee_cfg.get("partner_id"):
        store_config = {
            "id": store_id,
            "name": store_name,
            "niche": niche,
            "sources": source_cfg,
            "shopee": shopee_cfg,
            "schedule": config.get("schedule", {
                "crawl_interval_hours": 24,
                "post_per_day": 10,
                "post_interval_minutes": 60,
            }),
        }
        STORES_DIR.mkdir(parents=True, exist_ok=True)
        store_path = STORES_DIR / f"{store_id}.json"
        with open(store_path, "w", encoding="utf-8") as f:
            json.dump(store_config, f, ensure_ascii=False, indent=2)
        print(f"  Đã tạo cấu hình cửa hàng: {store_path}")

    print_header("HOÀN TẤT!")
    print("Cấu hình đã được lưu. Bạn có thể chạy phần mềm ngay bây giờ!")
    print(f"\n  Để chạy giao diện: python scripts/run.py")
    print(f"  Để crawl thủ công: python scripts/crawl_products.py")
    print(f"  Để xử lý ảnh:     python scripts/process_images.py")
    print(f"  Để tạo caption:   python scripts/generate_captions.py")
    print(f"  Để đăng Shopee:   python scripts/post_to_shopee.py")
    print(f"\nCần chỉnh sửa sau? Mở file: config/config.json")
    print("\nCảm ơn đã sử dụng China Dropship to Shopee!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nĐã hủy. Cấu hình chưa được lưu.")
        sys.exit(0)
