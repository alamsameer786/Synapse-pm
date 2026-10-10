#!/bin/bash
# ============================================================
# SYNAPPM - macOS BUILD SCRIPT v5.2.1
# Production-ready build with code signing
# ============================================================

APP_NAME="SynapsePM"
APP_VERSION="5.2.1"
APP_COMPANY="SynapsePM Technologies"
APP_IDENTIFIER="com.synapsepm.desktop"
TEAM_ID="${APPLE_TEAM_ID:-}"

echo "============================================================"
echo "  🏭 ${APP_NAME} - macOS BUILDER v${APP_VERSION}"
echo "============================================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check dependencies
echo "🔍 Checking dependencies..."

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python3 not found!${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Python3 found${NC}"

# Check for code signing certificate
if [ -n "$TEAM_ID" ]; then
    echo -e "${GREEN}✅ Code signing certificate found${NC}"
else
    echo -e "${YELLOW}⚠️ No code signing certificate found. Build will not be signed.${NC}"
    echo "  Set APPLE_TEAM_ID environment variable for signing."
fi

# Install dependencies
echo ""
echo "📦 Installing dependencies..."
pip3 install --upgrade pip
pip3 install pyinstaller webview pystray pillow requests

echo -e "${GREEN}✅ Dependencies installed${NC}"

# Create output directory
OUTPUT_DIR="dist"
mkdir -p "$OUTPUT_DIR"

# Create .app bundle
echo ""
echo "🔨 Building ${APP_NAME}.app..."

# Build with PyInstaller (one file, windowed)
cd desktop
pyinstaller --onefile \
    --windowed \
    --name=synapsepm \
    --add-data "../frontend:frontend" \
    --add-data "../web:web" \
    --hidden-import=webview \
    --hidden-import=pystray \
    --hidden-import=PIL \
    --hidden-import=requests \
    --clean \
    main.py

cd ..

# Create .app structure
APP_BUNDLE="${OUTPUT_DIR}/${APP_NAME}.app"
mkdir -p "${APP_BUNDLE}/Contents/MacOS"
mkdir -p "${APP_BUNDLE}/Contents/Resources"
mkdir -p "${APP_BUNDLE}/Contents/Frameworks"

# Copy executable
cp "desktop/dist/synapsepm" "${APP_BUNDLE}/Contents/MacOS/${APP_NAME}"

# Create Info.plist
cat > "${APP_BUNDLE}/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>${APP_NAME}</string>
    <key>CFBundleDisplayName</key>
    <string>${APP_NAME}</string>
    <key>CFBundleIdentifier</key>
    <string>${APP_IDENTIFIER}</string>
    <key>CFBundleVersion</key>
    <string>${APP_VERSION}</string>
    <key>CFBundleShortVersionString</key>
    <string>${APP_VERSION}</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleSignature</key>
    <string>????</string>
    <key>CFBundleExecutable</key>
    <string>${APP_NAME}</string>
    <key>CFBundleIconFile</key>
    <string>appicon</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>LSMinimumSystemVersion</key>
    <string>10.13</string>
    <key>NSHumanReadableCopyright</key>
    <string>${APP_COPYRIGHT}</string>
</dict>
</plist>
EOF

# Copy icon
if [ -f "frontend/images/applogo.icns" ]; then
    cp "frontend/images/applogo.icns" "${APP_BUNDLE}/Contents/Resources/appicon.icns"
fi

# Make executable
chmod +x "${APP_BUNDLE}/Contents/MacOS/${APP_NAME}"

# Code sign (if certificate available)
if [ -n "$TEAM_ID" ]; then
    echo ""
    echo "🔐 Code signing..."
    codesign --deep --force --sign "Developer ID Application: ${APP_COMPANY} (${TEAM_ID})" \
        --entitlements desktop/entitlements.plist \
        "${APP_BUNDLE}"
    echo -e "${GREEN}✅ Code signed${NC}"
fi

# Create DMG
echo ""
echo "📦 Creating DMG..."

if command -v create-dmg &> /dev/null; then
    create-dmg \
        --window-size 500 300 \
        --icon-size 100 \
        --app-drop-link 350 200 \
        --icon "${APP_NAME}" 150 200 \
        --background "frontend/images/dmg_bg.png" \
        --volname "${APP_NAME} ${APP_VERSION}" \
        "${OUTPUT_DIR}/${APP_NAME}.dmg" \
        "${OUTPUT_DIR}/${APP_NAME}.app"
    echo -e "${GREEN}✅ DMG created${NC}"
else
    echo -e "${YELLOW}⚠️ create-dmg not found. Creating zip instead.${NC}"
    cd "${OUTPUT_DIR}"
    zip -r "${APP_NAME}-macOS.zip" "${APP_NAME}.app"
    cd ..
    echo -e "${GREEN}✅ ZIP created${NC}"
fi

# Create release notes
cat > "$OUTPUT_DIR/README.txt" << EOF
${APP_NAME} v${APP_VERSION}
${APP_COPYRIGHT}

Files included:
- ${APP_NAME}.app: macOS application bundle
- ${APP_NAME}.dmg: DMG installer
- ${APP_NAME}-macOS.zip: ZIP archive

System Requirements:
- macOS 10.13 (High Sierra) or later
- Apple Silicon or Intel processor

Installation:
1. Open the DMG file
2. Drag ${APP_NAME}.app to Applications folder
3. Launch from Applications

First launch may require:
- Right-click and select "Open"
- Click "Open" in the security dialog

Support: support@synapsepm.com
EOF

echo ""
echo "============================================================"
echo -e "${GREEN}  ✅ BUILD COMPLETE!${NC}"
echo "  📁 Output Directory: ${OUTPUT_DIR}/"
echo ""
echo "  📦 Files created:"
ls -la "$OUTPUT_DIR/" | grep -v "^d" | awk '{print "   - " $9 " (" $5 " bytes)"}'
echo ""
echo "============================================================"