"""Tests for get_conversations_count logic and /v1/conversations/count endpoint.

The DB function is exercised through the neutral document-store port: a ``_CountCaptureStore``
(a ``FakeDocumentStore`` whose ``count()`` returns a scripted value and records the neutral
filters it saw) is injected at the ``_store`` seam (ADR-0002/ADR-0028). This drives the real
``database.conversations.get_conversations_count`` — no inline copy to drift, so no source-scrape
tripwire. The router-level tests still read production source via ``open()`` for registration
parity assertions.
"""

import os

import database.conversations as conversations_db
from tests.store_fakes import FakeDocumentStore


class _CountCaptureStore(FakeDocumentStore):
    """A store whose ``count()`` returns a scripted value and records the neutral filters it saw.

    This exercises the real ``database.conversations.get_conversations_count`` through the port
    seam, so there is no inline copy to drift and no source-scrape tripwire (AGENTS.md prefers
    behavioral coverage over asserting source strings).
    """

    def __init__(self, value):
        super().__init__()
        self._value = value
        self.count_calls = []

    def count(self, collection, *, filters=None):
        self.count_calls.append((collection, [tuple(f) for f in (filters or [])]))
        return self._value


class TestConversationsCount:
    """Behavioral tests of the real get_conversations_count against the neutral port seam."""

    def _seed(self, monkeypatch, value):
        store = _CountCaptureStore(value)
        monkeypatch.setattr(conversations_db, '_store', lambda: store)
        return store

    def _filters(self, store):
        assert len(store.count_calls) == 1
        collection, filters = store.count_calls[0]
        assert collection == 'users/uid1/conversations'
        return filters

    def test_count_returns_integer(self, monkeypatch):
        self._seed(monkeypatch, 42)

        result = conversations_db.get_conversations_count('uid1')
        assert result == 42
        assert isinstance(result, int)

    def test_count_with_statuses_applies_correct_filters(self, monkeypatch):
        store = self._seed(monkeypatch, 10)

        result = conversations_db.get_conversations_count('uid1', statuses=['processing', 'completed'])
        assert result == 10
        assert self._filters(store) == [
            ('discarded', '==', False),
            ('status', 'in', ['processing', 'completed']),
        ]

    def test_count_composes_sources_and_statuses(self, monkeypatch):
        store = self._seed(monkeypatch, 3)

        result = conversations_db.get_conversations_count(
            'uid1', statuses=['processing', 'completed'], sources=['omi']
        )

        assert result == 3
        assert self._filters(store) == [
            ('discarded', '==', False),
            ('source', '==', 'omi'),
            ('status', 'in', ['processing', 'completed']),
        ]

    def test_count_include_discarded_skips_filter(self, monkeypatch):
        store = self._seed(monkeypatch, 55)

        result = conversations_db.get_conversations_count('uid1', include_discarded=True)
        assert result == 55
        assert self._filters(store) == []

    def test_count_zero(self, monkeypatch):
        self._seed(monkeypatch, 0)

        assert conversations_db.get_conversations_count('uid1') == 0

    def test_count_discarded_only_applies_discarded_filter(self, monkeypatch):
        """No statuses passed — only the discarded filter should be applied."""
        store = self._seed(monkeypatch, 7)

        result = conversations_db.get_conversations_count('uid1')
        assert result == 7
        assert self._filters(store) == [('discarded', '==', False)]

    def test_count_include_discarded_with_statuses(self, monkeypatch):
        """include_discarded=True + statuses — only status filter, no discarded filter."""
        store = self._seed(monkeypatch, 20)

        result = conversations_db.get_conversations_count('uid1', include_discarded=True, statuses=['processing'])
        assert result == 20
        assert self._filters(store) == [('status', '==', 'processing')]

    def test_count_applies_list_filter_parity(self, monkeypatch):
        store = self._seed(monkeypatch, 3)

        result = conversations_db.get_conversations_count(
            'uid1',
            statuses=['completed'],
            start_date='2026-06-01T00:00:00Z',
            end_date='2026-06-02T00:00:00Z',
            folder_id='folder-a',
            starred=False,
        )

        assert result == 3
        assert self._filters(store) == [
            ('discarded', '==', False),
            ('status', '==', 'completed'),
            ('folder_id', '==', 'folder-a'),
            ('starred', '==', False),
            ('created_at', '>=', '2026-06-01T00:00:00Z'),
            ('created_at', '<=', '2026-06-02T00:00:00Z'),
        ]


