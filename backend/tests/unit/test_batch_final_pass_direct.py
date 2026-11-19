"""Serving attempts and speaker-only wakes share one fenced obligation."""

import threading
from copy import deepcopy

import pytest
from google.api_core.exceptions import ServiceUnavailable

from database.batch_final_pass_retry import DIRECT_LEASE_SECONDS, MAX_ATTEMPTS
from tests.unit.fixtures.speaker_final_pass_retry import retry_state  # noqa: F401
from tests.unit.test_batch_final_pass import UID, batch_outcome_counts, prod_shaped  # noqa: F401
from tests.unit.test_batch_final_pass_retry import ready, next_wake  # noqa: F401
from utils.conversations import final_pass_batch as batch, final_pass_retry as retry, processing_speakers


@pytest.fixture
def direct(ready, monkeypatch):
    from utils.conversations import speaker_resolution as stage

    monkeypatch.setenv('CONVERSATION_SPEAKER_RESOLUTION_ENABLED', 'true')
    monkeypatch.setattr(stage, '_resolve', lambda *a, **kw: None)
    monkeypatch.setattr(stage.speaker_evidence, 'begin', lambda *a: None)
    monkeypatch.setattr(stage.speaker_evidence, 'finish', lambda *a: None)
    callbacks = []

    def run():
        assert processing_speakers.resolve_speakers_for_processing(
            UID, ready.lane.conversation, on_persist=callbacks.append
        )

    ready.run, ready.callbacks = run, callbacks
    return ready


def test_successful_direct_replay_before_old_wake_counts_once_without_rediarization(direct, monkeypatch):
    slot = threading.BoundedSemaphore(1)
    monkeypatch.setattr(batch, '_SLOTS', slot)
    before = batch_outcome_counts()
    assert slot.acquire()
    try:
        direct.run()
    finally:
        slot.release()
    key, row = next(iter(direct.state.rows.items()))
    old_token = row['token']
    assert row['attempts'] == 0 and row['due_at'] > direct.state.clock[0]
    assert len(direct.state.wakes) == 1 and not direct.lane.gpu
    direct.callbacks.pop()(True)  # The deferred attempt already released custody.

    direct.run()  # Before the queued wake is due.
    assert len(direct.lane.gpu) == 1
    assert direct.state.rows[key]['outcome'] is None
    assert batch_outcome_counts() == before  # Not terminal before canonical commit.
    assert retry.consume(key, old_token)['outcome'] == 'stale'  # Live direct lease.
    direct.callbacks[-1](True)
    direct.callbacks[-1](True)  # Duplicate persistence notification.
    assert direct.state.rows[key]['outcome'] == 'success'
    assert sum(batch_outcome_counts().values()) - sum(before.values()) == 1
    direct.state.clock[0] = row['due_at'] + 1
    assert retry.consume(key, old_token)['outcome'] == 'stale'
    labeled = deepcopy(direct.lane.conversation.transcript_segments)
    direct.run()  # A second enrichment delivery cannot reopen the receipt.
    assert direct.lane.conversation.transcript_segments == labeled
    assert len(direct.lane.gpu) == 1
    assert sum(batch_outcome_counts().values()) - sum(before.values()) == 1


def test_first_direct_success_has_durable_custody_and_no_local_terminal(direct):
    direct.run()
    key, row = next(iter(direct.state.rows.items()))
    assert row['attempts'] == 0 and row['lease_until'] == direct.state.clock[0] + DIRECT_LEASE_SECONDS
    assert not direct.state.store.terminal_counts()
    direct.callbacks[-1](True)
    assert direct.state.rows[key]['outcome'] == 'success'
    assert sum(c.get('success', 0) for c in direct.state.store.terminal_counts().values()) == 1


def test_failed_canonical_write_defers_without_counting_success(direct):
    before = batch_outcome_counts()
    direct.run()
    direct.callbacks[-1](False)
    assert batch_outcome_counts() == before
    key, token = next_wake(direct.state)
    assert retry.consume(key, token)['outcome'] == 'success'
    assert sum(batch_outcome_counts().values()) - sum(before.values()) == 1
    assert len(direct.writes) == 1


