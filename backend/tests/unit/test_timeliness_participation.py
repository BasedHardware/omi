"""Bounded TIMELINESS_METRICS-only participation control (SCA-1649).

Covers the strict schema, the explicit plane binding, the 60s coalesced read
cache, cold start, read-failure retention, clock movement, expiry and the
elected-sampler gate. No network: the control read is replaced at its boundary.
"""

import datetime as dt
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from prometheus_client import CollectorRegistry

from database.batch_pipeline_store import FirestoreStore
from utils.batch_pipeline import metrics as metrics_module
from utils.batch_pipeline import timeliness_participation as participation
from utils.batch_pipeline.metrics import QueueMetrics

NOW = 1_800_000_000.0
MONO = 5_000.0


class _Snapshot:
    def __init__(self, data=None, *, exists=True, update_time=None):
        self._data = data
        self.exists = exists
        self.update_time = update_time

    def to_dict(self):
        return dict(self._data or {})


def _doc(**overrides):
    data = {
        'version': 1,
        'target_plane': 'prod-omi-backend',
        'created_at': dt.datetime.fromtimestamp(NOW - 10, dt.timezone.utc),
        'suppressed_until': dt.datetime.fromtimestamp(NOW + 600, dt.timezone.utc),
        'operation_id': 'sca1649-op-1',
    }
    data.update(overrides)
    return data


def _store(namespace='batch_pipeline_prod'):
    return SimpleNamespace(client=Mock(), namespace=namespace)


@pytest.fixture
def gke(monkeypatch):
    monkeypatch.setenv('KUBERNETES_SERVICE_HOST', '10.0.0.1')
    monkeypatch.setenv('POD_NAMESPACE', 'prod-omi-backend')
    for marker in participation.CLOUD_RUN_MARKERS:
        monkeypatch.delenv(marker, raising=False)
    return monkeypatch


# --- plane identity ---------------------------------------------------------------


def test_plane_identity_is_the_allowlisted_gke_plane(gke):
    assert participation.timeliness_plane('batch_pipeline_prod') == 'prod-omi-backend'


@pytest.mark.parametrize('marker', participation.CLOUD_RUN_MARKERS)
def test_cloud_run_markers_never_identify_the_gke_plane(gke, marker):
    gke.setenv(marker, 'backend-integration')
    assert participation.timeliness_plane('batch_pipeline_prod') is None


def test_missing_in_cluster_marker_is_unrecognized(gke):
    gke.delenv('KUBERNETES_SERVICE_HOST')
    assert participation.timeliness_plane('batch_pipeline_prod') is None


def test_mismatched_pod_namespace_is_unrecognized(gke):
    gke.setenv('POD_NAMESPACE', 'some-other-namespace')
    assert participation.timeliness_plane('batch_pipeline_prod') is None


def test_missing_pod_namespace_still_identifies_the_gke_plane(gke):
    # backend-listen does not inject POD_NAMESPACE; the in-cluster marker plus
    # the prod data namespace is the static binding.
    gke.delenv('POD_NAMESPACE')
    assert participation.timeliness_plane('batch_pipeline_prod') == 'prod-omi-backend'


@pytest.mark.parametrize('namespace', ['batch_pipeline_dev', 'batch_pipeline_test_x', 'synthetic'])
def test_non_prod_namespace_is_unrecognized(gke, namespace):
    assert participation.timeliness_plane(namespace) is None


# --- strict schema ----------------------------------------------------------------


@pytest.mark.parametrize(
    'overrides',
    [
        {'version': True},
        {'version': 2},
        {'version': '1'},
        {'target_plane': 'backend-integration'},
        {'target_plane': None},
        {'operation_id': ''},
        {'operation_id': 'x' * 129},
        {'operation_id': 7},
        {'created_at': NOW - 10},
        {'suppressed_until': 'later'},
        {'created_at': dt.datetime(2026, 1, 1)},
        {'suppressed_until': dt.datetime.fromtimestamp(NOW - 20, dt.timezone.utc)},
        {
            'created_at': dt.datetime.fromtimestamp(NOW - 10, dt.timezone.utc),
            'suppressed_until': dt.datetime.fromtimestamp(NOW + 1801, dt.timezone.utc),
        },
        {'created_at': dt.datetime.fromtimestamp(NOW + 61, dt.timezone.utc)},
    ],
)
def test_schema_refusals(overrides):
    with pytest.raises(participation.ParticipationInvalid):
        participation.parse_participation(_doc(**overrides), plane='prod-omi-backend', now_wall=NOW, now_monotonic=MONO)


