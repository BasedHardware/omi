"""Delivery must not buy notes while a recording's new upload is unresolved."""

from types import SimpleNamespace
from dataclasses import replace

from config.record_audio import require_record_audio_barrier
from database.batch_pipeline_intake import admit
from database import record_notes_hold
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from unittest.mock import Mock

import pytest

from database import pipeline_ledger, record_audio
from database.outbox_firestore import FirestoreEnrichmentOutbox
from tests.unit.test_record_complete_notes import recording, NOW, POLICY
from utils.conversations import demand_processing
from utils.enrichment import age_gate, callback, consumer
from utils.sync import processing_hold, reprocess
from utils.workers.consumer import run_push


@pytest.fixture(params=['consumer', 'legacy'])
def delivery(recording, monkeypatch, request):
    return make_delivery(recording, monkeypatch, request.param)


def make_delivery(recording, monkeypatch, adapter_kind):
    f = recording
    monkeypatch.setenv('DEMAND_PROCESSING_ENABLED', 'false')
    monkeypatch.setattr(age_gate, 'park_if_expired', lambda *a, **k: False)
    monkeypatch.setattr(demand_processing, 'admit', lambda *a, **k: True)
    adapter = FirestoreEnrichmentOutbox(f.client, privacy_blocked=lambda *_: False, create_wake=Mock())
    key = reprocess.key(f.binding.owner_id, 'capture')
    ref = f.client.collection(reprocess.COLLECTION).document(key)

    def mutate(row_id, operation):
        tx = f.client.transaction()
        row_ref = f.client.collection(reprocess.COLLECTION).document(row_id)
        old = row_ref.get(transaction=tx).to_dict()
        new, result = operation(old)
        if new != old:
            if new is None:
                tx.delete(row_ref)
            else:
                tx.set(row_ref, new)
        return result

    monkeypatch.setattr(adapter, '_mutate', mutate)
    monkeypatch.setattr(reprocess, '_mutate', mutate)
    monkeypatch.setattr(reprocess, '_enqueue', Mock())
    monkeypatch.setattr(reprocess, 'get_firestore_client', lambda: f.client)
    f.store.mark_enrichment('first', f.binding, NOW, 'capture', 'en', policy=POLICY)
    if ref.get().to_dict().get('record_notes_producers'):
        assert ref.get().to_dict()['record_notes_producers'] == {
            'capture': f.client.rows[f.store.ref('jobs', 'first').path].get('record_input_upload_revision')
        }
    clock = [NOW + 120]
    monkeypatch.setattr(consumer.time, 'time', lambda: clock[0])
    paid = Mock(return_value=SimpleNamespace(structured={'overview': 'Complete synthetic transcript'}))
    worker = consumer.EnrichmentConsumer(adapter, process=paid)

    def deliver(at):
        clock[0] = at
        token = ref.get().to_dict()['task_token']
        if adapter_kind == 'legacy':
            status = reprocess.run(key, token, worker._callback(), now=at)
            return SimpleNamespace(outcome='done' if status == 'processed' else status)
        return run_push(worker, adapter, key, token, now=at)

    return SimpleNamespace(**locals())


def reopen(d):
    assert record_audio.set_record_upload_pending(
        d.f.binding.owner_id, 'capture', 'late-producer', True, firestore_client=d.f.client
    )
    assert d.f.conversation.get().to_dict()['record_upload_revision'] == 2


