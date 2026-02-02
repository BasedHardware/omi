#!/usr/bin/env python3
"""
Reproduce issue #4494: KeyError: 'id' in get_closest_conversation_to_timestamps
https://github.com/BasedHardware/omi/issues/4494

Run: python scripts/reproduce_issue_4494.py
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock


def mock_firestore_document(doc_id: str, data: dict):
    """Simulate Firestore DocumentSnapshot behavior"""
    doc = MagicMock()
    doc.id = doc_id  # ID is on the doc object, not in to_dict()
    doc.to_dict = lambda: data  # to_dict() returns only fields
    return doc


def simulate_current_code():
    """Current code at conversations.py:1014-1021"""
    print("=" * 60)
    print("CURRENT CODE (conversations.py:1014-1021)")
    print("=" * 60)

    # Simulate Firestore query results
    mock_docs = [
        mock_firestore_document(
            doc_id="conv_abc123",
            data={
                "started_at": datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
                "finished_at": datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
                "status": "completed",
            }
        ),
        mock_firestore_document(
            doc_id="conv_def456",
            data={
                "started_at": datetime(2024, 1, 15, 11, 0, tzinfo=timezone.utc),
                "finished_at": datetime(2024, 1, 15, 11, 45, tzinfo=timezone.utc),
                "status": "completed",
            }
        ),
    ]

    # Line 1014: current code
    conversations = [doc.to_dict() for doc in mock_docs]

    print("\nLine 1014: conversations = [doc.to_dict() for doc in query.stream()]")
    print(f"\nResult: {conversations}")
    print(f"\nKeys in first conversation: {list(conversations[0].keys())}")
    print("Note: 'id' is NOT in the keys")

    # Line 1021: this fails
    print("\nLine 1021: print('-', conversation['id'], ...)")
    print("\nAttempting to access conversation['id']...")

    try:
        for conversation in conversations:
            print('-', conversation['id'], conversation['started_at'], conversation['finished_at'])
    except KeyError as e:
        print(f"\n>>> KeyError: {e}")
        print(">>> This is the bug!")
        return False

    return True


def simulate_fixed_code():
    """Fixed code that includes doc.id"""
    print("\n" + "=" * 60)
    print("FIXED CODE")
    print("=" * 60)

    mock_docs = [
        mock_firestore_document(
            doc_id="conv_abc123",
            data={
                "started_at": datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
                "finished_at": datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
                "status": "completed",
            }
        ),
        mock_firestore_document(
            doc_id="conv_def456",
            data={
                "started_at": datetime(2024, 1, 15, 11, 0, tzinfo=timezone.utc),
                "finished_at": datetime(2024, 1, 15, 11, 45, tzinfo=timezone.utc),
                "status": "completed",
            }
        ),
    ]

    # Fixed: include doc.id in the dict
    conversations = [{'id': doc.id, **doc.to_dict()} for doc in mock_docs]

    print("\nFixed line: conversations = [{'id': doc.id, **doc.to_dict()} for doc in query.stream()]")
    print(f"\nResult: {conversations}")
    print(f"\nKeys in first conversation: {list(conversations[0].keys())}")
    print("Note: 'id' IS now in the keys")

    print("\nAccessing conversation['id']...")

    try:
        for conversation in conversations:
            print('-', conversation['id'], conversation['started_at'], conversation['finished_at'])
        print("\n>>> Success!")
        return True
    except KeyError as e:
        print(f"\n>>> KeyError: {e}")
        return False


def show_firestore_behavior():
    """Explain Firestore DocumentSnapshot behavior"""
    print("\n" + "=" * 60)
    print("FIRESTORE BEHAVIOR EXPLANATION")
    print("=" * 60)

    doc = mock_firestore_document(
        doc_id="example_id",
        data={"field1": "value1", "field2": "value2"}
    )

    print(f"\ndoc.id         = {doc.id!r}")
    print(f"doc.to_dict()  = {doc.to_dict()}")
    print("\nFirestore stores document ID in the path (collection/docId),")
    print("not as a field in the document data.")
    print("to_dict() returns only user-defined fields.")


if __name__ == "__main__":
    print("Issue #4494 Reproduction Script")
    print("https://github.com/BasedHardware/omi/issues/4494\n")

    show_firestore_behavior()

    bug_reproduced = not simulate_current_code()

    if bug_reproduced:
        print("\n" + "-" * 60)
        print("BUG REPRODUCED SUCCESSFULLY")
        print("-" * 60)

    simulate_fixed_code()

    print("\n" + "=" * 60)
    print("AFFECTED LOCATIONS IN conversations.py")
    print("=" * 60)
    print("""
Line 255:  get_conversations_without_photos()
Line 516:  get_conversations_by_id()
Line 673:  get_processing_conversations()
Line 1014: get_closest_conversation_to_timestamps()

All use: [doc.to_dict() for doc in query.stream()]
Should be: [{'id': doc.id, **doc.to_dict()} for doc in query.stream()]
""")
