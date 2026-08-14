import inspect

from utils.memory.v3.write_convergence import (
    V3ExternalWriteOperation,
    V3WriteConvergenceContext,
    V3WriteConvergenceDecision,
    V3WriteConvergenceStatus,
    decide_v3_write_convergence,
)


def _ready_context(**overrides):
    values = {
        'uid': 'uid-a',
        'enrolled': True,
        'operation': V3ExternalWriteOperation.CREATE,
        'write_surface_active': True,
        'reads_blocked_for_cohort': False,
        'memory_authoritative_write_path_available': True,
        'status': V3WriteConvergenceStatus.CONVERGED,
        'expected_account_generation': 7,
        'observed_account_generation': 7,
        'durable_outbox_fence': True,
        'independent_dual_write': False,
        'swallowed_failure': False,
        'projection_update_committed': True,
        'projection_commit_id': 'projection-commit-7',
        'projection_generation': 7,
        'tombstone_committed': False,
        'projection_removal_committed': False,
        'vector_cleanup_outbox_fence': False,
    }
    values.update(overrides)
    return V3WriteConvergenceContext(**values)


def test_create_and_update_require_memory_authoritative_path_projection_commit_and_current_generation_before_read_cutover():
    for operation in [V3ExternalWriteOperation.CREATE, V3ExternalWriteOperation.UPDATE]:
        decision = decide_v3_write_convergence(_ready_context(operation=operation))

        assert decision.status == V3WriteConvergenceStatus.CONVERGED
        assert decision.write_success_allowed is True
        assert decision.read_cutover_allowed is True
        assert decision.http_status == 200
        assert decision.reason == f'{operation.value}_write_converged'
        assert decision.legacy_direct_write_fallback_allowed is False
        assert decision.archive_default_available is False
        assert decision.stale_short_term_default_visible is False
        assert decision.headers == {
            'X-Omi-Memory-Write-Convergence': 'converged',
            'X-Omi-Memory-Write-Operation': operation.value,
            'X-Omi-Memory-Write-Decision': f'{operation.value}_write_converged',
        }


def test_delete_requires_tombstone_projection_removal_and_vector_cleanup_outbox_fence_before_success_or_read_cutover():
    decision = decide_v3_write_convergence(
        _ready_context(
            operation=V3ExternalWriteOperation.DELETE,
            tombstone_committed=True,
            projection_removal_committed=True,
            vector_cleanup_outbox_fence=True,
        )
    )

    assert decision.status == V3WriteConvergenceStatus.CONVERGED
    assert decision.write_success_allowed is True
    assert decision.read_cutover_allowed is True
    assert decision.reason == 'delete_write_converged'
    assert decision.legacy_direct_write_fallback_allowed is False

    delete_blockers = [
        ({'tombstone_committed': False}, 'delete_tombstone_missing'),
        ({'projection_removal_committed': False}, 'delete_projection_removal_missing'),
        ({'vector_cleanup_outbox_fence': False}, 'delete_vector_cleanup_outbox_fence_missing'),
    ]
    for overrides, reason in delete_blockers:
        base = {
            'operation': V3ExternalWriteOperation.DELETE,
            'tombstone_committed': True,
            'projection_removal_committed': True,
            'vector_cleanup_outbox_fence': True,
        }
        base.update(overrides)
        result = decide_v3_write_convergence(_ready_context(**base))

        assert result.status == V3WriteConvergenceStatus.BLOCKED
        assert result.write_success_allowed is False
        assert result.read_cutover_allowed is False
        assert result.reason == reason
        assert result.legacy_direct_write_fallback_allowed is False


