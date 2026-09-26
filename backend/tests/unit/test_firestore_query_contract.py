import ast
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import SimpleNamespace

import pytest
from google.cloud.firestore_v1 import FieldFilter

import database.firestore_index_registry as firestore_index_registry
import database.action_items as action_items_db
import database.chat as chat_db
import database.conversations as conversations_db
import database.memories as memories_db
import database.task_recommendations as task_recommendations_db
import routers.task_recommendations as task_recommendations_router
from database.firestore_index_registry import (
    ACTIVE_ATTENTION_OVERRIDE_QUERY,
    CANONICAL_CONSOLIDATION_QUERY,
    CANONICAL_MEMORY_ATLAS_READ_QUERY,
    CONVERSATION_PHOTOS_NAME_RANGE_QUERY,
    CONVERSATION_SOURCE_MEMORY_QUERY,
    CONVERSATIONS_ACTIVE_ORDERED_QUERY,
    DUE_MEMORY_OUTBOX_QUERY,
    DAILY_SWEEP_ONBOARDING_CONVERSATIONS_QUERY,
    EXPIRED_SHORT_TERM_LIFECYCLE_QUERY,
    EXPIRED_MEMORY_OUTBOX_LEASE_QUERY,
    INDEX_ONLY_REQUIREMENTS,
    INDEX_REQUIREMENTS,
    MESSAGES_BY_APP_ORDERED_QUERY,
    MESSAGES_BY_SESSION_ORDERED_QUERY,
    POLICY_EXPIRED_SHORT_TERM_QUERY,
    RECENT_REJECTED_MEMORY_FEEDBACK_QUERY,
    REVIEW_QUEUE_BY_CONFLICT_QUERY,
    REVIEW_QUEUE_BY_FACT_QUERY,
    REVIEW_QUEUE_BY_STATUS_QUERY,
    REVIEW_QUEUE_BY_STATUS_ID_QUERY,
    REVIEW_QUEUE_ORDERED_QUERY,
    REQUIRED_MEMORY_PROCESSING_QUERY,
    SUPERSEDED_MEMORY_BY_CANONICAL_TARGET_QUERY,
    SUPERSEDED_MEMORY_BY_LEGACY_TARGET_QUERY,
    STALE_IN_PROGRESS_CONVERSATIONS_QUERY,
    UNIVERSAL_CANONICAL_LIST_SCAN_QUERY,
    UNIVERSAL_HISTORICAL_CREATED_LIST_SCAN_QUERY,
    UNIVERSAL_HISTORICAL_UPDATED_LIST_SCAN_QUERY,
    QUERY_SPECS,
    FirestoreIndexField,
    FirestoreQueryFilter,
    FirestoreQuerySpec,
    _index_fields_need_composite_manifest,
    firebase_index_manifest,
)
from scripts import firestore_query_coverage, generate_firestore_indexes
from utils.memory import canonical_graph as canonical_graph_service


class _RecordingQuery:
    def __init__(self):
        self.filters = []

    def where(self, *, filter):
        self.filters.append((filter.field_path, filter.op_string, filter.value))
        return self


class _OverrideSnapshot:
    def __init__(self, payload):
        self._payload = payload

    def to_dict(self):
        return dict(self._payload)


class _OverrideCollection:
    def __init__(self, rows, filters=()):
        self.rows = rows
        self.filters = filters

    def where(self, *, filter):
        return _OverrideCollection(self.rows, (*self.filters, (filter.field_path, filter.op_string, filter.value)))

    def stream(self):
        def matches(payload):
            for field, operator, expected in self.filters:
                actual = payload.get(field)
                if operator == '==' and actual != expected:
                    return False
                if operator == '>' and not (actual is not None and actual > expected):
                    return False
            return True

        return [_OverrideSnapshot(payload) for payload in self.rows if matches(payload)]


class _OverrideUserRef:
    def __init__(self, rows):
        self.rows = rows

    def collection(self, name):
        assert name == 'task_attention_overrides'
        return _OverrideCollection(self.rows)


class _OverrideUsersCollection:
    def __init__(self, rows):
        self.rows = rows

    def document(self, _uid):
        return _OverrideUserRef(self.rows)


