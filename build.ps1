# Build script for creating the Windows .exe
# Run this on your Windows PC

Write-Host "Building Modern DNS Changer .exe..." -ForegroundColor Cyan

# Install dependencies
Write-Host "`nInstalling dependencies..." -ForegroundColor Yellow
pip install customtkinter keyboard pyinstaller pillow pystray

# Generate icon if it doesn't exist
if (-not (Test-Path "icon.ico")) {
    Write-Host "Generating app icon..." -ForegroundColor Yellow
    python generate_icon.py
}

# Build with PyInstaller
Write-Host "`nBuilding .exe with PyInstaller..." -ForegroundColor Yellow
pyinstaller build.spec --clean --noconfirm

Write-Host "`n✓ Build complete!" -ForegroundColor Green
Write-Host "Your .exe is in: dist\ModernDNSChanger.exe" -ForegroundColor Green
Write-Host "`nFeatures:" -ForegroundColor Cyan
Write-Host "  - No console window (GUI only)" -ForegroundColor White
Write-Host "  - Auto-admin elevation (UAC prompt)" -ForegroundColor White
Write-Host "  - System tray support" -ForegroundColor White
Write-Host "  - Dark/Light mode" -ForegroundColor White
Write-Host "  - English/Persian language" -ForegroundColor White
Write-Host "  - Custom app icon" -ForegroundColor White

Read-Host "`nPress Enter to exit..."
