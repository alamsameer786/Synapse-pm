#!/usr/bin/env python3
"""
SYNAPSEPM - AUTO-UPDATER
"""

import os
import sys
import json
import time
import hashlib
import requests
import tempfile
import subprocess
import zipfile
import shutil
from pathlib import Path
from datetime import datetime

# ============================================================
# CONFIGURATION
# ============================================================

APP_NAME = "SynapsePM"
APP_VERSION = "12.0.0"
UPDATE_URL = "https://api.synapsepm.com/updates"
BASE_DIR = Path(__file__).resolve().parent.parent

# ============================================================
# UPDATER
# ============================================================

class Updater:
    """Auto-update functionality"""
    
    def __init__(self):
        self.current_version = APP_VERSION
        self.update_url = UPDATE_URL
        self.base_dir = BASE_DIR
        self.temp_dir = Path(tempfile.gettempdir()) / 'synapsepm_update'
        self.temp_dir.mkdir(parents=True, exist_ok=True)
    
    def check_for_updates(self) -> dict:
        """Check if update is available"""
        try:
            response = requests.get(
                self.update_url,
                params={
                    'app': APP_NAME,
                    'version': self.current_version,
                    'platform': sys.platform
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('available', False):
                    return {
                        'available': True,
                        'version': data.get('version'),
                        'release_notes': data.get('release_notes', ''),
                        'download_url': data.get('download_url'),
                        'checksum': data.get('checksum'),
                        'size': data.get('size', 0)
                    }
            
            return {'available': False}
            
        except Exception as e:
            print(f"Update check failed: {e}")
            return {'available': False, 'error': str(e)}
    
    def download_update(self, download_url: str, checksum: str = None) -> bool:
        """Download update package"""
        try:
            print(f"📥 Downloading update from: {download_url}")
            response = requests.get(download_url, stream=True, timeout=60)
            
            if response.status_code != 200:
                print(f"❌ Download failed: {response.status_code}")
                return False
            
            update_file = self.temp_dir / 'update.zip'
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(update_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            progress = (downloaded / total_size) * 100
                            print(f"\r📥 Download progress: {progress:.1f}%", end='')
            
            print("\n✅ Download complete")
            
            # Verify checksum
            if checksum:
                if not self.verify_checksum(update_file, checksum):
                    print("❌ Checksum verification failed")
                    return False
            
            return True
            
        except Exception as e:
            print(f"❌ Download failed: {e}")
            return False
    
    def verify_checksum(self, file_path: Path, expected_checksum: str) -> bool:
        """Verify file checksum"""
        try:
            sha256 = hashlib.sha256()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    sha256.update(chunk)
            actual = sha256.hexdigest()
            return actual == expected_checksum
        except Exception:
            return False
    
    def install_update(self) -> bool:
        """Install downloaded update"""
        try:
            update_file = self.temp_dir / 'update.zip'
            
            if not update_file.exists():
                print("❌ Update file not found")
                return False
            
            # Extract update
            extract_dir = self.temp_dir / 'extracted'
            extract_dir.mkdir(parents=True, exist_ok=True)
            
            print("📦 Extracting update...")
            with zipfile.ZipFile(update_file, 'r') as zipf:
                zipf.extractall(extract_dir)
            
            # Create update script
            if sys.platform == 'win32':
                self._create_windows_update_script(extract_dir)
            else:
                self._create_unix_update_script(extract_dir)
            
            return True
            
        except Exception as e:
            print(f"❌ Installation failed: {e}")
            return False
    
    def _create_windows_update_script(self, extract_dir: Path):
        """Create Windows update script"""
        script_content = f"""@echo off
echo Updating SynapsePM...
timeout /t 2 /nobreak > nul

REM Copy new files
xcopy /E /I /Y "{extract_dir}\\*" "{self.base_dir}\\"

echo Update complete!
echo Starting SynapsePM...
start "" "{self.base_dir}\\dist\\synapsepm.exe"

REM Cleanup
rmdir /S /Q "{self.temp_dir}"

exit
"""
        script_path = self.temp_dir / 'update.bat'
        script_path.write_text(script_content)
        subprocess.Popen([str(script_path)], shell=True)
    
    def _create_unix_update_script(self, extract_dir: Path):
        """Create Unix update script"""
        script_content = f"""#!/bin/bash
echo "Updating SynapsePM..."
sleep 2

# Copy new files
cp -R "{extract_dir}/"* "{self.base_dir}/"

echo "Update complete!"
echo "Starting SynapsePM..."
"{self.base_dir}/dist/synapsepm" &

# Cleanup
rm -rf "{self.temp_dir}"
"""
        script_path = self.temp_dir / 'update.sh'
        script_path.write_text(script_content)
        script_path.chmod(0o755)
        subprocess.Popen([str(script_path)], shell=True)
    
    def run(self):
        """Main update check and install"""
        print(f"🔍 Checking for updates (v{self.current_version})...")
        
        result = self.check_for_updates()
        
        if result.get('available'):
            print(f"🆕 New version available: v{result['version']}")
            print(f"📝 Release notes: {result.get('release_notes', 'N/A')}")
            
            # Ask user
            response = input("Download and install update? (y/n): ")
            if response.lower() == 'y':
                if self.download_update(result['download_url'], result.get('checksum')):
                    print("📦 Installing update...")
                    self.install_update()
                else:
                    print("❌ Update failed")
            else:
                print("Update skipped")
        else:
            print("✅ You are running the latest version")

if __name__ == '__main__':
    updater = Updater()
    updater.run()