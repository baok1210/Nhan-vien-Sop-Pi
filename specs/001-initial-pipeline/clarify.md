# Clarification: China Dropship to Shopee Pipeline

## Câu hỏi 1: Xử lý Anti-bot
**Q**: Khi 1688 hoặc AliExpress trả về mã CAPTCHA/x5sec dẫn đến việc không crawl được Giá hoặc Mô tả, hệ thống sẽ sử dụng cơ chế giải mã tự động (2Captcha/CapSolver) hay thực hiện đổi IP Proxy xoay vòng ngay lập tức?

**A**: Sử dụng proxy rotation + User-Agent rotation trước; nếu vẫn bị chặn thì dùng Playwright full browser làm fallback. Tích hợp 2Captcha/CapSolver trong tương lai (P3).

## Câu hỏi 2: Ngưỡng chặn dữ liệu rác
**Q**: Thuộc tính sản phẩm (Attributes) thiếu bao nhiêu % thì coi như sản phẩm đó lỗi hoàn toàn và hủy bỏ tiến trình?

**A**: Nếu thiếu bất kỳ trường cốt lõi nào (price <= 0, title rỗng, description < 50 ký tự) → Fail-Fast ngay. Các trường phụ (category, images) thiếu thì ghi log warning và vẫn tiếp tục.

## Câu hỏi 3: Môi trường Shopee API
**Q**: Hệ thống sẽ triển khai trực tiếp trên ứng dụng Shopee Live (Production) với tài khoản doanh nghiệp, hay chạy qua môi trường kiểm thử Sandbox?

**A**: Phát triển trên Sandbox (UAT) trước. Chuyển sang Production sau khi test thành công 10 sản phẩm.
