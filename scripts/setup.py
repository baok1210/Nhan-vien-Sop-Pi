#!/usr/bin/env python3
"""One-command setup for newbies: python scripts/setup.py"""
import subprocess, sys, os
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
        env_example.rename(env_file) if not env_file.exists() else None
        print("  Da tao .env tu .env.example")
    else:
        print("  .env da ton tai, bo qua")

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
