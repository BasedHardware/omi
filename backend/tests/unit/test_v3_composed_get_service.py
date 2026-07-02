from __future__ import annotations

import inspect
from dataclasses import replace

import pytest

from utils.memory.v3_composed_get_service import (
    V3ComposedAdapters,
    V3ComposedCursor,
    V3ComposedDependencyDecision,
    V3ComposedExecutionContext,
    V3ComposedGrant,
    V3ComposedProjectionPage,
    V3ComposedRequest,
    V3ComposedRequestParams,
    V3ComposedResponse,
    V3ComposedRow,
    V3ComposedSnapshotDecision,
    compose_v3_get,
)


def ctx(**overrides):
    values = dict(
        subject_uid='uid-a',
        grant_epoch='grant-1',
        config_epoch='config-1',
        account_generation=7,
        projection_generation=7,
        projection_commit='commit-7',
        cursor_policy_version='policy-1',
        cursor_secret_version='secret-1',
        read_timestamp_ms=1_800_000_000_000,
        deadline_ms=1_800_000_001_000,
        filter_hash='default:noarchive',
        archive_requested=False,
        source='memory_compatibility_projection',
        read_mode='default_memory',
    )
    values.update(overrides)
    return V3ComposedExecutionContext(**values)


def row(memory_id, created_at_ms, **overrides):
    values = dict(
        memory_id=memory_id,
        created_at_ms=created_at_ms,
        subject_uid='uid-a',
        account_generation=7,
        projection_generation=7,
        projection_commit='commit-7',
        item_revision=1,
        source_version='source-1',
        source_commit='source-commit-1',
        deleted=False,
        tombstoned=False,
        visibility='long_term',
        lifecycle_status='active',
        source_freshness='stable',
        source_backed_projection=True,
        memorydb_item={'id': memory_id, 'created_at': created_at_ms},
        estimated_response_bytes=10,
    )
    values.update(overrides)
    return V3ComposedRow(**values)


class Spies:
    def __init__(self):
        self.calls = []
        self.pages = []
        self.now = 1_800_000_000_000

    def normalize(self, params):
        self.calls.append('normalize')
        return V3ComposedRequest(
            limit=params.limit, offset=params.offset, cursor=params.cursor, include_archive=params.include_archive
        )

    def dependency(self, request, budget_ms):
        self.calls.append(('dependency', budget_ms))
        return V3ComposedDependencyDecision.enrolled_ready('uid-a')

    def snapshot(self, subject_uid, request, budget_ms):
        self.calls.append(('snapshot', budget_ms))
        return V3ComposedSnapshotDecision.ready(ctx(subject_uid=subject_uid, archive_requested=request.include_archive))

    def decode_cursor(self, token, context, budget_ms):
        self.calls.append(('decode_cursor', budget_ms))
        return V3ComposedCursor(created_at_ms=900, memory_id='m9') if token else None

    def projection(self, request, context, after, limit, budget_ms):
        self.calls.append(('projection', after, limit, budget_ms))
        return self.pages.pop(0)

    def encode_cursor(self, cursor, context, budget_ms):
        self.calls.append(('encode_cursor', cursor.memory_id, budget_ms))
        return f'cursor:{cursor.memory_id}'

    def legacy(self, request, budget_ms):
        self.calls.append(('legacy', budget_ms))
        return V3ComposedResponse.success(body=[{'legacy': True}], next_cursor=None, source='legacy_primary')

    def now_ms(self):
        return self.now

    def adapters(self):
        return V3ComposedAdapters(
            normalize_request=self.normalize,
            decide_dependency=self.dependency,
            build_snapshot=self.snapshot,
            decode_cursor=self.decode_cursor,
            read_projection=self.projection,
            encode_cursor=self.encode_cursor,
            read_legacy=self.legacy,
            now_ms=self.now_ms,
        )


def page(rows, *, next_cursor=None, context=None, scanned=None, partial=False, bytes_=0):
    context = context or ctx()
    return V3ComposedProjectionPage(
        rows=tuple(rows),
        next_cursor=next_cursor,
        subject_uid=context.subject_uid,
        grant_epoch=context.grant_epoch,
        config_epoch=context.config_epoch,
        account_generation=context.account_generation,
        projection_generation=context.projection_generation,
        projection_commit=context.projection_commit,
        cursor_policy_version=context.cursor_policy_version,
        cursor_secret_version=context.cursor_secret_version,
        read_timestamp_ms=context.read_timestamp_ms,
        scanned_count=scanned if scanned is not None else len(rows),
        partial=partial,
        estimated_response_bytes=bytes_,
    )


