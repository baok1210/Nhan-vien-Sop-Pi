import re
from src.utils.logger import setup_logger

logger = setup_logger("classifier")

NICHE_CATEGORIES = {
    "Climbing & Hiking": {
        "keywords": [
            "hiking", "trekking", "climbing", "mountaineering", "outdoor",
            "camping", "backpack", "trail", "登山", "徒步", "户外",
            "trekking pole", "hiking boot", "climbing gear",
        ],
        "icon": "🏔️",
    },
    "Pet Supplies": {
        "keywords": [
            "dog", "cat", "pet", "puppy", "kitten", "leash", "collar",
            "宠物", "猫", "狗", "pet bed", "cat toy", "dog treat",
        ],
        "icon": "🐱",
    },
    "Phone Accessories": {
        "keywords": [
            "phone case", "phone accessories", "screen protector",
            "phone stand", "手机壳", "手机配件", "手机支架",
            "phone holder", "earphone", "charger cable",
        ],
        "icon": "📱",
    },
    "Beauty & Makeup": {
        "keywords": [
            "makeup", "cosmetic", "skincare", "beauty", "lipstick",
            "foundation", "化妆", "美容", "护肤品",
            "makeup brush", "eyelash", "nail",
        ],
        "icon": "💄",
    },
    "Home & Kitchen": {
        "keywords": [
            "kitchen", "home", "storage", "organizer", "收纳",
            "厨房", "家居", "container", "kitchen tool",
        ],
        "icon": "🏠",
    },
    "Fashion Accessories": {
        "keywords": [
            "wallet", "belt", "watch", "jewelry", "necklace",
            "bracelet", "earring", "ring", "配件", "饰品",
            "sunglasses", "scarf", "hat",
        ],
        "icon": "👗",
    },
    "Electronics & Gadgets": {
        "keywords": [
            "gadget", "electronic", "bluetooth", "speaker", "headphone",
            "耳机", "音箱", "充电", "smart", "usb",
        ],
        "icon": "🔌",
    },
    "Sports & Fitness": {
        "keywords": [
            "sport", "fitness", "yoga", "gym", "exercise", "workout",
            "运动", "健身", "瑜伽", "跑步",
        ],
        "icon": "🏋️",
    },
    "Toys & Games": {
        "keywords": [
            "toy", "game", "puzzle", "board game", "玩具",
            "gaming", "remote control", "drone",
        ],
        "icon": "🎮",
    },
    "Baby & Kids": {
        "keywords": [
            "baby", "kids", "children", "婴儿", "宝宝", "儿童",
            "stroller", "baby toy", "baby care",
        ],
        "icon": "👶",
    },
    "Car Accessories": {
        "keywords": [
            "car", "auto", "vehicle", "车", "汽车", "车载",
            "car charger", "car phone holder", "seat cover",
        ],
        "icon": "🚗",
    },
}


def classify_product(title: str, description: str = "") -> tuple[str, float]:
    """Return (category_name, confidence) for a product."""
    text = f"{title} {description}".lower()

    scores: list[tuple[str, int, float]] = []
    for cat, info in NICHE_CATEGORIES.items():
        score = 0
        for kw in info["keywords"]:
            if kw.lower() in text:
                score += 1

        if score > 0:
            confidence = min(score / 3, 1.0)
            scores.append((cat, score, confidence))

    if not scores:
        return ("Other", 0.0)

    scores.sort(key=lambda x: -x[1])
    return (scores[0][0], scores[0][2])


def classify_products(products: list[dict]) -> list[dict]:
    """Classify a list of product dicts, adding 'category' and 'confidence' fields."""
    classified = []
    for p in products:
        cat, conf = classify_product(
            p.get("title_cn", "") + " " + p.get("title_en", ""),
            p.get("description_cn", ""),
        )
        p["category"] = cat
        p["category_confidence"] = round(conf, 2)
        classified.append(p)
    return classified
