"""A failed audio-chunk copy during merge must abort, not silently drop a source's audio.

perform_merge_async copies every source conversation's audio chunks to the merged conversation
(_copy_audio_chunks_for_merge), then in step 9 unconditionally deletes every source's original
chunks. The copy helper used to wrap each conversation's copy in a try/except that only logged the
error. Because `has_chunks` could already be True from an earlier source that copied fine, a later
source whose copy threw (a transient GCS error, no adversarial input) left the helper returning a
normal non-empty result. The merge then completed and deleted that source's original audio, which
was never copied anywhere: the user's raw recording is destroyed with a merge-completed
notification and only a log line as the record.

The fix lets the failure propagate so perform_merge_async aborts into _handle_merge_failure before
any source is deleted. These tests assert the propagation happens even after an earlier source
copied successfully, which is the case the swallowing except masked.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

from unittest.mock import MagicMock

import pytest

import utils.conversations.merge_conversations as merge


class _FakeBucket:
    """copy_blob raises when the source path belongs to a conversation in fail_for."""

    def __init__(self, fail_for=()):
        self._fail_for = set(fail_for)

    def blob(self, path):
        b = MagicMock()
        b.path = path
        return b

    def copy_blob(self, source_blob, _bucket, _new_path):
        for conv_id in self._fail_for:
            if f'/{conv_id}/' in getattr(source_blob, 'path', ''):
                raise Exception(f"simulated transient GCS copy error for {conv_id}")


def _install(monkeypatch, *, chunks_by_conv, bucket, list_raises_for=()):
    storage_client = MagicMock()
    storage_client.bucket.return_value = bucket
    monkeypatch.setattr(merge, "_get_storage_client", lambda: storage_client)

    def _list_audio_chunks(uid, conv_id):
        if conv_id in list_raises_for:
            raise Exception(f"simulated transient GCS listing error for {conv_id}")
        return chunks_by_conv.get(conv_id, [])

    monkeypatch.setattr(merge, "list_audio_chunks", _list_audio_chunks)
    monkeypatch.setattr(
        merge.conversations_db,
        "create_audio_files_from_chunks",
        lambda uid, new_id: ["audio-file-record"],
    )


_CONVS = [{'id': 'conv_a'}, {'id': 'conv_b'}]
_CHUNKS = {
    'conv_a': [{'path': 'chunks/u1/conv_a/100.bin'}],
    'conv_b': [{'path': 'chunks/u1/conv_b/200.bin'}],
}


def test_later_conversation_list_failure_propagates(monkeypatch):
    # conv_a lists+copies fine (has_chunks becomes True), conv_b's listing throws.
    _install(monkeypatch, chunks_by_conv=_CHUNKS, bucket=_FakeBucket(), list_raises_for={'conv_b'})

    with pytest.raises(Exception):
        merge._copy_audio_chunks_for_merge('u1', _CONVS, 'merged_1')


def test_later_conversation_copy_failure_propagates(monkeypatch):
    # conv_a copies fine, conv_b's copy_blob throws.
    _install(monkeypatch, chunks_by_conv=_CHUNKS, bucket=_FakeBucket(fail_for={'conv_b'}))

    with pytest.raises(Exception):
        merge._copy_audio_chunks_for_merge('u1', _CONVS, 'merged_1')


def test_all_conversations_copy_successfully_returns_audio_files(monkeypatch):
    # No failure anywhere: the helper still returns the created audio-file records unchanged.
    _install(monkeypatch, chunks_by_conv=_CHUNKS, bucket=_FakeBucket())

    result = merge._copy_audio_chunks_for_merge('u1', _CONVS, 'merged_1')

    assert result == ["audio-file-record"]


def test_no_chunks_anywhere_returns_empty(monkeypatch):
    # A source with genuinely no chunks is not a failure and must not abort the merge.
    _install(monkeypatch, chunks_by_conv={}, bucket=_FakeBucket())

    assert merge._copy_audio_chunks_for_merge('u1', _CONVS, 'merged_1') == []
