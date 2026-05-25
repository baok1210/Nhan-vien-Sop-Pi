# Project Scope Document: China Dropship to Shopee

## 1. Project Name & Goal

**Project Name:** China Dropship to Shopee

**Goal:** Build a fully automated pipeline that discovers, crawls, processes, and publishes Chinese-source products (from 1688.com and AliExpress) to Shopee Vietnam stores. The system uses AI for image processing (background removal, resizing) and Vietnamese caption generation (translation, SEO title, bullet points, hashtags), then publishes via the Shopee Open Platform API v2. It supports multi-store management, niche discovery, and a full Textual-based TUI (Terminal User Interface) for interactive control.

---

## 2. Architecture Overview - 4-Stage Pipeline

```
+-------------------+     +-------------------+     +--------------------+     +-------------------+
|  STAGE 1          |     |  STAGE 2          |     |  STAGE 3           |     |  STAGE 4          |
|  CRAWL            |---->|  PROCESS          |---->|  AI ENRICHMENT     |---->|  PUBLISH           |
|                   |     |                   |     |                    |     |                   |
| * 1688 (curl)     |     | * Download images |     | * Remove BG        |     | * Shopee API       |
| * AliExpress      |     | * Resize/crop     |     | * Gen caption VN   |     | * Upload image     |
| * Phantom JS      |     | * Sharpen         |     | * Translate        |     | * Add item         |
| * Broad crawl     |     |                   |     | * Gen hashtag      |     | * Multi-store      |
+-------------------+     +-------------------+     +--------------------+     +-------------------+
```

1. **Stage 1 - CRAWL:** Fetch product listings from 1688.com (via cookie-authenticated curl_cffi) and AliExpress (via direct curl_cffi with anti-bot detection). Products are serialized to JSON.
2. **Stage 2 - PROCESS IMAGES:** Download raw product images via httpx async client. Apply optional background removal (rembg), resize to Shopee standard (800x800), and compose onto white background. Output JPEG files.
3. **Stage 3 - AI ENRICHMENT:** Translate Chinese titles to Vietnamese (via googletrans or AI API). Generate SEO-optimized Vietnamese title, description, bullet points, and hashtags using Google Gemini (or OpenAI). Falls back to template-based generation if no API key is configured.
4. **Stage 4 - PUBLISH:** Upload processed images to Shopee Media Space, create product items via Shopee Open Platform API v2 (add_item), and optionally publish (unlist_item). All API calls are HMAC-SHA256 signed.

---

## 3. Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Language | Python 3.11+ | Primary runtime |
| Scraping | curl_cffi (>=0.7) | Impersonates Chrome 120 - bypasses basic TLS fingerprinting |
| Scraping (fallback) | Playwright (>=1.60) | Full browser for 1688 CAPTCHA handling |
| Parsing | BeautifulSoup4, parsel, lxml | HTML extraction + CSS selectors |
| Async HTTP | httpx (>=0.27) | Image downloading + Shopee API calls |
| Image Processing | Pillow (>=10.0) | Resize, composite, sharpen, format conversion |
| BG Removal | rembg (>=0.3, optional) | U2Net model for background removal |
| AI Caption | google-generativeai / openai (optional) | Gemini / GPT for Vietnamese caption generation |
| Translation | googletrans (>=4.0.2) | Fallback CN to VI translation |
| Scheduling | APScheduler (>=3.10) | Cron-based crawl/publish scheduling |
| Data Models | Pydantic (>=2.0) | listed in reqs but not used (dataclasses used instead) |
| Database | SQLite3 (built-in) | Chrome cookie extraction |
| TUI | Textual | Terminal-based interactive UI |
| Auth | HMAC-SHA256 | Shopee API signing |
| Config | JSON | Store configs, main config |
| Env/Dotenv | python-dotenv (>=1.0) | Environment variable management |

---

## 4. Directory Structure