def test_non_map_document_is_invalid():
    with pytest.raises(participation.ParticipationInvalid):
        participation.parse_participation([], plane='prod-omi-backend', now_wall=NOW, now_monotonic=MONO)


def test_valid_suppression_applies_only_to_its_target_plane():
    validated = participation.parse_participation(_doc(), plane='prod-omi-backend', now_wall=NOW, now_monotonic=MONO)
    assert validated is not None and validated.operation_id == 'sca1649-op-1'
    assert participation.parse_participation(_doc(), plane=None, now_wall=NOW, now_monotonic=MONO) is None


def test_expired_suppression_participates():
    expired = _doc(
        created_at=dt.datetime.fromtimestamp(NOW - 900, dt.timezone.utc),
        suppressed_until=dt.datetime.fromtimestamp(NOW - 1, dt.timezone.utc),
    )
    assert (
        participation.parse_participation(expired, plane='prod-omi-backend', now_wall=NOW, now_monotonic=MONO) is None
    )


def test_lifetime_is_bounded_even_with_a_rolled_back_wall_clock():
    # created_at is 60s in the future (allowed skew) and the window is 1800s, so
    # the monotonic deadline may not exceed the contract lifetime.
    doc = _doc(
        created_at=dt.datetime.fromtimestamp(NOW + 60, dt.timezone.utc),
        suppressed_until=dt.datetime.fromtimestamp(NOW + 1860, dt.timezone.utc),
    )
    validated = participation.parse_participation(doc, plane='prod-omi-backend', now_wall=NOW, now_monotonic=MONO)
    assert validated is not None
    assert validated.expires_monotonic - MONO <= participation.MAX_LIFETIME_SECONDS


# --- cache ------------------------------------------------------------------------


def test_cache_reads_once_per_sixty_seconds(monkeypatch):
    reads = []
    monkeypatch.setattr(participation, 'read_control', lambda store: reads.append(1) or _Snapshot(_doc()))
    cache = participation.ParticipationCache()
    store = _store()
    for offset in (0, 15, 30, 45, 59):
        assert cache.suppressed(store, plane='prod-omi-backend', now_wall=NOW + offset, now_monotonic=MONO + offset)
    assert len(reads) == 1
    assert cache.suppressed(store, plane='prod-omi-backend', now_wall=NOW + 60, now_monotonic=MONO + 60)
    assert len(reads) == 2


def test_absent_document_participates(monkeypatch):
    monkeypatch.setattr(participation, 'read_control', lambda store: _Snapshot(exists=False))
    cache = participation.ParticipationCache()
    assert not cache.suppressed(_store(), plane='prod-omi-backend', now_wall=NOW, now_monotonic=MONO)


def test_malformed_document_participates(monkeypatch):
    monkeypatch.setattr(participation, 'read_control', lambda store: _Snapshot(_doc(version=True)))
    cache = participation.ParticipationCache()
    assert not cache.suppressed(_store(), plane='prod-omi-backend', now_wall=NOW, now_monotonic=MONO)


def test_unknown_plane_never_reads(monkeypatch):
    reads = []
    monkeypatch.setattr(participation, 'read_control', lambda store: reads.append(1) or _Snapshot(_doc()))
    cache = participation.ParticipationCache()
    assert not cache.suppressed(_store(), plane=None, now_wall=NOW, now_monotonic=MONO)
    assert reads == []


def test_cold_start_read_failure_participates(monkeypatch):
    def boom(store):
        raise RuntimeError('synthetic')

    monkeypatch.setattr(participation, 'read_control', boom)
    cache = participation.ParticipationCache()
    assert not cache.suppressed(_store(), plane='prod-omi-backend', now_wall=NOW, now_monotonic=MONO)


