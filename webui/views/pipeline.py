import json
import threading
from flask import Blueprint, jsonify, request

from webui.state import (
    _pipeline_lock, _get_scheduler, _scheduler_jobs, _schedule_run,
    set_pipeline_running, is_pipeline_running, add_log,
)
from webui.step_registry import get_step, get_func, check_prerequisites
from src.config_manager import load_store, save_store

pipeline_bp = Blueprint('pipeline', __name__)


@pipeline_bp.route('/run/<store_id>/<step>', methods=['POST'])
def run_step(store_id, step):
    func = get_func(step)
    if not func:
        return jsonify({'error': 'Bước không hợp lệ'}), 400

    ok, msgs = check_prerequisites(store_id, step)
    if not ok:
        add_log(f'⚠️ {"; ".join(msgs)}')
        return jsonify({'error': '; '.join(msgs)}), 400

    with _pipeline_lock:
        if is_pipeline_running():
            return jsonify({'error': 'Pipeline đang chạy, chờ đến khi xong'}), 400
        set_pipeline_running(True)

    config = load_store(store_id)
    if not config:
        with _pipeline_lock:
            set_pipeline_running(False)
        return jsonify({'error': 'Không tìm thấy store'}), 404

    if request.is_json:
        rp = request.get_json(silent=True) or {}
        if 'max_pages_1688' in rp:
            config.setdefault('sources', {}).setdefault('1688', {})['max_pages'] = int(rp['max_pages_1688'])
        if 'max_pages_aliexpress' in rp:
            config.setdefault('sources', {}).setdefault('aliexpress', {})['max_pages'] = int(rp['max_pages_aliexpress'])
        if 'proxy' in rp and rp['proxy']:
            config.setdefault('sources', {}).setdefault('1688', {})['proxy'] = rp['proxy']
            config.setdefault('sources', {}).setdefault('aliexpress', {})['proxy'] = rp['proxy']
        if 'cookies_1688' in rp and rp['cookies_1688']:
            try:
                config.setdefault('sources', {}).setdefault('1688', {})['cookies'] = json.loads(rp['cookies_1688'])
            except:
                pass
        if 'cookies_ae' in rp and rp['cookies_ae']:
            try:
                config.setdefault('sources', {}).setdefault('aliexpress', {})['cookies'] = json.loads(rp['cookies_ae'])
            except:
                pass
        if 'delay_min' in rp:
            config.setdefault('sources', {}).setdefault('1688', {})['delay_seconds'] = int(rp['delay_min'])
            config.setdefault('sources', {}).setdefault('aliexpress', {})['delay_seconds'] = int(rp['delay_min'])
        if 'delay_max' in rp:
            config.setdefault('sources', {}).setdefault('1688', {})['delay_max'] = int(rp['delay_max'])
            config.setdefault('sources', {}).setdefault('aliexpress', {})['delay_max'] = int(rp['delay_max'])
        if 'max_retries' in rp:
            config['max_retries'] = int(rp['max_retries'])
        if 'quality' in rp:
            config.setdefault('image_processing', {})['quality'] = int(rp['quality'])
        if 'bg_removal' in rp:
            config.setdefault('image_processing', {})['bg_removal'] = rp['bg_removal']
        if 'enhance' in rp:
            config.setdefault('image_processing', {})['enhance'] = rp['enhance']
        if 'watermark' in rp:
            config.setdefault('image_processing', {})['watermark'] = rp['watermark']
        if 'item_status' in rp:
            config.setdefault('shopee', {})['item_status'] = rp['item_status']
        if 'pre_order_days' in rp:
            config.setdefault('shopee', {})['pre_order_days'] = int(rp['pre_order_days'])
        if 'volume' in rp:
            config.setdefault('video_processing', {})['volume'] = float(rp['volume'])
        if 'max_videos' in rp:
            config.setdefault('video_processing', {})['max_videos'] = int(rp['max_videos'])
        if 'days_back' in rp:
            config['days_back'] = int(rp['days_back'])
        if 'max_items' in rp:
            config['max_items'] = int(rp['max_items'])
        if 'ai_provider' in rp:
            config.setdefault('ai', {}).setdefault('caption', {})['provider'] = rp['ai_provider']
        if 'ai_api_key' in rp and rp['ai_api_key']:
            config.setdefault('ai', {}).setdefault('caption', {})['api_key'] = rp['ai_api_key']
        if 'ai_model' in rp and rp['ai_model']:
            config.setdefault('ai', {}).setdefault('caption', {})['model'] = rp['ai_model']
        if 'ai_language' in rp and rp['ai_language']:
            config.setdefault('ai', {}).setdefault('caption', {})['language'] = rp['ai_language']
        if 'ai_tone' in rp:
            config.setdefault('ai', {}).setdefault('caption', {})['tone'] = rp['ai_tone']
        if 'ai_max_title' in rp:
            config.setdefault('ai', {}).setdefault('caption', {})['max_title_length'] = int(rp['ai_max_title'])
        if 'ai_num_hashtags' in rp:
            config.setdefault('ai', {}).setdefault('caption', {})['num_hashtags'] = int(rp['ai_num_hashtags'])
    save_store(store_id, config)

    t = threading.Thread(target=func, args=(store_id, config), daemon=True)
    t.start()
    return jsonify({'status': 'started'})


@pipeline_bp.route('/schedule/<store_id>', methods=['POST'])
def set_schedule(store_id):
    data = request.get_json(silent=True) or {}
    interval_hours = data.get('interval_hours', 24)
    step = data.get('step', 'crawl')
    enabled = data.get('enabled', False)
    sched = _get_scheduler()
    if not sched:
        return jsonify({'error': 'APScheduler not installed. Run: pip install apscheduler'}), 400
    job_id = f'{store_id}_{step}'
    if job_id in _scheduler_jobs:
        try:
            sched.remove_job(job_id)
        except Exception:
            pass
        del _scheduler_jobs[job_id]
    if enabled:
        sched.add_job(
            _schedule_run,
            'interval',
            hours=interval_hours,
            args=[store_id, step],
            id=job_id,
            name=f'{store_id}/{step}',
            replace_existing=True,
        )
        _scheduler_jobs[job_id] = step
        add_log(f'Đã lên lịch: {store_id}/{step} mỗi {interval_hours}h')
    return jsonify({
        'status': 'scheduled' if enabled else 'unscheduled',
        'job_id': job_id,
        'enabled': enabled,
        'interval_hours': interval_hours,
    })


@pipeline_bp.route('/schedule/<store_id>', methods=['GET'])
def get_schedule(store_id):
    sched = _get_scheduler()
    jobs = []
    if sched:
        for job in sched.get_jobs():
            if job.name.startswith(f'{store_id}/'):
                next_run = job.next_run_time.isoformat() if job.next_run_time else None
                jobs.append({
                    'id': job.id,
                    'name': job.name,
                    'next_run': next_run,
                    'interval': str(job.trigger.interval) if hasattr(job.trigger, 'interval') else '',
                })
    return jsonify({'jobs': jobs})


@pipeline_bp.route('/schedules', methods=['GET'])
def list_schedules():
    sched = _get_scheduler()
    jobs = []
    if sched:
        for job in sched.get_jobs():
            next_run = job.next_run_time.isoformat() if job.next_run_time else None
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run': next_run,
            })
    return jsonify({'jobs': jobs})
