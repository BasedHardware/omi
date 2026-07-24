"""A source soft-deleted after admission must not be merged by the background worker.

validate_merge_compatibility rejects a soft-deleted source at admission, but
perform_merge_async re-fetches the sources later in the background task. If a source
becomes a soft-deleted tombstone between admission and that fetch (the delete-vs-merge
race), the worker must abort — otherwise it resurrects the deleted source's
transcript/photos/audio into a new visible conversation and then re-deletes the sources.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

from unittest.mock import MagicMock

import pytest

import utils.conversations.merge_conversations as merge


@pytest.fixture(scope='module', autouse=True)
def _warm_merge_imports():
    """perform_merge_async does heavy local imports (process_conversation) at call
    time. Charge them to module setup so the fast-unit CPU-time guard measures only
    the call phase (mirrors test_modulate_stt.py's warm fixture)."""
    import utils.conversations.process_conversation  # noqa: F401
    import utils.notifications  # noqa: F401


def _install(monkeypatch, sources):
    monkeypatch.setattr(merge.conversations_db, "get_conversation", lambda uid, cid: sources.get(cid))
    fail = MagicMock()
    monkeypatch.setattr(merge, "_handle_merge_failure", fail)
    create = MagicMock()
    monkeypatch.setattr(merge.lifecycle_service, "create_processing_conversation", create)
    return fail, create


def test_merge_aborts_when_a_source_is_deleted_after_admission(monkeypatch):
    # c1 became a soft-deleted tombstone between admission and this background fetch.
    fail, create = _install(
        monkeypatch,
        {
            'c1': {'id': 'c1', 'status': 'completed', 'deleted': True},
            'c2': {'id': 'c2', 'status': 'completed'},
        },
    )

    merge.perform_merge_async('u1', ['c1', 'c2'])

    fail.assert_called_once()
    # The deleted source's content never reached a new visible conversation.
    create.assert_not_called()


def test_merge_does_not_abort_when_no_source_is_deleted(monkeypatch):
    # The guard must not reject a legitimate merge: two live sources reach the build step
    # (create_processing_conversation) rather than _handle_merge_failure. Downstream build
    # is stubbed to raise right there so the test stays on the guard boundary.
    fail, create = _install(
        monkeypatch,
        {
            'c1': {'id': 'c1', 'status': 'completed', 'started_at': None},
            'c2': {'id': 'c2', 'status': 'completed', 'started_at': None},
        },
    )
    monkeypatch.setattr(merge, "_normalize_conversation_timestamps", lambda convs: convs)
    monkeypatch.setattr(merge, "_merge_transcript_segments", lambda convs: [])
    monkeypatch.setattr(merge, "_collect_all_photos", lambda uid, convs: [])
    monkeypatch.setattr(merge, "_copy_audio_chunks_for_merge", lambda uid, convs, new_id: [])
    monkeypatch.setattr(merge, "Conversation", lambda **kw: MagicMock(**{'model_dump.return_value': {}}))
    create.side_effect = RuntimeError("stop at build; the guard already let us through")

    merge.perform_merge_async('u1', ['c1', 'c2'])

    create.assert_called_once()  # got past the deleted guard into the build step
