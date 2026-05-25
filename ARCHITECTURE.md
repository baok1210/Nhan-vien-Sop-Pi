# Architecture: China Dropship -> AI Edit -> Shopee Automation

## Mục tiêu
Tự động hoá hoàn toàn pipeline:
```
Nguồn hàng TQ (1688/Taobao) → Crawl sản phẩm → AI edit ảnh + caption → Đăng lên Shopee
```

---

## 1. TỔNG QUAN PIPELINE

```
┌─────────────────┐     ┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│                 │     │                 │     │                  │     │                 │
│  SOURCE         │────▶│  PROCESSING     │────▶│  AI ENRICHMENT   │────▶│  PUBLISH        │
│                 │     │                 │     │                  │     │                 │
│ • 1688 API      │     │ • Parse data    │     │ • Remove BG      │     │ • Shopee API    │
│ • Taobao API    │     │ • Download ảnh  │     │ • Resize/crop    │     │ • Bulk upload   │
│ • Web scrape    │     │ • Extract info  │     │ • Gen caption VN │     │ • Schedule post │
│ • Pinduoduo     │     │ • Filter SP     │     │ • Translate      │     │ • Multi-store   │
│                 │     │                 │     │ • Gen hashtag    │     │                 │
└─────────────────┘     └─────────────────┘     └──────────────────┘     └─────────────────┘
```

---

## 2. NGUỒN HÀNG DROPSHIP TRUNG QUỐC

### 2.1 Platform chính
| Platform | Loại | Ghi chú |
|----------|------|---------|
| 1688.com | Bán buôn B2B | Tốt nhất cho dropship, có tag "一件代发" |
| Taobao.com | Bán lẻ C2C | Hàng đa dạng, giá tốt |
| Tmall.com | Bán lẻ chính hãng | Chất lượng cao, giá cao hơn |
| Pinduoduo | Bán buôn giá rẻ | Hàng siêu rẻ, phù hợp test |

### 2.2 API Services (trả phí)
| Service | Platform | Giá | Đặc điểm |
|---------|----------|-----|----------|
| **Elimapi** (elim.asia) | 1688/Taobao/Pinduoduo | Theo gói | Chính thức, support VN, 200-500ms |
| **DajiAPI** (dajiapi.cn) | 1688/Taobao | Free 100 req, $100/50k req | Image search, keyword search |
| **TMAPI** (tmapi.top) | 1688/Taobao | Theo gói | Support multilingual, dropship filter |
| **Apify Actors** | Taobao/1688 | Pay per run | Crawler, có free tier |

### 2.3 ERP/Platform dropship trọn gói
| Service | Giá | Tính năng |
|---------|-----|-----------|
| **Keyouyun** (客优云) | Free | 30W+ users, support Shopee, auto translate, auto post |
| **BuckyDrop** | Theo gói | Tự động fulfillment, tracking |
| **Dropast** | $39-89/th | Real-time sync, auto fulfillment |
| **LooperBuy** | Theo gói | Trung gian mua + logistics |

### 2.4 Open Source / Tự build
- Python script dùng `requests` + BeautifulSoup crawl 1688
- Hoặc dùng Oxylabs 1688 Scraper API
- Dùng Apify actors gọi qua REST API

---

## 3. XỬ LÝ ẢNH SẢN PHẨM

### 3.1 Các bước xử lý ảnh
1. **Download** ảnh gốc từ nguồn
2. **Remove background** (xóa nền) → ảnh trong suốt
3. **Thay background** mới (trắng tinh / lifestyle scene)
4. **Resize** về chuẩn Shopee (800x800 hoặc 1000x1000)
5. **Enhance** chất lượng (sharpness, color)
6. **Thêm watermark** (tuỳ chọn)

### 3.2 Công cụ AI xoá nền / edit ảnh

