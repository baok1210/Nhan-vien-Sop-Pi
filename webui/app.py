import os
from flask import Flask
from webui.admin import AppAdmin
from webui.state import _ensure_dirs
from webui.views import dashboard_bp, stores_bp, products_bp, pipeline_bp, research_bp

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'change-me-in-production')

admin = AppAdmin(app)
admin.add_view(dashboard_bp, 'Dashboard', icon='home')
admin.add_view(stores_bp, 'Kho hàng', icon='store')
admin.add_view(products_bp, 'Sản phẩm', icon='list')
admin.add_view(pipeline_bp, 'Pipeline', icon='play')
admin.add_view(research_bp, 'Nghiên cứu', icon='search')

if __name__ == '__main__':
    _ensure_dirs()
    print('=' * 60)
    print('  WEB UI - China Dropship to Shopee')
    print('  Open browser: http://localhost:5000')
    print('=' * 60)
    app.run(host='127.0.0.1', port=5000, debug=False, threaded=True)
