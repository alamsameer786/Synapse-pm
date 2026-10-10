@echo off
:: ============================================================
:: SYNAPPM - WINDOWS BUILD SCRIPT v5.2.1
:: Production-ready build with code signing
:: ============================================================

setlocal enabledelayedexpansion

set APP_NAME=SynapsePM
set APP_VERSION=5.2.1
set APP_COMPANY=SynapsePM Technologies
set APP_IDENTIFIER=com.synapsepm.desktop

echo ============================================================
echo   🏭 %APP_NAME% - WINDOWS BUILDER v%APP_VERSION%
echo ============================================================
echo.

:: Check Python
echo 🔍 Checking dependencies...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python not found! Please install Python.
    pause
    exit /b 1
)
echo ✅ Python found

:: Install dependencies
echo.
echo 📦 Installing dependencies...
pip install --upgrade pip
pip install pyinstaller webview pystray pillow requests

echo ✅ Dependencies installed

:: Create output directory
set OUTPUT_DIR=dist
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

:: Build application
echo.
echo 🔨 Building %APP_NAME%.exe...
cd desktop

pyinstaller --onefile ^
    --windowed ^
    --name=synapsepm ^
    --add-data "../frontend;frontend" ^
    --add-data "../web;web" ^
    --hidden-import=webview ^
    --hidden-import=pystray ^
    --hidden-import=PIL ^
    --hidden-import=requests ^
    --version-file=version_info.txt ^
    --icon=../frontend/images/applogo.ico ^
    --clean ^
    main.py

cd ..

:: Check build
if exist "desktop\dist\synapsepm.exe" (
    echo ✅ Build successful
    copy "desktop\dist\synapsepm.exe" "%OUTPUT_DIR%\"
) else (
    echo ❌ Build failed
    pause
    exit /b 1
)

:: Code signing (if certificate available)
if defined WINDOWS_CERT_PASSWORD (
    echo.
    echo 🔐 Code signing...
    signtool sign /fd SHA256 /a /f "%WINDOWS_CERT_PATH%" /p "%WINDOWS_CERT_PASSWORD%" /tr http://timestamp.digicert.com /td SHA256 "%OUTPUT_DIR%\synapsepm.exe"
    echo ✅ Code signed
) else (
    echo ⚠️ No code signing certificate found. Build will not be signed.
    echo   Set WINDOWS_CERT_PATH and WINDOWS_CERT_PASSWORD for signing.
)

:: Create installer using Inno Setup
if exist "build\installer\synapsepm.iss" (
    echo.
    echo 📦 Creating installer...
    "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "build\installer\synapsepm.iss"
    echo ✅ Installer created
) else (
    echo ⚠️ Inno Setup script not found. Creating zip instead.
    cd "%OUTPUT_DIR%"
    powershell Compress-Archive -Path synapsepm.exe -DestinationPath "%APP_NAME%-Windows.zip"
    cd ..
    echo ✅ ZIP created
)

:: Create release notes
(
echo %APP_NAME% v%APP_VERSION%
echo %APP_COPYRIGHT%
echo.
echo Files included:
echo - synapsepm.exe: Standalone executable
echo - %APP_NAME%-Windows.zip: ZIP archive
echo - synapsepm_installer.exe: Installer (if available)
echo.
echo System Requirements:
echo - Windows 10 or later
echo - 64-bit processor
echo - 4GB RAM minimum
echo.
echo Installation:
echo 1. Run synapsepm.exe directly, or
echo 2. Run the installer for system integration
echo.
echo First launch may show a Windows SmartScreen warning:
echo - Click "More info"
echo - Click "Run anyway"
echo.
echo Support: support@synapsepm.com
) > "%OUTPUT_DIR%\README.txt"

echo.
echo ============================================================
echo   ✅ BUILD COMPLETE!
echo   📁 Output Directory: %OUTPUT_DIR%\
echo.
echo   📦 Files created:
dir "%OUTPUT_DIR%" /b | findstr /v "README" | findstr /v "^d" | for /f "usebackq" %%f in (`findstr /v "^d"`) do echo    - %%f
echo.
echo ============================================================
pause