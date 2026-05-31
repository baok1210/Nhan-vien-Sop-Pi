import json, os
from flask import Blueprint, render_template, jsonify, request
from pathlib import Path

from webui.state import BASE_DIR, pipeline_log, pipeline_running, add_log, _dict_translate
from webui.step_registry import list_steps, check_prerequisites, get_step
from src.config_manager import list_stores, load_store

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
def index():
    stores = list_stores()
    all_step_meta = list_steps()
    store_data = []
    for sid in stores:
        if sid == 'example':
            continue
        data = load_store(sid) or {}
        product_count = 0
        for fname in ['captions.json', 'products_with_images.json', 'products.json']:
            p = BASE_DIR / 'data' / sid / fname
            if p.exists():
                try:
                    with open(p, encoding='utf-8') as f:
                        product_count = len(json.load(f))
                except:
                    pass
                break
        step_states = {}
        for step in all_step_meta:
            ok, _ = check_prerequisites(sid, step['name'])
            step_states[step['name']] = ok
        wm_cfg = data.get('image_processing', {}).get('anti_duplication', {}).get('watermark', {})
        store_data.append({
            'id': sid,
            'name': data.get('name', sid),
            'product_count': product_count,
            'step_states': step_states,
            'crawl_max_pages_1688': data.get('sources', {}).get('1688', {}).get('max_pages', 3),
            'crawl_proxies': '\n'.join(data.get('sources', {}).get('1688', {}).get('proxies', []) or []),
            'watermark_text': wm_cfg.get('text', ''),
            'watermark_use_shop_name': wm_cfg.get('use_store_name', True),
            'ai_provider': data.get('ai', {}).get('caption', {}).get('provider', ''),
            'ai_api_key': data.get('ai', {}).get('caption', {}).get('api_key', ''),
            'ai_model': data.get('ai', {}).get('caption', {}).get('model', 'gemini-flash-latest'),
            'ai_language': data.get('ai', {}).get('caption', {}).get('language', 'vi'),
            'ai_tone': data.get('ai', {}).get('caption', {}).get('tone', 'professional'),
            'ai_max_title': data.get('ai', {}).get('caption', {}).get('max_title_length', 120),
            'ai_num_hashtags': data.get('ai', {}).get('caption', {}).get('num_hashtags', 10),
        })
    step_meta_json = json.dumps(list_steps(serializable=True), ensure_ascii=False)
    return render_template('index.html', stores=store_data, running=pipeline_running,
                           all_step_meta=all_step_meta, step_meta_json=step_meta_json)


@dashboard_bp.route('/log')
def get_log():
    return jsonify({'log': pipeline_log[-100:], 'running': pipeline_running})


@dashboard_bp.route('/translate', methods=['POST'])
def translate_keywords():
    text = request.json.get('text', '').strip()
    if not text:
        return jsonify({'error': 'Nhập từ khóa tiếng Việt'}), 400
    dict_cn, dict_en = _dict_translate(text)
    if dict_cn and dict_en:
        return jsonify({'cn': dict_cn, 'en': dict_en})
    try:
        import asyncio
        from googletrans import Translator as GTranslator

        async def do_translate():
            t = GTranslator()
            r_cn = await t.translate(text, dest='zh-cn')
            r_en = await t.translate(text, dest='en')
            return (r_cn.text if r_cn and r_cn.text else text,
                    r_en.text if r_en and r_en.text else text)
        cn, en = asyncio.run(do_translate())
        return jsonify({'cn': cn, 'en': en, 'source': 'google'})
    except Exception as e:
        add_log(f'LỖI dịch google: {e}')
        return jsonify({'cn': text, 'en': text, 'source': 'original'})


@dashboard_bp.route('/steps/<store_id>')
def steps_status(store_id):
    """Return step metadata + prereq check for each step in this store."""
    result = []
    for step in list_steps(serializable=True):
        ok, msgs = check_prerequisites(store_id, step['name'])
        result.append({**step, 'prereqs_ok': ok, 'prereq_messages': msgs})
    return jsonify(result)
