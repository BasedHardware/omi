"""The live conversation-row write must replay contention on the shared bounded budget.

``update_conversation_segments`` is the hottest write on the listen path: one
transaction per ~0.6s drain per live socket, replanning the merge against the
row's current receipt every attempt. Until 2026-10-28 it was the last
conversation-surface writer still running a bare transactional call: Firestore
retries a commit abort by replaying the SAME — often already retired —
transaction id, and never retries an abort raised by the body's read, so a
mid-write contention burst surfaced immediately as ``Live transcript persist
failed; retained N segment(s) for retry`` with the whole batch parked on the
backoff ladder (prod backend-listen 2026-10-28: expired-id ``InvalidArgument``
×199/3h through this boundary plus its read-time ``Aborted 409`` sibling
×77/20m). The write now runs on the same bounded fresh-transaction budget as
its sibling writers (session open/renewal/event, continuation adoption, sync
assignment): only contention shapes replay, every replay re-reads the row and
replans, deterministic refusals and permanent rejections never replay, and an
exhausted budget surfaces as ``FirestoreContentionExhausted`` — classified as
transient contention by every caller arm, so the persist loop keeps its
retained-batch retry.

Failure-Class: FC-conversation-persistence-expired-transaction (nearest
existing registry class: the conversation-persistence contract whose
canonical artifact is this exact file pair — ``database/conversations.py``
plus its unit guards. The class names the retired-id half, which
``run_transactional`` already restarted; this diff closes the contention half
of the same contract — the read-side ``Aborted`` the SDK never retries and the
commit-side ``Aborted`` the SDK only replayed on the dead id — by routing the
transaction through the shared bounded budget like the recording-session and
sync-assignment writers before it.)

Guards:
- a read-time or commit-time contention burst replays on fresh transactions
  and commits once;
- a burst outliving the budget raises ``FirestoreContentionExhausted``, which
  classifies as transient contention (never a permanent rejection or a
  deterministic defect) and leaves the row untouched;
- expired-id commits and reads restart inside one budget attempt;
- permanent rejections (document size, permission) and deterministic refusals
  (missing row, deleted row, stale sync revision) never replay;
- a replay replans from the receipt a concurrent writer committed between the
  attempts, never mutates the caller's segments, and stamps the absorption
  receipt exactly once;
- the projection family, the audio-timeline pin and owner-recognition
  diagnostics keep their write semantics across replays;
- the two listen-loop callers — the speaker-map flush and the on-demand
  translation persist — survive the same bursts through the real
  ``update_conversation_segments`` boundary.
"""

from __future__ import annotations

import asyncio
import os
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from google.api_core.exceptions import Aborted, InvalidArgument

from database import conversations as db
from database._client import firestore_failure_reason, is_permanent_firestore_write_rejection
from database.firestore_transaction_retry import FirestoreContentionExhausted, run_with_transaction_contention_retry
from routers.listen.transcripts import _is_deterministic_persist_defect
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.manual_speaker_assignments import LiveTranscriptMerge

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

EXPIRED_MESSAGE = '400 The referenced transaction has expired or is no longer valid'
EXPIRED_READ_MESSAGE = '409 The referenced transaction has expired or is no longer valid'
CONTENTION_MESSAGE = '409 Too much contention on these documents. Please try again.'
SIZE_LIMIT_MESSAGE = 'InvalidArgument 400: the request exceeds the maximum allowed size'
PERMISSION_MESSAGE = '403 the caller does not have permission to access this document'

CONV_PATH = ('users', 'u', 'conversations', 'c')


def speech(sid, text='Hello', speaker=0, start=0, end=1):
    return dict(
        id=sid,
        text=text,
        speaker=f'SPEAKER_{speaker:02}',
        speaker_id=speaker,
        start=start,
        end=end,
        is_user=False,
        person_id=None,
    )


def _segments():
    return [speech('s0'), speech('s1', 'Second.', 1, 1, 2)]


def _row():
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    return dict(
        id='c',
        status='in_progress',
        created_at=now,
        started_at=now,
        finished_at=now,
        structured={'title': 'Live row'},
        transcript_segments=_segments(),
        data_protection_level='standard',
    )


