"""Delivery counters use terminal results, bounded labels and original behavior."""

from types import SimpleNamespace
import re
from pathlib import Path

import pytest
import yaml
from utils.observability import delivery


@pytest.fixture(scope='module', autouse=True)
def load_terminal_modules():
    # Load real boundary dependencies in setup, outside the call-only CPU guard.
    from utils import task_sync
    from utils.sync import pipeline
    from utils.conversations import summary_delivery

    assert task_sync and pipeline and summary_delivery


@pytest.fixture
def observed(monkeypatch):
    calls = []
    monkeypatch.setattr(delivery, 'record_delivery', lambda *args: calls.append(args))
    return calls


def test_untrusted_labels_are_rejected_before_child_creation(monkeypatch):
    assert delivery.OUTCOMES == frozenset({'delivered', 'no_op', 'deferred', 'failed'})
    calls = []
    monkeypatch.setattr(
        delivery,
        'DELIVERY_OUTCOME',
        SimpleNamespace(labels=lambda **labels: SimpleNamespace(inc=lambda count: calls.append((labels, count)))),
    )
    for unsafe in ('X' * 28, 'person@example.invalid', '/conversations/private/job', 'unknown'):
        delivery.record_delivery(unsafe, 'no_op')
        delivery.record_delivery('summary', unsafe)
    assert calls == []
    delivery.record_delivery('summary', 'delivered')
    assert calls == [(dict(kind='summary', outcome='delivered'), 1)]


@pytest.mark.parametrize(
    'patch,existing,expected',
    [
        ({}, {}, 'delivered'),
        ({}, {'summary_completed_at': 1, 'structured': {'title': 'Same'}}, 'no_op'),
        ({}, {'structured': {'title': 'Same'}}, 'no_op'),
        ({'discarded': True}, {}, 'no_op'),
        ({'summary_output_present': False}, {}, 'deferred'),
        ({'deferred': True}, {}, 'deferred'),
        ({'processing_state': 'local_pending'}, {}, 'deferred'),
        ({'status': 'processing'}, {}, None),
    ],
)
def test_summary_classification_is_pure(patch, existing, expected):
    write = dict(status='completed', summary_output_present=True, structured={'title': 'Same'}, **{})
    write.update(patch)
    before = dict(write)
    assert delivery.summary_terminal_outcome(existing, write) == expected
    assert write == before


def test_summary_counter_is_independent_of_first_summary_protocol_gate(monkeypatch):
    write = dict(status='completed', structured={'title': 'Final', 'overview': 'Useful output'})
    assert delivery.summary_terminal_outcome({}, write) == 'delivered'
    assert 'summary_output_present' not in write


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'reason,expected',
    [
        ('no_default_integration', 'no_op'),
        ('integration_not_found', 'no_op'),
        ('integration_not_connected', 'no_op'),
        ('client_handles_sync', 'deferred'),
    ],
)
async def test_actual_action_export_noop_and_device_deferral(observed, monkeypatch, reason, expected):
    from utils import task_sync

    async def run(executor, function, *args):
        if function is task_sync.users_db.get_default_task_integration:
            return None if reason == 'no_default_integration' else 'apple_reminders'
        return None if reason == 'integration_not_found' else {'connected': reason != 'integration_not_connected'}

    monkeypatch.setattr(task_sync, 'run_blocking', run)
    result, _, _ = await task_sync.auto_sync_action_item_with_outcome(
        'synthetic', {'id': 'item'}, skip_apple_reminders=True
    )
    assert result['reason'] == reason
    assert observed == [('action_item_export', expected)]


@pytest.mark.asyncio
async def test_actual_batch_counts_each_terminal_once_and_keeps_results(observed, monkeypatch):
    from utils import task_sync

    async def run(executor, function, *args):
        return 'cloud' if function is task_sync.users_db.get_default_task_integration else {'connected': True}

    rows = [{'synced': True}, {'synced': True, 'reason': 'already_exported'}, {'synced': False, 'reason': 'lease_lost'}]
    # Keep provider results stable and observe that no extra calls are introduced.
    calls = []

    async def export(*args, **kwargs):
        result = rows[len(calls)]
        calls.append(args)
        return result

    monkeypatch.setattr(task_sync, 'run_blocking', run)
    monkeypatch.setattr(task_sync, '_sync_to_cloud_service', export)
    result = await task_sync.auto_sync_action_items_batch('synthetic', [{'id': str(i)} for i in range(3)])
    assert result == rows and len(calls) == 3
    assert observed == [('action_item_export', outcome) for outcome in ('delivered', 'no_op', 'deferred')]


@pytest.mark.asyncio
async def test_empty_batch_emits_nothing(observed):
    from utils import task_sync

    assert await task_sync.auto_sync_action_items_batch('synthetic', []) == []
    assert observed == []


@pytest.mark.asyncio
@pytest.mark.parametrize('result', [None, (), 'opaque'])
async def test_observation_preserves_unexpected_results_without_new_exceptions(observed, result):
    @delivery.observe_action_export
    async def terminal():
        return result

    assert await terminal() == result
    assert observed == [('action_item_export', 'failed')]


