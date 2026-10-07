"""Explicit driver registry for every statically discovered ``database.*`` querying function.

Each entry is either a ``DriverEntry`` (driven across the full product of its
shape-affecting parameter domains), a ``CoveredByEntry`` (query shapes are
exercised by named drivers — private helpers and thin wrappers), or a
``SkipEntry`` (reasoned non-driven candidate). Entries are never generated at
test time: a newly discovered function has no entry until one is added here.
"""

from __future__ import annotations

import importlib
import unittest.mock
from datetime import timedelta, timezone
from types import SimpleNamespace
from typing import Any

from tests.support.firestore_query_drivers import (
    FROZEN_LATER,
    FROZEN_NOW,
    FROZEN_TODAY,
    SHAPE_UID,
    CallerProfile,
    CoveredByEntry,
    DriverEntry,
    SkipEntry,
    noop,
    ref_collection,
    ref_document,
    ref_transaction,
)
from tests.support.firestore_conversation_profiles import (
    COUNT_PROFILES,
    PHOTO_PROFILES,
    RECIPE_PROFILES,
    SCAN_PROFILES,
    WITHOUT_PHOTOS_PROFILES,
)
from tests.support import firestore_outside_query_drivers as outside_drivers
from models.announcement import AnnouncementType
from models.candidate import CandidateStatus
from models.chat_first import ChatFirstSubject
from models.frame_request import FrameRequestState
from models.goal import GoalRelationshipDisposition, GoalStatus
from models.task_recommendation import (
    FeedbackSubjectKind,
    NormalizedContextSnapshot,
    OpenLoopSnapshot,
    OutcomeCreate,
    TaskIntelligenceOutcomeCode,
    WhatMattersNowProjection,
)
from models.workstream import TaskGoalLinkImportRequest
from database.memory_outbox_worker import CanonicalMemoryOutboxSideEffects, CanonicalMemoryOutboxWorkerConfig
from utils.other.list_budget import ListReadBudget
from database.memory_vector_repair_outbox_worker import VectorRepairOutboxWorkerTickConfig

UID = SHAPE_UID
T0 = FROZEN_NOW
T1 = FROZEN_LATER
D0 = FROZEN_TODAY

_LIMIT = (50, 'page bound; fixed small positive, not filter-affecting')
_LIMIT_OPT = (None, 'optional page bound; absent does not change filters')
_OFFSET = (0, 'row window; fixed, not filter-affecting')
_PAGE = (25, 'scan/page bound; fixed small positive, not filter-affecting')
_BUDGET = (None, 'request budget; RPC timeout/charge only, no filter effect')
_EXTRA_FIELDS = (('provenance',), 'widens the select projection only; no filter or order effect')
_DAYS = (30, 'window length; fixed, not filter-affecting')
_NOW = (None, 'defaults to frozen clock; none/set produce identical filters')
_NOOP = (noop, 'callback side-effect neutralized; does not affect filters')


def _seed(path: str, data: dict):
    def apply(client, combo, trial):
        client.documents[path] = dict(data)

    return apply


def _queue_conversation_scan_pages(client, combo, trial):
    """One full batch page then an empty one, forcing a ``start_after`` cursor."""
    snapshot = client.snapshot(
        f'users/{UID}/conversations/conv-1',
        {'id': 'conv-1', 'created_at': T0, 'discarded': False, 'data_protection_level': 'standard'},
    )
    client.queue_results([snapshot])
    client.queue_results([])


def _queue_conversation_scan_page(client, combo, trial):
    """One short page: the recipe batches (50/100) end the scan without a cursor."""
    snapshot = client.snapshot(
        f'users/{UID}/conversations/conv-1',
        {'id': 'conv-1', 'created_at': T0, 'discarded': False, 'data_protection_level': 'standard'},
    )
    client.queue_results([snapshot])


def _redis_noop(dotted: str):
    """Return a patcher stubbing a bound redis helper with a callable returning ``None``."""

    def patcher(client):
        module_name, attr = dotted.rsplit('.', 1)
        module = importlib.import_module(module_name)
        return unittest.mock.patch.object(module, attr, lambda *a, **k: None)

    return patcher


def _stub(dotted: str, result: Any):
    """Return a patcher replacing ``dotted`` with a callable returning ``result``."""

    def patcher(client):
        module_name, attr = dotted.rsplit('.', 1)
        module = importlib.import_module(module_name)
        return unittest.mock.patch.object(module, attr, lambda *a, **k: result)

    return patcher


_CACHE_MISS = SimpleNamespace(mode='MISS', data=None)
_DEV_KEY = 'omi_dev_' + 'a' * 32
_MCP_KEY = 'omi_mcp_' + 'a' * 32

BODY_DIGEST = {
    'database.proactivity_producers.mentor_history_query': '716c4f332e0ff0cf6fda3bcea41f479ce3bb7eb2956c8bfe37c61e0baabbfdb3',
    'database.proactivity_producers.recent_mentor_query': 'dc28a1084121daa40a430764d1c638ec4fe090e66dff499e0bec152444035dee',
    'database.proactivity_producers.task_items_query': '9e98b929e35f9118cdb76076bb526e41a5383d94d0304f098d17a0a2a3bc3cb5',
    'database.proactivity.cohort_query': 'b14c1c6f3a2f47db38dd468da1bf6b51054d27e6418d813a614cc5b9e1a7a698',
    'database.proactivity.feed_query': '9426ea3253186857c638371d1bcebb7007b92a9430aaad1db5e49e96465ddb84',
    'database.action_items._apply_action_item_date_filters': 'b69dc9810414753e0b0715560b872121566b965f36bdefc5b91869587037336f',
    'database.action_items._harvest_legacy_docs': 'dbd3731b503ea8c2f6b9d98bf7cc4a6ffd85bf530ea09660539fb6569ae98114',
    'database.action_items._probe_legacy_completion_rows': '57a375ed6e56cdd9c6156ef4cee5944dbfb089a2477844c5b9c52de9a3214a30',
    'database.conversation_finalization_jobs._create_or_get_finalization_intent_txn': 'c7310ad7eaab2e1085c5493e4e2b6c7f618ea88f0aae670e4b4f84dd3e828b59',
    'database.firestore_query_types.FirestoreQuerySpec.build': '2c26a157a8e87be2bcfef668e3bd5cdc0a9c0d96e0b56bada98c30741c8be01a',
    'database.sync_backfill_sequencer._pending_for_uid': '0215df28fdc7128cc68bf0abf087e4f98854698851b22821008460b68b699ea9',
    'database.workstreams.import_task_goal_links': 'd0c7c57d032067c3d72829663dd6f249073e6438ec7adac966b617fe3eaf1c56',
    'database.smart_merge.absorb_conversation': '56123c7f51757edce7c7f0ed8b61fc718e080b542ce5a153bb5b83e6a1a84ca5',
}

DRIVERS: dict[str, DriverEntry] = {}
COVERED_BY: dict[str, CoveredByEntry] = {}
SKIPS: dict[str, SkipEntry] = {}


def _add(entry: DriverEntry | CoveredByEntry | SkipEntry) -> None:
    if entry.function in DRIVERS or entry.function in COVERED_BY or entry.function in SKIPS:
        raise ValueError(f'duplicate registry entry: {entry.function}')
    if isinstance(entry, DriverEntry):
        DRIVERS[entry.function] = entry
    elif isinstance(entry, CoveredByEntry):
        COVERED_BY[entry.function] = entry
    else:
        SKIPS[entry.function] = entry


_add(
    DriverEntry(
        'database._client.delete_collection_recursive',
        base={'collection_ref': ref_collection('users/shape-user/trash')},
        neutrals={'batch_size': _PAGE},
    )
)
_add(DriverEntry('database._client.get_users_uid'))

_add(DriverEntry('database.account_deletion_transitions.read_agent_vm_migration_journals', base={'uid': UID}))

_add(
    DriverEntry(
        'database.action_item_sync.get_action_items_sync_page',
        base={'uid': UID},
        domains={'updated_since': [None, T0], 'after': [None, (T0, 'doc-1')]},
        neutrals={'limit': _LIMIT},
    )
)

_add(
    CoveredByEntry(
        'database.action_items._apply_action_item_date_filters',
        covered_by=('database.action_items.get_action_items',),
        reason='pure query-builder helper; it only attaches wheres and the terminal '
        'stream executes inside get_action_items, so it never appears as a caller',
        expect_observed=False,
        body_digest=BODY_DIGEST['database.action_items._apply_action_item_date_filters'],
    )
)
_add(
    CoveredByEntry(
        'database.action_items._count_query',
        covered_by=('database.action_items.get_action_items',),
        reason='count aggregation wrapper observed inside the get_action_items driver only',
    )
)
_add(
    CoveredByEntry(
        'database.action_items._harvest_legacy_docs',
        covered_by=('database.action_items.get_action_items',),
        reason='runs on every call but delegates its terminal stream to _count_query/'
        '_iter_query_pages, so those helpers own the recorded caller',
        expect_observed=False,
        body_digest=BODY_DIGEST['database.action_items._harvest_legacy_docs'],
    )
)
_add(
    CoveredByEntry(
        'database.action_items._iter_query_pages',
        covered_by=(
            'database.action_items.get_action_item_ids',
            'database.action_items.get_active_action_item_by_description',
            'database.action_items.get_scores',
            'database.action_items.get_visible_action_item_ids',
            'database.action_items.iter_all_action_items',
        ),
        reason='page iterator reached by each listed consumer driver',
    )
)
_add(
    CoveredByEntry(
        'database.action_items._probe_legacy_completion_rows',
        covered_by=('database.action_items.get_action_items',),
        reason='runs on every call but its terminal stream is recorded under '
        '_count_query/_iter_query_pages, which own the caller frame',
        expect_observed=False,
        body_digest=BODY_DIGEST['database.action_items._probe_legacy_completion_rows'],
    )
)
_add(
    CoveredByEntry(
        'database.action_items._stream_action_items_bounded',
        covered_by=(
            'database.action_items.get_action_items',
            'database.action_items.get_action_items_by_conversation',
        ),
        reason='bounded stream wrapper observed inside both listed consumers',
    )
)


def _seed_action_items_control(client, combo, trial):
    """Trial 0 leaves the control document absent (generation 0).

    Trial 1 seeds ``task_intelligence_control/state`` with a nonzero
    ``account_generation`` so the idempotency lookup adds its
    ``account_generation ==`` predicate and the two-equality shape is
    captured instead of only the single-field ``idempotency_key`` query.
    """
    if trial == 1:
        client.documents[f'users/{UID}/task_intelligence_control/state'] = {'account_generation': 2}


_add(
    DriverEntry(
        'database.action_items.create_action_item',
        base={'uid': UID, 'action_item_data': {'description': 'shape-task'}},
        domains={'idempotency_key': [None, 'shape-key']},
        neutrals={'document_id': (None, 'optional doc id; absent does not change query')},
        setup=_seed_action_items_control,
        trials=2,
    )
)
_add(
    DriverEntry(
        'database.action_items.delete_action_items_for_conversation', base={'uid': UID, 'conversation_id': 'conv-1'}
    )
)
_add(DriverEntry('database.action_items.get_action_item_ids', base={'uid': UID}))
_add(
    DriverEntry(
        'database.action_items.get_action_items',
        base={'uid': UID},
        domains={
            'conversation_id': [None, 'conv-1'],
            'completed': [None, False, True],
            'start_date': [None, T0],
            'end_date': [None, T1],
            'due_start_date': [None, T0],
            'due_end_date': [None, T1],
        },
        neutrals={'limit': _LIMIT_OPT, 'offset': _OFFSET, 'budget': _BUDGET, 'extra_fields': _EXTRA_FIELDS},
    )
)
_add(
    DriverEntry(
        'database.action_items.get_action_items_by_conversation',
        base={'uid': UID, 'conversation_id': 'conv-1'},
        neutrals={'extra_fields': _EXTRA_FIELDS},
    )
)
_add(
    DriverEntry(
        'database.action_items.get_action_items_count_by_conversation', base={'uid': UID, 'conversation_id': 'conv-1'}
    )
)
_add(
    DriverEntry(
        'database.action_items.get_active_action_item_by_description', base={'uid': UID, 'description': 'shape-task'}
    )
)
_add(
    DriverEntry(
        'database.action_items.get_daily_score',
        base={'uid': UID},
        domains={'date': [None, '2026-01-01']},
        neutrals={'tz': (timezone.utc, 'presentation tz; does not change filters')},
    )
)
_add(DriverEntry('database.action_items.get_pending_apple_reminders_sync', base={'uid': UID}))
_add(
    DriverEntry(
        'database.action_items.get_scores',
        base={'uid': UID},
        domains={'date': [None, '2026-01-01']},
        neutrals={'tz': (timezone.utc, 'presentation tz; does not change filters')},
    )
)
_add(
    DriverEntry(
        'database.action_items.get_visible_action_item_ids', base={'uid': UID}, domains={'completed': [False, True]}
    )
)
_add(DriverEntry('database.action_items.iter_all_action_items', base={'uid': UID}))
_add(
    DriverEntry(
        'database.action_items.retire_action_items_for_conversation',
        base={'uid': UID, 'conversation_id': 'conv-1', 'active_ids': ['id-1', 'id-2']},
        neutrals={'replacements': (None, 'optional rename map; not filter-affecting')},
    )
)
_add(DriverEntry('database.action_items.unlock_all_action_items', base={'uid': UID}))

