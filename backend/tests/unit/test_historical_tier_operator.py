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
        self.store, self.key, self.id = store, key, key
        self.update_time = store.versions[key]
        self.exists = key in store.rows
        self.reference = SimpleNamespace(update=self._update)

    def to_dict(self):
        return dict(self.store.rows[self.key])

    def _update(self, data, option=None):
        if option is None or self.store.versions[self.key] != self.update_time:
            raise FailedPrecondition('changed')
        self.store.writes.append((self.key, data))


class Query:
    def __init__(self, store, field, value):
        self.store, self.field, self.value, self._limit, self._after = store, field, value, None, None

    def select(self, fields):
        self.store.selected = tuple(fields)
        return self

    def order_by(self, field):
        return self

    def limit(self, count):
        clone = Query(self.store, self.field, self.value)
        clone._limit, clone._after = count, self._after
        return clone

    def start_after(self, snapshot):
        clone = Query(self.store, self.field, self.value)
        clone._limit, clone._after = self._limit, snapshot.key
        return clone

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
        if self._after is not None:
            keys = keys[keys.index(self._after) + 1 :]
        self.store.reads += len(keys[: self._limit])
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
        self.reads = 0

    def collection(self, name):
        self.paths.append(name)
        return self

    def document(self, name):
        self.paths.append(name)
        store = self

        def get(field_paths=None):
            return Snapshot(store, name) if name in store.rows else SimpleNamespace(exists=False)

        return SimpleNamespace(collection=self.collection, get=get)

    def where(self, *, filter):
        return Query(self, filter.field_path, filter.value)


def _run(client, **kwargs):
    kwargs.setdefault('retire_outbox', lambda *_: False)
    return operator.run(client, 'owner', now=NOW.timestamp(), **kwargs)['counts']


@pytest.fixture(autouse=True)
def _gate(monkeypatch):
    monkeypatch.delenv('ENRICHMENT_MAX_AGE_HOURS', raising=False)


def test_dry_run_counts_and_writes_nothing():
    client = Client({'a': stuck(), 'b': stuck(summary_lane='live'), 'c': stuck(created_at=NOW - timedelta(hours=70))})
    counts = _run(client)
    assert counts == {'eligible': 1, 'kept_not_backfill': 1, 'kept_too_recent': 1, 'scanned': 3}
    assert client.writes == []
    assert client.paths[:3] == ['users', 'owner', 'conversations']
    # Only classifier fields are read: no transcript or summary text, not even the overview.
    assert not any(field.startswith(('transcript', 'structured.overview')) for field in client.selected)


def test_apply_converts_a_stuck_row_into_a_ready_historical_row(monkeypatch):
    monkeypatch.delenv('HOME_STEP_PROJECTION_ENABLED', raising=False)
    client = Client({'a': stuck(sync_processing_hold={'pending_since': 5.0, 'held': True})})
    retired = []
    result = operator.run(
        client, 'owner', apply=True, now=NOW.timestamp(), retire_outbox=lambda c, u, cid: retired.append(cid) or True
    )
    assert result['counts'] == {'eligible': 1, 'outbox_retired': 1, 'scanned': 1, 'written': 1}
    assert result['written_ids'] == ['a'] and retired == ['a']
    key, update = client.writes[0]
    assert update['processing_tier'] == 'historical'
    assert update['summary_due_at'] is None
    assert update['structured.title_provenance'] == 'historical_minimum'
    assert update['summary_title_provenance'] is firestore.DELETE_FIELD
    # The open sync hold ends with the conversion, so no wake is owed behind the gate.
    assert update['sync_processing_hold.pending_since'] is None and update['sync_processing_hold.held'] is False
    converted = stuck(
        processing_tier='historical',
        summary_due_at=None,
        terminal_no_derived_effects=True,
        summary_blocked_reason='historical_on_open',
        structured={'title': 'We planned the garden beds', 'title_provenance': 'historical_minimum'},
    )
    converted.pop('summary_title_provenance')
    assert home_step.classify(converted) == 'ready'
    assert summary_delivery.refusal(converted) == 'local_only'


def test_a_row_without_an_open_hold_gets_no_hold_patch():
    client = Client({'a': stuck()})
    _run(client, apply=True)
    assert not any(field.startswith('sync_processing_hold') for field in client.writes[0][1])


