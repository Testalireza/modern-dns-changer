# Build script for creating the Windows .exe
# Run this on your Windows PC (not in the Base44 sandbox)

Write-Host "Building Modern DNS Changer .exe..." -ForegroundColor Cyan

# Install dependencies
Write-Host "`nInstalling dependencies..." -ForegroundColor Yellow
pip install customtkinter keyboard pyinstaller pillow

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
Write-Host "`nYou can copy it anywhere and double-click to run." -ForegroundColor Cyan
Write-Host "It will auto-request admin elevation (needed for DNS changes)." -ForegroundColor Cyan

Read-Host "`nPress Enter to exit..."