```
C:\project\china-dropship-to-shopee\
|
|-- ARCHITECTURE.md                          # Architecture document (bilingual VN/EN)
|-- analysis_results.json                    # Output of 1688 endpoint analysis
|-- requirements.txt                         # Python dependencies
|
|-- config/
|   |-- config.json                          # Main pipeline configuration
|   |-- config.example.json                  # Template copy
|   +-- stores/
|       |-- example.json                     # Example: phone accessories
|       |-- cho-meo.json                     # Store: pet supplies
|       |-- dien-gia-dung.json               # Store: smart home electronics
|       +-- leo-nui.json                     # Store: climbing/hiking gear
|
|-- data/
|   |-- raw/
|   |   +-- products.json                    # Raw crawl output
|   +-- dien-gia-dung/
|       |-- products.json
|       |-- products_with_images.json
|       |-- captions.json
|       +-- images/
|           |-- raw/
|           +-- processed/
|
|-- logs/
|   +-- pipeline.log
|
|-- scripts/
|   |-- run.py                               # TUI launcher
|   |-- crawl_products.py                    # CLI crawl
|   |-- process_images.py                    # CLI images
|   |-- generate_captions.py                 # CLI captions
|   |-- post_to_shopee.py                    # CLI publish
|   +-- export_cookies.py                    # Chrome cookie exporter
|
|-- src/
|   |-- __init__.py
|   |-- main.py                              # Programmatic entry point
|   |-- classifier.py                        # Category classifier
|   |-- config_manager.py                    # Store CRUD
|   |-- discovery.py                         # Niche discovery
|   |
|   |-- source/
|   |   |-- __init__.py
|   |   |-- base.py                          # Abstract base scraper
|   |   |-- browser.py                       # Playwright manager (UNUSED)
|   |   |-- ali1688.py                       # 1688.com scraper
|   |   +-- aliexpress.py                    # AliExpress scraper
|   |
|   |-- models/
|   |   |-- __init__.py
|   |   +-- product.py                       # Dataclasses
|   |
|   |-- processing/
|   |   |-- __init__.py
|   |   |-- image_processor.py               # Image download + process
|   |   +-- text_translate.py                # CN to VI translation
|   |
|   |-- ai/
|   |   |-- __init__.py
|   |   +-- caption_gen.py                   # AI caption generator
|   |
|   |-- publisher/
|   |   |-- __init__.py
|   |   +-- shopee.py                        # Shopee API client
|   |
|   |-- utils/
|   |   |-- __init__.py
|   |   +-- logger.py                        # Dual-output logger
|   |
|   +-- tui/
|       |-- __init__.py
|       |-- app.py                           # Textual app (all screens)
|       +-- screens/
|           +-- __init__.py                  # Empty
|
+-- test_dl/
```

---

## 5. Module Inventory

### 5.1 src/main.py
| Export | Type | Purpose | State |
|--------|------|---------|-------|
| load_config(path) | function | Load main config JSON | WORKING |
| run_crawl(config) | function | Crawl 1688 + AliExpress | WORKING |
| run_process_images(config, products) | function | Process images (5 limit) | WORKING |
| run_generate_captions(config, products) | function | Generate captions (5 limit) | WORKING |
| run_publish(config, products) | function | Publish to Shopee (2 limit) | WORKING |

### 5.2 src/classifier.py
| Export | Type | Purpose | State |
|--------|------|---------|-------|
| NICHE_CATEGORIES | dict | 11 categories with keywords + icons | WORKING |
| classify_product() | function | Keyword-based category scoring | WORKING |
| classify_products() | function | Batch classification | WORKING |

### 5.3 src/config_manager.py
| Export | Type | Purpose | State |
|--------|------|---------|-------|
| list_stores() | function | List store IDs | WORKING |
| load_store(id) | function | Load store config | WORKING |
| save_store(id, data) | function | Write store config | WORKING |
| delete_store(id) | function | Delete store config | WORKING |
| create_store(id, name) | function | Create default config | WORKING |

### 5.4 src/discovery.py
| Export | Type | Purpose | State |
|--------|------|---------|-------|
| load_pool() | function | Load product pool | WORKING |
| save_pool() | function | Save product pool | WORKING |
| add_to_pool() | function | Dedup + classify + append | WORKING |
| discover_niches() | function | Cluster pool into categories | WORKING |
| create_shop_from_suggestion() | function | Generate store config | WORKING |

### 5.5 src/source/ali1688.py - BUGGY
| Export | Type | Purpose | State |
|--------|------|---------|-------|
| extract_chrome_cookies() | function | Read Chrome cookies | WORKING |
| Ali1688Scraper.search() | method | HTTP GET search | BUGGY |
| Ali1688Scraper._parse_products() | method | Parse results | BUGGY |
| Ali1688Scraper.crawl_by_keywords() | method | Iterate keywords | WORKING |

### 5.6 src/source/aliexpress.py - BUGGY
| Export | Type | Purpose | State |
|--------|------|---------|-------|
| AliExpressScraper.search() | method | HTTP GET search | BUGGY |
| AliExpressScraper._parse_products() | method | Parse results | WORKING |
| AliExpressScraper.crawl_by_keywords() | method | Iterate keywords | WORKING |

