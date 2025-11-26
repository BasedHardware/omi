"""
Pytest configuration for integration tests.
"""

import os
import sys

import firebase_admin
import pytest
from dotenv import load_dotenv
from firebase_admin import credentials

# Add project root to path (go up from integration -> tests -> backend -> root)
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
sys.path.insert(0, project_root)

# Also add backend directory
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

env_file = os.path.join(backend_dir, '.env')
if os.path.exists(env_file):
    load_dotenv(env_file)
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = backend_dir + "/" + os.getenv('GOOGLE_APPLICATION_CREDENTIALS')


@pytest.fixture(scope="session", autouse=True)
def initialize_firebase():
    """Initialize Firebase Admin SDK before running tests"""
    try:
        cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred)
        print("✅ Firebase initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize Firebase: {e}")
        print("Make sure GOOGLE_APPLICATION_CREDENTIALS is set")
        raise

    yield


def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line("markers", "integration: mark test as an integration test")


def pytest_collection_modifyitems(config, items):
    """Automatically mark all tests in integration folder"""
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
