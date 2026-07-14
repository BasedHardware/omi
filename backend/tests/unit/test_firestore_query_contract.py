import ast
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import SimpleNamespace

import pytest
from google.cloud.firestore_v1 import FieldFilter

import database.task_recommendations as task_recommendations_db
import routers.task_recommendations as task_recommendations_router
from database.firestore_index_registry import ACTIVE_ATTENTION_OVERRIDE_QUERY, firebase_index_manifest
from scripts import firestore_query_coverage, generate_firestore_indexes


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

    assert manifest_path.read_text(encoding='utf-8') == generate_firestore_indexes.render_manifest()
    assert firebase_index_manifest()['indexes'][-1] == {
        'collectionGroup': 'task_attention_overrides',
        'queryScope': 'COLLECTION',
        'fields': [
            {'fieldPath': 'account_generation', 'order': 'ASCENDING'},
            {'fieldPath': 'expires_at', 'order': 'ASCENDING'},
            {'fieldPath': '__name__', 'order': 'ASCENDING'},
        ],
    }


@pytest.mark.slow
def test_query_inventory_registers_the_migrated_attention_override_shape():
    report = firestore_query_coverage.report_for(firestore_query_coverage.inventory(waiver_ids=set()))

    matching = [
        query for query in report['queries'] if query['registered_spec'] == ACTIVE_ATTENTION_OVERRIDE_QUERY.identifier
    ]
    assert len(matching) == 1
    assert matching[0]['classification'] == 'registered'
    assert matching[0]['collection_group'] == 'task_attention_overrides'
    assert report['counts']['serving']['registered'] >= 1


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


def test_query_source_paths_are_posix_canonical_on_every_host_platform():
    windows_path = PureWindowsPath('backend\\database\\conversations.py')
    posix_path = PurePosixPath('backend/database/conversations.py')

    assert firestore_query_coverage.canonical_source_path(windows_path) == 'backend/database/conversations.py'
    assert firestore_query_coverage.canonical_source_path(
        windows_path
    ) == firestore_query_coverage.canonical_source_path(posix_path)