_add(
    DriverEntry(
        'database.advice.get_advice',
        base={'uid': UID},
        domains={'category': [None, 'cat-1'], 'include_dismissed': [False, True]},
        neutrals={'limit': _LIMIT, 'offset': _OFFSET},
    )
)
_add(DriverEntry('database.advice.mark_all_advice_read', base={'uid': UID}))

_add(
    DriverEntry(
        'database.announcements.get_all_announcements',
        domains={'announcement_type': [None] + list(AnnouncementType), 'active_only': [False, True]},
    )
)
_add(DriverEntry('database.announcements.get_app_changelogs', base={'from_version': '1.0.0', 'to_version': '2.0.0'}))
_add(DriverEntry('database.announcements.get_app_features', base={'app_version': '2.0.0'}))
_add(DriverEntry('database.announcements.get_dismissed_announcement_ids', base={'uid': UID}))
_add(
    DriverEntry(
        'database.announcements.get_firmware_features',
        base={'firmware_version': '2.0.0'},
        domains={'device_model': [None, 'devkit']},
    )
)
_add(DriverEntry('database.announcements.get_general_announcements', domains={'last_checked_at': [None, T0]}))
_add(
    DriverEntry(
        'database.announcements.get_pending_announcements',
        base={'uid': UID, 'app_version': '2.0.0', 'platform': 'ios', 'trigger': 'on_open'},
        domains={'firmware_version': [None, '2.0.0'], 'device_model': [None, 'devkit']},
    )
)
_add(
    DriverEntry(
        'database.announcements.get_recent_changelogs',
        domains={'max_version': [None, '2.0.0']},
        neutrals={'limit': _LIMIT},
    )
)

_add(DriverEntry('database.apps.get_api_key_by_hash_db', base={'app_id': 'app-1', 'hashed_key': 'hash-1'}))
_add(DriverEntry('database.apps.get_app_chat_message_sent_usage_count_db', base={'app_id': 'app-1'}))
_add(DriverEntry('database.apps.get_app_memory_created_integration_usage_count_db', base={'app_id': 'app-1'}))
_add(DriverEntry('database.apps.get_app_memory_prompt_usage_count_db', base={'app_id': 'app-1'}))
_add(DriverEntry('database.apps.get_app_usage_count_db', base={'app_id': 'app-1'}))
_add(DriverEntry('database.apps.get_app_usage_history_db', base={'app_id': 'app-1'}))
_add(
    DriverEntry(
        'database.apps.get_apps_for_tester_db', base={'uid': UID}, setup=_seed(f'testers/{UID}', {'apps': ['app-1']})
    )
)
_add(DriverEntry('database.apps.get_audio_apps_count', base={'app_ids': ['app-1', 'app-2']}))
_add(DriverEntry('database.apps.get_omi_persona_apps_by_uid_db', base={'uid': UID}))
_add(DriverEntry('database.apps.get_omi_personas_by_uid_db', base={'uid': UID}))
_add(DriverEntry('database.apps.get_persona_by_twitter_handle_db', base={'handle': 'shape-handle'}))
_add(DriverEntry('database.apps.get_persona_by_uid_db', base={'uid': UID}))
_add(DriverEntry('database.apps.get_persona_by_username_db', base={'username': 'shape-name'}))
_add(
    DriverEntry(
        'database.apps.get_persona_by_username_twitter_handle_db',
        base={'username': 'shape-name', 'handle': 'shape-handle'},
    )
)
_add(DriverEntry('database.apps.get_personas_by_username_db', base={'persona_id': 'persona-1'}))
_add(DriverEntry('database.apps.get_popular_apps_db'))
_add(DriverEntry('database.apps.get_private_apps_db', base={'uid': UID}))
_add(
    DriverEntry(
        'database.apps.get_public_approved_apps_cached_db',
        patchers=(
            _redis_noop('database.apps.get_generic_cache'),
            _redis_noop('database.apps.set_generic_cache'),
        ),
    )
)
_add(DriverEntry('database.apps.get_public_approved_apps_db'))
_add(DriverEntry('database.apps.get_public_unapproved_apps_db', base={'uid': UID}))
_add(DriverEntry('database.apps.get_unapproved_public_apps_db'))
_add(DriverEntry('database.apps.get_user_persona_by_uid', base={'uid': UID}))
_add(DriverEntry('database.apps.list_api_keys_db', base={'app_id': 'app-1'}))
_add(DriverEntry('database.apps.migrate_app_owner_id_db', base={'new_id': 'new-1', 'old_id': 'old-1'}))
_add(
    DriverEntry(
        'database.apps.search_apps_db',
        base={'uid': UID},
        domains={
            'category': [None, 'cat-1'],
            'capability': [None, 'cap-1'],
            'my_apps': [False, True],
            'installed_apps': [False, True],
            'enabled_app_ids': [None, ['app-1'], ['app-1', 'app-2'], [f'app-{i}' for i in range(31)]],
        },
        patchers=(
            _redis_noop('database.apps.get_generic_cache'),
            _redis_noop('database.apps.set_generic_cache'),
        ),
    )
)

_add(DriverEntry('database.calendar_meetings.delete_old_meetings', base={'uid': UID, 'before_date': T0}))
_add(
    DriverEntry(
        'database.calendar_meetings.get_meeting_id_by_calendar_event',
        base={'uid': UID, 'calendar_event_id': 'ev-1', 'calendar_source': 'gcal'},
    )
)
_add(
    DriverEntry(
        'database.calendar_meetings.get_meetings_in_time_range', base={'uid': UID, 'start_time': T0, 'end_time': T1}
    )
)
_add(
    DriverEntry(
        'database.calendar_meetings.list_meetings',
        base={'uid': UID},
        domains={'start_date': [None, T0], 'end_date': [None, T1]},
        neutrals={'limit': _LIMIT},
    )
)

_add(
    DriverEntry(
        'database.candidate_integration_outbox.list_candidate_integration_dispatches',
        base={'uid': UID, 'account_generation': 1},
        neutrals={'limit': _LIMIT},
    )
)
_add(
    DriverEntry(
        'database.candidates.list_candidates',
        base={'uid': UID},
        neutrals={'limit': _LIMIT, 'offset': _OFFSET},
        profiles=(
            CallerProfile(
                'candidate-list',
                {'status': [None] + list(CandidateStatus), 'account_generation': [0, 1]},
            ),
            CallerProfile('candidate-suggested', {'status': [None], 'account_generation': [0, 1]}),
        ),
    )
)


def _candidates_page_cursor(client, combo, trial):
    if combo.get('cursor') is not None:
        combo['cursor'] = client.snapshot(f'users/{UID}/candidates/cursor-1', {'created_at': T0})


_add(
    DriverEntry(
        'database.candidates.list_candidates_compatibility_page',
        base={'uid': UID, 'account_generation': 1},
        domains={'cursor': [None, True]},
        neutrals={'limit': _LIMIT},
        setup=_candidates_page_cursor,
    )
)

_add(DriverEntry('database.chat.acquire_chat_session', base={'uid': UID}, domains={'app_id': [None, 'app-1']}))
_add(
    DriverEntry(
        'database.chat.add_app_message',
        base={'text': 'shape-text', 'app_id': 'app-1', 'uid': UID},
        domains={'conversation_id': [None, 'conv-1']},
        neutrals={'proactivity_item_id': (None, 'internal message mapping only; does not change query shape')},
    )
)
_add(
    DriverEntry(
        'database.chat.add_integration_chat_message', base={'text': 'shape-text', 'app_id': 'app-1', 'uid': UID}
    )
)
_add(
    DriverEntry(
        'database.chat.batch_delete_messages',
        base={'parent_doc_ref': ref_document('users/shape-user')},
        domains={'app_id': [None, 'app-1'], 'chat_session_id': [None, 'sess-1']},
        neutrals={'batch_size': _PAGE},
    )
)
_add(
    DriverEntry(
        'database.chat.clear_chat',
        base={'uid': UID},
        domains={'app_id': [None, 'app-1'], 'chat_session_id': [None, 'sess-1']},
        setup=_seed(f'users/{UID}', {'fcm_token': 'legacy-1'}),
    )
)
_add(
    DriverEntry(
        'database.chat.delete_chat_session',
        base={'uid': UID, 'chat_session_id': 'sess-1'},
        domains={'cascade_messages': [False, True]},
        setup=_seed(f'users/{UID}/chat_sessions/sess-1', {'app_id': 'app-1'}),
    )
)
_add(
    DriverEntry(
        'database.chat.delete_messages',
        base={'uid': UID},
        domains={'app_id': [None, 'app-1'], 'session_id': [None, 'sess-1']},
    )
)
_add(
    DriverEntry(
        'database.chat.get_app_messages',
        base={'uid': UID, 'app_id': 'app-1'},
        domains={'include_conversations': [False, True]},
        neutrals={'limit': _LIMIT},
    )
)
_add(
    DriverEntry(
        'database.chat.get_cache_aligned_messages',
        base={'uid': UID},
        domains={'app_id': [None, 'app-1'], 'chat_session_id': [None, 'sess-1']},
    )
)
_add(
    DriverEntry(
        'database.chat.get_chat_files',
        base={'uid': UID},
        domains={'files_id': [None, ['file-1'], ['file-1', 'file-2']]},
    )
)
_add(
    DriverEntry(
        'database.chat.get_chat_files_desc',
        base={'uid': UID},
        domains={'files_id': [None, ['file-1'], ['file-1', 'file-2']]},
        neutrals={'limit': _LIMIT},
    )
)
_add(DriverEntry('database.chat.get_chat_session', base={'uid': UID}, domains={'app_id': [None, 'app-1']}))
_add(
    DriverEntry(
        'database.chat.get_chat_sessions',
        base={'uid': UID},
        domains={'app_id': [None, 'app-1'], 'starred': [None, False, True]},
        neutrals={'limit': _LIMIT, 'offset': _OFFSET},
    )
)
_add(DriverEntry('database.chat.get_chats_to_migrate', base={'uid': UID, 'target_level': 'level-2'}))
_add(DriverEntry('database.chat.get_message', base={'uid': UID, 'message_id': 'msg-1'}))
_add(DriverEntry('database.chat.get_message_count', base={'uid': UID}))
_add(
    DriverEntry(
        'database.chat.get_messages',
        base={'uid': UID},
        domains={
            'include_conversations': [False, True],
            'app_id': [None, 'app-1'],
            'chat_session_id': [None, 'sess-1'],
        },
        neutrals={'limit': _LIMIT, 'offset': _OFFSET},
    )
)


def _seed_reconcile_cursor(client, combo, trial):
    client.documents[f'users/{UID}/messages/msg-1'] = {
        'created_at': T0,
        'plugin_id': combo.get('app_id'),
        'chat_session_id': combo.get('chat_session_id'),
    }


