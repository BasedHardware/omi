"""Focused tests for metadata-only screen evidence emitted by semantic search."""

import json
import os
import contextvars
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def sa():
    def _pkg(name):
        mod = ModuleType(name)
        mod.__path__ = []  # type: ignore[attr-defined]
        return mod

    def _leaf(name, attrs):
        mod = ModuleType(name)
        for attr in attrs:
            setattr(mod, attr, MagicMock())
        return mod

    fakes = {
        "database": _pkg("database"),
        "utils": _pkg("utils"),
        "utils.llm": _pkg("utils.llm"),
        "utils.retrieval": _pkg("utils.retrieval"),
        "utils.retrieval.tools": _pkg("utils.retrieval.tools"),
        "database.screen_activity": _leaf("database.screen_activity", []),
        "database.vector_db": _leaf("database.vector_db", []),
        "database.notifications": _leaf("database.notifications", ["get_user_time_zone"]),
        "database._client": _leaf("database._client", ["db"]),
        "utils.llm.clients": _leaf("utils.llm.clients", ["gemini_embed_query"]),
        "utils.retrieval.agentic": _leaf("utils.retrieval.agentic", ["agent_config_context"]),
    }
    with stub_modules(fakes):
        module = load_module_fresh(
            "utils.retrieval.tools.screen_activity_tools",
            os.path.join(str(_BACKEND), "utils", "retrieval", "tools", "screen_activity_tools.py"),
        )
        yield module


class _Doc:
    def __init__(self, data):
        self.exists = data is not None
        self._data = data

    def to_dict(self):
        return self._data

    def get(self):
        return self


class _Collection:
    def __init__(self, rows):
        self._rows = rows

    def document(self, key):
        return _Doc(self._rows.get(key))


class _Firestore:
    def __init__(self, rows):
        self._rows = rows

    def collection(self, name):
        return _Collection(self._rows) if name == 'screen_activity' else self

    def document(self, name):
        return self

    def get(self):
        return _Doc(None)


def _search(sa):
    return getattr(sa.search_screen_activity_tool, 'func', sa.search_screen_activity_tool)


def _setup(monkeypatch, sa, rows, matches):
    monkeypatch.setattr(sa, 'gemini_embed_query', lambda query: [0.1])
    monkeypatch.setattr(sa.vector_db, 'search_screen_activity_vectors', lambda **kwargs: matches, raising=False)
    monkeypatch.setattr(sa.notification_db, 'get_user_time_zone', lambda uid: 'UTC')
    monkeypatch.setattr(sa, 'firestore_db', _Firestore(rows))


def test_direct_config_emits_bounded_metadata_only_reference(monkeypatch, sa):
    _setup(
        monkeypatch,
        sa,
        {'s1': {'ocrText': 'Budget   review\n' * 200, 'windowTitle': 'Editor'}},
        [{'screenshot_id': 's1', 'timestamp': 1_700_000_000, 'appName': 'Cursor', 'score': 0.91}],
    )
    references = []
    result = _search(sa)('budget', config={'configurable': {'user_id': 'u1', 'evidence_references': references}})

    assert 'Found 1 screen activity matches' in result
    assert len(references) == 1
    reference = references[0]
    assert reference['id'] == 'screen:s1'
    assert reference['kind'] == 'screen'
    assert reference['state'] == 'available'
    assert reference['frame_id'] == 's1'
    assert reference['captured_at_ms'] == 1_700_000_000_000
    assert len(reference['summary']) <= sa.MAX_SCREEN_EVIDENCE_SUMMARY_CHARS
    assert len(reference['metadata']['window_title']) <= sa.MAX_SCREEN_EVIDENCE_TITLE_CHARS
    assert len(reference['metadata']['ocr_preview']) <= sa.MAX_SCREEN_EVIDENCE_SUMMARY_CHARS
    assert len(json.dumps(reference['metadata'], sort_keys=True, separators=(',', ':'))) <= 2_000
    assert not any(key in reference for key in ('image', 'image_url', 'pixels', 'bytes'))


