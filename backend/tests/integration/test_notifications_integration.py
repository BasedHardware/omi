"""
Simplified integration tests for notification system.
Tests real Firebase notifications.

Setup:
1. pip install pytest pytest-asyncio
2. Set TEST_USER_ID environment variable (a real Firebase user)
3. Run: pytest backend/tests/integration/test_notifications_integration.py -v
"""

import pytest
import os
from datetime import datetime, timedelta

from backend.utils.notifications import (
    send_notification,
    send_bulk_notification,
    send_action_item_created_notification,
    send_action_item_completed_notification,
    send_training_data_submitted_notification,
)
import database.notifications as notification_db


@pytest.fixture
def test_user_id():
    """Get test user ID from environment"""
    user_id = os.getenv('TEST_USER_ID')
    if not user_id:
        pytest.skip("TEST_USER_ID environment variable not set")
    return user_id


@pytest.fixture
def test_tokens():
    """Get test tokens from environment (comma-separated)"""
    tokens = os.getenv('TEST_FCM_TOKENS', '').split(',')
    tokens = [t.strip() for t in tokens if t.strip()]
    if not tokens:
        pytest.skip("TEST_FCM_TOKENS environment variable not set")
    return tokens


class TestBasicNotifications:
    """Test basic notification functionality"""

    def test_send_basic_notification(self, test_user_id):
        """Test sending a basic notification"""
        print(f"\n📱 Sending notification to user: {test_user_id}")

        send_notification(
            user_id=test_user_id,
            title="Integration Test",
            body="This is a test notification from integration tests",
            data={"test": "true", "timestamp": str(datetime.now())},
        )

        print("✅ Notification sent successfully")

    def test_send_notification_no_data(self, test_user_id):
        """Test sending notification without data payload"""
        send_notification(user_id=test_user_id, title="Simple Test", body="Notification without data")

        print("✅ Simple notification sent")

    def test_send_notification_with_emoji(self, test_user_id):
        """Test notification with emoji"""
        send_notification(user_id=test_user_id, title="Emoji Test 🎉", body="Testing emojis: ✅ 🚀 💡")

        print("✅ Emoji notification sent")


class TestBulkNotifications:
    """Test bulk notification sending"""

    @pytest.mark.asyncio
    async def test_bulk_send_small(self, test_tokens):
        """Test bulk send to a few tokens"""
        print(f"\n📢 Sending bulk notification to {len(test_tokens)} tokens")

        await send_bulk_notification(
            user_tokens=test_tokens, title="Bulk Test", body="This is a bulk notification test"
        )

        print("✅ Bulk notifications sent")

    @pytest.mark.asyncio
    async def test_bulk_send_large(self, test_tokens):
        """Test bulk send with many tokens (simulated)"""
        # Duplicate tokens to test batching (500+ tokens)
        large_token_list = test_tokens * 200  # Creates 200x the test tokens

        print(f"\n📢 Sending bulk notification to {len(large_token_list)} tokens")

        await send_bulk_notification(
            user_tokens=large_token_list, title="Large Bulk Test", body="Testing batch processing"
        )

        print("✅ Large bulk notifications sent")


class TestActionItemNotifications:
    """Test action item notifications"""

    def test_action_created(self, test_user_id):
        """Test action item created notification"""
        send_action_item_created_notification(user_id=test_user_id, action_item_description="Buy groceries for dinner")

        print("✅ Action created notification sent")

    def test_action_completed(self, test_user_id):
        """Test action item completed notification"""
        send_action_item_completed_notification(user_id=test_user_id, action_item_description="Finish quarterly report")

        print("✅ Action completed notification sent")

    def test_action_long_description(self, test_user_id):
        """Test action with very long description (should truncate)"""
        long_desc = "A" * 100  # 100 characters

        send_action_item_created_notification(user_id=test_user_id, action_item_description=long_desc)

        print("✅ Long description notification sent (truncated)")