def test_reopened_record_defers_until_new_revision_projects_then_runs_once(delivery):
    d = delivery
    # The producer registers before the seal. On an already sealed record the
    # lease instead re-arms a partial continuation, and notes wait at the hold
    # cap (test_never_cleared_producer_is_parked_at_existing_hold_cap...).
    d.f.client.rows[d.f.conversation.path]['record_audio_closed'] = False
    reopen(d)
    assert d.deliver(NOW + 120).outcome == 'deferred'
    assert d.ref.get().to_dict()['due_at'] == NOW + 240
    d.paid.assert_not_called()
    # A seal alone is insufficient: revision 2 audio has not projected yet.
    d.f.client.rows[d.f.conversation.path].update(record_upload_sessions={}, record_audio_closed=True)
    assert d.deliver(NOW + 240).outcome == 'deferred'
    d.paid.assert_not_called()
    # The new projection coalesces the same durable obligation, attesting revision 2.
    d.adapter.enqueue(
        d.key,
        d.f.binding.owner_id,
        {
            'conversation_id': 'capture',
            'language': 'en',
            'record_notes_producer': {'conversation_id': 'capture', 'revision': 2},
        },
        NOW + 360,
        now=NOW + 250,
        coalesce='min',
        snapshot_summary=True,
    )
    assert d.deliver(NOW + 360).outcome == 'done'
    d.paid.assert_called_once()
    assert d.ref.get().to_dict()['dormant']
    assert d.deliver(NOW + 361).outcome == 'stale'
    d.paid.assert_called_once()


def test_never_cleared_producer_is_parked_at_existing_hold_cap_and_ledger_records_timeout(delivery):
    d = delivery
    reopen(d)
    assert d.deliver(NOW + 120).outcome == 'deferred'
    maximum = NOW + processing_hold.MAX_HOLD_SECONDS
    assert d.deliver(maximum - 1).outcome == 'deferred'
    assert d.ref.get().to_dict()['due_at'] == maximum
    assert d.deliver(maximum).outcome == 'stale'
    saved = d.ref.get().to_dict()
    assert saved['dormant'] and saved['due_at'] is None
    assert saved['record_notes_producer_timeout_at'] == maximum
    ledger = pipeline_ledger.ledger_ref(d.f.client, d.f.binding.owner_id, 'capture').get().to_dict()
    assert ledger['stage'] == 'failed:timeout' and ledger['terminal_reason'] == 'failed:timeout'
    d.paid.assert_not_called()
    assert d.deliver(maximum + 120).outcome == 'stale'


def test_clear_barrier_does_not_add_a_delay_or_buy_duplicate_notes(delivery):
    d = delivery
    assert d.deliver(NOW + 120).outcome == 'done'
    assert d.deliver(NOW + 121).outcome == 'stale'
    d.paid.assert_called_once()


@pytest.mark.parametrize('merge_first', [False, True])
def test_refresh_carries_hold_provenance_and_rechecks_later_canonical_quiet_deadline(
    delivery, monkeypatch, merge_first
):

    d = delivery
    d.f.client.rows[d.ref.path]['summary_seen'] = True
    d.adapter.enqueue(
        d.key,
        d.f.binding.owner_id,
        {'conversation_id': 'capture', 'language': 'en', 'record_notes_processing_hold': {'merge_first': merge_first}},
        NOW + 650,
        now=NOW + 50,
        coalesce='max',
        processing_hold_deadline=True,
    )
    # Another arrival after completion extends the canonical clock beyond the saved wake.
    canonical = d.f.conversation.get().to_dict()
    canonical['sync_processing_hold'] = {
        'held': True,
        'pending_since': NOW,
        'last_content_at': NOW + 100,
    }
    monkeypatch.setenv('SYNC_PROCESSING_QUIET_SECONDS', '600')
    monkeypatch.setenv('SYNC_PROCESSING_HOLD_ENABLED', 'false' if merge_first else 'true')
    monkeypatch.setenv('CONVERSATION_MERGE_BEFORE_PROCESSING', 'true')
    monkeypatch.setattr(callback.conversations_db, 'get_conversation', lambda *a, **k: canonical)
    paid = Mock()
    monkeypatch.setattr(callback, 'process_conversation', paid)
    d.worker._process = callback.enrich_conversation
    result = d.deliver(NOW + 650)
    assert result.outcome == 'deferred'
    assert d.ref.get().to_dict()['due_at'] == NOW + 700
    paid.assert_not_called()