### 5.7 src/source/base.py
| Export | Type | Purpose | State |
|--------|------|---------|-------|
| BaseSource | class | Abstract base class | WORKING |

### 5.8 src/source/browser.py - UNUSED
| Export | Type | Purpose | State |
|--------|------|---------|-------|
| BrowserManager | class | Playwright launcher | WORKING |

### 5.9 src/models/product.py
| Export | Type | Purpose | State |
|--------|------|---------|-------|
| ProductSource | dataclass | Raw product data | WORKING |
| ProductProcessed | dataclass | Processed product data | WORKING |
| ShopeeProduct | dataclass | Shopee-bound product | WORKING |

### 5.10 src/processing/image_processor.py - BUGGY
| Export | Type | Purpose | State |
|--------|------|---------|-------|
| ImageProcessor | class | Async download + PIL processing | WORKING |
| download_images() | method | Async httpx download | BUGGY |
| process_single() | method | BG removal + resize | WORKING |
| process_batch() | method | Batch processing | WORKING |

### 5.11 src/processing/text_translate.py - BUGGY
| Export | Type | Purpose | State |
|--------|------|---------|-------|
| TextTranslator | class | googletrans-based translation | BUGGY |
| translate() | method | Sync wrapper | BUGGY |
| translate_async() | method | Async translation | BUGGY |

### 5.12 src/ai/caption_gen.py - STUB (no API key)
| Export | Type | Purpose | State |
|--------|------|---------|-------|
| CAPTION_PROMPT | str | Prompt template | WORKING |
| CaptionGenerator | class | Caption generation | WORKING |
| generate() | method | Dispatcher | WORKING |
| _generate_gemini() | method | Gemini API | STUB |
| _generate_openai() | method | OpenAI API | STUB |
| _generate_template() | method | Template fallback | WORKING |

### 5.13 src/publisher/shopee.py - UNCONFIGURED
| Export | Type | Purpose | State |
|--------|------|---------|-------|
| ShopeeClient | class | Shopee API v2 client | WORKING |
| _sign() | method | HMAC-SHA256 | WORKING |
| _request() | method | Signed HTTP | WORKING |
| upload_image() | method | Media upload | WORKING |
| get_categories() | method | Category list | WORKING |
| add_item() | method | Create product | WORKING |
| publish_item() | method | Publish product | WORKING |

### 5.14 src/utils/logger.py
| Export | Type | Purpose | State |
|--------|------|---------|-------|
| setup_logger() | function | Dual-handler logger | WORKING |

### 5.15 src/tui/app.py - ALL SCREENS IN ONE FILE
| Export | Type | Purpose | State |
|--------|------|---------|-------|
| ConfirmScreen | class | Confirmation dialog | WORKING |
| MainMenuScreen | class | Main menu | WORKING |
| BrowseCrawlScreen | class | Broad crawl | WORKING |
| DiscoveryScreen | class | Niche discovery | WORKING |
| SuggestionCard | class | Niche card widget | WORKING |
| StoreListScreen | class | Store list | WORKING |
| StoreCard | class | Store card widget | WORKING |
| StoreFormScreen | class | Add store form | WORKING |
| StoreEditScreen | class | Edit store config | WORKING |
| StoreDetailScreen | class | Per-store pipeline | WORKING |
| PipelineApp | class | Root Textual App | WORKING |

### 5.16 Scripts
| File | Purpose | State |
|------|---------|-------|
| scripts/run.py | TUI launcher | WORKING |
| scripts/crawl_products.py | CLI crawl | WORKING |
| scripts/process_images.py | CLI images | WORKING |
| scripts/generate_captions.py | CLI captions | WORKING |
| scripts/post_to_shopee.py | CLI publish | WORKING |
| scripts/export_cookies.py | Cookie export | WORKING |

### 5.17 Config files
| File | State |
|------|-------|
| config/config.json | STUB (keys empty) |
| config/config.example.json | STUB |
| config/stores/example.json | STUB |
| config/stores/cho-meo.json | STUB (no Shopee keys) |
| config/stores/dien-gia-dung.json | STUB (no Shopee keys) |
| config/stores/leo-nui.json | STUB (no Shopee keys) |

### 5.18 Data files
| File | State |
|------|-------|
| data/raw/products.json | WORKING (low quality - empty titles) |
| data/dien-gia-dung/products.json | WORKING (1 product) |
| data/dien-gia-dung/products_with_images.json | WORKING |
| data/dien-gia-dung/captions.json | WORKING (template, low quality) |

