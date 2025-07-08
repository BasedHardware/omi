#!/usr/bin/env python3
"""
Test script for Google Calendar integration.
This script tests the basic functionality of the calendar integration.
"""

import os
import sys
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models.calendar import CalendarEventCreate, CalendarConfig
from models.conversation import Conversation, ConversationStatus
from utils.calendar import calendar_service


class CalendarIntegrationTest:
    def __init__(self):
        self.test_uid = "test_user_123"
        self.test_results = []
    
    def log_test(self, test_name, success, message=""):
        """Log test results."""
        status = "✅ PASS" if success else "❌ FAIL"
        self.test_results.append((test_name, success, message))
        print(f"{status}: {test_name}")
        if message:
            print(f"   {message}")
    
    def test_environment_variables(self):
        """Test that required environment variables are set."""
        required_vars = ['GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET']
        missing_vars = []
        
        for var in required_vars:
            if not os.getenv(var):
                missing_vars.append(var)
        
        if missing_vars:
            self.log_test(
                "Environment Variables",
                False,
                f"Missing variables: {', '.join(missing_vars)}"
            )
        else:
            self.log_test("Environment Variables", True)
    
    def test_calendar_service_initialization(self):
        """Test calendar service initialization."""
        try:
            # Mock the environment variables if they don't exist
            if not os.getenv('GOOGLE_CLIENT_ID'):
                os.environ['GOOGLE_CLIENT_ID'] = 'test_client_id'
            if not os.getenv('GOOGLE_CLIENT_SECRET'):
                os.environ['GOOGLE_CLIENT_SECRET'] = 'test_client_secret'
            
            service = calendar_service
            self.log_test("Calendar Service Initialization", True)
            
            # Test auth URL generation
            auth_url = service.get_auth_url(self.test_uid)
            if auth_url and 'oauth2' in auth_url:
                self.log_test("Auth URL Generation", True)
            else:
                self.log_test("Auth URL Generation", False, "Invalid auth URL")
                
        except Exception as e:
            self.log_test("Calendar Service Initialization", False, str(e))
    
    def test_calendar_models(self):
        """Test calendar model validation."""
        try:
            # Test CalendarEventCreate
            event = CalendarEventCreate(
                summary="Test Event",
                description="Test description",
                start_time=datetime.now(),
                end_time=datetime.now() + timedelta(hours=1),
                timezone="UTC"
            )
            self.log_test("CalendarEventCreate Model", True)
            
            # Test CalendarConfig
            config = CalendarConfig(
                auto_create_events=True,
                event_duration_minutes=60,
                default_timezone="UTC",
                include_transcript=True,
                include_summary=True
            )
            self.log_test("CalendarConfig Model", True)
            
        except Exception as e:
            self.log_test("Calendar Models", False, str(e))
    
    def test_memory_event_creation_logic(self):
        """Test the logic for creating events from memory data."""
        try:
            # Create mock memory data
            memory_data = {
                'uid': self.test_uid,
                'structured': {
                    'title': 'Test Meeting',
                    'summary': 'This is a test meeting summary'
                },
                'started_at': datetime.now().isoformat(),
                'finished_at': (datetime.now() + timedelta(hours=1)).isoformat(),
                'transcript': 'This is a test transcript of the conversation.'
            }
            
            # Mock the calendar service methods
            with patch.object(calendar_service, 'get_credentials') as mock_creds, \
                 patch.object(calendar_service, 'create_event') as mock_create:
                
                mock_creds.return_value = None  # No credentials (expected for test)
                mock_create.return_value = None  # No event created (expected for test)
                
                # Test the create_memory_event method
                result = calendar_service.create_memory_event(self.test_uid, memory_data)
                self.log_test("Memory Event Creation Logic", True, "Logic executed without errors")
                
        except Exception as e:
            self.log_test("Memory Event Creation Logic", False, str(e))
    
    def test_database_models_import(self):
        """Test that database models can be imported."""
        try:
            from database.calendar import (
                get_user_calendar_integration,
                save_user_calendar_integration,
                get_user_calendar_config,
                save_user_calendar_config
            )
            self.log_test("Database Models Import", True)
        except Exception as e:
            self.log_test("Database Models Import", False, str(e))
    
    def test_conversation_integration(self):
        """Test integration with conversation processing."""
        try:
            from utils.conversations.process_conversation import _create_calendar_event_from_conversation
            
            # Create a mock conversation
            mock_conversation = Mock()
            mock_conversation.discarded = False
            mock_conversation.structured = Mock()
            mock_conversation.structured.dict.return_value = {
                'title': 'Test Conversation',
                'summary': 'Test summary'
            }
            mock_conversation.started_at = datetime.now()
            mock_conversation.finished_at = datetime.now() + timedelta(hours=1)
            mock_conversation.get_transcript.return_value = "Test transcript"
            
            # Test the function (should not crash)
            _create_calendar_event_from_conversation(self.test_uid, mock_conversation)
            self.log_test("Conversation Integration", True)
            
        except Exception as e:
            self.log_test("Conversation Integration", False, str(e))
    
    def test_api_router_import(self):
        """Test that the API router can be imported."""
        try:
            from routers.calendar import router
            self.log_test("API Router Import", True)
        except Exception as e:
            self.log_test("API Router Import", False, str(e))
    
    def run_all_tests(self):
        """Run all tests and print summary."""
        print("🧪 Starting Google Calendar Integration Tests")
        print("=" * 50)
        
        self.test_environment_variables()
        self.test_calendar_service_initialization()
        self.test_calendar_models()
        self.test_memory_event_creation_logic()
        self.test_database_models_import()
        self.test_conversation_integration()
        self.test_api_router_import()
        
        print("\n" + "=" * 50)
        print("📊 Test Summary")
        print("=" * 50)
        
        passed = sum(1 for _, success, _ in self.test_results if success)
        failed = len(self.test_results) - passed
        
        print(f"Total tests: {len(self.test_results)}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        
        if failed > 0:
            print("\n❌ Failed tests:")
            for test_name, success, message in self.test_results:
                if not success:
                    print(f"  - {test_name}: {message}")
        
        if failed == 0:
            print("\n🎉 All tests passed! Calendar integration is ready.")
        else:
            print(f"\n⚠️  {failed} test(s) failed. Please check the configuration.")
        
        return failed == 0


def main():
    """Main function to run the tests."""
    test_runner = CalendarIntegrationTest()
    success = test_runner.run_all_tests()
    
    if success:
        print("\n🚀 Next steps:")
        print("1. Set up your Google Cloud Console project")
        print("2. Configure OAuth2 credentials")
        print("3. Set environment variables")
        print("4. Start the backend server")
        print("5. Test the integration with a real user")
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())