def test_redirect_transfers_every_source_producer_fence_without_renewing_deadline(delivery):
    from database.outbox import Claim
    from utils.enrichment import custody

    d = delivery
    d.f.client.rows[d.f.conversation.path].update(deleted=True, sync_merged_into='survivor')
    d.f.user.collection('conversations').document('survivor').create({'status': 'completed'})
    target_key = reprocess.key(d.f.binding.owner_id, 'survivor')
    d.adapter.enqueue(
        target_key,
        d.f.binding.owner_id,
        {
            'conversation_id': 'survivor',
            'language': 'en',
            'record_notes_producer': {'conversation_id': 'another-capture', 'revision': 3},
        },
        NOW + 120,
        now=NOW + 10,
        snapshot_summary=True,
    )
    token = d.ref.get().to_dict()['task_token']
    claim = d.adapter.claim_key(d.key, token, 120, now=NOW + 120)
    assert isinstance(claim, Claim)
    moved = custody.transfer_redirect(d.key, token, claim.lease_token, 'survivor', now=NOW + 120)
    assert moved['record_notes_producers'] == {'capture': 1, 'another-capture': 3}
    assert moved['first_pending_at'] == NOW
    assert not d.ref.get().exists


def test_fallback_refresh_rechecks_canonical_hold_before_any_sibling_completion(delivery, monkeypatch):
    d = delivery
    d.f.client.rows[d.ref.path].update(summary_seen=True, due_at=NOW + 600, sync_hold=False)
    d.f.client.rows[d.f.conversation.path]['sync_processing_hold'] = {
        'held': True,
        'pending_since': NOW,
        'last_content_at': NOW + 100,
    }
    monkeypatch.setenv('SYNC_PROCESSING_QUIET_SECONDS', '600')
    monkeypatch.setattr(callback.conversations_db, 'get_conversation', lambda *a, **k: d.f.conversation.get().to_dict())
    paid = Mock()
    monkeypatch.setattr(callback, 'process_conversation', paid)
    d.worker._process = callback.enrich_conversation
    assert d.deliver(NOW + 600).outcome == 'deferred'
    assert d.ref.get().to_dict()['due_at'] == NOW + 700
    paid.assert_not_called()


def admit_main_intake(recording, monkeypatch, *, eager):
    f = recording
    if eager is None:
        monkeypatch.delenv('RECORD_NOTES_EAGER_ENABLED', raising=False)
    else:
        monkeypatch.setenv('RECORD_NOTES_EAGER_ENABLED', eager)
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_UID_ALLOWLIST', f.binding.owner_id)
    monkeypatch.setenv('BATCH_PIPELINE_RECORD_PROTOCOL_READY', 'true')
    source = f.conversation.get().to_dict()
    intake = MemoryStore()
    intake.rows['conversations', f'{f.binding.owner_id}/capture'] = source
    works = [
        replace(item(sid, owner=f.binding.owner_id, capture=NOW - 2000 + i), privacy_generation=0)
        for i, sid in enumerate(f.binding.segment_ids)
    ]
    admit(intake, works, f.binding, NOW, namespace='record_notes', record_barrier=require_record_audio_barrier(source))
    for sid in f.binding.segment_ids:
        job = intake.rows['jobs', sid]
        assert job['record_input_upload_revision'] == source.get('record_upload_revision')
        job['result'] = f.client.rows[f.store.ref('results', sid).path]['result']
        f.client.rows[f.store.ref('jobs', sid).path] = job
    return f