def test_red_mutation_bomb_proves_later_stages_do_not_run_after_each_failure():
    failures = {
        'normalize': ('normalize', lambda s: setattr(s, 'normalize', lambda p: {'limit': 100})),
        'dependency': (
            'dependency',
            lambda s: setattr(s, 'dependency', lambda r, b: V3ComposedDependencyDecision.fail('bad_request', 400)),
        ),
        'snapshot': (
            'snapshot',
            lambda s: setattr(s, 'snapshot', lambda u, r, b: V3ComposedSnapshotDecision.fail('grant_denied', 403)),
        ),
        'cursor': (
            'decode_cursor',
            lambda s: setattr(s, 'decode_cursor', lambda t, c, b: (_ for _ in ()).throw(ValueError('boom'))),
        ),
        'projection': ('projection', lambda s: setattr(s, 'projection', lambda r, c, a, l, b: {'rows': []})),
    }
    for name, (stage, mutate) in failures.items():
        s = Spies()
        mutate(s)
        result = compose_v3_get(V3ComposedRequestParams(cursor='tok'), s.adapters())
        assert result.http_status >= 400, name
        call_names = [c if isinstance(c, str) else c[0] for c in s.calls]
        if stage in call_names:
            assert 'legacy' not in call_names[call_names.index(stage) + 1 :]
            assert 'projection' not in call_names[call_names.index(stage) + 1 :] or stage == 'projection'


def test_non_enrolled_calls_only_legacy_and_enrolled_never_calls_legacy():
    s = Spies()
    s.dependency = lambda request, budget_ms: (
        s.calls.append(('dependency', budget_ms)) or V3ComposedDependencyDecision.legacy('uid-a')
    )
    result = compose_v3_get(V3ComposedRequestParams(offset=25), s.adapters())
    assert result.http_status == 200 and result.body == [{'legacy': True}]
    assert [c if isinstance(c, str) else c[0] for c in s.calls] == ['normalize', 'dependency', 'legacy']

    s = Spies()
    s.pages = [page([row('m1', 1000)])]
    result = compose_v3_get(V3ComposedRequestParams(), s.adapters())
    assert result.http_status == 200
    assert 'legacy' not in [c if isinstance(c, str) else c[0] for c in s.calls]


@pytest.mark.parametrize('grant', [False, None, 'yes', V3ComposedGrant(revoked=True, epoch='grant-1')])
def test_missing_false_malformed_or_revoked_default_memory_grant_zero_reads(grant):
    s = Spies()

    def snapshot(subject_uid, request, budget_ms):
        s.calls.append(('snapshot', budget_ms))
        return V3ComposedSnapshotDecision.fail('grant_denied', 403, grant=grant)

    s.snapshot = snapshot
    result = compose_v3_get(V3ComposedRequestParams(), s.adapters())
    assert result.http_status == 403
    assert 'projection' not in [c if isinstance(c, str) else c[0] for c in s.calls]
    assert 'legacy' not in [c if isinstance(c, str) else c[0] for c in s.calls]


def test_closed_typed_adapter_outputs_fail_closed():
    cases = [
        ('dependency_dict', lambda s: setattr(s, 'dependency', lambda r, b: {'status': 'enrolled_ready'})),
        (
            'unknown_dependency_status',
            lambda s: setattr(
                s, 'dependency', lambda r, b: V3ComposedDependencyDecision(status='weird', subject_uid='uid-a')
            ),
        ),
        (
            'contradictory_dependency',
            lambda s: setattr(
                s,
                'dependency',
                lambda r, b: V3ComposedDependencyDecision(
                    status='legacy', subject_uid='uid-a', should_read_projection=True
                ),
            ),
        ),
        ('snapshot_dict', lambda s: setattr(s, 'snapshot', lambda u, r, b: {'context': ctx()})),
        (
            'projection_exception',
            lambda s: setattr(s, 'projection', lambda r, c, a, l, b: (_ for _ in ()).throw(RuntimeError('x'))),
        ),
    ]
    for _, mutate in cases:
        s = Spies()
        mutate(s)
        result = compose_v3_get(V3ComposedRequestParams(), s.adapters())
        assert result.http_status >= 500
        assert result.body is None


def test_projection_attestation_mismatch_invalidates_whole_page():
    s = Spies()
    s.pages = [page([row('m1', 1000)], context=ctx(projection_commit='other'))]
    result = compose_v3_get(V3ComposedRequestParams(), s.adapters())
    assert result.http_status == 409
    assert result.public_error == 'generation_invalidated'
    assert result.body is None


@pytest.mark.parametrize(
    'bad_row',
    [
        row('m1', 1000, subject_uid='attacker'),
        row('m1', 1000, account_generation=8),
        row('m1', 1000, projection_generation=8),
        row('m1', 1000, projection_commit='old'),
        row('m1', 1000, item_revision=0),
        row('m1', 1000, source_version=''),
        row('m1', 1000, source_commit=''),
    ],
)
def test_row_level_fence_mismatch_fails_whole_page_not_drop(bad_row):
    s = Spies()
    s.pages = [page([bad_row, row('m2', 900)])]
    result = compose_v3_get(V3ComposedRequestParams(), s.adapters())
    assert result.http_status == 409
    assert result.body is None


