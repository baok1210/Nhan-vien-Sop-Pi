"""Shared pipeline state, translation dictionaries, and background thread functions."""
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

import json, threading, time, asyncio, random, os
from datetime import datetime, timedelta

from webui.step_registry import step_register

from src.source.aliexpress import AliExpressScraper
from src.source.ali1688 import Ali1688Scraper
from src.processing.image_processor import ImageProcessor
from src.processing.video_processor import VideoProcessor
from src.ai.caption_gen import CaptionGenerator
from src.publisher.shopee import ShopeeClient
from src.utils.exchange_rate import calculate_final_price, async_calculate_final_price
from src.pricing.competitor import async_analyze_store_pricing
from src.publisher.order_manager import OrderManager
from src.publisher.flash_sale import FlashSaleManager
from src.publisher.cashflow_planner import CashFlowPlanner
from src.trends.trend_hijacker import TrendDetector
from src.publisher.virtual_hub import VirtualHub
from src.publisher.customer_care import CustomerCareBot

pipeline_log: list[str] = []
pipeline_running = False
_pipeline_lock = threading.Lock()
_scheduler = None
_scheduler_jobs: dict[str, str] = {}


def is_pipeline_running() -> bool:
    return pipeline_running


def set_pipeline_running(val: bool):
    global pipeline_running
    pipeline_running = val


def add_log(msg):
    ts = time.strftime('%H:%M:%S')
    with _pipeline_lock:
        pipeline_log.append(f'[{ts}] {msg}')
        if len(pipeline_log) > 500:
            pipeline_log[:100] = []


def _get_scheduler():
    global _scheduler
    if _scheduler is None:
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            _scheduler = BackgroundScheduler(daemon=True)
            _scheduler.start()
        except ImportError:
            pass
    return _scheduler


def _schedule_run(store_id: str, step: str):
    from src.config_manager import load_store
    from webui.step_registry import get_func
    config = load_store(store_id)
    if not config:
        return
    func = get_func(step)
    if func:
        func(store_id, config)


def _dict_translate(text):
    text_lower = text.lower().strip()
    if text_lower in _VN_CN_DICT:
        return (_VN_CN_DICT[text_lower], _VN_EN_DICT.get(text_lower, text_lower))
    parts = [p.strip() for p in text_lower.split(',') if p.strip()]
    if len(parts) > 1:
        cn_parts = [_VN_CN_DICT.get(p, p) for p in parts]
        en_parts = [_VN_EN_DICT.get(p, p) for p in parts]
        return (', '.join(cn_parts), ', '.join(en_parts))
    return ('', '')


