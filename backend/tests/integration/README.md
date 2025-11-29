# Notification Integration Tests

Simple integration tests for the notification system that send real Firebase notifications.

## Quick Setup

1. **Install dependencies:**
```bash
pip install pytest pytest-asyncio firebase-admin
```

2. **Set up Firebase credentials:**
```bash
# Download service account key from Firebase Console
# Settings > Service accounts > Generate new private key

# Set the environment variable
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/serviceAccountKey.json"
```

3. **Set test environment variables:**
```bash
# Required: Your Firebase user ID
export TEST_USER_ID="your-firebase-user-id-here"

# Optional: Comma-separated FCM tokens for bulk testing
export TEST_FCM_TOKENS="token1,token2,token3"
```

4. **Get your test user ID:**
   - Go to Firebase Console → Authentication
   - Find your test user
   - Copy the UID

5. **Get FCM tokens (optional, for bulk tests):**
   - Use the app to register devices
   - Get tokens from the database or device

## Running Tests

**Important: Run from the project root directory!**

```bash
# Make sure you're in the project root
cd /path/to/your/project

# Set environment variables
export TEST_USER_ID="your-firebase-user-id-here"
export TEST_FCM_TOKENS="token1,token2,token3"  # optional

# Run all integration tests
pytest backend/tests/integration/test_notifications_integration.py -v

# Run with output (see print statements)
pytest backend/tests/integration/test_notifications_integration.py -v -s

# Run specific test
pytest backend/tests/integration/test_notifications_integration.py::TestBasicNotifications::test_send_basic_notification -v -s

# Run only basic tests
pytest backend/tests/integration/test_notifications_integration.py::TestBasicNotifications -v -s
```

## What Gets Tested

- ✅ Basic notifications (with/without data, with emoji)
- ✅ Bulk notifications (small and large batches)
- ✅ Action item notifications
- ✅ Training data notifications
- ✅ Error handling (non-existent users, empty lists)

## Important Notes

⚠️ **These tests send REAL notifications!**
- Use a test Firebase project
- Use your own test user
- Notifications will appear on your device
- Don't run in production environment

## Example Output

```
test_send_basic_notification 
📱 Sending notification to user: abc123xyz
✅ Notification sent successfully
PASSED

test_bulk_send_small 
📢 Sending bulk notification to 3 tokens
✅ Bulk notifications sent
PASSED
```

## Troubleshooting

**Tests are skipped:**
- Make sure `TEST_USER_ID` is set
- For bulk tests, set `TEST_FCM_TOKENS`

**Import errors:**
- Run from project root directory
- Ensure backend is in Python path

**Firebase errors:**
- Check Firebase credentials are set
- Verify user exists in Firebase Auth
- Ensure tokens are valid