#### Open Source (tự host, miễn phí)
| Tool | Model | Ghi chú |
|------|-------|---------|
| **rembg** (Python) | U2Net | Phổ biến nhất, CLI đơn giản |
| **HoneyClean** | BiRefNet (9 models) | Batch, GPU-accel, MIT license |
| **WithoutBG** | Focus v1.0.0 | CLI + Python API, ONNX |
| **BackgroundRemover** | U2Net | Docker, HTTP API server |

#### API Services (trả phí)
| Service | Giá | Batch | API |
|---------|-----|-------|-----|
| Autophoto.ai | ~$0.10/image | ✅ 5000/batch | ✅ |
| Banana Pro | ~$0.05/image | ✅ | ✅ |
| Crop.photo | Theo gói | ✅ | ✅ |
| Hypotenuse.ai | Theo gói | ✅ | ✅ |
| ShoPPix.io | Free 50 ảnh | ✅ | ✅ |

### 3.3 Pipeline xử lý ảnh đề xuất
```
Ảnh gốc (1688)
    ↓
rembg / HoneyClean ─── Xóa nền
    ↓
Pillow / OpenCV ────── Resize 800x800
    ↓
AI (tuỳ chọn) ──────── Thay background lifestyle
    ↓
Pillow ─────────────── Sharpen + optimize
    ↓
Output: 8-9 ảnh / sản phẩm
```

---

## 4. TẠO CAPTION & MÔ TẢ

### 4.1 Input
- Tên sản phẩm tiếng Trung (từ 1688)
- Đặc điểm kỹ thuật
- Giá gốc
- Danh mục

### 4.2 Output
- **Title**: Tên sản phẩm tiếng Việt (SEO-friendly)
- **Description**: Mô tả chi tiết
- **Bullet points**: 5-7 đặc điểm nổi bật
- **Hashtags**: 10-15 hashtag liên quan

### 4.3 Cách triển khai
| Approach | Chi phí | Chất lượng |
|----------|---------|-----------|
| **OpenAI GPT-4 / Claude** | ~$0.01/sp | Tốt nhất |
| **Google Gemini API** | Free (60 req/min) | Tốt |
| **Qwen2-VL** (self-host) | Free (cần GPU) | Khá |
| **BLIP-2** (HuggingFace) | Free (cần GPU) | Trung bình |
| **Captora.app** | Freemium | Chuyên cho bán hàng |

### 4.4 Prompt template cho caption
```
Bạn là copywriter bán hàng Shopee Việt Nam. Hãy tạo nội dung cho sản phẩm sau:

Tên gốc (TQ): {product_name_cn}
Danh mục: {category}
Giá gốc: {original_price} CNY
Đặc điểm: {features}

Yêu cầu:
1. Title tiếng Việt (tối đa 120 ký tự, có từ khóa SEO)
2. Description (3-4 đoạn, đúng chuẩn bán hàng online)
3. 5 bullet points nổi bật
4. 10 hashtag
```

---

## 5. ĐĂNG LÊN SHOPEE

### 5.1 Shopee Open Platform API v2
- Docs: https://open.shopee.com
- API Product: `v2.product.add_item` - Tạo sản phẩm
- API Media: `v2.media_space.upload_image` - Upload ảnh
- Cần đăng ký App trên Shopee Developer Portal

### 5.2 Luồng đăng sản phẩm
```
1. Get category tree ───── v2.product.get_category
2. Get attributes ──────── v2.product.get_attribute
3. Upload ảnh lên ──────── v2.media_space.upload_image → lấy image_id
4. Tạo sản phẩm ───────── v2.product.add_item
5. Đăng bán ───────────── v2.product.unlist_item (nếu muốn UNLIST trước)
```

### 5.3 SDK có sẵn
| SDK | Ngôn ngữ | Link |
|-----|----------|------|
| **shopee-sdk** | TypeScript | github.com/congminh1254/shopee-sdk |
| Shopee SDK | PHP | github.com/Faiznurullah/shopee |
| Shopee API | Node.js | npm: @shopee/sdk (chính thức) |