@step_register(
    name='crawl', label='1. Crawl sản phẩm',
    desc='Tự động tìm kiếm sản phẩm từ AliExpress (từ khóa Anh) và 1688 (từ khóa Trung). Nếu bị chặn, thử tăng delay hoặc dùng proxy.',
    icon='🔍', category='pipeline', order=1,
    assigns_files=['products.json', 'product_pool.json'],
)
def run_crawl_thread(store_id, config):
    global pipeline_running
    try:
        add_log(f'Bắt đầu crawl store: {store_id}')
        all_products = []
        ae_cfg = config.get('sources', {}).get('aliexpress', {})
        if ae_cfg.get('enabled'):
            keywords = config.get('niche', {}).get('keywords_en', [])
            add_log(f'  AliExpress: {ae_cfg}')
            add_log(f'  Từ khóa EN: {keywords}')
            if keywords:
                add_log(f'  Đang crawl AliExpress ({len(keywords)} từ khóa)...')
                max_retries = config.get('max_retries', 3)
                scraper = AliExpressScraper(ae_cfg)
                try:
                    for kw in keywords:
                        add_log(f'    Tìm: "{kw}"...')
                        for page in range(1, ae_cfg.get('max_pages', 3) + 1):
                            ok = False
                            for attempt in range(1, max_retries + 1):
                                try:
                                    if attempt > 1:
                                        delay = attempt * random.uniform(5, 10)
                                        add_log(f'    Retry {attempt}/{max_retries} sau {delay:.0f}s...')
                                        time.sleep(delay)
                                    products = scraper.search(kw, page)
                                    if products:
                                        count = len(products)
                                        all_products.extend(products)
                                        add_log(f'    Trang {page}: +{count} sp')
                                        ok = True
                                        break
                                    else:
                                        add_log(f'    Trang {page}: 0 sp (attempt {attempt})')
                                        if attempt < max_retries:
                                            continue
                                except Exception as e:
                                    add_log(f'    LỖI attempt {attempt}: {e}')
                                    if attempt < max_retries:
                                        continue
                            if not ok:
                                add_log(f'    Dừng "{kw}" sau {max_retries} lần thử')
                                break
                finally:
                    scraper.close()
                add_log(f'  AliExpress tổng: {len(all_products)} sp')
            else:
                add_log(f'  Bỏ qua AliExpress: không có từ khóa EN')
        c8_cfg = config.get('sources', {}).get('1688', {})
        if c8_cfg.get('enabled'):
            keywords = config.get('niche', {}).get('keywords_cn', [])
            add_log(f'  1688: {c8_cfg}')
            add_log(f'  Từ khóa CN: {keywords}')
            if keywords:
                add_log(f'  Đang crawl 1688 ({len(keywords)} từ khóa)...')
                max_retries = config.get('max_retries', 3)
                scraper = Ali1688Scraper(c8_cfg)
                try:
                    for kw in keywords:
                        add_log(f'    Tìm: "{kw}"...')
                        for attempt in range(1, max_retries + 1):
                            try:
                                products = scraper.crawl_by_keywords([kw])
                                if products:
                                    all_products.extend(products)
                                    add_log(f'    +{len(products)} sp')
                                    break
                                else:
                                    if attempt < max_retries:
                                        delay = attempt * 5
                                        add_log(f'    Retry {attempt}/{max_retries} sau {delay}s...')
                                        time.sleep(delay)
                                    else:
                                        add_log(f'    0 sp (cần cookie? 1688 thường chặn nếu chưa đăng nhập)')
                            except Exception as e:
                                add_log(f'    LỖI: {e}')
                                if attempt < max_retries:
                                    time.sleep(5)
                finally:
                    scraper.close()
                add_log(f'  1688 tổng: {len(all_products)} sp')
            else:
                add_log(f'  Bỏ qua 1688: không có từ khóa CN')
        if all_products:
            out = []
            for p in all_products:
                out.append({
                    'id': p.id, 'title_cn': p.title_cn, 'price_cny': p.price_cny,
                    'original_price_cny': p.original_price_cny, 'image_urls': p.image_urls,
                    'description_cn': p.description_cn[:500] if p.description_cn else '',
                    'category_name_cn': p.category_name_cn, 'supplier_name': p.supplier_name,
                    'supplier_rating': p.supplier_rating, 'sales_count': p.sales_count,
                    'detail_url': p.detail_url, 'platform': p.platform, 'is_dropship': p.is_dropship,
                })
            data_dir = BASE_DIR / 'data' / store_id
            data_dir.mkdir(parents=True, exist_ok=True)
            with open(data_dir / 'products.json', 'w', encoding='utf-8') as f:
                json.dump(out, f, ensure_ascii=False, indent=2)
            pool_path = BASE_DIR / 'data' / 'product_pool.json'
            existing = []
            if pool_path.exists():
                try:
                    with open(pool_path, encoding='utf-8') as f:
                        existing = json.load(f)
                except:
                    pass
            pool_map = {p.get('id', ''): p for p in existing if isinstance(p, dict)}
            for p in out:
                pid = p.get('id', '')
                if pid and pid in pool_map:
                    pool_map[pid].update(p)
                elif pid:
                    pool_map[pid] = p
            with open(pool_path, 'w', encoding='utf-8') as f:
                json.dump(list(pool_map.values()), f, ensure_ascii=False, indent=2)
            add_log(f'Hoàn thành! {len(out)} sp -> data/{store_id}/products.json + product_pool.json')
        else:
            add_log('Không lấy được sản phẩm nào')
            add_log('  Nguyên nhân có thể:')
            add_log('  - AliExpress chặn anti-bot (x5sec/captcha)')
            add_log('  - 1688 yêu cầu cookie đăng nhập')
            add_log('  - Từ khóa không đúng hoặc không có kết quả')
            add_log('  - Proxy/network bị chặn')
            add_log('  Vào phần Sửa store để kiểm tra từ khóa và nguồn hàng')
    except Exception as e:
        add_log(f'LỖI crawl: {e}')
        import traceback
        add_log(f'  Chi tiết: {traceback.format_exc()[:500]}')
    finally:
        with _pipeline_lock:
            pipeline_running = False