class _OverrideFirestore:
    def __init__(self, rows):
        self.rows = rows

    def collection(self, name):
        assert name == 'users'
        return _OverrideUsersCollection(self.rows)


def test_registered_attention_override_query_builds_the_real_filter_chain():
    query = _RecordingQuery()
    now = object()

    built = ACTIVE_ATTENTION_OVERRIDE_QUERY.build(
        query,
        {'account_generation': 4, 'now': now},
        field_filter_factory=FieldFilter,
    )

    assert built is query
    assert query.filters == [('account_generation', '==', 4), ('expires_at', '>', now)]


@pytest.mark.parametrize(
    ("spec", "values", "expected"),
    [
        (
            REQUIRED_MEMORY_PROCESSING_QUERY,
            {
                "tier": "short_term",
                "status": "active",
                "processing_state": "pending",
                "required": True,
                "processing_statuses": ["pending_processing", "processing_failed_retryable"],
            },
            [
                ("tier", "==", "short_term"),
                ("status", "==", "active"),
                ("processing_state", "==", "pending"),
                ("promotion.required", "==", True),
                (
                    "promotion.processing_status",
                    "in",
                    ["pending_processing", "processing_failed_retryable"],
                ),
            ],
        ),
        (
            CANONICAL_CONSOLIDATION_QUERY,
            {
                "tier": "short_term",
                "status": "active",
                "processing_state": "processed",
                "source_state": "active",
            },
            [
                ("tier", "==", "short_term"),
                ("status", "==", "active"),
                ("processing_state", "==", "processed"),
                ("source_state", "==", "active"),
            ],
        ),
        (
            RECENT_REJECTED_MEMORY_FEEDBACK_QUERY,
            {
                "statuses": ["active", "hidden"],
                "source_state": "active",
                "user_review": False,
                "updated_at": datetime(2026, 8, 1, tzinfo=timezone.utc),
            },
            [
                ("status", "in", ["active", "hidden"]),
                ("source_state", "==", "active"),
                ("promotion.user_review", "==", False),
                ("updated_at", ">=", datetime(2026, 8, 1, tzinfo=timezone.utc)),
            ],
        ),
        (
            CONVERSATION_SOURCE_MEMORY_QUERY,
            {"source_id": "conversation-a"},
            [("source_ids", "array_contains", "conversation-a")],
        ),
        (
            SUPERSEDED_MEMORY_BY_CANONICAL_TARGET_QUERY,
            {
                "status": "superseded",
                "target_memory_ids": ["memory-a", "memory-b"],
            },
            [
                ("status", "==", "superseded"),
                ("canonical_memory_id", "in", ["memory-a", "memory-b"]),
            ],
        ),
        (
            SUPERSEDED_MEMORY_BY_LEGACY_TARGET_QUERY,
            {
                "status": "superseded",
                "target_memory_ids": ["memory-a", "memory-b"],
            },
            [
                ("status", "==", "superseded"),
                ("superseded_by", "in", ["memory-a", "memory-b"]),
            ],
        ),
        (
            EXPIRED_SHORT_TERM_LIFECYCLE_QUERY,
            {
                "tier": "short_term",
                "status": "active",
                "processing_state": "processed",
                "expires_at": "2026-07-28T12:00:00+00:00",
            },
            [
                ("tier", "==", "short_term"),
                ("status", "==", "active"),
                ("processing_state", "==", "processed"),
                ("expires_at", "<=", "2026-07-28T12:00:00+00:00"),
            ],
        ),
        (
            POLICY_EXPIRED_SHORT_TERM_QUERY,
            {
                "tier": "short_term",
                "status": "active",
                "processing_state": "processed",
                "source_state": "active",
                "captured_at": "2026-07-26T12:00:00+00:00",
            },
            [
                ("tier", "==", "short_term"),
                ("status", "==", "active"),
                ("processing_state", "==", "processed"),
                ("source_state", "==", "active"),
                ("captured_at", "<=", "2026-07-26T12:00:00+00:00"),
            ],
        ),
        (
            DUE_MEMORY_OUTBOX_QUERY,
            {"status": "pending", "available_at": "2026-07-28T12:00:00+00:00"},
            [
                ("status", "==", "pending"),
                ("available_at", "<=", "2026-07-28T12:00:00+00:00"),
            ],
        ),
        (
            EXPIRED_MEMORY_OUTBOX_LEASE_QUERY,
            {
                "event_type": "projection_sync",
                "status": "processing",
                "lease_expires_at": "2026-07-28T12:00:00+00:00",
            },
            [
                ("event_type", "==", "projection_sync"),
                ("status", "==", "processing"),
                ("lease_expires_at", "<=", "2026-07-28T12:00:00+00:00"),
            ],
        ),
        (
            REVIEW_QUEUE_BY_FACT_QUERY,
            {"fact_ids": ["memory-a", "memory-b"]},
            [("fact_id", "in", ["memory-a", "memory-b"])],
        ),
        (
            REVIEW_QUEUE_BY_CONFLICT_QUERY,
            {"conflict_ids": ["memory-a", "memory-b"]},
            [("conflict_with", "array_contains_any", ["memory-a", "memory-b"])],
        ),
        (
            REVIEW_QUEUE_BY_STATUS_QUERY,
            {"status": "pending"},
            [("status", "==", "pending")],
        ),
        (
            REVIEW_QUEUE_ORDERED_QUERY,
            {},
            [],
        ),
        (
            REVIEW_QUEUE_BY_STATUS_ID_QUERY,
            {"status": "pending"},
            [("status", "==", "pending")],
        ),
        (
            STALE_IN_PROGRESS_CONVERSATIONS_QUERY,
            {"status": "in_progress"},
            [("status", "==", "in_progress")],
        ),
    ],
)
def test_registered_memory_maintenance_queries_build_the_real_filter_chains(spec, values, expected):
    query = _RecordingQuery()

    built = spec.build(query, values, field_filter_factory=FieldFilter)

    assert built is query
    assert query.filters == expected