def test_filtering_advances_cursor_by_last_scanned_with_bounded_refill_no_duplicates_or_omissions():
    s = Spies()
    s.pages = [
        page(
            [
                row(
                    'a', 1000, visibility='archived_evidence', lifecycle_status='active', source_freshness='historical'
                ),
                row('b', 1000, deleted=True),
                row('c', 999, visibility='short_term', lifecycle_status='working', source_freshness='stale'),
                row('d', 998),
            ],
            next_cursor=V3ComposedCursor(998, 'd'),
            scanned=4,
        ),
        page([row('e', 998), row('f', 997)], next_cursor=V3ComposedCursor(997, 'f'), scanned=2),
    ]
    result = compose_v3_get(V3ComposedRequestParams(limit=2), s.adapters())
    assert result.http_status == 200
    assert [item['id'] for item in result.body] == ['d', 'e']
    assert result.next_cursor == 'cursor:f'
    assert [c[0] for c in s.calls if isinstance(c, tuple) and c[0] == 'projection'] == ['projection', 'projection']

    # Generation change between pages is a page failure, not duplicate-prone continuation.
    s = Spies()
    s.pages = [
        page([row('d', 998)], next_cursor=V3ComposedCursor(998, 'd')),
        page([row('e', 997)], context=ctx(account_generation=8)),
    ]
    result = compose_v3_get(V3ComposedRequestParams(limit=2), s.adapters())
    assert result.http_status == 409


def test_deadline_propagation_and_timeout_never_returns_200_empty():
    s = Spies()
    s.now = 1_800_000_001_001
    result = compose_v3_get(V3ComposedRequestParams(deadline_ms=1_800_000_001_000), s.adapters())
    assert result.http_status == 504 and result.body is None

    s = Spies()
    s.pages = [page([], partial=True)]
    result = compose_v3_get(V3ComposedRequestParams(), s.adapters())
    assert result.http_status == 503 and result.body is None


def test_public_error_taxonomy_and_200_empty_only_verified_empty():
    s = Spies()
    s.dependency = lambda r, b: (
        s.calls.append(('dependency', b)) or V3ComposedDependencyDecision.fail('bad_request', 400)
    )
    assert compose_v3_get(V3ComposedRequestParams(limit=0), s.adapters()).public_error == 'request_invalid'

    s = Spies()
    s.snapshot = lambda u, r, b: (
        s.calls.append(('snapshot', b)) or V3ComposedSnapshotDecision.fail('infrastructure_failure', 503)
    )
    assert compose_v3_get(V3ComposedRequestParams(), s.adapters()).public_error == 'infrastructure_failure'

    s = Spies()
    s.pages = [page([])]
    result = compose_v3_get(V3ComposedRequestParams(), s.adapters())
    assert result.http_status == 200 and result.body == []

    s = Spies()
    s.pages = [page([row('x', 1, deleted=True)])]
    result = compose_v3_get(V3ComposedRequestParams(), s.adapters())
    assert result.http_status == 200 and result.body == []
    assert result.verified_empty is False


def test_bounded_scan_read_counts_response_cap_and_offset_semantics():
    s = Spies()
    s.pages = [
        page(
            [row(str(i), 1000 - i, deleted=True) for i in range(50)],
            next_cursor=V3ComposedCursor(951, '49'),
            scanned=50,
        )
        for _ in range(20)
    ]
    result = compose_v3_get(V3ComposedRequestParams(limit=500, max_projection_reads=3, scan_budget=60), s.adapters())
    assert result.http_status == 200
    assert len([c for c in s.calls if isinstance(c, tuple) and c[0] == 'projection']) <= 3

    s = Spies()
    s.pages = [page([row('big', 1, estimated_response_bytes=2_000_000)])]
    result = compose_v3_get(V3ComposedRequestParams(response_byte_cap=100), s.adapters())
    assert result.http_status == 413

    s = Spies()
    result = compose_v3_get(V3ComposedRequestParams(offset=1), s.adapters())
    assert result.http_status == 400 and result.public_error == 'offset_invalid'


def test_static_import_checks_prohibit_fastapi_router_production_clients_and_telemetry():
    source = inspect.getsource(__import__('utils.memory.v3_composed_get_service', fromlist=['']))
    for forbidden in [
        'fastapi',
        'routers.memories',
        'firebase',
        'firestore',
        'requests.',
        'httpx.',
        'openai',
        'pinecone',
        'telemetry',
    ]:
        assert forbidden not in source.lower()
