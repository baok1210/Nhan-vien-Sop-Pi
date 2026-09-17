# China Dropship to Shopee

Tự động tìm kiếm sản phẩm từ **1688.com** và **AliExpress**, xử lý ảnh, tạo mô tả tiếng Việt, và đăng lên **Shopee** — tất cả chỉ với vài cú click.

## Tính năng

- **Crawl tự động** — Tìm sản phẩm từ 1688.com và AliExpress (API chính thức)
- **Kiểm tra dữ liệu** — Tự động validate giá, tên, mô tả trước khi xử lý
- **Xóa nền ảnh** — Tự động xóa phông, thêm watermark, chống trùng ảnh
- **Tạo caption tiếng Việt** — Dùng Google Gemini AI hoặc từ điển mẫu
- **Đăng Shopee** — Đăng sản phẩm lên Shopee tự động qua API
- **Web UI** — Giao diện web trực quan, chạy trên localhost

## Cài đặt

### Yêu cầu

- Windows 10/11
- Python 3.11 trở lên
- Chrome (để lấy cookie 1688)

### Cách cài (1 phút)

**Cách 1: Double-click**

| File | Click để |
|------|----------|
| `1-Cai-dat-lan-dau.bat` | Cài đặt + nhập thông tin |
| `2-Chay-Web-UI.bat` | Mở Web UI |

**Cách 2: Gõ lệnh**

```bash
python scripts\setup.py
python scripts\run_web.py
```

## Sử dụng

### Mở Web UI

```bash
python scripts\run_web.py
```

Mở trình duyệt: **http://localhost:5000**

### Web UI có 4 trang

| Trang | URL | Chức năng |
|-------|-----|-----------|
| Dashboard | `/` | Tổng quan cấu hình, cảnh báo |
| Crawl | `/crawl` | Bắt đầu crawl, xem log realtime |
| Sản phẩm | `/products` | Danh sách sản phẩm đã crawl |
| Cấu hình | `/config` | Sửa cấu hình JSON |

### Giao diện Terminal (TUI)

```bash
python scripts\run.py
```

### Web UI FastAPI (bản cũ, tuỳ chọn)

```bash
python -m uvicorn src.web.app:app --port 7860
```

### Chạy từng bước riêng

```bash
python scripts\crawl_products.py    # Bước 1: Crawl
python scripts\process_images.py    # Bước 2: Xử lý ảnh
python scripts\generate_captions.py # Bước 3: Tạo caption
python scripts\post_to_shopee.py    # Bước 4: Đăng Shopee
python src\main.py                  # Chạy toàn bộ pipeline
```

## Cấu hình

### File cấu hình

| File | Chức năng | Commit lên Git? |
|------|-----------|-----------------|
| `config/config.example.json` | Template cấu hình mẫu | ✅ Có |
| `config/config.json` | Cấu hình thật của bạn (từ `setup.py` tự tạo) | ❌ Không |
| `config/stores/*.json` | Cấu hình từng store | ❌ Không |
| `.env.example` | Template API keys | ✅ Có |
| `.env` | API keys, bí mật thật (từ `setup.py` tự tạo) | ❌ Không |
| `config/*_cookies.*`, `data/shopee_cookies.json` | Cookie đăng nhập (cục bộ) | ❌ Không — **không bao giờ commit** |

> 🔒 **Bảo mật:** Cookie Shopee/1688/AliExpress và file cấu hình cá nhân nằm ngoài Git.
> Nếu bạn từng commit nhầm cookie, hãy **đăng xuất khỏi mọi thiết bị** trên dịch vụ đó để vô hiệu phiên cũ.

### Chuẩn bị API keys

| Dịch vụ | Link đăng ký | Phí |
|---------|-------------|-----|
| Google Gemini | https://aistudio.google.com/apikey | **Miễn phí** (60 req/phút) |
| AliExpress API | https://openservice.aliexpress.com | **Miễn phí** |
| Shopee API | https://open.shopee.com | Miễn phí |
| 1688.com | Đăng nhập 1 lần bằng lệnh bên dưới | Miễn phí |

### Hướng dẫn nhanh

1. **1688**: Chạy `python scripts\login_source.py 1688` → cửa sổ mở ra → đăng nhập bằng tay **1 lần duy nhất**. Tool tự lưu profile + cookie. Cửa sổ Chrome sẽ tự mở mỗi khi crawl — nếu 1688 hỏi xác minh (slider), kéo slider là tool tự chạy tiếp
2. **Gemini**: Vào [aistudio.google.com](https://aistudio.google.com/apikey) → Generate API key → dán vào `.env`
3. **AliExpress API**: Vào [openservice.aliexpress.com](https://openservice.aliexpress.com) → Tạo App → lấy App Key + Secret
4. **Shopee API**: Vào [open.shopee.com](https://open.shopee.com) → Đăng ký App → lấy Partner ID + Key

## Kiến trúc

```
src/
├── main.py                  # Pipeline chính (4 giai đoạn)
├── source/
│   ├── ali1688.py           # Crawler 1688 (cookie + Playwright)
│   ├── aliexpress.py        # Crawler AliExpress (web)
│   └── aliexpress_api.py    # AliExpress API chính thức
├── models/product.py        # ProductSchema (Pydantic validation)
├── web/                     # Web UI (FastAPI — bản cũ)
├── webui/                   # Web UI Flask chính (port 5000)
│   ├── app.py
│   └── templates/
├── tui/                     # Terminal UI (Textual)
├── ai/                      # Gemini AI integration
├── processing/              # Ảnh, video, dịch thuật
└── publisher/               # Shopee, đơn hàng, flash sale
```

## Phát triển

```bash
# Chạy test
python -m pytest tests/ -v

# Cấu trúc
python -m pytest tests/ --cov=src
```

## License

MIT
