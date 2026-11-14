"""Hermetic bounds and classification for the 24-hour audio silence census."""

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from prometheus_client import CollectorRegistry

from database.audio_silence_census import sample
from testing.hermetic_network import block_outbound_network
from utils.batch_pipeline.metrics import QueueMetrics
from utils.lifecycle_metrics import SILENCE_CENSUS_INTERVAL_SECONDS, SilenceCensusMetrics

NOW = datetime(2026, 11, 10, 12, tzinfo=timezone.utc).timestamp()


@pytest.fixture(autouse=True)
def hermetic():
    with block_outbound_network():
        yield


@dataclass
class Query:
    client: object
    name: str
    parent: str = ''
    group: bool = False
    filters: tuple = ()
    orders: tuple = ()
    cap: int | None = None

    def where(self, *, filter):
        return replace(self, filters=(*self.filters, filter))

    def order_by(self, field, direction=None):
        return replace(self, orders=(*self.orders, (field, direction)))

    def select(self, _fields):
        return self

    def limit(self, cap):
        return replace(self, cap=cap)

    def rows(self):
        rows = []
        for path, row in self.client.rows.items():
            parts = path.split('/')
            if self.group:
                if len(parts) != 4 or parts[2] != self.name:
                    continue
            elif self.parent:
                if not path.startswith(self.parent + '/') or parts[-2] != self.name:
                    continue
            elif len(parts) != 2 or parts[0] != self.name:
                continue
            if all(
                condition.field_path in row
                and (
                    row[condition.field_path] == condition.value
                    if condition.op_string == '=='
                    else (
                        row[condition.field_path] >= condition.value
                        if condition.op_string == '>='
                        else row[condition.field_path] <= condition.value
                    )
                )
                for condition in self.filters
            ):
                rows.append((path, row))
        for order, direction in reversed(self.orders):
            rows.sort(
                key=(lambda pair: pair[0]) if order == '__name__' else (lambda pair: pair[1][order]),
                reverse=direction == 'DESCENDING',
            )
        assert self.cap is not None, 'unbounded query'
        return rows[: self.cap]

    def stream(self, **kwargs):
        assert kwargs == {'timeout': 10, 'retry': None}
        rows = self.rows()
        self.client.streamed += len(rows)
        return [
            SimpleNamespace(reference=SimpleNamespace(path=path), to_dict=lambda row=row: row) for path, row in rows
        ]

    def count(self):
        return SimpleNamespace(
            get=lambda **kwargs: [[SimpleNamespace(value=len(self.rows()))]],
        )


class Collection(Query):
    def document(self, key):
        parent = f'{self.name}/{key}'
        return SimpleNamespace(collection=lambda name: Query(self.client, name, parent=parent))


class Client:
    def __init__(self, rows=None):
        self.rows = rows or {}
        self.streamed = 0

    def collection(self, name):
        return Collection(self, name)

    def collection_group(self, name):
        return Query(self, name, group=True)


def conversation(uid, cid, **row):
    return f'users/{uid}/conversations/{cid}', {
        'created_at': datetime.fromtimestamp(row.pop('created_at', NOW - 3600), tz=timezone.utc),
        'source': 'omi',
        **row,
    }


def test_complete_window_deduplicates_users_and_partitions_states_sources():
    rows = dict(
        [
            conversation('silent', 'one'),
            conversation('silent', 'two', created_at=NOW - 7200),
            conversation('heard', 'one', source='desktop', record_upload_sessions={'token': True}),
            conversation('received', 'one', source='friend', server_batch_audio_received=True),
            conversation('multi', 'omi', created_at=NOW - 7200, source='omi'),
            conversation('multi', 'desktop', created_at=NOW - 3600, source='desktop'),
            conversation('outbox-app', 'one'),
        ]
    )
    rows['batch_pipeline_prod_jobs/job'] = {
        'owner_id': 'job-user',
        'enqueued_at': NOW - 60,
        'record_snapshot': {'source': 'desktop'},
    }
    rows['sync_reprocess_outbox/orphan'] = {'uid': 'orphan', 'first_pending_at': NOW - 30}
    rows['sync_reprocess_outbox/app'] = {'uid': 'outbox-app', 'first_pending_at': NOW - 20}

    result = sample(Client(rows), 'batch_pipeline_prod', NOW)

    assert not result['partial']
    assert result['reads'] == len(rows)
    assert result['counts'] == {
        ('app_active_no_audio', 'omi'): 1,
        ('app_active_no_audio', 'desktop'): 1,
        ('app_active_no_audio', 'other'): 0,
        ('app_active_with_audio', 'omi'): 1,
        ('app_active_with_audio', 'desktop'): 2,
        ('app_active_with_audio', 'other'): 1,
        ('audio_no_app_activity', 'omi'): 0,
        ('audio_no_app_activity', 'desktop'): 0,
        ('audio_no_app_activity', 'other'): 1,
    }


def test_future_and_expired_rows_are_outside_the_24_hour_window():
    rows = dict(
        [
            conversation('future', 'one', created_at=NOW + 1),
            conversation('expired', 'one', created_at=NOW - 86401),
        ]
    )
    result = sample(Client(rows), 'batch_pipeline_prod', NOW)
    assert result['reads'] == 0
    assert not any(result['counts'].values())


