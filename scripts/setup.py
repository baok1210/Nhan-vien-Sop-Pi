#!/usr/bin/env python3
"""One-command setup for newbies: python scripts/setup.py"""
import json, shutil, subprocess, sys, os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
os.chdir(str(BASE_DIR))
PY = sys.executable


def run(cmd, label):
    print(f"\n  >> {label}...")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"  !! Loi: {label} that bai, code={result.returncode}")
    return result.returncode


def main():
    print("=" * 60)
    print("  CHINA DROPSHIP TO SHOPEE - SETUP")
    print("  Tu dong cai dat moi truong va cau hinh")
    print("=" * 60)

    print("\n--- 1. Kiem tra Python ---")
    print(f"  Python: {sys.version}")

    print("\n--- 2. Cai dat thu vien ---")
    run(f"{PY} -m pip install -e .", "Cai dat package")

    print("\n--- 3. Tao .env (neu chua co) ---")
    env_example = BASE_DIR / ".env.example"
    env_file = BASE_DIR / ".env"
    if not env_file.exists() and env_example.exists():
        shutil.copyfile(env_example, env_file)
        print("  Da tao .env tu .env.example")
    elif env_file.exists():
        print("  .env da ton tai, bo qua")
    else:
        print("  !! Khong tim thay .env.example — tao .env rong")
        env_file.write_text("", encoding="utf-8")

    print("\n--- 3b. Tao config/config.json (neu chua co) ---")
    cfg_example = BASE_DIR / "config" / "config.example.json"
    cfg_file = BASE_DIR / "config" / "config.json"
    if not cfg_file.exists() and cfg_example.exists():
        shutil.copyfile(cfg_example, cfg_file)
        print("  Da tao config/config.json tu config.example.json")
    elif cfg_file.exists():
        print("  config.json da ton tai, bo qua")

    # Stores dir phai ton tai truoc khi pipeline chay
    stores_dir = BASE_DIR / "config" / "stores"
    stores_dir.mkdir(parents=True, exist_ok=True)
    ex_store = stores_dir / "example.json"
    if not ex_store.exists():
        ex_store.write_text(
            json.dumps({
                "id": "example", "name": "Store mau (sua hoac xoa)",
                "niche": {"keywords_cn": ["\u624b\u673a\u914d\u4ef6"], "keywords_en": ["phone accessories"],
                          "keywords_vn": ["ph\u1ee5 ki\u1ec7n \u0111i\u1ec7n tho\u1ea1i"], "category_shopee_id": 0,
                          "max_price_cny": 50, "min_margin_percent": 30,
                          "min_margin_percentage": 0.15, "price_multiplier": 2.5,
                          "competitor_search_enabled": True},
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print("  Da tao config/stores/example.json (store mau)")

    print("\n--- 4. Cau hinh thong tin ---")
    run(f"{PY} scripts/config_wizard.py", "Config wizard")

    print("\n--- 5. Kiem tra pipeline ---")
    run(f"{PY} -m pytest tests/ -q --tb=short", "Chay test")

    print("\n" + "=" * 60)
    print("  HOAN TAT!")
    print("  Chay: python scripts/run.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
