"""Every conversation-row transaction replays contention on the shared bounded budget.

``database/conversations.py`` still ran thirteen conversation-row writers as
bare transactional calls after the segments write got the shared budget
(2026-10-28). Every one of those bodies READS the row (or its photos,
corrections, or deletion fence) before writing, and Firestore never retries
an abort raised by a transactional read, while a commit abort is replayed by
the SDK on the SAME — often already retired — transaction id. The bootstrap
create is the worst exposed: it is the transaction every live session is
born inside, reached through ``lifecycle.create_in_progress_conversation``
from ``create_new_in_progress_conversation`` on the ASGI coroutine via
``prepare()`` — a caller that cannot classify a storage fault and has no
retry of its own. One contention burst escaped as uvicorn's
``Exception in ASGI application`` and tore down the freshly opened session
(prod backend-listen 2026-10-29 04:00Z: read-time ``Aborted 409 Too much
contention`` from the create transaction's ``batch_get_documents``; the
run_asgi bucket carried ×472 events across the prior two days).

All conversation-row transactions now run through one shared budget helper
(``_run_conversation_transaction``): only contention shapes replay, every
replay re-reads the row and re-derives its merge or fence from what it
reads, expired-id restarts stay inside ``run_transactional``, permanent
rejections and deterministic refusals never replay, and an exhausted budget
raises ``FirestoreContentionExhausted`` — classified as transient
contention by every caller arm, so the recording-session fail-open
classification absorbs it on the bootstrap chain instead of failing the
open, and the session tears down only when the data plane stays contended
for a full bounded budget.

Failure-Class: FC-conversation-persistence-expired-transaction (nearest
existing registry class: the conversation-persistence contract whose
canonical artifacts are ``database/conversations.py`` and its unit guards.
The class names the retired-id half, which ``run_transactional`` already
restarted; tick 2026-10-28 closed the contention half for the segments
write, and this diff closes the same read-side ``Aborted`` half for the
remaining conversation-row writers — the bootstrap create included — by
routing every transaction through the same shared bounded budget.)
"""

from __future__ import annotations

import os
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from google.api_core.exceptions import Aborted, InvalidArgument, PermissionDenied

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from database import conversations as db
import config.owner_recognition_diagnostics as owner_diagnostics
from database.firestore_transaction_retry import FirestoreContentionExhausted
from models.client_processing import ClientProcessing, ProjectedStructure, ProjectionProvenance
from routers.listen.conversations import LiveConversationController
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

# Warm pydantic's schema compilation at import (collection) time: the first
# ClientProcessing build costs more than the fast-unit duration guard's whole
# 1.0s CPU fail budget, which would otherwise land in whichever bind test
# runs first and fail the file on the timing guard, not on behavior.
_WARM_CLIENT_PROCESSING = ClientProcessing(
    schema_version=1,
    transcript_sha256='0' * 64,
    structure=ProjectedStructure(title='warm'),
    action_items=[],
    provenance=ProjectionProvenance(
        model_id='warm',
        runtime='mlx',
        device_class='apple_silicon',
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    ),
)
assert _WARM_CLIENT_PROCESSING.structure.title == 'warm'

# Same warm-up for the live-session payload models: the controller bootstrap
# builds a Conversation + Structured per generation, and the first build pays
# pydantic's one-time schema compilation — more CPU than the duration guard's
# 1.0s budget. Construction at import time keeps that cost out of the call
# phase, where the guard measures it.
from models.conversation import Conversation as _WarmConversation
from models.conversation_enums import ConversationSource as _WarmSource
from models.conversation_enums import ConversationStatus as _WarmStatus
from models.structured import Structured as _WarmStructured

_WARM_CONVERSATION = _WarmConversation(
    id='warm',
    created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    finished_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    structured=_WarmStructured(),
    language='en',
    transcript_segments=[],
    photos=[],
    status=_WarmStatus.in_progress,
    source=_WarmSource.omi,
)
assert _WARM_CONVERSATION.id == 'warm'

EXPIRED_MESSAGE = '400 The referenced transaction has expired or is no longer valid'
EXPIRED_READ_MESSAGE = '409 The referenced transaction has expired or is no longer valid'
CONTENTION_MESSAGE = '409 Too much contention on these documents. Please try again.'
PERMISSION_MESSAGE = '403 the caller does not have permission to access this document'

CONV_PATH = ('users', 'u', 'conversations', 'conversation-1')


def _now():
    return datetime.now(timezone.utc)


def _incoming(status='in_progress'):
    return {
        'id': 'conversation-1',
        'structured': {'title': 'Generated title'},
        'status': status,
        'data_protection_level': 'standard',
    }


