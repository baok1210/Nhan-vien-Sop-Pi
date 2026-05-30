@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo   WEB UI - China Dropship to Shopee
echo ============================================================
echo.
echo  Dang khoi dong Web UI...
echo  Mo trinh duyet: http://localhost:5000
echo.
echo  Web UI dung Flask (day du tinh nang)
echo  Neu muon dung FastAPI (cu): python scripts\run_web.py
echo.

set PYTHONIOENCODING=utf-8

python webui\app.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  LOI: Khong the chay.
    echo  Chay "1-Cai-dat-lan-dau.bat" de cai dat.
    pause
)
