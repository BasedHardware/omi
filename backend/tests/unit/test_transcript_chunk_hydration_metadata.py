"""hydrate_chunk_texts must attach parent-conversation metadata for typed sources.

The /v1/tools/conversations/search-chunks endpoint builds ToolSource entries
(kind 'conversation', source_id = parent conversation id) from hydrated rows, so
hydration has to carry the conversation title and start time alongside the text
without a second Firestore read.
"""

from datetime import datetime, timezone

import pytest

import utils.conversations.transcript_chunks as transcript_chunks
from database import vector_db

STARTED_AT = datetime(2026, 8, 14, 21, 30, tzinfo=timezone.utc)


def _conversation(conv_id="conv-a", title="Release chat", segments=None):
    return {
        'id': conv_id,
        'structured': {'title': title},
        'started_at': STARTED_AT,
        'transcript_segments': segments if segments is not None else [{'text': 'the beta shipped', 'is_user': True}],
    }


@pytest.fixture
def conversations_by_id(monkeypatch):
    holder = {'conversations': []}
    monkeypatch.setattr(
        transcript_chunks.conversations_db,
        'get_conversations_by_id',
        lambda _uid, _ids, **_kwargs: holder['conversations'],
    )
    return holder


def test_hydrated_rows_carry_conversation_title_and_start_time(conversations_by_id):
    conversations_by_id['conversations'] = [_conversation()]
    rows = transcript_chunks.hydrate_chunk_texts(
        'uid-1', [{'conversation_id': 'conv-a', 'chunk_index': 0, 'created_at': 0, 'score': 0.9}]
    )
    assert len(rows) == 1
    assert 'the beta shipped' in rows[0]['text']
    assert rows[0]['conversation_title'] == 'Release chat'
    assert rows[0]['conversation_started_at'] == STARTED_AT


def test_non_dict_structured_yields_none_title_not_a_crash(conversations_by_id):
    conversation = _conversation()
    conversation['structured'] = None
    conversations_by_id['conversations'] = [conversation]
    rows = transcript_chunks.hydrate_chunk_texts(
        'uid-1', [{'conversation_id': 'conv-a', 'chunk_index': 0, 'created_at': 0, 'score': 0.9}]
    )
    assert rows[0]['conversation_title'] is None


def test_vanished_conversation_rows_still_drop(conversations_by_id):
    conversations_by_id['conversations'] = [_conversation()]
    rows = transcript_chunks.hydrate_chunk_texts(
        'uid-1',
        [
            {'conversation_id': 'conv-a', 'chunk_index': 0, 'created_at': 0, 'score': 0.9},
            {'conversation_id': 'conv-gone', 'chunk_index': 0, 'created_at': 0, 'score': 0.8},
        ],
    )
    assert [r['conversation_id'] for r in rows] == ['conv-a']


def test_build_transcript_chunks_handles_iso_string_and_numeric_timestamps():
    segs = [{'text': 'the beta shipped', 'is_user': True}]
    # ISO string with UTC 'Z'
    chunks_iso = transcript_chunks.build_transcript_chunks(segs, '2026-08-14T21:30:00Z')
    assert len(chunks_iso) == 1
    assert '[Conversation on 14 Aug 2026, 21:30]' in chunks_iso[0]['text']
    assert chunks_iso[0]['created_at'] == int(STARTED_AT.timestamp())

    # Numeric integer epoch timestamp
    chunks_int = transcript_chunks.build_transcript_chunks(segs, int(STARTED_AT.timestamp()))
    assert len(chunks_int) == 1
    assert '[Conversation on 14 Aug 2026, 21:30]' in chunks_int[0]['text']
    assert chunks_int[0]['created_at'] == int(STARTED_AT.timestamp())

    # Numeric float epoch timestamp
    chunks_float = transcript_chunks.build_transcript_chunks(segs, STARTED_AT.timestamp() + 0.75)
    assert len(chunks_float) == 1
    assert chunks_float[0]['created_at'] == int(STARTED_AT.timestamp())

    # Naive datetime is treated as UTC
    naive_dt = datetime(2026, 8, 14, 21, 30, 0)
    chunks_naive = transcript_chunks.build_transcript_chunks(segs, naive_dt)
    assert chunks_naive[0]['created_at'] == int(STARTED_AT.timestamp())

    # Fallbacks on None, boolean, or malformed string
    for invalid in [None, False, True, 'not-a-date']:
        chunks_invalid = transcript_chunks.build_transcript_chunks(segs, invalid)
        assert len(chunks_invalid) == 1
        assert chunks_invalid[0]['created_at'] == 0
        assert not chunks_invalid[0]['text'].startswith('[Conversation on')


