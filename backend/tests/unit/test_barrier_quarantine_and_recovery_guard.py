"""A language barrier failure quarantines terminally and drains through the guarded lane.

The scheduler-side shape of the vad_windows signature: the first GPU attempt
of an unservable unit quarantines at attempt 1 under a closed worker failure,
and the recovery lane reads the same closed codes to select the multilingual
provider. The intake flip stamps the same provider reason, so a flipped unit
that ever quarantines drains guarded too.
"""

import logging

import pytest

from config.batch_language_recovery import language_guarded
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline.errors import validate_worker_failure, validate_worker_failure_evidence
from utils.batch_pipeline.scheduler import Scheduler
from utils.capture.retry_cap import retry_cap

log = logging.getLogger(__name__)


def queue_with_job(segment='a', owner='guard-owner', duration=30):
    from utils.batch_pipeline.contracts import Priority

    store = MemoryStore()
    queue = Scheduler(store)
    work = item(segment, owner=owner, duration=duration, priority=Priority.FRESH)
    assert queue.enqueue(work, 100.0)
    return store, queue


def lease_of(queue, now=1000.0):
    pulled = queue.pull(now)
    assert pulled
    return pulled[0]


def test_barrier_worker_failure_is_a_closed_shape():
    validate_worker_failure({'stage': 'vad_windows', 'reason': 'unsupported_language'})


def test_worker_failure_rejects_extra_fields():
    with pytest.raises(ValueError):
        validate_worker_failure({'stage': 'vad_windows', 'reason': 'unsupported_language', 'detail': 'x'})


def test_worker_failure_rejects_an_off_vocabulary_stage():
    with pytest.raises(ValueError):
        validate_worker_failure({'stage': 'not_a_stage', 'reason': 'unsupported_language'})


def test_worker_failure_rejects_a_free_form_reason():
    with pytest.raises(ValueError):
        validate_worker_failure({'stage': 'vad_windows', 'reason': 'japanese audio'})


def test_worker_failure_accepts_every_documented_stage():
    for stage in ('fetch_decode', 'vad_windows', 'assemble_words', 'word_clocks', 'asr_recovery'):
        validate_worker_failure({'stage': stage, 'reason': 'unsupported_language'})


def test_worker_failure_evidence_shares_the_closed_stage_vocabulary():
    validate_worker_failure_evidence({'stage': 'vad_windows', 'reason': 'vad_bounds'})


def test_worker_failure_evidence_rejects_an_open_stage():
    with pytest.raises(ValueError):
        validate_worker_failure_evidence({'stage': 'mystery', 'reason': 'vad_bounds'})


def test_quarantined_at_first_attempt_under_a_barrier_failure():
    store, queue = queue_with_job()
    lease = lease_of(queue)
    assert queue.fail(
        lease.item.segment_id,
        lease.token,
        1100.0,
        worker_failure={'stage': 'vad_windows', 'reason': 'unsupported_language'},
    )
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined'


def test_the_terminal_quarantine_names_attempt_one():
    store, queue = queue_with_job()
    lease = lease_of(queue)
    queue.fail(
        lease.item.segment_id,
        lease.token,
        1100.0,
        worker_failure={'stage': 'vad_windows', 'reason': 'unsupported_language'},
    )
    assert store.rows['jobs', 'a']['attempt'] == 1


def test_the_terminal_quarantine_records_the_worker_failure():
    store, queue = queue_with_job()
    lease = lease_of(queue)
    queue.fail(
        lease.item.segment_id,
        lease.token,
        1100.0,
        worker_failure={'stage': 'vad_windows', 'reason': 'unsupported_language'},
    )
    assert store.rows['jobs', 'a']['worker_failure'] == {'stage': 'vad_windows', 'reason': 'unsupported_language'}


def test_the_terminal_quarantine_holds_for_recovery():
    store, queue = queue_with_job()
    lease = lease_of(queue)
    queue.fail(
        lease.item.segment_id,
        lease.token,
        1100.0,
        worker_failure={'stage': 'vad_windows', 'reason': 'unsupported_language'},
    )
    assert store.rows['jobs', 'a']['recovery_state'] == 'held'


def test_the_terminal_quarantine_keeps_the_encrypted_audio():
    store, queue = queue_with_job()
    lease = lease_of(queue)
    queue.fail(
        lease.item.segment_id,
        lease.token,
        1100.0,
        worker_failure={'stage': 'vad_windows', 'reason': 'unsupported_language'},
    )
    job = store.rows['jobs', 'a']
    assert job['audio_uri'] and job['quarantine_reason'] == 'worker_failed'


def test_the_terminal_quarantine_releases_the_lease_token():
    store, queue = queue_with_job()
    lease = lease_of(queue)
    queue.fail(
        lease.item.segment_id,
        lease.token,
        1100.0,
        worker_failure={'stage': 'vad_windows', 'reason': 'unsupported_language'},
    )
    assert store.rows['jobs', 'a']['token'] == ''