### 5.4 Lưu ý quan trọng
- Cần **Partner ID** và **Partner Key** từ Shopee
- Access token có hạn (4h), cần refresh token
- Rate limit: 3000 req/ngày (tuỳ app)
- Shopee có thể duyệt sản phẩm trước khi hiển thị
- Cần chọn đúng category_id + attribute_id

### 5.5 Chiến lược đăng
- Không đăng tràn lan: chọn **ngành hàng ngách** (niche)
- Mỗi shop chỉ nên tập trung 1-3 category liên quan
- Đăng theo lịch (schedule), tránh spam
- Dùng nhiều shop cho nhiều ngách khác nhau

---

## 6. CHIẾN LƯỢC CHỌN NGÀNH HÀNG (NICHE SELECTION)

### 6.1 Tiêu chí chọn ngành
- **Chênh lệch giá** (margin) >= 30%
- **Trọng lượng nhẹ** (< 500g) để tiết kiệm ship
- **Kích thước nhỏ** (dễ vận chuyển)
- **Không dễ hỏng** (không thực phẩm tươi, không chất lỏng)
- **Không vi phạm bản quyền** (no fake brand)
- **Cạnh tranh vừa phải** trên Shopee

### 6.2 Gợi ý ngành hàng ngách
| Ngành | Margin | Trọng lượng | Ghi chú |
|-------|--------|-------------|---------|
| Phụ kiện điện thoại (case, ốp) | 40-60% | 50g | Tốt |
| Trang trí nhà cửa mini | 50-70% | 100g | Tốt |
| Đồ dùng bếp nhỏ | 40-60% | 200g | Ổn |
| Phụ kiện thời trang (túi, ví) | 50-70% | 100g | Tốt |
| Đồ chơi trẻ em (mini) | 40-60% | 150g | Ổn |
| Đồ da dụng thông minh | 40-50% | 200g | Ổn |
| Mỹ phẩm/tools làm đẹp | 50-70% | 100g | Tốt, cần giấy phép |
| Điện tử nhỏ (cáp, adapter) | 30-50% | 50g | Ổn |

### 6.3 Công cụ nghiên cứu ngành hàng
- **Shopee** tự tra: xem top search, top sản phẩm
- **1688** lọc "一件代发" + "跨境" (cross-border)
- **Google Trends** so sánh xu hướng
- **AdSpy / Bigspy** xem quảng cáo đang chạy

---

## 7. TECH STACK ĐỀ XUẤT

### 7.1 Core Pipeline (Python)
- **Python 3.11+** - Ngôn ngữ chính
- **httpx / aiohttp** - HTTP async
- **BeautifulSoup / parsel** - Crawl web fallback
- **Pillow / OpenCV** - Xử lý ảnh cơ bản
- **rembg** - Xoá nền (open source)
- **Pydantic** - Data models

### 7.2 Database
- **SQLite** → Đủ dùng cho MVP
- **PostgreSQL** → Khi scale

### 7.3 Queue & Scheduler
- **APScheduler** → Cron-based scheduling
- **Celery + Redis** → Khi cần queue (optional)

### 7.4 AI/API
- **OpenAI API** hoặc **Google Gemini** → Caption + dịch
- **rembg / HoneyClean** → Xử lý ảnh
- **Shopee SDK (TS)** → Đăng sản phẩm

### 7.5 Deployment
- **Docker** → Container hóa
- **VPS rẻ** (5$-10$ tháng) → Host pipeline
- **GitHub Actions** → CI/CD

---

## 8. KẾ HOẠCH TRIỂN KHAI (TỪNG BƯỚC)

### Phase 1: Foundation (Tuần 1-2)
```
[ ] Nghiên cứu ngành hàng, chọn niche đầu tiên
[ ] Setup project Python với cấu trúc thư mục chuẩn
[ ] Viết script crawl 1688 (search theo keyword)
[ ] Parse data sản phẩm (tên, giá, ảnh, mô tả)
[ ] Lưu vào SQLite
```