_add(
    DriverEntry(
        'database.chat.get_messages_reconcile_page',
        base={'uid': UID},
        domains={
            'cursor_message_id': [None, 'msg-1'],
            'app_id': [None, 'app-1'],
            'chat_session_id': [None, 'sess-1'],
        },
        neutrals={'limit': _LIMIT},
        setup=_seed_reconcile_cursor,
    )
)
_add(DriverEntry('database.chat.iter_all_messages', base={'uid': UID}, neutrals={'batch_size': _PAGE}))
_add(
    DriverEntry(
        'database.chat.save_message',
        base={'uid': UID, 'text': 'shape-text', 'sender': 'user'},
        domains={'app_id': [None, 'app-1'], 'session_id': [None, 'sess-1']},
        neutrals={
            'metadata': (None, 'optional payload; not filter-affecting'),
            'content_blocks': (None, 'optional payload; not filter-affecting'),
            'client_message_id': (None, 'optional dedupe id; not filter-affecting'),
            'message_source': (None, 'provenance payload; not filter-affecting'),
            'journal_revision': (None, 'journal bookkeeping; not filter-affecting'),
        },
    )
)
_add(DriverEntry('database.chat.update_message_rating', base={'uid': UID, 'message_id': 'msg-1', 'rating': 1}))

_add(
    DriverEntry(
        'database.chat_first_delivery_attempts.repair_transient_dead_letters',
        base={'uid': UID, 'account_generation': 1, 'now': T0},
        neutrals={'limit': _LIMIT, 'requeue': _NOOP},
    )
)
_add(
    DriverEntry(
        'database.chat_first_intents.fetch_ready_intent_batch',
        base={'uid': UID, 'account_generation': 0},
        domains={
            'exclude_block_types': [None, {'block-1'}],
            'deferred_intent_ids': [None, {'intent-1'}],
            'now': [None, T0],
        },
        neutrals={'limit': _LIMIT},
    )
)
_add(
    DriverEntry(
        'database.chat_first_intents.fetch_ready_intents',
        base={'uid': UID, 'account_generation': 0},
        domains={'exclude_block_types': [None, {'block-1'}], 'now': [None, T0]},
        neutrals={'limit': _LIMIT},
    )
)
_add(
    DriverEntry(
        'database.chat_first_intents.has_active_sparse_cold_start_sequence', base={'uid': UID, 'account_generation': 0}
    )
)
_add(
    DriverEntry(
        'database.chat_first_intents.has_cold_start_intent_created_on',
        base={'uid': UID, 'account_generation': 0, 'date_value': D0},
    )
)
_add(
    DriverEntry(
        'database.chat_first_intents.release_due_deferrals',
        base={'uid': UID, 'account_generation': 0, 'now': T0},
        domains={'subject': [None, ChatFirstSubject(kind='task', id='sub-1')]},
    )
)

_add(
    DriverEntry(
        'database.conversation_finalization_jobs._conversation_has_finalization_content',
        base={
            'uid': UID,
            'conversation': {'transcript_segments': []},
            'conversation_ref': ref_document(f'users/{UID}/conversations/conv-1'),
            'transaction': ref_transaction(),
        },
    )
)
_add(
    CoveredByEntry(
        'database.conversation_finalization_jobs._create_or_get_finalization_intent_txn',
        covered_by=('database.conversation_finalization_jobs._conversation_has_finalization_content',),
        reason='orchestrator whose only querying dependency is the content probe, now driven '
        'directly; its transaction body runs inside the caller-supplied transaction only',
        expect_observed=False,
        body_digest=BODY_DIGEST['database.conversation_finalization_jobs._create_or_get_finalization_intent_txn'],
    )
)
_add(
    DriverEntry(
        'database.conversation_finalization_jobs.get_abandoned_byok_job_candidates',
        base={'abandoned_after': timedelta(minutes=10)},
        domains={'resume_after_path': [None, 'users/shape-user/jobs/job-1']},
        neutrals={'limit': _LIMIT, 'max_scan': (200, 'scan bound; fixed, not filter-affecting')},
    )
)
_add(DriverEntry('database.conversation_finalization_jobs.get_finalization_job_summary'))
_add(
    DriverEntry(
        'database.conversation_finalization_jobs.get_finalization_replay_candidates', neutrals={'limit': _LIMIT}
    )
)
_add(
    DriverEntry(
        'database.conversation_finalization_jobs.get_meeting_receipt_backfill_candidates',
        domains={'resume_after_path': [None, 'users/shape-user/receipts/r-1']},
        neutrals={'limit': _LIMIT, 'max_scan': (200, 'scan bound; fixed, not filter-affecting')},
    )
)
_add(
    DriverEntry(
        'database.conversation_finalization_jobs.get_meeting_receipt_reconcile_candidates',
        domains={'now': [None, T0]},
        neutrals={'limit': _LIMIT},
    )
)
_add(
    DriverEntry(
        'database.conversation_finalization_jobs.get_stale_processing_orphan_candidates',
        base={'stale_after': timedelta(minutes=10)},
        domains={'resume_after_path': [None, 'users/shape-user/jobs/job-1']},
        neutrals={'limit': _LIMIT, 'max_scan': (200, 'scan bound; fixed, not filter-affecting')},
    )
)
_add(
    DriverEntry(
        'database.conversation_finalization_jobs.scan_in_progress_conversations',
        domains={'resume_after_path': [None, 'users/shape-user/conversations/c-1']},
        neutrals={'page_size': _PAGE, 'max_scan': (200, 'scan bound; fixed, not filter-affecting')},
    )
)
_add(
    DriverEntry(
        'database.conversation_scan.iter_conversations',
        base={'uid': UID},
        profiles=SCAN_PROFILES,
        neutrals={
            'limit': (1000, 'visible-row work bound; fixed, not filter-affecting'),
            'batch': (1, 'page size; fixed small so one queued row forces a cursor page'),
            'budget': (
                ListReadBudget(
                    deadline_monotonic=12.0,
                    max_documents=2000,
                    clock=lambda: 0.0,
                    started_monotonic=0.0,
                ),
                'required scan budget; frozen clock, deep-copied fresh per trial',
            ),
        },
        setup=_queue_conversation_scan_pages,
    )
)
_add(
    DriverEntry(
        'database.conversation_scan.people_stats_scan',
        base={'uid': UID},
        profiles=(RECIPE_PROFILES[0],),
        neutrals={
            'budget': (
                ListReadBudget(
                    deadline_monotonic=12.0,
                    max_documents=2000,
                    clock=lambda: 0.0,
                    started_monotonic=0.0,
                ),
                'required scan budget; frozen clock, deep-copied fresh per trial',
            ),
        },
        setup=_queue_conversation_scan_page,
    )
)
_add(
    DriverEntry(
        'database.conversation_scan.recap_people_scan',
        base={'uid': UID},
        profiles=(RECIPE_PROFILES[2],),
        neutrals={
            'budget': (
                ListReadBudget(
                    deadline_monotonic=12.0,
                    max_documents=2000,
                    clock=lambda: 0.0,
                    started_monotonic=0.0,
                ),
                'required scan budget; frozen clock, deep-copied fresh per trial',
            ),
        },
        setup=_queue_conversation_scan_page,
    )
)
_add(
    DriverEntry(
        'database.conversation_scan.speaker_browse_scan',
        base={'uid': UID},
        profiles=(RECIPE_PROFILES[1],),
        neutrals={
            'budget': (
                ListReadBudget(
                    deadline_monotonic=12.0,
                    max_documents=2000,
                    clock=lambda: 0.0,
                    started_monotonic=0.0,
                ),
                'required scan budget; frozen clock, deep-copied fresh per trial',
            ),
        },
        setup=_queue_conversation_scan_page,
    )
)

_add(
    CoveredByEntry(
        'database.conversations._collect_visible_conversation_page',
        covered_by=(
            'database.conversations.get_conversations',
            'database.conversations.get_conversations_without_photos',
        ),
        reason='page collector observed inside both listed consumers',
    )
)
_add(
    CoveredByEntry(
        'database.conversations._count_matching_tombstones',
        covered_by=('database.conversations.get_conversations_count',),
        reason='tombstone count query invoked by the count driver on every combo',
    )
)
_add(DriverEntry('database.conversations.count_conversations_with_geolocation', base={'uid': UID}))
_add(DriverEntry('database.conversations.delete_conversation_photos', base={'uid': UID, 'conversation_id': 'conv-1'}))
_add(
    DriverEntry(
        'database.conversations.get_action_items',
        base={'uid': UID},
        domains={'include_completed': [True, False], 'start_date': [None, T0], 'end_date': [None, T1]},
        neutrals={'limit': _LIMIT, 'offset': _OFFSET},
    )
)
_add(
    DriverEntry(
        'database.conversations.get_closest_conversation_to_timestamps',
        base={'uid': UID, 'start_timestamp': 1767225600, 'end_timestamp': 1767312000},
    )
)
_add(DriverEntry('database.conversations.get_conversation_ids', base={'uid': UID}))
_add(DriverEntry('database.conversations.get_conversation_photos', base={'uid': UID, 'conversation_id': 'conv-1'}))
_add(
    DriverEntry(
        'database.conversations.get_conversation_transcripts_by_model', base={'uid': UID, 'conversation_id': 'conv-1'}
    )
)
_add(
    DriverEntry(
        'database.conversations.get_conversations',
        base={'uid': UID},
        profiles=PHOTO_PROFILES,
        neutrals={'limit': _LIMIT, 'offset': _OFFSET},
    )
)
_add(
    DriverEntry(
        'database.conversations.get_conversations_count',
        base={'uid': UID},
        profiles=COUNT_PROFILES,
    )
)
_add(
    DriverEntry(
        'database.conversations.get_conversations_finished_after',
        base={'uid': UID, 'status': 'completed', 'finished_after': T0},
        neutrals={'limit': _LIMIT},
    )
)
_add(DriverEntry('database.conversations.get_conversations_to_migrate', base={'uid': UID, 'target_level': 'level-2'}))
_add(
    DriverEntry(
        'database.conversations.get_conversations_without_photos',
        base={'uid': UID},
        profiles=WITHOUT_PHOTOS_PROFILES,
        neutrals={'limit': _LIMIT, 'offset': _OFFSET, 'budget': _BUDGET},
    )
)
_add(DriverEntry('database.conversations.get_in_progress_conversation', base={'uid': UID}))
_add(DriverEntry('database.conversations.get_last_completed_conversation', base={'uid': UID}))
_add(DriverEntry('database.conversations.get_processing_conversations', base={'uid': UID}))
_add(
    DriverEntry(
        'database.conversations.get_stale_in_progress_conversations',
        base={'uid': UID, 'older_than_seconds': 3600},
        neutrals={'limit': _LIMIT},
    )
)
_add(DriverEntry('database.conversations.iter_all_conversation_photos', base={'uid': UID}))
_add(
    DriverEntry(
        'database.conversations.iter_all_conversations',
        base={'uid': UID},
        domains={'include_discarded': [True, False]},
        neutrals={'batch_size': _PAGE},
    )
)
_add(
    DriverEntry(
        'database.conversations.migrate_conversations_level_batch',
        base={'uid': UID, 'conversation_ids': ['conv-1', 'conv-2'], 'target_level': 'level-2'},
        setup=_seed(
            f'users/{UID}/conversations/conv-1',
            {'visibility': 'private', 'data_protection_level': 'standard', 'created_at': T0},
        ),
    )
)
_add(DriverEntry('database.conversations.unlock_all_conversations', base={'uid': UID}))

_add(
    DriverEntry(
        'database.daily_summaries.get_daily_summaries',
        base={'uid': UID},
        domains={'start_date': [None, '2026-01-01'], 'end_date': [None, '2026-01-02']},
        neutrals={'limit': _LIMIT, 'offset': _OFFSET},
    )
)
_add(DriverEntry('database.daily_summaries.get_daily_summary_by_date', base={'uid': UID, 'date': '2026-01-01'}))
_add(DriverEntry('database.daily_summaries.get_desktop_daily_usage', base={'uid': UID, 'date': '2026-01-01'}))
_add(DriverEntry('database.daily_summaries.get_summaries_count', base={'uid': UID}))