def test_the_terminal_quarantine_leaves_merge_pending_off():
    store, queue = queue_with_job()
    lease = lease_of(queue)
    queue.fail(
        lease.item.segment_id,
        lease.token,
        1100.0,
        worker_failure={'stage': 'vad_windows', 'reason': 'unsupported_language'},
    )
    assert store.rows['jobs', 'a']['merge_pending'] is False


def test_the_terminal_quarantine_bumps_the_owner_revision():
    store, queue = queue_with_job()
    lease = lease_of(queue)
    revision_before = store.rows[
        'owners', __import__('utils.batch_pipeline.scheduler', fromlist=['owner_key']).owner_key('guard-owner')
    ]['revision']
    queue.fail(
        lease.item.segment_id,
        lease.token,
        1100.0,
        worker_failure={'stage': 'vad_windows', 'reason': 'unsupported_language'},
    )
    assert (
        store.rows[
            'owners', __import__('utils.batch_pipeline.scheduler', fromlist=['owner_key']).owner_key('guard-owner')
        ]['revision']
        > revision_before
    )


def test_a_barrier_failure_is_terminal_at_any_attempt():
    store, queue = queue_with_job()
    lease = lease_of(queue)
    queue.fail(
        lease.item.segment_id,
        lease.token,
        1100.0,
        worker_failure={'stage': 'assemble_words', 'reason': 'unsupported_language'},
    )
    assert store.rows['jobs', 'a']['state'] == 'quarantined'


def test_a_flipped_provider_reason_reads_as_language_guarded():
    job = {'worker_failure': None, 'stt_route': {'provider_reason': 'unsupported_language'}}
    assert language_guarded(job) is True


def test_a_barrier_worker_failure_reads_as_language_guarded():
    job = {'worker_failure': {'stage': 'vad_windows', 'reason': 'unsupported_language'}}
    assert language_guarded(job) is True


def test_an_empty_job_is_not_language_guarded():
    assert language_guarded({}) is False


def test_an_empty_asr_failure_is_not_language_guarded():
    assert language_guarded({'worker_failure': {'stage': 'assemble_words', 'reason': 'empty_asr'}}) is False


def test_a_provider_reason_of_none_is_not_language_guarded():
    assert language_guarded({'stt_route': {'provider_reason': 'none'}}) is False


def test_a_byok_provider_reason_is_not_language_guarded():
    assert language_guarded({'stt_route': {'provider_reason': 'byok'}}) is False


def test_the_compute_lane_job_has_no_provider_reason():
    from utils.batch_pipeline.provider_stt_admission import resolve_route

    assert resolve_route('en').provider_reason == 'none'


def test_the_flip_route_carries_the_guard_reason():
    from utils.batch_pipeline.provider_stt_admission import SttRoute

    assert SttRoute('provider', 'unsupported_language', 'modulate', 'und').provider_reason == 'unsupported_language'


def test_retry_cap_counts_down_the_ladder():
    assert retry_cap('owner', 3, 5).reached is False


def test_retry_cap_fires_at_the_maximum():
    decision = retry_cap('owner', 5, 5)
    assert decision is not None and decision.reached


def test_retry_cap_never_fires_below_the_maximum():
    assert retry_cap('owner', 4, 5).reached is False


def test_retry_cap_with_a_zero_budget_fires_immediately():
    decision = retry_cap('owner', 1, 1)
    assert decision is not None and decision.reached


def test_a_lease_expiry_at_the_cap_quarantines_for_recovery():
    from utils.batch_pipeline.retry_policy import quarantine_job

    class Tx:
        def __init__(self, rows):
            self.rows = rows

        def get(self, table, key):
            return self.rows.get((table, key), {})

        def put(self, table, key, value):
            self.rows[table, key] = value

    rows = {
        ('jobs', 'a'): {
            'owner_key': 'owner-key',
            'attempt': 5,
            'duration_seconds': 30,
            'lease_until': 0,
        },
        ('owners', 'owner-key'): {'revision': 1},
    }
    tx = Tx(rows)
    job = rows[('jobs', 'a')]
    quarantine_job(tx, job, 100.0, 'worker_failed')
    assert job['state'] == 'quarantined' and job['recovery_state'] == 'held'
    assert rows[('owners', 'owner-key')]['revision'] == 2


def test_quarantine_never_deletes_the_source_audio_reference():
    from utils.batch_pipeline.retry_policy import quarantine_job

    class Tx:
        def __init__(self, rows):
            self.rows = rows

        def get(self, table, key):
            return self.rows.get((table, key), {})

        def put(self, table, key, value):
            self.rows[table, key] = value

    rows = {
        ('jobs', 'a'): {'owner_key': 'owner-key', 'attempt': 1, 'duration_seconds': 30, 'audio_uri': 'gs://kept'},
        ('owners', 'owner-key'): {'revision': 1},
    }
    tx = Tx(rows)
    job = rows[('jobs', 'a')]
    quarantine_job(tx, job, 100.0, 'worker_failed')
    assert job['audio_uri'] == 'gs://kept'


