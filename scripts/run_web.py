#!/usr/bin/env python3
"""WebUI launcher: python scripts/run_web.py
Chay Flask Web UI (day du) tren port 5000.
De xem FastAPI (cu) dung: python -m uvicorn src.web.app:app --port 7860
"""
import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.environ["PYTHONIOENCODING"] = "utf-8"

from webui.app import app

if __name__ == "__main__":
    print("=" * 60)
    print("  CHINA DROPSHIP TO SHOPEE - WebUI (Flask)")
    print("=" * 60)
    print("  Mo trinh duyet: http://localhost:5000")
    print("  Nhan Ctrl+C de dung")
    print("=" * 60)
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
