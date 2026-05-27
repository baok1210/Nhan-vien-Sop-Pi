import sys, os, json, threading, time, asyncio, random
from datetime import datetime, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from flask import Flask, render_template, request, jsonify, Response

from src.config_manager import list_stores, load_store, save_store, delete_store, create_store
from src.source.aliexpress import AliExpressScraper
from src.source.ali1688 import Ali1688Scraper
from src.processing.image_processor import ImageProcessor
from src.processing.video_processor import VideoProcessor
from src.ai.caption_gen import CaptionGenerator
from src.publisher.shopee import ShopeeClient
from src.utils.exchange_rate import calculate_final_price, async_calculate_final_price
from src.utils.logger import setup_logger
from src.pricing.competitor import async_analyze_store_pricing
from src.publisher.order_manager import OrderManager
from src.publisher.flash_sale import FlashSaleManager
from src.publisher.cashflow_planner import CashFlowPlanner
from src.trends.trend_hijacker import TrendDetector
from src.publisher.virtual_hub import VirtualHub
from src.publisher.customer_care import CustomerCareBot

app = Flask(__name__)
app.config['SECRET_KEY'] = 'china-dropship-shopee-secret'
BASE_DIR = Path(__file__).parent.parent

pipeline_log: list[str] = []
pipeline_running = False

# APScheduler
_scheduler = None
_scheduler_jobs: dict[str, str] = {}  # store_id -> job_id


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
    config = load_store(store_id)
    if not config:
        return
    if step == 'crawl':
        run_crawl_thread(store_id, config)
    elif step == 'images':
        run_images_thread(store_id, config)
    elif step == 'caption':
        run_caption_thread(store_id, config)

def add_log(msg):
    ts = time.strftime('%H:%M:%S')
    pipeline_log.append(f'[{ts}] {msg}')
    if len(pipeline_log) > 500:
        pipeline_log[:100] = []

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
                user_agents = [
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36',
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36',
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15',
                    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
                ]
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
                                        scraper._headers()['User-Agent'] = random.choice(user_agents)
                                    products = scraper.search(kw, page)
                                    if products:
                                        count = len(products)
                                        all_products.extend(products)
                                        add_log(f'    Trang {page}: +{count} sp')
                                        ok = True
                                        break
                                    else:
                                        # Check if blocked
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
            # Write to global product pool for downstream features
            pool_path = BASE_DIR / 'data' / 'product_pool.json'
            existing = []
            if pool_path.exists():
                try:
                    with open(pool_path, encoding='utf-8') as f:
                        existing = json.load(f)
                except: pass
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
        pipeline_running = False

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
        pipeline_running = False

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
        gen = CaptionGenerator(config)
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
        pipeline_running = False

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
        # Save published products for downstream features
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
        pipeline_running = False

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
        pipeline_running = False

def run_pricing_thread(store_id, config):
    global pipeline_running
    try:
        caps_path = BASE_DIR / 'data' / store_id / 'captions.json'
        if not caps_path.exists():
            add_log('⚠️ Cần chạy bước Caption trước (tạo captions.json)')
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
        pipeline_running = False

def run_orders_thread(store_id, config):
    global pipeline_running
    try:
        s = config.get('shopee', {})
        if not (s.get('partner_id') and s.get('partner_key') and s.get('shop_id')):
            add_log('⚠️ Cần cấu hình Shopee API (Partner ID, Key, Shop ID) trong phần Sửa store trước khi đồng bộ đơn')
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
        pipeline_running = False

def run_flashsale_thread(store_id, config):
    global pipeline_running
    try:
        s = config.get('shopee', {})
        if not (s.get('partner_id') and s.get('partner_key') and s.get('shop_id')):
            add_log('⚠️ Cần cấu hình Shopee API (Partner ID, Key, Shop ID) trong phần Sửa store trước khi tạo flash sale')
            pipeline_running = False; return
        report_path = BASE_DIR / 'data' / store_id / 'pricing_report.json'
        if not report_path.exists():
            add_log('⚠️ Cần chạy Phân tích giá trước (tạo pricing_report.json)')
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
        pipeline_running = False