def test_what_matters_now_route_executes_the_registered_attention_override_query(monkeypatch):
    now = datetime(2026, 7, 14, tzinfo=timezone.utc)
    database = _OverrideFirestore(
        [
            {'dedupe_key': 'active', 'account_generation': 3, 'expires_at': now + timedelta(minutes=1)},
            {'dedupe_key': 'expired', 'account_generation': 3, 'expires_at': now - timedelta(minutes=1)},
            {'dedupe_key': 'prior-generation', 'account_generation': 2, 'expires_at': now + timedelta(minutes=1)},
        ]
    )
    sentinel_projection = object()
    monkeypatch.setattr(
        task_recommendations_router,
        '_rollout',
        lambda _uid: SimpleNamespace(intelligence_product_enabled=True, account_generation=3),
    )
    monkeypatch.setattr(task_recommendations_router, '_bound_device_id', lambda *_args, **_kwargs: None)

    def evaluate(uid, _request, *, account_generation, **_kwargs):
        assert uid == 'smoke-user'
        assert account_generation == 3
        assert task_recommendations_db.list_active_override_dedupe_keys(
            uid,
            now=now,
            account_generation=account_generation,
            firestore_client=database,
        ) == {'active'}
        return sentinel_projection

    monkeypatch.setattr(task_recommendations_router.recommendations, 'evaluate', evaluate)

    result = task_recommendations_router.get_what_matters_now(
        request_context=object(), device_id=None, uid='smoke-user'
    )

    assert result is sentinel_projection


def test_generated_firestore_manifest_matches_the_checked_in_contract():
    manifest_path = Path(__file__).resolve().parents[3] / 'firestore.indexes.json'
    expected_conversations_status_finished = {
        'collectionGroup': 'conversations',
        'queryScope': 'COLLECTION',
        'fields': [
            {'fieldPath': 'status', 'order': 'ASCENDING'},
            {'fieldPath': 'finished_at', 'order': 'ASCENDING'},
            {'fieldPath': '__name__', 'order': 'ASCENDING'},
        ],
    }

    assert manifest_path.read_text(encoding='utf-8') == generate_firestore_indexes.render_manifest()
    assert any(
        requirement.identifier == 'conversations_status_finished'
        and requirement.to_manifest() == expected_conversations_status_finished
        for requirement in INDEX_ONLY_REQUIREMENTS
    )
    assert (
        STALE_IN_PROGRESS_CONVERSATIONS_QUERY.index_requirement.to_manifest() == expected_conversations_status_finished
    )
    assert firebase_index_manifest()['indexes'].count(expected_conversations_status_finished) == 1
    assert CANONICAL_MEMORY_ATLAS_READ_QUERY.index_requirement.to_manifest() in firebase_index_manifest()['indexes']
    assert CANONICAL_MEMORY_ATLAS_READ_QUERY.identifier == 'memory_items_canonical_atlas_read'
    assert CANONICAL_MEMORY_ATLAS_READ_QUERY.index_requirement.signature == (
        'memory_items',
        'COLLECTION',
        (
            ('account_generation', 'ASCENDING'),
            ('tier', 'ASCENDING'),
            ('status', 'ASCENDING'),
            ('processing_state', 'ASCENDING'),
            ('updated_at', 'DESCENDING'),
            ('__name__', 'DESCENDING'),
        ),
    )