@step_register(
    name='images', label='2. Xử lý ảnh',
    desc='Tải ảnh về, xóa nền, resize, thêm watermark.',
    icon='🖼️', category='pipeline', order=2,
    requires_files=['products.json'],
    assigns_files=['products_with_images.json'],
)
def run_images_thread(store_id, config):
    global pipeline_running
    try:
        data_dir = BASE_DIR / 'data' / store_id
        prod_path = data_dir / 'products.json'
        if not prod_path.exists():
            add_log('Không tìm thấy products.json, chạy crawl trước')
            return
        with open(prod_path, encoding='utf-8') as f:
            products = json.load(f)
        add_log(f'Xử lý ảnh cho {len(products)} sp...')
        processor = ImageProcessor(config)
        raw_dir = str(data_dir / 'images' / 'raw')
        proc_dir = str(data_dir / 'images' / 'processed')
        ok = 0
        for i, prod in enumerate(products, 1):
            pid = prod.get('id', f'p{i}')
            urls = prod.get('image_urls', [])
            if not urls:
                continue
            saved = processor.download_images(urls, raw_dir, pid)
            if saved:
                out_dir = f'{proc_dir}/{pid}'
                results = processor.process_batch(saved, out_dir)
                prod['images_local'] = saved
                prod['images_processed'] = results
                prod['image_count'] = len(results)
                ok += 1
        with open(data_dir / 'products_with_images.json', 'w', encoding='utf-8') as f:
            json.dump(products, f, ensure_ascii=False, indent=2)
        add_log(f'Xong! {ok}/{len(products)} sp đã xử lý ảnh')
    except Exception as e:
        add_log(f'LỖI xử lý ảnh: {e}')
    finally:
        with _pipeline_lock:
            pipeline_running = False


@step_register(
    name='caption', label='4. Tạo caption',
    desc='Sinh tiêu đề, mô tả, bullet points và hashtag. Dùng AI (Gemini/OpenAI) nếu có API key.',
    icon='✍️', category='pipeline', order=4,
    requires_files_any=['products_with_images.json', 'products.json'],
    assigns_files=['captions.json'],
)
def run_caption_thread(store_id, config):
    global pipeline_running
    try:
        data_dir = BASE_DIR / 'data' / store_id
        prod_path = data_dir / 'products_with_images.json'
        if not prod_path.exists():
            prod_path = data_dir / 'products.json'
        if not prod_path.exists():
            add_log('Không tìm thấy sản phẩm')
            return
        with open(prod_path, encoding='utf-8') as f:
            products = json.load(f)
        from src.ai.caption_gen import CachedCaptionGenerator
        gen = CachedCaptionGenerator(CaptionGenerator(config))
        niche = config.get('niche', {})
        niche_name = niche.get('keywords_vn', [store_id])[0]
        multiplier = niche.get('price_multiplier', 2.5)
        captions = []
        add_log(f'Tạo caption cho {len(products)} sp...')
        for i, prod in enumerate(products, 1):
            price_cny = prod.get('price_cny', 0)
            price_vnd = calculate_final_price(price_cny, multiplier)
            caption = gen.generate(prod.get('title_cn', ''), niche_name, price_cny, prod.get('description_cn', ''), price_vnd)
            entry = {
                'product_id': prod.get('id'), 'title_cn': prod.get('title_cn', ''),
                'price_cny': price_cny, 'price_vnd': int(price_vnd),
                'images_processed': prod.get('images_processed', []), 'image_ids': [],
                **caption,
            }
            captions.append(entry)
        with open(data_dir / 'captions.json', 'w', encoding='utf-8') as f:
            json.dump(captions, f, ensure_ascii=False, indent=2)
        add_log(f'Xong! {len(captions)} caption đã tạo')
    except Exception as e:
        add_log(f'LỖI tạo caption: {e}')
    finally:
        with _pipeline_lock:
            pipeline_running = False