def run_cashflow_thread(store_id, config):
    global pipeline_running
    try:
        fulfill_path = BASE_DIR / 'data' / 'orders_to_fulfill.json'
        if not fulfill_path.exists():
            add_log('⚠️ Chưa có đơn hàng để phân tích. Cần đồng bộ đơn Shopee (bước Đơn hàng) trước.')
            pipeline_running = False; return
        planner = CashFlowPlanner(config, store_id)
        add_log('Phân tích dòng tiền...')
        report = planner.run()
        add_log(f'Xong! Lợi nhuận ước tính: {report.get("summary", {}).get("estimated_profit_vnd", 0):,.0f} VND')
    except Exception as e:
        add_log(f'LỖI phân tích dòng tiền: {e}')
    finally:
        pipeline_running = False

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
        pipeline_running = False

def run_virtualhub_thread(store_id, config):
    global pipeline_running
    try:
        track_path = BASE_DIR / 'data' / 'tracking_map.json'
        fulfill_path = BASE_DIR / 'data' / 'orders_to_fulfill.json'
        if not track_path.exists():
            add_log('⚠️ Chưa có dữ liệu mã vận đơn. Import tracking từ 1688 hoặc nhà vận chuyển trước.')
            pipeline_running = False; return
        if not fulfill_path.exists():
            add_log('⚠️ Chưa có đơn hàng để map. Cần đồng bộ đơn Shopee trước.')
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
        pipeline_running = False

def run_customercare_thread(store_id, config):
    global pipeline_running
    try:
        s = config.get('shopee', {})
        if not (s.get('partner_id') and s.get('partner_key') and s.get('access_token')):
            add_log('⚠️ Cần cấu hình Shopee API (Partner ID, Key, Access Token) trong phần Sửa store để gửi tin nhắn')
            pipeline_running = False; return
        fulfill_path = BASE_DIR / 'data' / 'orders_to_fulfill.json'
        if not fulfill_path.exists():
            add_log('⚠️ Chưa có đơn hàng để gửi tin nhắn. Cần đồng bộ đơn Shopee trước.')
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

@app.route('/research')
def research_page():
    from src.research.market_research import _load_cached
    data = _load_cached()
    return render_template('research.html', data=data)


@app.route('/research/scan', methods=['POST'])
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


@app.route('/')
def index():
    stores = list_stores()
    store_data = []
    for sid in stores:
        if sid == 'example': continue
        data = load_store(sid) or {}
        has_products = (BASE_DIR / 'data' / sid / 'products.json').exists()
        has_images = (BASE_DIR / 'data' / sid / 'products_with_images.json').exists()
        has_captions = (BASE_DIR / 'data' / sid / 'captions.json').exists()
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
        store_data.append({
            'id': sid,
            'name': data.get('name', sid),
            'has_products': has_products,
            'has_images': has_images,
            'has_captions': has_captions,
            'product_count': product_count,
            'crawl_max_pages_1688': data.get('sources', {}).get('1688', {}).get('max_pages', 3),
            'crawl_proxy': data.get('sources', {}).get('1688', {}).get('proxy', '') or data.get('sources', {}).get('aliexpress', {}).get('proxy', ''),
            'ai_provider': data.get('ai', {}).get('caption', {}).get('provider', ''),
            'ai_api_key': data.get('ai', {}).get('caption', {}).get('api_key', ''),
            'ai_model': data.get('ai', {}).get('caption', {}).get('model', 'gemini-flash-latest'),
            'ai_language': data.get('ai', {}).get('caption', {}).get('language', 'vi'),
            'ai_tone': data.get('ai', {}).get('caption', {}).get('tone', 'professional'),
            'ai_max_title': data.get('ai', {}).get('caption', {}).get('max_title_length', 120),
            'ai_num_hashtags': data.get('ai', {}).get('caption', {}).get('num_hashtags', 10),
        })
    return render_template('index.html', stores=store_data, running=pipeline_running)

