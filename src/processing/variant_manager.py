import copy, hashlib, json
from pathlib import Path
from typing import Optional
from datetime import datetime
from src.models.product import ProductSource, ProductProcessed, ProductVariantGroup
from src.utils.logger import setup_logger

logger = setup_logger("variant_manager")

SHOPEE_MAX_VARIANTS = 50


class VariantManager:
    def __init__(self, config: dict, store_id: str = ""):
        vm = config.get("variant_management", {})
        self.store_id = store_id
        self.max_variants = vm.get("max_variants_per_listing", SHOPEE_MAX_VARIANTS)
        self.merge_enabled = vm.get("merge_enabled", False)
        self.split_enabled = vm.get("split_enabled", True)
        self.current_time = datetime.now()

    # ── SKU generation ────────────────────────────────────────────

    def _generate_sku(
        self, product_id: str, color: str = "", size: str = ""
    ) -> tuple[str, str]:
        parts = [self.store_id, product_id]
        label_parts = []
        if color:
            safe_color = self._slugify(color)
            parts.append(safe_color)
            label_parts.append(color)
        if size:
            safe_size = self._slugify(size)
            parts.append(safe_size)
            label_parts.append(size)
        variation_sku = "-".join(parts)
        parent_sku = "-".join(parts[:2])
        variation_label = " / ".join(label_parts)
        return parent_sku, variation_sku, variation_label

    def _slugify(self, s: str) -> str:
        result = []
        for ch in s.strip().lower():
            if ch.isalnum() or ord(ch) > 127:
                result.append(ch)
            elif ch in " _-":
                result.append("-")
        return "".join(result).strip("-") or "var"

    # ── Variation detection ───────────────────────────────────────

    def count_variations(self, source: ProductSource) -> int:
        v = source.variations or []
        if v:
            return len(v)
        opts = source.attributes.get("options", source.attributes.get("sku_map", {}))
        if isinstance(opts, dict):
            return len(opts)
        if isinstance(opts, list):
            return len(opts)
        return 1

    def needs_split(self, source: ProductSource) -> bool:
        if not self.split_enabled:
            return False
        return self.count_variations(source) > self.max_variants

    # ── Split logic ───────────────────────────────────────────────

    def split_product(self, source: ProductSource) -> list[ProductProcessed]:
        if not self.needs_split(source):
            pp = self._source_to_processed(source)
            pp.parent_sku, pp.variation_sku, pp.variation_label = self._generate_sku(source.id)
            return [pp]

        variations = source.variations or []
        groups = self._group_variations(variations)
        products = []
        seen_titles: set[str] = set()

        for idx, (group_key, group_vars) in enumerate(groups.items(), 1):
            new_source = copy.deepcopy(source)
            new_source.id = f"{source.id}_{idx}"
            new_source.variations = group_vars
            new_source.price_cny = min(v.get("price", source.price_cny) for v in group_vars)
            new_source.original_price_cny = max(
                v.get("original_price", v.get("price", source.original_price_cny))
                for v in group_vars
            )
            color_part = group_key
            parent_sku, variation_sku, label = self._generate_sku(source.id, color=color_part)
            title_cn = self._make_unique_title(source.title_cn, group_key, idx, seen_titles)
            new_source.title_cn = title_cn

            pp = self._source_to_processed(new_source)
            pp.parent_sku = parent_sku
            pp.variation_sku = variation_sku
            pp.variation_label = label
            products.append(pp)

        return products

    def _group_variations(self, variations: list[dict]) -> dict[str, list[dict]]:
        groups: dict[str, list[dict]] = {}
        for v in variations:
            color = v.get("color", v.get("色", ""))
            if not color:
                color = v.get("属性", v.get("规格", "default"))
            sku_name = v.get("sku_name", v.get("spec", ""))
            if not color and sku_name:
                color = sku_name.split()[0] if " " in sku_name else sku_name
            if not color:
                color = "default"
            if color not in groups:
                groups[color] = []
            groups[color].append(v)
        return groups

    def _make_unique_title(
        self, base_title: str, group_key: str, idx: int, seen: set[str]
    ) -> str:
        suffix = f" ({group_key})"
        candidate = base_title
        if len(candidate) + len(suffix) > 120:
            candidate = candidate[: 120 - len(suffix) - 3] + "..."
        candidate = candidate + suffix
        if candidate in seen:
            candidate = f"{base_title[:100]} ({group_key} {idx})"
        seen.add(candidate)
        return candidate

    def _source_to_processed(self, source: ProductSource) -> ProductProcessed:
        return ProductProcessed(
            source=source,
            status="variant_split" if self.needs_split(source) else "raw",
            created_at=self.current_time,
        )

    # ── Merge logic ───────────────────────────────────────────────

    def can_merge(
        self, sources: list[ProductSource]
    ) -> Optional[list[ProductSource]]:
        if not self.merge_enabled or len(sources) < 2:
            return None
        supplier_groups: dict[str, list[ProductSource]] = {}
        for s in sources:
            key = s.supplier_name or s.platform
            if key not in supplier_groups:
                supplier_groups[key] = []
            supplier_groups[key].append(s)

        for group in supplier_groups.values():
            if len(group) >= 2:
                return group
        return None

    def merge_products(
        self, group: list[ProductSource], base_id: str
    ) -> ProductProcessed:
        primary = group[0]
        merged_variations = []
        for s in group:
            sv = s.variations or [self._variation_from_source(s)]
            merged_variations.extend(sv)

        merged_source = copy.deepcopy(primary)
        merged_source.id = base_id
        merged_source.variations = merged_variations
        merged_source.price_cny = min(s.price_cny for s in group)
        merged_source.original_price_cny = max(s.original_price_cny for s in group)
        merged_source.image_urls = list(
            dict.fromkeys(
                img for s in group for img in (s.image_urls or [])
            )
        )
        all_desc = [s.description_cn for s in group if s.description_cn]
        merged_source.description_cn = "\n".join(dict.fromkeys(all_desc))

        pp = self._source_to_processed(merged_source)
        pp.parent_sku, pp.variation_sku, pp.variation_label = self._generate_sku(base_id)
        pp.status = "merged"
        return pp

    def _variation_from_source(self, source: ProductSource) -> dict:
        return {
            "sku_name": source.title_cn[:50],
            "price": source.price_cny,
            "stock": 999,
            "image": source.image_urls[0] if source.image_urls else "",
        }

    # ── Batch entry point ─────────────────────────────────────────

    def process_products(
        self, products: list[dict], store_id: str
    ) -> list[ProductProcessed]:
        self.store_id = store_id
        sources = self._dicts_to_sources(products)
        groups: list[ProductVariantGroup] = []
        singles: list[ProductProcessed] = []

        for src in sources:
            if self.needs_split(src):
                split_pp = self.split_product(src)
                gid = self._group_id(src.id)
                group = ProductVariantGroup(
                    group_id=gid,
                    store_id=store_id,
                    parent_source_id=src.id,
                    parent_title_cn=src.title_cn,
                    products=split_pp,
                    split_reason=f"> {self.max_variants} variations",
                )
                groups.append(group)
                singles.extend(split_pp)
            else:
                pp = self._source_to_processed(src)
                pp.parent_sku, pp.variation_sku, pp.variation_label = self._generate_sku(src.id)
                singles.append(pp)

        merge_group = self.can_merge(sources)
        if merge_group:
            base_id = merge_group[0].id
            merged = self.merge_products(merge_group, f"{base_id}_merged")
            gid = self._group_id(base_id)
            groups.append(
                ProductVariantGroup(
                    group_id=gid,
                    store_id=store_id,
                    parent_source_id=base_id,
                    parent_title_cn=merge_group[0].title_cn,
                    products=[merged],
                    split_reason="supplier_merge",
                )
            )
            for s in merge_group:
                singles = [pp for pp in singles if pp.source.id != s.id]
            singles.append(merged)

        if groups:
            self._save_groups(groups, store_id)
        return singles

    def _dicts_to_sources(self, products: list[dict]) -> list[ProductSource]:
        sources = []
        for p in products:
            try:
                sources.append(ProductSource(
                    id=p.get("id", ""),
                    title_cn=p.get("title_cn", ""),
                    price_cny=float(p.get("price_cny", 0)),
                    original_price_cny=float(p.get("original_price_cny", p.get("price_cny", 0))),
                    image_urls=p.get("image_urls", []),
                    description_cn=p.get("description_cn", ""),
                    category_name_cn=p.get("category_name_cn", ""),
                    attributes=p.get("attributes", {}),
                    variations=p.get("variations", []),
                    supplier_name=p.get("supplier_name", ""),
                    supplier_rating=float(p.get("supplier_rating", 0)),
                    sales_count=int(p.get("sales_count", 0)),
                    detail_url=p.get("detail_url", ""),
                    platform=p.get("platform", "1688"),
                    is_dropship=bool(p.get("is_dropship", False)),
                ))
            except Exception as e:
                logger.warning(f"Skipping product {p.get('id', '?')}: {e}")
        return sources

    def _group_id(self, base_id: str) -> str:
        raw = f"{self.store_id}_{base_id}_{self.current_time.isoformat()}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    def _save_groups(self, groups: list[ProductVariantGroup], store_id: str):
        from dataclasses import asdict

        path = Path("data") / store_id / "variant_groups.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = []
        for g in groups:
            gd = asdict(g)
            gd["created_at"] = g.created_at.isoformat()
            data.append(gd)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(groups)} variant groups to {path}")
