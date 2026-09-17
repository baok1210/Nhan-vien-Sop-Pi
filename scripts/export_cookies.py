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
import json, os, sqlite3, shutil, tempfile, sys, base64
from pathlib import Path
from datetime import datetime

CDP_PORT = int(os.environ.get("CHROME_CDP_PORT", "9333"))

sys.path.insert(0, str(Path(__file__).parent.parent))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')
from src.utils.logger import setup_logger

logger = setup_logger("cookie_exporter")

AUTO = {"restart": None}  # cau hoi restart Chrome 1 lan duy nhat moi chay

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


def _aesgcm_decrypt(enc_val: bytes) -> bytes | None:
    """Decrypt Chrome v10/v11 blob: AES-256-GCM voi key trong 'Local State'
    (chinh key nay duoc DPAPI bao ve). Cach nay moi dung voi Chrome hien dai."""
    try:
        import win32crypt
        from Crypto.Cipher import AES
    except ImportError:
        return None
    try:
        local_state = Path(_CHROME_BASE) / "Local State"
        key_b64 = json.loads(local_state.read_text(encoding="utf-8"))["os_crypt"]["encrypted_key"]
        key = win32crypt.CryptUnprotectData(base64.b64decode(key_b64)[5:], None, None, None, 0)[1]
        nonce, body = enc_val[3:15], enc_val[15:]
        return AES.new(key, AES.MODE_GCM, nonce=nonce).decrypt_and_verify(body[:-16], body[-16:])
    except Exception:
        return None


def _decrypt(enc_val: bytes) -> bytes | None:
    """Decrypt Chrome cookie value: AES-GCM truoc, DPAPI-truc-tiep cho blob cu."""
    if not enc_val or enc_val == b"":
        return None
    if enc_val.startswith(b"v10") or enc_val.startswith(b"v11"):
        val = _aesgcm_decrypt(enc_val)
        if val:
            return val
        # Fallback Chrome cu (pre-80): DPAPI truc tiep
        try:
            import win32crypt
            return win32crypt.CryptUnprotectData(enc_val, None, None, None, 0)[1]
        except ImportError:
            logger.warning("win32crypt not installed, trying raw value")
            return enc_val
        except Exception:
            return None
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


def _cdp_alive(port: int) -> bool:
    import urllib.request
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2)
        return True
    except Exception:
        return False


def _restart_chrome_with_debug(port: int) -> bool:
    """Dong Chrome hien tai, mo lai CUNG profile voi CDP. Chrome se hoi phuc
    session/tab; cookie dang nhap giu nguyen vi cung user-data-dir."""
    import time, subprocess
    exe = next((p for p in [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ] if Path(p).exists()), None)
    if not exe:
        logger.warning("Khong tim thay chrome.exe")
        return False
    running = subprocess.run(["tasklist", "/FI", "IMAGENAME eq chrome.exe"],
                             capture_output=True, text=True).stdout.lower()
    if "chrome.exe" in running:
        logger.info("Dong Chrome hien tai (tab se duoc hoi phuc khi mo lai)...")
        subprocess.run(["taskkill", "/IM", "chrome.exe", "/F"], capture_output=True)
        time.sleep(3)
    subprocess.Popen([exe, f"--remote-debugging-port={port}"],
                     creationflags=0x00000008)  # DETACHED_PROCESS
    for _ in range(30):
        time.sleep(1)
        if _cdp_alive(port):
            logger.info(f"Chrome da len o che do debug (port {port})")
            return True
    return False


def _export_via_cdp(domains: list[str]) -> dict:
    """Method 0: doc cookie tu Chrome DANG CHAY qua CDP (Storage.getCookies).
    Chrome tu giai ma — hoat dong ca voi App-Bound Encryption (Chrome 127+),
    tuc la duong duy nhat con lai voi cookie dang nhap tren Chrome moi.
    Yeu cau Chrome mo voi --remote-debugging-port (mac dinh 9222)."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=3) as r:
            ver = json.loads(r.read().decode())
    except Exception:
        logger.info(f"CDP: khong co Chrome debug o port {CDP_PORT} - bo qua Method 0")
        return {}
    try:
        import websocket
    except ImportError:
        logger.warning("CDP: chua cai websocket-client (pip install websocket-client)")
        return {}
    ws_url = ver.get("webSocketDebuggerUrl")
    if not ws_url:
        return {}
    try:
        ws = websocket.create_connection(ws_url, timeout=15)
        ws.send(json.dumps({"id": 1, "method": "Storage.getCookies"}))
        msg = {}
        for _ in range(20):
            msg = json.loads(ws.recv())
            if msg.get("id") == 1:
                break
        ws.close()
        all_cookies = (msg.get("result") or {}).get("cookies") or []
        out = {}
        suffixes = tuple(d.lstrip(".") for d in domains)
        for c in all_cookies:
            d = (c.get("domain") or "").lstrip(".")
            if d.endswith(suffixes) and c.get("value"):
                out[c["name"]] = c["value"]
        logger.info(f"CDP OK: {len(all_cookies)} cookies tong, {len(out)} khop domain")
        return out
    except Exception as e:
        logger.warning(f"CDP failed: {e}")
        return {}


def export_cookies(domains: list[str], auto_restart: bool = False) -> dict:
    # Method 0: Chrome dang chay qua CDP - duy nhat hoat dong voi Chrome 127+ ABE
    if not _cdp_alive(CDP_PORT) and auto_restart:
        _restart_chrome_with_debug(CDP_PORT)
    cookies = _export_via_cdp(domains)
    if cookies:
        return cookies

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
        if not _cdp_alive(CDP_PORT) and AUTO["restart"] is None:
            ans = input("Khong thay Chrome debug. Dong Chrome va mo lai o che do debug de lay cookie dang nhap? [Y/n] ").strip().lower()
            AUTO["restart"] = (ans != "n")
            if AUTO["restart"] and not _restart_chrome_with_debug(CDP_PORT):
                print("  Khong mo duoc Chrome debug — se thu cac cach cu.")
                AUTO["restart"] = False
        cookies = export_cookies(domains, auto_restart=AUTO["restart"] or False)

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