def test_context_var_sink_deduplicates_and_falls_back_when_config_has_no_sink(monkeypatch, sa):
    _setup(
        monkeypatch,
        sa,
        {'s2': {'ocrText': 'one'}},
        [
            {'screenshot_id': 's2', 'timestamp': '2026-08-23T12:00:00Z', 'appName': 'Safari', 'score': 0.8},
            {'screenshot_id': 's2', 'timestamp': '2026-08-23T12:00:00Z', 'appName': 'Safari', 'score': 0.7},
        ],
    )
    references = []
    context = contextvars.ContextVar('screen_test_agent_config', default=None)
    monkeypatch.setattr(sa, 'agent_config_context', context)
    token = context.set({'configurable': {'user_id': 'u1', 'evidence_references': references}})
    try:
        assert sa._evidence_references({'configurable': {'user_id': 'u1'}}) is references
        _search(sa)('one', config={'configurable': {'user_id': 'u1'}})
    finally:
        context.reset(token)
    assert [reference['id'] for reference in references] == ['screen:s2']
    assert references[0]['captured_at_ms'] is not None


def test_malformed_ids_are_skipped_and_reference_cap_is_24(monkeypatch, sa):
    _setup(
        monkeypatch,
        sa,
        {'good': None},
        [
            {'screenshot_id': '../escape', 'timestamp': 1_700_000_000, 'appName': 'Bad', 'score': 0.9},
            {'screenshot_id': 'bad\x00id', 'timestamp': 1_700_000_000, 'appName': 'Bad', 'score': 0.8},
            {'screenshot_id': 'good', 'timestamp': 1_700_000_000, 'appName': 'Good', 'score': 0.7},
        ],
    )
    references = [{'id': f'screen:existing-{index}'} for index in range(23)]
    result = _search(sa)('query', config={'configurable': {'user_id': 'u1', 'evidence_references': references}})
    assert 'Found 1 screen activity matches' in result
    assert len(references) == 24
    assert references[-1]['id'] == 'screen:good'

    admitted = []
    assert sa._append_screen_evidence_reference(
        admitted,
        screenshot_id='good',
        captured_at_ms=1_700_000_000_000,
        app_name='Good',
        window_title='',
        ocr_preview='',
    )
    for invalid in ('', ' ', '/', 'a/b', 'a\\b', 'a:b', 'a\x00b', '../x', 'x' * 97):
        assert not sa._append_screen_evidence_reference(
            admitted,
            screenshot_id=invalid,
            captured_at_ms=1_700_000_000_000,
            app_name='',
            window_title='',
            ocr_preview='',
        )
    assert len(admitted) == 1


def test_timestamp_and_score_normalization_are_fail_soft(sa):
    assert sa._normalized_captured_at_ms(1_700_000_000) == 1_700_000_000_000
    assert sa._normalized_captured_at_ms(1_700_000_000_123) == 1_700_000_000_123
    assert sa._normalized_captured_at_ms('2026-08-23T12:00:00Z') is not None
    assert sa._normalized_captured_at_ms(float('inf')) is None
    assert sa._normalized_captured_at_ms(10**30) is None
    assert sa._bounded_relevance(float('nan')) == 'unknown'
    assert sa._bounded_relevance(float('inf')) == 'unknown'
    assert sa._bounded_relevance('not-a-number') == 'unknown'


def test_search_malformed_timestamp_and_score_do_not_crash(monkeypatch, sa):
    _setup(
        monkeypatch,
        sa,
        {'s3': {'ocrText': 'safe'}},
        [{'screenshot_id': 's3', 'timestamp': 10**30, 'appName': 'App', 'score': float('nan')}],
    )
    references = []
    result = _search(sa)('safe', config={'configurable': {'user_id': 'u1', 'evidence_references': references}})
    assert 'Unknown' in result
    assert 'relevance: unknown' in result
    assert 'nan' not in result.lower()
    assert references == []
