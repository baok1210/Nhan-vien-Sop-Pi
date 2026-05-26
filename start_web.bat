@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   WEB UI - China Dropship to Shopee
echo ============================================
echo.

if exist .venv\Scripts\python.exe (
    set PY=.venv\Scripts\python.exe
) else if exist venv\Scripts\python.exe (
    set PY=venv\Scripts\python.exe
) else (
    set PY=python
)

echo Dang chay: %PY% webui\app.py
echo.
echo Mo trinh duyet: http://localhost:5000
echo.
%PY% webui\app.py
pause