def test_actual_sync_missing_and_deleted_terminal_sites(observed, monkeypatch):
    from utils.sync import pipeline

    for row, outcome in ((None, 'deferred'), ({'deleted': True}, 'no_op')):
        monkeypatch.setattr(pipeline.conversations_db, 'get_conversation', lambda *args: row)
        pipeline._reprocess_conversation_after_update('synthetic', 'synthetic', 'en')
        assert observed[-1] == ('sync', outcome)


def test_sync_fence_is_deferred_and_original_error_survives(observed):
    from utils.conversations.summary_delivery import SummaryRepairSuperseded

    error = SummaryRepairSuperseded('synthetic')

    @delivery.observe_sync_failures
    def fenced():
        raise error

    with pytest.raises(SummaryRepairSuperseded) as caught:
        fenced()
    assert caught.value is error
    assert observed == [('sync', 'deferred')]


def test_action_item_revision_race_is_deferred_not_failed(observed):
    from database.action_item_refresh import RefreshRevisionChanged

    error = RefreshRevisionChanged()

    @delivery.observe_sync_failures
    def raced():
        raise error

    with pytest.raises(RefreshRevisionChanged) as caught:
        raced()
    assert caught.value is error
    assert observed == [('sync', 'deferred')]


def test_sync_decode_failure_has_one_failed_terminal(observed):
    error = ValueError('synthetic')

    def decode(row):
        raise error

    @delivery.observe_sync_failures
    def terminal():
        return delivery.sync_refreshed({'structured': {}}, decode, lambda value: True)

    with pytest.raises(ValueError) as caught:
        terminal()
    assert caught.value is error
    assert observed == [('sync', 'failed')]


def test_both_gmp_keep_lists_retain_delivery_and_cost_grade_metrics():
    root = Path(__file__).resolve().parents[2]
    required = (
        'omi_delivery_outcome_total',
        'omi_people_scan_dedupe_total',
        'omi_firestore_billed_reads_by_caller_total',
        'omi_firestore_billed_reads_by_origin_total',
        'omi_fsr_leader_lease_total',
    )
    for name in ('cloud_run_gmp_sidecar.yaml', 'cloud_run_gmp_sync.yaml'):
        config = yaml.safe_load((root / 'deploy' / name).read_text())
        rules = config['spec']['endpoints'][0]['metricRelabeling']
        keep = [row['regex'] for row in rules if row['action'] == 'keep' and row['sourceLabels'] == ['__name__']]
        assert keep
        assert all(any(re.fullmatch(pattern, metric) for pattern in keep) for metric in required)


def test_malformed_summary_observation_does_not_reject_a_write():
    write = dict(status='completed', structured={'sections': 7})
    assert delivery.summary_terminal_outcome({}, write) is None
    assert write == dict(status='completed', structured={'sections': 7})


def test_real_minimum_preparation_keeps_open_summary_debt_deferred(monkeypatch):
    from utils.conversations import summary_delivery

    write = dict(status='completed', structured={'title': 'Waiting', 'title_provenance': 'server_minimum'})
    summary_delivery.prepare(write, 'synthetic', now=100)
    assert write['summary_due_at'] > 100 and write['summary_output_present'] is False
    assert delivery.summary_terminal_outcome({}, write) == 'deferred'
    assert summary_delivery.creation_result(write, 'synthetic') is None


def test_intentionally_waived_short_clip_debt_is_not_pending(monkeypatch):
    from utils.conversations import summary_delivery

    write = dict(
        status='completed',
        structured={'title': 'Short capture', 'title_provenance': 'server_minimum'},
        relevance_decision={'verdict': 'keep', 'decided_by': 'rule', 'reason': 'content_below_floor'},
    )
    summary_delivery.prepare(write, 'synthetic', now=100)
    assert write['summary_due_at'] is None and write['summary_output_present'] is False
    assert delivery.summary_terminal_outcome({}, write) == 'no_op'


@pytest.mark.parametrize(
    'patch,expected',
    [
        ({'discarded': True}, 'no_op'),
        ({'discarded': True, 'deferred': True}, 'no_op'),
        ({'processing_deferred': True}, 'deferred'),
        ({'deferred': True}, 'deferred'),
        ({'terminal_no_derived_effects': True}, 'deferred'),
        ({'is_locked': True}, 'deferred'),
        ({'processing_state': 'local_pending'}, 'deferred'),
        ({}, 'delivered'),
        ({'structured': {'title': 'Waiting'}}, 'deferred'),
    ],
)
def test_sync_terminals_prioritize_discard_and_debt_without_changing_results(observed, patch, expected):
    from utils.conversations.summary_delivery import present

    row = dict(structured={'overview': 'Retained summary'}, **{})
    row.update(patch)
    result = SimpleNamespace(**row)
    assert delivery.sync_refreshed(row, lambda raw: result, present) is result
    assert delivery.sync_done(result) is result
    assert observed == [('sync', expected), ('sync', expected)]


@pytest.mark.asyncio
async def test_malformed_provider_reason_preserves_a_successful_result(observed):
    result = {'synced': True, 'reason': []}

    @delivery.observe_action_export
    async def terminal():
        return result

    assert await terminal() is result
    assert observed == [('action_item_export', 'delivered')]