def test_missing_stale_partial_swallowed_dual_write_without_durable_outbox_generation_mismatch_and_missing_projection_commit_fail_closed():
    cases = [
        ({'status': None}, 'write_convergence_status_missing'),
        ({'status': V3WriteConvergenceStatus.MISSING}, 'write_convergence_missing'),
        ({'status': V3WriteConvergenceStatus.STALE}, 'write_convergence_stale'),
        ({'status': V3WriteConvergenceStatus.PARTIAL}, 'write_convergence_partial'),
        ({'status': V3WriteConvergenceStatus.SWALLOWED_FAILURE}, 'write_failure_swallowed'),
        ({'swallowed_failure': True}, 'write_failure_swallowed'),
        (
            {'status': V3WriteConvergenceStatus.INDEPENDENT_DUAL_WRITE_WITHOUT_DURABLE_OUTBOX},
            'durable_outbox_fence_missing',
        ),
        ({'independent_dual_write': True, 'durable_outbox_fence': False}, 'durable_outbox_fence_missing'),
        ({'durable_outbox_fence': False}, 'durable_outbox_fence_missing'),
        ({'observed_account_generation': None}, 'observed_account_generation_missing'),
        ({'observed_account_generation': 6}, 'account_generation_mismatch'),
        ({'projection_update_committed': False}, 'projection_update_commit_missing'),
        ({'projection_commit_id': None}, 'projection_commit_id_missing'),
        ({'projection_generation': None}, 'projection_generation_missing'),
        ({'projection_generation': 6}, 'projection_generation_stale'),
        ({'memory_authoritative_write_path_available': False}, 'memory_authoritative_write_path_unavailable'),
    ]

    for overrides, reason in cases:
        decision = decide_v3_write_convergence(_ready_context(**overrides))

        assert decision.status == V3WriteConvergenceStatus.BLOCKED
        assert decision.write_success_allowed is False
        assert decision.read_cutover_allowed is False
        assert decision.http_status == 503
        assert decision.reason == reason
        assert decision.legacy_direct_write_fallback_allowed is False


def test_external_writes_disabled_is_safe_only_when_reads_remain_blocked_or_no_surfaces_are_active():
    blocked_reads = decide_v3_write_convergence(
        _ready_context(status=V3WriteConvergenceStatus.DISABLED, reads_blocked_for_cohort=True)
    )
    assert blocked_reads.status == V3WriteConvergenceStatus.DISABLED
    assert blocked_reads.write_success_allowed is False
    assert blocked_reads.read_cutover_allowed is False
    assert blocked_reads.safe_pilot_policy_allowed is True
    assert blocked_reads.reason == 'external_writes_disabled_reads_blocked_safe_pilot'

    no_surface = decide_v3_write_convergence(
        _ready_context(
            status=V3WriteConvergenceStatus.DISABLED,
            write_surface_active=False,
            reads_blocked_for_cohort=False,
        )
    )
    assert no_surface.safe_pilot_policy_allowed is True
    assert no_surface.reason == 'external_writes_disabled_no_active_write_surface_safe_pilot'

    unsafe = decide_v3_write_convergence(
        _ready_context(status=V3WriteConvergenceStatus.DISABLED, reads_blocked_for_cohort=False)
    )
    assert unsafe.status == V3WriteConvergenceStatus.BLOCKED
    assert unsafe.write_success_allowed is False
    assert unsafe.read_cutover_allowed is False
    assert unsafe.safe_pilot_policy_allowed is False
    assert unsafe.reason == 'external_writes_disabled_but_reads_not_blocked'


def test_non_enrolled_legacy_primary_plan_only_and_no_enrolled_legacy_direct_write_fallback_knob():
    non_enrolled = decide_v3_write_convergence(
        _ready_context(
            enrolled=False, status=V3WriteConvergenceStatus.MISSING, memory_authoritative_write_path_available=False
        )
    )
    assert non_enrolled.http_status == 200
    assert non_enrolled.reason == 'non_enrolled_legacy_primary_write_plan_only'
    assert non_enrolled.write_success_allowed is False
    assert non_enrolled.read_cutover_allowed is False
    assert non_enrolled.legacy_direct_write_fallback_allowed is False

    decision_fields = set(V3WriteConvergenceDecision.__dataclass_fields__)
    context_fields = set(V3WriteConvergenceContext.__dataclass_fields__)
    forbidden_fields = {
        'fallback_to_legacy',
        'use_legacy_on_error',
        'legacy_direct_write_fallback',
        'allow_legacy_direct_write_for_memory',
        'include_archive_by_default',
        'show_stale_short_term_by_default',
    }
    assert forbidden_fields.isdisjoint(decision_fields)
    assert forbidden_fields.isdisjoint(context_fields)

    source = inspect.getsource(__import__('utils.memory.v3.write_convergence', fromlist=['']))
    forbidden_tokens = [
        'routers.memories',
        'database.',
        'firebase',
        'firestore',
        'pinecone',
        'requests.',
        'httpx.',
        'openai',
        'legacy_direct_write_fallback_allowed=True',
        'archive_default_available=True',
        'stale_short_term_default_visible=True',
    ]
    for token in forbidden_tokens:
        assert token not in source