@pytest.fixture
def create_world(monkeypatch):
    """A bootstrap-create harness whose transaction can hit injected faults.

    Mirrors the segments-write harness: the transactional wrapper pops one
    read fault before the body and one commit fault after it, the real
    budget runs with jitter stripped so a burst replays instantly, and
    every budget attempt is counted through its sleep.
    """
    store = StrictFirestore()
    store.read_errors = []
    store.commit_errors = []
    store.before_body = None
    store.attempts = 0
    store.body_runs = 0
    store.budget_calls = []
    store.stats_invalidations = []
    store.index_syncs = []

    monkeypatch.setattr(db, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(db, 'db', store)
    monkeypatch.setattr(db, 'invalidate_people_stats_cache', lambda uid: store.stats_invalidations.append(uid))
    monkeypatch.setattr(db, '_sync_conversation_search_index', lambda uid, cid: store.index_syncs.append(cid))
    # The rollover payload omits data_protection_level, so the write decorator
    # resolves the user's level live; keep that seam on the fixture too.
    from database import users as users_db_module
    from database import redis_db as redis_db_module

    monkeypatch.setattr(users_db_module, 'get_user_profile', lambda uid: {'data_protection_level': 'standard'})
    monkeypatch.setattr(redis_db_module, 'get_user_data_protection_level', lambda uid: 'standard')
    monkeypatch.setattr(redis_db_module, 'set_user_data_protection_level', lambda uid, level: None)

    def injecting_transactional(func):
        def locked(transaction, *args, **kwargs):
            # Firestore atomicity: an aborted commit wrote nothing, so the
            # attempt's staged writes roll back before the budget replays.
            pre_attempt = deepcopy(store.rows)
            store.body_runs += 1
            if store.read_errors:
                raise store.read_errors.pop(0)
            if store.before_body is not None:
                hook, store.before_body = store.before_body, None
                hook()
            result = func(transaction, *args, **kwargs)
            if store.commit_errors:
                error = store.commit_errors.pop(0)
                store.rows.clear()
                store.rows.update(pre_attempt)
                raise error
            return result

        return locked

    monkeypatch.setattr(db.firestore, 'transactional', injecting_transactional)

    def budget(factory, operation, **kw):
        store.budget_calls.append(kw.get('operation_name'))

        def count_sleep(_delay):
            store.attempts += 1

        from database.firestore_transaction_retry import run_with_transaction_contention_retry as real_budget

        return real_budget(factory, operation, sleep=count_sleep, random_value=lambda: 0.0, **kw)

    monkeypatch.setattr(db, 'run_with_transaction_contention_retry', budget)
    return store


@pytest.fixture
def row_world(create_world):
    """A create harness seeded with an existing conversation row."""
    store = create_world
    store.rows[CONV_PATH] = {
        'id': 'conversation-1',
        'status': 'completed',
        'created_at': _now(),
        'started_at': _now(),
        'finished_at': _now(),
        'structured': {'title': 'My title', 'overview': 'Old summary'},
        'user_title': 'My title',
        'starred': True,
        'folder_id': 'important',
        'visibility': 'shared',
        'data_protection_level': 'standard',
    }
    return store


# ── The bootstrap create: budget contract ───────────────────────────────────


def test_bootstrap_create_uncontended_runs_one_body(row_world):
    store = row_world
    db.upsert_conversation_with_lifecycle('u', _incoming('completed'))
    assert store.attempts == 0
    assert store.body_runs == 1
    assert store.stats_invalidations == ['u']
    assert store.index_syncs == ['conversation-1']


def test_bootstrap_create_budget_operation_name_is_pinned(row_world):
    store = row_world
    db.upsert_conversation_with_lifecycle('u', _incoming('completed'))
    assert store.budget_calls == ['conversation_create_write']


def test_bootstrap_create_read_contention_replays_and_commits(row_world):
    """The exact prod shape: a read-time Aborted must not fail the create."""
    store = row_world
    store.read_errors = [Aborted(CONTENTION_MESSAGE)]
    db.upsert_conversation_with_lifecycle('u', _incoming('completed'))
    assert store.attempts == 1
    assert store.body_runs == 2
    stored = store.rows[CONV_PATH]
    assert stored['status'] == 'completed'
    assert stored['starred'] is True, 'user-owned fields survive across the replay'
    assert stored['user_title'] == 'My title'


def test_bootstrap_create_commit_contention_replays_on_fresh_attempt(row_world):
    store = row_world
    store.commit_errors = [Aborted(CONTENTION_MESSAGE)]
    db.upsert_conversation_with_lifecycle('u', _incoming('completed'))
    assert store.attempts == 1
    assert store.body_runs == 2
    assert store.rows[CONV_PATH]['status'] == 'completed'


def test_bootstrap_create_expired_id_read_restarts_inside_one_attempt(row_world):
    store = row_world
    store.read_errors = [Aborted(EXPIRED_READ_MESSAGE)]
    db.upsert_conversation_with_lifecycle('u', _incoming('completed'))
    assert store.attempts == 0, 'the expired-id restart lives inside run_transactional'
    assert store.body_runs == 2
    assert store.rows[CONV_PATH]['status'] == 'completed'


def test_bootstrap_create_expired_id_commit_restarts_inside_one_attempt(row_world):
    store = row_world
    store.commit_errors = [InvalidArgument(EXPIRED_MESSAGE)]
    db.upsert_conversation_with_lifecycle('u', _incoming('completed'))
    assert store.attempts == 0
    assert store.body_runs == 2
    assert store.rows[CONV_PATH]['status'] == 'completed'


def test_bootstrap_create_five_read_contention_attempts_exhaust(row_world):
    store = row_world
    store.read_errors = [Aborted(CONTENTION_MESSAGE)] * 5
    with pytest.raises(FirestoreContentionExhausted):
        db.upsert_conversation_with_lifecycle('u', _incoming('completed'))
    assert store.attempts == 4
    assert store.body_runs == 5


def test_bootstrap_create_row_is_untouched_after_an_exhausted_burst(row_world):
    """The replay is atomic: a drained burst leaves the previous row intact."""
    store = row_world
    before = deepcopy(store.rows[CONV_PATH])
    store.commit_errors = [Aborted(CONTENTION_MESSAGE)] * 5
    with pytest.raises(FirestoreContentionExhausted):
        db.upsert_conversation_with_lifecycle('u', _incoming('completed'))
    assert store.rows[CONV_PATH] == before


def test_bootstrap_create_permission_denied_never_replays(row_world):
    store = row_world
    store.commit_errors = [PermissionDenied(PERMISSION_MESSAGE)]
    with pytest.raises(PermissionDenied):
        db.upsert_conversation_with_lifecycle('u', _incoming('completed'))
    assert store.attempts == 0
    assert store.body_runs == 1


def test_bootstrap_create_fresh_row_create_branch_replays_too(create_world):
    """The missing-row create arm replays the same way — the first-write case."""
    store = create_world
    store.read_errors = [Aborted(CONTENTION_MESSAGE)]
    db.upsert_conversation_with_lifecycle('u', _incoming())
    assert store.attempts == 1
    assert store.body_runs == 2
    stored = store.rows[CONV_PATH]
    assert stored['status'] == 'in_progress'
    assert stored['has_photos'] is False


def test_bootstrap_create_between_attempts_user_edit_still_wins(row_world):
    """A user edit committed between two attempts is re-read by the replay.

    The replay re-derives the user-owned-field merge from what it reads, so
    the mid-burst edit wins the row, and the effective_user_title projection
    keeps structured.title consistent with it.
    """
    store = row_world
    store.before_body = lambda: store.rows[CONV_PATH].update({'user_title': 'Edited mid-burst'})
    db.upsert_conversation_with_lifecycle('u', _incoming('completed'))
    stored = store.rows[CONV_PATH]
    assert stored['user_title'] == 'Edited mid-burst'
    assert stored['structured']['title'] == 'Edited mid-burst'


# ── The class: the remaining conversation-row writers ──────────────────────


@pytest.fixture
def summary_world(create_world):
    store = create_world
    store.rows[CONV_PATH] = {
        'id': 'conversation-1',
        'status': 'completed',
        'structured': {'overview': 'Old overview'},
        'data_protection_level': 'standard',
    }
    return store


def test_summary_write_read_contention_replays_and_commits(summary_world):
    store = summary_world
    store.read_errors = [Aborted(CONTENTION_MESSAGE)]
    result = db.update_conversation_summary('u', 'conversation-1', None, 'Fresh overview')
    assert result == 'ok'
    assert store.attempts == 1
    assert store.body_runs == 2
    assert store.rows[CONV_PATH]['structured.overview'] == 'Fresh overview'


def test_claim_status_commit_contention_replays(create_world):
    store = create_world
    store.rows[CONV_PATH] = {'id': 'conversation-1', 'status': 'processing', 'data_protection_level': 'standard'}
    store.commit_errors = [Aborted(CONTENTION_MESSAGE)]
    claimed = db.claim_conversation_status(
        'u', 'conversation-1', db.ConversationStatus.processing, db.ConversationStatus.completed
    )
    assert claimed is True
    assert store.attempts == 1
    assert store.body_runs == 2
    assert store.rows[CONV_PATH]['status'] == 'completed'


def test_discard_by_relevance_read_contention_replays(create_world):
    store = create_world
    store.rows[CONV_PATH] = {'id': 'conversation-1', 'status': 'completed', 'data_protection_level': 'standard'}
    store.read_errors = [Aborted(CONTENTION_MESSAGE)]
    discarded = db.discard_by_relevance('u', 'conversation-1', {'verdict': 'low_value'})
    assert discarded is True
    assert store.attempts == 1
    assert store.body_runs == 2
    assert store.rows[CONV_PATH]['discarded'] is True


def test_restore_from_discarded_read_contention_replays(create_world):
    store = create_world
    store.rows[CONV_PATH] = {'id': 'conversation-1', 'status': 'completed', 'discarded': True}
    store.read_errors = [Aborted(CONTENTION_MESSAGE)]
    restored = db.restore_conversation_from_discarded('u', 'conversation-1')
    assert restored is True
    assert store.attempts == 1
    assert store.body_runs == 2
    assert store.rows[CONV_PATH]['discarded'] is False


def test_bind_client_processing_commit_contention_replays(create_world):
    """The projection bind replays its fence on a fresh snapshot."""
    from utils.conversations.transcript_hash import transcript_sha256

    segments = [speech('s0'), speech('s1', 'Second.', 1, 1, 2)]
    store = create_world
    store.rows[CONV_PATH] = {
        'id': 'conversation-1',
        'status': 'in_progress',
        'transcript_segments': deepcopy(segments),
        'data_protection_level': 'standard',
    }
    digest = transcript_sha256(
        [db.TranscriptSegment(**speech('s0')), db.TranscriptSegment(**speech('s1', 'Second.', 1, 1, 2))]
    )
    projection = ClientProcessing(
        schema_version=1,
        transcript_sha256=digest,
        structure=ProjectedStructure(title='Live row'),
        action_items=[],
        provenance=ProjectionProvenance(
            model_id='local-test-model',
            runtime='mlx',
            device_class='apple_silicon',
            generated_at=_now(),
        ),
    )
    # The projection reaches the bind under its family root, exactly as the
    # persisted client rows show it (client_processing on the conversation).
    mutation = {'client_processing': projection.model_dump()}
    store.commit_errors = [Aborted(CONTENTION_MESSAGE)]
    bound = db.bind_client_processing('u', 'conversation-1', mutation)
    assert bound is True
    assert store.attempts == 1
    assert store.body_runs == 2
    assert store.rows[CONV_PATH]['client_processing']['structure']['title'] == 'Live row'


def test_owner_diagnostics_read_contention_replays(create_world):
    store = create_world
    store.rows[CONV_PATH] = {'id': 'conversation-1', 'status': 'completed', 'data_protection_level': 'standard'}
    store.read_errors = [Aborted(CONTENTION_MESSAGE)]
    persisted = db.update_owner_recognition_diagnostics(
        'u',
        'conversation-1',
        {'live': [{'conversation': 'conversation-1', 'generation': 2, 'attempted': 3, 'successful': 3}]},
    )
    assert persisted is True
    assert store.attempts == 1
    assert store.body_runs == 2
    merged = store.rows[CONV_PATH][owner_diagnostics.FIELD]
    assert merged['live'][0]['attempted'] == 3
    assert merged['live'][0]['successful'] == 3


def test_photo_store_read_contention_replays(create_world):
    from models.conversation_photo import ConversationPhoto

    store = create_world
    store.rows[CONV_PATH] = {
        'id': 'conversation-1',
        'status': 'completed',
        'data_protection_level': 'standard',
    }
    photo = ConversationPhoto(base64='AAAA')
    store.read_errors = [Aborted(CONTENTION_MESSAGE)]
    stored = db.store_conversation_photos('u', 'conversation-1', [photo], firestore_client=store)
    assert stored is True
    assert store.attempts == 1
    assert store.body_runs == 2
    assert store.rows[CONV_PATH]['has_photos'] is True


def test_exhausted_budget_classifies_as_transient_contention_not_permanent():
    """The exhaustion verdict callers see is the transient contention class."""
    from database._client import firestore_failure_reason, is_permanent_firestore_write_rejection
    from utils.conversations.lifecycle import _is_recording_session_transient

    error = FirestoreContentionExhausted('Firestore transaction contention exhausted for conversation_create_write')
    assert is_permanent_firestore_write_rejection(error) is False
    assert firestore_failure_reason(error) == 'contention'
    assert _is_recording_session_transient(error) is True


# ── Per-writer fences: refusals never replay ───────────────────────────────


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


def _completed_row(store, **extra):
    store.rows[CONV_PATH] = {
        'id': 'conversation-1',
        'status': 'completed',
        'data_protection_level': 'standard',
        **extra,
    }
    return store.rows[CONV_PATH]


def test_claim_status_missing_row_raises_without_replay(create_world):
    from google.api_core.exceptions import NotFound

    store = create_world
    with pytest.raises(NotFound):
        db.claim_conversation_status(
            'u', 'conversation-1', db.ConversationStatus.processing, db.ConversationStatus.completed
        )
    assert store.body_runs == 1
    assert store.attempts == 0


def test_claim_status_mismatch_refuses_without_replay(create_world):
    store = create_world
    _completed_row(store, status='completed')
    claimed = db.claim_conversation_status(
        'u', 'conversation-1', db.ConversationStatus.processing, db.ConversationStatus.completed
    )
    assert claimed is False
    assert store.body_runs == 1
    assert store.attempts == 0


def test_summary_write_missing_row_reports_not_found_without_replay(create_world):
    store = create_world
    result = db.update_conversation_summary('u', 'conversation-1', None, 'Fresh overview')
    assert result == 'not_found'
    assert store.body_runs == 1
    assert store.attempts == 0


def test_summary_write_app_result_commit_contention_replays(create_world):
    store = create_world
    _completed_row(store, apps_results=[{'app_id': 'a1', 'content': 'Old content'}])
    store.commit_errors = [Aborted(CONTENTION_MESSAGE)]
    result = db.update_conversation_summary('u', 'conversation-1', 'a1', 'New content')
    assert result == 'ok'
    assert store.attempts == 1
    assert store.body_runs == 2
    row = store.rows[CONV_PATH]
    rewritten = [entry for entry in row['apps_results'] if isinstance(entry, dict) and entry.get('app_id') == 'a1']
    assert rewritten and rewritten[0]['content'] == 'New content'


def test_summary_write_permission_denied_never_replays(create_world):
    store = create_world
    _completed_row(store)
    store.commit_errors = [PermissionDenied(PERMISSION_MESSAGE)]
    with pytest.raises(PermissionDenied):
        db.update_conversation_summary('u', 'conversation-1', None, 'Fresh overview')
    assert store.body_runs == 1
    assert store.attempts == 0


def test_summary_write_expired_id_commit_restarts_inside_one_attempt(create_world):
    store = create_world
    _completed_row(store)
    store.commit_errors = [InvalidArgument(EXPIRED_MESSAGE)]
    result = db.update_conversation_summary('u', 'conversation-1', None, 'Fresh overview')
    assert result == 'ok'
    assert store.attempts == 0
    assert store.body_runs == 2


def test_discard_by_relevance_user_curated_refuses_without_replay(create_world):
    store = create_world
    _completed_row(store, starred=True)
    discarded = db.discard_by_relevance('u', 'conversation-1', {'verdict': 'low_value'})
    assert discarded is False
    assert store.body_runs == 1
    assert store.attempts == 0
    assert store.rows[CONV_PATH].get('discarded') is None


def test_discard_by_relevance_stale_revision_refuses_without_replay(create_world):
    store = create_world
    _completed_row(store, sync_content_revision=7)
    discarded = db.discard_by_relevance(
        'u', 'conversation-1', {'verdict': 'low_value'}, expected_sync_content_revision=5
    )
    assert discarded is False
    assert store.body_runs == 1
    assert store.rows[CONV_PATH].get('discarded') is None


def test_discard_by_relevance_five_read_attempts_exhaust_and_leave_row(create_world):
    store = create_world
    _completed_row(store)
    before = deepcopy(store.rows[CONV_PATH])
    store.read_errors = [Aborted(CONTENTION_MESSAGE)] * 5
    with pytest.raises(FirestoreContentionExhausted):
        db.discard_by_relevance('u', 'conversation-1', {'verdict': 'low_value'})
    assert store.attempts == 4
    assert store.rows[CONV_PATH] == before


def test_discard_by_relevance_expired_id_read_restarts(create_world):
    store = create_world
    _completed_row(store)
    store.read_errors = [Aborted(EXPIRED_READ_MESSAGE)]
    discarded = db.discard_by_relevance('u', 'conversation-1', {'verdict': 'low_value'})
    assert discarded is True
    assert store.attempts == 0
    assert store.body_runs == 2
    assert store.rows[CONV_PATH]['discarded'] is True


def test_restore_tombstone_refuses_without_replay(create_world):
    store = create_world
    _completed_row(store, discarded=True, deleted=True)
    restored = db.restore_conversation_from_discarded('u', 'conversation-1')
    assert restored is False
    assert store.body_runs == 1
    assert store.attempts == 0
    assert store.rows[CONV_PATH]['discarded'] is True


def test_restore_jev_discard_marks_restored_marker(create_world):
    store = create_world
    _completed_row(
        store,
        discarded=True,
        relevance_decision={'verdict': 'discard', 'decided_by': 'jev'},
    )
    restored = db.restore_conversation_from_discarded('u', 'conversation-1')
    assert restored is True
    assert store.rows[CONV_PATH]['jev_discard_restored'] is True
    assert store.rows[CONV_PATH]['discarded'] is False


def test_restore_commit_contention_replays_and_keeps_marker_derivation(create_world):
    store = create_world
    _completed_row(
        store,
        discarded=True,
        sync_relevance='review',
        relevance_decision={'verdict': 'discard', 'decided_by': 'jev'},
    )
    store.commit_errors = [Aborted(CONTENTION_MESSAGE)]
    restored = db.restore_conversation_from_discarded('u', 'conversation-1')
    assert restored is True
    assert store.attempts == 1
    row = store.rows[CONV_PATH]
    assert row['sync_relevance'] == 'keep'
    assert row['jev_discard_restored'] is True


def test_photo_store_missing_row_refuses_without_replay(create_world):
    from models.conversation_photo import ConversationPhoto

    store = create_world
    stored = db.store_conversation_photos(
        'u', 'conversation-1', [ConversationPhoto(base64='AAAA')], firestore_client=store
    )
    assert stored is False
    assert store.body_runs == 1
    assert store.attempts == 0


def test_photo_store_expired_id_read_restarts(create_world):
    from models.conversation_photo import ConversationPhoto

    store = create_world
    _completed_row(store)
    store.read_errors = [Aborted(EXPIRED_READ_MESSAGE)]
    stored = db.store_conversation_photos(
        'u', 'conversation-1', [ConversationPhoto(base64='AAAA')], firestore_client=store
    )
    assert stored is True
    assert store.attempts == 0
    assert store.body_runs == 2
    assert store.rows[CONV_PATH]['has_photos'] is True


def test_bind_client_processing_digest_mismatch_refuses_without_replay(create_world):
    store = create_world
    store.rows[CONV_PATH] = {
        'id': 'conversation-1',
        'status': 'in_progress',
        'transcript_segments': [speech('s0', 'Stored words.')],
        'data_protection_level': 'standard',
    }
    projection = ClientProcessing(
        schema_version=1,
        transcript_sha256='0' * 64,
        structure=ProjectedStructure(title='Live row'),
        action_items=[],
        provenance=ProjectionProvenance(
            model_id='local-test-model', runtime='mlx', device_class='apple_silicon', generated_at=_now()
        ),
    )
    bound = db.bind_client_processing('u', 'conversation-1', {'client_processing': projection.model_dump()})
    assert bound is False
    assert store.body_runs == 1
    assert store.attempts == 0
    assert 'client_processing' not in store.rows[CONV_PATH]


def test_bind_client_processing_five_commit_attempts_exhaust(create_world):
    from utils.conversations.transcript_hash import transcript_sha256

    store = create_world
    segments = [speech('s0'), speech('s1', 'Second.', 1, 1, 2)]
    store.rows[CONV_PATH] = {
        'id': 'conversation-1',
        'status': 'in_progress',
        'transcript_segments': deepcopy(segments),
        'data_protection_level': 'standard',
    }
    digest = transcript_sha256([db.TranscriptSegment(**s) for s in segments])
    projection = ClientProcessing(
        schema_version=1,
        transcript_sha256=digest,
        structure=ProjectedStructure(title='Live row'),
        action_items=[],
        provenance=ProjectionProvenance(
            model_id='local-test-model', runtime='mlx', device_class='apple_silicon', generated_at=_now()
        ),
    )
    before = deepcopy(store.rows[CONV_PATH])
    store.commit_errors = [Aborted(CONTENTION_MESSAGE)] * 5
    with pytest.raises(FirestoreContentionExhausted):
        db.bind_client_processing('u', 'conversation-1', {'client_processing': projection.model_dump()})
    assert store.attempts == 4
    assert store.rows[CONV_PATH] == before


# ── Per-writer replays: the remaining class members ────────────────────────


def test_duplicate_capture_link_commit_contention_replays_and_stamps_marker(create_world):
    from types import SimpleNamespace as NS
    from datetime import datetime

    store = create_world
    started = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
    finished = datetime(2026, 10, 29, 12, 5, tzinfo=timezone.utc)
    _completed_row(store, source='omi')
    store.rows[CONV_PATH]['started_at'] = started
    store.rows[CONV_PATH]['finished_at'] = finished
    secondary_path = ('users', 'u', 'conversations', 'conversation-2')
    store.rows[secondary_path] = {
        'id': 'conversation-2',
        'status': 'completed',
        'started_at': started,
        'finished_at': finished,
        'source': 'omi',
        'data_protection_level': 'standard',
    }
    primary = NS(conversation_id='conversation-1', started_at=started, finished_at=finished, source='omi')
    secondary = NS(conversation_id='conversation-2', started_at=started, finished_at=finished, source='omi')
    store.commit_errors = [Aborted(CONTENTION_MESSAGE)]
    linked = db.link_duplicate_capture('u', primary, secondary, {'gap_seconds': 3.0}, firestore_client=store)
    assert linked is True
    assert store.attempts == 1
    assert store.body_runs == 2
    external = store.rows[secondary_path]['external_data']
    assert external['duplicate_capture_of'] == 'conversation-1'
    assert external['cross_device_duplicate']['primary_conversation_id'] == 'conversation-1'


def test_duplicate_capture_link_discarded_secondary_refuses_without_replay(create_world):
    from types import SimpleNamespace as NS
    from datetime import datetime

    store = create_world
    started = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
    finished = datetime(2026, 10, 29, 12, 5, tzinfo=timezone.utc)
    _completed_row(store, source='omi')
    store.rows[CONV_PATH]['started_at'] = started
    store.rows[CONV_PATH]['finished_at'] = finished
    secondary_path = ('users', 'u', 'conversations', 'conversation-2')
    store.rows[secondary_path] = {
        'id': 'conversation-2',
        'status': 'completed',
        'discarded': True,
        'started_at': started,
        'finished_at': finished,
        'source': 'omi',
        'data_protection_level': 'standard',
    }
    primary = NS(conversation_id='conversation-1', started_at=started, finished_at=finished, source='omi')
    secondary = NS(conversation_id='conversation-2', started_at=started, finished_at=finished, source='omi')
    linked = db.link_duplicate_capture('u', primary, secondary, {'gap_seconds': 3.0}, firestore_client=store)
    assert linked is False
    assert store.body_runs == 1
    assert store.attempts == 0
    assert 'external_data' not in store.rows[secondary_path]


def test_translation_materialization_commit_contention_replays(create_world):
    store = create_world
    _completed_row(
        store,
        transcript_segments=[speech('s0', 'Hello')],
    )
    store.rows[CONV_PATH]['transcript_segments'][0]['speaker'] = ''
    store.commit_errors = [Aborted(CONTENTION_MESSAGE)]
    result = db.materialize_translation('u', 'conversation-1', 's0', 'Hello', 'fr', 'Bonjour', firestore_client=store)
    assert isinstance(result, dict)
    assert result['translations'] == [{'lang': 'fr', 'text': 'Bonjour'}]
    assert store.attempts == 1
    assert store.body_runs == 2
    assert store.rows[CONV_PATH]['translation_materializations_compressed'] is True


def test_translation_materialization_locked_row_refuses_without_replay(create_world):
    store = create_world
    _completed_row(store, transcript_segments=[speech('s0', 'Hello')], is_locked=True)
    result = db.materialize_translation('u', 'conversation-1', 's0', 'Hello', 'fr', 'Bonjour', firestore_client=store)
    assert result is None
    assert store.body_runs == 1
    assert store.attempts == 0


def test_reserve_share_email_commit_contention_replays_and_reclaims(create_world):
    store = create_world
    _completed_row(store)
    fake_field_path = type(
        'FakeFieldPath',
        (),
        {
            '__init__': lambda self, *parts: None,
            'to_api_repr': lambda self: 'share_email_in_flight.a@example.com',
        },
    )
    import google.cloud.firestore_v1.field_path as field_path_module

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(field_path_module, 'FieldPath', fake_field_path)
        store.commit_errors = [Aborted(CONTENTION_MESSAGE)]
        to_dispatch, already_sent, in_flight = db.reserve_share_email_recipients(
            'u', 'conversation-1', ['a@example.com'], now_epoch=1000.0
        )
    assert to_dispatch == ['a@example.com']
    assert already_sent == []
    assert in_flight == []
    assert store.attempts == 1
    assert store.body_runs == 2


def test_reserve_share_email_already_sent_never_reclaims(create_world):
    store = create_world
    _completed_row(store, share_email_sent_to=['a@example.com'])
    fake_field_path = type(
        'FakeFieldPath',
        (),
        {
            '__init__': lambda self, *parts: None,
            'to_api_repr': lambda self: 'share_email_in_flight.a@example.com',
        },
    )
    import google.cloud.firestore_v1.field_path as field_path_module

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(field_path_module, 'FieldPath', fake_field_path)
        to_dispatch, already_sent, in_flight = db.reserve_share_email_recipients(
            'u', 'conversation-1', ['a@example.com'], now_epoch=1000.0
        )
    assert to_dispatch == []
    assert already_sent == ['a@example.com']
    assert store.body_runs == 1
    assert store.attempts == 0


def test_reserve_share_email_fresh_in_flight_claim_elsewhere(create_world):
    store = create_world
    _completed_row(store)
    fake_field_path = type(
        'FakeFieldPath',
        (),
        {
            '__init__': lambda self, *parts: None,
            'to_api_repr': lambda self: 'share_email_in_flight.a@example.com',
        },
    )
    import google.cloud.firestore_v1.field_path as field_path_module

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(field_path_module, 'FieldPath', fake_field_path)
        store.rows[CONV_PATH]['share_email_in_flight'] = {'a@example.com': 995.0}
        to_dispatch, already_sent, in_flight = db.reserve_share_email_recipients(
            'u', 'conversation-1', ['a@example.com'], now_epoch=1000.0
        )
    assert to_dispatch == []
    assert in_flight == ['a@example.com']
    assert store.body_runs == 1
    assert store.attempts == 0


def test_level_migration_replays_per_conversation_and_skips_batched_photos(create_world):
    from types import SimpleNamespace as NS
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreCollection

    store = create_world
    _completed_row(store)
    reference = store.collection('users').document('u').collection('conversations').document('conversation-1')

    def fake_get_all(references, *, field_paths):
        assert field_paths, 'the migration read is projected'
        return [NS(exists=True, id='conversation-1', reference=reference)]

    def fake_select(self, fields):
        return NS(stream=lambda: iter(()))

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(store, 'get_all', fake_get_all, raising=False)
        mp.setattr(store, 'batch', lambda: NS(commit=lambda: None), raising=False)
        mp.setattr(StrictFirestoreCollection, 'select', fake_select, raising=False)
        migrated = db.migrate_conversations_level_batch('u', ['conversation-1'], 'enhanced')

    assert migrated is None or migrated == [] or migrated is not False
    assert store.rows[CONV_PATH]['data_protection_level'] == 'enhanced'
    assert store.body_runs == 1
    assert store.attempts == 0


def test_level_migration_read_contention_replays(create_world):
    from types import SimpleNamespace as NS
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreCollection

    store = create_world
    _completed_row(store)
    reference = store.collection('users').document('u').collection('conversations').document('conversation-1')

    def fake_get_all(references, *, field_paths):
        return [NS(exists=True, id='conversation-1', reference=reference)]

    def fake_select(self, fields):
        return NS(stream=lambda: iter(()))

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(store, 'get_all', fake_get_all, raising=False)
        mp.setattr(store, 'batch', lambda: NS(commit=lambda: None), raising=False)
        mp.setattr(StrictFirestoreCollection, 'select', fake_select, raising=False)
        store.read_errors = [Aborted(CONTENTION_MESSAGE)]
        db.migrate_conversations_level_batch('u', ['conversation-1'], 'enhanced')

    assert store.rows[CONV_PATH]['data_protection_level'] == 'enhanced'
    assert store.attempts == 1
    assert store.body_runs == 2


def test_level_migration_already_at_target_refuses_without_replay(create_world):
    from types import SimpleNamespace as NS
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreCollection

    store = create_world
    _completed_row(store, data_protection_level='enhanced')
    reference = store.collection('users').document('u').collection('conversations').document('conversation-1')

    def fake_get_all(references, *, field_paths):
        return [NS(exists=True, id='conversation-1', reference=reference)]

    def fake_select(self, fields):
        return NS(stream=lambda: iter(()))

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(store, 'get_all', fake_get_all, raising=False)
        mp.setattr(store, 'batch', lambda: NS(commit=lambda: None), raising=False)
        mp.setattr(StrictFirestoreCollection, 'select', fake_select, raising=False)
        db.migrate_conversations_level_batch('u', ['conversation-1'], 'enhanced')

    assert store.body_runs == 1
    assert store.attempts == 0
    assert store.rows[CONV_PATH]['data_protection_level'] == 'enhanced'


# ── The session teardown that motivated the fix ────────────────────────────


class _StoreBackend:
    """Persistence.call that runs lifecycle/store functions against the store."""

    def __init__(self, store):
        self.store = store
        self.call_log = []

    async def __call__(self, fn, *args, **kwargs):
        self.call_log.append(getattr(fn, '__name__', str(fn)))
        return fn(*args, **kwargs)


class _SessionHost:
    """Minimal listen host driving the real controller bootstrap chain."""

    def __init__(self, store, open_error=None):
        self.request = SimpleNamespace(
            uid='u',
            source='omi',
            conversation_role=None,
            onboarding_mode=False,
            call_id=None,
            geolocation=None,
        )
        self.state = SimpleNamespace(
            current_conversation_id=None,
            active=True,
            capture_timeline={},
            conversations_awaiting_capture_origin=set(),
            conversations_legacy_locked=set(),
            conversation_capture_origins={},
            live_transcription_failed=False,
        )
        self.recording_session_id = 'rs-1'
        self.recording_session_ids_by_conversation = {}
        self.is_multi_channel = False
        self.client_conversation_id = None
        self.onboarding_admitted = False
        self.conversation_creation_timeout = 120
        self.use_custom_stt = False
        self.private_cloud_sync_enabled = False
        self.client_device_context = SimpleNamespace(client_device_id='dev-1', platform='test')
        self.client_kind = 'test'
        self.language = 'en'
        self.speakers = SimpleNamespace(
            refresh_for_conversation=AsyncMock(),
            diagnostics=None,
            queue=SimpleNamespace(),
            tasks=SimpleNamespace(),
            note_rollover_carry=None,
        )
        self.transcripts = SimpleNamespace(flush_speaker_assignments=AsyncMock())
        self.send_events = []
        self._store = store
        self._open_error = open_error
        self.persistence = self._persistence()

    def _persistence(self):
        host = self
        store = self._store

        async def call(fn, *args, **kwargs):
            name = getattr(fn, '__name__', str(fn))
            if name == 'open_live_recording_session':
                if host._open_error is not None:
                    raise host._open_error
                return {
                    'recording_session_id': host.recording_session_id,
                    'conversation_id': 'conversation-1',
                    'lifecycle_version': 1,
                    'lifecycle_phase': 'in_progress',
                    'lifecycle_sequence': 0,
                    'mapping_conflict': False,
                    'requires_rollover': False,
                    'conversation_snapshot': store.rows.get(CONV_PATH),
                    'conversation_snapshot_known': True,
                }
            if name == 'retrieve_in_progress_conversation':
                return store.rows.get(CONV_PATH)
            return fn(*args, **kwargs)

        return SimpleNamespace(call=call)

    def send_event(self, event):
        self.send_events.append(event)

    async def wait(self, seconds: float) -> bool:
        return False

    def spawn(self, coro, name=None):
        coro.close()

    def on_conversation_processed(self, conversation_id):
        pass


def _aged_in_progress_row(store):
    """An attachable in-progress row aged past its continuation window.

    ``has_content`` is set so prepare()'s process_and_create_new branch does
    not drive the real (external-finalizer) processing path — this suite
    pins the storage-classification arm, not finalization.
    """
    store.rows[CONV_PATH] = {
        'id': 'conversation-1',
        'status': 'in_progress',
        'created_at': _now() - timedelta(hours=1),
        'started_at': _now() - timedelta(hours=1),
        'finished_at': _now() - timedelta(hours=1),
        'source': 'omi',
        'client_device_id': 'dev-1',
        'has_content': True,
        'structured': {'title': 'Live row'},
        'data_protection_level': 'standard',
    }
    return store.rows[CONV_PATH]


def _prepare_controller(store, create_world):
    """The REAL controller bootstrap chain against the fault-injecting store.

    `create_new_in_progress_conversation` runs for real — payload build,
    session open, `lifecycle.create_in_progress_conversation`, the budgeted
    upsert — against the store, so the budget is exercised on the exact
    path the prod escape took. Only the two edges that fan OUT of the
    create boundary are stubbed: continuation resolution (its pointer
    service is out of scope here) and the speaker refresh (its own store
    contract). The recovery generation uses a fresh conversation id, and
    the in-pointer Redis write is absorbed the way `_cache_set_fail_open`
    does under a capacity fault.
    """
    host = _SessionHost(store)

    def make_binding(recording_session_id, conversation_id, snapshot):
        return {
            'recording_session_id': recording_session_id,
            'conversation_id': conversation_id,
            'lifecycle_version': 1,
            'lifecycle_phase': 'in_progress',
            'lifecycle_sequence': 0,
            'mapping_conflict': False,
            'requires_rollover': False,
            'conversation_snapshot': snapshot,
            'conversation_snapshot_known': True,
        }

    async def call(fn, *args, **kwargs):
        name = getattr(fn, '__name__', str(fn))
        if name == 'open_live_recording_session':
            session_id = args[1] if len(args) > 1 else kwargs.get('recording_session_id')
            proposed = args[2] if len(args) > 2 else kwargs.get('proposed_conversation_id')
            if session_id == 'rs-1':
                # Only the original prepare() open resolves to the aged row;
                # every later generation binds its own fresh proposal.
                return make_binding(session_id, 'conversation-1', dict(store.rows[CONV_PATH]))
            return make_binding(session_id, proposed, None)
        if name == 'retrieve_in_progress_conversation':
            return store.rows[CONV_PATH]
        if name == 'get_conversation':
            uid, conversation_id = args[0], args[1]
            return store.rows.get(('users', uid, 'conversations', conversation_id))
        if name == 'set_in_progress_conversation_id':
            return None
        return fn(*args, **kwargs)

    host.persistence = SimpleNamespace(call=call)
    controller = LiveConversationController(host)

    async def no_continuation(proposed=None):
        return None

    async def no_speaker_refresh(conversation_id, **kwargs):
        return None

    async def no_active_meeting():
        return None

    def no_session_event(binding, recording_session_id, **kwargs):
        return None

    controller._continuation = no_continuation
    controller._refresh_speakers = no_speaker_refresh
    controller._active_calendar_meeting = no_active_meeting
    controller.send_conversation_session = no_session_event
    return controller


async def _run_prepare_with_failing_create(store, create_world, create_errors):
    """prepare() whose bootstrap create hits `create_errors` on the store.

    The aged in-progress row forces the create (process_and_create_new);
    each commit attempt raises the next injected fault until the list is
    empty, then the real transactional body commits.
    """
    _aged_in_progress_row(store)
    controller = _prepare_controller(store, create_world)
    create_world.commit_errors = list(create_errors)
    return await controller.prepare()


async def test_prepare_create_contention_burst_recovers_within_the_budget(create_world):
    """A mid-bootstrap contention burst replays and the session boots.

    The REAL controller bootstrap chain runs: the aged in-progress row
    forces the rollover create through `lifecycle.create_in_progress_
    conversation` onto the budgeted upsert. Two aborted commits replay on
    fresh attempts, the third commits, and prepare() returns with the next
    generation adopted — before the fix the first abort escaped prepare()
    as uvicorn's `Exception in ASGI application` and tore the session down.
    """
    result = await _run_prepare_with_failing_create(
        create_world, create_world, [Aborted(CONTENTION_MESSAGE), Aborted(CONTENTION_MESSAGE)]
    )
    assert result == 'conversation-1'
    assert create_world.attempts >= 2, 'the burst replayed on fresh attempts'
    stored = create_world.rows[CONV_PATH]
    assert stored['status'] == 'in_progress'
    assert stored['structured']['title'] == 'Live row'


async def test_prepare_create_drained_budget_still_ends_the_session(create_world):
    """A burst outliving the budget fails the boot — bounded, not infinite.

    The contract under fix is the replay: one burst drains, the ASGI frame
    sees the exhausted-transient shape (classified as contention by every
    caller arm), and the next reconnect retries the open. The boot failure
    is the bounded terminal, never a silent retry loop.
    """
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted):
        await _run_prepare_with_failing_create(create_world, create_world, [Aborted(CONTENTION_MESSAGE)] * 5)
    assert create_world.attempts == 4
    assert (
        CONV_PATH in create_world.rows and create_world.rows[CONV_PATH]['status'] == 'in_progress'
    ), 'an exhausted burst leaves the aged row untouched'