def test_unseen_upload_sessions_never_become_false_silence():
    client = Client(dict([conversation('possible-audio', 'first'), conversation('possible-audio', 'second')]))

    result = sample(client, 'batch_pipeline_prod', NOW, page_limit=1)

    assert result['partial']
    assert result['reads'] == 2  # one page document and one COUNT(1)
    assert not any(result['counts'].values())


def test_candidate_aggregates_join_audio_and_app_evidence_outside_the_page():
    rows = dict(
        [
            conversation('received', 'silent', created_at=NOW - 3400),
            conversation('received', 'received', created_at=NOW - 3500, server_batch_audio_received=True),
            conversation('outbox-app', 'hidden', created_at=NOW - 3600),
        ]
    )
    rows['sync_reprocess_outbox/app'] = {'uid': 'outbox-app', 'first_pending_at': NOW}
    client = Client(rows)

    result = sample(client, 'batch_pipeline_prod', NOW, page_limit=1)

    assert result['partial']
    assert result['reads'] == 6  # one page document plus five candidate COUNT(1)s
    assert result['counts']['app_active_with_audio', 'omi'] == 1
    assert result['counts']['app_active_with_audio', 'other'] == 1  # no source-bearing row was read
    assert not any(count for (state, _), count in result['counts'].items() if state != 'app_active_with_audio')


def test_hard_read_budget_stops_candidate_queries():
    rows = dict([conversation(f'user-{index}', 'one') for index in range(5)])
    rows['batch_pipeline_prod_jobs/job'] = {'owner_id': 'job', 'enqueued_at': NOW}
    rows['sync_reprocess_outbox/outbox'] = {'uid': 'orphan', 'first_pending_at': NOW}

    result = sample(Client(rows), 'batch_pipeline_prod', NOW, read_budget=4)

    assert result['partial']
    assert result['reads'] <= 4
    assert sum(result['counts'].values()) < 7


def test_metrics_have_only_nine_static_series_and_six_hour_cadence():
    registry = CollectorRegistry()
    metrics = SilenceCensusMetrics(registry=registry)
    counts = {
        (state, source): 1
        for state in ('app_active_no_audio', 'app_active_with_audio', 'audio_no_app_activity')
        for source in ('omi', 'desktop', 'other')
    }
    calls = []

    def complete():
        calls.append(1)
        return {'counts': counts, 'partial': False, 'reads': 1}

    metrics.refresh(NOW, complete)
    metrics.refresh(NOW + SILENCE_CENSUS_INTERVAL_SECONDS - 1, complete)
    assert len(calls) == 1
    assert (
        len(
            list(
                registry.get_sample_value('omi_audio_silence_census', {'state': state, 'source': source})
                for state, source in counts
            )
        )
        == 9
    )
    assert registry.get_sample_value('omi_audio_silence_census_partial') == 0

    metrics.refresh(NOW + SILENCE_CENSUS_INTERVAL_SECONDS, lambda: {'counts': counts, 'partial': True, 'reads': 4000})
    assert registry.get_sample_value('omi_audio_silence_census_partial') == 1
    samples = [
        sample
        for family in registry.collect()
        if family.name == 'omi_audio_silence_census'
        for sample in family.samples
    ]
    assert len(samples) == 9
    assert {sample.labels['state'] for sample in samples} == {
        'app_active_no_audio',
        'app_active_with_audio',
        'audio_no_app_activity',
    }
    assert {sample.labels['source'] for sample in samples} == {'omi', 'desktop', 'other'}


def test_queue_kill_switch_skips_all_census_reads(monkeypatch):
    from database.batch_pipeline_store import FirestoreStore
    from utils.batch_pipeline import metrics as module

    monkeypatch.setenv('AUDIO_SILENCE_CENSUS_ENABLED', 'false')
    registry = CollectorRegistry()
    sampler = QueueMetrics(registry)
    store = Mock(spec=FirestoreStore)
    store.client, store.namespace = Mock(), 'synthetic'
    store.oldest.return_value = store.oldest_retry.return_value = None
    monkeypatch.setattr(sampler.record_pending, 'refresh', Mock())
    monkeypatch.setattr(sampler.nojob, 'refresh', Mock())
    monkeypatch.setattr(sampler, 'refresh_timeliness', Mock())
    monkeypatch.setattr(sampler, 'refresh_projection', Mock())
    reader = Mock()
    monkeypatch.setattr(module, 'audio_silence_sample', reader)

    sampler.refresh(store, NOW)
    reader.assert_not_called()
    assert registry.get_sample_value('omi_audio_silence_census_observed_at_seconds') == 0

    monkeypatch.delenv('AUDIO_SILENCE_CENSUS_ENABLED')
    result = sample(Client(), 'batch_pipeline_prod', NOW)
    reader.return_value = result
    sampler.refresh(store, NOW + 1)
    reader.assert_called_once_with(store.client, 'synthetic', NOW + 1)
    assert registry.get_sample_value('omi_audio_silence_census_observed_at_seconds') == NOW + 1