### Phase 2: Xử lý ảnh (Tuần 3-4)
```
[ ] Tích hợp rembg / HoneyClean xoá nền batch
[ ] Resize + optimize ảnh chuẩn Shopee
[ ] Optional: Thay background cho ảnh lifestyle
[ ] Download + process tự động khi crawl xong
```

### Phase 3: Caption & AI (Tuần 5-6)
```
[ ] Tích hợp Google Gemini API / OpenAI
[ ] Tạo prompt chuẩn cho caption tiếng Việt
[ ] Translate + optimize title SEO
[ ] Sinh hashtag tự động
```

### Phase 4: Shopee Integration (Tuần 7-8)
```
[ ] Đăng ký Shopee Developer App
[ ] Test upload ảnh + tạo sản phẩm qua API
[ ] Build module đăng sản phẩm
[ ] Test với 10 sản phẩm thật
[ ] Xử lý lỗi, rate limit, refresh token
```

### Phase 5: Tự động hoá & Scale (Tuần 9-12)
```
[ ] Build scheduler (đăng theo lịch)
[ ] Multi-store support
[ ] Auto review sản phẩm sau khi đăng
[ ] Monitoring: Telegram bot báo trạng thái
[ ] Dockerize toàn bộ pipeline
[ ] Deploy lên VPS
```

---

## 9. PROJECT STRUCTURE

```
china-dropship-to-shopee/
├── config/
│   ├── config.json              # Cấu hình chính
│   └── niches.yaml              # Cấu hình ngành hàng
├── src/
│   ├── __init__.py
│   ├── main.py                  # Entry point
│   ├── source/
│   │   ├── base.py              # Base scraper
│   │   ├── ali1688.py           # 1688 API/scraper
│   │   └── taobao.py            # Taobao API/scraper
│   ├── processing/
│   │   ├── image_processor.py   # Xử lý ảnh hàng loạt
│   │   ├── bg_remover.py        # Xoá nền
│   │   └── text_translate.py    # Translate + optimize
│   ├── ai/
│   │   ├── caption_gen.py       # Tạo caption
│   │   └── hashtag_gen.py       # Sinh hashtag
│   ├── publisher/
│   │   └── shopee.py            # Shopee API integration
│   ├── models/
│   │   └── product.py           # Data models
│   └── utils/
│       ├── image_utils.py       # Helper xử lý ảnh
│       └── logger.py            # Logging
├── scripts/
│   ├── crawl_products.py        # Crawl sản phẩm
│   ├── process_images.py        # Xử lý ảnh batch
│   ├── generate_captions.py     # Tạo caption batch
│   └── post_to_shopee.py        # Đăng lên Shopee
├── data/
│   ├── raw/                     # Dữ liệu crawl raw
│   ├── processed/               # Dữ liệu đã xử lý
│   └── images/                  # Ảnh sản phẩm
├── storage/
│   └── db.sqlite                # Database
├── logs/                        # Log files
├── tests/                       # Unit tests
├── docker-compose.yml           # Docker deployment
├── requirements.txt             # Python dependencies
└── README.md                    # Hướng dẫn
```

---

## 10. RỦI RO & GIẢI PHÁP

| Rủi ro | Giải pháp |
|--------|-----------|
| Shopee block API | Dùng nhiều app, rotate |
| 1688 block IP | Dùng proxy, delay giữa request |
| Chất lượng ảnh gốc kém | AI upscale (Real-ESRGAN) |
| Vi phạm bản quyền | Check kỹ brand, viết lại mô tả |
| Dropship shipping lâu | Đặt pre-order, thông báo rõ |
| Hàng lỗi/không như ảnh | Chọn supplier có rating > 4.5 |
| Cạnh tranh mạnh | Chọn niche nhỏ, unique content |
| Chi phí AI cao | Dùng open source (rembg, Gemini free) |