_add(
    DriverEntry(
        'database.dev_api_key.get_api_key_auth_result',
        base={'api_key': _DEV_KEY},
        patchers=(_stub('database.redis_db.read_cached_dev_api_key_data', _CACHE_MISS),),
    )
)
_add(DriverEntry('database.dev_api_key.get_dev_keys_for_user', base={'user_id': UID}))
_add(DriverEntry('database.dev_api_key.get_dev_keys_for_user_with_repair_info', base={'user_id': UID}))
_add(
    DriverEntry(
        'database.dev_api_key.get_user_and_scopes_by_api_key',
        base={'api_key': _DEV_KEY},
        patchers=(_stub('database.redis_db.read_cached_dev_api_key_data', _CACHE_MISS),),
    )
)
_add(
    CoveredByEntry(
        'database.dev_api_key._get_api_key_auth_result',
        covered_by=(
            'database.dev_api_key.get_api_key_auth_result',
            'database.dev_api_key.get_user_and_scopes_by_api_key',
        ),
        reason='hashed-key lookup shared by the public auth entry points; the revocation fence retries through it',
    )
)
_add(
    DriverEntry(
        'database.dev_api_key.get_user_id_by_api_key',
        base={'api_key': _DEV_KEY},
        patchers=(_stub('database.redis_db.read_cached_dev_api_key_data', _CACHE_MISS),),
    )
)

_add(
    CoveredByEntry(
        'database.durable_queue_age._sample_status_page',
        covered_by=(
            'database.durable_queue_age.publish_all_queue_oldest_ready_ages',
            'database.durable_queue_age.sample_store_wide_oldest_ready_ages',
        ),
        reason='group-scope sampler reached by both wrappers on every call',
    )
)
_add(
    DriverEntry(
        'database.durable_queue_age.publish_all_queue_oldest_ready_ages',
        domains={'now': [None, T0], 'finalization_summary': [None, {'jobs': 1}]},
    )
)
_add(
    DriverEntry(
        'database.durable_queue_age.sample_store_wide_oldest_ready_ages',
        domains={'now': [None, T0], 'finalization_summary': [None, {'jobs': 1}]},
    )
)

for _fn in (
    'list_entity_timeline_conversations',
    'list_entity_timeline_meetings',
    'list_entity_timeline_screen_activity',
):
    _add(
        DriverEntry(
            f'database.entity_timeline_sources.{_fn}',
            base={'uid': UID},
            domains={'start_date': [None, T0], 'end_date': [None, T1]},
            neutrals={'limit': _LIMIT},
        )
    )

_add(DriverEntry('database.fair_use.get_fair_use_events', base={'uid': UID}, neutrals={'limit': _LIMIT}))
_add(
    DriverEntry(
        'database.fair_use.get_flagged_users', domains={'stage_filter': [None, 'stage-1']}, neutrals={'limit': _LIMIT}
    )
)
_add(DriverEntry('database.fair_use.get_violation_counts', base={'uid': UID}))
_add(
    DriverEntry(
        'database.feedback.list_negative_events', base={'start_at': T0, 'end_at': T1}, neutrals={'limit': _LIMIT}
    )
)
_add(DriverEntry('database.feedback.list_report_dates', neutrals={'limit': _LIMIT}))
_add(
    DriverEntry(
        'database.first_open_obligations.commit_first_open_folder_count',
        base={'uid': UID, 'conversation_id': 'conv-1', 'token': 'token-1', 'folder_id': 'folder-1'},
    )
)
_add(
    DriverEntry(
        'database.focus_sessions.get_focus_sessions',
        base={'uid': UID},
        domains={'date': [None, '2026-01-01']},
        neutrals={'limit': _LIMIT, 'offset': _OFFSET},
    )
)
_add(DriverEntry('database.focus_sessions.get_focus_stats', base={'uid': UID}, domains={'date': [None, '2026-01-01']}))

_add(
    DriverEntry(
        'database.folders.bulk_move_conversations_to_folder',
        base={'uid': UID, 'conversation_ids': ['conv-1', 'conv-2'], 'folder_id': 'folder-1'},
    )
)
_add(
    DriverEntry(
        'database.folders.create_folder',
        base={'uid': UID, 'name': 'shape-folder'},
        neutrals={
            'description': (None, 'optional payload field; not filter-affecting'),
            'color': (None, 'optional payload field; not filter-affecting'),
            'icon': (None, 'optional payload field; not filter-affecting'),
        },
    )
)
_add(
    DriverEntry(
        'database.folders.delete_folder',
        base={'uid': UID, 'folder_id': 'folder-1'},
        domains={'move_to_folder_id': [None, 'folder-2']},
        setup=_seed(f'users/{UID}/folders/folder-1', {'name': 'shape-folder', 'deleted': False}),
    )
)
_add(
    DriverEntry(
        'database.folders.get_conversations_in_folder',
        base={'uid': UID, 'folder_id': 'folder-1'},
        domains={'include_discarded': [False, True]},
        neutrals={'limit': _LIMIT, 'offset': _OFFSET},
    )
)
_add(DriverEntry('database.folders.get_folder_by_category_mapping', base={'uid': UID, 'category_mapping': 'cat-1'}))
_add(DriverEntry('database.folders.get_folders', base={'uid': UID}))
_add(DriverEntry('database.folders.initialize_system_folders', base={'uid': UID}))
_add(
    DriverEntry(
        'database.folders.move_conversation_to_folder',
        base={'uid': UID, 'conversation_id': 'conv-1', 'folder_id': 'folder-1'},
        setup=_seed(f'users/{UID}/conversations/conv-1', {'folder_id': None}),
    )
)
_add(DriverEntry('database.folders.update_folder_conversation_count', base={'uid': UID, 'folder_id': 'folder-1'}))

_FRAME_REQUEST_DOC = {
    'request_id': 'req-1',
    'uid': UID,
    'device_id': 'dev-1',
    'account_generation': 1,
    'dedupe_key': 'dedupe-1',
    'created_at': T0,
    'expires_at': T1,
}
_FRAME_LIMIT = (32, 'bounded frame-request window cap; fixed, not filter-affecting')

_add(
    DriverEntry(
        'database.frame_requests.attach_frame_request_to_conversation',
        base={
            'uid': UID,
            'request_id': 'req-1',
            'device_id': 'dev-1',
            'account_generation': 1,
            'conversation_id': 'conv-1',
            'permanent_storage_id': 'store-1',
        },
        domains={'now': [None, T0]},
        setup=lambda client, combo, trial: (
            client.documents.__setitem__(
                f'users/{UID}/frame_requests/req-1',
                {**_FRAME_REQUEST_DOC, 'state': 'uploaded', 'storage_id': 'store-1', 'conversation_id': 'conv-1'},
            ),
            client.documents.__setitem__(f'users/{UID}/conversations/conv-1', {'status': 'completed'}),
        ),
    )
)
_add(
    DriverEntry(
        'database.frame_requests.cleanup_ambiguous_frame_upload_pixels',
        base={'uid': UID, 'delete_storage': noop},
        domains={'now': [None, T0], 'report_page': [False, True]},
        neutrals={'limit': _FRAME_LIMIT},
    )
)
_add(
    DriverEntry(
        'database.frame_requests.cleanup_conversation_frame_deletion_outbox',
        base={'uid': UID, 'delete_storage': noop},
        domains={'now': [None, T0], 'report_page': [False, True]},
        neutrals={'limit': _FRAME_LIMIT},
    )
)
_add(
    DriverEntry(
        'database.frame_requests.cleanup_expired_frame_vision_outputs',
        base={'uid': UID},
        domains={'now': [None, T0], 'report_page': [False, True]},
        neutrals={'limit': _FRAME_LIMIT},
    )
)
_add(
    DriverEntry(
        'database.frame_requests.cleanup_frame_request_pixels',
        base={'uid': UID, 'delete_storage': noop},
        domains={'now': [None, T0], 'report_page': [False, True]},
        neutrals={'limit': _FRAME_LIMIT},
    )
)
_add(
    DriverEntry(
        'database.frame_requests.delete_expired_frame_request_metadata',
        base={'uid': UID},
        domains={'now': [None, T0], 'report_page': [False, True]},
        neutrals={'limit': _FRAME_LIMIT},
    )
)
_add(
    DriverEntry(
        'database.frame_requests.delete_frame_requests_for_conversation',
        base={'uid': UID, 'conversation_id': 'conv-1'},
        neutrals={'batch_size': _PAGE},
    )
)
_add(
    DriverEntry(
        'database.frame_requests.enqueue_frame_request',
        base={'uid': UID, 'device_id': 'dev-1', 'dedupe_key': 'dedupe-1'},
        domains={
            'conversation_id': [None, 'conv-1'],
            'screenshot_id': [None, 'shot-1'],
            'requested_ttl_seconds': [None, 60],
            'device_retention_seconds': [None, 60],
            'now': [None, T0],
        },
        neutrals={'account_generation': (1, 'generation stamp; payload value, not filter-affecting')},
    )
)
_add(
    DriverEntry(
        'database.frame_requests.list_all_frame_deletion_outbox_storage_ids',
        base={'uid': UID},
        neutrals={'page_size': _PAGE, 'max_pages': (5, 'page bound; fixed small, not filter-affecting')},
    )
)
_add(
    DriverEntry(
        'database.frame_requests.list_all_frame_request_storage_ids',
        base={'uid': UID},
        domains={'conversation_id': [None, 'conv-1']},
        neutrals={'page_size': _PAGE, 'max_pages': (5, 'page bound; fixed small, not filter-affecting')},
    )
)
_add(
    DriverEntry(
        'database.frame_requests.list_all_frame_upload_orphan_storage_ids',
        base={'uid': UID},
        neutrals={'page_size': _PAGE, 'max_pages': (5, 'page bound; fixed small, not filter-affecting')},
    )
)
_add(
    DriverEntry(
        'database.frame_requests.list_attached_frame_requests',
        base={'uid': UID, 'conversation_id': 'conv-1'},
        neutrals={'limit': (2, 'attached keyframe bound is capped at 2; fixed, not filter-affecting')},
    )
)
_add(
    DriverEntry(
        'database.frame_requests.list_frame_request_storage_ids',
        base={'uid': UID},
        domains={'conversation_id': [None, 'conv-1']},
        neutrals={'limit': (500, 'page bound; fixed, not filter-affecting')},
    )
)
_add(
    DriverEntry(
        'database.frame_requests.list_pending_frame_requests',
        base={'uid': UID, 'device_id': 'dev-1', 'account_generation': 1},
        domains={'now': [None, T0]},
        neutrals={'limit': _FRAME_LIMIT, 'cleanup_storage': (None, 'optional storage callback; not filter-affecting')},
    )
)
_add(
    DriverEntry(
        'database.frame_requests.list_recoverable_frame_requests',
        base={'uid': UID, 'device_id': 'dev-1', 'account_generation': 1},
        domains={'now': [None, T0]},
        neutrals={'limit': _FRAME_LIMIT},
    )
)
_add(
    DriverEntry(
        'database.frame_requests.prune_expired_frame_requests',
        base={'uid': UID},
        domains={'account_generation': [None, 1], 'now': [None, T0]},
        neutrals={'limit': _FRAME_LIMIT, 'cleanup_storage': (None, 'optional storage callback; not filter-affecting')},
    )
)
_add(
    DriverEntry(
        'database.frame_requests.transition_frame_request',
        base={
            'uid': UID,
            'request_id': 'req-1',
            'next_state': FrameRequestState.uploaded,
            'device_id': 'dev-1',
            'account_generation': 1,
        },
        domains={'now': [None, T0]},
        neutrals={
            'storage_id': ('store-1', 'transition payload field; not a query filter'),
            'byte_count': (100, 'byte limit payload field; not a query filter'),
            'content_type': ('image/png', 'transition payload field; not a query filter'),
            'terminal_reason': (None, 'uploaded transition carries no terminal reason'),
            'cleanup_storage': (None, 'optional storage callback; not filter-affecting'),
        },
        setup=_seed(f'users/{UID}/frame_requests/req-1', {**_FRAME_REQUEST_DOC, 'state': 'claimed'}),
    )
)

_GOAL_DOC = {
    'id': 'goal-1',
    'goal_id': 'goal-1',
    'title': 'shape-goal',
    'desired_outcome': 'shape-outcome',
    'status': 'focused',
    'source': 'user',
    'created_at': T0,
    'updated_at': T0,
    'goal_type': 'habit',
    'target_value': 1.0,
    'current_value': 0.0,
    'min_value': 0.0,
    'max_value': 1.0,
    'is_active': True,
    'account_generation': 0,
}