@step_register(
    name='video', label='3. Tạo video',
    desc='Tải video và ghép nhạc nền.',
    icon='🎬', category='pipeline', order=3,
    requires_files_any=['products_with_images.json', 'products.json'],
)
def run_video_thread(store_id, config):
    global pipeline_running
    try:
        data_dir = BASE_DIR / 'data' / store_id
        prod_path = data_dir / 'products_with_images.json'
        if not prod_path.exists():
            prod_path = data_dir / 'products.json'
        if not prod_path.exists():
            add_log('Không tìm thấy sản phẩm, chạy crawl trước')
            return
        with open(prod_path, encoding='utf-8') as f:
            products = json.load(f)
        processor = VideoProcessor(config)
        raw_dir = str(data_dir / 'videos' / 'raw')
        proc_dir = str(data_dir / 'videos' / 'processed')
        Path(raw_dir).mkdir(parents=True, exist_ok=True)
        Path(proc_dir).mkdir(parents=True, exist_ok=True)
        add_log(f'Xử lý video cho {len(products)} sp...')
        ok = 0
        for i, prod in enumerate(products, 1):
            vid_url = prod.get('video_url', '')
            if not vid_url:
                continue
            pid = prod.get('id', f'p{i}')
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            dl_path = loop.run_until_complete(processor.download_video(vid_url, raw_dir, pid))
            if dl_path:
                out = processor.process_single(dl_path, proc_dir)
                if out:
                    prod['video_processed'] = out
                    ok += 1
            loop.close()
        with open(data_dir / 'products_with_images.json', 'w', encoding='utf-8') as f:
            json.dump(products, f, ensure_ascii=False, indent=2)
        add_log(f'Xong! {ok} video đã xử lý')
    except Exception as e:
        add_log(f'LỖI xử lý video: {e}')
    finally:
        with _pipeline_lock:
            pipeline_running = False


