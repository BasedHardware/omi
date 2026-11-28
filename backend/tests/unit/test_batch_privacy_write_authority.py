"""Tokenless reuse only covers existing scheduling metadata and bounded proof lifetimes."""

from concurrent.futures import Future
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database import batch_privacy_write_audit as audit
from database import batch_privacy_write_cache as cache
from database.batch_pipeline_store import FirestoreTransaction
from database.batch_pipeline_transaction_labels import pull_operation
from database.batch_privacy_write_authority import _only_existing_leases, authorize_buffered_writes

SHARD = 'scheduler_00'


@pytest.fixture
def view():
    before = {
        ('jobs', 'segment'): {
            'segment_id': 'segment',
            'owner_id': 'owner',
            'owner_key': 'owner',
            'conversation_id': 'source',
            'priority': 0,
            'next': '',
            'state': 'ready',
            'requires_compute_admission': True,
            'privacy_generation': 7,
            'attempt': 0,
        },
        ('queues', '0_owner'): {'head': 'segment', 'tail': 'segment', 'continuing': True, 'deficit': 5},
        ('gpus', 'gpu'): {'token': '', 'released_token': 'old', 'lease_until': 0},
        ('control', SHARD): {'rings': {'0': ['0_owner']}, 'p0_active': True, 'p0_service': 10},
        ('pull_claims', SHARD): {'token': 'claimed', 'expires_at': 20},
    }
    after = {
        ('jobs', 'segment'): {
            **before['jobs', 'segment'],
            'state': 'leased',
            'attempt': 1,
            'lease_until': 100,
            'token': 'leased',
            'shared_gpu_key': 'gpu',
        },
        ('queues', '0_owner'): {'head': '', 'tail': '', 'continuing': False, 'deficit': 0},
        ('gpus', 'gpu'): {'segment_id': 'segment', 'token': 'leased', 'lease_until': 100},
        ('control', SHARD): {'rings': {'0': []}, 'p0_active': False, 'p0_service': 15},
        ('pull_claims', SHARD): {'token': '', 'expires_at': 0.0},
    }
    return SimpleNamespace(cache=before, exists=dict.fromkeys(before, True), writes=after, patches={}, external={})


def test_existing_lease_accepts_only_matching_scheduler_companions(view):
    with pull_operation('pull', SHARD):
        assert _only_existing_leases(view)
    assert not _only_existing_leases(view)


@pytest.mark.parametrize('table', ['jobs', 'queues', 'gpus', 'control', 'pull_claims'])
def test_missing_original_or_unrelated_field_requires_certification(view, table):
    address = next(address for address in view.writes if address[0] == table)
    with pull_operation('pull', SHARD):
        view.exists[address] = False
        assert not _only_existing_leases(view)
        view.exists[address] = True
        view.writes[address]['unrelated'] = None
        assert not _only_existing_leases(view)


@pytest.mark.parametrize(
    'address,change',
    [
        (('jobs', 'segment'), {'requires_compute_admission': False}),
        (('jobs', 'segment'), {'unit_kind': 'other'}),
        (('jobs', 'segment'), {'policy_parts': {'scheduler': {}}}),
        (('queues', '0_owner'), {'head': 'another-owner-job'}),
        (('gpus', 'gpu'), {'token': 'different-lease'}),
        (('control', SHARD), {'rings': {'0': ['another-queue']}}),
        (('control', SHARD), {'p0_service': 0}),
        (('pull_claims', SHARD), {'token': 'new'}),
    ],
)
def test_lease_companions_must_follow_the_scheduler_transition(view, address, change):
    view.writes[address].update(change)
    with pull_operation('pull', SHARD):
        assert not _only_existing_leases(view)


@pytest.mark.parametrize('generation,site', [(7, 'lease'), (8, None), (7.0, None)])
def test_lease_authorization_requires_unchanged_integer_privacy_generation(view, monkeypatch, generation, site):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"bpp_tokenless_write_cache":100}')
    view.writes['jobs', 'segment']['privacy_generation'] = generation
    view._check_privacy = Mock()
    with pull_operation('pull', SHARD):
        authorize_buffered_writes(view)
    view._check_privacy.assert_called_once_with(
        'owner', conversation_ids=('source',), expected_generation=generation, site=site
    )


def test_needs_job_lease_and_disallows_external_or_canonical_patches(view):
    with pull_operation('pull', SHARD):
        companions = deepcopy(view.writes)
        del companions['jobs', 'segment']
        transaction = SimpleNamespace(**{**vars(view), 'writes': companions})
        assert not _only_existing_leases(transaction)
        view.external['write'] = {}
        assert not _only_existing_leases(view)
        view.external.clear()
        view.patches['conversations', 'owner/source'] = {'record_lane_owner': 'batch'}
        assert not _only_existing_leases(view)


