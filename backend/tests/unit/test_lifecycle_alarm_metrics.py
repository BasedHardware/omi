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
        # Aggregation caps may be large (billed per 1,000 index entries); stream() bounds document reads.
        assert 0 < cap <= 1_000_000
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


@pytest.mark.parametrize(
    'rows, expected',
    [
        ([], (0, 0, False)),
        (
            [
                {'state': 'record_pending', 'enqueued_at': 'NOW-7201'},
                {'state': 'record_pending', 'enqueued_at': 'NOW-3'},
            ],
            None,
        ),
        ([{'state': 'record_pending', 'enqueued_at': 'NOW-8000'}] * 999, None),
        ([{'state': 'record_pending', 'enqueued_at': 'NOW-8000'}] * 1000, None),
        ([{'state': 'record_pending', 'enqueued_at': 'NOW-8000'}] * 6000, None),
        (
            [
                {'state': 'record_pending', 'enqueued_at': 'NOW-259200'},
                {'state': 'record_pending', 'enqueued_at': 'NOW+50'},
            ],
            None,
        ),
    ],
)
def test_record_pending_head_lever_matches_the_full_page_with_one_document_read(monkeypatch, rows, expected):
    now = COHORT_START + 20_000
    resolved = [
        {**row, 'enqueued_at': now + int(row['enqueued_at'][3:])} if isinstance(row.get('enqueued_at'), str) else row
        for row in rows
    ]
    monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)
    legacy_client = Client(batch_pipeline_prod_jobs=entries(resolved))
    legacy = queries.record_pending(legacy_client, 'batch_pipeline_prod', now)
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"lifecycle_record_pending_head":100}')
    head_client = Client(batch_pipeline_prod_jobs=entries(resolved))
    head = queries.record_pending(head_client, 'batch_pipeline_prod', now)
    assert head == legacy
    if expected is not None:
        assert head == {'record_pending': expected}
    assert [read.cap for read in head_client.reads] == [1]


def test_record_pending_head_lever_cohorts_per_replica(monkeypatch):
    from config.firestore_read_levers import lever_enabled

    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"lifecycle_record_pending_head":50}')
    seen = set()
    for i in range(40):
        monkeypatch.setenv('HOSTNAME', f'backend-integration-{i}')
        seen.add(lever_enabled('lifecycle_record_pending_head', queries._replica_key('batch_pipeline_prod')))
    assert seen == {True, False}  # a percentage splits replicas instead of the whole fleet
    monkeypatch.delenv('HOSTNAME')
    monkeypatch.delenv('K_REVISION', raising=False)
    assert queries._replica_key('batch_pipeline_prod') == 'batch_pipeline_prod'


def test_vendor_held_counts_each_reason_and_the_oldest_age():
    from utils.observability.reasons import VendorHoldReason

    now = COHORT_START + 50_000
    client = Client(
        batch_pipeline_prod_jobs=entries(
            [
                {'state': 'vendor_held', 'vendor_hold.reason': 'funds_refusal', 'enqueued_at': now - 9000},
                {'state': 'vendor_held', 'vendor_hold.reason': 'funds_refusal', 'enqueued_at': now - 100},
                {'state': 'vendor_held', 'vendor_hold.reason': 'cap_reached', 'enqueued_at': now - 50},
                # A row with no recognised reason still counts, as unknown.
                {'state': 'vendor_held', 'enqueued_at': now - 10},
                {'state': 'provider_pending', 'vendor_hold.reason': 'funds_refusal', 'enqueued_at': now - 99_000},
            ]
        )
    )
    counts, age, truncated = queries.vendor_held(client, 'batch_pipeline_prod', now)
    assert counts[VendorHoldReason.FUNDS_REFUSAL] == 2
    assert counts[VendorHoldReason.CAP_REACHED] == 1
    assert counts[VendorHoldReason.UNKNOWN] == 1
    assert counts[VendorHoldReason.NO_HEALTHY_VENDOR] == 0
    assert set(counts) == set(VendorHoldReason)
    assert age == 9000 and truncated is False
    # One document read (the head); everything else is an aggregation.
    assert len(client.reads) == 1


def test_vendor_held_empty_stock_reads_zero_without_reason_counts():
    client = Client(batch_pipeline_prod_jobs=entries([{'state': 'ready', 'enqueued_at': 1.0}]))
    counts, age, truncated = queries.vendor_held(client, 'batch_pipeline_prod', COHORT_START + 10)
    assert set(counts.values()) == {0} and age == 0.0 and truncated is False


def test_provider_stage_stock_includes_old_rows_and_both_states():
    now = COHORT_START + 50_000
    client = Client(
        batch_pipeline_prod_jobs=entries(
            [
                # All epochs: a week-old pending row is exactly the stock the timeliness alarm leaves out.
                {'state': 'provider_pending', 'enqueued_at': now - 7 * 86400},
                {'state': 'provider_pending', 'enqueued_at': now - 60},
                {'state': 'provider_running', 'enqueued_at': now - 30},
                {'state': 'vendor_held', 'enqueued_at': now - 9 * 86400},
            ]
        )
    )
    assert queries.provider_stage(client, 'batch_pipeline_prod', now) == {
        'provider_pending': (2, 7 * 86400),
        'provider_running': (1, 30),
    }
    assert len(client.reads) == 2
