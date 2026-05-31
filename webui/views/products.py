import csv, io, json, uuid
from flask import Blueprint, render_template, jsonify, request
from webui.state import BASE_DIR, add_log

products_bp = Blueprint('products', __name__)


@products_bp.route('/products/<store_id>')
def view_products(store_id):
    data_dir = BASE_DIR / 'data' / store_id
    products = []
    for fname in ['captions.json', 'products_with_images.json', 'products.json']:
        p = data_dir / fname
        if p.exists():
            with open(p, encoding='utf-8') as f:
                products = json.load(f)
            break
    return render_template('products.html', store_id=store_id, products=products[:100])


def _save_products(store_id: str, products: list[dict]):
    """Write products to per-store products.json and merge into product_pool.json."""
    data_dir = BASE_DIR / 'data' / store_id
    data_dir.mkdir(parents=True, exist_ok=True)
    with open(data_dir / 'products.json', 'w', encoding='utf-8') as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    pool_path = BASE_DIR / 'data' / 'product_pool.json'
    pool = []
    if pool_path.exists():
        try:
            with open(pool_path, encoding='utf-8') as f:
                pool = json.load(f)
        except Exception:
            pass
    pool_map = {p.get('id', ''): p for p in pool if isinstance(p, dict)}
    for p in products:
        pid = p.get('id', '')
        if pid and pid in pool_map:
            pool_map[pid].update(p)
        elif pid:
            pool_map[pid] = p
    with open(pool_path, 'w', encoding='utf-8') as f:
        json.dump(list(pool_map.values()), f, ensure_ascii=False, indent=2)


@products_bp.route('/products/<store_id>/add', methods=['POST'])
def add_product(store_id):
    """Manual add a single product."""
    data = request.get_json(silent=True) or {}
    title_cn = data.get('title_cn', '').strip()
    price_cny = data.get('price_cny', '').strip()
    if not title_cn or not price_cny:
        return jsonify({'error': 'Vui lòng nhập tên sản phẩm (tiếng Trung) và giá CNY'}), 400
    try:
        price_cny = float(price_cny)
    except ValueError:
        return jsonify({'error': 'Giá CNY không hợp lệ'}), 400

    product = {
        'id': data.get('id', '').strip() or f'manual_{uuid.uuid4().hex[:12]}',
        'title_cn': title_cn,
        'title_en': data.get('title_en', '').strip(),
        'price_cny': price_cny,
        'original_price_cny': data.get('original_price_cny', '').strip() or price_cny,
        'image_urls': [u.strip() for u in data.get('image_urls', '').split(',') if u.strip()],
        'description_cn': data.get('description_cn', '').strip(),
        'category_name_cn': data.get('category_name_cn', '').strip(),
        'supplier_name': data.get('supplier_name', '').strip() or 'Manual',
        'supplier_rating': 0,
        'sales_count': 0,
        'detail_url': data.get('detail_url', '').strip(),
        'platform': data.get('platform', '').strip() or 'manual',
        'is_dropship': False,
    }

    data_dir = BASE_DIR / 'data' / store_id
    prod_path = data_dir / 'products.json'
    products = []
    if prod_path.exists():
        try:
            with open(prod_path, encoding='utf-8') as f:
                products = json.load(f)
        except Exception:
            pass
    products.append(product)
    _save_products(store_id, products)
    add_log(f'Đã thêm sản phẩm thủ công: {title_cn}')
    return jsonify({'status': 'ok', 'product': product})