_add(
    DriverEntry(
        'database.goals.focus_goal',
        base={'uid': UID, 'goal_id': 'goal-1', 'idempotency_key': 'key-1', 'account_generation': 0},
        domains={'replacement_goal_id': [None, 'goal-2'], 'focus_rank': [None, 1]},
        neutrals={'focus_cap': (3, 'payload cap; not filter-affecting')},
        setup=_seed(f'users/{UID}/goals/goal-1', _GOAL_DOC),
    )
)
_add(
    DriverEntry(
        'database.goals.get_all_goals',
        base={'uid': UID},
        domains={'include_inactive': [False, True], 'limit': [None, 50]},
    )
)
_add(DriverEntry('database.goals.get_goal_history', base={'uid': UID, 'goal_id': 'goal-1'}, neutrals={'days': _DAYS}))
_add(DriverEntry('database.goals.get_user_goal', base={'uid': UID}))
_add(
    DriverEntry(
        'database.goals.get_user_goals',
        base={'uid': UID},
        neutrals={'limit': (3, 'goal cap; fixed, not filter-affecting')},
    )
)
_add(
    DriverEntry(
        'database.goals.list_goal_progress_events', base={'uid': UID, 'goal_id': 'goal-1'}, neutrals={'limit': _LIMIT}
    )
)
_add(
    DriverEntry(
        'database.goals.transition_goal_lifecycle',
        base={'uid': UID, 'goal_id': 'goal-1', 'idempotency_key': 'key-1', 'account_generation': 0},
        domains={
            'status': [GoalStatus.paused, GoalStatus.achieved, GoalStatus.abandoned],
            'relationship_disposition': [GoalRelationshipDisposition.retain, GoalRelationshipDisposition.detach],
        },
        setup=_seed(f'users/{UID}/goals/goal-1', _GOAL_DOC),
    )
)

_add(DriverEntry('database.import_jobs.get_import_jobs', base={'uid': UID}, neutrals={'limit': _LIMIT}))

_add(
    CoveredByEntry(
        'database.knowledge_graph._load_active_memory_graph_assertions',
        covered_by=(
            'database.knowledge_graph.get_active_memory_graph_assertions',
            'database.knowledge_graph.get_knowledge_graph',
        ),
        reason='assertion loader observed inside both listed consumers',
    )
)
for _fn in (
    'delete_knowledge_graph',
    'get_active_memory_graph_assertions',
    'get_knowledge_edges',
    'get_knowledge_graph',
    'get_knowledge_nodes',
    'has_stored_memory_graph_assertions',
):
    _entry = DriverEntry(f'database.knowledge_graph.{_fn}', base={'uid': UID})
    if _fn in ('get_knowledge_edges', 'get_knowledge_nodes'):
        _entry.neutrals['limit'] = (100, 'graph bound; fixed, not filter-affecting')
    _add(_entry)
_add(DriverEntry('database.knowledge_graph.find_node_by_label_or_alias', base={'uid': UID, 'label': 'shape-label'}))
_add(
    DriverEntry(
        'database.knowledge_graph.prune_memory_citations_from_kg', base={'uid': UID, 'memory_ids': ['mem-1', 'mem-2']}
    )
)
_add(
    DriverEntry(
        'database.knowledge_graph.upsert_knowledge_node', base={'uid': UID, 'node_data': {'label': 'shape-node'}}
    )
)

_add(DriverEntry('database.llm_usage.get_global_top_features', neutrals={'days': _DAYS, 'limit': (3, 'top-n; fixed')}))
_add(DriverEntry('database.llm_usage.get_plan_usage_report', base={'uid': UID}, neutrals={'days': _DAYS}))
_add(
    DriverEntry(
        'database.llm_usage.get_top_features', base={'uid': UID}, neutrals={'days': _DAYS, 'limit': (3, 'top-n; fixed')}
    )
)
_add(
    DriverEntry(
        'database.llm_usage.get_total_llm_cost',
        base={'uid': UID},
        neutrals={'bucket': ('desktop_chat', 'document field key; not a query filter')},
    )
)
_add(DriverEntry('database.llm_usage.get_usage_summary', base={'uid': UID}, neutrals={'days': _DAYS}))

_add(
    DriverEntry(
        'database.mcp_api_key.get_api_key_auth_result',
        base={'api_key': _MCP_KEY},
        patchers=(_stub('database.redis_db.read_cached_mcp_api_key_auth_context', _CACHE_MISS),),
    )
)
_add(DriverEntry('database.mcp_api_key.get_mcp_keys_for_user', base={'user_id': UID}))
_add(DriverEntry('database.mcp_api_key.get_mcp_keys_for_user_with_repair_info', base={'user_id': UID}))
_add(
    DriverEntry(
        'database.mcp_api_key.get_user_and_scopes_by_api_key',
        base={'api_key': _MCP_KEY},
        patchers=(_stub('database.redis_db.read_cached_mcp_api_key_auth_context', _CACHE_MISS),),
    )
)
_add(
    DriverEntry(
        'database.mcp_api_key.get_user_id_by_api_key',
        base={'api_key': _MCP_KEY},
        patchers=(_stub('database.redis_db.read_cached_mcp_api_key_auth_context', _CACHE_MISS),),
    )
)
_add(
    DriverEntry(
        'database.mcp_api_key._get_api_key_auth_result',
        base={'hashed_key': 'a' * 64},
        domains={'cache_available': [True, False]},
        patchers=(_stub('database.redis_db.read_cached_mcp_api_key_auth_context', _CACHE_MISS),),
    )
)
_add(
    CoveredByEntry(
        'database.mcp_auth_read.mcp_auth_stream',
        covered_by=(
            'database.mcp_api_key.get_api_key_auth_result',
            'database.mcp_api_key.get_user_and_scopes_by_api_key',
            'database.mcp_api_key.get_user_id_by_api_key',
        ),
        reason='generic stream helper observed inside all three querying consumers',
    )
)
_add(
    DriverEntry(
        'database.mcp_conversation_pages.get_mcp_conversation_cards',
        base={'uid': UID},
        domains={
            'start_date': [None, T0],
            'end_date': [None, T1],
            'categories': [None, ['one'], ['one', 'two']],
            'extra_field_paths': [None, ('created_at',)],
        },
        neutrals={'limit': _LIMIT, 'offset': _OFFSET},
    )
)
_add(
    DriverEntry(
        'database.mcp_conversation_pages.get_mcp_conversation_cards_page',
        base={'uid': UID},
        domains={
            'after': [None, (T0, 'doc-1')],
            'start_date': [None, T0],
            'end_date': [None, T1],
            'categories': [None, ['one'], ['one', 'two']],
            'extra_field_paths': [None, ('created_at',)],
        },
        neutrals={'limit': _LIMIT},
    )
)
_add(DriverEntry('database.mcp_oauth.list_user_grants', base={'uid': UID}))
_MCP_NOOP_CACHE = (_redis_noop('database.mcp_token_cache.invalidate_grant'),)
_MCP_GRANT_DOC = {'uid': UID, 'client_id': 'client-1', 'resource': 'res-1', 'scopes': []}


def _seed_delete_user_oauth_credentials(client, combo, trial):
    """Trial 0 keeps the empty path; trial 1 exercises the per-grant deletes.

    A queued grant makes ``delete_user_oauth_credentials`` walk every grant and
    issue the per-grant ``mcp_oauth_access_tokens`` / ``mcp_oauth_refresh_tokens``
    queries (inside ``revoke_grant`` and its own loop) plus the final grant
    document delete; the token streams consume the remaining empty queues.
    """
    if trial == 0:
        return
    client.queue_results([client.snapshot('mcp_oauth_grants/grant-1', dict(_MCP_GRANT_DOC))])
    client.queue_results([])
    client.queue_results([])
    client.queue_results([])
    client.queue_results([])


def _seed_mcp_refresh_replay(client, combo, trial):
    hash_secret = importlib.import_module('database.mcp_oauth').hash_secret
    client.documents[f'mcp_oauth_grants/grant-1'] = dict(_MCP_GRANT_DOC)
    client.documents[f'mcp_oauth_refresh_tokens/{hash_secret("token-1")}'] = {
        'client_id': 'client-1',
        'resource': 'res-1',
        'grant_id': 'grant-1',
        'scopes': [],
        'used_at': T0 - timedelta(minutes=10),
        'expires_at': T1,
    }


_add(
    DriverEntry(
        'database.mcp_oauth.delete_user_oauth_credentials',
        base={'uid': UID},
        setup=_seed_delete_user_oauth_credentials,
        patchers=_MCP_NOOP_CACHE,
        trials=2,
    )
)
_add(
    DriverEntry(
        'database.mcp_oauth.revoke_grant',
        base={'grant_id': 'grant-1'},
        domains={'replay_detected': [False, True]},
        patchers=_MCP_NOOP_CACHE,
    )
)
_add(
    DriverEntry(
        'database.mcp_oauth.revoke_user_grant',
        base={'uid': UID, 'grant_id': 'grant-1'},
        setup=_seed('mcp_oauth_grants/grant-1', _MCP_GRANT_DOC),
        patchers=_MCP_NOOP_CACHE,
    )
)
_add(
    DriverEntry(
        'database.mcp_oauth.rotate_refresh_token',
        base={'refresh_token': 'token-1', 'client_id': 'client-1', 'resource': 'res-1'},
        domains={'scope': [None, 'scope-1']},
        neutrals={'on_outcome': _NOOP},
        setup=_seed_mcp_refresh_replay,
        patchers=_MCP_NOOP_CACHE,
    )
)

_add(
    CoveredByEntry(
        'database.memories._aggregation_count',
        covered_by=('database.memories.count_memories_created',),
        reason='count aggregation helper; driven via count_memories_created populated trials',
    )
)
_add(
    CoveredByEntry(
        'database.memories._historical_scan_page',
        covered_by=(
            'database.memories.scan_memories_created_at_page',
            'database.memories.scan_memories_updated_at_page',
        ),
        reason='keyset scan body reached by both public scan wrappers',
    )
)
_add(
    CoveredByEntry(
        'database.memories._id_union',
        covered_by=('database.memories.count_memories_created',),
        reason='union path only runs when both stores have rows; populated trial exercises it',
    )
)
_add(
    CoveredByEntry(
        'database.memories._query_has_any',
        covered_by=('database.memories.count_memories_created',),
        reason='existence probe run for both stores on every count driver call',
    )
)
_add(
    CoveredByEntry(
        'database.memories._stream_memory_list_index_window',
        covered_by=(
            'database.memories.get_memories',
            'database.memories.list_memory_updated_or_created_index',
        ),
        reason='candidate window streamer observed inside both listed consumers',
    )
)
_add(DriverEntry('database.memories.count_default_visible_memories', base={'uid': UID}))


def _seed_memories_stores(client, combo, trial):
    canonical_path = f'users/{UID}/memory_items/item-1'
    legacy_path = f'users/{UID}/memories/mem-1'
    if trial == 0:
        return
    if trial == 1:
        client.queue_results([client.snapshot(canonical_path, {'id': 'item-1'})])
        client.queue_results([])
        return
    if trial == 2:
        client.queue_results([])
        client.queue_results([client.snapshot(legacy_path, {'id': 'mem-1'})])
        return
    client.queue_results([client.snapshot(canonical_path, {'id': 'item-1'})])
    client.queue_results([client.snapshot(legacy_path, {'id': 'mem-1'})])
    client.queue_results([client.snapshot(canonical_path, {'id': 'item-1'})])
    client.queue_results([client.snapshot(legacy_path, {'id': 'mem-1'})])


