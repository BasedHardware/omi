"""Contract pins for the margin-20 prod Cloud Run targets (2026-11-04).

Read-only serving revisions before this change: backend 8Gi/cpu 2/concurrency 20;
backend-sync 6Gi/cpu 2/concurrency 20; backfill 3Gi/cpu 2/concurrency 6;
integration 4Gi/cpu 2/concurrency 80. Seven-day application-memory histogram
p95/max upper bounds (GiB): backend 1.312/1.710, sync 1.007/3.786,
backfill 0.882/1.149, integration 1.312/2.229. Sync and integration stay put.

The deploy flags and staging shape must agree on backend 4Gi and backfill
2Gi/concurrency 6 (concurrency 10 unqualified, Luna P2 on #24596). Rollback restores 8Gi and 3Gi;
service min/max ownership remains with the existing ops/Redis guard contract.
"""

from __future__ import annotations

import re
from pathlib import Path

from scripts.ops import drift_check as dc

RIGHTSIZED_SERVICES = ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')
REPO_ROOT = Path(__file__).resolve().parents[3]


def test_workflow_backend_sync_memory_fallback_is_the_costcut_value():
    # vars.BACKEND_SYNC_MEMORY is unset in both GitHub environments, so the fallback
    # literal is what a prod deploy passes. Pinned as text because the drift model
    # only sees the expression through _WORKFLOW_ENV_SCOPED: an edit that breaks the
    # expression shape would otherwise pass silently with stale model values.
    text = (REPO_ROOT / '.github' / 'workflows' / 'gcp_backend.yml').read_text(encoding='utf-8')
    assert re.search(
        r"backend_sync_memory: \$\{\{ vars\.BACKEND_SYNC_MEMORY \|\| "
        r"\(github\.event\.inputs\.environment == 'prod' && '6Gi' \|\| '8Gi'\) \}\}",
        text,
    )


def test_deploy_action_accepts_the_5gi_sync_trial_value():
    # 5Gi is a trial value (vars.BACKEND_SYNC_MEMORY), not the fallback: the 10-25 fleet peak was
    # 4.74 GiB and the runbook's 4.9 GiB sample predates it, so 6Gi stays until a trial qualifies 5Gi.
    text = (REPO_ROOT / '.github' / 'actions' / 'deploy-backend-stack' / 'action.yml').read_text(encoding='utf-8')
    assert 'case "$SYNC_MEMORY" in 4Gi|5Gi|6Gi|8Gi) ;;' in text


def test_prod_deploy_flags_match_the_margin20_target():
    model = dc.source_model('prod')

    backend = model['backend'].scale
    assert (backend['memory'], backend['cpu'], backend['concurrency']) == ('4Gi', '2', 20)
    assert (backend['revision_min'], backend['revision_max']) == (3, 100)

    sync = model['backend-sync'].scale
    assert (sync['memory'], sync['cpu']) == ('6Gi', '2')
    # max-instances is live-resolved by design (Resolve live sync maxScale); the cap
    # itself is pinned in the ops file. The deploy never touches sync min.
    assert sync['revision_min'] is None and sync['revision_max'] is None

    backfill = model['backend-sync-backfill'].scale
    assert (backfill['memory'], backfill['cpu'], backfill['concurrency'], backfill['revision_min']) == (
        '2Gi',
        '2',
        6,
        0,
    )

    integration = model['backend-integration'].scale
    # 2026-11-01 packing (#24308): LLM-bound enrichment runs 80 per instance with 64 postprocess threads.
    assert (integration['memory'], integration['cpu'], integration['concurrency']) == ('4Gi', '2', 80)
    assert (integration['revision_min'], integration['revision_max']) == (3, 35)


def test_ops_train_values_match_the_live_right_sizing():
    model = dc.source_model('prod')

    sync = model['backend-sync'].ops_scale
    # Legacy-dark (2026-11-04, David e53a35) dropped the warm floor 5 -> 0.
    assert (sync['service_min'], sync['service_max']) == (0, 40)

    # redis_guard owns the backfill cap between its bounds (live 16).
    backfill = model['backend-sync-backfill'].ops_scale
    assert backfill['service_min'] is None
    assert backfill['service_max']['owner'] == 'redis_guard'
    assert backfill['service_max']['floor'] <= 16 <= backfill['service_max']['ceiling']

    # Equal to the deploy flag (prod && 3): the ops file must never fight the deploy.
    integration = model['backend-integration'].ops_scale
    assert (integration['service_min'], integration['service_max']) == (3, None)

    backend = model['backend'].ops_scale
    assert (backend['service_min'], backend['service_max']) == (None, None)


def test_staging_shape_keeps_parity_with_prod():
    prod = dc.source_model('prod')
    staging = dc.source_model('staging')
    for name in RIGHTSIZED_SERVICES:
        findings = dc._scale_vs_prod(name, staging[name].scale, prod[name].scale)
        assert not findings, f'{name}: {[f.line() for f in findings]}'
