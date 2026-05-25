#!/usr/bin/env python3
"""
Export cookies from Chrome for 1688.com and shopee.vn.
Saves as JSON (for curl_cffi) and Netscape format (for curl CLI).

Usage:
    python scripts/export_cookies.py

Requirements:
    - Chrome must be fully closed (or use a different Chrome profile)
    - If Chrome is running, you'll get a database locked error.
      Close all Chrome windows first, or copy the Cookies file manually.
"""
import json, os, sqlite3, http.cookiejar, sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.utils.logger import setup_logger

logger = setup_logger("cookie_exporter")

# Possible Chrome cookie DB locations
CHROME_PATHS = [
    os.environ.get("LOCALAPPDATA", "") + r"\Google\Chrome\User Data\Default\Network\Cookies",
    os.environ.get("LOCALAPPDATA", "") + r"\Google\Chrome\User Data\Default\Cookies",
    os.environ.get("LOCALAPPDATA", "") + r"\Google\Chrome\User Data\Profile 1\Network\Cookies",
    os.environ.get("LOCALAPPDATA", "") + r"\Google\Chrome\User Data\Profile 1\Cookies",
    os.environ.get("LOCALAPPDATA", "") + r"\Google\Chrome\User Data\Profile 2\Network\Cookies",
    os.environ.get("LOCALAPPDATA", "") + r"\Google\Chrome\User Data\Profile 2\Cookies",
]

DOMAINS = {
    "1688": ["1688.com", ".1688.com"],
    "shopee": ["shopee.vn", ".shopee.vn", "shopee.com", ".shopee.com"],
}


def export_cookies(domains: list[str]) -> dict:
    cookies = {}
    for db_path in CHROME_PATHS:
        if not Path(db_path).exists():
            continue
        logger.info(f"Trying: {db_path}")
        try:
            conn = sqlite3.connect(db_path)
            conn.text_factory = bytes
            cur = conn.cursor()
            for domain in domains:
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
                            logger.debug(f"  {key}={val_s[:20]}...")
                    except Exception:
                        pass
            conn.close()
            if cookies:
                logger.info(f"Found {len(cookies)} cookies")
                break
        except sqlite3.OperationalError as e:
            logger.warning(f"Cannot open: {e}")
        except Exception as e:
            logger.warning(f"Error: {e}")
    return cookies


def _decrypt(enc_val: bytes) -> bytes | None:
    """Decrypt Chrome cookie value using Windows DPAPI."""
    if not enc_val or enc_val == b"":
        return None
    if enc_val.startswith(b"v10") or enc_val.startswith(b"v11"):
        try:
            import win32crypt
            return win32crypt.CryptUnprotectData(enc_val, None, None, None, 0)[1]
        except ImportError:
            return enc_val  # Return raw (might be plaintext)
    else:
        return enc_val  # Plaintext cookie


def save_netscape(cookies: dict, domain: str, path: str):
    """Save cookies in Netscape format for curl CLI."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Netscape HTTP Cookie File\n")
        f.write(f"# Exported at {datetime.now().isoformat()}\n")
        for name, value in cookies.items():
            f.write(f"{domain}\tTRUE\t/\tFALSE\t0\t{name}\t{value}\n")


def main():
    print("=" * 60)
    print("CHROME COOKIE EXPORTER")
    print("=" * 60)
    print("Close Chrome completely before running!")
    print()

    for target, domains in DOMAINS.items():
        print(f"\n--- {target} ---")
        cookies = export_cookies(domains)

        if cookies:
            out_json = Path(f"config/{target}_cookies.json")
            with open(out_json, "w", encoding="utf-8") as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved: {out_json} ({len(cookies)} cookies)")

            out_netscape = Path(f"config/{target}_cookies.txt")
            save_netscape(cookies, domains[0], str(out_netscape))
            logger.info(f"Saved: {out_netscape} ({len(cookies)} cookies)")

            print(f"\n  Export complete. Files saved to config/")
            if target == "shopee":
                print(f"\n  To use these cookies in your store config:")
                print(f"  1. Copy shopee_cookies.json content")
                print(f"  2. Add it to config/stores/<store_id>.json under shopee.cookies:")
            if target == "1688":
                print(f"\n  1688 scraper auto-loads from config/1688_cookies.json")
        else:
            print(f"  No cookies found for {target}")
            print(f"  Make sure you're logged into {target} in Chrome.")

    print("\nDone.")


if __name__ == "__main__":
    main()