@pytest.mark.parametrize(
    ('updates', 'reason'),
    [
        ({'discarded': True}, 'kept_lifecycle'),
        ({'is_locked': True}, 'kept_local_only'),
        ({'processing_tier': 'historical'}, 'kept_already_historical'),
        ({'user_title': 'Mine'}, 'kept_manual'),
        ({'summary_output_present': True}, 'kept_already_enriched'),
        ({'summary_output_present': None}, 'kept_already_enriched'),
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


def test_kept_rows_never_stall_the_run(monkeypatch):
    # Pages advance by cursor past every kept row, so an eligible row behind them is reached.
    monkeypatch.setattr(operator, 'PAGE_SIZE', 3)
    rows = {str(i): stuck(user_title='Mine') for i in range(9)}
    rows['9'] = stuck()
    client = Client(rows)
    counts = _run(client, limit=1)
    assert counts['eligible'] == 1 and counts['kept_manual'] == 9


def test_scan_and_limit_are_bounded(monkeypatch):
    monkeypatch.setattr(operator, 'PAGE_SIZE', 3)
    client = Client({str(i): stuck() for i in range(10)})
    assert _run(client, limit=4)['eligible'] == 4
    assert _run(client, scan=5)['scanned'] == 5
    for bad in ({'limit': 0}, {'limit': operator.MAX_LIMIT + 1}, {'scan': 0}, {'scan': operator.MAX_SCAN + 1}):
        with pytest.raises(ValueError):
            _run(client, **bad)
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


def _cli(monkeypatch, client, argv):
    monkeypatch.setattr('database._client.get_firestore_client', lambda: client)
    monkeypatch.setattr(operator, '_retire_parked_outbox', lambda *_: False)
    return operator.main(argv)


def test_cli_refuses_apply_without_an_approval_reference(monkeypatch, tmp_path):
    client = Client({'a': stuck()})
    with pytest.raises(SystemExit):
        _cli(monkeypatch, client, ['convert', '--uid', 'owner', '--apply', '--receipt-dir', str(tmp_path)])
    assert client.writes == [] and not list(tmp_path.iterdir())


def test_cli_refuses_production_apply_without_confirmation(monkeypatch, capsys, tmp_path):
    client = Client({'a': stuck()})
    client.project = 'based-hardware'
    with pytest.raises(SystemExit):
        _cli(monkeypatch, client, ['convert', '--uid', 'owner', '--apply', '--approval-ref', 'ref-1'])
    assert client.writes == []
    assert _cli(monkeypatch, client, ['convert', '--uid', 'owner']) == 0
    out = json.loads(capsys.readouterr().out)
    assert out['apply'] is False and 'owner' not in json.dumps(out) and 'written_ids' not in out


def test_an_applied_run_writes_a_receipt_that_clear_marker_replays(monkeypatch, capsys, tmp_path):
    client = Client({'row-alpha': stuck(), 'row-beta': stuck(summary_lane='live')})
    argv = ['--uid', 'owner', '--apply', '--approval-ref', 'ref-1', '--receipt-dir', str(tmp_path)]
    assert _cli(monkeypatch, client, ['convert', *argv]) == 0
    out = json.loads(capsys.readouterr().out)
    assert 'row-alpha' not in json.dumps(out) and 'written_ids' not in out
    (receipt_path,) = tmp_path.iterdir()
    receipt = json.loads(receipt_path.read_text())
    assert receipt['mode'] == 'convert' and receipt['approval_ref'] == 'ref-1'
    assert receipt['written_ids'] == ['row-alpha'] and receipt['owner_hash'] == operator.owner_hash('owner')
    assert 'owner' not in receipt_path.name
    # Another historical row the receipt did not write is left alone by the replay.
    client.rows['row-alpha'] = stuck(processing_tier='historical', summary_due_at=None)
    client.rows['row-gamma'] = stuck(processing_tier='historical', summary_due_at=None)
    client.versions['row-gamma'] = 1
    client.writes.clear()
    assert _cli(monkeypatch, client, ['clear-marker', '--from-receipt', str(receipt_path), *argv]) == 0
    assert [key for key, _ in client.writes] == ['row-alpha']


def test_a_receipt_for_another_owner_is_refused(monkeypatch, tmp_path):
    receipt = tmp_path / 'r.json'
    receipt.write_text(
        json.dumps({'mode': 'convert', 'owner_hash': operator.owner_hash('other'), 'written_ids': ['a']})
    )
    with pytest.raises(ValueError):
        _cli(monkeypatch, Client({}), ['clear-marker', '--uid', 'owner', '--from-receipt', str(receipt)])


@pytest.mark.parametrize(
    ('row', 'retired'),
    [
        ({'age_gate_parked': True, 'dormant': True, 'lease_until': 0}, True),
        ({'dormant': False, 'lease_until': 0}, False),
        ({'age_gate_parked': True, 'lease_until': 4102444800}, False),
        (None, False),
    ],
)
def test_only_a_parked_unleased_wake_is_retired(monkeypatch, row, retired):
    from utils.enrichment import outbox

    seen = {}

    def mutate(document_id, update, client=None):
        new, result = update(row)
        seen.update(id=document_id, deleted=new is None and row is not None)
        return result

    monkeypatch.setattr(outbox, 'mutate_row', mutate)
    assert operator._retire_parked_outbox(object(), 'owner', 'row-1') is retired
    assert seen['id'] == outbox.key('owner', 'row-1') and seen['deleted'] is retired
