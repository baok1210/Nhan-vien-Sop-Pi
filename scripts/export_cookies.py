#!/usr/bin/env python3
"""
Export cookies from Chrome for 1688.com, aliexpress.com, shopee.vn.
Tự động lấy cookie — KHÔNG cần đóng Chrome.

Cách hoạt động:
  1. Copy file Cookies của Chrome ra temp (Windows cho copy dù file đang bị lock)
  2. Đọc SQLite từ bản copy → giải mã DPAPI → lưu JSON
  3. Fallback: dùng Playwright nếu SQLite không có cookie

Usage:
    python scripts/export_cookies.py
"""
import json, os, sqlite3, shutil, tempfile, sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')
from src.utils.logger import setup_logger

logger = setup_logger("cookie_exporter")

# Auto-detect all Chrome profiles
_CHROME_BASE = os.environ.get("LOCALAPPDATA", "") + r"\Google\Chrome\User Data"
CHROME_PATHS = []
if Path(_CHROME_BASE).exists():
    for profile in ["Default"] + [f"Profile {i}" for i in range(1, 10)]:
        for sub in ["Network/Cookies", "Cookies"]:
            p = Path(_CHROME_BASE) / profile / sub
            if p.exists():
                CHROME_PATHS.append(str(p))

DOMAINS = {
    "1688": ["1688.com", ".1688.com"],
    "aliexpress": ["aliexpress.com", ".aliexpress.com"],
    "shopee": ["shopee.vn", ".shopee.vn", "shopee.com", ".shopee.com"],
}


def _decrypt(enc_val: bytes) -> bytes | None:
    """Decrypt Chrome cookie value using Windows DPAPI."""
    if not enc_val or enc_val == b"":
        return None
    if enc_val.startswith(b"v10") or enc_val.startswith(b"v11"):
        try:
            import win32crypt
            return win32crypt.CryptUnprotectData(enc_val, None, None, None, 0)[1]
        except ImportError:
            logger.warning("win32crypt not installed, trying raw value")
            return enc_val
    return enc_val


def _copy_and_read_cookies(db_path: str, domains: list[str]) -> dict:
    """Copy cookie DB to temp (works even if Chrome is running) and read cookies."""
    tmp = tempfile.mktemp(suffix=".sqlite")
    try:
        shutil.copy2(db_path, tmp)
        conn = sqlite3.connect(tmp)
        conn.text_factory = bytes
        cur = conn.cursor()
        cookies = {}
        for domain in domains:
            try:
                rows = cur.execute(
                    "SELECT name, encrypted_value, has_expires, expires_utc "
                    "FROM cookies WHERE host_key LIKE ? OR host_key = ?",
                    (f"%{domain}", domain),
                ).fetchall()
                for name, enc_val, has_expires, expires_utc in rows:
                    try:
                        val = _decrypt(enc_val)
                        if val:
                            key = name.decode() if isinstance(name, bytes) else name
                            val_s = val.decode() if isinstance(val, bytes) else val
                            cookies[key] = val_s
                    except Exception:
                        pass
            except Exception:
                continue
        conn.close()
        return cookies
    except Exception as e:
        logger.debug(f"Copy+read failed: {e}")
        return {}
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _export_via_playwright(domains: list[str]) -> dict:
    """Fallback: dùng Playwright launch Chromium với từng profile để lấy cookie."""
    if not Path(_CHROME_BASE).exists():
        return {}
    profiles = ["Default"] + [f"Profile {i}" for i in range(1, 10)]
    all_cookies = {}
    for pname in profiles:
        pdir = Path(_CHROME_BASE) / pname
        if not pdir.is_dir():
            continue
        logger.info(f"Playwright: thử profile {pname}...")
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                ctx = p.chromium.launch_persistent_context(
                    user_data_dir=str(pdir),
                    headless=True,
                    args=["--no-sandbox"],
                )
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                for domain in domains:
                    try:
                        page.goto(f"https://{domain.lstrip('.')}", timeout=15000, wait_until="domcontentloaded")
                        cks = ctx.cookies()
                        for c in cks:
                            all_cookies[c["name"]] = c["value"]
                    except Exception:
                        continue
                ctx.close()
                if all_cookies:
                    logger.info(f"Playwright OK: {len(all_cookies)} cookies từ {pname}")
                    return all_cookies
        except Exception as e:
            logger.debug(f"Playwright {pname} failed: {e}")
            continue
    return all_cookies


def export_cookies(domains: list[str]) -> dict:
    # Method 1: Copy SQLite DB (works with Chrome running)
    for db_path in CHROME_PATHS:
        if not Path(db_path).exists():
            continue
        logger.info(f"Reading: {db_path}")
        cookies = _copy_and_read_cookies(db_path, domains)
        if cookies:
            logger.info(f"OK: {len(cookies)} cookies từ SQLite")
            return cookies
        logger.info("  No cookies found, trying next path...")

    # Method 2: Playwright fallback
    logger.info("SQLite không có cookie, thử Playwright...")
    return _export_via_playwright(domains)


def save_netscape(cookies: dict, domain: str, path: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Netscape HTTP Cookie File\n")
        f.write(f"# Exported at {datetime.now().isoformat()}\n")
        for name, value in cookies.items():
            f.write(f"{domain}\tTRUE\t/\tFALSE\t0\t{name}\t{value}\n")


def main():
    print("=" * 60)
    print("XUẤT COOKIE CHROME (không cần đóng Chrome)")
    print("=" * 60)
    print()

    for target, domains in DOMAINS.items():
        print(f"\n--- {target} ---")
        cookies = export_cookies(domains)

        if cookies:
            out_json = Path(f"config/{target}_cookies.json")
            with open(out_json, "w", encoding="utf-8") as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)
            logger.info(f"Đã lưu: {out_json} ({len(cookies)} cookies)")

            out_netscape = Path(f"config/{target}_cookies.txt")
            save_netscape(cookies, domains[0], str(out_netscape))
            logger.info(f"Đã lưu: {out_netscape} ({len(cookies)} cookies)")

            print(f"\n  ✅ Xuất thành công: {len(cookies)} cookies → config/{target}_cookies.json")
            print(f"  Scraper sẽ tự động tải cookies từ file này.")
        else:
            print(f"  ❌ Không tìm thấy cookies cho {target}")
            print(f"  Hãy đảm bảo bạn đã đăng nhập {target} trong Chrome.")

    print("\nHoàn tất.")


if __name__ == "__main__":
    main()