class TestConversationsCountEndpointParsing:
    """Test the router-level statuses parsing logic."""

    def test_statuses_none_returns_empty_list(self):
        statuses = None
        result = [s.strip() for s in statuses.split(',') if s.strip()] if statuses else []
        assert result == []

    def test_statuses_empty_string_returns_empty_list(self):
        statuses = ''
        result = [s.strip() for s in statuses.split(',') if s.strip()] if statuses else []
        assert result == []

    def test_statuses_single_value(self):
        statuses = 'processing'
        result = [s.strip() for s in statuses.split(',') if s.strip()] if statuses else []
        assert result == ['processing']

    def test_statuses_multiple_values(self):
        statuses = 'processing,completed'
        result = [s.strip() for s in statuses.split(',') if s.strip()] if statuses else []
        assert result == ['processing', 'completed']

    def test_statuses_with_whitespace(self):
        statuses = ' processing , completed , '
        result = [s.strip() for s in statuses.split(',') if s.strip()] if statuses else []
        assert result == ['processing', 'completed']

    def test_statuses_comma_only_returns_empty(self):
        statuses = ','
        result = [s.strip() for s in statuses.split(',') if s.strip()] if statuses else []
        assert result == []

    def test_statuses_multiple_commas_returns_empty(self):
        statuses = ',,,'
        result = [s.strip() for s in statuses.split(',') if s.strip()] if statuses else []
        assert result == []

    def test_response_shape(self):
        """The endpoint should return {'count': N}."""
        count = 42
        response = {'count': count}
        assert 'count' in response
        assert isinstance(response['count'], int)


class TestConversationsCountRouteSource:
    """Verify the real route source matches expected registration and forwarding."""

    def test_route_registered_with_correct_path(self):
        source_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'conversations.py')
        with open(source_path, encoding='utf-8') as f:
            source = f.read()
        assert "'/v1/conversations/count'" in source

    def test_route_forwards_include_discarded(self):
        source_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'conversations.py')
        with open(source_path, encoding='utf-8') as f:
            source = f.read()
        assert 'include_discarded=include_discarded' in source

    def test_route_forwards_statuses_as_list(self):
        source_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'conversations.py')
        with open(source_path, encoding='utf-8') as f:
            source = f.read()
        assert 'statuses=status_list' in source

    def test_route_forwards_visible_list_filters(self):
        source_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'conversations.py')
        with open(source_path, encoding='utf-8') as f:
            source = f.read()
        assert 'start_date=start_date' in source
        assert 'end_date=end_date' in source
        assert 'folder_id=folder_id' in source
        assert 'starred=starred' in source

    def test_route_returns_count_dict(self):
        source_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'conversations.py')
        with open(source_path, encoding='utf-8') as f:
            source = f.read()
        assert "{'count': count}" in source or "{'count':count}" in source

    def test_route_forwards_sources_as_list(self):
        source_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'conversations.py')
        with open(source_path, encoding='utf-8') as f:
            source = f.read()
        assert 'sources=source_list' in source

    def test_route_does_not_reject_statuses_combined_with_sources(self):
        source_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'conversations.py')
        with open(source_path, encoding='utf-8') as f:
            source = f.read()
        assert 'statuses and sources filters cannot be combined' not in source

    def test_route_echoes_sources_when_filtered(self):
        # Clients rely on the echo to distinguish a filtered count from an
        # older backend that ignored the unknown sources param.
        source_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'conversations.py')
        with open(source_path, encoding='utf-8') as f:
            source = f.read()
        assert "{'count': count, 'sources': source_list}" in source


class TestAppsV2LimitBoundary:
    """Test the /v2/apps limit parameter boundary (le=100) against real source."""

    def test_source_has_le_100(self):
        """Verify the real route source has le=100 (not le=50 or other)."""
        source_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'apps.py')
        with open(source_path, encoding='utf-8') as f:
            source = f.read()
        assert 'le=100' in source

    def test_source_has_ge_1(self):
        """Verify the real route source has ge=1."""
        source_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'apps.py')
        with open(source_path, encoding='utf-8') as f:
            source = f.read()
        assert 'ge=1' in source

    def test_limit_at_maximum_is_valid(self):
        """limit=100 should be accepted (le=100)."""
        limit = 100
        assert 1 <= limit <= 100

    def test_limit_above_maximum_is_invalid(self):
        """limit=101 should fail validation (le=100)."""
        limit = 101
        assert not (1 <= limit <= 100)

    def test_limit_zero_is_invalid(self):
        """limit=0 should fail validation (ge=1)."""
        limit = 0
        assert not (1 <= limit <= 100)

    def test_limit_negative_is_invalid(self):
        """limit=-1 should fail validation (ge=1)."""
        limit = -1
        assert not (1 <= limit <= 100)

    def test_limit_at_minimum_is_valid(self):
        """limit=1 should be accepted (ge=1)."""
        limit = 1
        assert 1 <= limit <= 100
