"""
Integration test for issue #4494: KeyError: 'id' in get_closest_conversation_to_timestamps
https://github.com/BasedHardware/omi/issues/4494

This test reproduces the bug using real Firestore operations.

Setup:
1. Set GOOGLE_APPLICATION_CREDENTIALS or have Firebase credentials configured
2. Set TEST_USER_ID environment variable (a real or test Firebase user)
3. Run: pytest backend/tests/integration/test_issue_4494_conversations.py -v -s

The test:
1. Creates a real conversation document in Firestore
2. Calls get_closest_conversation_to_timestamps
3. Expects KeyError: 'id' (the bug)
4. Cleans up the test document
"""

import os
import uuid
import pytest
from datetime import datetime, timezone, timedelta

from database._client import db
from database.conversations import (
    get_closest_conversation_to_timestamps,
    conversations_collection,
)


@pytest.fixture
def test_user_id():
    """Get test user ID from environment"""
    user_id = os.getenv('TEST_USER_ID')
    if not user_id:
        pytest.skip("TEST_USER_ID environment variable not set")
    return user_id


@pytest.fixture
def test_conversation(test_user_id):
    """
    Create a real conversation document in Firestore.

    This mimics how a conversation would exist in production:
    - Document ID is separate from document data
    - Document data contains started_at, finished_at, etc.
    - Document data does NOT contain 'id' field (Firestore design)
    """
    conversation_id = f"test-issue-4494-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)

    # conversation data - note: no 'id' field in the data
    # this is how Firestore stores documents: ID is in the path, not in data
    conversation_data = {
        "created_at": now,
        "started_at": now - timedelta(minutes=10),
        "finished_at": now - timedelta(minutes=5),
        "status": "completed",
        "discarded": False,
        "source": "omi",
        "structured": {
            "title": "Test conversation for issue 4494",
            "overview": "Integration test",
            "emoji": "🧪",
            "category": "other",
            "action_items": [],
            "events": [],
        },
        "transcript_segments": [],
        "apps_results": [],
        "plugins_results": [],
        "photos": [],
    }

    # create document in Firestore
    # the document ID (conversation_id) is NOT stored in the document data
    # this is normal Firestore behavior
    user_ref = db.collection('users').document(test_user_id)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_ref.set(conversation_data)

    print(f"\n📝 Created test conversation: {conversation_id}")
    print(f"   User: {test_user_id}")
    print(f"   started_at: {conversation_data['started_at']}")
    print(f"   finished_at: {conversation_data['finished_at']}")

    yield {
        "id": conversation_id,
        "data": conversation_data,
        "ref": conversation_ref,
    }

    # cleanup
    print(f"\n🗑️ Cleaning up test conversation: {conversation_id}")
    conversation_ref.delete()


class TestIssue4494:
    """
    Test case for issue #4494: KeyError: 'id' in get_closest_conversation_to_timestamps

    Root cause: Firestore's doc.to_dict() does not include document ID.
    The function at conversations.py:1014 uses:
        conversations = [doc.to_dict() for doc in query.stream()]

    Then at line 1021 it tries:
        print('-', conversation['id'], ...)

    This fails because 'id' is not in the dict.
    """

    def test_keyerror_id_reproduced(self, test_user_id, test_conversation):
        """
        Reproduce the KeyError: 'id' bug.

        This test PASSES if the bug exists (KeyError is raised).
        This test FAILS if the bug is fixed (no KeyError).
        """
        print("\n" + "=" * 60)
        print("REPRODUCING ISSUE #4494")
        print("=" * 60)

        # calculate timestamps that will match our test conversation
        started_at = test_conversation["data"]["started_at"]
        finished_at = test_conversation["data"]["finished_at"]

        start_timestamp = int(started_at.timestamp())
        end_timestamp = int(finished_at.timestamp())

        print(f"\nCalling get_closest_conversation_to_timestamps()")
        print(f"  uid: {test_user_id}")
        print(f"  start_timestamp: {start_timestamp}")
        print(f"  end_timestamp: {end_timestamp}")

        # this should raise KeyError: 'id' due to the bug
        try:
            result = get_closest_conversation_to_timestamps(
                uid=test_user_id,
                start_timestamp=start_timestamp,
                end_timestamp=end_timestamp,
            )

            # if we get here, the bug is fixed
            print(f"\n✅ No KeyError - bug is FIXED")
            print(f"   Returned conversation ID: {result.get('id', 'MISSING')}")

            # verify the fix works correctly
            assert result is not None, "Expected a conversation to be returned"
            assert 'id' in result, "Expected 'id' field in result"
            assert (
                result['id'] == test_conversation["id"]
            ), f"Expected id={test_conversation['id']}, got {result.get('id')}"

        except KeyError as e:
            # bug reproduced
            print(f"\n❌ KeyError raised: {e}")
            print("   Bug #4494 reproduced!")
            print("\n   Location: backend/database/conversations.py")
            print("   Line 1014: conversations = [doc.to_dict() for doc in query.stream()]")
            print("   Line 1021: print('-', conversation['id'], ...)")
            print("\n   doc.to_dict() does not include document ID.")
            print("   ID is metadata on doc.id, not in the document data.")

            pytest.fail(
                f"Bug #4494 reproduced: KeyError: {e}\n"
                "Fix: conversations = [{{'id': doc.id, **doc.to_dict()}} for doc in query.stream()]"
            )

    def test_verify_firestore_behavior(self, test_user_id, test_conversation):
        """
        Verify that Firestore's to_dict() does not include document ID.
        This documents the expected Firestore behavior.
        """
        print("\n" + "=" * 60)
        print("VERIFYING FIRESTORE BEHAVIOR")
        print("=" * 60)

        # read the document back
        doc = test_conversation["ref"].get()

        print(f"\nDocument ID (doc.id): {doc.id}")
        print(f"Document ID type: {type(doc.id)}")
        print(f"Document exists: {doc.exists}")

        data = doc.to_dict()
        print(f"\nKeys in doc.to_dict(): {list(data.keys())}")
        print(f"'id' in doc.to_dict(): {'id' in data}")

        print(f"\n--- COMPARISON ---")
        print(f"doc.id = {repr(doc.id)}")
        print(f"data.get('id') = {repr(data.get('id'))}")
        print(f"doc.id exists: {bool(doc.id)}")
        print(f"data has 'id': {'id' in data}")

        # verify Firestore behavior
        assert doc.id == test_conversation["id"], "doc.id should match"
        assert 'id' not in data, "doc.to_dict() should NOT contain 'id'"

        print("\n✅ Confirmed: Firestore doc.to_dict() does not include document ID")
        print("   This is by design - ID is metadata, not a document field.")


# run directly
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("ISSUE #4494 INTEGRATION TEST")
    print("https://github.com/BasedHardware/omi/issues/4494")
    print("=" * 60)
    print("\nSet these environment variables:")
    print("  export TEST_USER_ID='your-firebase-user-id'")
    print("\nThen run:")
    print("  pytest backend/tests/integration/test_issue_4494_conversations.py -v -s")
    print("=" * 60 + "\n")
