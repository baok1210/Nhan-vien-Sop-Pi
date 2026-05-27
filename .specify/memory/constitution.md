# China Dropship to Shopee — Constitution

## Core Principles

### I. Data Self-Verification (Tối cao)
Đây là nguyên tắc tối cao. Toàn bộ mã nguồn thu thập dữ liệu không được phép bỏ qua lỗi âm thầm. Mọi thực thể dữ liệu đầu ra phải được kiểm chuẩn nghiêm ngặt qua tầng Validation. Nếu thiếu bất kỳ trường thông tin cốt lõi nào (Giá, Mô tả, Tên sản phẩm), hệ thống phải kích hoạt cơ chế dừng khẩn cấp (Fail-Fast) và ném ra ngoại lệ rõ ràng.

### II. Tính module hóa độc lập
Pipeline được chia thành 4 giai đoạn riêng biệt (Crawl, Xử lý ảnh, AI Enrichment, Publisher). Đầu ra của module trước là đầu vào hợp lệ (đã qua kiểm chuẩn) của module sau. Một module lỗi không gây sụp đổ dây chuyền nhưng phải cô lập được tiến trình lỗi.

### III. Bảo mật và cấu hình tập trung
Tuyệt đối không hardcode thông tin nhạy cảm. Toàn bộ API key, token, cấu hình proxy, và tài khoản Shopee phải nằm trong file config/config.json hoặc biến môi trường.

### IV. Kiểm thử bao phủ kịch bản lỗi
Hệ thống kiểm thử tự động (Unit Test) phải mô phỏng được các kịch bản tiêu cực: HTML bị thay đổi cấu trúc, phản hồi thiếu trường dữ liệu, hoặc phản hồi bị chặn bởi hệ thống phòng chống bot (Anti-bot). Tỷ lệ bao phủ mã nguồn (Code coverage) tối thiểu 80%.

## Development Workflow

### Pipeline Execution
- Thứ tự bắt buộc: Crawl → Xử lý ảnh → AI Enrichment → Publish
- Mỗi giai đoạn phải kiểm tra tính toàn vẹn dữ liệu đầu vào trước khi xử lý
- Dữ liệu lỗi phải được ghi log chi tiết kèm nguyên nhân và vị trí HTML/fix

### Quality Gates
- Unit test coverage >= 80%
- Mọi API key phải được injected qua config, không hardcode
- Validation schema bằng Pydantic cho mọi đầu ra crawl

## Governance
- Nguyên tắc Data Self-Verification được ưu tiên cao nhất, không được phép vô hiệu hóa
- Mọi thay đổi validation logic phải kèm unit test chứng minh
- Code review bắt buộc trước khi merge vào module chính

**Version**: 1.0.0 | **Ratified**: 2026-05-27 | **Last Amended**: 2026-05-27