@step_register(
    name='publish', label='5. Đăng Shopee',
    desc='Đăng sản phẩm lên Shopee qua API.',
    icon='📦', category='pipeline', order=5,
    requires_files=['captions.json'],
    assigns_files=['published.json'],
    requires_shopee=True,
)
def run_publish_thread(store_id, config):
    global pipeline_running
    try:
        shopee_cfg = config.get('shopee', {})
        if not shopee_cfg.get('partner_id') or not shopee_cfg.get('partner_key'):
            add_log('Chưa cấu hình Shopee API. Bỏ qua đăng bài.')
            return
        data_dir = BASE_DIR / 'data' / store_id
        cap_path = data_dir / 'captions.json'
        if not cap_path.exists():
            add_log('Chưa có caption, chạy Generate Caption trước')
            return
        with open(cap_path, encoding='utf-8') as f:
            captions = json.load(f)
        from src.models.product import ProductSource, ProductProcessed, ShopeeProduct
        client = ShopeeClient(config)
        ok = 0
        add_log(f'Đăng lên Shopee {len(captions)} sp...')
        for i, cap in enumerate(captions, 1):
            image_ids = []
            for img_path in cap.get('images_processed', [])[:9]:
                if Path(img_path).exists():
                    iid = client.upload_image(img_path)
                    if iid:
                        image_ids.append(iid)
            src = ProductSource(
                id=cap.get('product_id', ''),
                title_cn=cap.get('title_cn', ''),
                price_cny=cap.get('price_cny', 0),
                original_price_cny=cap.get('price_cny', 0),
                image_urls=[],
                description_cn='',
                category_name_cn='',
                supplier_name='',
                detail_url='',
                platform='manual',
                is_dropship=True,
            )
            pp = ProductProcessed(source=src, images_processed=image_ids, title_vi=cap.get('title_vi', ''), description_vi=cap.get('description', ''), bullet_points=cap.get('bullet_points', []), hashtags=cap.get('hashtags', []), price_vnd=cap.get('price_vnd', 0))
            sp = ShopeeProduct(product=pp, image_ids=image_ids, category_id=config.get('niche', {}).get('category_shopee_id', 0))
            item_id = client.add_item(sp)
            if item_id:
                ok += 1
                cap['shopee_item_id'] = item_id
                cap['published_at'] = datetime.now().isoformat()
        pub_path = data_dir / 'published.json'
        published = []
        for cap in captions:
            if cap.get('shopee_item_id'):
                published.append({
                    'product_id': cap.get('product_id', ''),
                    'shopee_item_id': cap.get('shopee_item_id'),
                    'title_vi': cap.get('title_vi', ''),
                    'title_cn': cap.get('title_cn', ''),
                    'detail_url': cap.get('detail_url', ''),
                    'images_processed': cap.get('images_processed', []),
                    'published_at': cap.get('published_at', ''),
                })
        if published:
            with open(pub_path, 'w', encoding='utf-8') as f:
                json.dump(published, f, ensure_ascii=False, indent=2)
        client.close()
        add_log(f'Xong! {ok}/{len(captions)} sp đã đăng')
    except Exception as e:
        add_log(f'LỖI đăng Shopee: {e}')
    finally:
        with _pipeline_lock:
            pipeline_running = False


@step_register(
    name='pricing', label='Phân tích giá',
    desc='So sánh giá với đối thủ, tính lợi nhuận.',
    icon='💰', category='operations', order=1,
    requires_files=['captions.json'],
    assigns_files=['pricing_report.json'],
)
def run_pricing_thread(store_id, config):
    global pipeline_running
    try:
        caps_path = BASE_DIR / 'data' / store_id / 'captions.json'
        if not caps_path.exists():
            add_log('⚠️ Cần chạy bước Caption trước (tạo captions.json)')
            with _pipeline_lock:
                pipeline_running = False; return
        add_log(f'Phân tích giá của store: {store_id}')
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        report = loop.run_until_complete(async_analyze_store_pricing(store_id))
        loop.close()
        total = report.get('total', 0)
        profitable = report.get('profitable', 0)
        add_log(f'Xong! {profitable}/{total} sp có lợi nhuận. Xem báo cáo tại store edit.')
    except Exception as e:
        add_log(f'LỖI phân tích giá: {e}')
    finally:
        with _pipeline_lock:
            pipeline_running = False


@step_register(
    name='orders', label='Đồng bộ đơn hàng',
    desc='Kéo đơn từ Shopee về, xuất kho tự động.',
    icon='📋', category='operations', order=2,
    requires_shopee=True,
)
def run_orders_thread(store_id, config):
    global pipeline_running
    try:
        s = config.get('shopee', {})
        if not (s.get('partner_id') and s.get('partner_key') and s.get('shop_id')):
            add_log('⚠️ Cần cấu hình Shopee API (Partner ID, Key, Shop ID) trong phần Sửa store trước khi đồng bộ đơn')
            with _pipeline_lock:
                pipeline_running = False; return
        mgr = OrderManager(config, store_id)
        days_back = config.get('days_back', 7)
        add_log(f'Đồng bộ đơn hàng Shopee ({days_back} ngày)...')
        count = mgr.sync(days_back=days_back)
        mgr.close()
        add_log(f'Xong! {count} đơn xuất kho')
    except Exception as e:
        add_log(f'LỖI đồng bộ đơn: {e}')
    finally:
        with _pipeline_lock:
            pipeline_running = False


