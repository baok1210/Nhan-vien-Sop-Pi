# Implementation Plan: China Dropship to Shopee Pipeline

## Summary
Xây dựng pipeline 4 giai đoạn với Data Self-Verification, Pydantic validation, và module hóa độc lập.

## Technical Context

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Ngôn ngữ | Python 3.11+ | Runtime chính |
| Validation | Pydantic | Schema + ép kiểu bắt buộc |
| Crawl | curl_cffi | TLS/JA3 impersonation |
| Crawl fallback | Playwright | Full browser cho CAPTCHA |
| Image | rembg + Pillow | Xóa nền, resize 800x800, watermark |
| AI Caption | Google Gemini API / OpenAI | Sinh caption SEO tiếng Việt |
| Translation | Từ điển _CN_VI_DICT → Gemini → template | Fallback 3 tầng |
| Web UI | Flask (port 5000) | Dashboard quản lý |
| TUI | Textual | Terminal UI |
| Testing | pytest + pytest-mock | Mock HTML lỗi, anti-bot |
| Config | JSON + python-dotenv | API keys tập trung |
| Deploy | Docker | Container hóa |

## Lịch trình triển khai

| Giai đoạn | Nội dung | Thời gian |
|-----------|----------|-----------|
| Phase 1 | Pydantic Schema + Self-Verification Crawl + Anti-bot | Tuần 1 |
| Phase 2 | Refactor TUI module + Translation fallback | Tuần 2 |
| Phase 3 | Unit test (7 files) với mock scenarios | Tuần 3 |
| Phase 4 | Shopee API v2 + Docker + Extended features | Tuần 4 |

## Ràng buộc
- Zero silent failure: mọi thiếu sót dữ liệu phải fail-fast
- Không hardcode API keys
- Module độc lập: lỗi 1 module không sập toàn pipeline
