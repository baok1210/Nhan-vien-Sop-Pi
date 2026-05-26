#Requires -Version 5.1
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Stop"
$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptPath

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  CHINA DROPSHIP TO SHOPEE - AUTO SETUP" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Check Python
Write-Host "[1/4] Kiem tra Python..." -ForegroundColor Yellow
$py = $null
foreach ($cmd in @("python3", "python")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python 3\.(1[1-9]|[2-9]\d)") {
            $py = $cmd
            break
        }
    } catch {}
}
if (-not $py) {
    Write-Host "Python 3.11+ chua duoc cai dat!" -ForegroundColor Red
    Write-Host "Tai Python tai: https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "NHO tick 'Add Python to PATH' khi cai dat." -ForegroundColor Yellow
    exit 1
}
Write-Host "  OK: $(& $py --version)" -ForegroundColor Green

# Step 2: Create virtual environment
Write-Host "[2/4] Tao virtual environment..." -ForegroundColor Yellow
if (Test-Path "venv") {
    Write-Host "  venv da ton tai, bo qua..." -ForegroundColor Gray
} else {
    & $py -m venv venv
    Write-Host "  Da tao venv thanh cong" -ForegroundColor Green
}

if ($env:OS -match "Windows") {
    $pip = Join-Path $ScriptPath "venv\Scripts\pip.exe"
    $python = Join-Path $ScriptPath "venv\Scripts\python.exe"
} else {
    $pip = Join-Path $ScriptPath "venv/bin/pip"
    $python = Join-Path $ScriptPath "venv/bin/python"
}

# Step 3: Install libraries
Write-Host "[3/4] Cai dat thu vien Python..." -ForegroundColor Yellow
& $pip install --upgrade pip
& $pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "Cai dat that bai! Kiem tra log o tren." -ForegroundColor Red
    exit 1
}
Write-Host "  Cai dat thu vien thanh cong" -ForegroundColor Green

# Step 4: Config wizard
Write-Host "[4/4] Chay Config Wizard de nhap thong tin..." -ForegroundColor Yellow
& $python scripts/config_wizard.py

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  CAI DAT HOAN TAT!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Cach chay:"
Write-Host "  .\venv\Scripts\activate  (kich hoat moi truong)"
Write-Host "  python scripts\run.py     (mo giao dien)"
Write-Host ""
Write-Host "Hoac chay tung buoc:"
Write-Host "  python scripts\crawl_products.py"
Write-Host "  python scripts\process_images.py"
Write-Host "  python scripts\generate_captions.py"
Write-Host "  python scripts\post_to_shopee.py"
Write-Host ""
Write-Host "Can ho tro? Bao loi tai: https://github.com/anomalyco/opencode/issues"
Write-Host ""

pause