---

## 6. Data Flow

### File Format: JSON

```
Stage 1 (CRAWL):
  Input:  config / store config
  Output: data/raw/products.json or data/<store_id>/products.json
  Format: [ {id, title_cn, price_cny, image_urls[], description_cn, ...} ]

Stage 2 (PROCESS IMAGES):
  Input:  data/<store_id>/products.json
  Output: images/raw/*, images/processed/*/*, products_with_images.json

Stage 3 (AI ENRICHMENT):
  Input:  products_with_images.json (fallback products.json)
  Output: captions.json
  Format: [ {product_id, title_vi, description, bullet_points[], hashtags[]} ]

Stage 4 (PUBLISH):
  Input:  captions.json + store config
  Output: published.json
  Side effect: Shopee API calls (image upload + add_item)

Product Pool: data/product_pool.json
  Accumulated, deduplicated (by ID), classified products from broad crawls.
```

---

## 7. TUI Screens

| Screen | Class | Purpose |
|--------|-------|---------|
| Main Menu | MainMenuScreen | Pool/stores count, Crawl/Discover/Manage buttons |
| Confirm | ConfirmScreen | Yes/no confirmation dialog |
| Browse Crawl | BrowseCrawlScreen | 50 keywords across 11 niches, real-time log |
| Discovery | DiscoveryScreen | Niche analysis, suggestion cards, one-click store creation |
| Store List | StoreListScreen | All stores, per-store crawl/detail/edit buttons |
| Store Form | StoreFormScreen | New store name + ID inputs |
| Store Edit | StoreEditScreen | Full config form (keywords, credentials, sources) |
| Store Detail | StoreDetailScreen | Pipeline runner with 4 stage buttons, Run All, log |

---

## 8. Key Design Decisions

1. **curl_cffi over Playwright:** TLS impersonation lighter than browser.
2. **Product-first flow:** Crawl broad, then classify into niches.
3. **Multi-store architecture:** Each store gets its own config + data dir.
4. **Template fallback for AI:** Works without API keys (lower quality).
5. **JSON storage over SQLite:** Simple, debuggable MVP.
6. **TUI-first over CLI-first:** Textual app as primary interface.
7. **Cookie-based 1688 scraping:** Free but fragile, avoids paid APIs.
8. **Price formula VND = CNY * 3500 * 2.5:** Hardcoded in 4 locations.

---

## 9. Known Issues & Limitations

| Issue | Severity | Details |
|-------|----------|---------|
| x5sec anti-bot | HIGH | AliExpress blocks after 1-2 requests |
| 1688 CAPTCHA | HIGH | curl_cffi cannot handle CAPTCHA |
| Chrome cookie dependency | HIGH | Must close Chrome, cookies expire |
| No AI API keys | HIGH | All fall back to template |
| No Shopee credentials | HIGH | Publishing will always fail |
| Template captions low quality | MEDIUM | Generic bullets, useless hashtags |
| googletrans unreliable | MEDIUM | Returns original text |
| Image URL parsing broken | MEDIUM | Malformed file paths |
| Broad crawl empty data | MEDIUM | 58 products with no titles/prices |
| TUI in single file | MEDIUM | 844-line app.py |
| No database | MEDIUM | Flat JSON files |
| No scheduler | LOW | APScheduler unused |
| No Docker | LOW | No container support |
| No tests | LOW | Zero unit tests |

---

## 10. Next Steps / Roadmap (Prioritized)

### P0 - Must fix (blocking any real use)
1. Configure AI API keys (GOOGLE_API_KEY)
2. Configure Shopee credentials (Partner ID/Key, OAuth)
3. Fix 1688 scraper (Playwright or paid API)
4. Fix AliExpress x5sec blocking (proxies, delays, Playwright)

### P1 - Should fix (pipeline quality)
5. Fix image downloader URL parsing
6. Fix googletrans or replace with reliable alternative
7. Improve template caption quality
8. Separate TUI screens into individual files

### P2 - Should do (productivity)
9. Add SQLite database
10. Implement scheduled crawling (APScheduler)
11. Add Telegram notifications
12. Add Docker support

### P3 - Nice to have (polish)
13. Enable rembg background removal
14. Add image upscaling (Real-ESRGAN)
15. Cross-store product deduplication
16. Unit/integration tests
17. CI/CD (GitHub Actions)
18. Search result analysis diagnostic tool