@step_register(
    name='flashsale', label='Flash sale',
    desc='Tạo chiến dịch flash sale tự động.',
    icon='⚡', category='marketing', order=1,
    requires_files=['pricing_report.json'],
    requires_shopee=True,
)
def run_flashsale_thread(store_id, config):
    global pipeline_running
    try:
        s = config.get('shopee', {})
        if not (s.get('partner_id') and s.get('partner_key') and s.get('shop_id')):
            add_log('⚠️ Cần cấu hình Shopee API (Partner ID, Key, Shop ID) trong phần Sửa store trước khi tạo flash sale')
            with _pipeline_lock:
                pipeline_running = False; return
        report_path = BASE_DIR / 'data' / store_id / 'pricing_report.json'
        if not report_path.exists():
            add_log('⚠️ Cần chạy Phân tích giá trước (tạo pricing_report.json)')
            with _pipeline_lock:
                pipeline_running = False; return
        mgr = FlashSaleManager(config, store_id)
        max_items = config.get('max_items', 20)
        add_log(f'Chạy flash sale (tối đa {max_items} sp)...')
        results = mgr.run(max_items=max_items)
        mgr.close()
        add_log(f'Xong! {len(results)} sp được tạo campaign')
    except Exception as e:
        add_log(f'LỖI flash sale: {e}')
    finally:
        with _pipeline_lock:
            pipeline_running = False


@step_register(
    name='cashflow', label='Dòng tiền',
    desc='Phân tích dòng tiền và vốn lưu động.',
    icon='💵', category='operations', order=3,
)
def run_cashflow_thread(store_id, config):
    global pipeline_running
    try:
        fulfill_path = BASE_DIR / 'data' / 'orders_to_fulfill.json'
        if not fulfill_path.exists():
            add_log('⚠️ Chưa có đơn hàng để phân tích. Cần đồng bộ đơn Shopee (bước Đơn hàng) trước.')
            with _pipeline_lock:
                pipeline_running = False; return
        planner = CashFlowPlanner(config, store_id)
        add_log('Phân tích dòng tiền...')
        report = planner.run()
        add_log(f'Xong! Lợi nhuận ước tính: {report.get("summary", {}).get("estimated_profit_vnd", 0):,.0f} VND')
    except Exception as e:
        add_log(f'LỖI phân tích dòng tiền: {e}')
    finally:
        with _pipeline_lock:
            pipeline_running = False


@step_register(
    name='trends', label='Quét trend',
    desc='Phát hiện từ khóa hot và spike dựa trên dữ liệu lịch sử.',
    icon='📈', category='marketing', order=2,
)
def run_trends_thread(store_id, config):
    global pipeline_running
    try:
        detector = TrendDetector(config)
        add_log('Quét trend...')
        spikes = detector.scan_and_trigger()
        detector.close()
        if len(spikes) == 0:
            history_path = BASE_DIR / 'data' / 'trend_history.json'
            if not history_path.exists():
                add_log('⚠️ Chưa có dữ liệu trend. Cần chạy ít nhất 3 lần để tích lũy và phát hiện spike.')
            else:
                add_log('Quét xong. Chưa phát hiện trend spike. Tiếp tục chạy định kỳ (cần >=3 lần quét).')
        else:
            add_log(f'Xong! {len(spikes)} trend spike được phát hiện!')
    except Exception as e:
        add_log(f'LỖI quét trend: {e}')
    finally:
        with _pipeline_lock:
            pipeline_running = False