def test_daily_sweep_onboarding_query_uses_one_deployable_range_order():
    query = _RecordingQuery()
    built = DAILY_SWEEP_ONBOARDING_CONVERSATIONS_QUERY.build(
        query,
        {"onboarding_marker": ""},
        field_filter_factory=FieldFilter,
    )

    assert built is query
    assert query.filters == [("external_data.onboarding_session_id", ">", "")]
    assert DAILY_SWEEP_ONBOARDING_CONVERSATIONS_QUERY.query_signature == (
        "conversations",
        "COLLECTION",
        (("external_data.onboarding_session_id", ">"),),
    )
    assert DAILY_SWEEP_ONBOARDING_CONVERSATIONS_QUERY.index_requirement.to_manifest() == {
        "collectionGroup": "conversations",
        "queryScope": "COLLECTION",
        "fields": [{"fieldPath": "external_data.onboarding_session_id", "order": "ASCENDING"}],
    }


def _equality_plus_order_signature(collection_group, filters, orders):
    """Composite Firestore requires for equality filters plus explicit orderings."""
    fields = [(field_path, 'ASCENDING') for field_path, operator in filters if operator == '==']
    fields.extend(orders)
    if not fields or fields[-1][0] != '__name__':
        fields.append(('__name__', orders[-1][1] if orders else 'ASCENDING'))
    return (collection_group, 'COLLECTION', tuple(fields))


def test_canonical_atlas_read_serving_query_requires_declared_composite():
    """The live atlas list query must keep its apply-spec composite.

    firestore_readiness failed on based-hardware-dev (run 31666135748) with
    COLLECTION/memory_items (account_generation ASC, tier ASC, status ASC,
    processing_state ASC, updated_at DESC, __name__ DESC)=MISSING. That tuple is
    memory_items_canonical_atlas_read; dropping it from the apply spec while the
    serving builder still uses it must fail here.
    """
    recorded = _StreamRecordingQuery(recorder=[])
    client = SimpleNamespace(collection=lambda path: recorded)
    revision = canonical_graph_service._CanonicalGraphRevision(
        account_generation=3,
        commit_sequence=1,
        head_commit_id='head-atlas',
    )

    built = canonical_graph_service._build_canonical_graph_items_query(
        client,
        'atlas-index-user',
        revision,
        cursor_boundary=None,
    )

    assert built is not recorded
    signature = _equality_plus_order_signature('memory_items', built._filters, built._orders)
    assert signature == CANONICAL_MEMORY_ATLAS_READ_QUERY.index_requirement.signature
    assert signature in _declared_index_signatures()


