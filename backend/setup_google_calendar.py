#!/usr/bin/env python3
"""
Setup script for Google Calendar integration with Omi.
This script helps configure the necessary environment variables and dependencies.
"""

import os
import subprocess
import sys

def print_step(step_num, description):
    print(f"\n🔧 Step {step_num}: {description}")
    print("=" * 50)

def check_dependency(package_name):
    """Check if a Python package is installed."""
    try:
        __import__(package_name)
        return True
    except ImportError:
        return False

def install_dependency(package_name):
    """Install a Python package."""
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
        return True
    except subprocess.CalledProcessError:
        return False

def main():
    print("🗓️  Google Calendar Integration Setup for Omi")
    print("=" * 50)
    
    # Step 1: Check dependencies
    print_step(1, "Checking dependencies")
    
    required_packages = [
        "google-auth-oauthlib", 
        "google-api-python-client", 
        "google-auth",
        "pytz"
    ]
    
    missing_packages = []
    for package in required_packages:
        package_check = package.replace('-', '_')  # Handle naming differences
        if not check_dependency(package_check):
            missing_packages.append(package)
    
    if missing_packages:
        print(f"❌ Missing packages: {', '.join(missing_packages)}")
        print("📦 Installing missing packages...")
        
        for package in missing_packages:
            print(f"   Installing {package}...")
            if install_dependency(package):
                print(f"   ✅ {package} installed successfully")
            else:
                print(f"   ❌ Failed to install {package}")
                return False
    else:
        print("✅ All required packages are installed")
    
    # Step 2: Environment variables check
    print_step(2, "Checking environment variables")
    
    env_vars = {
        'GOOGLE_CLIENT_ID': 'Google OAuth Client ID',
        'GOOGLE_CLIENT_SECRET': 'Google OAuth Client Secret',
        'GOOGLE_REDIRECT_URI': 'Google OAuth Redirect URI (optional, has default)'
    }
    
    missing_env_vars = []
    for var, description in env_vars.items():
        if not os.getenv(var):
            missing_env_vars.append((var, description))
    
    if missing_env_vars:
        print("❌ Missing environment variables:")
        for var, desc in missing_env_vars:
            print(f"   {var}: {desc}")
        print("\n📝 To set these variables, add them to your .env file or environment:")
        for var, desc in missing_env_vars:
            print(f"   export {var}='your_value_here'")
        print("\n🔗 Get your Google OAuth credentials at: https://console.cloud.google.com/apis/credentials")
    else:
        print("✅ All required environment variables are set")
    
    # Step 3: Google Cloud Setup Instructions
    print_step(3, "Google Cloud Console Setup")
    
    print("""
📋 Follow these steps to set up Google Calendar API:

1. Go to Google Cloud Console: https://console.cloud.google.com/
2. Create a new project or select an existing one
3. Enable the Google Calendar API:
   - Go to 'APIs & Services' > 'Library'
   - Search for 'Google Calendar API'
   - Click 'Enable'
4. Create OAuth 2.0 credentials:
   - Go to 'APIs & Services' > 'Credentials'
   - Click 'Create Credentials' > 'OAuth 2.0 Client ID'
   - Choose 'Web application'
   - Add authorized redirect URI: http://localhost:8000/v1/calendar/oauth/callback
   - Save the Client ID and Client Secret
5. Set the environment variables with your credentials

🔐 Required OAuth Scopes:
   - https://www.googleapis.com/auth/calendar
   - https://www.googleapis.com/auth/userinfo.email
   - https://www.googleapis.com/auth/userinfo.profile
""")
    
    # Step 4: Database collections info
    print_step(4, "Database Collections")
    
    print("""
📊 The integration will create these Firestore collections:
   - calendar_integrations: User OAuth tokens and calendar info
   - calendar_configs: User preferences and settings
   - calendar_events: Record of created calendar events

🔄 These collections will be created automatically when users connect their calendars.
""")
    
    # Step 5: API endpoints info
    print_step(5, "Available API Endpoints")
    
    print("""
🔌 Calendar API endpoints available:
   - GET  /v1/calendar/auth - Initiate OAuth flow
   - GET  /v1/calendar/oauth/callback - Handle OAuth callback
   - GET  /v1/calendar/status - Check integration status
   - GET  /v1/calendar/config - Get user configuration
   - PUT  /v1/calendar/config - Update user configuration
   - POST /v1/calendar/events - Create calendar event
   - GET  /v1/calendar/events - Get upcoming events
   - DELETE /v1/calendar/disconnect - Disconnect integration
   - GET  /v1/calendar/test - Test integration
""")
    
    # Step 6: Usage example
    print_step(6, "Usage Example")
    
    print("""
🚀 Example usage flow:
1. User calls GET /v1/calendar/auth to get OAuth URL
2. User visits OAuth URL and grants permissions
3. Google redirects to /v1/calendar/oauth/callback
4. Integration is now active and will create calendar events automatically
5. User can configure settings via PUT /v1/calendar/config

🔄 Automatic event creation:
   - When a conversation is processed, a calendar event is automatically created
   - Events include conversation title, summary, and transcript (if enabled)
   - User can configure event duration, timezone, and content preferences
""")
    
    print("\n🎉 Setup complete! Your Google Calendar integration is ready to use.")
    print("📖 Check the documentation for more details on usage and configuration.")
    
    return True

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Setup interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Setup failed with error: {e}")
        sys.exit(1)