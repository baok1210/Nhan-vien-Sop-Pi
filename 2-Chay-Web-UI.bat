@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo   WEB UI - China Dropship to Shopee
echo ============================================================
echo.
echo  Dang khoi dong Web UI...
echo  Mo trinh duyet: http://localhost:7860
echo  Nhan Ctrl+C de dung
echo.

set PYTHONIOENCODING=utf-8

python scripts\run_web.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  LOI: Khong the chay.
    echo  Chay "1-Cai-dat-lan-dau.bat" de cai dat.
    pause
)
