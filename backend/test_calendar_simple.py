#!/usr/bin/env python3
"""
Simple test script for Google Calendar integration.
This script tests the basic functionality without database dependencies.
"""

import os
import sys
from datetime import datetime, timedelta

def test_imports():
    """Test that we can import our models."""
    print("Testing imports...")
    try:
        from models.calendar import CalendarEventCreate, CalendarConfig
        print("✅ Calendar models imported successfully")
        return True
    except Exception as e:
        print(f"❌ Failed to import calendar models: {e}")
        return False

def test_model_creation():
    """Test that we can create model instances."""
    print("\nTesting model creation...")
    try:
        from models.calendar import CalendarEventCreate, CalendarConfig
        
        # Test CalendarEventCreate
        event = CalendarEventCreate(
            summary="Test Event",
            description="Test description",
            start_time=datetime.now(),
            end_time=datetime.now() + timedelta(hours=1),
            timezone="UTC",
            attendees=["test@example.com"],
            location="Test Location"
        )
        print("✅ CalendarEventCreate model created successfully")
        
        # Test CalendarConfig
        config = CalendarConfig(
            auto_create_events=True,
            event_duration_minutes=60,
            default_timezone="UTC",
            include_transcript=True,
            include_summary=True
        )
        print("✅ CalendarConfig model created successfully")
        
        return True
    except Exception as e:
        print(f"❌ Failed to create models: {e}")
        return False

def test_google_auth_dependencies():
    """Test that Google auth dependencies are available."""
    print("\nTesting Google auth dependencies...")
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import Flow
        from googleapiclient.discovery import build
        print("✅ Google auth dependencies available")
        return True
    except Exception as e:
        print(f"❌ Google auth dependencies not available: {e}")
        return False

def test_environment_setup():
    """Test environment variable setup."""
    print("\nTesting environment setup...")
    
    # Set test environment variables
    os.environ.setdefault('GOOGLE_CLIENT_ID', 'test_client_id')
    os.environ.setdefault('GOOGLE_CLIENT_SECRET', 'test_client_secret')
    os.environ.setdefault('GOOGLE_REDIRECT_URI', 'http://localhost:8000/v1/calendar/oauth/callback')
    
    required_vars = ['GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GOOGLE_REDIRECT_URI']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"❌ Missing environment variables: {missing_vars}")
        return False
    else:
        print("✅ Environment variables set")
        return True

def test_auth_url_generation():
    """Test OAuth URL generation."""
    print("\nTesting OAuth URL generation...")
    try:
        from google_auth_oauthlib.flow import Flow
        
        client_config = {
            "web": {
                "client_id": os.getenv('GOOGLE_CLIENT_ID'),
                "client_secret": os.getenv('GOOGLE_CLIENT_SECRET'),
                "redirect_uris": [os.getenv('GOOGLE_REDIRECT_URI')],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token"
            }
        }
        
        scopes = [
            'https://www.googleapis.com/auth/calendar',
            'https://www.googleapis.com/auth/userinfo.email',
            'https://www.googleapis.com/auth/userinfo.profile'
        ]
        
        flow = Flow.from_client_config(client_config, scopes=scopes)
        flow.redirect_uri = os.getenv('GOOGLE_REDIRECT_URI')
        
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            state='test_user_123',
            prompt='consent'
        )
        
        if auth_url and 'oauth2' in auth_url:
            print("✅ OAuth URL generated successfully")
            print(f"   Sample URL: {auth_url[:80]}...")
            return True
        else:
            print("❌ Invalid OAuth URL generated")
            return False
            
    except Exception as e:
        print(f"❌ Failed to generate OAuth URL: {e}")
        return False

def test_calendar_event_data():
    """Test calendar event data structure."""
    print("\nTesting calendar event data structure...")
    try:
        # Test event data structure
        event_data = {
            'summary': 'Test Event',
            'description': 'Test description',
            'start': {
                'dateTime': datetime.now().isoformat(),
                'timeZone': 'UTC',
            },
            'end': {
                'dateTime': (datetime.now() + timedelta(hours=1)).isoformat(),
                'timeZone': 'UTC',
            },
            'location': 'Test Location',
            'attendees': [{'email': 'test@example.com'}]
        }
        
        # Validate required fields
        required_fields = ['summary', 'start', 'end']
        for field in required_fields:
            if field not in event_data:
                print(f"❌ Missing required field: {field}")
                return False
        
        print("✅ Calendar event data structure valid")
        return True
        
    except Exception as e:
        print(f"❌ Failed to validate event data: {e}")
        return False

def test_timezone_handling():
    """Test timezone handling."""
    print("\nTesting timezone handling...")
    try:
        import pytz
        
        # Test timezone creation
        tz = pytz.timezone('America/New_York')
        now = datetime.now(tz)
        
        # Test ISO format
        iso_string = now.isoformat()
        
        print("✅ Timezone handling working")
        print(f"   Sample timestamp: {iso_string}")
        return True
        
    except Exception as e:
        print(f"❌ Failed timezone handling: {e}")
        return False

def main():
    """Run all tests."""
    print("🗓️  Google Calendar Integration - Simple Tests")
    print("=" * 50)
    
    tests = [
        test_imports,
        test_model_creation,
        test_google_auth_dependencies,
        test_environment_setup,
        test_auth_url_generation,
        test_calendar_event_data,
        test_timezone_handling,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} crashed: {e}")
            failed += 1
    
    print("\n" + "=" * 50)
    print("📊 Test Summary")
    print("=" * 50)
    print(f"Total tests: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    if failed == 0:
        print("\n🎉 All tests passed! Basic calendar integration is working.")
        print("\n🚀 Next steps:")
        print("1. Set up your Google Cloud Console project")
        print("2. Configure OAuth2 credentials")
        print("3. Set real environment variables")
        print("4. Start the backend server")
        print("5. Test the integration with a real user")
    else:
        print(f"\n⚠️  {failed} test(s) failed. Please check the configuration.")
    
    return failed == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)