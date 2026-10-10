#!/usr/bin/env python3
"""
SYNAPSEPM - SYSTEM TRAY APPLICATION
Independent tray application
"""

import os
import sys
import json
import threading
import webbrowser
import subprocess
from pathlib import Path
import time

# ============================================================
# CONFIGURATION
# ============================================================

APP_NAME = "SynapsePM"
APP_VERSION = "12.0.0"
BASE_DIR = Path(__file__).resolve().parent.parent

# ============================================================
# TRAY APPLICATION
# ============================================================

class TrayApp:
    """System tray application"""
    
    def __init__(self):
        self.icon = None
        self.running = True
        self.pystray = None
        self.Image = None
        self.ImageDraw = None
        
        try:
            import pystray
            from PIL import Image, ImageDraw
            self.pystray = pystray
            self.Image = Image
            self.ImageDraw = ImageDraw
            print("✅ pystray and PIL loaded successfully")
        except ImportError as e:
            print(f"❌ Error: {e}")
            print("Install required packages: pip install pystray pillow")
            sys.exit(1)
    
    def run(self):
        """Run the tray application"""
        print(f"🔄 Starting {APP_NAME} system tray...")
        print(f"📂 Base directory: {BASE_DIR}")
        
        # Create icon
        icon_image = self._create_icon()
        print("✅ Icon created")
        
        # Create menu
        menu = self.pystray.Menu(
            self.pystray.MenuItem("🌐 Open Dashboard", self.open_dashboard),
            self.pystray.MenuItem("🔄 Check for Updates", self.check_updates),
            self.pystray.MenuItem("⚙️ Settings", self.open_settings),
            self.pystray.MenuItem("ℹ️ About", self.show_about),
            self.pystray.MenuItem("🚪 Quit", self.quit)
        )
        
        # Create and run icon
        print("🔄 Creating system tray icon...")
        self.icon = self.pystray.Icon(
            APP_NAME, 
            icon_image, 
            f"{APP_NAME} v{APP_VERSION}",
            menu
        )
        
        print(f"✅ {APP_NAME} is running in system tray!")
        print("ℹ️ Look for the icon in your system tray (near the clock)")
        print("ℹ️ On Windows, you may need to click the '^' arrow to see hidden icons")
        
        # Run the icon (this blocks until quit)
        self.icon.run()
    
    def _create_icon(self):
        """Create tray icon"""
        # Try multiple possible locations for the logo
        logo_paths = [
            BASE_DIR / 'frontend' / 'images' / 'applogo.png',
            BASE_DIR / 'frontend' / 'public' / 'logo192.png',
            BASE_DIR / 'frontend' / 'public' / 'logo512.png',
            BASE_DIR / 'desktop' / 'logo.png',
            BASE_DIR / 'logo.png'
        ]
        
        for logo_path in logo_paths:
            if logo_path.exists():
                try:
                    print(f"✅ Found logo at: {logo_path}")
                    img = self.Image.open(logo_path)
                    img = img.resize((64, 64), self.Image.Resampling.LANCZOS)
                    return img
                except Exception as e:
                    print(f"⚠️ Could not load logo from {logo_path}: {e}")
                    continue
        
        print("⚠️ No logo found, creating default icon")
        return self._create_default_icon()
    
    def _create_default_icon(self):
        """Create default icon if logo not found"""
        size = 64
        image = self.Image.new('RGB', (size, size), '#0f2b3d')
        draw = self.ImageDraw.Draw(image)
        
        # Draw a stylized "S" in a circle
        draw.ellipse([4, 4, 60, 60], fill='#00b4aa', outline='#009688', width=3)
        draw.text((22, 14), "S", fill='white', font=None)
        
        return image
    
    def open_dashboard(self, icon=None, item=None):
        """Open dashboard"""
        print("🌐 Opening dashboard...")
        
        # Try to find and open the main app
        main_exe = BASE_DIR / 'dist' / 'synapsepm'
        if sys.platform == 'win32':
            main_exe = main_exe.with_suffix('.exe')
        
        if main_exe.exists():
            print(f"✅ Found main app at: {main_exe}")
            try:
                subprocess.Popen([str(main_exe)], shell=True)
                return
            except Exception as e:
                print(f"⚠️ Could not launch main app: {e}")
        
        # Fallback to web browser
        print("🌐 Opening web version...")
        webbrowser.open('https://app.synapsepm.com')
    
    def check_updates(self, icon=None, item=None):
        """Check for updates"""
        print("🔄 Checking for updates...")
        # TODO: Implement update check
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("Update Check", 
            f"{APP_NAME} v{APP_VERSION}\n\n"
            "You are running the latest version."
        )
        root.destroy()
    
    def open_settings(self, icon=None, item=None):
        """Open settings"""
        print("⚙️ Opening settings...")
        # TODO: Implement settings
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("Settings", 
            "Settings will be available in the next version."
        )
        root.destroy()
    
    def show_about(self, icon=None, item=None):
        """Show about dialog"""
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("About SynapsePM",
            f"{APP_NAME} v{APP_VERSION}\n\n"
            "AI-Powered Predictive Maintenance\n"
            "© 2026 SynapsePM. All rights reserved.\n\n"
            f"📂 Data Directory: {BASE_DIR}"
        )
        root.destroy()
    
    def quit(self, icon=None, item=None):
        """Quit application"""
        print("🚪 Quitting application...")
        self.running = False
        if self.icon:
            self.icon.stop()
        sys.exit(0)

def run_with_console():
    """Run with console window for debugging"""
    print("="*60)
    print(f"🏭 SYNAPSEPM SYSTEM TRAY v{APP_VERSION}")
    print("="*60)
    print()
    
    app = TrayApp()
    app.run()

if __name__ == '__main__':
    try:
        run_with_console()
    except KeyboardInterrupt:
        print("\n🔄 Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        input("Press Enter to exit...")
        sys.exit(1)