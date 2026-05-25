#!/usr/bin/env python3
"""Launcher cho Shopee Dropship Pipeline TUI.
Usage: python scripts/run.py
"""
import sys, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Fix Windows console encoding for Unicode
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    os.environ["PYTHONIOENCODING"] = "utf-8"

if __name__ == "__main__":
    from src.tui.app import PipelineApp
    app = PipelineApp()
    app.run()