_add(
    DriverEntry(
        'database.memories.count_memories_created',
        base={'uid': UID, 'start_date': T0, 'end_date': T1},
        setup=_seed_memories_stores,
        trials=4,
    )
)
_add(DriverEntry('database.memories.delete_all_memories', base={'uid': UID}))
_add(DriverEntry('database.memories.delete_memories', base={'uid': UID}))
_add(DriverEntry('database.memories.delete_memories_for_conversation', base={'uid': UID, 'memory_id': 'mem-1'}))
_add(
    DriverEntry(
        'database.memories.get_memories',
        base={'uid': UID},
        neutrals={'limit': _LIMIT, 'offset': _OFFSET},
        profiles=(
            CallerProfile(
                'legacy-scoring',
                {
                    'categories': [[]],
                    'start_date': [None],
                    'end_date': [None],
                    'include_invalidated': [False],
                    'sort': ['scoring_desc'],
                },
            ),
            CallerProfile(
                'exploratory-updated-sorts',
                {
                    'categories': [[]],
                    'start_date': [None],
                    'end_date': [None],
                    'include_invalidated': [False],
                    'sort': ['updated_desc', 'updated_at_desc', 'updated_or_created_desc'],
                },
                serving=False,
            ),
        ),
    )
)
_add(DriverEntry('database.memories.get_memories_to_migrate', base={'uid': UID, 'target_level': 'level-2'}))
_add(DriverEntry('database.memories.get_memory_ids', base={'uid': UID}))
_add(DriverEntry('database.memories.get_memory_ids_for_conversation', base={'uid': UID, 'conversation_id': 'conv-1'}))
_add(
    DriverEntry(
        'database.memories.get_non_filtered_memories', base={'uid': UID}, neutrals={'limit': _LIMIT, 'offset': _OFFSET}
    )
)
_add(
    DriverEntry(
        'database.memories.get_user_public_memories', base={'uid': UID}, neutrals={'limit': _LIMIT, 'offset': _OFFSET}
    )
)
_add(
    DriverEntry(
        'database.memories.list_memory_updated_or_created_index',
        base={'uid': UID},
        neutrals={'limit': _LIMIT, 'offset': _OFFSET, 'budget': _BUDGET},
        profiles=(
            CallerProfile(
                'historical-dual-window',
                {'categories': [[]], 'start_date': [None], 'end_date': [None], 'include_invalidated': [False]},
            ),
        ),
    )
)
_add(
    DriverEntry(
        'database.memories.migrate_memories',
        base={'prev_uid': 'old-user', 'new_uid': UID},
        domains={'app_id': [None, 'app-1']},
    )
)
_add(DriverEntry('database.memories.ripple_source_deletion', base={'uid': UID, 'source_id': 'src-1'}))
_add(
    DriverEntry(
        'database.memories.scan_memories_created_at_page',
        base={'uid': UID},
        domains={'start_after': [None, (T0, 'doc-1')]},
        neutrals={'limit': _LIMIT, 'budget': _BUDGET},
    )
)
_add(
    DriverEntry(
        'database.memories.scan_memories_updated_at_page',
        base={'uid': UID},
        domains={'start_after': [None, (T0, 'doc-1')]},
        neutrals={'limit': _LIMIT, 'budget': _BUDGET},
    )
)
_add(DriverEntry('database.memories.unlock_all_memories', base={'uid': UID}))

_add(
    DriverEntry(
        'database.memory_apply_store.cleanup_expired_memory_deletion_receipts',
        base={'uid': UID},
        domains={'now': [None, T0]},
        neutrals={'limit': (128, 'receipt page bound; fixed')},
    )
)
_add(
    CoveredByEntry(
        'database.memory_ledger._iter_collection_documents',
        covered_by=(
            'database.memory_ledger.finalize_canonical_privacy_tombstones',
            'database.memory_ledger.purge_canonical_privacy_history_for_memories',
            'database.memory_ledger.purge_source_replacement_receipts_for_memories',
            'database.review_queue.purge_stale_review_conflicts_for_memories',
        ),
        reason='collection walker observed inside all four listed consumers',
    )
)
_add(
    DriverEntry(
        'database.memory_ledger.finalize_canonical_privacy_tombstones',
        base={'uid': UID, 'memory_ids': ['mem-1', 'mem-2']},
        domains={'preserve_source_replacement_receipts': [False, True]},
    )
)
_add(
    DriverEntry(
        'database.memory_ledger.purge_canonical_privacy_history_for_memories',
        base={'uid': UID, 'memory_ids': ['mem-1', 'mem-2']},
        domains={'preserve_source_replacement_receipts': [False, True]},
    )
)
_add(
    DriverEntry(
        'database.memory_ledger.purge_legacy_memory_commits_for_memories',
        base={'uid': UID, 'memory_ids': ['mem-1', 'mem-2']},
    )
)
_add(
    DriverEntry(
        'database.memory_ledger.purge_source_replacement_receipts_for_memories',
        base={'uid': UID, 'memory_ids': ['mem-1', 'mem-2']},
    )
)
_add(
    DriverEntry(
        'database.memory_ledger.replay_to',
        base={'uid': UID},
        domains={'commit_time': [None, T0], 'valid_time': [None, T0]},
    )
)

_add(
    DriverEntry(
        'database.memory_outbox_worker.lease_canonical_memory_outbox_events',
        base={'uid': UID, 'worker_id': 'worker-1'},
        domains={'now': [None, T0]},
        neutrals={
            'limit': (25, 'lease bound; fixed'),
            'scan_limit': (100, 'scan bound; fixed'),
            'lease_seconds': (300, 'lease ttl; payload, not filter-affecting'),
        },
    )
)
_add(
    DriverEntry(
        'database.memory_outbox_worker.run_canonical_memory_outbox_worker_tick',
        base={
            'uid': UID,
            'config': CanonicalMemoryOutboxWorkerConfig(worker_id='worker-1'),
            'side_effects': CanonicalMemoryOutboxSideEffects(
                projection_upsert=lambda *a, **k: True,
                projection_delete=lambda *a, **k: True,
                vector_upsert=lambda *a, **k: True,
                vector_delete=lambda *a, **k: True,
            ),
        },
        domains={'now': [None, T0]},
    )
)
_add(
    DriverEntry(
        'database.memory_vector_repair_outbox_worker.lease_vector_repair_purge_outbox_records',
        base={'uid': UID, 'worker_id': 'worker-1'},
        neutrals={'limit': (25, 'lease bound; fixed'), 'lease_seconds': (300, 'lease ttl; payload')},
        profiles=(CallerProfile('unwired-vector-repair-pending-and-expired', {'now': [None, T0]}, serving=False),),
    )
)
_add(
    DriverEntry(
        'database.memory_vector_repair_outbox_worker.run_vector_repair_outbox_worker_tick',
        base={
            'uid': UID,
            'config': VectorRepairOutboxWorkerTickConfig(enabled=True, worker_id='worker-1'),
            'authoritative_item_loader': noop,
            'vector_deleter': noop,
            'vector_repairer': noop,
        },
        profiles=(CallerProfile('unwired-vector-repair-pending-and-expired', {'now': [None, T0]}, serving=False),),
        neutrals={
            'telemetry_emitter': (None, 'optional telemetry callback; not filter-affecting'),
            'telemetry_config': (None, 'optional telemetry config; not filter-affecting'),
            'backlog': (None, 'optional backlog hint; not filter-affecting'),
            'duration_ms': (None, 'optional duration budget; not filter-affecting'),
        },
    )
)

_add(
    CoveredByEntry(
        'database.notifications._get_users_in_timezones',
        covered_by=(
            'database.notifications.get_users_id_in_timezones',
            'database.notifications.get_users_token_in_timezones',
        ),
        reason='timezone query helper observed inside both listed consumers',
    )
)


def _seed_daily_summary_recipient(client, combo, trial):
    """Queue a due owner; tokens are now resolved after generation guards."""
    client.queue_results([client.snapshot(f'users/{UID}', {'fcm_token': 'legacy-1'})])


def _seed_notification_recipient_with_tokens(client, combo, trial):
    _seed_daily_summary_recipient(client, combo, trial)
    client.queue_results([])


_add(
    DriverEntry(
        'database.notifications.get_all_tokens',
        base={'uid': UID},
        domains={'user_document_loaded': [False, True], 'legacy_token': [None, 'legacy-1']},
    )
)
_add(
    DriverEntry(
        'database.notifications.get_users_for_daily_summary_indexed',
        base={'timezones': ['UTC'], 'target_local_hour': 7},
        setup=_seed_daily_summary_recipient,
    )
)
_add(
    DriverEntry(
        'database.notifications.get_users_id_in_timezones',
        base={'timezones': ['UTC']},
        setup=_seed_notification_recipient_with_tokens,
    )
)
_add(
    DriverEntry(
        'database.notifications.get_users_token_in_timezones',
        base={'timezones': ['UTC']},
        setup=_seed_notification_recipient_with_tokens,
    )
)
_add(DriverEntry('database.notifications.remove_bulk_tokens', base={'tokens': ['token-1', 'token-2']}))
_add(DriverEntry('database.notifications.remove_invalid_token', base={'token': 'token-1'}))
_add(
    DriverEntry(
        'database.notifications.save_token',
        base={'uid': UID, 'data': {'fcm_token': 'token-1', 'device_key': 'dev-1'}},
        setup=_seed(f'users/{UID}', {'fcm_token': 'legacy-1'}),
    )
)

_add(DriverEntry('database.phone_calls.get_phone_number_by_number', base={'uid': UID, 'phone_number': '+15550101'}))
_add(DriverEntry('database.phone_calls.get_phone_numbers', base={'uid': UID}))
_add(DriverEntry('database.phone_calls.get_primary_phone_number', base={'uid': UID}))
_add(
    DriverEntry(
        'database.projection_repair.process_projection_repairs',
        base={'uid': UID, 'fact_loader': noop, 'repair_func': noop},
        neutrals={'limit': _LIMIT, 'max_attempts': (3, 'retry bound; not filter-affecting')},
    )
)
_add(
    DriverEntry(
        'database.recurrence_inbox.list_pending_recurrence_receipts',
        base={'uid': UID, 'account_generation': 1},
        neutrals={'limit': _LIMIT},
    )
)
_add(
    CoveredByEntry(
        'database.review_queue._purge_correction_history_for_memories',
        covered_by=('database.review_queue.purge_stale_review_conflicts_for_memories',),
        reason='correction-history purge reached by the public purge driver',
    )
)
_add(
    DriverEntry(
        'database.review_queue.list_review_conflicts',
        base={'uid': UID},
        domains={'status': ['pending', 'resolved']},
        neutrals={'limit': _LIMIT},
    )
)
_add(
    DriverEntry(
        'database.review_queue.purge_stale_review_conflicts_for_memories',
        base={'uid': UID, 'memory_ids': ['mem-1', 'mem-2']},
        neutrals={'reason': ('source_memory_deleted', 'purge payload value; not a query filter')},
        domains={'include_legacy_commits': [False, True], 'preserve_source_replacement_receipts': [False, True]},
    )
)
_add(
    DriverEntry(
        'database.review_queue.resolve_expired_review_conflicts',
        base={'uid': UID},
        domains={'now': [None, T0], 'current_veracity_by_fact': [None, {'fact-1': 0.5}]},
        neutrals={'limit': _LIMIT},
    )
)

_add(
    DriverEntry(
        'database.screen_activity.get_screen_activity',
        base={'uid': UID},
        domains={'start_date': [None, T0], 'end_date': [None, T1], 'app_filter': [None, 'app-1']},
        neutrals={'limit': (500, 'page bound; fixed')},
    )
)
_add(DriverEntry('database.screen_activity.get_screen_activity_ids', base={'uid': UID}))
_add(
    DriverEntry(
        'database.screen_activity.get_screen_activity_page',
        base={'uid': UID},
        domains={
            'start_date': [None, T0],
            'end_date': [None, T1],
            'app_filter': [None, 'app-1'],
            'after': [None, ('2026-01-01T00:00:00+00:00', 'doc-1')],
        },
        neutrals={'limit': (500, 'page bound; fixed')},
    )
)
_add(
    DriverEntry(
        'database.screen_activity.get_screen_activity_summary',
        base={'uid': UID},
        domains={'start_date': [None, T0], 'end_date': [None, T1]},
    )
)
_add(
    DriverEntry(
        'database.screen_frames.delete_conversation_screen_frame_docs', base={'uid': UID, 'conversation_id': 'conv-1'}
    )
)
_add(
    DriverEntry('database.screen_frames.get_conversation_screen_frames', base={'uid': UID, 'conversation_id': 'conv-1'})
)
_add(
    DriverEntry(
        'database.screen_frames.list_screen_frame_cleanups', base={'bucket': 'bucket-1'}, neutrals={'limit': _LIMIT}
    )
)