@app.route('/log')
def get_log():
    return jsonify({'log': pipeline_log[-100:], 'running': pipeline_running})

@app.route('/run/<store_id>/<step>', methods=['POST'])
def run_step(store_id, step):
    global pipeline_running
    if pipeline_running:
        return jsonify({'error': 'Pipeline đang chạy, chờ đến khi xong'}), 400
    config = load_store(store_id)
    if not config:
        return jsonify({'error': 'Không tìm thấy store'}), 404
    # Merge optional JSON body params into proper config paths
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
            try: import json as _j; config.setdefault('sources', {}).setdefault('1688', {})['cookies'] = _j.loads(rp['cookies_1688'])
            except: pass
        if 'cookies_ae' in rp and rp['cookies_ae']:
            try: import json as _j; config.setdefault('sources', {}).setdefault('aliexpress', {})['cookies'] = _j.loads(rp['cookies_ae'])
            except: pass
        if 'delay_min' in rp:
            d = int(rp['delay_min'])
            config.setdefault('sources', {}).setdefault('1688', {})['delay_seconds'] = d
            config.setdefault('sources', {}).setdefault('aliexpress', {})['delay_seconds'] = d
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
        if 'days_back' in rp:
            config['days_back'] = int(rp['days_back'])
        if 'max_items' in rp:
            config['max_items'] = int(rp['max_items'])
        # AI caption overrides
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
    # Save config so user's settings persist
    save_store(store_id, config)

    pipeline_running = True
    if step == 'crawl':
        t = threading.Thread(target=run_crawl_thread, args=(store_id, config), daemon=True)
    elif step == 'images':
        t = threading.Thread(target=run_images_thread, args=(store_id, config), daemon=True)
    elif step == 'caption':
        t = threading.Thread(target=run_caption_thread, args=(store_id, config), daemon=True)
    elif step == 'publish':
        t = threading.Thread(target=run_publish_thread, args=(store_id, config), daemon=True)
    elif step == 'video':
        t = threading.Thread(target=run_video_thread, args=(store_id, config), daemon=True)
    elif step == 'pricing':
        t = threading.Thread(target=run_pricing_thread, args=(store_id, config), daemon=True)
    elif step == 'orders':
        t = threading.Thread(target=run_orders_thread, args=(store_id, config), daemon=True)
    elif step == 'flashsale':
        t = threading.Thread(target=run_flashsale_thread, args=(store_id, config), daemon=True)
    elif step == 'cashflow':
        t = threading.Thread(target=run_cashflow_thread, args=(store_id, config), daemon=True)
    elif step == 'trends':
        t = threading.Thread(target=run_trends_thread, args=(store_id, config), daemon=True)
    elif step == 'virtualhub':
        t = threading.Thread(target=run_virtualhub_thread, args=(store_id, config), daemon=True)
    elif step == 'customercare':
        t = threading.Thread(target=run_customercare_thread, args=(store_id, config), daemon=True)
    else:
        pipeline_running = False
        return jsonify({'error': 'Bước không hợp lệ'}), 400
    t.start()
    return jsonify({'status': 'started'})

@app.route('/products/<store_id>')
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

@app.route('/store/new', methods=['GET', 'POST'])
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
        # Save keywords & pricing if provided
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
            # Watermark config on create
            wm_text = request.form.get('wm_text', '').strip()
            if wm_text:
                img_proc = data.setdefault('image_processing', {})
                ad = img_proc.setdefault('anti_duplication', {})
                wm = ad.setdefault('watermark', {})
                wm['text'] = wm_text
                wm_img = request.form.get('wm_image_path', '').strip()
                if wm_img:
                    wm['image_path'] = wm_img
            save_store(store_id, data)
        return jsonify({'status': 'ok', 'store_id': store_id})
    return render_template('store_form.html')

