"""Focused tests for metadata-only screen evidence emitted by semantic search."""

import json
import os
import contextvars
from pathlib import Path
from types import ModuleType
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from database.screen_activity import normalize_screen_activity_timestamp

from testing.import_isolation import load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def sa():
    def _pkg(name):
        mod = ModuleType(name)
        mod.__path__ = [str(_BACKEND / name.replace(".", "/"))]  # type: ignore[attr-defined]
        return mod

    def _leaf(name, attrs):
        mod = ModuleType(name)
        for attr in attrs:
            setattr(mod, attr, MagicMock())
        return mod

    fakes = {
        "utils.observability": _pkg("utils.observability"),
        "utils.observability.fallback": _leaf("utils.observability.fallback", ["record_fallback"]),
        "database": _pkg("database"),
        "utils": _pkg("utils"),
        "utils.llm": _pkg("utils.llm"),
        "utils.retrieval": _pkg("utils.retrieval"),
        "utils.retrieval.tools": _pkg("utils.retrieval.tools"),
        "database.screen_activity": _leaf("database.screen_activity", ["normalize_screen_activity_timestamp"]),
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
        module.screen_activity_db.normalize_screen_activity_timestamp = normalize_screen_activity_timestamp
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


class _KeywordDoc(_Doc):
    def __init__(self, key, data):
        super().__init__(data)
        self.id = key


class _KeywordCollection(_Collection):
    def __init__(self, rows):
        super().__init__(rows)
        self.filters = []
        self.cap = None
        self.order = None

    def where(self, *, filter):
        self.filters.append(filter)
        return self

    def order_by(self, field, direction):
        self.order = (field, direction)
        return self

    def limit(self, cap):
        self.cap = cap
        return self

    def stream(self):
        assert self.order == ('timestamp', 'DESCENDING')
        assert self.cap == 500
        rows = list(self._rows.items())
        for condition in self.filters:
            rows = [
                (key, row)
                for key, row in rows
                if (
                    row['timestamp'] >= condition.value
                    if condition.op_string == '>='
                    else row['timestamp'] <= condition.value
                )
            ]
        rows.sort(key=lambda item: item[1]['timestamp'], reverse=True)
        return [_KeywordDoc(key, row) for key, row in rows[: self.cap]]


class _KeywordFirestore(_Firestore):
    def __init__(self, rows):
        super().__init__(rows)
        self.screens = _KeywordCollection(rows)

    def collection(self, name):
        assert name in ('users', 'screen_activity')
        return self.screens if name == 'screen_activity' else self

    def document(self, name):
        assert name == 'u1'
        return self


def _keyword_setup(monkeypatch, sa, mode='empty'):
    monkeypatch.setenv('SCREEN_ACTIVITY_KEYWORD_FALLBACK_ENABLED', 'true')
    monkeypatch.delenv('SCREEN_ACTIVITY_VECTORS_DISABLED_UIDS', raising=False)
    rows = {
        'both': {
            'timestamp': '2026-09-09 10:00:00.000',
            'ocrText': 'BUDGET budget',
            'windowTitle': 'Review',
            'appName': 'Editor',
        },
        'title': {
            'timestamp': '2026-09-09 11:00:00.000',
            'ocrText': '',
            'windowTitle': 'Budget review',
            'appName': 'Editor',
        },
        'partial': {'timestamp': '2026-09-09 12:00:00.000', 'ocrText': 'budget only'},
        'old': {'timestamp': '2026-08-01 10:00:00.000', 'ocrText': 'budget review'},
    }
    _setup(monkeypatch, sa, {}, [])
    client = _KeywordFirestore(rows)
    monkeypatch.setattr(sa, 'firestore_db', client)
    if mode == 'error':

        def fail(query):
            raise RuntimeError('sensitive provider text')

        monkeypatch.setattr(sa, 'gemini_embed_query', fail)
    return client


@pytest.mark.parametrize('mode', ['error', 'empty', 'malformed', 'disabled'])
def test_keyword_fallback_preserves_shape_evidence_ranking_and_window(monkeypatch, sa, mode, caplog):
    client = _keyword_setup(monkeypatch, sa, mode)
    if mode == 'malformed':
        monkeypatch.setattr(
            sa.vector_db, 'search_screen_activity_vectors', lambda **kwargs: [{'screenshot_id': '../bad'}]
        )
    if mode == 'disabled':
        monkeypatch.setenv('SCREEN_ACTIVITY_VECTORS_DISABLED_UIDS', 'other,u1')

        def forbidden(*args, **kwargs):
            pytest.fail('disabled account attempted cloud vectors')

        monkeypatch.setattr(sa, 'gemini_embed_query', forbidden)
        monkeypatch.setattr(sa.vector_db, 'search_screen_activity_vectors', forbidden)
    refs = []
    result = _search(sa)(
        'budget REVIEW',
        end_date='2026-09-10T00:00:00Z',
        config={'configurable': {'user_id': 'u1', 'evidence_references': refs}},
    )
    assert 'Found 2 screen activity matches' in result
    assert result.count('(relevance: keyword)') == 2
    assert [ref['frame_id'] for ref in refs] == ['both', 'title']
    assert refs[0]['captured_at_ms'] == 1_788_948_000_000
    assert client.screens.filters[0].value == '2026-09-03 00:00:00.000'
    assert 'sensitive provider text' not in caplog.text
    assert 'BUDGET' not in caplog.text


def test_keyword_empty_is_honest_about_scanned_window(monkeypatch, sa):
    _keyword_setup(monkeypatch, sa)
    result = _search(sa)('missing', end_date='2026-09-10T00:00:00Z', config={'configurable': {'user_id': 'u1'}})
    assert result == 'No matches (keyword search over 3 screens in window).'


def test_keyword_scan_caps_at_500_and_single_term_matches_app(monkeypatch, sa):
    client = _keyword_setup(monkeypatch, sa)
    client.screens._rows = {str(i): {'timestamp': '2026-09-09 10:00:00.000', 'appName': 'Editor'} for i in range(501)}
    matches, scanned = sa._keyword_screen_matches('u1', 'editor', None, 1_789_027_200, 10)
    assert scanned == 500
    assert len(matches) == 10


def test_keyword_flag_off_does_not_override_vector_opt_out(monkeypatch, sa):
    _keyword_setup(monkeypatch, sa)
    monkeypatch.setenv('SCREEN_ACTIVITY_KEYWORD_FALLBACK_ENABLED', 'false')
    monkeypatch.setenv('SCREEN_ACTIVITY_VECTORS_DISABLED_UIDS', 'u1')

    def forbidden(*args, **kwargs):
        pytest.fail('policy opt-out attempted a provider')

    monkeypatch.setattr(sa, 'gemini_embed_query', forbidden)
    monkeypatch.setattr(sa, '_keyword_screen_matches', forbidden)
    result = _search(sa)('budget', config={'configurable': {'user_id': 'u1'}})
    assert 'keyword fallback is disabled' in result


def test_keyword_uses_snapshot_identity_and_skips_malformed_payload(monkeypatch, sa):
    client = _keyword_setup(monkeypatch, sa)
    snapshots = [
        _KeywordDoc('actual', {'_document_id': 'spoofed', 'timestamp': '2026-09-09 10:00:00.000', 'ocrText': 'budget'}),
        _KeywordDoc('broken', ['not a mapping']),
    ]
    monkeypatch.setattr(client.screens, 'stream', lambda: snapshots)
    matches, scanned = sa._keyword_screen_matches('u1', 'budget', None, 1_789_027_200, 10)
    assert scanned == 2
    assert [match['screenshot_id'] for match in matches] == ['actual']


def test_keyword_fallback_records_provider_switch(monkeypatch, sa):
    _keyword_setup(monkeypatch, sa, 'error')
    from utils.observability.fallback import record_fallback

    record_fallback.reset_mock()
    _search(sa)('budget', end_date='2026-09-10T00:00:00Z', config={'configurable': {'user_id': 'u1'}})
    record_fallback.assert_called_once_with(
        component='agent_tools',
        from_mode='screen_vectors',
        to_mode='screen_keyword',
        reason='capability_mismatch',
        outcome='degraded',
        log=sa.logger,
    )


def test_keyword_finds_document_written_at_normalized_window_edge(monkeypatch, sa):
    end = datetime(2026, 9, 10, 0, 0, 0, tzinfo=timezone.utc)
    edge = normalize_screen_activity_timestamp(end, end_of_second=True)
    start = normalize_screen_activity_timestamp(end.replace(day=3))
    assert edge == '2026-09-10 00:00:00.999'
    _keyword_setup(monkeypatch, sa)
    client = sa.firestore_db
    client.screens._rows = {
        'edge': {
            'timestamp': edge,
            'ocrText': 'budget review',
            'windowTitle': 'Plan',
            'appName': 'Editor',
        },
        'before': {
            'timestamp': '2026-09-02 23:59:59.999',
            'ocrText': 'budget review',
            'windowTitle': 'Plan',
            'appName': 'Editor',
        },
    }
    matches, scanned = sa._keyword_screen_matches('u1', 'budget', None, int(end.timestamp()), 10)
    assert scanned == 1
    assert [match['screenshot_id'] for match in matches] == ['edge']
    assert client.screens.filters[0].value == start
    assert client.screens.filters[1].value == edge


def test_vector_opt_out_parses_whitespace_without_crash(monkeypatch, sa):
    monkeypatch.delenv('SCREEN_ACTIVITY_VECTORS_DISABLED_UIDS', raising=False)
    assert sa._parse_csv_tokens(None) == []
    assert sa._parse_csv_tokens('  \n\t ') == []
    assert sa._parse_csv_tokens(' other , u1 \n, ') == ['other', 'u1']
    assert sa._screen_vectors_disabled('u1') is False
    monkeypatch.setenv('SCREEN_ACTIVITY_VECTORS_DISABLED_UIDS', '  \n\t ')
    assert sa._screen_vectors_disabled('u1') is False
    monkeypatch.setenv('SCREEN_ACTIVITY_VECTORS_DISABLED_UIDS', ' other , u1 \n')
    assert sa._screen_vectors_disabled('u1') is True
    monkeypatch.setenv('SCREEN_ACTIVITY_VECTORS_DISABLED_UIDS', ' * ')
    assert sa._screen_vectors_disabled('anyone') is True
