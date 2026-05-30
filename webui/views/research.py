import os, json, threading
from pathlib import Path
from flask import Blueprint, render_template, jsonify, request

from webui.state import add_log, BASE_DIR

research_bp = Blueprint('research', __name__)


@research_bp.route('/research')
def research_page():
    from src.research.market_research import _load_cached, SHOPEE_COOKIE_FILE
    data = _load_cached()
    cookie_count = 0
    if SHOPEE_COOKIE_FILE.exists():
        try:
            ck = json.loads(SHOPEE_COOKIE_FILE.read_text(encoding='utf-8'))
            cookie_count = len(ck) if isinstance(ck, list) else 0
        except Exception:
            pass
    return render_template('research.html', data=data, cookie_count=cookie_count)


@research_bp.route('/research/scan', methods=['POST'])
def research_scan():
    from src.research.market_research import scan_categories
    min_price = request.json.get('min_price', 0) if request.is_json else 0
    max_price = request.json.get('max_price', 0) if request.is_json else 0
    category_ids = request.json.get('category_ids', '') if request.is_json else ''
    try:
        result = scan_categories(
            min_price=int(min_price),
            max_price=int(max_price),
            category_ids=str(category_ids),
        )
        return jsonify({'status': 'ok', 'categories': len(result.get('categories', [])), 'summaries': result.get('summary', {})})
    except Exception as e:
        add_log(f'LỖI nghiên cứu thị trường: {e}')
        return jsonify({'error': str(e)}), 500


@research_bp.route('/research/shopee-login', methods=['POST'])
def research_shopee_login():
    cookie_file = Path('data/shopee_cookies.json')

    def _open_browser():
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                chrome_paths = [
                    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
                ]
                chrome_exe = next((pth for pth in chrome_paths if os.path.isfile(pth)), None)
                user_data = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")
                if chrome_exe and os.path.isdir(user_data):
                    add_log('🟢 Đang mở Chrome với profile hiện tại của bạn...')
                    browser = p.chromium.launch(
                        headless=False,
                        executable_path=chrome_exe,
                        args=[f"--user-data-dir={user_data}"]
                    )
                else:
                    add_log('🟢 Đang mở trình duyệt Playwright...')
                    browser = p.chromium.launch(headless=False)
                ctx = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36'
                )
                page = ctx.new_page()
                page.goto('https://shopee.vn', timeout=30000)
                page.wait_for_timeout(5000)
                add_log('🟢 Đã mở Shopee.vn. Đăng nhập trong 120s...')
                page.wait_for_timeout(120000)
                cookies = ctx.cookies()
                if cookies:
                    cookie_file.write_text(json.dumps(cookies, indent=2), encoding='utf-8')
                    add_log(f'✅ Đã lưu {len(cookies)} cookie từ Shopee')
                else:
                    add_log('⚠️ Không lấy được cookie')
                browser.close()
        except Exception as e:
            add_log(f'⚠️ Lỗi Playwright: {e}')

    threading.Thread(target=_open_browser, daemon=True).start()
    return jsonify({'status': 'opened', 'msg': 'Đã mở trình duyệt Shopee. Đăng nhập trong 120s, cookie sẽ tự động lưu.'})


@research_bp.route('/research/save-cookies', methods=['POST'])
def research_save_cookies():
    data = request.get_json(silent=True) or {}
    raw = data.get('cookies', '')
    if not raw:
        return jsonify({'error': 'Thiếu cookies'}), 400
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(parsed, list):
            return jsonify({'error': 'Phải là mảng JSON'}), 400
        Path('data/shopee_cookies.json').write_text(json.dumps(parsed, indent=2), encoding='utf-8')
        add_log(f'✅ Đã lưu {len(parsed)} cookie thủ công từ Shopee')
        return jsonify({'status': 'ok', 'count': len(parsed)})
    except Exception as e:
        return jsonify({'error': str(e)}), 400
