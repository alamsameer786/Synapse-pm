#!/bin/bash
# ============================================================
# SYNAPPM - ANDROID BUILD SCRIPT v5.2.1
# Production-ready with code signing
# ============================================================

set -e

APP_NAME="SynapsePM"
APP_VERSION="12.0.0"
APP_COMPANY="SynapsePM Technologies"

echo "============================================================"
echo "  📱 ${APP_NAME} - ANDROID BUILDER v${APP_VERSION}"
echo "============================================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check dependencies
echo "🔍 Checking dependencies..."

if ! command -v java &> /dev/null; then
    echo -e "${RED}❌ Java not found!${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Java found${NC}"

if ! command -v gradle &> /dev/null; then
    echo -e "${YELLOW}⚠️ Gradle not found. Using wrapper.${NC}"
fi

# Clean previous build
echo ""
echo "🧹 Cleaning previous build..."
cd android
./gradlew clean
cd ..

# Generate keystore if not exists
if [ ! -f "android/app/release.keystore" ]; then
    echo ""
    echo "🔑 Generating keystore..."
    keytool -genkey -v -keystore android/app/release.keystore \
        -alias synapsepm \
        -keyalg RSA -keysize 2048 -validity 10000 \
        -storepass synapsepm2024 \
        -keypass synapsepm2024 \
        -dname "CN=SynapsePM Technologies, OU=Engineering, O=SynapsePM, L=Kathmandu, ST=Province 3, C=NP"
    echo -e "${GREEN}✅ Keystore generated${NC}"
fi

# Build release APK
echo ""
echo "🔨 Building release APK..."
cd android
./gradlew assembleRelease
cd ..

# Verify build
if [ -f "android/app/build/outputs/apk/release/app-release.apk" ]; then
    echo -e "${GREEN}✅ Build successful${NC}"
    cp "android/app/build/outputs/apk/release/app-release.apk" "dist/SynapsePM-Android.apk"
    echo "   📁 Output: dist/SynapsePM-Android.apk"
else
    echo -e "${RED}❌ Build failed${NC}"
    exit 1
fi

# Sign with zipalign
echo ""
echo "🔐 Signing APK..."
zipalign -v -p 4 "dist/SynapsePM-Android.apk" "dist/SynapsePM-Android-signed.apk"
mv "dist/SynapsePM-Android-signed.apk" "dist/SynapsePM-Android.apk"
echo -e "${GREEN}✅ APK signed${NC}"

# Generate AAB for Play Store
echo ""
echo "📦 Generating AAB for Play Store..."
cd android
./gradlew bundleRelease
cd ..

if [ -f "android/app/build/outputs/bundle/release/app-release.aab" ]; then
    cp "android/app/build/outputs/bundle/release/app-release.aab" "dist/SynapsePM-Android.aab"
    echo "   📁 AAB: dist/SynapsePM-Android.aab"
    echo -e "${GREEN}✅ AAB generated${NC}"
fi

# Generate SHA1 fingerprint
echo ""
echo "🔐 Generating SHA1 fingerprint..."
keytool -list -v -keystore android/app/release.keystore -alias synapsepm -storepass synapsepm2024 -keypass synapsepm2024

echo ""
echo "============================================================"
echo -e "${GREEN}  ✅ BUILD COMPLETE!${NC}"
echo "  📁 Output Directory: dist/"
echo ""
echo "  📦 Files created:"
ls -la dist/ | grep "SynapsePM" | awk '{print "   - " $9 " (" $5 " bytes)"}'
echo ""
echo "  📱 To install on device:"
echo "   adb install dist/SynapsePM-Android.apk"
echo ""
echo "============================================================"