@step_register(
    name='virtualhub', label='Vận đơn',
    desc='Map mã vận đơn Trung Quốc (1688) sang Shopee.',
    icon='🚚', category='service', order=1,
)
def run_virtualhub_thread(store_id, config):
    global pipeline_running
    try:
        track_path = BASE_DIR / 'data' / 'tracking_map.json'
        fulfill_path = BASE_DIR / 'data' / 'orders_to_fulfill.json'
        if not track_path.exists():
            add_log('⚠️ Chưa có dữ liệu mã vận đơn. Import tracking từ 1688 hoặc nhà vận chuyển trước.')
            with _pipeline_lock:
                pipeline_running = False; return
        if not fulfill_path.exists():
            add_log('⚠️ Chưa có đơn hàng để map. Cần đồng bộ đơn Shopee trước.')
            with _pipeline_lock:
                pipeline_running = False; return
        hub = VirtualHub(config, store_id)
        add_log('Đồng bộ mã vận đơn...')
        mapped = hub.auto_map_tracking()
        if mapped == 0:
            add_log('⚠️ Không tìm thấy tracking nào cần map. Kiểm tra tracking_map.json đã có dữ liệu chưa.')
        else:
            add_log(f'Xong! Đã map {mapped} đơn.')
    except Exception as e:
        add_log(f'LỖI virtual hub: {e}')
    finally:
        with _pipeline_lock:
            pipeline_running = False


@step_register(
    name='customercare', label='CSKH',
    desc='Gửi tin nhắn chăm sóc khách hàng tự động.',
    icon='💬', category='service', order=2,
    requires_shopee=True,
)
def run_customercare_thread(store_id, config):
    global pipeline_running
    try:
        s = config.get('shopee', {})
        if not (s.get('partner_id') and s.get('partner_key') and s.get('access_token')):
            add_log('⚠️ Cần cấu hình Shopee API (Partner ID, Key, Access Token) trong phần Sửa store để gửi tin nhắn')
            with _pipeline_lock:
                pipeline_running = False; return
        fulfill_path = BASE_DIR / 'data' / 'orders_to_fulfill.json'
        if not fulfill_path.exists():
            add_log('⚠️ Chưa có đơn hàng để gửi tin nhắn. Cần đồng bộ đơn Shopee trước.')
            with _pipeline_lock:
                pipeline_running = False; return
        bot = CustomerCareBot(config, store_id)
        add_log('Gửi tin nhắn chăm sóc KH...')
        result = bot.process_fulfillment_orders(config)
        bot.close()
        sent = result.get('sent', 0)
        skipped = result.get('skipped', 0)
        if sent == 0 and skipped == 0:
            add_log('⚠️ Không có tin nhắn nào được gửi. Kiểm tra lại đơn hàng và cấu hình.')
        else:
            add_log(f'Xong! Đã gửi {sent} tin nhắn ({skipped} bỏ qua)')
    except Exception as e:
        add_log(f'LỖI chăm sóc KH: {e}')
    finally:
        pipeline_running = False


def _ensure_dirs():
    for d in [BASE_DIR / 'data', BASE_DIR / 'config/stores', BASE_DIR / 'logs', BASE_DIR / 'assets/background_music']:
        d.mkdir(parents=True, exist_ok=True)


