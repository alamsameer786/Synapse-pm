#!/bin/bash
# ============================================================
# SYNAPPM - LINUX BUILD SCRIPT v5.2.1
# Production-ready build with proper signing
# ============================================================

set -e

APP_NAME="SynapsePM"
APP_VERSION="5.2.1"
APP_COMPANY="SynapsePM Technologies"

echo "============================================================"
echo "  🏭 ${APP_NAME} - LINUX BUILDER v${APP_VERSION}"
echo "============================================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check dependencies
echo "🔍 Checking dependencies..."

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python3 not found!${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Python3 found${NC}"

if ! command -v pip3 &> /dev/null; then
    echo -e "${RED}❌ pip3 not found!${NC}"
    exit 1
fi
echo -e "${GREEN}✅ pip3 found${NC}"

# Install dependencies
echo ""
echo "📦 Installing dependencies..."
pip3 install --upgrade pip
pip3 install pyinstaller webview pystray pillow requests

echo -e "${GREEN}✅ Dependencies installed${NC}"

# Create output directory
OUTPUT_DIR="dist"
mkdir -p "$OUTPUT_DIR"

# Build application
echo ""
echo "🔨 Building ${APP_NAME}..."
cd desktop

# Build with PyInstaller (one file)
pyinstaller --onefile \
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

# Verify build
if [ -f "desktop/dist/synapsepm" ]; then
    echo -e "${GREEN}✅ Build successful${NC}"
    cp desktop/dist/synapsepm "$OUTPUT_DIR/"
else
    echo -e "${RED}❌ Build failed${NC}"
    exit 1
fi

# Create AppImage (if appimagetool is available)
if command -v appimagetool &> /dev/null; then
    echo ""
    echo "📦 Creating AppImage..."
    
    APP_DIR="SynapsePM.AppDir"
    mkdir -p "$APP_DIR/usr/bin"
    cp "$OUTPUT_DIR/synapsepm" "$APP_DIR/usr/bin/"
    
    # Create AppRun
    cat > "$APP_DIR/AppRun" << 'EOF'
#!/bin/bash
SELF="$(readlink -f "$0")"
HERE="${SELF%/*}"
exec "$HERE/usr/bin/synapsepm" "$@"
EOF
    chmod +x "$APP_DIR/AppRun"
    
    # Create desktop file
    cat > "$APP_DIR/synapsepm.desktop" << EOF
[Desktop Entry]
Name=${APP_NAME}
Comment=AI Predictive Maintenance Platform
Exec=synapsepm
Icon=synapsepm
Terminal=false
Type=Application
Categories=Utility;
Version=${APP_VERSION}
EOF
    
    # Create icon
    if [ -f "frontend/images/applogo.png" ]; then
        cp "frontend/images/applogo.png" "$APP_DIR/synapsepm.png"
    fi
    
    # Build AppImage
    appimagetool "$APP_DIR" "$OUTPUT_DIR/${APP_NAME}.AppImage"
    echo -e "${GREEN}✅ AppImage created${NC}"
else
    echo -e "${YELLOW}⚠️ appimagetool not found. Skipping AppImage.${NC}"
    echo "  Install: wget https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
fi

# Create deb package (if dpkg is available)
if command -v dpkg &> /dev/null; then
    echo ""
    echo "📦 Creating DEB package..."
    
    DEB_DIR="synapsepm_${APP_VERSION}_amd64"
    mkdir -p "${DEB_DIR}/usr/bin"
    mkdir -p "${DEB_DIR}/usr/share/applications"
    mkdir -p "${DEB_DIR}/usr/share/icons/hicolor/64x64/apps"
    mkdir -p "${DEB_DIR}/DEBIAN"
    
    cp "$OUTPUT_DIR/synapsepm" "${DEB_DIR}/usr/bin/"
    
    # Create control file
    cat > "${DEB_DIR}/DEBIAN/control" << EOF
Package: synapsepm
Version: ${APP_VERSION}
Section: utils
Priority: optional
Architecture: amd64
Maintainer: ${APP_COMPANY} <support@synapsepm.com>
Description: ${APP_NAME} - AI Predictive Maintenance Platform
 ${APP_NAME} is an enterprise-grade predictive maintenance platform
 powered by AI/ML for industrial equipment monitoring.
EOF
    
    # Create desktop entry
    cat > "${DEB_DIR}/usr/share/applications/synapsepm.desktop" << EOF
[Desktop Entry]
Name=${APP_NAME}
Comment=AI Predictive Maintenance Platform
Exec=synapsepm
Icon=synapsepm
Terminal=false
Type=Application
Categories=Utility;
Version=${APP_VERSION}
EOF
    
    # Copy icon
    if [ -f "frontend/images/applogo.png" ]; then
        cp "frontend/images/applogo.png" "${DEB_DIR}/usr/share/icons/hicolor/64x64/apps/synapsepm.png"
    fi
    
    # Build DEB
    dpkg-deb --build "${DEB_DIR}" "$OUTPUT_DIR/"
    echo -e "${GREEN}✅ DEB package created${NC}"
fi

# Create release notes
cat > "$OUTPUT_DIR/README.txt" << EOF
${APP_NAME} v${APP_VERSION}
${APP_COPYRIGHT}

Files included:
- synapsepm: Standalone executable
- ${APP_NAME}.AppImage: AppImage for Linux
- synapsepm_${APP_VERSION}_amd64.deb: DEB package

System Requirements:
- Linux (x86_64)
- Python 3.8+ (if running from source)
- GLIBC 2.31+

Installation:
1. Make executable: chmod +x synapsepm
2. Run: ./synapsepm

For DEB: sudo dpkg -i synapsepm_${APP_VERSION}_amd64.deb
For AppImage: chmod +x ${APP_NAME}.AppImage && ./${APP_NAME}.AppImage

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