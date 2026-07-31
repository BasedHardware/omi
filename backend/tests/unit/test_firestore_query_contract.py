import ast
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import SimpleNamespace

import pytest
from google.cloud.firestore_v1 import FieldFilter

import database.action_items as action_items_db
import database.task_recommendations as task_recommendations_db
import routers.task_recommendations as task_recommendations_router
from database.firestore_index_registry import (
    ACTIVE_ATTENTION_OVERRIDE_QUERY,
    CANONICAL_CONSOLIDATION_QUERY,
    CONVERSATION_SOURCE_MEMORY_QUERY,
    DUE_MEMORY_OUTBOX_QUERY,
    EXPIRED_SHORT_TERM_LIFECYCLE_QUERY,
    EXPIRED_MEMORY_OUTBOX_LEASE_QUERY,
    INDEX_ONLY_REQUIREMENTS,
    REVIEW_QUEUE_BY_CONFLICT_QUERY,
    REVIEW_QUEUE_BY_FACT_QUERY,
    REVIEW_QUEUE_BY_STATUS_QUERY,
    REVIEW_QUEUE_BY_STATUS_ID_QUERY,
    REVIEW_QUEUE_ORDERED_QUERY,
    REQUIRED_MEMORY_PROCESSING_QUERY,
    SUPERSEDED_MEMORY_BY_CANONICAL_TARGET_QUERY,
    SUPERSEDED_MEMORY_BY_LEGACY_TARGET_QUERY,
    STALE_IN_PROGRESS_CONVERSATIONS_QUERY,
    firebase_index_manifest,
)
from scripts import firestore_query_coverage, generate_firestore_indexes
from tests.store_fakes import FakeDocumentStore


class _RecordingQuery:
    def __init__(self):
        self.filters = []

    def where(self, *, filter):
        self.filters.append((filter.field_path, filter.op_string, filter.value))
        return self


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
    store = FakeDocumentStore()
    for index, row in enumerate(
        [
            {'dedupe_key': 'active', 'account_generation': 3, 'expires_at': now + timedelta(minutes=1)},
            {'dedupe_key': 'expired', 'account_generation': 3, 'expires_at': now - timedelta(minutes=1)},
            {'dedupe_key': 'prior-generation', 'account_generation': 2, 'expires_at': now + timedelta(minutes=1)},
        ]
    ):
        store.set(f'users/smoke-user/{task_recommendations_db.ATTENTION_OVERRIDES_COLLECTION}/o{index}', row)
    monkeypatch.setattr(task_recommendations_db, '_store', lambda: store)
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
        ACTIVE_ATTENTION_OVERRIDE_QUERY,
        STALE_IN_PROGRESS_CONVERSATIONS_QUERY,
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


def test_query_coverage_ratchet_rejects_a_new_raw_serving_shape():
    baseline = {
        'schema_version': 1,
        'eligible_serving': 1,
        'registered_serving': 1,
        'raw_unregistered': [],
        'unsupported': [],
    }
    report = {
        'counts': {
            'serving': {
                'eligible': 2,
                'registered': 1,
                'raw_unregistered': 1,
                'waived': 0,
                'unsupported': 0,
            }
        },
        'queries': [
            {'id': 'registered', 'classification': 'registered'},
            {'id': 'new-raw', 'classification': 'raw_unregistered'},
        ],
    }

    assert firestore_query_coverage.check_ratchet(report, baseline) == [
        'new unregistered serving compound query shape(s): new-raw',
        'registered serving-query coverage percentage decreased',
    ]


@pytest.mark.slow
def test_query_coverage_baseline_tracks_current_raw_and_unsupported_debt():
    baseline_path = Path(__file__).resolve().parents[2] / 'scripts' / 'firestore_query_coverage_baseline.json'
    committed = json.loads(baseline_path.read_text(encoding='utf-8'))
    report = firestore_query_coverage.report_for(firestore_query_coverage.inventory(waiver_ids=set()))

    assert firestore_query_coverage.check_ratchet(report, committed) == []


# Firestore's asc/desc query directions map onto the ASCENDING/DESCENDING order strings the
# committed composite-index manifest declares per field.
_DIRECTION_TO_INDEX_ORDER = {'asc': 'ASCENDING', 'desc': 'DESCENDING'}


class _QueryShapeRecordingStore:
    """A document store that records the filter + ordering shape of every ``query()``.

    The persistence port carries the whole query shape as data — ``filters`` triples plus an
    ``order_by``/``direction`` pair — so we intercept it at the store seam rather than a raw
    Firestore client handle (removed in ADR-0028) and normalize it into the (filters, orders)
    form the index-signature contract asserts against.
    """

    def __init__(self, recorder):
        self._recorder = recorder

    def query(self, collection, *, filters=None, order_by=None, direction='asc', limit=None, **_kwargs):
        recorded_filters = tuple((field_path, op) for field_path, op, _value in (filters or ()))
        if order_by is None:
            orders = ()
        elif isinstance(order_by, str):
            orders = ((order_by, _DIRECTION_TO_INDEX_ORDER[direction]),)
        else:
            orders = tuple((field_path, _DIRECTION_TO_INDEX_ORDER[fdir]) for field_path, fdir in order_by)
        self._recorder.append((recorded_filters, orders))
        return []


def _required_index_signature(collection_group, filters, orders):
    """The composite index Firestore requires for one equality-plus-ordering chain."""
    fields = [(field_path, 'ASCENDING') for field_path, operator in filters if operator == '==']
    fields.extend(orders)
    fields.append(('__name__', orders[-1][1]))
    return (collection_group, 'COLLECTION', tuple(fields))


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
    monkeypatch.setattr(action_items_db, '_store', lambda: _QueryShapeRecordingStore(recorder))

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
        assert _required_index_signature('action_items', filters, orders) in declared


def test_query_source_paths_are_posix_canonical_on_every_host_platform():
    windows_path = PureWindowsPath('backend\\database\\conversations.py')
    posix_path = PurePosixPath('backend/database/conversations.py')

    assert firestore_query_coverage.canonical_source_path(windows_path) == 'backend/database/conversations.py'
    assert firestore_query_coverage.canonical_source_path(
        windows_path
    ) == firestore_query_coverage.canonical_source_path(posix_path)