@products_bp.route('/products/<store_id>/import', methods=['POST'])
def import_products(store_id):
    """Import products from CSV or JSON."""
    fmt = request.form.get('format', 'csv')
    total = 0
    new_products = []

    if fmt == 'json':
        raw = request.form.get('json_data', '').strip()
        if not raw:
            return jsonify({'error': 'Dán dữ liệu JSON vào'}), 400
        try:
            items = json.loads(raw)
        except json.JSONDecodeError:
            return jsonify({'error': 'JSON không hợp lệ'}), 400
        items = items if isinstance(items, list) else [items]
        for item in items:
            p = _normalize_imported(item)
            if p:
                new_products.append(p)
    else:
        file = request.files.get('file')
        if not file:
            return jsonify({'error': 'Chưa chọn file CSV'}), 400
        try:
            text = file.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            try:
                text = file.read().decode('utf-8')
            except Exception:
                return jsonify({'error': 'Không đọc được file, hãy dùng UTF-8'}), 400
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            p = _normalize_imported(row)
            if p:
                new_products.append(p)

    if not new_products:
        return jsonify({'error': 'Không tìm thấy sản phẩm hợp lệ trong dữ liệu'}), 400

    data_dir = BASE_DIR / 'data' / store_id
    prod_path = data_dir / 'products.json'
    products = []
    if prod_path.exists():
        try:
            with open(prod_path, encoding='utf-8') as f:
                products = json.load(f)
        except Exception:
            pass
    existing_ids = {p.get('id') for p in products}
    for p in new_products:
        if p['id'] not in existing_ids:
            products.append(p)
            existing_ids.add(p['id'])

    _save_products(store_id, products)
    add_log(f'Import {len(new_products)} sản phẩm vào {store_id}')
    return jsonify({'status': 'ok', 'count': len(new_products)})


FIELD_MAP = {
    'title': 'title_cn', 'tên': 'title_cn', 'name': 'title_cn', 'ten': 'title_cn',
    'title_cn': 'title_cn', 'title_en': 'title_en',
    'price': 'price_cny', 'giá': 'price_cny', 'price_cny': 'price_cny',
    'original_price': 'original_price_cny', 'original_price_cny': 'original_price_cny',
    'images': 'image_urls', 'image_urls': 'image_urls', 'image': 'image_urls',
    'description': 'description_cn', 'mô tả': 'description_cn', 'mo_ta': 'description_cn',
    'category': 'category_name_cn', 'danh mục': 'category_name_cn',
    'supplier': 'supplier_name', 'ncc': 'supplier_name',
    'url': 'detail_url', 'link': 'detail_url', 'detail_url': 'detail_url',
    'platform': 'platform', 'id': 'id',
}


def _normalize_imported(item: dict) -> dict | None:
    """Normalize a row (from CSV/JSON) into product dict with field aliases."""
    normalized = {}
    for k, v in item.items():
        k2 = FIELD_MAP.get(k.strip().lower(), k.strip().lower().replace(' ', '_'))
        if v is not None:
            normalized[k2] = v
    title_cn = str(normalized.get('title_cn', '') or normalized.get('title_en', '')).strip()
    price_cny = normalized.get('price_cny', '')
    if not title_cn or not price_cny:
        return None
    try:
        price_cny = float(price_cny)
    except (ValueError, TypeError):
        return None
    original_price = normalized.get('original_price_cny', '') or price_cny
    try:
        original_price = float(original_price)
    except (ValueError, TypeError):
        original_price = price_cny
    image_urls = normalized.get('image_urls', '')
    if isinstance(image_urls, str):
        image_urls = [u.strip() for u in image_urls.replace('\n', ',').split(',') if u.strip()]
    elif not isinstance(image_urls, list):
        image_urls = []
    return {
        'id': str(normalized.get('id', '')) or f'import_{uuid.uuid4().hex[:12]}',
        'title_cn': title_cn,
        'title_en': str(normalized.get('title_en', '')).strip(),
        'price_cny': price_cny,
        'original_price_cny': original_price,
        'image_urls': image_urls,
        'description_cn': str(normalized.get('description_cn', '')).strip(),
        'category_name_cn': str(normalized.get('category_name_cn', '')).strip(),
        'supplier_name': str(normalized.get('supplier_name', '')).strip() or 'Manual',
        'supplier_rating': 0,
        'sales_count': 0,
        'detail_url': str(normalized.get('detail_url', '')).strip(),
        'platform': str(normalized.get('platform', '')).strip() or 'manual',
        'is_dropship': False,
    }
