"""Hermetic lifecycle alarm samplers: cohorts, bounds, stale clocks and no IDs."""

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from prometheus_client import CollectorRegistry, generate_latest

from database import lifecycle_metrics_queries as queries
from testing.hermetic_network import block_outbound_network
from utils.lifecycle_metrics import COHORT_START, PhaseMetrics


@pytest.fixture(autouse=True)
def hermetic():
    with block_outbound_network():
        yield


@dataclass
class Query:
    client: object
    name: str
    filters: tuple = ()
    order: str | None = None
    cap: int | None = None

    def where(self, *, filter):
        return replace(self, filters=(*self.filters, filter))

    def order_by(self, field):
        return replace(self, order=field)

    def select(self, fields):
        return self

    def limit(self, cap):
        assert 0 < cap <= 20001
        return replace(self, cap=cap)

    def document(self, key):
        return SimpleNamespace(path=f'{self.name}/{key}')

    def rows(self):
        rows = self.client.rows.get(self.name, [])
        for f in self.filters:
            field, op, value = f.field_path, f.op_string, f.value
            rows = [
                (path, row)
                for path, row in rows
                if field in row
                and (row[field] == value if op == '==' else row[field] is not None and row[field] >= value)
            ]
        if self.order and self.order != '__name__':
            rows = sorted(rows, key=lambda pair: pair[1][self.order])
        assert self.cap is not None, 'unbounded read'
        return rows[: self.cap]

    def stream(self, **kwargs):
        assert self.cap <= 1000
        assert kwargs == {'timeout': 10, 'retry': None}
        self.client.reads.append(self)
        return [
            SimpleNamespace(to_dict=lambda row=row: row, reference=SimpleNamespace(path=path))
            for path, row in self.rows()
        ]

    def count(self):
        return SimpleNamespace(get=lambda **kwargs: [[SimpleNamespace(value=len(self.rows()))]])


class Client:
    def __init__(self, **rows):
        self.rows, self.reads = rows, []

    def collection(self, name):
        return Query(self, name)

    collection_group = collection

    def get_all(self, refs, **kwargs):
        present = {path for rows in self.rows.values() for path, _ in rows}
        return [SimpleNamespace(reference=ref, exists=ref.path in present) for ref in refs]


def entries(rows):
    return [
        (f'synthetic/{i}', {**({'dormant': False} if 'first_pending_at' in row else {}), **row})
        for i, row in enumerate(rows)
    ]


def test_record_pending_cohort_excludes_legacy_and_retries_do_not_reset_clock():
    now = COHORT_START + 20_000
    client = Client(
        batch_pipeline_prod_jobs=entries(
            [
                {'state': 'record_pending', 'enqueued_at': now - 3 * 86400, 'available_at': now},
                {'state': 'record_pending', 'enqueued_at': now - 7201, 'available_at': now},
                {'state': 'ready', 'enqueued_at': now - 8000},
            ]
        )
    )
    assert queries.record_pending(client, 'batch_pipeline_prod', now) == {'record_pending': (7201, 2, False)}
    assert len(client.reads) == 1
    assert client.reads[0].order == 'enqueued_at'


def test_record_pending_full_page_and_capped_aggregate_are_explicitly_blind():
    now = COHORT_START + 20_000
    client = Client(
        batch_pipeline_prod_jobs=entries([{'state': 'record_pending', 'enqueued_at': now - 8000} for _ in range(6000)])
    )
    assert queries.record_pending(client, 'batch_pipeline_prod', now) == {'record_pending': (8000, 5001, True)}


def test_initial_cohort_excludes_known_eight_hour_stock_from_both_age_pages():
    now = COHORT_START + 10000
    client = Client(
        batch_pipeline_prod_jobs=entries(
            [
                {'state': 'record_pending', 'enqueued_at': now - 8 * 3600},
                {'state': 'record_pending', 'enqueued_at': now - 7201},
            ]
        ),
        sync_reprocess_outbox=entries(
            [
                {'summary_lane': 'fresh', 'first_pending_at': now - 8 * 3600, 'due_at': now},
                {'summary_lane': 'fresh', 'first_pending_at': now - 3601, 'due_at': now},
            ]
        ),
    )
    assert queries.record_pending(client, 'batch_pipeline_prod', now)['record_pending'] == (7201, 2, False)
    assert queries.enrichment(client, now)['fresh'] == (3601, 1, False)


def test_completed_receipts_cannot_fill_enrichment_active_page():
    now = COHORT_START + 10000
    receipts = [{'first_pending_at': now - 8000, 'due_at': None, 'dormant': True} for _ in range(1000)]
    active = {'first_pending_at': now - 4000, 'due_at': now, 'summary_lane': 'fresh'}
    client = Client(sync_reprocess_outbox=entries([*receipts, active]))
    assert queries.enrichment(client, now)['fresh'] == (4000, 1, False)


