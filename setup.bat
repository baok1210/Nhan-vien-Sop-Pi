@echo off
chcp 65001 >nul
echo ============================================
echo   CHINA DROPSHIP TO SHOPEE - AUTO SETUP
echo ============================================
echo.
echo Dang cai dat... Vui long doi...
echo.

powershell -ExecutionPolicy Bypass -File "%~dp0setup.ps1"

if %errorlevel% neq 0 (
    echo.
    echo Co loi xay ra. Thu chay manual:
    echo   1. Mo PowerShell (Admin)
    echo   2. Go: Set-ExecutionPolicy RemoteSignature -Scope CurrentUser
    echo   3. Go: .\setup.ps1
    pause
)