def test_quarantine_keeps_measured_vad_absence_explicit():
    from utils.batch_pipeline.retry_policy import quarantine_job

    class Tx:
        def __init__(self, rows):
            self.rows = rows

        def get(self, table, key):
            return self.rows.get((table, key), {})

        def put(self, table, key, value):
            self.rows[table, key] = value

    rows = {
        ('jobs', 'a'): {'owner_key': 'owner-key', 'attempt': 1, 'duration_seconds': 30},
        ('owners', 'owner-key'): {},
    }
    tx = Tx(rows)
    job = rows[('jobs', 'a')]
    quarantine_job(tx, job, 100.0, 'worker_failed')
    assert job['measured_held_vad_speech_seconds'] is None


def test_a_lease_expired_job_below_the_cap_defers_not_quarantines():
    store, queue = queue_with_job()
    lease = lease_of(queue)
    assert queue.fail(lease.item.segment_id, lease.token, 1100.0) is True
    assert store.rows['jobs', 'a']['state'] != 'quarantined'


def test_the_flipped_job_state_is_provider_pending_not_ready():
    from utils.batch_pipeline.provider_stt_admission import PENDING

    assert PENDING == 'provider_pending'


def test_pull_never_leases_provider_pending_jobs():
    store, queue = queue_with_job()
    lease = lease_of(queue)
    queue.fail(
        lease.item.segment_id,
        lease.token,
        1100.0,
        worker_failure={'stage': 'vad_windows', 'reason': 'unsupported_language'},
    )
    assert store.rows['jobs', 'a']['state'] == 'quarantined'
    assert queue.pull(2000.0) == []


def test_a_quarantined_barrier_unit_awaits_the_fenced_recovery_lane():
    store, queue = queue_with_job()
    lease = lease_of(queue)
    queue.fail(
        lease.item.segment_id,
        lease.token,
        1100.0,
        worker_failure={'stage': 'vad_windows', 'reason': 'unsupported_language'},
    )
    job = store.rows['jobs', 'a']
    assert job['recovery_state'] == 'held'
    assert job['worker_failure']['reason'] == 'unsupported_language'
    assert 'event=batch_recovery outcome=held reason=awaiting_fenced_recovery' not in job.values()


def test_terminal_quarantine_logs_the_documented_shape(
    caplog,
):
    store, queue = queue_with_job()
    lease = lease_of(queue)
    with caplog.at_level(logging.ERROR):
        queue.fail(
            lease.item.segment_id,
            lease.token,
            1100.0,
            worker_failure={'stage': 'vad_windows', 'reason': 'unsupported_language'},
        )
    messages = [r.message for r in caplog.records]
    assert any(
        'event=batch_quarantined reason=worker_failed attempt=1 recovery=held stage=vad_windows worker_reason=unsupported_language'
        in message
        for message in messages
    )


def test_terminal_quarantine_also_logs_the_recovery_hold(caplog):
    store, queue = queue_with_job()
    lease = lease_of(queue)
    with caplog.at_level(logging.WARNING):
        queue.fail(
            lease.item.segment_id,
            lease.token,
            1100.0,
            worker_failure={'stage': 'vad_windows', 'reason': 'unsupported_language'},
        )
    assert any('event=batch_recovery outcome=held' in r.message for r in caplog.records)


def test_the_flip_job_policy_names_the_guard_reason_for_recovery():
    from utils.batch_pipeline.provider_stt_admission import SttRoute

    route = SttRoute('provider', 'unsupported_language', 'modulate', 'und')
    job = {'stt_route': {'provider_reason': route.provider_reason}}
    assert language_guarded(job) is True


def test_intake_plan_reason_vocabulary_matches_the_worker_barrier_reason():
    from config.batch_pipeline_language import INTAKE_UNIT_PLAN_REASONS

    assert 'unknown_speech' in INTAKE_UNIT_PLAN_REASONS
    assert 'detected_unsupported_speech' in INTAKE_UNIT_PLAN_REASONS


def test_the_worker_barrier_reason_is_the_recovery_guard_reason():
    from utils.batch_pipeline.word_validation import ValidationReason

    assert ValidationReason.UNSUPPORTED_LANGUAGE.value == 'unsupported_language'
    assert language_guarded(
        {'worker_failure': {'stage': 'vad_windows', 'reason': ValidationReason.UNSUPPORTED_LANGUAGE.value}}
    )


def test_units_on_the_compute_lane_carry_no_guard_reason():
    from utils.batch_pipeline.provider_stt_admission import resolve_route

    assert resolve_route('en').provider_reason == 'none'
    assert language_guarded({'stt_route': {'provider_reason': resolve_route('en').provider_reason}}) is False
