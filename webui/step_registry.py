"""Decorator-based step registry + ComponentMetadata (requires/assigns).
Inspired by spaCy's @Language.factory with requires/assigns metadata."""
from pathlib import Path

_registry: dict[str, dict] = {}
BASE_DIR = Path(__file__).parent.parent


def step_register(name, label="", desc="", icon="", requires_files=None,
                  requires_files_any=None, assigns_files=None,
                  requires_shopee=False,
                  category="other", order=99, fields=None):
    """Register a pipeline step function with metadata.
    
    Args:
        name: Short unique key (e.g. 'crawl')
        label: UI label (e.g. '1. Crawl sản phẩm')
        desc: Full description shown in modal tooltip
        icon: Emoji icon
        requires_files: List of data files ALL must exist before this step runs
        requires_files_any: List of data files where AT LEAST ONE must exist
        assigns_files: List of data files this step produces
        requires_shopee: True if Shopee API creds must be configured
        category: 'pipeline' | 'operations' | 'marketing' | 'service'
        order: Display order within category
        fields: Config field definitions for the step modal
    """
    def decorator(func):
        _registry[name] = {
            'name': name,
            'label': label,
            'desc': desc,
            'icon': icon,
            'requires_files': requires_files or [],
            'requires_files_any': requires_files_any or [],
            'assigns_files': assigns_files or [],
            'requires_shopee': requires_shopee,
            'category': category,
            'order': order,
            'fields': fields or [],
            'func': func,
        }
        return func
    return decorator


def get_step(name: str) -> dict | None:
    return _registry.get(name)


def list_steps(category: str = None, serializable: bool = False) -> list[dict]:
    steps = sorted(_registry.values(), key=lambda s: (s['order'], s['name']))
    if category:
        steps = [s for s in steps if s['category'] == category]
    if serializable:
        return [{k: v for k, v in s.items() if k != 'func'} for s in steps]
    return steps


def get_func(name: str):
    info = _registry.get(name)
    if info:
        return info['func']
    return None


def check_prerequisites(store_id: str, step_name: str) -> tuple[bool, list[str]]:
    """Check if prerequisites are met for a step.
    Returns (ok: bool, messages: list[str])."""
    info = _registry.get(step_name)
    if not info:
        return False, ['Không tìm thấy bước này']

    data_dir = BASE_DIR / 'data' / store_id
    missing = []

    for f in info['requires_files']:
        if not (data_dir / f).exists():
            missing.append(f)

    if info['requires_files_any']:
        any_exists = any((data_dir / f).exists() for f in info['requires_files_any'])
        if not any_exists:
            names = ' hoặc '.join(info['requires_files_any'])
            missing.append(names)

    if info['requires_shopee']:
        try:
            from src.config_manager import load_store
            config = load_store(store_id) or {}
            shopee = config.get('shopee', {})
            if not shopee.get('partner_id') or not shopee.get('partner_key'):
                missing.append('thông tin Shopee API (partner_id, partner_key)')
        except Exception:
            missing.append('không thể đọc config store')

    if missing:
        return False, [f'Cần có: {", ".join(missing)} trước khi chạy bước này']
    return True, []


def check_store_file_status(store_id: str) -> dict[str, bool]:
    """Return dict of {filename: exists} for all data files referenced by steps."""
    data_dir = BASE_DIR / 'data' / store_id
    all_files = set()
    for info in _registry.values():
        all_files.update(info['requires_files'])
        all_files.update(info['assigns_files'])
    return {f: (data_dir / f).exists() for f in sorted(all_files) if f}


