# ASS Worker - 1-Click Automated Environment Setup
param(
    [switch]$Auto
)

$ErrorActionPreference = "Continue"

# 1. Clear any proxy environment variables
$env:HTTP_PROXY = ""
$env:HTTPS_PROXY = ""
$env:NO_PROXY = "*"

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  ASS Worker - Automated Environment Setup" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

# 2. Check if venv or portable python already exists
$venvPy = Join-Path $scriptDir "venv\Scripts\python.exe"
$portablePy = Join-Path $scriptDir "venv\python.exe"

if (Test-Path $portablePy) {
    Write-Host "[INFO] Bundled portable Python detected and ready: $portablePy" -ForegroundColor Green
    if (-not $Auto) { Read-Host "Press Enter to continue..." }
    exit 0
}

if (Test-Path $venvPy) {
    Write-Host "[INFO] Virtual environment (venv) already exists: $venvPy" -ForegroundColor Green
    if (-not $Auto) { Read-Host "Press Enter to continue..." }
    exit 0
}

# 3. Detect system Python
Write-Host "[1/3] Detecting system Python..." -ForegroundColor Yellow
$pyCmd = $null

# Check python in PATH
try {
    $ver = & python --version 2>&1
    if ($LASTEXITCODE -eq 0 -and $ver -match "Python") {
        $pyCmd = "python"
        Write-Host "  -> Found: $ver" -ForegroundColor Green
    }
} catch {}

# Fallback: check Windows Python launcher 'py'
if (-not $pyCmd) {
    try {
        $ver = & py -3 --version 2>&1
        if ($LASTEXITCODE -eq 0 -and $ver -match "Python") {
            $pyCmd = "py -3"
            Write-Host "  -> Found via py launcher: $ver" -ForegroundColor Green
        }
    } catch {}
}

if (-not $pyCmd) {
    Write-Host ""
    Write-Host "[ERROR] Python was NOT found in system PATH!" -ForegroundColor Red
    Write-Host "Please install Python 3.10 or 3.11 from https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "IMPORTANT: Make sure to check the box 'Add Python to PATH' during installation!" -ForegroundColor Yellow
    Write-Host ""
    if (-not $Auto) { Read-Host "Press Enter to continue..." }
    exit 1
}

# 4. Create virtual environment
Write-Host ""
Write-Host "[2/3] Creating virtual environment (venv)..." -ForegroundColor Yellow
if ($pyCmd -eq "python") {
    & python -m venv venv
} else {
    & py -3 -m venv venv
}

if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPy)) {
    Write-Host "[ERROR] Failed to create virtual environment 'venv'!" -ForegroundColor Red
    if (-not $Auto) { Read-Host "Press Enter to continue..." }
    exit 1
}
Write-Host "  -> Virtual environment created successfully." -ForegroundColor Green

# 5. Upgrade pip & Install requirements
Write-Host ""
Write-Host "[3/3] Installing dependencies from requirements.txt..." -ForegroundColor Yellow
$venvPip = Join-Path $scriptDir "venv\Scripts\pip.exe"

& $venvPy -m pip install --upgrade pip --quiet
if (Test-Path (Join-Path $scriptDir "requirements.txt")) {
    & $venvPip install -r (Join-Path $scriptDir "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[WARNING] Retrying dependency installation..." -ForegroundColor Yellow
        & $venvPip install -r (Join-Path $scriptDir "requirements.txt")
    }
} else {
    Write-Host "[WARNING] requirements.txt not found, skipping package installation." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "  Worker environment setup completed successfully!" -ForegroundColor Green
Write-Host "  You can now launch: run_worker.bat" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Green
Write-Host ""

if (-not $Auto) {
    Read-Host "Press Enter to continue..."
}
exit 0