def test_enrichment_fresh_cohort_excludes_dormant_and_old_rows():
    now = COHORT_START + 20_000
    client = Client(
        sync_reprocess_outbox=entries(
            [
                {'first_pending_at': now - 4000, 'due_at': now - 3900, 'summary_lane': 'fresh'},
                {'first_pending_at': now - 4 * 86400, 'due_at': now - 8000, 'summary_lane': 'fresh'},
                {'first_pending_at': now - 8000, 'due_at': None, 'dormant': True},
                {'first_pending_at': now - 5000, 'due_at': now - 4000, 'summary_lane': 'backfill'},
                {
                    'first_pending_at': now - 5001,
                    'due_at': now - 4000,
                    'summary_lane': 'backfill',
                    'first_summary_policy': {'first_summary_enabled': True},
                },
            ]
        )
    )
    assert queries.enrichment(client, now) == {'fresh': (5001, 2, False), 'backfill': (5000, 2, False)}


def test_byok_uses_state_entry_not_creation_and_ignores_unstamped_legacy():
    now = 2_000_000
    stamp = lambda age: datetime.fromtimestamp(now - age, tz=timezone.utc)
    client = Client(
        conversation_finalization_jobs=entries(
            [
                {'status': 'blocked_byok', 'created_at': stamp(13 * 86400)},
                {'status': 'blocked_byok', 'created_at': stamp(13 * 86400), 'blocked_byok_at': stamp(4 * 86400)},
                {'status': 'blocked_byok', 'blocked_byok_at': stamp(8 * 86400)},
                {'status': 'queued', 'blocked_byok_at': stamp(6 * 86400)},
            ]
        )
    )
    assert queries.blocked_byok(client, now) == {'blocked_byok': (4 * 86400, 1, False)}


def test_nojob_reports_only_allowlisted_kinds_and_excludes_registered_rows():
    from config.record_audio import record_identity

    path = 'users/synthetic-user/conversations/synthetic-conversation'
    row = {'status': 'completed', 'record_lane_owner': 'batch_live_v1', 'record_audio_closed': True}
    client = Client(conversations=[(path, row)])
    sample = queries.nojob(client, 'batch_pipeline_prod')
    assert sample['sealed_no_job'] == (0, 1, False)
    _, job = record_identity('synthetic-user', 'synthetic-conversation')
    client.rows['batch_pipeline_prod_jobs'] = [(f'batch_pipeline_prod_jobs/{job}', {})]
    assert queries.nojob(client, 'batch_pipeline_prod')['sealed_no_job'] == (0, 0, False)


def test_sampler_retains_previous_values_and_freshness_on_error(caplog):
    registry = CollectorRegistry()
    metrics = PhaseMetrics('synthetic_phase', ['state'], registry=registry)
    metrics.refresh(1000, lambda: {'sealed': (5, 1, False)})

    def fail():
        raise ValueError('private-user@example.invalid/AAAAAAAAAAAAAAAAAAAAAAAAAAAA/job-private')

    metrics.refresh(1300, fail)
    assert registry.get_sample_value('synthetic_phase_observed_at_seconds') == 1000
    assert registry.get_sample_value('synthetic_phase_new_oldest_age_seconds', {'state': 'sealed'}) == 5
    assert 'private' not in caplog.text
    assert 'AAAAAAAA' not in caplog.text
    assert 'private' not in generate_latest(registry).decode()
    metrics.refresh(1600, lambda: {'sealed': (0, 0, False)})
    assert registry.get_sample_value('synthetic_phase_observed_at_seconds') == 1600


def test_first_failed_sample_remains_never_observed_and_calls_are_throttled():
    registry = CollectorRegistry()
    metrics = PhaseMetrics('synthetic_phase', ['state'], registry=registry)
    calls = []

    def sample():
        calls.append(1)
        raise RuntimeError('unavailable')

    metrics.refresh(1000, sample)
    metrics.refresh(1100, sample)
    assert len(calls) == 1
    assert registry.get_sample_value('synthetic_phase_observed_at_seconds') == 0


def test_repair_stock_is_capped_and_excludes_settled_receipts():
    client = Client(
        sync_reprocess_outbox=entries(
            [
                *[{'summary_repair': True, 'due_at': 0} for _ in range(120)],
                {'summary_repair': True, 'due_at': None, 'dormant': True},
                {'summary_repair': False, 'due_at': 0},
            ]
        )
    )
    assert queries.enrichment_summary_repair(client) == {'all': (0, 101, True)}
    client = Client(
        sync_reprocess_outbox=entries(
            [
                {'summary_repair': True, 'due_at': None, 'dormant': True},
                {'summary_repair': False, 'due_at': 0},
            ]
        )
    )
    assert queries.enrichment_summary_repair(client) == {'all': (0, 0, False)}