def test_read_failure_retains_the_last_validated_operation_until_its_deadline(monkeypatch):
    responses = [_Snapshot(_doc())]

    def read(store):
        if responses:
            return responses.pop()
        raise RuntimeError('synthetic')

    monkeypatch.setattr(participation, 'read_control', read)
    cache = participation.ParticipationCache()
    store = _store()
    assert cache.suppressed(store, plane='prod-omi-backend', now_wall=NOW, now_monotonic=MONO)
    # 600s of remaining lifetime: the failure keeps suppression, never extends it.
    assert cache.suppressed(store, plane='prod-omi-backend', now_wall=NOW + 60, now_monotonic=MONO + 60)
    assert cache.suppressed(store, plane='prod-omi-backend', now_wall=NOW + 540, now_monotonic=MONO + 540)
    assert not cache.suppressed(store, plane='prod-omi-backend', now_wall=NOW + 601, now_monotonic=MONO + 601)


def test_same_operation_reread_does_not_extend_the_deadline(monkeypatch):
    responses = [_Snapshot(_doc()), _Snapshot(_doc())]
    monkeypatch.setattr(participation, 'read_control', lambda store: responses.pop(0))
    cache = participation.ParticipationCache()
    store = _store()
    assert cache.suppressed(store, plane='prod-omi-backend', now_wall=NOW, now_monotonic=MONO)
    assert cache.suppressed(store, plane='prod-omi-backend', now_wall=NOW + 60, now_monotonic=MONO + 60)
    # The reread would have produced a deadline 60s later; the earlier one wins.
    assert not cache.suppressed(store, plane='prod-omi-backend', now_wall=NOW + 601, now_monotonic=MONO + 601)


def test_same_operation_reread_after_monotonic_expiry_resumes_participation(monkeypatch):
    responses = [_Snapshot(_doc()), _Snapshot(_doc())]
    monkeypatch.setattr(participation, 'read_control', lambda store: responses.pop(0))
    cache = participation.ParticipationCache()
    store = _store()
    assert cache.suppressed(store, plane='prod-omi-backend', now_wall=NOW, now_monotonic=MONO)
    # The small wall-clock rollback keeps the document valid, but its clamped
    # deadline is already past on the monotonic clock.
    assert not cache.suppressed(store, plane='prod-omi-backend', now_wall=NOW - 30, now_monotonic=MONO + 601)


def test_control_read_disables_retries_and_has_a_bounded_timeout(monkeypatch):
    reference = Mock()
    snapshot = _Snapshot(_doc())
    reference.get.return_value = snapshot
    monkeypatch.setattr(participation, 'control_document', lambda store: reference)

    assert participation.read_control(_store()) is snapshot
    reference.get.assert_called_once_with(retry=None, timeout=participation.READ_TIMEOUT_SECONDS)


def test_wall_clock_rollback_does_not_extend_the_deadline(monkeypatch):
    responses = [_Snapshot(_doc()), _Snapshot(_doc())]
    monkeypatch.setattr(participation, 'read_control', lambda store: responses.pop(0))
    cache = participation.ParticipationCache()
    store = _store()
    assert cache.suppressed(store, plane='prod-omi-backend', now_wall=NOW, now_monotonic=MONO)
    # Wall clock jumps back 30s (inside the skew allowance): the reread would
    # compute a later deadline, and the earlier one must win.
    assert cache.suppressed(store, plane='prod-omi-backend', now_wall=NOW - 30, now_monotonic=MONO + 60)
    assert not cache.suppressed(store, plane='prod-omi-backend', now_wall=NOW - 30, now_monotonic=MONO + 601)


def test_large_wall_clock_rollback_expires_early_instead_of_extending(monkeypatch):
    responses = [_Snapshot(_doc()), _Snapshot(_doc())]
    monkeypatch.setattr(participation, 'read_control', lambda store: responses.pop(0))
    cache = participation.ParticipationCache()
    store = _store()
    assert cache.suppressed(store, plane='prod-omi-backend', now_wall=NOW, now_monotonic=MONO)
    # A 300s rollback makes created_at look 290s future-dated, beyond the 60s
    # allowance: the document is refused and participation resumes. Fail-safe
    # direction only; suppression is never stretched.
    assert not cache.suppressed(store, plane='prod-omi-backend', now_wall=NOW - 300, now_monotonic=MONO + 60)


