"""The owner-scoped historical-tier operator: bounded, dry-run first, update-time fenced, counts only."""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from google.api_core.exceptions import FailedPrecondition
from google.cloud import firestore

from utils.conversations import home_step, summary_delivery

_PATH = Path(__file__).resolve().parents[2] / 'scripts' / 'historical_tier_operator.py'
_SPEC = importlib.util.spec_from_file_location('historical_tier_operator', _PATH)
operator = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(operator)

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


def stuck(**updates):
    row = {
        'status': 'completed',
        'created_at': NOW - timedelta(days=10),
        'structured': {'title': 'We planned the garden beds', 'title_provenance': 'server_minimum'},
        'summary_title_provenance': 'server_minimum',
        'summary_due_at': (NOW - timedelta(days=9)).timestamp(),
        'summary_first_pending_at': (NOW - timedelta(days=10)).timestamp(),
        'summary_lane': 'backfill',
        'summary_output_present': False,
    }
    row.update(updates)
    return row


class Snapshot:
    def __init__(self, store, key):
        self.store, self.key = store, key
        self.update_time = store.versions[key]
        self.reference = SimpleNamespace(update=self._update)

    def to_dict(self):
        return dict(self.store.rows[self.key])

    def _update(self, data, option=None):
        if option is None or self.store.versions[self.key] != self.update_time:
            raise FailedPrecondition('changed')
        self.store.writes.append((self.key, data))


class Query:
    def __init__(self, store, field, value):
        self.store, self.field, self.value, self._limit = store, field, value, None

    def select(self, fields):
        self.store.selected = tuple(fields)
        return self

    def limit(self, count):
        self._limit = count
        return self

    def stream(self):
        keys = [
            key
            for key, row in self.store.rows.items()
            if (
                row.get(self.field) == self.value
                if self.field == 'processing_tier'
                else _same_type(row.get(self.field), self.value) and row.get(self.field) > self.value
            )
        ]
        return [Snapshot(self.store, key) for key in keys[: self._limit]]


def _same_type(stored, bound):
    # Firestore range filters never cross value types: numbers and timestamps are separate ranges.
    if isinstance(bound, datetime):
        return isinstance(stored, datetime)
    return isinstance(stored, (int, float)) and not isinstance(stored, bool)


class Client:
    def __init__(self, rows):
        self.rows = dict(rows)
        self.versions = {key: 1 for key in rows}
        self.writes = []
        self.paths = []

    def collection(self, name):
        self.paths.append(name)
        return self

    def document(self, name):
        self.paths.append(name)
        return self

    def where(self, *, filter):
        return Query(self, filter.field_path, filter.value)


def _run(client, **kwargs):
    return operator.run(client, 'owner', now=NOW.timestamp(), **kwargs)['counts']


def test_dry_run_counts_and_writes_nothing():
    client = Client({'a': stuck(), 'b': stuck(summary_lane='live'), 'c': stuck(created_at=NOW - timedelta(hours=70))})
    counts = _run(client)
    assert counts == {'eligible': 1, 'kept_not_backfill': 1, 'kept_too_recent': 1, 'scanned': 3}
    assert client.writes == []
    assert client.paths[:3] == ['users', 'owner', 'conversations']
    # Only classifier fields are read: no transcript or summary text.
    assert 'transcript_segments' not in client.selected and 'structured.overview' in client.selected


def test_apply_converts_a_stuck_row_into_a_ready_historical_row(monkeypatch):
    monkeypatch.delenv('HOME_STEP_PROJECTION_ENABLED', raising=False)
    client = Client({'a': stuck()})
    assert _run(client, apply=True) == {'eligible': 1, 'scanned': 1, 'written': 1}
    key, update = client.writes[0]
    assert update['processing_tier'] == 'historical'
    assert update['summary_due_at'] is None
    assert update['structured.title_provenance'] is firestore.DELETE_FIELD
    assert update['summary_title_provenance'] is firestore.DELETE_FIELD
    converted = stuck(
        processing_tier='historical',
        summary_due_at=None,
        terminal_no_derived_effects=True,
        summary_blocked_reason='historical_on_open',
        structured={'title': 'We planned the garden beds'},
    )
    converted.pop('summary_title_provenance')
    assert home_step.classify(converted) == 'ready'
    assert summary_delivery.refusal(converted) == 'local_only'


@pytest.mark.parametrize(
    ('updates', 'reason'),
    [
        ({'discarded': True}, 'kept_lifecycle'),
        ({'is_locked': True}, 'kept_local_only'),
        ({'processing_tier': 'historical'}, 'kept_already_historical'),
        ({'user_title': 'Mine'}, 'kept_manual'),
        ({'summary_output_present': True}, 'kept_already_enriched'),
        ({'summary_due_at': None, 'summary_lane': 'backfill'}, None),
        ({'structured': {'title': 'Real'}, 'summary_title_provenance': None}, 'kept_unknown_provenance'),
        ({'finalization_status': 'leased'}, 'kept_generation_owned'),
    ],
)
def test_every_other_row_is_kept(updates, reason):
    client = Client({'a': stuck(**updates)})
    counts = _run(client, apply=True)
    assert client.writes == []
    if reason is None:
        assert counts == {}  # an unarmed row never enters the due query
    else:
        assert counts == {reason: 1, 'scanned': 1}


def test_timestamp_due_rows_are_scanned_in_their_own_pass():
    client = Client({'a': stuck(summary_due_at=NOW - timedelta(days=9))})
    assert _run(client)['eligible'] == 1


def test_a_changed_row_is_a_conflict_not_a_write():
    client = Client({'a': stuck()})
    original = Snapshot.__init__

    def stale(self, store, key):
        original(self, store, key)
        store.versions[key] += 1

    try:
        Snapshot.__init__ = stale
        counts = _run(client, apply=True)
    finally:
        Snapshot.__init__ = original
    assert counts['conflicts'] == 1 and client.writes == []


def test_scan_is_bounded():
    client = Client({str(i): stuck() for i in range(10)})
    assert _run(client, limit=4)['scanned'] == 4
    for bad in (0, operator.MAX_LIMIT + 1):
        with pytest.raises(ValueError):
            _run(client, limit=bad)
    with pytest.raises(ValueError):
        operator.run(client, '', now=NOW.timestamp())


def test_clear_marker_removes_the_tier_from_unsummarized_rows_only():
    client = Client(
        {
            'a': stuck(processing_tier='historical', summary_due_at=None),
            'b': stuck(processing_tier='historical', summary_output_present=True),
        }
    )
    counts = _run(client, mode='clear-marker', apply=True)
    assert counts == {'eligible': 1, 'kept_already_enriched': 1, 'scanned': 2, 'written': 1}
    assert client.writes[0][1]['processing_tier'] is firestore.DELETE_FIELD


def test_cli_refuses_production_apply_without_confirmation(monkeypatch, capsys):
    client = Client({'a': stuck()})
    client.project = 'based-hardware'
    monkeypatch.setattr('database._client.get_firestore_client', lambda: client)
    with pytest.raises(SystemExit):
        operator.main(['convert', '--uid', 'owner', '--apply'])
    assert client.writes == []
    assert operator.main(['convert', '--uid', 'owner']) == 0
    out = json.loads(capsys.readouterr().out)
    assert out['apply'] is False and 'owner' not in json.dumps(out)