def _projection_payload():
    """A valid persisted client projection for projection-family tests."""
    from models.client_processing import (
        ClientProcessing,
        ProjectedActionItem,
        ProjectedStructure,
        ProjectionProvenance,
    )
    from models.transcript_segment import TranscriptSegment
    from utils.conversations.transcript_hash import transcript_sha256

    digest = transcript_sha256(
        [TranscriptSegment(**speech('s0')), TranscriptSegment(**speech('s1', 'Second.', 1, 1, 2))]
    )
    projection = ClientProcessing(
        schema_version=1,
        transcript_sha256=digest,
        structure=ProjectedStructure(title='Live row', overview='canary'),
        action_items=[ProjectedActionItem(description='canary', completed=False)],
        provenance=ProjectionProvenance(
            model_id='local-test-model',
            runtime='mlx',
            device_class='apple_silicon',
            generated_at=_row()['created_at'],
        ),
    )
    return projection.model_dump()


@pytest.fixture
def row_world(monkeypatch):
    """A seeded conversation row whose Firestore transaction can hit injected faults.

    The transactional wrapper pops one read fault before the body and one
    commit fault after it, mirroring the SDK boundaries, and counts every body
    run. The budget wrapper keeps the real helper but strips its jitter and
    sleep so a burst replays instantly, counts every attempt, and records the
    ``operation_name`` it was invoked with. The budget's own factory
    transaction is passed through unused — ``run_transactional`` owns the
    mint so the expired-transaction restart and its attempt bookkeeping stay
    in one place — so attempt counting lives here, not in mint counts.
    """
    store = StrictFirestore()
    store.rows[CONV_PATH] = dict(
        id='c',
        status='in_progress',
        created_at=_row()['created_at'],
        started_at=_row()['started_at'],
        finished_at=_row()['finished_at'],
        structured={'title': 'Live row'},
        transcript_segments=_segments(),
        data_protection_level='standard',
    )
    store.rows[('users', 'u', 'people', 'new')] = dict(name='New')
    store.read_errors = []
    store.commit_errors = []
    store.before_body = None
    store.attempts = 0
    store.body_runs = 0
    store.budget_calls = []
    store.stats_invalidations = []

    monkeypatch.setattr(db, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(db, 'invalidate_people_stats_cache', lambda uid: store.stats_invalidations.append(uid))

    def injecting_transactional(func):
        def locked(transaction, *args, **kwargs):
            store.body_runs += 1
            if store.read_errors:
                raise store.read_errors.pop(0)
            if store.before_body is not None:
                hook, store.before_body = store.before_body, None
                hook()
            result = func(transaction, *args, **kwargs)
            if store.commit_errors:
                raise store.commit_errors.pop(0)
            return result

        return locked

    monkeypatch.setattr(db.firestore, 'transactional', injecting_transactional)

    def budget(factory, operation, **kw):
        store.budget_calls.append(kw.get('operation_name'))

        # One sleep call per replayed attempt: counting here keeps the count
        # identical to the helper's internal attempt bookkeeping even when a
        # single budget invocation carries several attempts.
        def count_sleep(_delay):
            store.attempts += 1

        return run_with_transaction_contention_retry(
            factory, operation, sleep=count_sleep, random_value=lambda: 0.0, **kw
        )

    monkeypatch.setattr(db, 'run_with_transaction_contention_retry', budget)
    return store


def _decoded_segments(store):
    raw = deepcopy(store.rows[CONV_PATH])
    return db._decode_transcript_segments_strict(
        'u', raw['transcript_segments'], bool(raw.get('transcript_segments_compressed'))
    )


def _last_payload(store):
    written = [transaction for transaction in store.transactions if transaction.updates]
    assert written, 'expected one transaction that staged the update'
    return written[-1].updates[-1][1]


def _staged_writes(store):
    return [transaction for transaction in store.transactions if transaction.updates]


# ── The budget contract on the write itself ─────────────────────────────────


def test_uncontended_write_runs_one_body_and_commits(row_world):
    store = row_world
    result = db.update_conversation_segments('u', 'c', deepcopy(store.rows[CONV_PATH]['transcript_segments']))
    assert result is True
    assert store.attempts == 0
    assert store.body_runs == 1
    assert len(_staged_writes(store)) == 1
    assert store.stats_invalidations == ['u']


def test_budget_operation_name_is_pinned(row_world):
    store = row_world
    db.update_conversation_segments('u', 'c', deepcopy(store.rows[CONV_PATH]['transcript_segments']))
    assert store.budget_calls == ['conversation_segments_write']


def test_read_contention_burst_replays_and_commits(row_world):
    store = row_world
    store.read_errors = [Aborted(CONTENTION_MESSAGE)]
    segments = deepcopy(store.rows[CONV_PATH]['transcript_segments'])
    result = db.update_conversation_segments('u', 'c', segments)
    assert result is True
    assert store.attempts == 1
    assert store.body_runs == 2
    assert len(_decoded_segments(store)) == 2


def test_commit_contention_replays_on_fresh_attempt(row_world):
    store = row_world
    store.commit_errors = [Aborted(CONTENTION_MESSAGE)]
    segments = deepcopy(store.rows[CONV_PATH]['transcript_segments'])
    result = db.update_conversation_segments('u', 'c', segments)
    assert result is True
    assert store.attempts == 1
    assert store.body_runs == 2
    assert len(_decoded_segments(store)) == 2


def test_mixed_read_then_commit_contention_burst_recovers(row_world):
    store = row_world
    store.read_errors = [Aborted(CONTENTION_MESSAGE)]
    store.commit_errors = [Aborted(CONTENTION_MESSAGE)]
    segments = deepcopy(store.rows[CONV_PATH]['transcript_segments'])
    result = db.update_conversation_segments('u', 'c', segments)
    assert result is True
    assert store.attempts == 2
    assert store.body_runs == 3
    assert len(_decoded_segments(store)) == 2


def test_expired_id_commit_restarts_inside_one_attempt(row_world):
    store = row_world
    store.commit_errors = [InvalidArgument(EXPIRED_MESSAGE)]
    segments = deepcopy(store.rows[CONV_PATH]['transcript_segments'])
    result = db.update_conversation_segments('u', 'c', segments)
    assert result is True
    # The expired-id restart lives inside run_transactional: two body runs,
    # no budget replay (nothing slept).
    assert store.attempts == 0
    assert store.body_runs == 2
    assert len(_decoded_segments(store)) == 2


def test_expired_id_read_restarts_inside_one_attempt(row_world):
    store = row_world
    store.read_errors = [Aborted(EXPIRED_READ_MESSAGE)]
    segments = deepcopy(store.rows[CONV_PATH]['transcript_segments'])
    result = db.update_conversation_segments('u', 'c', segments)
    assert result is True
    assert store.attempts == 0
    assert store.body_runs == 2
    assert store.budget_calls == ['conversation_segments_write']


def test_five_read_contention_attempts_exhaust_to_contention_exhausted(row_world):
    store = row_world
    store.read_errors = [Aborted(CONTENTION_MESSAGE)] * 5
    segments = deepcopy(store.rows[CONV_PATH]['transcript_segments'])
    with pytest.raises(FirestoreContentionExhausted):
        db.update_conversation_segments('u', 'c', segments)
    assert store.attempts == 4
    assert store.body_runs == 5
    assert len(_decoded_segments(store)) == 2, 'an exhausted burst must leave the row untouched'


def test_exhausted_budget_is_transient_contention_not_permanent():
    """An exhausted budget classifies as transient contention, never a failure arm.

    The classification is what keeps the retained batch on the persist
    loop's retry ladder: a permanent-rejection or deterministic-defect
    verdict would end the batch instead.
    """
    error = FirestoreContentionExhausted('Firestore transaction contention exhausted for conversation_segments_write')
    assert is_permanent_firestore_write_rejection(error) is False
    assert _is_deterministic_persist_defect(error) is False
    assert firestore_failure_reason(error) == 'contention'


def test_row_is_untouched_after_an_exhausted_burst(row_world):
    store = row_world
    before = deepcopy(store.rows[CONV_PATH])
    store.read_errors = [Aborted(CONTENTION_MESSAGE)] * 5
    segments = deepcopy(store.rows[CONV_PATH]['transcript_segments'])
    with pytest.raises(FirestoreContentionExhausted):
        db.update_conversation_segments('u', 'c', segments)
    assert store.rows[CONV_PATH] == before
    assert store.stats_invalidations == []


def test_success_after_exhaustion_is_a_fresh_budget(row_world):
    store = row_world
    store.read_errors = [Aborted(CONTENTION_MESSAGE)] * 5
    segments = deepcopy(store.rows[CONV_PATH]['transcript_segments'])
    with pytest.raises(FirestoreContentionExhausted):
        db.update_conversation_segments('u', 'c', segments)
    store.read_errors.clear()
    assert db.update_conversation_segments('u', 'c', segments) is True
    assert len(_decoded_segments(store)) == 2


def test_document_size_rejection_is_never_replayed(row_world):
    store = row_world
    store.commit_errors = [InvalidArgument(SIZE_LIMIT_MESSAGE)]
    segments = deepcopy(store.rows[CONV_PATH]['transcript_segments'])
    with pytest.raises(InvalidArgument):
        db.update_conversation_segments('u', 'c', segments)
    assert store.attempts == 0
    assert store.body_runs == 1, 'a permanent rejection must not spend a single replay'


def test_permission_rejection_is_never_replayed(row_world):
    store = row_world
    store.commit_errors = [InvalidArgument(PERMISSION_MESSAGE)]
    segments = deepcopy(store.rows[CONV_PATH]['transcript_segments'])
    with pytest.raises(InvalidArgument):
        db.update_conversation_segments('u', 'c', segments)
    assert store.attempts == 0
    assert store.body_runs == 1


def test_missing_row_refuses_without_replay(row_world):
    store = row_world
    del store.rows[CONV_PATH]
    result = db.update_conversation_segments('u', 'c', [speech('s0')])
    assert result is False
    assert store.attempts == 0
    assert store.body_runs == 1
    assert store.stats_invalidations == []


def test_stale_merge_lease_refuses_without_replay(row_world):
    """A missing row's answer is deterministic and never replays.

    ``update_conversation_segments`` carries no smart-merge lease fence of
    its own (that fence lives on the processing-persist write), so the
    deterministic refusal this guard pins is the missing row: it refuses on
    the first attempt without spending a replay, and a caller-level
    SmartMerge staleness can never be laundered into a transient retry here.
    """
    store = row_world
    result = db.update_conversation_segments('u', 'c-not-there', [speech('s0')])
    assert result is False
    assert store.attempts == 0
    assert store.body_runs == 1


def test_mutually_exclusive_modes_raise_before_any_transaction(row_world):
    store = row_world
    with pytest.raises(ValueError):
        db.update_conversation_segments(
            'u', 'c', [], live_segments=[speech('b')], segment_update_fields=('translations',)
        )
    assert store.attempts == 0
    assert store.body_runs == 0


def test_invalid_segment_update_fields_raise_before_any_transaction(row_world):
    store = row_world
    with pytest.raises(ValueError):
        db.update_conversation_segments('u', 'c', [], segment_update_fields=('text',))
    assert store.attempts == 0
    assert store.body_runs == 0


# ── Replay semantics: replanning, receipts, projections, pins ───────────────


def test_replay_replans_from_receipt_committed_between_attempts(row_world, monkeypatch):
    store = row_world
    store.rows[CONV_PATH]['transcript_segments'] = [speech('a')]
    fresh = [speech('b', 'world.', 0, 1, 2)]
    attempts = []
    original = db.merge_live_segments

    # A concurrent owner's decision commits between the two attempts: the
    # first plan reads the pre-assignment receipt, then the plan boundary
    # fires the concurrent assignment (its own clean transactional calls) and
    # aborts the attempt, so the replay must replan against the receipt
    # generation the assignment committed. Arming nothing else keeps the
    # nested assignment's own transactions fault-free.
    assigned = False
    receipt_generations = []

    def concurrent_assignment():
        nonlocal assigned
        assigned = True
        db.assign_conversation_speaker('u', 'c', person_id='new', segment_ids=['a'], firestore_client=store)

    def plan(persisted, incoming, receipt, absorbed_ids=None, capture_reasons=None, capture_proofs=None):
        receipt_generations.append(receipt.get('generation'))
        if not assigned:
            concurrent_assignment()
            raise Aborted(CONTENTION_MESSAGE)
        result = original(
            persisted,
            incoming,
            receipt,
            absorbed_ids=absorbed_ids,
            capture_reasons=capture_reasons,
            capture_proofs=capture_proofs,
        )
        attempts.append(result)
        return result

    monkeypatch.setattr(db, 'merge_live_segments', plan)

    result = db.update_conversation_segments('u', 'c', [], live_segments=fresh)
    assert isinstance(result, LiveTranscriptMerge)
    # The aborted first plan never produced a merge result; the replay's plan
    # is the only committed one.
    assert len(attempts) == 1
    assert assigned is True
    # The first plan ran against the pre-assignment receipt (absent on the
    # fresh row), the replay ran against the receipt generation the
    # concurrent assignment committed.
    assert receipt_generations == [None, 1]
    # The replay honored the concurrent decision: the committed row carries
    # the assignment the first attempt never saw.
    committed = {segment['id']: segment for segment in _decoded_segments(store)}
    assert committed['a']['person_id'] == 'new'
    assert fresh[0]['text'] == 'world.', 'the caller\'s segment dicts must never be mutated by a replay'


def test_replay_does_not_mutate_caller_live_segments(row_world):
    store = row_world
    store.rows[CONV_PATH]['transcript_segments'] = [speech('a')]
    fresh = [speech('b', 'world.', 0, 1, 2)]
    before = deepcopy(fresh)
    store.read_errors = [Aborted(CONTENTION_MESSAGE)]
    result = db.update_conversation_segments('u', 'c', [], live_segments=fresh)
    assert isinstance(result, LiveTranscriptMerge)
    assert fresh == before
    assert _decoded_segments(store) == result.segments


def test_absorbed_receipt_is_stamped_exactly_once(row_world):
    store = row_world
    store.rows[CONV_PATH]['transcript_segments'] = [speech('a')]
    fresh = [speech('b', 'world.', 0, 1, 2)]
    store.read_errors = [Aborted(CONTENTION_MESSAGE)]
    result = db.update_conversation_segments('u', 'c', [], live_segments=fresh)
    assert isinstance(result, LiveTranscriptMerge)
    assert result.absorbed_into == {'b': 'a'}
    payload = _last_payload(store)
    receipt = db._reveal_json_value(payload['live_transcript_replay_receipt'], 'u', True)
    assert receipt == {'commits': [['b']]}, 'an aborted first attempt must not double-stamp the receipt'


def test_projection_is_cleared_on_first_write_when_present(row_world):
    store = row_world
    store.rows[CONV_PATH]['client_processing'] = _projection_payload()
    segments = deepcopy(store.rows[CONV_PATH]['transcript_segments'])
    db.update_conversation_segments('u', 'c', segments, invalidate_client_processing=False)
    payload = _last_payload(store)
    assert payload['client_processing'] is db.firestore.DELETE_FIELD
    assert store.rows[CONV_PATH]['client_processing'] is db.firestore.DELETE_FIELD


def test_projection_is_cleared_within_replayed_write(row_world):
    store = row_world
    store.rows[CONV_PATH]['client_processing'] = _projection_payload()
    store.read_errors = [Aborted(CONTENTION_MESSAGE)]
    segments = deepcopy(store.rows[CONV_PATH]['transcript_segments'])
    db.update_conversation_segments('u', 'c', segments, invalidate_client_processing=False)
    assert store.body_runs == 2
    assert len(_staged_writes(store)) == 1
    assert _staged_writes(store)[0].updates[0][1]['client_processing'] is db.firestore.DELETE_FIELD
    assert store.rows[CONV_PATH]['client_processing'] is db.firestore.DELETE_FIELD


def test_opt_out_leaves_absent_projection_untouched(row_world):
    store = row_world
    segments = deepcopy(store.rows[CONV_PATH]['transcript_segments'])
    db.update_conversation_segments('u', 'c', segments, invalidate_client_processing=False)
    assert 'client_processing' not in _last_payload(store)


def test_audio_timeline_pin_lands_atomically(row_world):
    store = row_world
    timeline = {'v': 2, 'first_audio_start': 1.25}
    segments = deepcopy(store.rows[CONV_PATH]['transcript_segments'])
    db.update_conversation_segments(
        'u', 'c', segments, invalidate_client_processing=False, audio_timeline=timeline, started_at=None
    )
    assert _last_payload(store)['audio_timeline'] == timeline


def test_owner_recognition_diagnostics_land_in_payload(row_world):
    store = row_world
    diagnostics = {
        'live': [
            {
                'socket': 'sock-1',
                'conversation': 'c',
                'generation': 3,
                'sequence': 2,
                'reasons': {'no_fresh_audio': 1},
            }
        ]
    }
    segments = deepcopy(store.rows[CONV_PATH]['transcript_segments'])
    db.update_conversation_segments(
        'u', 'c', segments, invalidate_client_processing=False, owner_recognition_diagnostics=diagnostics
    )
    payload = _last_payload(store)
    merged = payload['owner_recognition_diagnostics']
    assert merged['live'], 'the bounded contract must keep the live row'
    assert merged['live'][0]['socket'] == 'sock-1'
    assert merged['live'][0]['reasons'] == {'no_fresh_audio': 1}


def test_field_only_identity_patch_survives_contention_burst(row_world):
    store = row_world
    store.read_errors = [Aborted(CONTENTION_MESSAGE)]
    segments = deepcopy(store.rows[CONV_PATH]['transcript_segments'])
    for segment in segments:
        segment['person_id'] = 'new'
    written = db.update_conversation_segments(
        'u',
        'c',
        segments,
        invalidate_client_processing=False,
        segment_update_fields=('person_id',),
        return_segments=True,
    )
    assert [s['person_id'] for s in written] == ['new', 'new']
    decoded = _decoded_segments(store)
    assert [s['person_id'] for s in decoded] == ['new', 'new']
    assert [s['text'] for s in decoded] == ['Hello', 'Second.'], 'identity patches must never touch speech'


def test_field_only_writer_burst_preserves_concurrent_text_edit(row_world):
    store = row_world

    def concurrent_text_edit():
        # Another writer commits new speech between the two attempts; the
        # identity-only replay must read and keep it, never restore old text.
        edited = [dict(speech('s0'), text='Edited.'), speech('s1', 'Second.', 1, 1, 2)]
        payload = db._prepare_conversation_for_write({'transcript_segments': edited}, 'u', 'standard')
        store.rows[CONV_PATH]['transcript_segments'] = payload['transcript_segments']
        store.rows[CONV_PATH]['transcript_segments_compressed'] = payload['transcript_segments_compressed']

    store.before_body = concurrent_text_edit
    store.read_errors = [Aborted(CONTENTION_MESSAGE)]
    segments = deepcopy(_segments())
    written = db.update_conversation_segments(
        'u',
        'c',
        segments,
        invalidate_client_processing=False,
        segment_update_fields=('person_id',),
        return_segments=True,
    )
    assert [s['text'] for s in written] == ['Edited.', 'Second.']
    assert [s['text'] for s in _decoded_segments(store)] == ['Edited.', 'Second.']


def test_stats_cache_is_invalidated_once_per_committed_write(row_world):
    store = row_world
    segments = deepcopy(store.rows[CONV_PATH]['transcript_segments'])
    db.update_conversation_segments('u', 'c', segments)
    assert store.stats_invalidations == ['u']


# ── The listen-loop callers through the real boundary ───────────────────────


def _flush_processor(store, *, events):
    from routers.listen.transcripts import ConversationCache, TranscriptProcessor

    async def persist(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    processor = object.__new__(TranscriptProcessor)
    processor.host = SimpleNamespace(
        request=SimpleNamespace(uid='u'),
        state=SimpleNamespace(active=False, speaker_map_dirty=True, speaker_map_version=0),
        speakers=SimpleNamespace(
            segment_assignments={'s0': 'p1'},
            speaker_to_person={0: ('p1', 'Person One')},
            segment_identity_status={},
            diagnostics=None,
            match_scores=[],
        ),
        persistence=SimpleNamespace(call=persist),
        send_event=events.append,
    )
    processor.cache = ConversationCache(AsyncMock(return_value=deepcopy(store.rows[CONV_PATH])))
    processor.translation_lock = None
    processor._flush_failures = 0
    processor._flush_backoff_until = 0.0
    processor._speaker_flush_defect_attempts = 0
    processor._speaker_flush_park_until = 0.0
    processor._speaker_flush_park_conversation = None
    return processor


async def test_speaker_flush_without_map_touches_nothing(row_world):
    store = row_world
    processor = _flush_processor(store, events=[])
    processor.host.speakers = SimpleNamespace(
        segment_assignments={}, speaker_to_person={}, segment_identity_status={}, diagnostics=None
    )
    await processor.flush_speaker_assignments('c')
    assert store.body_runs == 0
    assert store.budget_calls == []


async def test_speaker_flush_survives_read_contention_burst(row_world):
    store = row_world
    processor = _flush_processor(store, events=[])
    store.read_errors = [Aborted(CONTENTION_MESSAGE)]
    await processor.flush_speaker_assignments('c')
    assert store.attempts == 1
    assert store.body_runs == 2
    assert processor.host.state.speaker_map_dirty is False
    assert processor._flush_failures == 0


async def test_speaker_flush_survives_commit_contention_burst(row_world):
    store = row_world
    processor = _flush_processor(store, events=[])
    store.commit_errors = [Aborted(CONTENTION_MESSAGE)]
    await processor.flush_speaker_assignments('c')
    assert store.attempts == 1
    assert store.body_runs == 2
    assert processor.host.state.speaker_map_dirty is False


async def test_speaker_flush_expired_commit_restarts(row_world):
    store = row_world
    processor = _flush_processor(store, events=[])
    store.commit_errors = [InvalidArgument(EXPIRED_MESSAGE)]
    await processor.flush_speaker_assignments('c')
    assert store.attempts == 0, 'the expired-id restart lives inside run_transactional, not a budget replay'
    assert store.body_runs == 2
    assert processor.host.state.speaker_map_dirty is False


async def test_speaker_flush_exhaustion_raises_transient_to_the_loop(row_world):
    store = row_world
    processor = _flush_processor(store, events=[])
    store.read_errors = [Aborted(CONTENTION_MESSAGE)] * 5
    with pytest.raises(FirestoreContentionExhausted):
        await processor.flush_speaker_assignments('c')

    assert processor.host.state.speaker_map_dirty is True
    assert store.stats_invalidations == []
    assert store.attempts == 4
    exhaustion = FirestoreContentionExhausted('probe')
    assert is_permanent_firestore_write_rejection(exhaustion) is False
    assert _is_deterministic_persist_defect(exhaustion) is False


async def test_speaker_flush_resets_ladder_on_commit(row_world):
    store = row_world
    processor = _flush_processor(store, events=[])
    processor._flush_failures = 2
    processor._flush_backoff_until = 10_000.0
    await processor.flush_speaker_assignments('c')
    assert processor._flush_failures == 0
    assert processor._flush_backoff_until == 0.0
    assert processor.host.state.speaker_map_dirty is False


async def test_speaker_flush_carries_diagnostics_through_replay(row_world):
    store = row_world
    processor = _flush_processor(store, events=[])
    snapshot = {
        'live': [
            {
                'socket': 'sock-1',
                'conversation': 'c',
                'generation': 3,
                'sequence': 2,
                'reasons': {'no_fresh_audio': 1},
            }
        ]
    }
    processor.host.speakers.diagnostics = SimpleNamespace(snapshot=lambda conversation_id: deepcopy(snapshot))
    store.read_errors = [Aborted(CONTENTION_MESSAGE)]
    await processor.flush_speaker_assignments('c')
    assert store.body_runs == 2
    assert len(_staged_writes(store)) == 1
    payload = _staged_writes(store)[0].updates[0][1]
    merged = payload['owner_recognition_diagnostics']
    assert merged['live'], 'the replayed write must carry the flush diagnostics'
    assert merged['live'][0]['socket'] == 'sock-1'
    assert merged['live'][0]['reasons'] == {'no_fresh_audio': 1}


def _translation_processor(store, *, translation_language='fr'):
    from routers.listen.transcripts import ConversationCache, TranscriptProcessor

    async def persist(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    events = []
    processor = object.__new__(TranscriptProcessor)
    processor.host = SimpleNamespace(
        request=SimpleNamespace(uid='u'),
        state=SimpleNamespace(active=True, current_conversation_id='c', speaker_map_dirty=False),
        translation_language=translation_language,
        persistence=SimpleNamespace(call=persist),
        send_event=events.append,
    )
    processor.cache = ConversationCache(AsyncMock(return_value=deepcopy(store.rows[CONV_PATH])))
    processor.translation_lock = asyncio.Lock()
    processor.translation_coordinator = None
    processor._events = events
    return processor


@pytest.fixture
def translation_gates(monkeypatch):
    monkeypatch.setenv('TRANSLATION_DEMAND_GATE_ENABLED', 'false')
    monkeypatch.setenv('TRANSLATION_ONOPEN_ENABLED', 'false')


async def test_translation_persist_survives_read_contention_burst(row_world, translation_gates):
    store = row_world
    processor = _translation_processor(store)
    store.read_errors = [Aborted(CONTENTION_MESSAGE)]
    committed = await processor._on_translation_ready('s0', 'bonjour', 'en', 'c')
    assert committed is True
    assert store.attempts == 1
    assert store.body_runs == 2
    decoded = _decoded_segments(store)
    assert decoded[0]['translations'] == [{'lang': 'fr', 'text': 'bonjour'}]
    assert [s['text'] for s in decoded] == ['Hello', 'Second.']


async def test_translation_persist_survives_commit_contention_burst(row_world, translation_gates):
    store = row_world
    processor = _translation_processor(store)
    store.commit_errors = [Aborted(CONTENTION_MESSAGE)]
    committed = await processor._on_translation_ready('s0', 'bonjour', 'en', 'c')
    assert committed is True
    assert store.attempts == 1
    assert store.body_runs == 2
    assert _decoded_segments(store)[0]['translations'] == [{'lang': 'fr', 'text': 'bonjour'}]


async def test_translation_persist_survives_expired_commit(row_world, translation_gates):
    store = row_world
    processor = _translation_processor(store)
    store.commit_errors = [InvalidArgument(EXPIRED_MESSAGE)]
    committed = await processor._on_translation_ready('s0', 'bonjour', 'en', 'c')
    assert committed is True
    assert store.attempts == 0
    assert store.body_runs == 2


async def test_translation_persist_exhaustion_stays_contained(row_world, translation_gates):
    store = row_world
    processor = _translation_processor(store)
    store.read_errors = [Aborted(CONTENTION_MESSAGE)] * 5
    committed = await processor._on_translation_ready('s0', 'bonjour', 'en', 'c')
    # The translation callback owns containment: an exhausted burst is logged
    # once and dropped, never raised into the coordinator's batch loop.
    assert committed is False
    assert store.attempts == 4
    assert store.body_runs == 5
    assert _decoded_segments(store)[0].get('translations') in (None, [])


async def test_translation_persist_permanent_rejection_stays_contained(row_world, translation_gates):
    store = row_world
    processor = _translation_processor(store)
    store.commit_errors = [InvalidArgument(SIZE_LIMIT_MESSAGE)]
    committed = await processor._on_translation_ready('s0', 'bonjour', 'en', 'c')
    assert committed is False
    assert store.attempts == 0
    assert store.body_runs == 1


async def test_translation_requires_translation_language(row_world):
    store = row_world
    processor = _translation_processor(store, translation_language=None)
    committed = await processor._on_translation_ready('s0', 'bonjour', 'en', 'c')
    assert committed is False
    assert store.body_runs == 0


async def test_translation_cache_updated_after_replayed_commit(row_world, translation_gates):
    store = row_world
    processor = _translation_processor(store)
    from unittest.mock import MagicMock

    processor.cache.update_segments = MagicMock()
    store.read_errors = [Aborted(CONTENTION_MESSAGE)]
    committed = await processor._on_translation_ready('s0', 'bonjour', 'en', 'c')
    assert committed is True
    processor.cache.update_segments.assert_called_once()
    updated = processor.cache.update_segments.call_args.args[0]
    accepted = next(segment for segment in updated if segment['id'] == 's0')
    assert accepted['translations'] == [{'lang': 'fr', 'text': 'bonjour'}]