@pytest.mark.slow
def test_query_inventory_registers_the_migrated_query_shapes():
    report = firestore_query_coverage.report_for(firestore_query_coverage.inventory(waiver_ids=set()))

    for spec in (
        DUE_MEMORY_OUTBOX_QUERY,
        EXPIRED_MEMORY_OUTBOX_LEASE_QUERY,
        REVIEW_QUEUE_BY_FACT_QUERY,
        REVIEW_QUEUE_BY_CONFLICT_QUERY,
        REVIEW_QUEUE_BY_STATUS_QUERY,
        REVIEW_QUEUE_ORDERED_QUERY,
        REVIEW_QUEUE_BY_STATUS_ID_QUERY,
        REQUIRED_MEMORY_PROCESSING_QUERY,
        CANONICAL_CONSOLIDATION_QUERY,
        CONVERSATION_SOURCE_MEMORY_QUERY,
        SUPERSEDED_MEMORY_BY_CANONICAL_TARGET_QUERY,
        SUPERSEDED_MEMORY_BY_LEGACY_TARGET_QUERY,
        EXPIRED_SHORT_TERM_LIFECYCLE_QUERY,
        POLICY_EXPIRED_SHORT_TERM_QUERY,
        ACTIVE_ATTENTION_OVERRIDE_QUERY,
        STALE_IN_PROGRESS_CONVERSATIONS_QUERY,
        UNIVERSAL_CANONICAL_LIST_SCAN_QUERY,
        UNIVERSAL_HISTORICAL_UPDATED_LIST_SCAN_QUERY,
        UNIVERSAL_HISTORICAL_CREATED_LIST_SCAN_QUERY,
    ):
        matching = [query for query in report['queries'] if query['registered_spec'] == spec.identifier]
        assert len(matching) == 1
        assert matching[0]['classification'] == 'registered'
        assert matching[0]['collection_group'] == spec.collection_group
    assert report['counts']['serving']['registered'] >= 14


def test_inventory_finds_a_direct_compound_chain_wrapped_by_list():
    tree = ast.parse(
        "def read(client):\n"
        "    return list(client.collection('items').where('status', '==', 'open').where('expires_at', '>', 0).stream())\n"
    )
    function = tree.body[0]
    analyzer = firestore_query_coverage.FunctionQueryAnalyzer(
        source='backend/database/example.py',
        symbol='read',
        constants={},
        non_serving_scope=None,
        registered_signatures={},
        waiver_ids=set(),
    )

    shapes = analyzer.analyze(function.body)

    assert len(shapes) == 1
    assert shapes[0].classification == 'raw_unregistered'
    assert [(field.field_path, field.operator) for field in shapes[0].components] == [
        ('status', '=='),
        ('expires_at', '>'),
    ]


class _StreamRecordingQuery:
    """One Firestore query chain that records itself when production code streams it."""

    def __init__(self, recorder, filters=(), orders=()):
        self._recorder = recorder
        self._filters = tuple(filters)
        self._orders = tuple(orders)

    def where(self, *, filter):
        return _StreamRecordingQuery(
            self._recorder, (*self._filters, (filter.field_path, filter.op_string)), self._orders
        )

    def order_by(self, field_path, direction):
        return _StreamRecordingQuery(self._recorder, self._filters, (*self._orders, (field_path, direction)))

    def select(self, _fields):
        return self

    def offset(self, _n):
        return self

    def limit(self, _n):
        return self

    def stream(self):
        self._recorder.append((self._filters, self._orders))
        return []


class _StreamRecordingUserRef:
    def __init__(self, recorder, collection_name='action_items'):
        self._recorder = recorder
        self._collection_name = collection_name

    def collection(self, name):
        assert name == self._collection_name
        return _StreamRecordingQuery(self._recorder)


class _StreamRecordingFirestore:
    def __init__(self, recorder, collection_name='action_items'):
        self._recorder = recorder
        self._collection_name = collection_name

    def collection(self, name):
        assert name == 'users'
        return SimpleNamespace(document=lambda _uid: _StreamRecordingUserRef(self._recorder, self._collection_name))


def _declared_index_signatures():
    return {
        (
            index['collectionGroup'],
            index['queryScope'],
            tuple((field['fieldPath'], field.get('order') or field.get('arrayConfig')) for field in index['fields']),
        )
        for index in firebase_index_manifest()['indexes']
    }


@pytest.mark.parametrize('completed', [None, False, True])
def test_due_date_filtered_action_item_reads_have_a_declared_composite_index(monkeypatch, completed):
    """A due-range read orders due_at ascending; without the matching index prod 500s.

    Regression for #10777: chat's get_action_items tool and GET /v1/action-items both
    raised FailedPrecondition because only (completed ASC, due_at DESC) was deployed.
    """
    recorder = []
    monkeypatch.setattr(action_items_db, 'db', _StreamRecordingFirestore(recorder))

    action_items_db.get_action_items(
        'index-contract-user',
        completed=completed,
        due_start_date=datetime(2026, 7, 1, tzinfo=timezone.utc),
        due_end_date=datetime(2026, 7, 31, tzinfo=timezone.utc),
        limit=50,
    )

    compound = [(filters, orders) for filters, orders in recorder if orders and any(op == '==' for _, op in filters)]
    assert compound, 'due-date filtered reads no longer build an equality + ordering chain'
    declared = _declared_index_signatures()
    for filters, orders in compound:
        assert _equality_plus_order_signature('action_items', filters, orders) in declared


