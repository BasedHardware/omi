"""Regression: vector_db functions must fail open when no Pinecone index is configured.

database.vector_db.index is None on deploys without Pinecone (self-hosted, offline, local dev).
20+ functions guard `if index is None`, but query_vectors_by_metadata, upsert_vector2, and
update_vector_metadata dereferenced index directly, raising AttributeError instead of the intended
empty/skip. That either silently dropped the proactive-notification memory lookup or died as an
unlogged AttributeError on the structured-vector save. The guards restore the fail-open contract.
"""

import database.vector_db as vector_db


def test_query_vectors_by_metadata_returns_empty_without_index(monkeypatch):
    monkeypatch.setattr(vector_db, 'index', None)
    result = vector_db.query_vectors_by_metadata('uid1', [0.1, 0.2], [], [], [], [], [], limit=5)
    assert result == []


def test_upsert_vector2_is_a_noop_without_index(monkeypatch):
    monkeypatch.setattr(vector_db, 'index', None)
    # Must not raise (previously AttributeError on index.upsert).
    assert vector_db.upsert_vector2('uid1', 'conv1', [0.1, 0.2], {'k': 'v'}) is False


def test_update_vector_metadata_returns_empty_without_index(monkeypatch):
    monkeypatch.setattr(vector_db, 'index', None)
    result = vector_db.update_vector_metadata('uid1', 'conv1', {'k': 'v'})
    assert result == {}


def test_summary_upsert_error_count_preserves_exception(monkeypatch):
    from contextlib import nullcontext
    from unittest.mock import MagicMock
    import pytest
    from utils.metrics import OMI_CONVERSATION_SUMMARY_VECTOR_UPSERTS_TOTAL as metric

    index = MagicMock()
    index.upsert.side_effect = RuntimeError('provider offline')
    monkeypatch.setattr(vector_db, 'index', index)
    monkeypatch.setattr(vector_db, 'external_write_fence', lambda *args, **kwargs: nullcontext())
    before = metric.labels(outcome='error')._value.get()
    with pytest.raises(RuntimeError, match='provider offline'):
        vector_db.upsert_vector2('uid', 'conv', [0.1], {})
    assert metric.labels(outcome='error')._value.get() == before + 1


def test_summary_upsert_reports_actual_provider_write(monkeypatch):
    from contextlib import nullcontext
    from unittest.mock import MagicMock

    index = MagicMock()
    monkeypatch.setattr(vector_db, 'index', index)
    monkeypatch.setattr(vector_db, 'external_write_fence', lambda *args, **kwargs: nullcontext())
    assert vector_db.upsert_vector2('uid', 'conv', [0.1], {}) is True
    assert index.upsert.call_args.kwargs['namespace'] == 'ns1'
    assert index.upsert.call_args.kwargs['vectors'][0]['id'] == 'uid-conv'