@pytest.mark.parametrize('adapter_kind', ['consumer', 'legacy'])
@pytest.mark.parametrize('eager', [None, 'false'])
@pytest.mark.parametrize('retired_hold', [None, 'sync_hold', 'merge_hold'])
def test_notes_off_matches_main_intake_enqueue_delivery(recording, monkeypatch, adapter_kind, eager, retired_hold):
    f = admit_main_intake(recording, monkeypatch, eager=eager)
    for sid in f.binding.segment_ids:
        job = f.client.rows[f.store.ref('jobs', sid).path]
        assert 'record_notes_after_complete' not in job
    key = reprocess.key(f.binding.owner_id, 'capture')
    ref = f.client.collection(reprocess.COLLECTION).document(key)
    if retired_hold:
        ref.create(
            {
                'version': 1,
                'dormant': True,
                'due_at': None,
                'summary_seen': True,
                retired_hold: True,
                'record_notes_producers': {'retired-capture': None},
            }
        )
    fence = Mock(side_effect=AssertionError('ordinary main obligation must not enter cut-2 producer fence'))
    monkeypatch.setattr(record_notes_hold, 'admit', fence)
    d = make_delivery(f, monkeypatch, adapter_kind)
    f.store.mark_enrichment('last', f.binding, NOW, 'capture', 'en', policy=POLICY)
    assert f.store.complete('last', f.binding, NOW, f.accounting, policy=POLICY)
    row = ref.get().to_dict()
    assert not row.get('record_notes_producers')
    assert 'record_notes_fallback_outputs' not in f.ledger.get().to_dict()
    assert 'record_notes_after_complete' not in f.ledger.get().to_dict()
    assert row['due_at'] > NOW
    assert d.deliver(row['due_at']).outcome == 'done'
    d.paid.assert_called_once()
    fence.assert_not_called()
    assert not ref.get().to_dict().get('record_notes_producer_timeout_at')


@pytest.mark.parametrize('adapter_kind', ['consumer', 'legacy'])
@pytest.mark.parametrize('eager', [None, 'false'])
@pytest.mark.parametrize('marker', ['job', 'ledger', 'outbox', 'all'])
def test_notes_off_ignores_all_preexisting_completion_and_producer_markers(
    recording, monkeypatch, adapter_kind, eager, marker
):
    f = recording
    for sid in f.binding.segment_ids:
        job = f.client.rows[f.store.ref('jobs', sid).path]
        job.pop('record_notes_after_complete', None)
        if marker in {'job', 'all'}:
            job['record_notes_after_complete'] = True
    if marker in {'ledger', 'all'}:
        f.client.rows[f.ledger.path]['record_notes_after_complete'] = True
    if eager is None:
        monkeypatch.delenv('RECORD_NOTES_EAGER_ENABLED', raising=False)
    else:
        monkeypatch.setenv('RECORD_NOTES_EAGER_ENABLED', eager)
    d = make_delivery(f, monkeypatch, adapter_kind)
    assert 'record_notes_fallback_outputs' not in f.ledger.get().to_dict()
    for sid in f.binding.segment_ids[1:]:
        f.store.mark_enrichment(sid, f.binding, NOW, 'capture', 'en', policy=POLICY)
    if marker in {'outbox', 'all'}:
        f.client.rows[d.ref.path]['record_notes_producers'] = {'capture': None}
    # A receipt written before rollback must not revive the completion path.
    for sid in f.binding.segment_ids:
        f.client.rows[f.store.ref('results', sid).path]['projection']['record_notes_deferred'] = True
    before = d.ref.get().to_dict()
    assert f.store.complete('last', f.binding, NOW, f.accounting, policy=POLICY)
    assert d.ref.get().to_dict() == before  # No completion refresh, even with old receipts/markers.
    f.client.rows[d.ref.path]['record_notes_producers'] = {'capture': None}
    f.client.rows[f.conversation.path].update(record_audio_closed=False, record_upload_sessions={'late': True})
    fence = Mock(side_effect=AssertionError('cut 2 off must ignore old producer markers'))
    monkeypatch.setattr(record_notes_hold, 'admit', fence)
    assert d.deliver(before['due_at']).outcome == 'done'
    d.paid.assert_called_once()
    fence.assert_not_called()