@pytest.mark.parametrize(
    ('symbol', 'call'),
    [
        ('get_app_messages', lambda: chat_db.get_app_messages('index-contract-user', 'some-app', limit=20)),
        (
            'get_messages',
            lambda: chat_db.get_messages('index-contract-user', app_id='some-app', limit=20),
        ),
    ],
)
def test_app_scoped_message_reads_have_a_declared_composite_index(monkeypatch, symbol, call):
    """plugin_id-filtered, created_at-descending message reads need a declared composite.

    Regression for a self-host FailedPrecondition 400 on GET /v1/messages: prod has this
    index only because it was created by hand at some point, but firestore_index_registry.py
    never declared it, so a fresh self-host deploy 400s on this exact query.
    """
    recorder = []
    monkeypatch.setattr(chat_db, 'db', _StreamRecordingFirestore(recorder, collection_name='messages'))

    call()

    compound = [(filters, orders) for filters, orders in recorder if orders and any(op == '==' for _, op in filters)]
    assert compound, f'{symbol} no longer builds a plugin_id equality + created_at ordering chain'
    declared = _declared_index_signatures()
    for filters, orders in compound:
        assert _equality_plus_order_signature('messages', filters, orders) in declared


def test_session_scoped_message_reads_have_a_declared_composite_index(monkeypatch):
    """chat_session_id-filtered, created_at-descending message reads need a declared composite.

    Regression for a self-host FailedPrecondition 400 on GET /v2/messages?chat_session_id=...:
    a chat session's first page of messages hits this branch instead of the app-scoped one,
    and it fails independently of it.
    """
    recorder = []
    monkeypatch.setattr(chat_db, 'db', _StreamRecordingFirestore(recorder, collection_name='messages'))

    chat_db.get_messages('index-contract-user', chat_session_id='some-session', limit=20)

    compound = [(filters, orders) for filters, orders in recorder if orders and any(op == '==' for _, op in filters)]
    assert compound, 'get_messages(chat_session_id=...) no longer builds an equality + created_at ordering chain'
    declared = _declared_index_signatures()
    for filters, orders in compound:
        assert _equality_plus_order_signature('messages', filters, orders) in declared


def test_messages_by_app_ordered_query_is_registered_for_the_messages_collection():
    assert MESSAGES_BY_APP_ORDERED_QUERY.collection_group == 'messages'
    assert MESSAGES_BY_APP_ORDERED_QUERY.index_requirement.to_manifest() in firebase_index_manifest()['indexes']


def test_messages_by_session_ordered_query_is_registered_for_the_messages_collection():
    assert MESSAGES_BY_SESSION_ORDERED_QUERY.collection_group == 'messages'
    assert MESSAGES_BY_SESSION_ORDERED_QUERY.index_requirement.to_manifest() in firebase_index_manifest()['indexes']


@pytest.mark.parametrize(
    ('symbol', 'call'),
    [
        ('get_conversations', lambda: conversations_db.get_conversations('index-contract-user', limit=20)),
        (
            'get_conversations_without_photos',
            lambda: conversations_db.get_conversations_without_photos('index-contract-user', limit=20),
        ),
    ],
)
def test_default_conversation_list_reads_have_a_declared_composite_index(monkeypatch, symbol, call):
    """The bare `discarded == False` + `created_at` descending list read needs a declared composite.

    Regression for a self-host FailedPrecondition 400 on GET /v1/conversations: this is the
    app's default conversation list call (no status/category/folder/starred filter), prod has
    the index only because it was created by hand at some point, but firestore_index_registry.py
    never declared it, so a fresh self-host deploy 400s the first time anyone loads their list.
    """
    recorder = []
    monkeypatch.setattr(conversations_db, 'db', _StreamRecordingFirestore(recorder, collection_name='conversations'))

    call()

    compound = [(filters, orders) for filters, orders in recorder if orders and any(op == '==' for _, op in filters)]
    assert compound, f'{symbol} no longer builds a discarded equality + created_at ordering chain'
    declared = _declared_index_signatures()
    for filters, orders in compound:
        assert _equality_plus_order_signature('conversations', filters, orders) in declared