_add(DriverEntry('database.short_term_memories.tombstone_source', base={'uid': UID, 'source_id': 'src-1'}))
_add(
    DriverEntry(
        'database.smart_merge.find_preceding_conversations',
        base={'uid': UID, 'source': 'omi', 'created_before': T0},
        domains={'discarded': [False, True], 'transaction': [None, ref_transaction()]},
        neutrals={'limit': _LIMIT_OPT},
    )
)
_add(
    CoveredByEntry(
        'database.smart_merge.absorb_conversation',
        covered_by=(
            'database.smart_merge.find_preceding_conversations',
            'database.smart_merge.has_intervening_discarded',
        ),
        reason='the discarded-barrier scan runs inside absorb_attempt through '
        'has_intervening_discarded/find_preceding_conversations, so the terminal '
        'stream records under those callees, never under absorb_conversation',
        expect_observed=False,
        body_digest=BODY_DIGEST['database.smart_merge.absorb_conversation'],
    )
)
_add(
    DriverEntry(
        'database.smart_merge.has_intervening_discarded',
        base={
            'uid': UID,
            'survivor': {'id': 'conv-p', 'finished_at': T0},
            'donor': {
                'id': 'conv-n',
                'source': 'omi',
                'client_device_id': 'pendant-1',
                'started_at': T0 + timedelta(minutes=5),
                'created_at': T0 + timedelta(minutes=5),
            },
        },
        domains={'transaction': [None, ref_transaction()]},
    )
)
_add(
    DriverEntry(
        'database.staged_tasks.batch_update_staged_scores', base={'uid': UID, 'scores': [{'id': 'task-1', 'score': 1}]}
    )
)
_add(DriverEntry('database.staged_tasks.clear_staged_tasks', base={'uid': UID}))
_add(DriverEntry('database.staged_tasks.create_staged_task', base={'uid': UID, 'description': 'shape-task'}))
_add(DriverEntry('database.staged_tasks.get_active_staged_tasks_for_compatibility', base={'uid': UID}))
_add(DriverEntry('database.staged_tasks.get_all_staged_tasks_for_migration', base={'uid': UID}))
_add(
    DriverEntry(
        'database.staged_tasks.get_staged_tasks', base={'uid': UID}, neutrals={'limit': _LIMIT, 'offset': _OFFSET}
    )
)
_add(DriverEntry('database.staged_tasks.get_top_staged_task_for_promotion', base={'uid': UID}))
_add(
    DriverEntry(
        'database.staged_tasks.promote_staged_task',
        base={'uid': UID},
        domains={
            'task_id': [None, 'task-1'],
            'include_staged_id': [False, True],
            'action_item_id': [None, 'ai-1'],
            'reservation_kind': [None, 'create', 'existing'],
        },
    )
)
_add(
    DriverEntry(
        'database.staged_tasks.restore_legacy_conversation_items',
        base={'uid': UID},
        domains={'cursor': [None, 'cursor-1']},
        neutrals={'limit': _LIMIT},
    )
)

_add(
    CoveredByEntry(
        'database.sync_backfill_sequencer._first_pending',
        covered_by=(
            'database.sync_backfill_sequencer.claim_next',
            'database.sync_backfill_sequencer.has_pending',
        ),
        reason='transactional claim probe observed inside both listed consumers',
    )
)
_add(
    CoveredByEntry(
        'database.sync_backfill_sequencer._pending_for_uid',
        covered_by=(
            'database.sync_backfill_sequencer.claim_next',
            'database.sync_backfill_sequencer.waiting_sample',
        ),
        reason='returns a base query object; the terminal streams execute inside '
        'claim_next/waiting_sample, so it never appears as a caller',
        expect_observed=False,
        body_digest=BODY_DIGEST['database.sync_backfill_sequencer._pending_for_uid'],
    )
)
_SYNC_PROD = (_stub('database.sync_backfill_sequencer.production_stage', True),)
_add(
    DriverEntry(
        'database.sync_backfill_sequencer.claim_next',
        base={'uid': UID},
        domains={'now': [None, T0]},
        patchers=_SYNC_PROD,
    )
)
_add(
    DriverEntry(
        'database.sync_backfill_sequencer.due_owners',
        domains={'now': [None, T0]},
        neutrals={'limit': _LIMIT},
        patchers=_SYNC_PROD,
    )
)
_add(
    DriverEntry(
        'database.sync_backfill_sequencer.due_pending',
        domains={'now': [None, T0]},
        neutrals={'limit': _LIMIT},
        patchers=_SYNC_PROD,
    )
)
_add(DriverEntry('database.sync_backfill_sequencer.has_pending', base={'uid': UID}, patchers=_SYNC_PROD))
_add(
    DriverEntry(
        'database.sync_backfill_sequencer.waiting_sample',
        base={'uid': UID},
        domains={'now': [None, T0]},
        patchers=_SYNC_PROD,
    )
)

_add(
    CoveredByEntry(
        'database.task_recommendations._cleanup_expired_snapshot_receipts',
        covered_by=(
            'database.task_recommendations.get_context_snapshot',
            'database.task_recommendations.list_open_loop_snapshots',
            'database.task_recommendations.replace_context_snapshot',
            'database.task_recommendations.replace_open_loop_snapshot',
        ),
        reason='receipt cleanup observed inside all four listed consumers',
    )
)
_add(
    CoveredByEntry(
        'database.task_recommendations._first_chain_record',
        covered_by=('database.task_recommendations.create_outcome',),
        reason='chain lookup observed inside the create_outcome driver only',
    )
)
_CONTEXT_SNAPSHOT = NormalizedContextSnapshot(device_id='dev-1', snapshot_id='snap-1', generated_at=T0, expires_at=T0)
_OPEN_LOOP_SNAPSHOT = OpenLoopSnapshot(
    device_id='dev-1',
    owner='owner-1',
    runtime_id='runtime-1',
    workstream_id='ws-1',
    conversation_id='conv-1',
    context_packet_version='v1',
    generated_at=T0,
    expires_at=T1,
)


def _seed_outcome_chain(client, combo, trial):
    """Trial 0 serves the chain from ``task_interventions``.

    Trial 1 empties the interventions lookup so ``create_outcome`` falls back
    to ``task_feedback`` (``database/task_recommendations.py`` ``create_outcome``),
    recording the fallback collection's distinct query shape.
    """
    if trial == 0:
        client.queue_results(
            [client.snapshot(f'users/{UID}/task_interventions/iv-1', {'subject_kind': 'task', 'subject_id': 'task-1'})]
        )
    else:
        client.queue_results([])
        client.queue_results(
            [
                client.snapshot(
                    f'users/{UID}/task_feedback/fb-1',
                    {'feedback_subject_kind': 'task', 'feedback_subject_id': 'task-1'},
                )
            ]
        )


def _seed_expired_context_snapshot(client, combo, trial):
    module = importlib.import_module('database.task_recommendations')
    payload = _CONTEXT_SNAPSHOT.model_dump(mode='python')
    payload['account_generation'] = 0
    path = f'users/{UID}/{module.CONTEXT_SNAPSHOTS_COLLECTION}/{module._stable_id("context", 0, "dev-1")}'
    client.documents[path] = payload


def _seed_canonical_product_state(client, combo, trial):
    """Queue a generation-matched workstream row so nested per-workstream queries run.

    ``account_generation`` is a domain: 0 records the unfiltered collection
    queries (the production default), 1 records the ``account_generation ==``
    filter; the seeded row always matches the driven generation so the
    ``workstreams/{id}/artifact_refs`` and ``workstreams/{id}/events``
    (``order_by sequence DESC``) queries execute in every combo. The
    consume-once queues feed the four top-level collections and both nested
    subcollections in call order.
    """
    payload: dict = {}
    if combo['account_generation']:
        payload['account_generation'] = combo['account_generation']
    client.queue_results([])
    client.queue_results([])
    client.queue_results([])
    client.queue_results([client.snapshot(f'users/{UID}/workstreams/ws-1', payload)])
    client.queue_results([])
    client.queue_results([])


_add(
    DriverEntry(
        'database.task_recommendations.create_outcome',
        base={
            'uid': UID,
            'request': OutcomeCreate(
                attribution_chain_id='chain-1',
                subject_kind=FeedbackSubjectKind.task,
                subject_id='task-1',
                outcome_code=TaskIntelligenceOutcomeCode.task_completed,
            ),
            'idempotency_key': 'key-1',
            'now': T0,
        },
        neutrals={
            'account_generation': (0, 'generation fence; fixed seeded scope, same filter set for any value'),
        },
        setup=_seed_outcome_chain,
        trials=2,
    )
)
_add(
    DriverEntry(
        'database.task_recommendations.get_context_snapshot',
        base={'uid': UID, 'device_id': 'dev-1', 'now': T0},
        neutrals={
            'account_generation': (0, 'generation fence; fixed seeded scope, same filter set for any value'),
        },
        setup=_seed_expired_context_snapshot,
    )
)
_add(
    DriverEntry(
        'database.task_recommendations.list_active_override_dedupe_keys',
        base={'uid': UID, 'now': T0},
        neutrals={
            'account_generation': (1, 'generation fence; fixed seeded scope, same filter set for any value'),
        },
    )
)
_add(
    DriverEntry(
        'database.task_recommendations.list_open_loop_snapshots',
        base={'uid': UID, 'device_id': 'dev-1', 'now': T0, 'account_generation': 1},
    )
)
_add(
    DriverEntry(
        'database.task_recommendations.load_canonical_product_state',
        base={'uid': UID},
        domains={
            'account_generation': [0, 1],
        },
        setup=_seed_canonical_product_state,
    )
)
_add(
    DriverEntry(
        'database.task_recommendations.replace_context_snapshot',
        base={'uid': UID, 'snapshot': _CONTEXT_SNAPSHOT},
        domains={'idempotency_key': [None, 'key-1']},
        neutrals={
            'account_generation': (0, 'generation fence; fixed seeded scope, same filter set for any value'),
        },
    )
)
_add(
    DriverEntry(
        'database.task_recommendations.replace_open_loop_snapshot',
        base={'uid': UID, 'snapshot': _OPEN_LOOP_SNAPSHOT},
        domains={'idempotency_key': [None, 'key-1']},
        neutrals={
            'account_generation': (0, 'generation fence; fixed seeded scope, same filter set for any value'),
        },
    )
)
_add(
    DriverEntry(
        'database.task_recommendations.save_projection',
        base={
            'uid': UID,
            'device_scope': 'dev-1',
            'projection': WhatMattersNowProjection(
                evaluation_id='eval-1',
                output_version='v1',
                material_version='m1',
                generated_at=T0,
                expires_at=T1,
                recommendations=[],
            ),
            'decisions': [],
        },
        neutrals={
            'account_generation': (0, 'generation fence; fixed seeded scope, same filter set for any value'),
        },
    )
)

_add(DriverEntry('database.tasks.get_task_by_action_request', base={'action': 'act-1', 'request_id': 'req-1'}))


def _seed_trends_categories(client, combo, trial):
    """Queue one valid category so the nested ``topics`` streams execute.

    The consume-once queues feed the top-level ``trends`` stream (one
    ``ceo`` category) and the per-category ``trends/{id}/topics`` stream.
    """
    client.queue_results([client.snapshot('trends/trend-ceo-1', {'id': 'trend-ceo-1', 'category': 'ceo'})])
    client.queue_results([])


_add(DriverEntry('database.trends.get_trends_data', setup=_seed_trends_categories))

