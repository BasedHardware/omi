#!/usr/bin/env python3
"""
Test script to verify the setup of the OMI-Composio integration plugin.
"""

import os
import sys
from dotenv import load_dotenv

def check_environment():
    """Check if the required environment variables are set."""
    load_dotenv(verbose=True)
    
    required_vars = [
        'OMI_APP_ID',
        'OMI_API_KEY',
        'NOTION_CLIENT_ID',
        'NOTION_CLIENT_SECRET',
        'NOTION_REDIRECT_URI',
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print("❌ Missing environment variables:")
        for var in missing_vars:
            print(f"  - {var}")
        print("\nPlease create a .env file with these variables. See .env.template for reference.")
    else:
        print("✅ All required environment variables are set.")
    
    return len(missing_vars) == 0

def check_dependencies():
    """Check if the required dependencies are installed."""
    try:
        import fastapi
        import uvicorn
        import jinja2
        import requests
        print("✅ All required dependencies are installed.")
        return True
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("\nPlease install the required dependencies with:")
        print("  pip install -r requirements.txt")
        return False

def check_directories():
    """Check if the required directories exist."""
    required_dirs = [
        'templates',
        'static',
        'src',
        'data',
    ]
    
    missing_dirs = [dir for dir in required_dirs if not os.path.isdir(dir)]
    
    if missing_dirs:
        print("❌ Missing directories:")
        for dir in missing_dirs:
            print(f"  - {dir}")
            # Create the directory
            os.makedirs(dir, exist_ok=True)
            print(f"  ✓ Created {dir} directory")
    else:
        print("✅ All required directories exist.")
    
    return len(missing_dirs) == 0

def main():
    """Run all checks."""
    print("====== OMI-Composio Integration Setup Check ======\n")
    
    # Ensure we're in the right directory
    if not os.path.exists('requirements.txt'):
        print("❌ Please run this script from the plugin root directory (plugins/composio)")
        return False
    
    env_ok = check_environment()
    deps_ok = check_dependencies()
    dirs_ok = check_directories()
    
    print("\n====== Summary ======")
    if env_ok and deps_ok and dirs_ok:
        print("✅ Setup complete! You can run the application with:")
        print("  uvicorn main:app --reload")
    else:
        print("❌ Some issues need to be fixed before running the application.")
    
    return env_ok and deps_ok and dirs_ok

if __name__ == "__main__":
    sys.exit(0 if main() else 1) 