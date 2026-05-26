import json
from pathlib import Path
from typing import Optional
from src.utils.logger import setup_logger

logger = setup_logger("caption_gen")

DEFAULT_GLOSSARY_PATH = Path("config/glossary.json")

CAPTION_PROMPT = """Bạn là copywriter bán hàng Shopee Việt Nam chuyên nghiệp.
Hãy tạo nội dung siêu thị cho sản phẩm sau:

# CONTEXT / DICTIONARY
{glossary_section}

Tên gốc (tiếng Trung): {title_cn}
Danh mục: {category}
Giá gốc: {price_cny} CNY ({price_vnd} VND)
Đặc điểm: {features}

Yêu cầu đầu ra (chỉ trả về JSON, không giải thích):
{{
  "title_vi": "title (tối đa 120 ký tự, có từ khóa, chuẩn SEO)",
  "description": "mô tả ngắn 2-3 câu (tối đa 300 ký tự), nhấn mạnh lợi ích",
  "bullet_points": ["điểm 1", "điểm 2", "điểm 3", "điểm 4", "điểm 5"],
  "hashtags": ["#tag1", "#tag2", ..., "#tag10"]
}}
"""


class CaptionGenerator:
    def __init__(self, config: dict):
        ai_cfg = config.get("ai", {}).get("caption", {})
        self.provider = ai_cfg.get("provider", "google_gemini")
        self.api_key = ai_cfg.get("api_key", "")
        self.model = ai_cfg.get("model", "gemini-2.0-flash")
        self.language = ai_cfg.get("language", "vi")
        self.tone = ai_cfg.get("tone", "professional")
        self.max_title_length = ai_cfg.get("max_title_length", 120)
        self.num_hashtags = ai_cfg.get("num_hashtags", 10)
        self._fallback_logged = False
        self._glossary: dict[str, dict] = {}
        self._glossary_match: dict[str, list[tuple[str, str]]] = {}
        self._load_glossary(config)

    def _load_glossary(self, config: dict):
        path_str = config.get("glossary_path", "") or str(DEFAULT_GLOSSARY_PATH)
        path = Path(path_str)
        if not path.exists():
            logger.info(f"Glossary not found at {path}, skipping")
            return
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load glossary: {e}")
            return

        for cat_key, cat_data in raw.items():
            terms = cat_data.get("glossary", {})
            keywords = [kw.lower() for kw in cat_data.get("keywords", [])]
            self._glossary[cat_key] = terms
            for kw in keywords:
                for word in kw.split():
                    if word not in self._glossary_match:
                        self._glossary_match[word] = []
                    for cn, vi in terms.items():
                        self._glossary_match[word].append((cn, vi))

    def _resolve_glossary(self, category: str, title_cn: str = "") -> str:
        matched: dict[str, str] = {}
        cat_lower = (category or "").lower()
        for cat_key, terms in self._glossary.items():
            cat_kws = list(self._glossary_match.keys())
            for kw in cat_kws:
                if kw in cat_lower or kw in title_cn.lower():
                    for cn, vi in self._glossary_match.get(kw, []):
                        if cn not in matched:
                            matched[cn] = vi

        if not matched and title_cn:
            for cn, vi_list in self._glossary_match.items():
                if isinstance(vi_list, list):
                    for cn_term, vi_term in vi_list:
                        if cn_term in title_cn and cn_term not in matched:
                            matched[cn_term] = vi_term

        if not matched:
            return ""

        lines = ["Danh sách thuật ngữ chuyên ngành (bắt buộc dùng các từ này khi dịch):"]
        for cn, vi in matched.items():
            lines.append(f"- {cn} -> {vi}")
        return "\n".join(lines)

    def _glossary_prompt(self, category: str, title_cn: str = "") -> str:
        section = self._resolve_glossary(category, title_cn)
        if not section:
            return "Không có từ điển chuyên ngành cho danh mục này. Hãy dịch dựa trên ngữ cảnh chung."
        return section

    def generate(
        self,
        title_cn: str,
        category: str = "",
        price_cny: float = 0,
        features: str = "",
        price_vnd: float = 0,
    ) -> dict:
        if self.provider in ("google_gemini", "openai") and not self.api_key:
            if not self._fallback_logged:
                logger.info(f"{self.provider}: no API key configured, using template fallback")
                self._fallback_logged = True
            return self._generate_template(title_cn, category, price_cny, features, price_vnd)
        glossary_section = self._glossary_prompt(category, title_cn)
        if self.provider == "google_gemini":
            return self._generate_gemini(title_cn, category, price_cny, features, price_vnd, glossary_section)
        elif self.provider == "openai":
            return self._generate_openai(title_cn, category, price_cny, features, price_vnd, glossary_section)
        logger.warning(f"No provider configured ({self.provider}), using template")
        return self._generate_template(title_cn, category, price_cny, features, price_vnd)

    def _build_prompt(self, title_cn, category, price_cny, features, price_vnd, glossary_section) -> str:
        return CAPTION_PROMPT.format(
            glossary_section=glossary_section,
            title_cn=title_cn,
            category=category,
            price_cny=price_cny,
            price_vnd=int(price_vnd),
            features=features or "không có thông tin thêm",
        )

    def _generate_gemini(
        self, title_cn, category, price_cny, features, price_vnd, glossary_section
    ) -> dict:
        try:
            import google.genai as genai
            client = genai.Client(api_key=self.api_key)
            prompt = self._build_prompt(title_cn, category, price_cny, features, price_vnd, glossary_section)
            resp = client.models.generate_content(model=self.model, contents=prompt)
            return self._parse_response(resp.text)
        except ImportError:
            try:
                import google.generativeai as genai_old
                genai_old.configure(api_key=self.api_key)
                model = genai_old.GenerativeModel(self.model)
                prompt = self._build_prompt(title_cn, category, price_cny, features, price_vnd, glossary_section)
                resp = model.generate_content(prompt)
                return self._parse_response(resp.text)
            except ImportError:
                logger.warning("google generativeai not installed, using template")
                return self._generate_template(title_cn, category, price_cny, features, price_vnd)
            except Exception as e:
                logger.info(f"Gemini (legacy) failed: {e}, using template")
                return self._generate_template(title_cn, category, price_cny, features, price_vnd)

    def _generate_openai(
        self, title_cn, category, price_cny, features, price_vnd, glossary_section
    ) -> dict:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            prompt = self._build_prompt(title_cn, category, price_cny, features, price_vnd, glossary_section)
            resp = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            return self._parse_response(resp.choices[0].message.content)
        except ImportError:
            logger.warning("openai not installed, using template")
            return self._generate_template(title_cn, category, price_cny, features, price_vnd)
        except Exception as e:
            logger.info(f"OpenAI failed: {e}, using template")
            return self._generate_template(title_cn, category, price_cny, features, price_vnd)

    def _generate_template(
        self, title_cn, category, price_cny, features, price_vnd
    ) -> dict:
        from src.processing.text_translate import TextTranslator
        translator = TextTranslator({})
        title_vi = translator.translate(title_cn)
        if not title_vi or title_vi == title_cn:
            title_vi = self._generate_title_vn_fallback(title_cn, category)

        glossary_section = self._glossary_prompt(category, title_cn)
        if glossary_section and "Không có từ điển" not in glossary_section:
            for line in glossary_section.split("\n"):
                if "->" in line:
                    parts = line.split("->")
                    if len(parts) == 2:
                        cn_term = parts[0].strip().lstrip("- ")
                        vi_term = parts[1].strip()
                        if cn_term in title_cn:
                            title_vi = title_vi.replace(
                                translator.translate(cn_term), vi_term
                            )

        words = title_vi.lower().split()
        hashtags = self._generate_hashtags(title_vi, category, words)

        cat_lower = category.lower() if category else ""
        cat_key = None
        for key, keywords in _CATEGORY_BULLETS.items():
            if any(k in cat_lower for k in keywords):
                cat_key = key
                break

        if cat_key and cat_key in _CATEGORY_BULLETS:
            bullets = [b.format(price=int(price_vnd)) for b in _CATEGORY_BULLETS[cat_key]]
        else:
            bullets = [
                f"Sản phẩm chất lượng cao, bền đẹp theo thời gian",
                f"Thiết kế thông minh, tiện lợi cho sử dụng hàng ngày",
                f"Giá chỉ từ {int(price_vnd):,}đ - Rẻ hơn mua tại cửa hàng",
                f"Giao hàng nhanh toàn quốc, đổi trả dễ dàng",
                f"Cam kết hàng giống mô tả, chất lượng đúng giá",
            ]

        description = self._generate_description(title_vi, bullets, price_vnd)

        return {
            "title_vi": self._clean_title(title_vi),
            "description": description,
            "bullet_points": bullets,
            "hashtags": hashtags,
        }

    def _generate_title_vn_fallback(self, title_cn: str, category: str) -> str:
        if not title_cn:
            return f"Sản phẩm {category}" if category else "Sản phẩm chất lượng cao"
        from src.processing.text_translate import TextTranslator
        t = TextTranslator({})
        result = t._fallback_translate(title_cn)
        if result == title_cn:
            return f"{title_cn} - {category}" if category else title_cn
        return result

    def _generate_hashtags(self, title_vi: str, category: str, words: list) -> list:
        seen = set()
        hashtags = []
        for w in words:
            w_clean = w.strip(",.!?()[]{}").lower()
            if len(w_clean) > 2 and w_clean not in seen:
                seen.add(w_clean)
                hashtags.append(f"#{w_clean}")
        if category:
            cat_words = category.lower().replace("&", "").split()
            for w in cat_words:
                tag = f"#{w.strip()}"
                if tag not in seen:
                    seen.add(tag)
                    hashtags.append(tag)
        extra = ["#muasamthongminh", "#dealhot", "#hangchatluong"]
        for tag in extra:
            if tag not in seen:
                seen.add(tag)
                hashtags.append(tag)
        return hashtags[:self.num_hashtags]

    def _generate_description(self, title_vi: str, bullets: list, price_vnd: float) -> str:
        desc = f"{title_vi}\n\n"
        desc += "THONG TIN SAN PHAM:\n"
        for b in bullets:
            desc += f"- {b}\n"
        desc += f"\nGIA: {int(price_vnd):,}d\n\n"
        desc += "Dat mua ngay hom nay de nhan uu dai!\n"
        desc += "Giao hang nhanh toan quoc\n"
        desc += "Doi tra trong 7 ngay neu san pham loi"
        return desc

    def _clean_title(self, title: str) -> str:
        max_len = self.max_title_length
        if len(title) > max_len:
            title = title[: title.rfind(" ", 0, max_len)]
        return title.strip().capitalize()

    def _parse_response(self, text: str) -> dict:
        import json
        import re
        try:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                return json.loads(match.group())
            return json.loads(text)
        except Exception as e:
            logger.error(f"Parse AI response failed: {e}")
            return {
                "title_vi": text[:120],
                "description": text[:300],
                "bullet_points": [],
                "hashtags": [],
            }


