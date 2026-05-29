#!/usr/bin/env python3
"""WebUI launcher: python scripts/run_web.py"""
import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.environ["PYTHONIOENCODING"] = "utf-8"

import uvicorn

if __name__ == "__main__":
    print("=" * 60)
    print("  CHINA DROPSHIP TO SHOPEE - WebUI")
    print("=" * 60)
    print("  Mo trinh duyet: http://localhost:7860")
    print("  Nhan Ctrl+C de dung")
    print("=" * 60)
    uvicorn.run("src.web.app:app", host="127.0.0.1", port=7860, log_level="info")
