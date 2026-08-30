@echo off
REM Build script for Modern DNS Changer v4.1
REM
REM Usage:
REM     build.bat           - Build using already-installed dependencies
REM     build.bat --clean   - Also delete build/ and dist/ before building
REM     build.bat --install - Install dependencies before building
REM
REM Result: dist\ModernDNSChanger.exe

setlocal EnableDelayedExpansion

cd /d "%~dp0"

echo ============================================================
echo  Modern DNS Changer v4.1 - Build Script
echo ============================================================
echo.

if /I "%1"=="--clean" goto :clean
if /I "%1"=="--install" goto :install
goto :check

:clean
echo [clean] Removing build/ and dist/...
if exist build  rmdir /S /Q build
if exist dist   rmdir /S /Q dist
if exist __pycache__ rmdir /S /Q __pycache__
echo.

:check
where pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [error] PyInstaller is not installed.
    echo Run:  build.bat --install
    exit /b 1
)

:install
if /I not "%1"=="--install" goto :do_build
echo [install] Installing Python dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller
if errorlevel 1 (
    echo [error] pip install failed.
    exit /b 1
)
echo.

:do_build
echo [icon] Generating icon.ico...
if not exist icon.ico (
    python generate_icon.py
    if errorlevel 1 (
        echo [error] Icon generation failed.
        exit /b 1
    )
)
echo.

echo [build] Running PyInstaller...
pyinstaller build.spec --clean --noconfirm
if errorlevel 1 (
    echo [error] PyInstaller build failed.
    exit /b 1
)
echo.

if exist dist\ModernDNSChanger.exe (
    echo ============================================================
    echo  Build successful!
    echo  EXE: %CD%\dist\ModernDNSChanger.exe
    echo ============================================================
) else (
    echo [error] dist\ModernDNSChanger.exe was not produced.
    exit /b 1
)

endlocal
exit /b 0
