#!/usr/bin/env python3
"""
Dang nhap 1688 / Shopee / AliExpress vao profile rieng cua tool → cookie tu luu.

Chrome moi (127+) ma hoa cookie bang App-Bound Encryption va chan CDP tren
profile mac dinh → KHONG the "an cap" cookie tu Chrome cua ban nua.
Cach dung la: tool co profile Chrome rieng, ban dang nhap 1 lan, cookie
song trong profile do va duoc luu ra file cho scraper.

Usage:
  python scripts/login_source.py 1688        # mo cua so, ban dang nhap
  python scripts/login_source.py shopee
  python scripts/login_source.py aliexpress

Cookie luu vao:
  1688        -> config/1688_cookies.json
  shopee      -> data/shopee_cookies.json (+ config/shopee_cookies.json)
  aliexpress  -> config/aliexpress_cookies.json

Dang nhap 1 lan, dung duoc nhieu thang; het han thi chay lai la xong.
"""
import json
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

START_URL = {
    "1688": "https://login.1688.com/member/signin.htm",
    "shopee": "https://shopee.vn/buyer/login",
    "aliexpress": "https://login.aliexpress.com/",
}
# Cookie danh dau "da dang nhap" de tu dong ket thuc
LOGIN_MARKERS = {
    "1688": ["cookie_login", "tb_token", "_tb_token_"],
    "shopee": ["SPC_EC", "SPC_F", "SPC_SI"],
    "aliexpress": ["xman_us_f", "intl_common_forever", "aep_usuc_f"],
}
SAVE_PATHS = {
    "1688": [("config", "1688_cookies.json")],
    "shopee": [("data", "shopee_cookies.json"), ("config", "shopee_cookies.json")],
    "aliexpress": [("config", "aliexpress_cookies.json")],
}
DOMAIN_FILTER = {
    "1688": ("1688.com", "taobao.com", "tmall.com"),
    "shopee": ("shopee.vn", "shopee.com"),
    "aliexpress": ("aliexpress.com", "alibaba.com"),
}


def main():
    target = (sys.argv[1] if len(sys.argv) > 1 else "1688").lower().strip()
    if target not in START_URL:
        print(f"Khong biet target '{target}'. Dung: 1688 | shopee | aliexpress")
        return 2

    profile_dir = BASE_DIR / f"chrome-profile-{target}"
    profile_dir.mkdir(parents=True, exist_ok=True)
    print("=" * 60)
    print(f"  DANG NHAP {target.upper()} — cua so Chrome se mo ngay")
    print("  Dang nhap bang tay (QR / mat khau / ma xac minh).")
    print("  Tool TU DONG luu cookie khi thay ban da dang nhap xong.")
    print("=" * 60)

    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        print("Thieu patchright: python -m pip install patchright && python -m patchright install chromium")
        return 2

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            args=["--no-sandbox", "--start-maximized"],
            no_viewport=True,
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(START_URL[target], wait_until="domcontentloaded")

        markers = LOGIN_MARKERS[target]
        domains = DOMAIN_FILTER[target]
        print("\nDang nhap xong thi QUAY LAI CUA SO NAY va nhan Enter de luu cookie.")
        print("(Tool cung tu luu neu phat hien da roi khoi trang login)")

        saved = False
        deadline = time.time() + 900
        while time.time() < deadline:
            # Xac nhan bang tay: Enter trong terminal = dang nhap xong
            import select
            rdy, _, _ = select.select([sys.stdin], [], [], 3.0) if hasattr(select, "select") else ([], [], [])
            if rdy:
                sys.stdin.readline()
                break
            try:
                url_now = page.url or ""
            except Exception:
                continue
            # Tu dong: da roi khoi trang login/punish va o trang noi dung
            on_login = any(k in url_now for k in ("login", "signin", "punish", "_____tmd_____"))
            if url_now.startswith("https") and not on_login:
                try:
                    cookies = ctx.cookies()
                except Exception:
                    continue
                names = {c["name"] for c in cookies if c.get("value")}
                if any(m in names for m in markers):
                    break
        try:
            cookies = ctx.cookies()
        except Exception:
            cookies = []
        out = {}
        for c in cookies:
            d = (c.get("domain") or "").lstrip(".")
            if d.endswith(domains) and c.get("value"):
                out[c["name"]] = c["value"]
        if out:
            for rel in SAVE_PATHS[target]:
                f = BASE_DIR.joinpath(*rel)
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"\n✅ Da luu {len(out)} cookies")
            for rel in SAVE_PATHS[target]:
                print(f"   → {BASE_DIR.joinpath(*rel)}")
            saved = True
        else:
            print("\n⚠️ Khong co cookie nao de luu. Chay lai script nay khi san sang.")
        try:
            ctx.close()
        except Exception:
            pass
        return 0 if saved else 1


if __name__ == "__main__":
    sys.exit(main())