@pytest.mark.parametrize(
    ('symbol', 'call'),
    [
        ('get_in_progress_conversation', lambda: conversations_db.get_in_progress_conversation('index-contract-user')),
        ('get_action_items', lambda: conversations_db.get_action_items('index-contract-user', limit=20)),
    ],
)
def test_conversations_status_ordered_reads_have_a_declared_composite_index(monkeypatch, symbol, call):
    """Status-filtered, created_at-descending conversation reads need a declared composite.

    Regression for a self-host FailedPrecondition 400 on the in-progress-conversation poll
    and the action-items read: prod has this index only because it was created by hand, but
    firestore_index_registry.py never declared it.
    """
    recorder = []
    monkeypatch.setattr(conversations_db, 'db', _StreamRecordingFirestore(recorder, collection_name='conversations'))

    call()

    compound = [(filters, orders) for filters, orders in recorder if orders and any(op == '==' for _, op in filters)]
    assert compound, f'{symbol} no longer builds a status equality + created_at ordering chain'
    declared = _declared_index_signatures()
    for filters, orders in compound:
        assert _equality_plus_order_signature('conversations', filters, orders) in declared


def test_conversations_active_ordered_query_is_registered_for_the_conversations_collection():
    assert CONVERSATIONS_ACTIVE_ORDERED_QUERY.collection_group == 'conversations'
    assert CONVERSATIONS_ACTIVE_ORDERED_QUERY.index_requirement.to_manifest() in firebase_index_manifest()['indexes']


def test_default_memories_list_read_has_a_declared_composite_index():
    """The bare scoring+created_at sort (no filters at all) still needs a composite.

    Regression: get_memories' default path (no category/date filters, default
    sort='scoring_desc') orders by two fields with zero `where` calls. Prod has this
    index only because it was created by hand at some point.
    """
    recorder = []
    memories_db.get_memories(
        'index-contract-user', firestore_client=_StreamRecordingFirestore(recorder, collection_name='memories')
    )

    assert recorder, 'get_memories no longer streams a query for its default path'
    filters, orders = recorder[0]
    assert not filters
    assert orders == (('scoring', 'DESCENDING'), ('created_at', 'DESCENDING'))
    declared = _declared_index_signatures()
    assert _equality_plus_order_signature('memories', filters, orders) in declared


def test_conversations_and_memories_index_only_requirements_are_registered():
    identifiers = {requirement.identifier: requirement for requirement in INDEX_ONLY_REQUIREMENTS}
    for identifier in (
        'conversations_status_created',
        'conversations_discarded_status_created',
        'memories_scoring_created',
    ):
        assert identifier in identifiers
        assert identifiers[identifier].to_manifest() in firebase_index_manifest()['indexes']


def test_query_source_paths_are_posix_canonical_on_every_host_platform():
    windows_path = PureWindowsPath('backend\\database\\conversations.py')
    posix_path = PurePosixPath('backend/database/conversations.py')

    assert firestore_query_coverage.canonical_source_path(windows_path) == 'backend/database/conversations.py'
    assert firestore_query_coverage.canonical_source_path(
        windows_path
    ) == firestore_query_coverage.canonical_source_path(posix_path)


def _asc(field_path: str) -> FirestoreIndexField:
    return FirestoreIndexField(field_path, order='ASCENDING')


def _desc(field_path: str) -> FirestoreIndexField:
    return FirestoreIndexField(field_path, order='DESCENDING')


def _contains(field_path: str) -> FirestoreIndexField:
    return FirestoreIndexField(field_path, array_config='CONTAINS')


