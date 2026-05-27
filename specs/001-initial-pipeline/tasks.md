# Tasks: China Dropship to Shopee Pipeline

## [TASK-01] [P1] Định nghĩa ProductSchema bằng Pydantic
- **File**: `src/models/product.py`
- **Nội dung**: Định nghĩa `ProductSchema` bằng pydantic với các trường:
  - `price: float` (must be > 0)
  - `title_cn: str` (must not be empty)
  - `description_cn: str` (must be >= 50 ký tự)
  - `image_urls: list[str]` (optional)
  - `supplier_name: str` (optional)
- **Validation**: Ném `ValidationError` nếu không thỏa điều kiện

## [TASK-02] [P1] Viết lại parser 1688 + AliExpress với self-verification
- **File**: `src/source/ali1688.py`, `src/source/aliexpress.py`
- **Nội dung**: 
  - Thêm khối kiểm chuẩn dữ liệu bằng Pydantic sau khi parse HTML
  - Nếu `ValidationError` → log chi tiết thẻ HTML bị thiếu, dừng sản phẩm đó
  - Rotate User-Agent mỗi lần retry

## [TASK-03] [P2] Refactor TUI từ 1 file thành cấu trúc module
- **File**: `src/tui/app.py` → tách thành `src/tui/app.py`, `src/tui/screens/`, `src/tui/widgets/`
- **Nội dung**: Mỗi màn hình (MainMenu, StoreList, StoreDetail, BrowseCrawl, Discovery) thành file riêng

## [TASK-04] [P2] Module dịch thuật multi-stage fallback
- **File**: `src/ai/translator.py`
- **Nội dung**: 
  - Tầng 1: Tra từ điển `_CN_VI_DICT`
  - Tầng 2: Gọi Google Gemini API
  - Tầng 3: Template mặc định
  - Ghi log tầng nào được dùng

## [TASK-05] [P3] Viết unit test với pytest + pytest-mock
- **File**: `tests/test_ali1688.py`, `tests/test_aliexpress.py`, `tests/test_image_processor.py`
- **Nội dung**:
  - Mock HTML thiếu thẻ price, description, title
  - Kiểm tra `ValidationError` được ném đúng
  - Test anti-bot response handling
  - Coverage >= 80%
