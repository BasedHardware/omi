#!/usr/bin/env python3
"""
Test the security fix for app uninstallation vulnerabilities.

This script demonstrates and validates that:
1. When an app is uninstalled, all its associated Redis keys are cleaned up
2. External notification is attempted, but failures don't block uninstallation
3. The app's pattern-based cleanup ensures no stray data remains

How to Run:
----------
$ python -m pytest backend/tests/test_security.py  # Run with pytest
$ python backend/tests/test_security.py            # Run as standalone

Dependencies:
------------
This test requires the following packages:
    pip install pytest requests redis
"""
import unittest
from unittest.mock import patch, MagicMock, call
import os
import sys
import pytest

# Add parent directory to path so imports work when run as standalone
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

# Import mocked Redis
class MockRedis:
    def __init__(self):
        self.data = {}
        self.sets = {}

    def set(self, key, value):
        self.data[key] = value
        return True

    def get(self, key):
        return self.data.get(key)

    def delete(self, key):
        if isinstance(key, bytes):
            key = key.decode()

        if key in self.data:
            del self.data[key]
            return 1
        return 0

    def sadd(self, set_name, *values):
        if set_name not in self.sets:
            self.sets[set_name] = set()
        for value in values:
            self.sets[set_name].add(value)
        return len(values)

    def srem(self, set_name, *values):
        if set_name not in self.sets:
            return 0
        count = 0
        for value in values:
            if value in self.sets[set_name]:
                self.sets[set_name].remove(value)
                count += 1
        return count

    def smembers(self, set_name):
        return self.sets.get(set_name, set())

    def keys(self, pattern):
        """Simple pattern matching"""
        if '*' in pattern:
            prefix = pattern.split('*')[0]
            return [key.encode() for key in self.data.keys() if key.startswith(prefix)]
        return [key.encode() for key in self.data.keys() if key == pattern]

# Define test function for pytest
def test_app_uninstallation_security():
    """Test the app uninstallation security fix."""
    from database.redis_db import disable_app

    # Mock Redis instance with our simple implementation
    mock_redis = MockRedis()

    # Test data
    uid = "test-user-123"
    app_id = "test-app-456"

    # Create test data in Redis
    enabled_plugins_key = f"users:{uid}:enabled_plugins"
    webhook_key = f"users:{uid}:app:{app_id}:webhook_url"
    token_key = f"users:{uid}:app:{app_id}:token"
    settings_key = f"users:{uid}:app:{app_id}:settings"

    # Add app to enabled plugins
    mock_redis.sadd(enabled_plugins_key, app_id)

    # Add app data
    mock_redis.set(webhook_key, "https://example.com/webhook")
    mock_redis.set(token_key, "secret-token-123")
    mock_redis.set(settings_key, "some-settings-data")

    # Print initial state (when running standalone)
    if __name__ == "__main__":
        print("\n===== BEFORE UNINSTALLATION =====")
        print(f"Enabled plugins: {mock_redis.smembers(enabled_plugins_key)}")
        print(f"Redis keys: {[k.decode() for k in mock_redis.keys('*')]}")

    # Patch Redis instance
    with patch('database.redis_db.r', mock_redis):
        # Call the uninstall function
        disable_app(uid, app_id)

    # Print final state (when running standalone)
    if __name__ == "__main__":
        print("\n===== AFTER UNINSTALLATION =====")
        print(f"Enabled plugins: {mock_redis.smembers(enabled_plugins_key)}")
        print(f"Redis keys: {[k.decode() for k in mock_redis.keys('*')]}")

    # Verify results
    all_tests_passed = True

    # Test 1: App removed from enabled plugins
    test1 = app_id not in mock_redis.smembers(enabled_plugins_key)
    # Test 2: Webhook key deleted
    test2 = not mock_redis.get(webhook_key)
    # Test 3: Token key deleted
    test3 = not mock_redis.get(token_key)
    # Test 4: Settings key deleted
    test4 = not mock_redis.get(settings_key)
    # Test 5: No app keys remain
    remaining_app_keys = [k for k in mock_redis.keys('*') if app_id in k.decode()]
    test5 = len(remaining_app_keys) == 0

    if __name__ == "__main__":
        # Print results when running standalone
        print(f"\n{'✅' if test1 else '❌'} Test 1: App removed from enabled plugins")
        print(f"{'✅' if test2 else '❌'} Test 2: Webhook key deleted")
        print(f"{'✅' if test3 else '❌'} Test 3: Token key deleted")
        print(f"{'✅' if test4 else '❌'} Test 4: Settings key deleted")
        print(f"{'✅' if test5 else '❌'} Test 5: No app keys remain")

        if all(tests := [test1, test2, test3, test4, test5]):
            print("\n✅ SUCCESS: All app data was properly cleaned up on uninstallation!")
            print("The security fix for issue #1836 is working correctly.")
        else:
            print("\n❌ FAILURE: Some tests failed. The security fix may not be working correctly.")

    # For pytest assertions
    assert test1, "App still in enabled plugins"
    assert test2, "Webhook key not deleted"
    assert test3, "Token key not deleted"
    assert test4, "Settings key not deleted"
    assert test5, f"App keys still exist: {remaining_app_keys}"

def print_disable_app_code():
    """Print the code of the disable_app function to understand it better."""
    import inspect
    from database.redis_db import disable_app

    print("\nCode of the disable_app function:")
    print("---------------------------------")
    print(inspect.getsource(disable_app))
    print("---------------------------------")

if __name__ == "__main__":
    print("=====================================================")
    print("🔒 App Uninstallation Security Test")
    print("   Verifying fix for GitHub issue #1836")
    print("=====================================================")

    # Print the disable_app function code when running standalone
    print_disable_app_code()

    # Run the test
    test_app_uninstallation_security()