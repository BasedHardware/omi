"""Whole-account cohort cutover utilities.

LIFECYCLE: permanent

Owns the legacy-side cutover contract: legal state transitions, authenticated
control projection, generation fencing of legacy product writes, and a
resumable forward-migration coordinator seam. The destination backend is not
implemented here; ``destination_backend_bound`` stays false until an external
binding lands in a later PR.
"""

from __future__ import annotations

from utils.account_cutover.access import (
    AccountCutoverAccessDenial,
    cutover_enforcement_enabled,
    enforce_account_cutover_http_access,
    enforce_account_cutover_ws_access,
    is_cutover_control_path,
    should_skip_background_account_mutation,
)
from utils.account_cutover.control import build_account_cutover_control
from utils.account_cutover.coordinator import (
    AccountCutoverCoordinator,
    apply_forward_checkpoint,
    begin_forward_migration,
)
from utils.account_cutover.fence import (
    AccountCutoverGenerationMismatchError,
    assert_legacy_product_write_allowed,
    background_job_should_skip_account,
    evaluate_write_fence,
    legacy_writes_allowed_for_state,
)
from utils.account_cutover.state import (
    AccountCutoverTransitionError,
    apply_cutover_transition,
    legal_transitions,
)

__all__ = [
    'AccountCutoverAccessDenial',
    'AccountCutoverCoordinator',
    'AccountCutoverGenerationMismatchError',
    'AccountCutoverTransitionError',
    'apply_cutover_transition',
    'apply_forward_checkpoint',
    'assert_legacy_product_write_allowed',
    'background_job_should_skip_account',
    'begin_forward_migration',
    'build_account_cutover_control',
    'cutover_enforcement_enabled',
    'enforce_account_cutover_http_access',
    'enforce_account_cutover_ws_access',
    'evaluate_write_fence',
    'is_cutover_control_path',
    'legal_transitions',
    'legacy_writes_allowed_for_state',
    'should_skip_background_account_mutation',
]