def test_expired_lease_is_recertified_before_flush(monkeypatch):
    transaction = FirestoreTransaction(Mock(), 'batch_pipeline_dev', Mock())
    decision = cache.Decision(0, ('token', 'revision', 0), 7)
    ids = frozenset({'source'})
    transaction._note_tokenless_hit('owner', ids, 'probe', decision)
    transaction._note_tokenless_hit('owner', ids, 'lease', decision)
    read = Mock()
    monkeypatch.setattr(transaction, '_check_certified_privacy', read)
    transaction.flush()
    read.assert_called_once_with('owner', ids, 7)
    assert [hit.site for hit in transaction.tokenless_hits] == ['probe']


def test_audit_saturation_is_not_an_evaluated_comparison(monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"bpp_tokenless_write_audit":100}')
    monkeypatch.setattr(audit.random, 'randrange', lambda _: 0)
    submit = Mock(side_effect=RuntimeError('synthetic executor saturation'))
    monkeypatch.setattr(audit.read_cache_shadow_executor, 'submit', submit)
    hit = audit.Hit('owner', frozenset({'source'}), 'lease', cache.Decision(audit.time.time(), ('token', 'rev', 0), 7))
    dropped = audit.INCOMPLETE.labels('lease', 'dropped')._value
    agree = audit.AUDIT.labels('lease', 'agree')._value
    before = dropped.get(), agree.get()
    audit.submit(object(), hit)
    submit.assert_called_once()
    assert (dropped.get(), agree.get()) == (before[0] + 1, before[1])


@pytest.mark.parametrize('site', ['probe', 'lease'])
def test_cancelled_audit_sample_is_counted_as_dropped(monkeypatch, site):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"bpp_tokenless_write_audit":100}')
    monkeypatch.setattr(audit.random, 'randrange', lambda _: 0)
    future = Future()
    submit = Mock(return_value=future)
    monkeypatch.setattr(audit.read_cache_shadow_executor, 'submit', submit)
    hit = audit.Hit('owner', frozenset({'source'}), site, cache.Decision(audit.time.time(), ('token', 'rev', 0), 7))
    dropped = audit.INCOMPLETE.labels(site, 'dropped')._value
    before = dropped.get()

    audit.submit(object(), hit)
    submit.assert_called_once()
    assert dropped.get() == before
    assert future.cancel()
    assert dropped.get() == before + 1


@pytest.mark.parametrize(
    'setting,draw,sampled',
    [(None, 0, False), (0, 0, False), (50, 49, True), (50, 50, False), (100, 99, True), (100, 100, False)],
)
def test_enforced_audit_sampling_defaults_off_with_configurable_sampling(monkeypatch, setting, draw, sampled):
    if setting is None:
        monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)
    else:
        monkeypatch.setenv('FIRESTORE_READ_LEVERS', f'{{"bpp_tokenless_write_audit":{setting}}}')
    monkeypatch.setattr(audit.random, 'randrange', lambda size: draw if size == 10_000 else pytest.fail('wrong range'))
    submit = Mock(return_value=Future())
    monkeypatch.setattr(audit.read_cache_shadow_executor, 'submit', submit)
    live = Mock()
    monkeypatch.setattr(audit, '_live_outcome', live)
    hit = audit.Hit('owner', frozenset({'source'}), 'lease', cache.Decision(audit.time.time(), ('token', 'rev', 0), 7))

    audit.submit(object(), hit)

    assert submit.call_count == int(sampled)
    live.assert_not_called()


@pytest.mark.parametrize(
    'worker,service,role',
    [
        ('', 'backend-integration', 'integration'),
        ('', 'backend-sync-backfill', 'sync'),
        ('', 'backend', 'backend'),
        ('true', '', 'worker'),
        ('', 'unrecognized-service', 'other'),
    ],
)
def test_write_audit_uses_bounded_role_labels(monkeypatch, worker, service, role):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_ENABLED', worker)
    monkeypatch.setenv('K_SERVICE', service)
    assert audit._deployment_role() == role


@pytest.mark.parametrize('outcome', [*audit.OUTCOMES, 'failed'])
def test_completed_write_audit_denominator_counts_each_evaluated_hit_once(monkeypatch, outcome):
    if outcome == 'failed':
        live = Mock(side_effect=RuntimeError('synthetic read failure'))
    else:
        live = Mock(return_value=outcome)
    monkeypatch.setattr(audit, '_live_outcome', live)
    monkeypatch.setattr(audit, '_ROLE', 'integration')
    hit = audit.Hit('owner', frozenset({'source'}), 'lease', cache.Decision(audit.time.time(), ('token', 'rev', 0), 7))
    counters = {label: audit.AUDIT_BY_ROLE.labels('integration', label)._value for label in audit.OUTCOMES}
    before = {label: counter.get() for label, counter in counters.items()}
    failed = audit.INCOMPLETE.labels('lease', 'failed')._value
    failed_before = failed.get()

    audit._run(object(), hit, object())

    assert {label: counter.get() - before[label] for label, counter in counters.items()} == {
        label: int(label == outcome) for label in audit.OUTCOMES
    }
    assert failed.get() - failed_before == int(outcome == 'failed')
