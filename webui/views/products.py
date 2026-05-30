import json
from flask import Blueprint, render_template
from webui.state import BASE_DIR

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
    return render_template('products.html', store_id=store_id, products=products[:50])
