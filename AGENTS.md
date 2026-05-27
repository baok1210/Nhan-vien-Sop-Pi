# Design Rules

## Web UI
- Flask web UI on port 5000; all features must have web UI access.
- Do NOT hardcode API keys or secrets in source code; users enter them via UI fields.
- User's API keys are stored in per-store config JSON, never in Python source.

## Pipeline Steps
- Order: 1.Crawl → 2.Ảnh → 3.Video → 4.Caption → 5.Đăng
- Each step button has a `title` tooltip explaining what it does.
- Clicking a step opens a modal (`openStepConfig`) with description + configurable fields before running.
- Step config fields pre-fill from saved per-store config; changes auto-save to config when "Chạy" is clicked.

## Vietnamese
- All UI text must use proper Vietnamese diacritics (đầy đủ dấu).
- The user enters Vietnamese keywords; the system auto-translates to Chinese (for 1688) and English (for AliExpress).

## Error Messages
- Never silently return 0 or empty results. Check dependencies upfront and show a clear log message with ⚠️ explaining what's missing and how to fix it.
- Features that need Shopee API credentials check `partner_id`, `partner_key`, `shop_id` before running.

## Config Persistence
- User-entered params in step config modals are saved to the store's `config.json` immediately when the step runs.
- The store card on dashboard loads saved config values via HTML `data-*` attributes so the modal pre-fills them on next open.
- Per-store config is stored in `config/stores/{store_id}.json`.

## Data Flow
Actual data must be real; never generate dummy/mock data for testing UI.
- Pipeline data flows: crawl → product_pool.json → images → products_with_images.json → caption → captions.json → pricing → pricing_report.json → publish → published.json
- Downstream features (orders, cashflow, flashsale, virtualhub, CSKH) all depend on upstream pipeline steps and/or Shopee API credentials.
- Trend detection needs ≥3 scan cycles before detecting spikes.

## Code Quality Rules
- `asyncio.get_running_loop()` + `run_coroutine_threadsafe` pattern is deprecated — use `asyncio.run()` directly in non-async contexts.
- Scrapers must rotate User-Agent and impersonation on each retry.
- Translation uses built-in dictionary (`_CN_VI_DICT` in text_translate.py) before falling back to AI.
- Download URLs must validate extension via `_get_ext()` (accepts: jpg/jpeg/png/webp/gif/bmp).
- Exchange rate cache uses JSON file (not SQLite).
- CLI scripts use `argparse` (not raw `sys.argv`).
- Docker deployment via `docker-compose.yml` (volume-mounts: config, data, logs, assets).

<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
<!-- SPECKIT END -->