def test_duplicate_direct_during_canonical_persist_cannot_start_another_pass(direct):
    direct.run()
    direct.run()
    assert len(direct.callbacks) == 1 and len(direct.lane.gpu) == 1
    direct.callbacks[0](True)


def test_direct_admission_outage_does_not_ack_without_custody(direct, monkeypatch):
    monkeypatch.setattr(
        direct.state.store, 'start_direct', lambda *a, **kw: (_ for _ in ()).throw(ServiceUnavailable('synthetic'))
    )
    with pytest.raises(ServiceUnavailable):
        direct.run()
    assert not direct.lane.gpu and not direct.callbacks and not direct.state.rows


def test_ambiguous_direct_settlement_is_repaired_without_full_enrichment(direct, monkeypatch):
    settle = direct.state.store.settle

    def lost_reply(*a, **kw):
        settle(*a, **kw)
        raise ServiceUnavailable('synthetic')

    monkeypatch.setattr(direct.state.store, 'settle', lost_reply)
    before = batch_outcome_counts()
    direct.run()
    direct.callbacks[-1](True)  # Does not throw after canonical persistence.
    key, row = next(iter(direct.state.rows.items()))
    assert row['terminal_pending'] and batch_outcome_counts() == before
    direct.state.clock[0] = row['repair_after'] + 1
    assert retry.sweep(now=direct.state.clock[0]) == 1
    key, token = next_wake(direct.state)
    assert retry.consume(key, token)['outcome'] == 'success'
    assert retry.consume(key, token)['outcome'] == 'stale'
    assert len(direct.lane.gpu) == 1
    assert sum(batch_outcome_counts().values()) - sum(before.values()) == 1


def test_direct_replays_cannot_bypass_shared_attempt_cap(direct, monkeypatch):
    slot = threading.BoundedSemaphore(1)
    monkeypatch.setattr(batch, '_SLOTS', slot)
    before = batch_outcome_counts()
    assert slot.acquire()
    try:
        for _ in range(MAX_ATTEMPTS + 2):
            direct.run()
    finally:
        slot.release()
    row = next(iter(direct.state.rows.values()))
    assert row['attempts'] == MAX_ATTEMPTS and row['outcome'] == 'skipped_slot_exhausted'
    assert sum(batch_outcome_counts().values()) - sum(before.values()) == 1
    assert not direct.lane.gpu


def test_rollback_never_claims_or_diarizes(direct, monkeypatch):
    monkeypatch.setenv('BATCH_FINAL_PASS_ENABLED', 'false')
    direct.run()
    assert not direct.state.rows and not direct.callbacks and not direct.lane.gpu


def test_disabled_resolver_does_not_schedule_work_via_managed_boundary(direct, monkeypatch):
    monkeypatch.setenv('CONVERSATION_SPEAKER_RESOLUTION_ENABLED', 'false')
    direct.run()
    assert not direct.state.rows and not direct.callbacks and not direct.lane.gpu


def test_closed_obligation_still_reads_and_applies_manual_authority(direct, monkeypatch):
    from database import conversations
    from utils.conversations import speaker_resolution as stage

    direct.run()
    direct.callbacks[-1](True)
    receipt = {'segments': {'synthetic-manual-edit': {}}}
    applied = []
    monkeypatch.setattr(conversations, 'get_manual_speaker_receipt', lambda *a: receipt)

    def overlay(conversation, current):
        applied.append(current)
        conversation.transcript_segments[0].person_id = 'synthetic-manual-person'
        return True

    monkeypatch.setattr(stage, '_apply_receipt_overlay', overlay)
    monkeypatch.setattr(stage, '_resolve', lambda *a, **kw: pytest.fail('closed obligation reran automatic resolver'))
    monkeypatch.setattr(stage.speaker_evidence, 'finish', lambda *a: pytest.fail('closed obligation projected labels'))
    direct.run()
    assert applied and all(r == receipt for r in applied)
    assert direct.lane.conversation.transcript_segments[0].person_id == 'synthetic-manual-person'
    assert len(direct.lane.gpu) == 1
