import asyncio, json, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from textual.screen import Screen
from textual.widgets import Header, Footer, Button, Static, Log
from textual.containers import VerticalScroll, Vertical
from textual import work

from src.config_manager import load_store
from src.source.aliexpress import AliExpressScraper
from src.source.ali1688 import Ali1688Scraper
from src.processing.image_processor import ImageProcessor
from src.processing.video_processor import VideoProcessor
from src.ai.caption_gen import CaptionGenerator
from src.publisher.shopee import ShopeeClient
from src.publisher.order_manager import OrderManager
from src.publisher.flash_sale import FlashSaleManager
from src.publisher.cashflow_planner import CashFlowPlanner
from src.publisher.virtual_hub import VirtualHub
from src.publisher.customer_care import CustomerCareBot
from src.trends.trend_hijacker import TrendDetector
from src.source.supplier_scorer import SupplierCreditScorer
from src.utils.exchange_rate import async_calculate_final_price
from src.utils.logger import setup_logger


logger = setup_logger("tui")


class StoreDetailScreen(Screen):
    def __init__(self, store_id: str, run_crawl: bool = False):
        super().__init__()
        self.store_id = store_id
        self.should_run_crawl = run_crawl

    @property
    def _data_dir(self) -> Path:
        return Path("data") / self.store_id

    @property
    def _store_cfg(self) -> dict:
        return load_store(self.store_id) or {}

    def compose(self):
        data = self._store_cfg
        name = data.get("name", self.store_id)
        yield Header(show_clock=True)
        yield VerticalScroll(
            Static(f"📋 {name}", classes="title"),
            Static("", id="store-info"),
            Vertical(
                Button("1️⃣ Crawl sản phẩm", variant="primary", id="run-crawl"),
                Button("2️⃣ Xử lý ảnh", variant="primary", id="run-images", disabled=True),
                Button("🎬 Xử lý video", variant="primary", id="run-video", disabled=True),
                Button("3️⃣ Tạo caption", variant="primary", id="run-caption", disabled=True),
                Button("📊 Cập nhật giá", variant="warning", id="run-pricing", disabled=True),
                Button("4️⃣ Đăng Shopee", variant="primary", id="run-publish", disabled=True),
                Static("", classes="section-title"),
                Static("📦 Hậu mãi & Vận hành", classes="section-title"),
                Button("🔄 Đồng bộ đơn hàng", variant="warning", id="run-orders", disabled=True),
                Button("⚡ Flash Sale", variant="warning", id="run-flashsale", disabled=True),
                Button("💰 Dòng tiền", variant="warning", id="run-cashflow", disabled=True),
                Button("📈 Trend Hijack", variant="warning", id="run-trends", disabled=True),
                Button("🏭 Virtual Hub", variant="warning", id="run-virtualhub", disabled=True),
                Button("💬 Auto Care", variant="warning", id="run-customercare", disabled=True),
                Button("▶️ Chạy toàn bộ", variant="success", id="run-all", disabled=True),
                id="pipeline-buttons",
            ),
            Static("📝 Nhật ký:", classes="section-title"),
            Log(id="log"),
            Static("", classes="section-title"),
            Static("🛠 Công cụ", classes="section-title"),
            Button("🍪 Xuất cookies 1688", variant="default", id="export-cookies"),
            Button("🔌 Kiểm tra Shopee API", variant="default", id="check-shopee"),
            Button("← Quay lại", variant="default", id="back"),
            id="detail-content",
        )
        yield Footer()

    def on_mount(self):
        self.refresh_info()
        self.refresh_buttons()
        if self.should_run_crawl:
            self.run_crawl()

    def refresh_info(self):
        data = self._store_cfg
        if not data:
            return
        niche = data.get("niche", {})
        sources = data.get("sources", {})
        kw_cn = ", ".join(niche.get("keywords_cn", [])[:5])
        kw_en = ", ".join(niche.get("keywords_en", [])[:5])
        ae = "✅" if sources.get("aliexpress", {}).get("enabled") else "❌"
        c8 = "✅" if sources.get("1688", {}).get("enabled") else "❌"
        self.query_one("#store-info").update(
            f"Từ khóa CN: {kw_cn}\nTừ khóa EN: {kw_en}\nAE: {ae} | 1688: {c8}"
        )

    def refresh_buttons(self):
        products_file = self._data_dir / "products.json"
        products_with_images = self._data_dir / "products_with_images.json"
        captions_file = self._data_dir / "captions.json"
        published_file = self._data_dir / "published.json"
        fulfillment_file = Path("data") / "orders_to_fulfill.json"
        has_products = products_file.exists()
        has_images = False
        if products_with_images.exists():
            try:
                with open(products_with_images, encoding="utf-8") as f:
                    data = json.load(f)
                has_images = any(p.get("images_processed") for p in data)
            except (json.JSONDecodeError, OSError):
                pass
        has_captions = captions_file.exists()
        has_published = published_file.exists()
        has_fulfillment = fulfillment_file.exists()
        self.query_one("#run-images").disabled = not has_products
        self.query_one("#run-video").disabled = not has_images
        self.query_one("#run-caption").disabled = not has_images
        self.query_one("#run-pricing").disabled = not has_captions
        self.query_one("#run-publish").disabled = not has_captions
        self.query_one("#run-orders").disabled = not has_published
        self.query_one("#run-flashsale").disabled = not has_published
        self.query_one("#run-cashflow").disabled = not has_fulfillment
        self.query_one("#run-trends").disabled = False
        self.query_one("#run-virtualhub").disabled = not has_fulfillment
        self.query_one("#run-customercare").disabled = not has_fulfillment
        self.query_one("#run-all").disabled = not has_products

    def write_log(self, msg: str):
        self.query_one("#log").write_line(f"[{time.strftime('%H:%M:%S')}] {msg}")

    def _load_products(self) -> list[dict]:
        path = self._data_dir / "products.json"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save_json(self, name: str, data: list):
        path = self._data_dir / name
        self._data_dir.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @work
    async def run_crawl(self):
        self.write_log("Crawl sản phẩm...")
        data = self._store_cfg
        if not data:
            return
        all_products = []
        ae_cfg = data.get("sources", {}).get("aliexpress", {})
        if ae_cfg.get("enabled"):
            self.write_log("  AliExpress...")
            scraper = AliExpressScraper(ae_cfg)
            try:
                products = await asyncio.get_event_loop().run_in_executor(
                    None, scraper.crawl_by_keywords, data.get("niche", {}).get("keywords_en", [])
                )
                all_products.extend(products)
                self.write_log(f"  +{len(products)} sản phẩm AE")
            finally:
                scraper.close()
        c8_cfg = data.get("sources", {}).get("1688", {})
        if c8_cfg.get("enabled"):
            self.write_log("  1688...")
            scraper = Ali1688Scraper(c8_cfg)
            scraper._store_config = data
            try:
                products = await asyncio.get_event_loop().run_in_executor(
                    None, scraper.crawl_by_keywords, data.get("niche", {}).get("keywords_cn", [])
                )
                all_products.extend(products)
                self.write_log(f"  +{len(products)} sản phẩm 1688")
            finally:
                scraper.close()
        if all_products:
            out = []
            for p in all_products:
                out.append({
                    "id": p.id, "title_cn": p.title_cn, "price_cny": p.price_cny,
                    "image_urls": p.image_urls, "detail_url": p.detail_url,
                    "platform": p.platform, "is_dropship": p.is_dropship,
                    "description_cn": p.description_cn[:500] if p.description_cn else "",
                    "supplier_name": p.supplier_name, "sales_count": p.sales_count,
                })
            self._save_json("products.json", out)
            self.write_log(f"Xong! {len(out)} sp -> data/{self.store_id}/products.json")
        else:
            self.write_log("Không crawl được sp nào")
        self.refresh_buttons()

    @work
    async def run_images(self):
        self.write_log("Xử lý ảnh...")
        products = self._load_products()
        if not products:
            self.write_log("Không có sản phẩm để xử lý ảnh")
            return
        processor = ImageProcessor(self._store_cfg)
        raw_dir = str(self._data_dir / "images" / "raw")
        proc_dir = str(self._data_dir / "images" / "processed")
        total_ok = 0
        for i, prod in enumerate(products, 1):
            pid = prod.get("id", f"p{i}")
            urls = prod.get("image_urls", [])
            if not urls:
                self.write_log(f"  [{i}/{len(products)}] {pid}: Không có URL ảnh")
                continue
            saved = await processor.download_images(urls, raw_dir, pid)
            if saved:
                out_dir = f"{proc_dir}/{pid}"
                results = processor.process_batch(saved, out_dir)
                prod["images_local"] = saved
                prod["images_processed"] = results
                prod["image_count"] = len(results)
                total_ok += 1
                self.write_log(f"  [{i}/{len(products)}] {pid}: {len(results)} ảnh")
            else:
                self.write_log(f"  [{i}/{len(products)}] {pid}: Tải ảnh thất bại")
        self._save_json("products_with_images.json", products)
        self.write_log(f"Xong! {total_ok}/{len(products)} sp có ảnh")
        self.refresh_buttons()

    @work
    async def run_video(self):
        self.write_log("Xử lý video...")
        bgm_dir = Path("assets/background_music")
        mp3s = list(bgm_dir.glob("*.mp3")) if bgm_dir.exists() else []
        if not mp3s:
            self.write_log("  ⚠️ Không tìm thấy file .mp3 trong assets/background_music/")
            self.write_log("  Video sẽ xuất ở chế độ không âm thanh (muted)")
        products_path = self._data_dir / "products_with_images.json"
        if not products_path.exists():
            self.write_log("Không có sản phẩm để xử lý video")
            return
        with open(products_path, encoding="utf-8") as f:
            products = json.load(f)
        processor = VideoProcessor(self._store_cfg)
        raw_dir = str(self._data_dir / "videos" / "raw")
        proc_dir = str(self._data_dir / "videos" / "processed")
        dl_items = []
        prod_index = {}
        for i, prod in enumerate(products, 1):
            url = prod.get("video_url", "") or prod.get("video", "")
            pid = prod.get("id", f"p{i}")
            if not url:
                continue
            dl_items.append((url, pid))
            prod_index[pid] = (i, prod)
        if dl_items:
            self.write_log(f"  Tải {len(dl_items)} video song song...")
            results = await processor.download_videos(dl_items, raw_dir)
            dl_map = {pid: path for pid, path in results}
            for pid, (i, prod) in prod_index.items():
                path = dl_map.get(pid)
                if path:
                    self.write_log(f"  [{i}/{len(products)}] {pid}: đã tải")
                else:
                    self.write_log(f"  [{i}/{len(products)}] {pid}: tải thất bại")
        else:
            dl_map = {}
        ok = fail = 0
        to_process = [(pid, dl_map[pid]) for pid in sorted(dl_map) if dl_map[pid]]
        if to_process:
            self.write_log(f"  Xử lý {len(to_process)} video song song...")
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor(max_workers=3) as pool:
                futs = {}
                for pid, rpath in to_process:
                    fut = loop.run_in_executor(pool, processor.process_single, rpath, proc_dir)
                    futs[fut] = pid
                for fut in asyncio.as_completed(futs):
                    pid = futs[fut]
                    try:
                        processed = await fut
                    except Exception:
                        processed = None
                    i, prod = prod_index[pid]
                    prod["video_processed"] = processed
                    if processed:
                        ok += 1
                        self.write_log(f"  [{i}/{len(products)}] {pid}: OK")
                    else:
                        fail += 1
                        self.write_log(f"  [{i}/{len(products)}] {pid}: FAIL (muted)")
        no_url = sum(1 for p in products if not (p.get("video_url") or p.get("video")))
        fail += no_url
        self._save_json("products_with_images.json", products)
        self.write_log(f"Xong! {ok} ok, {fail} fail ({no_url} không có URL)")
        self.refresh_buttons()

    @work
    async def run_caption(self):
        self.write_log("Tạo caption...")
        products_path = self._data_dir / "products_with_images.json"
        if not products_path.exists():
            products_path = self._data_dir / "products.json"
        if not products_path.exists():
            self.write_log("Không có sản phẩm để tạo caption")
            return
        with open(products_path, encoding="utf-8") as f:
            products = json.load(f)
        gen = CaptionGenerator(self._store_cfg)
        niche = self._store_cfg.get("niche", {})
        niche_name = niche.get("keywords_vn", [self.store_id])[0]
        multiplier = niche.get("price_multiplier", 2.5)
        captions = []
        for i, prod in enumerate(products, 1):
            price_cny = prod.get("price_cny", 0)
            price_vnd = await async_calculate_final_price(price_cny, multiplier)
            title_cn = prod.get("title_cn", "")
            caption = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda t=title_cn, n=niche_name, p=price_cny, d=prod.get("description_cn", ""), v=price_vnd:
                    gen.generate(t, n, p, d, v),
            )
            from src.seo.title_scorer import generate_and_score
            seo_result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda t=caption.get("title_vi", ""), c=niche_name,
                       f=prod.get("description_cn", ""), kw=niche.get("keywords_vn", []):
                    generate_and_score(t, c, f, kw),
            )
            caption["title_vi"] = seo_result["title_vi"]
            caption["title_variants"] = seo_result["all_titles"]
            caption["best_title_style"] = seo_result["best_style"]
            caption["best_title_score"] = seo_result["best_score"]
            entry = {
                "product_id": prod.get("id"), "price_cny": price_cny,
                "price_vnd": int(price_vnd),
                "images_processed": prod.get("images_processed", []), "image_ids": [],
                **caption,
            }
            captions.append(entry)
            self.write_log(
                f"  [{i}/{len(products)}] {prod.get('id')}: "
                f"{caption.get('title_vi', '')[:50]}... "
                f"(score={seo_result['best_score']:.3f}, {seo_result['best_style']})"
            )
        self._save_json("captions.json", captions)
        self.write_log(f"Xong! {len(captions)} caption -> data/{self.store_id}/captions.json")
        self.refresh_buttons()

    @work
    async def run_pricing(self):
        self.write_log("📊 Đang cập nhật giá cạnh tranh...")
        cap_path = self._data_dir / "captions.json"
        if not cap_path.exists():
            self.write_log("Chưa có caption. Chạy bước 3 trước.")
            return
        try:
            from src.pricing.competitor import async_analyze_store_pricing
            summary = await async_analyze_store_pricing(self.store_id)
            self.write_log(f"✅ {summary['profitable']}/{summary['total']} sản phẩm có lợi nhuận")
            if summary.get("unprofitable", 0) > 0:
                self.write_log(f"⏭️ {summary['unprofitable']} sản phẩm sẽ bị tạm ẩn:")
                for pid in summary.get("skipped_products", []):
                    self.write_log(f"   - {pid}")
            self.write_log(f"📄 Báo cáo lưu tại: {summary['report_path']}")
        except FileNotFoundError as e:
            self.write_log(f"❌ {e}")
        except Exception as e:
            self.write_log(f"❌ Lỗi phân tích giá: {e}")
        self.refresh_buttons()

    @work
    async def run_publish(self):
        self.write_log("Đăng Shopee...")
        cap_path = self._data_dir / "captions.json"
        if not cap_path.exists():
            self.write_log("Chưa có caption. Chạy bước 3 trước.")
            return
        with open(cap_path, encoding="utf-8") as f:
            captions = json.load(f)
        store_cfg = self._store_cfg
        shopee_cfg = store_cfg.get("shopee", {})
        if not shopee_cfg.get("partner_id") or not shopee_cfg.get("partner_key"):
            self.write_log("⚠️ Shopee chưa được cấu hình. Vào Store List -> Chi tiết -> sửa thông tin Shopee.")
            return
        products_path = self._data_dir / "products_with_images.json"
        variant_tier_map = {}
        if products_path.exists():
            try:
                from src.processing.variant_manager import VariantManager
                with open(products_path, encoding="utf-8") as f:
                    raw_products = json.load(f)
                vm = VariantManager(store_cfg, self.store_id)
                processed = await asyncio.get_event_loop().run_in_executor(
                    None, vm.process_products, raw_products, self.store_id
                )
                groups_path = self._data_dir / "variant_groups.json"
                if groups_path.exists():
                    with open(groups_path, encoding="utf-8") as gf:
                        groups = json.load(gf)
                    for g in groups:
                        parent_id = g.get("parent_source_id", "")
                        if g.get("products"):
                            options = []
                            variations = []
                            for idx, prod in enumerate(g["products"]):
                                label = prod.get("variation_label", f"Option {idx}")
                                sku = prod.get("variation_sku", f"sku_{idx}")
                                price = prod.get("price_vnd") or prod["source"].get("price_cny", 0) * 3500 * 2.5
                                if label not in options:
                                    options.append(label)
                                variations.append({
                                    "tier_index": [options.index(label)],
                                    "variation_sku": sku, "variation_stock": 999,
                                    "variation_price": int(price),
                                })
                            variant_tier_map[parent_id] = {
                                "tier_variation": [{"name": "Phân loại", "option_list": options}],
                                "variation": variations,
                            }
                self.write_log(f"  🔀 Variant: {len(variant_tier_map)} groups detected")
            except Exception as e:
                self.write_log(f"  ⚠️ Variant manager skipped: {e}")
        client = ShopeeClient(store_cfg)
        niche_name = store_cfg.get("niche", {}).get("keywords_vn", [self.store_id])[0]
        pricing_report_path = self._data_dir / "pricing_report.json"
        pricing_map = {}
        if pricing_report_path.exists():
            try:
                with open(pricing_report_path, encoding="utf-8") as pf:
                    for entry in json.load(pf):
                        pricing_map[entry.get("product_id")] = entry
            except Exception:
                pass
        results = []
        try:
            for i, cap in enumerate(captions, 1):
                self.write_log(f"  [{i}/{len(captions)}] Đang xử lý {cap.get('product_id')}...")
                price_vnd = cap.get("price_vnd", 0)
                pid_check = cap.get("product_id", "")
                if pid_check in pricing_map:
                    p_entry = pricing_map[pid_check]
                    if not p_entry.get("profitable", True):
                        self.write_log(f"    ⏭️ {pid_check}: không lợi nhuận, bỏ qua")
                        results.append({**cap, "shopee_status": "unprofitable", "shopee_error": "price_too_low"})
                        continue
                    price_vnd = p_entry.get("final_price_vnd", price_vnd)
                image_ids = []
                for img_path in cap.get("images_processed", [])[:9]:
                    if Path(img_path).exists():
                        iid = await asyncio.get_event_loop().run_in_executor(None, client.upload_image, img_path)
                        if iid:
                            image_ids.append(iid)
                if not image_ids:
                    self.write_log(f"    ⚠️ Không upload được ảnh, bỏ qua")
                    results.append({**cap, "shopee_status": "no_images", "shopee_error": ""})
                    continue
                from src.models.product import ProductSource, ProductProcessed, ShopeeProduct
                src = ProductSource(
                    id=cap.get("product_id", ""), title_cn=cap.get("title_cn", ""),
                    price_cny=cap.get("price_cny", 0), original_price_cny=cap.get("price_cny", 0),
                    image_urls=[], description_cn="", category_name_cn=niche_name,
                )
                pp = ProductProcessed(
                    source=src, images_processed=image_ids, title_vi=cap.get("title_vi", ""),
                    description_vi=cap.get("description", ""),
                    bullet_points=cap.get("bullet_points", []), hashtags=cap.get("hashtags", []),
                    price_vnd=price_vnd,
                )
                sp = ShopeeProduct(
                    product=pp, image_ids=image_ids,
                    category_id=store_cfg.get("niche", {}).get("category_shopee_id", 0),
                    logistic_id=shopee_cfg.get("default_logistic_id", 80001),
                    tier_variations=variant_tier_map.get(pid_check, {}),
                )
                item_id = client.add_item(sp)
                if item_id:
                    self.write_log(f"    ✅ Item: {item_id}")
                    results.append({**cap, "shopee_status": "created", "shopee_item_id": item_id})
                else:
                    self.write_log(f"    ❌ Tạo item thất bại")
                    results.append({**cap, "shopee_status": "failed", "shopee_error": "create_item_failed"})
            self._save_json("published.json", results)
            success = sum(1 for r in results if r.get("shopee_status") == "created")
            self.write_log(f"Xong! {success}/{len(results)} sản phẩm đã đăng")
        finally:
            client.close()

    @work
    async def run_orders(self):
        self.write_log("🔄 Đồng bộ đơn hàng Shopee...")
        try:
            mgr = OrderManager(self._store_cfg, self.store_id)
            count = await asyncio.get_event_loop().run_in_executor(None, mgr.sync)
            self.write_log(f"  {count} đơn hàng mới -> data/orders_to_fulfill.json")
            mgr.close()
        except Exception as e:
            self.write_log(f"❌ Lỗi đồng bộ đơn: {e}")
        self.refresh_buttons()

    @work
    async def run_flashsale(self):
        self.write_log("⚡ Đăng ký Flash Sale...")
        shopee_cfg = self._store_cfg.get("shopee", {})
        if not shopee_cfg.get("partner_id") or not shopee_cfg.get("partner_key"):
            self.write_log("⚠️ Shopee chưa được cấu hình. Bỏ qua Flash Sale.")
            return
        try:
            mgr = FlashSaleManager(self._store_cfg, self.store_id)
            results = await asyncio.get_event_loop().run_in_executor(None, lambda: mgr.run(max_items=20))
            self.write_log(f"  ✅ Đã đăng ký {len(results)} đợt Flash Sale")
            mgr.close()
        except Exception as e:
            self.write_log(f"❌ Lỗi Flash Sale: {e}")

    @work
    async def run_cashflow(self):
        self.write_log("💰 Phân tích dòng tiền...")
        try:
            planner = CashFlowPlanner(self._store_cfg, self.store_id)
            report = await asyncio.get_event_loop().run_in_executor(None, planner.run)
            summary = report.get("summary", {})
            forecast = report.get("forecast", {})
            self.write_log(f"  Đơn chờ: {summary.get('pending_orders', 0)} | Chi phí: {summary.get('total_pending_cost_vnd', 0):,.0f} VND")
            self.write_log(f"  Doanh thu: {summary.get('total_receivable_vnd', 0):,.0f} VND | Lãi: {summary.get('estimated_profit_vnd', 0):,.0f} VND")
            peak = forecast.get("peak_capital_needed_vnd", 0)
            if peak:
                self.write_log(f"  📊 Vốn đỉnh: {peak:,.0f} VND vào {forecast.get('peak_capital_day')}")
            if report.get("warning"):
                self.write_log(f"  ⚠️ {report['warning']}")
        except Exception as e:
            self.write_log(f"❌ Lỗi phân tích dòng tiền: {e}")

    @work
    async def run_trends(self):
        self.write_log("📈 Quét xu hướng thị trường...")
        try:
            detector = TrendDetector(self._store_cfg)
            spikes = await asyncio.get_event_loop().run_in_executor(None, detector.scan_and_trigger)
            if spikes:
                self.write_log(f"  📈 Phát hiện {len(spikes)} từ khóa nóng:")
                for s in spikes[:5]:
                    self.write_log(f"    - {s['keyword']} ({s['ratio']}x spike)")
            else:
                self.write_log("  ✅ Không phát hiện spike mới")
            detector.close()
        except Exception as e:
            self.write_log(f"❌ Lỗi quét xu hướng: {e}")

    @work
    async def run_virtualhub(self):
        self.write_log("🏭 Virtual Hub: Mapping tracking...")
        try:
            hub = VirtualHub(self._store_cfg, self.store_id)
            mapped = await asyncio.get_event_loop().run_in_executor(None, hub.auto_map_tracking)
            status = await asyncio.get_event_loop().run_in_executor(None, hub.status_summary)
            self.write_log(f"  Tổng: {status['total']} | Đã map: {status['mapped']} | Chờ: {status['pending']}")
            if mapped:
                self.write_log(f"  ✅ Tự động map {mapped} tracking mới")
                manifest = await asyncio.get_event_loop().run_in_executor(None, hub.generate_manifest)
                if manifest:
                    self.write_log(f"  📋 Manifest: {len(manifest)} mục (data/{self.store_id}/relabel_manifest_*.json)")
        except Exception as e:
            self.write_log(f"❌ Lỗi Virtual Hub: {e}")

    @work
    async def run_customercare(self):
        self.write_log("💬 Gửi tin nhắn chăm sóc khách hàng...")
        shopee_cfg = self._store_cfg.get("shopee", {})
        if not shopee_cfg.get("partner_id") or not shopee_cfg.get("partner_key"):
            self.write_log("⚠️ Shopee chưa được cấu hình. Bỏ qua Auto Care.")
            return
        try:
            bot = CustomerCareBot(self._store_cfg, self.store_id)
            result = await asyncio.get_event_loop().run_in_executor(None, bot.process_fulfillment_orders, self._store_cfg)
            self.write_log(f"  {result.get('sent', 0)} tin đã gửi, {result.get('skipped', 0)} bỏ qua")
        except Exception as e:
            self.write_log(f"❌ Lỗi Auto Care: {e}")

    def do_export_cookies(self):
        self.write_log("🍪 Xuất cookies 1688 từ Chrome...")
        try:
            from src.source.ali1688 import extract_chrome_cookies
            cookies = extract_chrome_cookies()
            if cookies:
                self.write_log(f"  ✅ Đã xuất {len(cookies)} cookies (domain: 1688.com)")
                cookie_path = Path("config") / "1688_cookies.json"
                with open(cookie_path, "w", encoding="utf-8") as f:
                    json.dump(cookies, f, ensure_ascii=False, indent=2)
                self.write_log(f"  💾 Đã lưu vào {cookie_path}")
            else:
                self.write_log("  ⚠️ Không tìm thấy cookies 1688 trong Chrome.")
                self.write_log("  Hãy đăng nhập 1688.com trong Chrome trước, hoặc dùng scripts/export_cookies.py")
        except Exception as e:
            self.write_log(f"  ❌ Lỗi: {e}")

    def do_check_shopee(self):
        self.write_log("🔌 Kiểm tra kết nối Shopee API...")
        shopee_cfg = self._store_cfg.get("shopee", {})
        pid = shopee_cfg.get("partner_id", "")
        key = shopee_cfg.get("partner_key", "")
        token = shopee_cfg.get("access_token", "")
        shop_id = shopee_cfg.get("shop_id", "")
        if not pid or not key:
            self.write_log("  ⚠️ Partner ID hoặc Partner Key chưa được cấu hình. Vào Sửa config để nhập.")
            return
        self.write_log(f"  Partner ID: {pid}")
        self.write_log(f"  Shop ID: {shop_id or '(trống)'}")
        self.write_log(f"  Access Token: {'...' + token[-8:] if len(token) > 8 else '(trống)'}")
        try:
            client = ShopeeClient(self._store_cfg)
            result = client._request("GET", "/api/v2/shop/get_shop_info", {})
            if result.get("error") is None or result.get("error") == 0:
                shop_name = result.get("response", {}).get("shop_name", "unknown")
                self.write_log(f"  ✅ Kết nối thành công! Shop: {shop_name}")
            else:
                self.write_log(f"  ❌ Kết nối thất bại: {result.get('message', str(result))}")
            client.close()
        except Exception as e:
            self.write_log(f"  ❌ Lỗi kết nối: {e}")

    @work
    async def run_all(self):
        self.write_log("▶️ Chạy toàn bộ pipeline...")
        await self.run_crawl()
        await self.run_images()
        await self.run_video()
        await self.run_caption()
        await self.run_publish()
        await self.run_cashflow()
        self.write_log("✅ Pipeline hoàn tất! Dùng các nút Hậu mãi cho bước tiếp theo.")

    def on_button_pressed(self, event: Button.Pressed):
        btn_id = event.button.id or ""
        if btn_id == "back":
            self.app.pop_screen()
        elif btn_id == "run-crawl":
            from .confirm import ConfirmScreen
            self.app.push_screen(
                ConfirmScreen("Xác nhận crawl", f"Crawl sản phẩm từ AliExpress/1688 cho store này?", "crawl"),
                lambda ok: self.run_crawl() if ok else None,
            )
        elif btn_id == "run-images":
            self.run_images()
        elif btn_id == "run-video":
            from .confirm import ConfirmScreen
            self.app.push_screen(
                ConfirmScreen("Xác nhận xử lý video", "Tải video gốc, xóa âm thanh và chèn nhạc nền?", "video"),
                lambda ok: self.run_video() if ok else None,
            )
        elif btn_id == "run-caption":
            self.run_caption()
        elif btn_id == "run-pricing":
            from .confirm import ConfirmScreen
            self.app.push_screen(
                ConfirmScreen("Xác nhận cập nhật giá", "So sánh giá với đối thủ trên Shopee?\nSản phẩm không lợi nhuận sẽ bị tạm ẩn.", "pricing"),
                lambda ok: self.run_pricing() if ok else None,
            )
        elif btn_id == "run-publish":
            from .confirm import ConfirmScreen
            self.app.push_screen(
                ConfirmScreen("Xác nhận đăng Shopee", f"Đăng sản phẩm lên Shopee thật? Cần có Partner ID hợp lệ.", "publish"),
                lambda ok: self.run_publish() if ok else None,
            )
        elif btn_id == "run-orders":
            from .confirm import ConfirmScreen
            self.app.push_screen(
                ConfirmScreen("Đồng bộ đơn hàng", "Đồng bộ đơn Shopee sang dữ liệu fulfillment?", "orders"),
                lambda ok: self.run_orders() if ok else None,
            )
        elif btn_id == "run-flashsale":
            from .confirm import ConfirmScreen
            self.app.push_screen(
                ConfirmScreen("Flash Sale", "Đăng ký Flash Sale cho sản phẩm có lợi nhuận?", "flashsale"),
                lambda ok: self.run_flashsale() if ok else None,
            )
        elif btn_id == "run-cashflow":
            from .confirm import ConfirmScreen
            self.app.push_screen(
                ConfirmScreen("Phân tích dòng tiền", "Dự báo vốn lưu động cho tuần tới?", "cashflow"),
                lambda ok: self.run_cashflow() if ok else None,
            )
        elif btn_id == "run-trends":
            from .confirm import ConfirmScreen
            self.app.push_screen(
                ConfirmScreen("Quét xu hướng", "Quét Shopee và 1688 để phát hiện từ khóa nóng?", "trends"),
                lambda ok: self.run_trends() if ok else None,
            )
        elif btn_id == "run-virtualhub":
            from .confirm import ConfirmScreen
            self.app.push_screen(
                ConfirmScreen("Virtual Hub", "Map tracking 1688 sang Shopee và tạo manifest?", "virtualhub"),
                lambda ok: self.run_virtualhub() if ok else None,
            )
        elif btn_id == "run-customercare":
            from .confirm import ConfirmScreen
            self.app.push_screen(
                ConfirmScreen("Auto Care", "Gửi tin nhắn chăm sóc cho đơn hàng?", "customercare"),
                lambda ok: self.run_customercare() if ok else None,
            )
        elif btn_id == "export-cookies":
            from .confirm import ConfirmScreen
            self.app.push_screen(
                ConfirmScreen("Xuất cookies 1688", "Đọc cookies 1688 từ Chrome và lưu vào config?", "cookies"),
                lambda ok: self.do_export_cookies() if ok else None,
            )
        elif btn_id == "check-shopee":
            self.do_check_shopee()
        elif btn_id == "run-all":
            from .confirm import ConfirmScreen
            self.app.push_screen(
                ConfirmScreen("Xác nhận pipeline", f"Chạy toàn bộ: Crawl → Ảnh → Video → Caption → Đăng Shopee?", "all"),
                lambda ok: self.run_all() if ok else None,
            )