def test_forward_clock_movement_expires_early(monkeypatch):
    responses = [_Snapshot(_doc()), _Snapshot(_doc())]
    monkeypatch.setattr(participation, 'read_control', lambda store: responses.pop(0))
    cache = participation.ParticipationCache()
    store = _store()
    assert cache.suppressed(store, plane='prod-omi-backend', now_wall=NOW, now_monotonic=MONO)
    # Wall clock jumps past suppressed_until: the reread expires the suppression.
    assert not cache.suppressed(store, plane='prod-omi-backend', now_wall=NOW + 700, now_monotonic=MONO + 60)


# --- observed expiry is monotonic history, not a discarded fact -------------------


def test_expiry_then_wall_clock_rollback_does_not_revive_the_operation(monkeypatch):
    """An operation observed expired must not come back under a rolled-back clock."""
    responses = [_Snapshot(_doc()), _Snapshot(_doc()), _Snapshot(_doc())]
    monkeypatch.setattr(participation, 'read_control', lambda store: responses.pop(0))
    cache = participation.ParticipationCache()
    store = _store()
    assert cache.suppressed(store, plane='prod-omi-backend', now_wall=NOW, now_monotonic=MONO)
    # The reread sees the wall clock past suppressed_until: the operation ended.
    assert not cache.suppressed(store, plane='prod-omi-backend', now_wall=NOW + 700, now_monotonic=MONO + 60)
    assert cache.operation_id is None
    assert cache.ended_operations == ('sca1649-op-1',)
    # The clock rolls back inside the same window and the document parses as
    # active again. The operation already ended here, so it stays ended.
    assert not cache.suppressed(store, plane='prod-omi-backend', now_wall=NOW, now_monotonic=MONO + 120)
    assert cache.operation_id is None


def test_expiry_on_the_monotonic_clock_wins_over_a_live_wall_clock(monkeypatch):
    """The monotonic deadline is authoritative even when the document looks live."""
    monkeypatch.setattr(participation, 'read_control', lambda store: _Snapshot(_doc()))
    cache = participation.ParticipationCache()
    store = _store()
    assert cache.suppressed(store, plane='prod-omi-backend', now_wall=NOW, now_monotonic=MONO)
    # No read reservation is due, but the monotonic window has passed.
    assert not cache.suppressed(store, plane='prod-omi-backend', now_wall=NOW, now_monotonic=MONO + 700)
    assert cache.ended_operations == ('sca1649-op-1',)
    # A fresh read of the same still-live document cannot reopen it.
    assert not cache.suppressed(store, plane='prod-omi-backend', now_wall=NOW, now_monotonic=MONO + 760)


def test_a_displaced_operation_cannot_return(monkeypatch):
    responses = [_Snapshot(_doc()), _Snapshot(_doc(operation_id='sca1649-op-2')), _Snapshot(_doc())]
    monkeypatch.setattr(participation, 'read_control', lambda store: responses.pop(0))
    cache = participation.ParticipationCache()
    store = _store()
    assert cache.suppressed(store, plane='prod-omi-backend', now_wall=NOW, now_monotonic=MONO)
    assert cache.suppressed(store, plane='prod-omi-backend', now_wall=NOW, now_monotonic=MONO + 60)
    assert cache.operation_id == 'sca1649-op-2'
    assert cache.ended_operations == ('sca1649-op-1',)
    # op-1 reappears; it ended when op-2 displaced it.
    assert not cache.suppressed(store, plane='prod-omi-backend', now_wall=NOW, now_monotonic=MONO + 120)


def test_a_new_operation_after_expiry_still_suppresses(monkeypatch):
    later = _doc(
        operation_id='sca1649-op-2',
        created_at=dt.datetime.fromtimestamp(NOW + 690, dt.timezone.utc),
        suppressed_until=dt.datetime.fromtimestamp(NOW + 1290, dt.timezone.utc),
    )
    responses = [_Snapshot(_doc()), _Snapshot(_doc()), _Snapshot(later)]
    monkeypatch.setattr(participation, 'read_control', lambda store: responses.pop(0))
    cache = participation.ParticipationCache()
    store = _store()
    assert cache.suppressed(store, plane='prod-omi-backend', now_wall=NOW, now_monotonic=MONO)
    assert not cache.suppressed(store, plane='prod-omi-backend', now_wall=NOW + 700, now_monotonic=MONO + 60)
    assert cache.suppressed(store, plane='prod-omi-backend', now_wall=NOW + 700, now_monotonic=MONO + 120)
    assert cache.operation_id == 'sca1649-op-2'