def _platform_requires_composite(index_fields: tuple[FirestoreIndexField, ...]) -> bool:
    """Firestore's automatic single-field rule, restated from platform docs.

    Independent of ``_index_fields_need_composite_manifest``. Automatic indexes
    cover ``field ASC, __name__ ASC`` and ``field DESC, __name__ DESC`` only.
    Opposite-direction ``field`` + ``__name__`` and any multi-field order need
    a declared composite. Array-contains (+ ``__name__``) stays automatic.
    https://firebase.google.com/docs/firestore/query-data/index-overview
    """
    non_name = [field for field in index_fields if field.field_path != '__name__']
    name_fields = [field for field in index_fields if field.field_path == '__name__']
    if any(field.array_config is not None for field in index_fields):
        return False
    if len(non_name) > 1:
        return True
    if len(non_name) != 1 or len(name_fields) != 1:
        return False
    ordered = non_name[0]
    name = name_fields[0]
    if ordered.order is None or name.order is None:
        return False
    return ordered.order != name.order


@pytest.mark.parametrize(
    ('fields', 'needs_composite'),
    [
        ((_desc('updated_at'), _desc('__name__')), False),
        ((_asc('updated_at'), _asc('__name__')), False),
        ((_desc('updated_at'), _asc('__name__')), True),
        ((_asc('updated_at'), _desc('__name__')), True),
        ((_asc('status'), _desc('updated_at'), _asc('__name__')), True),
        ((_contains('source_ids'), _asc('__name__')), False),
        ((_desc('updated_at'),), False),
    ],
)
def test_manifest_generator_classifies_the_firestore_single_field_rule(fields, needs_composite):
    assert _index_fields_need_composite_manifest(fields) is needs_composite


def test_every_composite_requiring_query_spec_is_declared_in_the_checked_in_manifest():
    """Independent of the generator: the checked-in file must declare each needed composite.

    ``test_generated_firestore_manifest_matches_the_checked_in_contract`` compares
    the generator to the file, so a generator shortcut makes both sides wrong
    together. This oracle restates Firestore's rule and then reads the file.
    The three list-scan specs from #11684 are named so deleting them from
    ``QUERY_SPECS`` cannot make the test vacuous.
    """
    outage_required_specs = (
        UNIVERSAL_CANONICAL_LIST_SCAN_QUERY,
        UNIVERSAL_HISTORICAL_UPDATED_LIST_SCAN_QUERY,
        UNIVERSAL_HISTORICAL_CREATED_LIST_SCAN_QUERY,
    )
    for spec in outage_required_specs:
        assert spec in QUERY_SPECS
        assert _platform_requires_composite(spec.index_fields)

    manifest_path = Path(__file__).resolve().parents[3] / 'firestore.indexes.json'
    checked_in = json.loads(manifest_path.read_text(encoding='utf-8'))
    declared = {
        (
            index['collectionGroup'],
            index['queryScope'],
            tuple((field['fieldPath'], field.get('order') or field.get('arrayConfig')) for field in index['fields']),
        )
        for index in checked_in['indexes']
    }
    missing = [
        spec.identifier
        for spec in QUERY_SPECS
        if _platform_requires_composite(spec.index_fields) and spec.index_requirement.signature not in declared
    ]
    assert missing == []


def test_document_id_only_collection_group_range_has_no_impossible_composite_requirement():
    assert CONVERSATION_PHOTOS_NAME_RANGE_QUERY in QUERY_SPECS
    assert all(
        requirement.identifier != CONVERSATION_PHOTOS_NAME_RANGE_QUERY.identifier for requirement in INDEX_REQUIREMENTS
    )

    manifest = firebase_index_manifest()
    assert not any(
        index['collectionGroup'] == 'photos'
        and index['queryScope'] == 'COLLECTION_GROUP'
        and index['fields'] == [{'fieldPath': '__name__', 'order': 'ASCENDING'}]
        for index in manifest['indexes']
    )


def test_document_id_range_with_additional_ordering_field_still_requires_composite(monkeypatch):
    spec = FirestoreQuerySpec(
        identifier='synthetic_document_id_range_with_order',
        collection_group='photos',
        query_scope='COLLECTION_GROUP',
        filters=(
            FirestoreQueryFilter('__name__', '>=', 'start_key'),
            FirestoreQueryFilter('__name__', '<=', 'end_key'),
        ),
        index_fields=(_asc('created_at'), _asc('__name__')),
    )
    monkeypatch.setattr(firestore_index_registry, 'QUERY_SPECS', (spec,))

    requirements = firestore_index_registry._query_spec_index_requirements()

    assert [requirement.identifier for requirement in requirements] == [spec.identifier]