@app.route('/store/<store_id>/delete', methods=['POST'])
def remove_store(store_id):
    delete_store(store_id)
    # Also remove data directory
    import shutil
    data_dir = BASE_DIR / 'data' / store_id
    if data_dir.exists():
        shutil.rmtree(str(data_dir))
    return jsonify({'status': 'deleted'})

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

def _dict_translate(text: str) -> tuple[str, str]:
    text_lower = text.lower().strip()
    if text_lower in _VN_CN_DICT:
        return (_VN_CN_DICT[text_lower], _VN_EN_DICT.get(text_lower, text_lower))
    parts = [p.strip() for p in text_lower.split(',') if p.strip()]
    if len(parts) > 1:
        cn_parts = [_VN_CN_DICT.get(p, p) for p in parts]
        en_parts = [_VN_EN_DICT.get(p, p) for p in parts]
        return (', '.join(cn_parts), ', '.join(en_parts))
    return ('', '')

@app.route('/translate', methods=['POST'])
def translate_keywords():
    text = request.json.get('text', '').strip()
    if not text:
        return jsonify({'error': 'Nhập từ khóa tiếng Việt'}), 400
    # Try dictionary first
    dict_cn, dict_en = _dict_translate(text)
    if dict_cn and dict_en:
        return jsonify({'cn': dict_cn, 'en': dict_en})
    # Fallback to Google Translate
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

@app.route('/store/<store_id>/edit', methods=['GET', 'POST'])
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
                try: sources.setdefault(src_key, {})['max_pages'] = int(mp)
                except ValueError: pass
        proxy_val = request.form.get('proxy', '').strip()
        if proxy_val:
            for src_key in ['1688', 'aliexpress']:
                sources.setdefault(src_key, {})['proxy'] = proxy_val
        ck = request.form.get('cookies_1688', '').strip()
        if ck:
            try: sources.setdefault('1688', {})['cookies'] = json.loads(ck)
            except: pass
        ck_ae = request.form.get('cookies_ae', '').strip()
        if ck_ae:
            try: sources.setdefault('aliexpress', {})['cookies'] = json.loads(ck_ae)
            except: pass
        # Watermark config
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
        # AI caption config
        ai_cap = data.setdefault('ai', {}).setdefault('caption', {})
        ai_cap['provider'] = request.form.get('ai_provider', '')
        ai_cap['api_key'] = request.form.get('ai_api_key', '')
        ai_cap['model'] = request.form.get('ai_model', 'gemini-flash-latest')
        ai_cap['language'] = request.form.get('ai_language', 'vi')
        ai_cap['tone'] = request.form.get('ai_tone', 'professional')
        try:
            ai_cap['max_title_length'] = int(request.form.get('ai_max_title', 120))
        except ValueError: pass
        try:
            ai_cap['num_hashtags'] = int(request.form.get('ai_num_hashtags', 10))
        except ValueError: pass
        save_store(store_id, data)
        return jsonify({'status': 'saved'})
    return render_template('store_edit.html', store_id=store_id, data=data)


@app.route('/schedule/<store_id>', methods=['POST'])
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


@app.route('/schedule/<store_id>', methods=['GET'])
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


@app.route('/schedules', methods=['GET'])
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


def _ensure_dirs():
    for d in [BASE_DIR / 'data', BASE_DIR / 'config/stores', BASE_DIR / 'logs', BASE_DIR / 'assets/background_music']:
        d.mkdir(parents=True, exist_ok=True)


if __name__ == '__main__':
    _ensure_dirs()
    print('=' * 60)
    print('  WEB UI - China Dropship to Shopee')
    print('  Open browser: http://localhost:5000')
    print('=' * 60)
    app.run(host='127.0.0.1', port=5000, debug=False, threaded=True)
