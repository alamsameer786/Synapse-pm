#!/bin/bash
# ============================================================
# SYNAPPM - iOS BUILD SCRIPT v5.2.1
# Production-ready with code signing
# ============================================================

set -e

APP_NAME="SynapsePM"
APP_VERSION="12.0.0"
APP_COMPANY="SynapsePM Technologies"
APP_IDENTIFIER="com.synapsepm.app"
TEAM_ID="${APPLE_TEAM_ID:-}"

echo "============================================================"
echo "  📱 ${APP_NAME} - iOS BUILDER v${APP_VERSION}"
echo "============================================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check dependencies
echo "🔍 Checking dependencies..."

if ! command -v xcodebuild &> /dev/null; then
    echo -e "${RED}❌ Xcode not found!${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Xcode found${NC}"

# Check for code signing
if [ -n "$TEAM_ID" ]; then
    echo -e "${GREEN}✅ Team ID found: ${TEAM_ID}${NC}"
else
    echo -e "${YELLOW}⚠️ No team ID found. Build will not be signed.${NC}"
    echo "  Set APPLE_TEAM_ID environment variable."
fi

# Clean previous build
echo ""
echo "🧹 Cleaning previous build..."
cd ios
rm -rf build
xcodebuild clean -workspace SynapsePM.xcworkspace -scheme SynapsePM
cd ..

# Build iOS app
echo ""
echo "🔨 Building iOS app..."
cd ios

if [ -n "$TEAM_ID" ]; then
    xcodebuild archive \
        -workspace SynapsePM.xcworkspace \
        -scheme SynapsePM \
        -configuration Release \
        -archivePath build/SynapsePM.xcarchive \
        CODE_SIGN_IDENTITY="iPhone Distribution" \
        DEVELOPMENT_TEAM="${TEAM_ID}"
    
    echo -e "${GREEN}✅ Archive created${NC}"
    
    # Export IPA
    echo ""
    echo "📦 Exporting IPA..."
    xcodebuild -exportArchive \
        -archivePath build/SynapsePM.xcarchive \
        -exportOptionsPlist exportOptions.plist \
        -exportPath build/
else
    # Build without signing (simulator only)
    xcodebuild build \
        -workspace SynapsePM.xcworkspace \
        -scheme SynapsePM \
        -configuration Debug \
        -derivedDataPath build \
        -sdk iphonesimulator
fi

cd ..

# Verify build
if [ -f "ios/build/SynapsePM.ipa" ]; then
    echo -e "${GREEN}✅ Build successful${NC}"
    cp "ios/build/SynapsePM.ipa" "dist/SynapsePM-iOS.ipa"
    echo "   📁 IPA: dist/SynapsePM-iOS.ipa"
else
    echo -e "${YELLOW}⚠️ IPA not found. Simulator build only.${NC}"
fi

echo ""
echo "============================================================"
echo -e "${GREEN}  ✅ BUILD COMPLETE!${NC}"
echo "  📁 Output Directory: dist/"
echo ""
echo "  📦 Files created:"
ls -la dist/ | grep "SynapsePM" | awk '{print "   - " $9 " (" $5 " bytes)"}'
echo ""
echo "============================================================"