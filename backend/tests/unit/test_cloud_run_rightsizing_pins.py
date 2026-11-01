"""Contract pins for the 2026-10-24 prod Cloud Run right-sizing (the lead's costcut).

The T4 deploy (image 646e54d7, run 40138604325) re-asserted backend-sync at
4Gi / max 80: #23495 had mirrored the 05:54Z right-sizing, not the evening
costcut. These pins hold every deploy source -- the workflow fallback, the
deploy-action flags, the ops-train values and the staging shape -- to the
costcut values, so the next train can no longer silently revert them.

Live reference (ro-prod, 2026-10-24 22:50Z): backend 8Gi/cpu 2/concurrency 20/
min 3/max 100; backend-sync 6Gi/cpu 2/min 5/max 50; backend-sync-backfill
4Gi/cpu 2/concurrency 6/min 0 (cap redis_guard-bounded, live 16);
backend-integration 2Gi/cpu 2/concurrency 40/min 3/max 50.
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


def test_prod_deploy_flags_match_the_live_right_sizing():
    model = dc.source_model('prod')

    backend = model['backend'].scale
    assert (backend['memory'], backend['cpu'], backend['concurrency']) == ('8Gi', '2', 20)
    assert (backend['revision_min'], backend['revision_max']) == (3, 100)

    sync = model['backend-sync'].scale
    assert (sync['memory'], sync['cpu']) == ('6Gi', '2')
    # max-instances is live-resolved by design (Resolve live sync maxScale); the cap
    # itself is pinned in the ops file. The deploy never touches sync min.
    assert sync['revision_min'] is None and sync['revision_max'] is None

    backfill = model['backend-sync-backfill'].scale
    assert (backfill['memory'], backfill['cpu'], backfill['concurrency'], backfill['revision_min']) == (
        '4Gi',
        '2',
        6,
        0,
    )

    integration = model['backend-integration'].scale
    assert (integration['memory'], integration['cpu'], integration['concurrency']) == ('2Gi', '2', 40)
    assert (integration['revision_min'], integration['revision_max']) == (3, 50)


def test_ops_train_values_match_the_live_right_sizing():
    model = dc.source_model('prod')

    sync = model['backend-sync'].ops_scale
    assert (sync['service_min'], sync['service_max']) == (5, 50)

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