_VN_CN_DICT = {
    'do choi cho meo': '猫玩具', 'do choi meo': '猫玩具',
    'phu kien cho': '狗配件', 'phu kien cho meo': '猫狗配件',
    'do dung thu cung': '宠物用品', 'thu cung': '宠物',
    'do choi cho cho': '狗玩具', 'do choi thu cung': '宠物玩具',
    'thuc an cho meo': '猫粮', 'thuc an cho cho': '狗粮',
    'cat ve sinh cho meo': '猫砂', 'long cho thu cung': '宠物笼',
    'ao cho thu cung': '宠物衣服', 'day dat cho': '狗绳',
    'op lung dien thoai': '手机壳', 'op dien thoai': '手机壳',
    'phu kien dien thoai': '手机配件',
    'cuong luc dien thoai': '钢化膜', 'kinh cuong luc': '钢化膜',
    'sac du phong': '充电宝', 'cap sac': '充电线',
    'tai nghe': '耳机', 'tai nghe bluetooth': '蓝牙耳机',
    'giap do dien thoai': '手机支架', 'ong kinh dien thoai': '手机镜头',
    'do dung bep': '厨房用具', 'phu kien bep': '厨房配件',
    'dung cu nau bep': '厨具', 'do gia dung': '家居用品',
    'noi chien khong dau': '空气炸锅', 'noi com dien': '电饭煲',
    'giu nhiet': '保温', 'binh giu nhiet': '保温杯',
    'hop dung do': '收纳盒', 'tu do': '储物柜',
    'phu kien tho trang': '时尚配件',
    'vi da': '钱包', 'tui xach': '手提包',
    'kinh mat': '太阳镜', 'dong ho': '手表',
    'vong tay': '手链', 'nhan': '戒指', 'bong tai': '耳环',
    'do dien tu': '电子产品', 'thiet bi dien tu': '电子设备',
    'sac khong day': '无线充电器', 'loa bluetooth': '蓝牙音箱',
    'cap du lieu': '数据线',
    'my pham': '化妆品', 'duong da': '护肤品',
    'trang diem': '彩妆', 'dung cu lam dep': '美容工具',
    'son moi': '口红', 'ke mat': '眼线笔',
    'do leo nui': '登山装备', 'do the thao': '运动装备',
    'gay leo nui': '登山杖', 'giay leo nui': '登山鞋',
    'do choi tre em': '儿童玩具', 'do choi thong minh': '益智玩具',
    'do choi dieu khien': '遥控玩具',
    'phu kien xe hoi': '汽车配件',
}

_VN_EN_DICT = {
    'do choi cho meo': 'cat toys', 'do choi meo': 'cat toys',
    'phu kien cho': 'dog accessories', 'phu kien cho meo': 'pet accessories',
    'do dung thu cung': 'pet supplies', 'thu cung': 'pet',
    'do choi cho cho': 'dog toys', 'do choi thu cung': 'pet toys',
    'thuc an cho meo': 'cat food', 'thuc an cho cho': 'dog food',
    'cat ve sinh cho meo': 'cat litter',
    'ao cho thu cung': 'pet clothes', 'day dat cho': 'dog leash',
    'op lung dien thoai': 'phone case', 'op dien thoai': 'phone case',
    'phu kien dien thoai': 'phone accessories',
    'cuong luc dien thoai': 'tempered glass', 'kinh cuong luc': 'tempered glass',
    'sac du phong': 'power bank', 'cap sac': 'charging cable',
    'tai nghe': 'headphones', 'tai nghe bluetooth': 'bluetooth earphones',
    'giap do dien thoai': 'phone stand',
    'do dung bep': 'kitchen tools', 'phu kien bep': 'kitchen accessories',
    'dung cu nau bep': 'cookware',
    'noi chien khong dau': 'air fryer', 'noi com dien': 'rice cooker',
    'binh giu nhiet': 'thermos', 'hop dung do': 'storage box',
    'phu kien tho trang': 'fashion accessories',
    'vi da': 'wallet', 'tui xach': 'handbag',
    'kinh mat': 'sunglasses', 'dong ho': 'watch',
    'vong tay': 'bracelet', 'nhan': 'ring', 'bong tai': 'earrings',
    'do dien tu': 'electronics', 'thiet bi dien tu': 'electronic devices',
    'sac khong day': 'wireless charger', 'loa bluetooth': 'bluetooth speaker',
    'my pham': 'cosmetics', 'duong da': 'skincare',
    'dung cu lam dep': 'beauty tools', 'son moi': 'lipstick',
    'do leo nui': 'climbing gear', 'do the thao': 'sports equipment',
    'gay leo nui': 'trekking pole', 'giay leo nui': 'hiking shoes',
    'do choi tre em': 'children toys', 'do choi thong minh': 'educational toys',
    'phu kien xe hoi': 'car accessories',
}