def test_hydrate_chunk_texts_handles_iso_string_and_timestamp_in_conversation(conversations_by_id):
    conv_str = {
        'id': 'conv-str',
        'structured': {'title': 'ISO Chat'},
        'started_at': '2026-08-14T21:30:00Z',
        'transcript_segments': [{'text': 'shipped today', 'is_user': True}],
    }
    conv_int = {
        'id': 'conv-int',
        'structured': {'title': 'Timestamp Chat'},
        'created_at': int(STARTED_AT.timestamp()),
        'transcript_segments': [{'text': 'shipped yesterday', 'is_user': False}],
    }
    conversations_by_id['conversations'] = [conv_str, conv_int]

    rows = transcript_chunks.hydrate_chunk_texts(
        'uid-1',
        [
            {'conversation_id': 'conv-str', 'chunk_index': 0},
            {'conversation_id': 'conv-int', 'chunk_index': 0},
        ],
    )
    assert len(rows) == 2
    assert '[Conversation on 14 Aug 2026, 21:30]' in rows[0]['text']
    assert rows[0]['conversation_title'] == 'ISO Chat'
    assert '[Conversation on 14 Aug 2026, 21:30]' in rows[1]['text']
    assert rows[1]['conversation_title'] == 'Timestamp Chat'


@pytest.mark.parametrize("enabled", [True, False])
def test_edit_refresh_reads_committed_text_and_replaces_old_windows(monkeypatch, enabled):
    from contextlib import nullcontext
    from database import vector_db

    class Index:
        def __init__(self):
            self.rows = {"uid-1-conv-a-c0": {"text": "old text"}, "uid-1-conv-a-c1": {"text": "obsolete"}}

        def upsert(self, *, vectors, namespace):
            assert namespace == vector_db.TRANSCRIPT_CHUNKS_NAMESPACE
            for row in vectors:
                self.rows[row["id"]] = row

        def list(self, *, prefix, namespace):
            assert prefix == "uid-1-conv-a-c"
            assert namespace == vector_db.TRANSCRIPT_CHUNKS_NAMESPACE
            yield list(self.rows)

        def delete(self, *, ids, namespace):
            for vector_id in ids:
                del self.rows[vector_id]

    index = Index()
    embedded = []

    def embed(texts):
        embedded.extend(texts)
        return [[1.0] for _ in texts]

    monkeypatch.setattr(vector_db, "index", index)
    monkeypatch.setattr(vector_db, "external_write_fence", lambda *_args, **_kwargs: nullcontext())
    from types import SimpleNamespace

    monkeypatch.setattr(vector_db, "embeddings", SimpleNamespace(embed_documents=embed))
    monkeypatch.setenv("TRANSCRIPT_CHUNK_INDEXING_ENABLED", str(enabled).lower())
    monkeypatch.setattr(
        transcript_chunks.conversations_db,
        "get_conversation",
        lambda *_args: _conversation(segments=[{"text": "edited release date", "is_user": True}]),
    )
    transcript_chunks.refresh_transcript_chunks_after_edit("uid-1", "conv-a")
    assert set(index.rows) == ({"uid-1-conv-a-c0"} if enabled else set())
    assert bool(embedded) is enabled
    if enabled:
        assert "edited release date" in embedded[0]
        assert "old text" not in embedded[0]
        assert "text" not in index.rows["uid-1-conv-a-c0"]["metadata"]


def test_replacement_pruning_failure_preserves_saved_edit_and_records_degradation(monkeypatch):
    from contextlib import nullcontext
    from database import vector_db

    class Index:
        def list(self, **_kwargs):
            yield ["uid-1-conv-a-c0"]

        def delete(self, **_kwargs):
            raise RuntimeError("delete failed")

    monkeypatch.setattr(vector_db, "index", Index())
    monkeypatch.setattr(vector_db, "external_write_fence", lambda *_args, **_kwargs: nullcontext())
    monkeypatch.setenv("TRANSCRIPT_CHUNK_INDEXING_ENABLED", "false")
    monkeypatch.setattr(transcript_chunks.conversations_db, "get_conversation", lambda *_args: _conversation())
    fallbacks = []
    monkeypatch.setattr(transcript_chunks, "record_fallback", lambda **kwargs: fallbacks.append(kwargs))
    transcript_chunks.refresh_transcript_chunks_after_edit("uid-1", "conv-a")
    assert len(fallbacks) == 1
    assert fallbacks[0]["outcome"] == "degraded"
