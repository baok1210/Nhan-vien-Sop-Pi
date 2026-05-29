# Feature Specification: China Dropship to Shopee — Pipeline tự động hoá

## 1. Mục tiêu (What)
Hệ thống tự động hóa hoàn toàn quy trình Dropshipping từ Trung Quốc (1688.com, AliExpress) về Shopee Việt Nam. Hệ thống thực hiện việc quét dữ liệu, bóc tách thông tin có kiểm chuẩn chất lượng, tự động xử lý đồ họa (xóa nền, chèn watermark), sử dụng LLM để tối ưu và dịch thuật nội dung chuẩn SEO, sau đó đồng bộ trực tiếp lên gian hàng Shopee thông qua API. Hệ thống được quản lý song song bằng giao diện đồ họa Web (Flask) và giao diện dòng lệnh (Textual TUI).

## 2. Lý do xây dựng (Why)
- **Triệt tiêu rủi ro dữ liệu rác**: Loại bỏ tình trạng sản phẩm đăng lên Shopee bị thiếu giá, thiếu mô tả hoặc sai thông tin phân loại do bot crawl bị chặn hoặc quét sót.
- **Tối ưu hóa hiệu suất**: Chuyển đổi quy trình thủ công phức tạp (tải ảnh, dịch thuật, tính giá, đăng bán) thành một chu trình tự động khép kín.
- **Đảm bảo tính sẵn sàng của dữ liệu**: Kiểm tra tính toàn vẹn của thông tin nhà cung cấp trước khi thực hiện các bước xử lý tốn tài nguyên (gọi API AI, xử lý ảnh).

## 3. Kiến trúc tổng quan (4-Stage Pipeline)

```
Stage 1 (CRAWL)     → Stage 2 (PROCESS)    → Stage 3 (AI ENRICH)  → Stage 4 (PUBLISH)
1688 (curl_cffi)    → Download images      → Remove BG             → Shopee API v2
AliExpress          → Resize/crop          → Gen caption VN        → Upload image
Cookie auth         → Sharpen              → Translate             → Add item
                    → Watermark            → Gen hashtag           → Multi-store
```

## 4. User Stories

### P1 - MVP
- **US-01**: Crawl sản phẩm từ 1688 và AliExpress với tự kiểm chuẩn dữ liệu (Price > 0, Title không rỗng, Description >= 50 ký tự)
- **US-02**: Xử lý ảnh tự động (download → xóa nền → resize 800x800 → watermark)
- **US-03**: Sinh caption tiếng Việt bằng AI (Gemini/OpenAI) với fallback template
- **US-04**: Đăng sản phẩm lên Shopee qua API v2 (HMAC-SHA256)

### P2 - Nâng cao
- **US-05**: Phát hiện và xử lý Anti-bot (x5sec, CAPTCHA) bằng proxy rotation
- **US-06**: Module dịch thuật multi-stage (từ điển → AI → template fallback)
- **US-07**: Refactor TUI từ 1 file thành cấu trúc thư mục module

### P3 - Mở rộng
- **US-08**: Dashboard Web UI (Flask) real-time monitoring
- **US-09**: Multi-store management với config riêng biệt
- **US-10**: Trend detection và competitor pricing

## 5. Yêu cầu phi chức năng
- Validation đầu vào bằng Pydantic schemas
- Zero silent failure: mọi lỗi crawl phải được log và ném exception
- API keys chỉ lưu trong config JSON, không hardcode
- Unit test coverage >= 80%
- Hỗ trợ cả Web UI (Flask port 5000) và TUI (Textual)
