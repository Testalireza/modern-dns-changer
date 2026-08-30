# Build script for Modern DNS Changer v4.1
# Run on Windows PowerShell.
#
# Usage:
#     .\build.ps1              - Build (deps must already be installed)
#     .\build.ps1 -Install     - Install Python deps before building
#     .\build.ps1 -Clean       - Delete build/ and dist/ before building
#     .\build.ps1 -Install -Clean
#
# Result: dist\ModernDNSChanger.exe

[CmdletBinding()]
param(
    [switch]$Install,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $scriptDir

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Modern DNS Changer v4.1 - Build Script" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

if ($Clean) {
    Write-Host "[clean] Removing build/ and dist/ ..." -ForegroundColor Yellow
    foreach ($d in @("build", "dist", "__pycache__")) {
        $p = Join-Path $scriptDir $d
        if (Test-Path $p) {
            Remove-Item -Recurse -Force $p
        }
    }
    # Also clean any top-level __pycache__ folders
    Get-ChildItem -Path $scriptDir -Recurse -Directory -Filter "__pycache__" |
        Remove-Item -Recurse -Force
    Write-Host ""
}

if ($Install) {
    Write-Host "[install] Installing Python dependencies ..." -ForegroundColor Yellow
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    python -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
    Write-Host ""
}

if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
    Write-Host "[error] PyInstaller is not installed. Run with -Install." -ForegroundColor Red
    exit 1
}

# Generate the icon if missing
if (-not (Test-Path (Join-Path $scriptDir "icon.ico"))) {
    Write-Host "[icon] Generating icon.ico ..." -ForegroundColor Yellow
    python generate_icon.py
    if ($LASTEXITCODE -ne 0) { throw "icon generation failed" }
    Write-Host ""
}

Write-Host "[build] Running PyInstaller ..." -ForegroundColor Yellow
pyinstaller build.spec --clean --noconfirm
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
Write-Host ""

$exe = Join-Path $scriptDir "dist\ModernDNSChanger.exe"
if (Test-Path $exe) {
    $size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host " Build successful!" -ForegroundColor Green
    Write-Host (" EXE: {0} ({1} MB)" -f $exe, $size) -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
} else {
    Write-Host "[error] $exe was not produced." -ForegroundColor Red
    exit 1
}