_add(
    CoveredByEntry(
        'database.user_usage._aggregate_stats',
        covered_by=(
            'database.user_usage.get_current_user_usage',
            'database.user_usage.get_monthly_usage_stats',
            'database.user_usage.get_yearly_usage_stats',
        ),
        reason='aggregation consumer observed inside all three listed stat drivers',
    )
)
_add(
    CoveredByEntry(
        'database.user_usage._current_month_llm_usage_docs',
        covered_by=(
            'database.user_usage.get_monthly_bucket_call_count',
            'database.user_usage.get_monthly_chat_usage',
            'database.user_usage.get_usage_by_plan',
        ),
        reason='month-scoped doc scan observed inside all three listed consumers',
    )
)
_add(
    CoveredByEntry(
        'database.user_usage._local_period_usage',
        covered_by=('database.user_usage.get_current_user_usage',),
        reason='period usage helper reached by the current usage driver',
    )
)
_add(
    CoveredByEntry(
        'database.user_usage._read_all_time_usage',
        covered_by=('database.user_usage.get_all_time_usage_stats',),
        reason='all-time scan reached by the all-time stats driver',
    )
)
_add(DriverEntry('database.user_usage.get_all_time_usage_stats', base={'uid': UID}))
_add(
    DriverEntry(
        'database.user_usage.get_current_user_usage',
        base={'uid': UID},
        domains={'period': ['today', 'monthly', 'yearly'], 'tz_name': [None, 'UTC'], 'now': [None, T0]},
    )
)
_add(DriverEntry('database.user_usage.get_daily_history_for_month', base={'uid': UID, 'date': T0}))
_add(DriverEntry('database.user_usage.get_hourly_history_for_today', base={'uid': UID, 'start': T0, 'end': T1}))
_add(
    DriverEntry(
        'database.user_usage.get_monthly_bucket_call_count',
        base={'uid': UID, 'bucket': 'desktop_chat'},
        domains={'now': [None, T0]},
    )
)
_add(DriverEntry('database.user_usage.get_monthly_chat_usage', base={'uid': UID}, domains={'now': [None, T0]}))
_add(DriverEntry('database.user_usage.get_monthly_history_for_year', base={'uid': UID, 'date': T0}))
_add(DriverEntry('database.user_usage.get_monthly_usage_stats', base={'uid': UID, 'date': T0}))
_add(DriverEntry('database.user_usage.get_monthly_usage_stats_since', base={'uid': UID, 'date': T0, 'start_date': T0}))
_add(DriverEntry('database.user_usage.get_today_usage_stats', base={'uid': UID, 'start': T0, 'end': T1}))
_add(DriverEntry('database.user_usage.get_usage_by_plan', base={'uid': UID}, domains={'now': [None, T0]}))
_add(DriverEntry('database.user_usage.get_yearly_history', base={'uid': UID}))
_add(DriverEntry('database.user_usage.get_yearly_usage_stats', base={'uid': UID, 'date': T0}))

_add(DriverEntry('database.users.count_people', base={'uid': UID}))
_add(DriverEntry('database.users.get_all_ratings', domains={'rating_type': ['memory_summary', 'other']}))
_add(
    DriverEntry(
        'database.users.get_pending_deletion_wipes',
        neutrals={
            'limit': _LIMIT,
            'stale_after': (timedelta(minutes=10), 'staleness bound; fixed'),
            'running_stale_after': (timedelta(minutes=10), 'staleness bound; fixed'),
        },
    )
)
_add(
    DriverEntry(
        'database.person_aliases.list_people',
        base={'uid': UID},
        neutrals={
            'include_dismissed': (False, 'post-read visibility filter; does not alter the Firestore query shape')
        },
    )
)
_add(DriverEntry('database.person_aliases.find_person_by_name', base={'uid': UID, 'name': 'shape-name'}))
_add(DriverEntry('database.users.get_task_integrations', base={'uid': UID}))
_add(DriverEntry('database.users.get_user_by_stripe_customer_id', base={'customer_id': 'cus_1'}))
_add(DriverEntry('database.users.resolve_deletion_wipe_job_id', base={'wipe_job_id': 'job-1'}))

_add(
    DriverEntry(
        'database.workstreams.get_goal_detail',
        base={'uid': UID, 'goal_id': 'goal-1'},
        setup=_seed(f'users/{UID}/goals/goal-1', _GOAL_DOC),
    )
)
_add(
    DriverEntry(
        'database.workstreams.get_workstream_detail',
        base={'uid': UID, 'workstream_id': 'ws-1'},
        setup=_seed(
            f'users/{UID}/workstreams/ws-1',
            {
                'workstream_id': 'ws-1',
                'title': 'shape-ws',
                'objective': 'shape-obj',
                'status': 'open',
                'created_at': T0,
                'updated_at': T0,
            },
        ),
    )
)
_add(
    SkipEntry(
        'database.workstreams.import_task_goal_links',
        reason='AST doc-get false positive: the entire body is transactional document '
        'get/set/update writes (control, receipt, task, goal, workstream refs); '
        'no where/stream/query terminal exists',
        body_digest=BODY_DIGEST['database.workstreams.import_task_goal_links'],
    )
)
_add(
    DriverEntry(
        'database.workstreams.list_artifact_descriptors',
        base={'uid': UID, 'workstream_id': 'ws-1'},
        neutrals={'limit': _LIMIT},
    )
)
_add(DriverEntry('database.workstreams.list_continuation_checkpoints', base={'uid': UID, 'workstream_id': 'ws-1'}))
_add(
    DriverEntry(
        'database.workstreams.list_open_workstreams',
        base={'uid': UID},
        domains={'account_generation': [None, 1]},
        neutrals={'limit': (500, 'page bound; fixed')},
    )
)
_add(
    DriverEntry(
        'database.workstreams.list_workstream_events',
        base={'uid': UID, 'workstream_id': 'ws-1'},
        domains={'after_sequence': [0, 5]},
        neutrals={'limit': _LIMIT},
    )
)
_add(
    DriverEntry(
        'database.workstreams.list_workstreams_for_goal',
        base={'uid': UID, 'goal_id': 'goal-1'},
        domains={'include_archived': [False, True]},
        neutrals={'limit': _LIMIT},
    )
)

_add(DriverEntry('database.x_posts.count_x_posts', base={'uid': UID}))
_add(DriverEntry('database.x_posts.get_newest_tweet_id', base={'uid': UID}))
_add(
    DriverEntry(
        'database.x_posts.get_pending_memory_extraction_posts',
        base={'uid': UID},
        neutrals={'limit': (200, 'page bound; fixed')},
    )
)
_add(
    DriverEntry(
        'database.x_posts.get_x_posts',
        base={'uid': UID},
        domains={'kind': [None, 'kind-1']},
        neutrals={'limit': _LIMIT},
    )
)

_add(
    CoveredByEntry(
        'database.firestore_query_types.FirestoreQuerySpec.build',
        covered_by=(
            'database.mcp_conversation_pages.get_mcp_conversation_cards',
            'database.mcp_conversation_pages.get_mcp_conversation_cards_page',
            'database.memories.count_memories_created',
            'database.memories.scan_memories_created_at_page',
            'database.memories.scan_memories_updated_at_page',
        ),
        reason='generic dataclass builder; it returns query objects and the terminals '
        'execute inside its consumers, so it never appears as a caller',
        expect_observed=False,
        body_digest=BODY_DIGEST['database.firestore_query_types.FirestoreQuerySpec.build'],
    )
)

_add(
    DriverEntry(
        'database.sync_recording_lineage.get_recording_generations',
        base={'uid': UID, 'origin_id': 'recording-1', 'started_before': T1, 'finished_after': T0},
        domains={'include_capture_evidence': [False, True]},
        neutrals={'limit': _LIMIT},
    )
)
_add(
    DriverEntry(
        'database.sync_recording_lineage.get_origin_generation',
        base={'uid': UID, 'origin_id': 'recording-1'},
        domains={'include_capture_evidence': [False, True]},
        neutrals={'limit': _LIMIT},
    )
)
_add(
    CoveredByEntry(
        'database.sync_recording_lineage._rows',
        covered_by=(
            'database.sync_recording_lineage.get_recording_generations',
            'database.sync_recording_lineage.get_origin_generation',
        ),
        reason='list-materializing helper; its query.stream() terminal is observed for both lineage readers',
    )
)

_add(
    DriverEntry(
        'database.conversation_terminal_title.dead_letter_conversation_updates',
        base={
            'uid': UID,
            'conversation': {'transcript_segments': []},
            'conversation_ref': ref_document(f'users/{UID}/conversations/conv-1'),
            'transaction': ref_transaction(),
            'failure_code': 'processing_failed',
            'time_zone_for_uid': None,
        },
    )
)
_add(
    CoveredByEntry(
        'database.conversation_terminal_title._has_described_photo',
        covered_by=('database.conversation_terminal_title.dead_letter_conversation_updates',),
        reason='photo-description probe streams the photos subcollection inside the caller transaction '
        'when a retryable failure row has no transcript text',
    )
)

for entry in (*outside_drivers.DRIVERS.values(), *outside_drivers.COVERED_BY.values(), *outside_drivers.SKIPS.values()):
    _add(entry)


_add(
    DriverEntry(
        'database.action_item_refresh.task_refs',
        base={'user': ref_document(f'users/{UID}'), 'conversation_id': 'conv-1', 'transaction': ref_transaction()},
    )
)


def _refresh_seed(client, combo, trial):
    client.documents[f'users/{UID}/conversations/conv-1'] = {'id': 'conv-1'}
    client.documents[f'users/{UID}/conversations/donor-1'] = {'deleted': True, 'smart_merge': {'survivor_id': 'conv-1'}}


_add(
    DriverEntry(
        'database.action_item_refresh.reconcile',
        base={'uid': UID, 'conversation_id': 'conv-1', 'items': [], 'expected_revision': None},
        domains={'donor_id': [None, 'donor-1']},
        setup=_refresh_seed,
        patchers=(_redis_noop('database.action_item_refresh.bump_action_items_list_version'),),
    )
)

# Proactivity v2: real serving builders, empty owner-safe page and mature cohort.
_add(
    DriverEntry(
        'database.proactivity.list_feed',
        base={'uid': UID},
        neutrals={
            'limit': _LIMIT,
            'cursor': ('', 'first page; keyset does not alter index shape'),
            'now': (T0, 'fixed UTC observation time'),
        },
        setup=_seed(f'users/{UID}', {'subscription': {'plan': 'basic'}}),
    )
)
_add(
    DriverEntry(
        'database.proactivity.refresh_health',
        base={'name': 'commitment_followup'},
        neutrals={'now': (T0, 'fixed UTC cohort boundary')},
    )
)
_add(
    CoveredByEntry(
        'database.proactivity.feed_query',
        covered_by=('database.proactivity.list_feed',),
        reason='Query builder consumed by the serving parent',
        expect_observed=False,
        body_digest=BODY_DIGEST['database.proactivity.feed_query'],
    )
)
_add(
    CoveredByEntry(
        'database.proactivity.cohort_query',
        covered_by=('database.proactivity.refresh_health',),
        reason='Query builder consumed by the serving parent',
        expect_observed=False,
        body_digest=BODY_DIGEST['database.proactivity.cohort_query'],
    )
)


_add(
    DriverEntry(
        'database.proactivity.purge_source_items',
        base={'uid': UID, 'source_kind': 'action_item', 'source_id': 'item-1'},
    )
)


# Producer serving paths use bounded history and canonical source mappings.
def _proactivity_producer_clock(_client):
    # utc_now is imported from config, outside the harness's module clock scope.
    return unittest.mock.patch('database.proactivity_producers.utc_now', return_value=T0)


_add(DriverEntry('database.proactivity_producers.delivered_mentor_items', base={'uid': UID}))
_add(
    DriverEntry(
        'database.proactivity_producers.record_mentor_reply',
        base={'uid': UID},
        patchers=(_proactivity_producer_clock,),
    )
)
_add(
    DriverEntry(
        'database.proactivity_producers.record_task_completion',
        base={'uid': UID, 'task_id': 'item-1'},
        patchers=(_proactivity_producer_clock,),
    )
)

_add(
    CoveredByEntry(
        'database.proactivity_producers.mentor_history_query',
        covered_by=('database.proactivity_producers.delivered_mentor_items',),
        reason='Builder consumed by its registered serving parent',
        expect_observed=False,
        body_digest=BODY_DIGEST['database.proactivity_producers.mentor_history_query'],
    )
)

_add(
    CoveredByEntry(
        'database.proactivity_producers.recent_mentor_query',
        covered_by=('database.proactivity_producers.record_mentor_reply',),
        reason='Builder consumed by its registered serving parent',
        expect_observed=False,
        body_digest=BODY_DIGEST['database.proactivity_producers.recent_mentor_query'],
    )
)

_add(
    CoveredByEntry(
        'database.proactivity_producers.task_items_query',
        covered_by=('database.proactivity_producers.record_task_completion',),
        reason='Builder consumed by its registered serving parent',
        expect_observed=False,
        body_digest=BODY_DIGEST['database.proactivity_producers.task_items_query'],
    )
)