_CATEGORY_BULLETS = {
    "pet": [
        "Sản phẩm chất lượng cao, an toàn tuyệt đối cho thú cưng của bạn",
        "Thiết kế thông minh, tiện lợi cho cả bạn và thú cưng",
        "Phù hợp cho mọi giống chó/mèo, kích cỡ đa dạng",
        "Giá chỉ từ {price:,}đ - Tiết kiệm hơn mua tại shop",
        "Giao hàng nhanh toàn quốc, đổi trả trong 7 ngày",
    ],
    "phone": [
        "Chất liệu cao cấp, bền bỉ, bảo vệ điện thoại tối ưu",
        "Thiết kế ôm sát, sang trọng, giữ nguyên vẻ đẹp máy",
        "Chống trầy, chống sốc, chống bám vân tay hiệu quả",
        "Dễ dàng lắp đặt, phù hợp với mọi dòng máy",
        "Giá chỉ từ {price:,}đ - Rẻ hơn mua tại cửa hàng",
    ],
    "outdoor": [
        "Chất liệu cao cấp, chịu lực tốt, bền bỉ trong mọi điều kiện thời tiết",
        "Thiết kế chuyên nghiệp, an toàn tuyệt đối khi sử dụng",
        "Siêu nhẹ, gấp gọn, dễ dàng mang theo mọi nơi",
        "Phù hợp cho mọi hoạt động: leo núi, cắm trại, dã ngoại",
        "Giá chỉ từ {price:,}đ - Đồ bền giá rẻ",
    ],
    "beauty": [
        "Sản phẩm chất lượng cao, an toàn cho da, không gây kích ứng",
        "Thành phần lành tính, phù hợp với mọi loại da",
        "Thiết kế sang trọng, tiện lợi khi sử dụng và mang theo",
        "Hiệu quả rõ rệt chỉ sau vài lần sử dụng",
        "Giá chỉ từ {price:,}đ - Mỹ phẩm chính hãng giá tốt",
    ],
    "electronic": [
        "Chất lượng cao, kiểm định nghiêm ngặt trước khi xuất xưởng",
        "Công nghệ mới nhất, tiết kiệm điện, hiệu suất vượt trội",
        "Tương thích với mọi thiết bị, dễ dàng cài đặt",
        "Bảo hành chính hãng, hỗ trợ kỹ thuật 24/7",
        "Giá chỉ từ {price:,}đ - Rẻ hơn thị trường",
    ],
    "fashion": [
        "Chất liệu cao cấp, thoải mái, thoáng mát khi mặc",
        "Thiết kế thời trang, phù hợp xu hướng mới nhất",
        "Phù hợp cho cả nam và nữ, nhiều màu sắc lựa chọn",
        "Bền màu, không phai, không xù lông sau nhiều lần giặt",
        "Giá chỉ từ {price:,}đ - Thời trang giá rẻ",
    ],
    "home": [
        "Chất liệu an toàn, không BPA, thân thiện môi trường",
        "Thiết kế thông minh, giúp không gian sống gọn gàng hơn",
        "Dễ dàng vệ sinh và bảo quản",
        "Đa năng, phù hợp với mọi không gian nhà ở",
        "Giá chỉ từ {price:,}đ - Đồ gia dụng chất lượng",
    ],
}