class TestOtherNotifications:
    """Test other notification types"""

    def test_training_data_notification(self, test_user_id):
        """Test training data submitted notification"""
        send_training_data_submitted_notification(user_id=test_user_id)

        print("✅ Training data notification sent")


class TestErrorHandling:
    """Test error handling"""

    def test_nonexistent_user(self):
        """Test sending to non-existent user (should handle gracefully)"""
        send_notification(user_id="nonexistent-user-12345", title="Test", body="Should not crash")

        print("✅ Handled non-existent user gracefully")

    @pytest.mark.asyncio
    async def test_empty_token_list(self):
        """Test bulk send with empty list (should handle gracefully)"""
        await send_bulk_notification(user_tokens=[], title="Empty Test", body="Testing empty list")

        print("✅ Handled empty token list gracefully")


class TestTokenManagement:
    """Test token management functionality"""

    def test_remove_bulk_tokens(self, test_user_id):
        """Test bulk token removal"""
        print(f"\n🗑️ Testing bulk token removal")

        # Create test tokens
        test_tokens = [
            f"test-token-bulk-1-{datetime.now().timestamp()}",
            f"test-token-bulk-2-{datetime.now().timestamp()}",
            f"test-token-bulk-3-{datetime.now().timestamp()}",
        ]

        # Save test tokens
        for i, token in enumerate(test_tokens):
            notification_db.save_token(
                test_user_id, {'fcm_token': token, 'device_key': f'test-device-{i}', 'time_zone': 'America/New_York'}
            )

        print(f"Created {len(test_tokens)} test tokens")

        # Verify tokens were saved
        saved_tokens = notification_db.get_all_tokens(test_user_id)
        for token in test_tokens:
            assert token in saved_tokens, f"Token {token} not saved"

        print("✅ Tokens saved successfully")

        # Remove tokens in bulk
        notification_db.remove_bulk_tokens(test_tokens)
        print("Removed tokens in bulk")

        # Verify tokens were removed
        remaining_tokens = notification_db.get_all_tokens(test_user_id)
        for token in test_tokens:
            assert token not in remaining_tokens, f"Token {token} not removed"

        print("✅ All test tokens removed successfully")

    def test_remove_bulk_tokens_large_batch(self, test_user_id):
        """Test bulk removal with more than 30 tokens (tests chunking)"""
        print(f"\n🗑️ Testing bulk token removal with large batch (40 tokens)")

        # Create 40 test tokens (more than the 30 item IN query limit)
        test_tokens = [f"test-token-large-{i}-{datetime.now().timestamp()}" for i in range(40)]

        # Save test tokens
        for i, token in enumerate(test_tokens):
            notification_db.save_token(
                test_user_id,
                {'fcm_token': token, 'device_key': f'test-device-large-{i}', 'time_zone': 'America/New_York'},
            )

        print(f"Created {len(test_tokens)} test tokens")

        # Remove tokens in bulk (tests chunking logic)
        notification_db.remove_bulk_tokens(test_tokens)
        print("Removed tokens in bulk with chunking")

        # Verify all tokens were removed
        remaining_tokens = notification_db.get_all_tokens(test_user_id)
        removed_count = sum(1 for token in test_tokens if token not in remaining_tokens)

        print(f"✅ Removed {removed_count}/{len(test_tokens)} tokens")
        assert removed_count == len(test_tokens), "Not all tokens were removed"

    def test_remove_bulk_tokens_empty_list(self):
        """Test bulk removal with empty list (should handle gracefully)"""
        print(f"\n🗑️ Testing bulk token removal with empty list")

        # Should not crash
        notification_db.remove_bulk_tokens([])

        print("✅ Handled empty list gracefully")


# For manual testing
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("NOTIFICATION INTEGRATION TESTS")
    print("=" * 60)
    print("\nSet these environment variables:")
    print("  export TEST_USER_ID='your-firebase-user-id'")
    print("  export TEST_FCM_TOKENS='token1,token2,token3'\n")
    print("Then run: pytest backend/tests/integration/test_notifications_integration.py -v -s")
    print("=" * 60 + "\n")
