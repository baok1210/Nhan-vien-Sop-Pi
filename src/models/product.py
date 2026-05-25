from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class ProductSource:
    id: str
    title_cn: str
    price_cny: float
    original_price_cny: float
    image_urls: list[str]
    description_cn: str
    category_name_cn: str
    attributes: dict = field(default_factory=dict)
    variations: list[dict] = field(default_factory=list)
    supplier_name: str = ""
    supplier_rating: float = 0.0
    sales_count: int = 0
    detail_url: str = ""
    platform: str = "1688"
    is_dropship: bool = False


@dataclass
class ProductProcessed:
    source: ProductSource
    images_local: list[str] = field(default_factory=list)
    images_processed: list[str] = field(default_factory=list)
    title_vi: str = ""
    description_vi: str = ""
    bullet_points: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)
    price_vnd: float = 0.0
    status: str = "raw"
    parent_sku: str = ""
    variation_sku: str = ""
    variation_group_id: str = ""
    variation_label: str = ""
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ProductVariantGroup:
    group_id: str
    store_id: str
    parent_source_id: str
    parent_title_cn: str
    products: list[ProductProcessed] = field(default_factory=list)
    split_reason: str = ""
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ShopeeProduct:
    shopee_item_id: Optional[int] = None
    product: Optional[ProductProcessed] = None
    image_ids: list[str] = field(default_factory=list)
    category_id: int = 0
    logistic_id: int = 80001
    weight_kg: float = 0.2
    package_dim_cm: tuple = (15, 10, 5)
    stock: int = 999
    tier_variations: list[dict] = field(default_factory=list)
    status: str = "draft"
    shopee_response: dict = field(default_factory=dict)
    error: str = ""
