import json
from flask import Blueprint, render_template, jsonify, request

from webui.state import BASE_DIR
from src.config_manager import load_store, save_store, delete_store, create_store

stores_bp = Blueprint('stores', __name__)


@stores_bp.route('/store/new', methods=['GET', 'POST'])
def new_store():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        store_id = request.form.get('store_id', '').strip()
        if not store_id:
            store_id = name.lower().replace(' ', '-').replace('\u0111', 'd')
            store_id = ''.join(c for c in store_id if c.isalnum() or c in '-')
        if not name:
            return jsonify({'error': 'Vui lòng nhập tên store'}), 400
        create_store(store_id, name)
        data = load_store(store_id)
        if data:
            niche = data.setdefault('niche', {})
            kw_vn = request.form.get('kw_vn', '').strip()
            kw_cn = request.form.get('kw_cn', '').strip()
            kw_en = request.form.get('kw_en', '').strip()
            if kw_vn:
                niche['keywords_vn'] = [k.strip() for k in kw_vn.split(',') if k.strip()]
            if kw_cn:
                niche['keywords_cn'] = [k.strip() for k in kw_cn.split(',') if k.strip()]
            if kw_en:
                niche['keywords_en'] = [k.strip() for k in kw_en.split(',') if k.strip()]
            for num_field in ['price_multiplier', 'max_price_cny', 'min_margin_percent']:
                val = request.form.get(num_field, '').strip()
                if val:
                    try:
                        niche[num_field] = float(val) if '.' in val else int(val)
                    except ValueError:
                        pass
            img_proc = data.setdefault('image_processing', {})
            ad = img_proc.setdefault('anti_duplication', {})
            wm = ad.setdefault('watermark', {})
            wm_text = request.form.get('wm_text', '').strip()
            if wm_text:
                wm['text'] = wm_text
            wm_img = request.form.get('wm_image_path', '').strip()
            if wm_img:
                wm['image_path'] = wm_img
            wm['use_store_name'] = request.form.get('wm_use_store_name') == 'on'
            save_store(store_id, data)
        return jsonify({'status': 'ok', 'store_id': store_id})
    return render_template('store_form.html')


@stores_bp.route('/store/<store_id>/edit', methods=['GET', 'POST'])
def edit_store(store_id):
    data = load_store(store_id)
    if not data:
        return jsonify({'error': 'Store not found'}), 404
    if request.method == 'POST':
        niche = data.setdefault('niche', {})
        niche['keywords_cn'] = [k.strip() for k in request.form.get('kw_cn', '').split(',') if k.strip()]
        niche['keywords_en'] = [k.strip() for k in request.form.get('kw_en', '').split(',') if k.strip()]
        niche['keywords_vn'] = [k.strip() for k in request.form.get('kw_vn', '').split(',') if k.strip()]
        try:
            niche['category_shopee_id'] = int(request.form.get('cat_id', 0))
        except ValueError:
            pass
        for num_field in ['price_multiplier', 'max_price_cny', 'min_margin_percent']:
            val = request.form.get(num_field, '').strip()
            if val:
                try:
                    niche[num_field] = float(val) if '.' in val else int(val)
                except ValueError:
                    pass
        shopee = data.setdefault('shopee', {})
        shopee['partner_id'] = request.form.get('partner_id', '')
        shopee['partner_key'] = request.form.get('partner_key', '')
        shopee['shop_id'] = request.form.get('shop_id', '')
        shopee['access_token'] = request.form.get('access_token', '')
        shopee['refresh_token'] = request.form.get('refresh_token', '')
        shopee['environment'] = request.form.get('env', 'uat')
        sources = data.setdefault('sources', {})
        sources.setdefault('1688', {})['enabled'] = request.form.get('src_1688') == 'on'
        sources.setdefault('aliexpress', {})['enabled'] = request.form.get('src_ae') == 'on'
        for src_key in ['1688', 'aliexpress']:
            mp = request.form.get(f'max_pages_{src_key}' if src_key == '1688' else 'max_pages_ae', '').strip()
            if mp:
                try:
                    sources.setdefault(src_key, {})['max_pages'] = int(mp)
                except ValueError:
                    pass
        proxy_val = request.form.get('proxy', '').strip()
        if proxy_val:
            for src_key in ['1688', 'aliexpress']:
                sources.setdefault(src_key, {})['proxy'] = proxy_val
        ck = request.form.get('cookies_1688', '').strip()
        if ck:
            try:
                sources.setdefault('1688', {})['cookies'] = json.loads(ck)
            except:
                pass
        ck_ae = request.form.get('cookies_ae', '').strip()
        if ck_ae:
            try:
                sources.setdefault('aliexpress', {})['cookies'] = json.loads(ck_ae)
            except:
                pass
        img_proc = data.setdefault('image_processing', {})
        ad = img_proc.setdefault('anti_duplication', {})
        wm = ad.setdefault('watermark', {})
        wm['text'] = request.form.get('wm_text', '')
        wm['image_path'] = request.form.get('wm_image_path', '')
        try:
            wm['opacity'] = int(request.form.get('wm_opacity', 80))
        except ValueError:
            pass
        wm['enabled'] = request.form.get('wm_enabled') == 'on'
        wm['use_store_name'] = request.form.get('wm_use_store_name') == 'on'
        ai_cap = data.setdefault('ai', {}).setdefault('caption', {})
        ai_cap['provider'] = request.form.get('ai_provider', '')
        ai_cap['api_key'] = request.form.get('ai_api_key', '')
        ai_cap['model'] = request.form.get('ai_model', 'gemini-flash-latest')
        ai_cap['language'] = request.form.get('ai_language', 'vi')
        ai_cap['tone'] = request.form.get('ai_tone', 'professional')
        try:
            ai_cap['max_title_length'] = int(request.form.get('ai_max_title', 120))
        except ValueError:
            pass
        try:
            ai_cap['num_hashtags'] = int(request.form.get('ai_num_hashtags', 10))
        except ValueError:
            pass
        save_store(store_id, data)
        return jsonify({'status': 'saved'})
    return render_template('store_edit.html', store_id=store_id, data=data)


@stores_bp.route('/store/<store_id>/delete', methods=['POST'])
def remove_store(store_id):
    import shutil
    delete_store(store_id)
    data_dir = BASE_DIR / 'data' / store_id
    if data_dir.exists():
        shutil.rmtree(str(data_dir))
    return jsonify({'status': 'deleted'})
