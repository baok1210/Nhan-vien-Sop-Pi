@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo   CHINA DROPSHIP TO SHOPEE - Cai dat
echo ============================================================
echo.

echo  Buoc 1: Cai dat thu vien...
python -m pip install -e . >nul 2>&1

echo  Buoc 2: Cau hinh thong tin...
python scripts\config_wizard.py

echo.
echo  Hoan tat! Chay "2-Chay-Web-UI.bat" de mo Web UI.
echo.
pause