def test_ended_operation_history_is_bounded():
    cache = participation.ParticipationCache()
    for index in range(participation.MAX_ENDED_OPERATIONS + 5):
        cache._remember_ended(f'op-{index}')
    assert len(cache.ended_operations) == participation.MAX_ENDED_OPERATIONS
    assert cache.ended_operations[0] == 'op-5'


# --- shared fallback telemetry ----------------------------------------------------


def test_read_failure_records_the_shared_fallback(monkeypatch):
    calls = []
    monkeypatch.setattr(participation, 'emit_fallback', lambda **kwargs: calls.append(kwargs))

    def boom(store):
        raise TimeoutError('synthetic')

    monkeypatch.setattr(participation, 'read_control', boom)
    cache = participation.ParticipationCache()
    assert not cache.suppressed(_store(), plane='prod-omi-backend', now_wall=NOW, now_monotonic=MONO)
    assert len(calls) == 1
    assert calls[0]['component'] == 'firestore_read'
    assert calls[0]['from_mode'] == 'control'
    assert calls[0]['to_mode'] == 'last_validated'
    assert calls[0]['reason'] == 'timeout'
    assert calls[0]['outcome'] == 'degraded'


def test_malformed_document_records_the_shared_fallback(monkeypatch):
    calls = []
    monkeypatch.setattr(participation, 'emit_fallback', lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(participation, 'read_control', lambda store: _Snapshot(_doc(version=True)))
    cache = participation.ParticipationCache()
    assert not cache.suppressed(_store(), plane='prod-omi-backend', now_wall=NOW, now_monotonic=MONO)
    assert [(call['to_mode'], call['outcome']) for call in calls] == [('participate', 'degraded')]


def test_healthy_reads_record_no_fallback(monkeypatch):
    calls = []
    monkeypatch.setattr(participation, 'emit_fallback', lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(participation, 'read_control', lambda store: _Snapshot(_doc()))
    cache = participation.ParticipationCache()
    assert cache.suppressed(_store(), plane='prod-omi-backend', now_wall=NOW, now_monotonic=MONO)
    assert calls == []


def test_fallback_telemetry_is_bounded_by_the_read_interval(monkeypatch):
    calls = []
    monkeypatch.setattr(participation, 'emit_fallback', lambda **kwargs: calls.append(kwargs))

    def boom(store):
        raise RuntimeError('synthetic')

    monkeypatch.setattr(participation, 'read_control', boom)
    cache = participation.ParticipationCache()
    store = _store()
    for offset in (0, 15, 30, 45, 59):
        cache.suppressed(store, plane='prod-omi-backend', now_wall=NOW + offset, now_monotonic=MONO + offset)
    assert len(calls) == 1
    cache.suppressed(store, plane='prod-omi-backend', now_wall=NOW + 60, now_monotonic=MONO + 60)
    assert len(calls) == 2


def test_outer_control_error_records_the_shared_fallback(monkeypatch):
    calls = []
    monkeypatch.setattr(participation, 'emit_fallback', lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(
        participation,
        'timeliness_plane',
        Mock(side_effect=RuntimeError('synthetic identity failure')),
    )
    sampler = QueueMetrics(CollectorRegistry())
    store = Mock(spec=FirestoreStore)
    store.namespace = 'batch_pipeline_prod'
    sampler.refresh_timeliness(store, NOW)
    assert len(calls) == 1
    assert calls[0]['component'] == 'firestore_read'
    assert calls[0]['to_mode'] == 'participate'
    assert calls[0]['outcome'] == 'degraded'
    assert sampler._participation_suppressed is False


# --- elected sampler gate ---------------------------------------------------------


def _sampler(monkeypatch, *, suppressed):
    registry = CollectorRegistry()
    sampler = QueueMetrics(registry)
    store = Mock(spec=FirestoreStore)
    store.namespace = 'batch_pipeline_prod'
    store.client = Mock()
    store.oldest.return_value = None
    store.oldest_retry.return_value = None
    store.ready_for_capacity.return_value = 0
    monkeypatch.setattr(sampler.record_pending, 'refresh', Mock())
    monkeypatch.setattr(sampler.nojob, 'refresh', Mock())
    monkeypatch.setattr(sampler, 'refresh_projection', Mock())
    monkeypatch.setattr(
        participation,
        'read_control',
        lambda store: _Snapshot(_doc()) if suppressed else _Snapshot(exists=False),
    )
    monkeypatch.setattr('utils.batch_pipeline.metrics.timeliness_sample', Mock(return_value=_sample()))
    monkeypatch.setattr('utils.batch_pipeline.metrics.allowance_held_count', Mock(return_value=0))
    monkeypatch.setattr('utils.batch_pipeline.metrics.record_wal_metrics', Mock())
    return sampler, store


def _sample():
    return {
        'staged_input_clock_invalid': 0,
        'drain_oldest': None,
        'held_oldest': {},
        'new_oldest': {},
        'new_over_sla': {},
        'backlog': {},
        'truncated': {},
    }


def test_suppression_withdraws_without_acquire_sample_or_companion_counts(gke, monkeypatch):
    sampler, store = _sampler(monkeypatch, suppressed=True)
    leader = Mock()
    leader.acquire.return_value = True
    sampler.timeliness_leader = leader
    sampler.refresh_timeliness(store, NOW)
    leader.acquire.assert_not_called()
    assert sampler._timeliness_visible is False
    assert sampler._timeliness_due == NOW + min(600.0, 60.0)
    metrics_module.timeliness_sample.assert_not_called()
    metrics_module.allowance_held_count.assert_not_called()
    metrics_module.record_wal_metrics.deactivate.assert_called()


def test_participation_samples_normally(gke, monkeypatch):
    sampler, store = _sampler(monkeypatch, suppressed=False)
    leader = Mock()
    leader.acquire.return_value = True
    sampler.timeliness_leader = leader
    sampler.refresh_timeliness(store, NOW)
    leader.acquire.assert_called_once()
    metrics_module.timeliness_sample.assert_called_once()
    assert sampler._timeliness_visible is True


def test_suppression_keeps_other_callbacks_advancing(gke, monkeypatch):
    sampler, store = _sampler(monkeypatch, suppressed=True)
    sampler.timeliness_leader = Mock()
    sampler.refresh(store, NOW)
    sampler.record_pending.refresh.assert_called_once()
    sampler.nojob.refresh.assert_called_once()
    sampler.refresh_projection.assert_called_once()


def test_alarm_disabled_skips_the_control_transport(monkeypatch):
    monkeypatch.setenv('BATCH_TIMELINESS_ALARM_ENABLED', 'false')
    reads = []
    monkeypatch.setattr(participation, 'read_control', lambda store: reads.append(1) or _Snapshot(_doc()))
    sampler = QueueMetrics(CollectorRegistry())
    store = Mock(spec=FirestoreStore)
    store.namespace = 'batch_pipeline_prod'
    sampler.refresh_timeliness(store, NOW)
    assert reads == []


def test_election_disabled_skips_the_control_transport(monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', 'batch_timeliness_leader=0')
    reads = []
    monkeypatch.setattr(participation, 'read_control', lambda store: reads.append(1) or _Snapshot(_doc()))
    sampler = QueueMetrics(CollectorRegistry())
    store = Mock(spec=FirestoreStore)
    store.namespace = 'batch_pipeline_prod'
    sampler.refresh_timeliness(store, NOW)
    assert reads == []


def test_control_read_failure_never_fails_the_sampler(gke, monkeypatch):
    def boom(store):
        raise RuntimeError('synthetic')

    monkeypatch.setattr(participation, 'read_control', boom)
    sampler = QueueMetrics(CollectorRegistry())
    store = Mock(spec=FirestoreStore)
    store.namespace = 'batch_pipeline_prod'
    store.client = Mock()
    monkeypatch.setattr('utils.batch_pipeline.metrics.timeliness_sample', Mock(return_value=_sample()))
    monkeypatch.setattr('utils.batch_pipeline.metrics.record_wal_metrics', Mock())
    sampler.refresh_timeliness(store, NOW)
    assert sampler._participation_suppressed is False