# --- Config field definitions per step (kept separate for readability) ---
_STEP_FIELDS: dict[str, list[dict]] = {
    'crawl': [
        {'name':'max_pages_1688', 'label':'Số trang 1688', 'type':'number', 'default':3, 'min':1, 'max':20},
        {'name':'max_pages_aliexpress', 'label':'Số trang AliExpress', 'type':'number', 'default':3, 'min':1, 'max':20},
        {'name':'', 'label':'Mạng & Chống chặn', 'type':'separator'},
        {'name':'proxies', 'label':'Danh sách proxy (mỗi dòng 1 proxy)', 'type':'textarea', 'default':'', 'help':'http://user:pass@ip:port — mỗi dòng 1 proxy, tự động rotation khi bị chặn'},
        {'name':'delay_min', 'label':'Delay min (giây)', 'type':'number', 'default':3, 'min':1, 'max':60},
        {'name':'delay_max', 'label':'Delay max (giây)', 'type':'number', 'default':8, 'min':1, 'max':60},
        {'name':'max_retries', 'label':'Số lần thử lại', 'type':'number', 'default':3, 'min':1, 'max':20},
        {'name':'', 'label':'Cookies 1688 (dán từ Chrome)', 'type':'separator'},
        {'name':'cookies_1688', 'label':'Cookies 1688', 'type':'textarea', 'default':'', 'help':'Click "Copy code" bên dưới → Paste vào Console 1688.com → Copy kết quả → Paste vào đây'},
        {'name':'cookies_ae', 'label':'Cookies AliExpress (tùy chọn)', 'type':'textarea', 'default':'', 'help':'Click "Copy code" bên dưới → Paste vào Console aliexpress.com. Để trống = dùng Playwright'},
    ],
    'images': [
        {'name':'bg_removal', 'label':'Xóa nền (background removal)', 'type':'checkbox', 'default':False},
        {'name':'enhance', 'label':'Tăng cường chất lượng', 'type':'checkbox', 'default':True},
        {'name':'watermark', 'label':'Thêm watermark', 'type':'checkbox', 'default':False},
        {'name':'watermark_text', 'label':'Nội dung watermark', 'type':'text', 'default':'', 'help':'Để trống = tên store'},
        {'name':'watermark_use_shop_name', 'label':'Dùng tên shop làm watermark', 'type':'checkbox', 'default':True},
        {'name':'quality', 'label':'Chất lượng ảnh (%)', 'type':'number', 'default':90, 'min':10, 'max':100},
    ],
    'video': [
        {'name':'max_videos', 'label':'Số video tối đa', 'type':'number', 'default':5, 'min':1, 'max':20},
        {'name':'volume', 'label':'Âm lượng nhạc nền (0-1)', 'type':'number', 'default':0.5, 'min':0, 'max':1, 'step':0.1},
    ],
    'caption': [
        {'name':'ai_provider', 'label':'Provider', 'type':'select', 'default':'google_gemini',
         'options':[{'v':'', 'l':'Template (không AI)'},{'v':'google_gemini','l':'Google Gemini'},{'v':'openai','l':'OpenAI'}]},
        {'name':'ai_api_key', 'label':'API Key', 'type':'text', 'default':''},
        {'name':'ai_model', 'label':'Model', 'type':'text', 'default':'gemini-flash-latest'},
        {'name':'ai_language', 'label':'Ngôn ngữ', 'type':'text', 'default':'vi'},
        {'name':'ai_tone', 'label':'Giọng văn', 'type':'select', 'default':'professional',
         'options':[{'v':'professional','l':'Chuyên nghiệp'},{'v':'friendly','l':'Thân thiện'},{'v':'sales','l':'Bán hàng'}]},
        {'name':'ai_max_title', 'label':'Độ dài tiêu đề (ký tự)', 'type':'number', 'default':120, 'min':30, 'max':200},
        {'name':'ai_num_hashtags', 'label':'Số hashtag', 'type':'number', 'default':10, 'min':3, 'max':30},
    ],
    'publish': [
        {'name':'item_status', 'label':'Trạng thái', 'type':'select', 'default':'UNLIST',
         'options':[{'v':'UNLIST','l':'Nháp'},{'v':'LIST','l':'Công khai'}]},
        {'name':'pre_order_days', 'label':'Ngày pre-order', 'type':'number', 'default':0, 'min':0, 'max':30},
    ],
    'orders': [
        {'name':'days_back', 'label':'Số ngày', 'type':'number', 'default':7, 'min':1, 'max':30},
    ],
    'flashsale': [
        {'name':'max_items', 'label':'Số sp tối đa', 'type':'number', 'default':20, 'min':1, 'max':100},
    ],
}


_fields_injected = False


def _inject_fields():
    """Merge _STEP_FIELDS into registry entries that have no fields yet."""
    global _fields_injected
    if _fields_injected:
        return
    for name, fields in _STEP_FIELDS.items():
        if name in _registry:
            _registry[name]['fields'] = fields
    _fields_injected = True


def _ensure_registered():
    """Ensure step functions are decorated and registry is populated."""
    from webui import state  # noqa: F401
    # Re-inject fields now because decorators may have fired during state import


# Update public accessors to call _inject_fields lazily
_original_list_steps = list_steps
_original_get_step = get_step
_original_get_func = get_func


def list_steps(category=None, serializable=False):
    _inject_fields()
    steps = sorted(_registry.values(), key=lambda s: (s['order'], s['name']))
    if category:
        steps = [s for s in steps if s['category'] == category]
    if serializable:
        return [{k: v for k, v in s.items() if k != 'func'} for s in steps]
    return steps


def get_step(name):
    _inject_fields()
    return _registry.get(name)


def get_func(name):
    _inject_fields()
    info = _registry.get(name)
    return info['func'] if info else None


_ensure_registered()
