"""Cross-service deploy contract (scripts/cross_service_contract.py).

The checked-in dev and prod manifests and charts must introduce no violation beyond the accepted known gaps.
Each mutation re-creates one 2026-10-18 rollout bug on a copy of the current manifest or chart, and the
suite must catch it:

- #22098: Cloud Run-shaped gke.config_map entry without ``source`` (deploy ConfigMap render failed)
- #22149: recovery task dispatched to an empty audience / to a host with recovery off / below the deadline
- #22121: head-priority flag on for the listener but never set on the GPU worker that also reads it

Rendering and code scanning run once in the module fixture; tests only assert on the results.
Replaying the real pre-fix commits needs git history, so it is opt-in: ``CROSS_SERVICE_CONTRACT_REPLAY=1``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pytest
import yaml

from scripts import cross_service_contract as contract

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKER_VALUES = 'backend/charts/batch-pipeline-worker/prod_omi_batch-pipeline-worker_values.yaml'
HAS_HELM = shutil.which('helm') is not None
SYNTHETIC_UID = 'SyntheticCohortMember0000000'
assert len(SYNTHETIC_UID) == 28


class OverlaySource(contract.Source):
    """The working tree with selected files replaced, so a mutation reuses the real code readers."""

    def __init__(self, tmp_path: Path, overrides: dict[str, str]):
        super().__init__()
        self.overrides = overrides
        self.tmp_path = tmp_path

    def read(self, rel: str) -> str:
        return self.overrides[rel] if rel in self.overrides else super().read(rel)

    def exists(self, rel: str) -> bool:
        return rel in self.overrides or super().exists(rel)

    def directory(self, rel: str) -> Path:
        if not any(path.startswith(rel + '/') for path in self.overrides):
            return super().directory(rel)
        target = self.tmp_path / rel
        if not target.exists():
            shutil.copytree(super().directory(rel), target)
            for path, text in self.overrides.items():
                if path.startswith(rel + '/'):
                    (self.tmp_path / path).write_text(text, encoding='utf-8')
        return target


def _manifest() -> dict:
    return yaml.safe_load((REPO_ROOT / contract.MANIFEST).read_text(encoding='utf-8'))


def _prod(manifest: dict) -> dict:
    return manifest['environments']['prod']


def _integration_env(manifest: dict) -> dict:
    return _prod(manifest)['cloud_run']['services']['backend-integration']['env']


def _manifest_mutation(mutate: Callable[[dict], None]) -> Callable[[], dict[str, str]]:
    def overrides() -> dict[str, str]:
        manifest = _manifest()
        mutate(manifest)
        return {contract.MANIFEST: yaml.safe_dump(manifest, sort_keys=False)}

    return overrides


def _config_map_without_source(manifest: dict) -> None:
    entries = _prod(manifest)['gke']['config_map']['entries']
    entries['SYNTHETIC_FLAG_ENABLED'] = {'value': 'false', 'category': 'rollout'}


def _recovery_without_audience(manifest: dict) -> None:
    del _integration_env(manifest)['BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE']


def _recovery_to_sync(manifest: dict) -> None:
    sync_env = _prod(manifest)['cloud_run']['services']['backend-sync']['env']
    _integration_env(manifest)['BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE']['value'] = sync_env[
        'BATCH_PIPELINE_WORKER_AUDIENCE'
    ]['value']


def _integration_timeout_300(manifest: dict) -> None:
    _prod(manifest)['cloud_run']['services']['backend-integration']['flags']['--timeout'] = '300s'


def _unparseable_boolean(manifest: dict) -> None:
    _integration_env(manifest)['BATCH_PIPELINE_SERVING_ENABLED']['value'] = 'enabled'


def _unparseable_named_set_boolean(manifest: dict) -> None:
    # LIVE_CAPTURE_WINDOW_RETENTION is compared against a named module-level frozenset (_TRUTHY), not a
    # literal tuple; a scanner that skips named sets never sees its tokens.
    for services in (_prod(manifest)['cloud_run']['services'],):
        for svc in services.values():
            if 'LIVE_CAPTURE_WINDOW_RETENTION' in svc.get('env', {}):
                svc['env']['LIVE_CAPTURE_WINDOW_RETENTION']['value'] = 'enabled'


def _sync_handler_wrong_route(manifest: dict) -> None:
    # Route check on a full-URL edge: the sync edge is inert while SYNC_DISPATCH_MODE is live-only
    # inline, so use the prod-active account-deletion edge with a literal URL on the wrong path.
    env = _prod(manifest)['cloud_run']['services']['backend-sync']['env']
    env['ACCOUNT_DELETION_HANDLER_URL'] = {
        'value': 'https://backend-sync-hhibjajaja-uc.a.run.app/v1/users/wrong-route/run',
        'category': 'reliability',
    }


def _recovery_audience_with_path(manifest: dict) -> None:
    _integration_env(manifest)['BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE'][
        'value'
    ] += '/v2/batch-pipeline/recover-quarantine'


def _backfill_audience_mismatch(manifest: dict) -> None:
    # Dispatcher mints one audience while the target verifies another: enable the live-only sync dispatch
    # on backend (its handler URL targets backend-sync) and point the dispatcher's minted audience at the
    # integration host. The target still verifies the backend-sync URL; every task would be rejected 403.
    env = _prod(manifest)['cloud_run']['services']['backend']['env']
    env['SYNC_DISPATCH_MODE'] = {'value': 'cloud_tasks', 'category': 'reliability'}
    env['SYNC_TASKS_OIDC_AUDIENCE']['default'] = 'https://backend-integration-hhibjajaja-uc.a.run.app/v2/sync-jobs/run'


def _typoed_sync_host(manifest: dict) -> None:
    env = _prod(manifest)['cloud_run']['services']['backend-sync']['env']
    env['SYNC_TASKS_HANDLER_URL']['default'] = 'https://backend-sync-hhibjajaja-ud.a.run.app/v2/sync-jobs/run'


def _uid_literal(manifest: dict) -> None:
    _integration_env(manifest)['SYNTHETIC_UID_ALLOWLIST'] = {'value': SYNTHETIC_UID, 'category': 'rollout'}


def _uid_allowlist_appended(manifest: dict) -> None:
    # Appending to an existing accepted cohort: same env key, one more UID-shaped literal. The prod
    # backend-listen STT cohort is accepted at uids=1 in the ratchet; appending must not stay "known".
    listen = _prod(manifest)['gke']['backend-listen']['env']['STT_LIVE_DEMAND_UID_ALLOWLIST']
    listen['value'] = f"{listen['value']},{SYNTHETIC_UID}"


def _prod_url_in_dev(manifest: dict) -> None:
    prod_url = _integration_env(manifest)['BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE']['value']
    dev = manifest['environments']['dev']['cloud_run']['services']['backend-integration']['env']
    dev['BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE']['value'] = prod_url


def _worker_without_head_priority() -> dict[str, str]:
    values = yaml.safe_load((REPO_ROOT / WORKER_VALUES).read_text(encoding='utf-8'))
    assert values['worker'].pop('headPriorityEnabled') is True
    return {WORKER_VALUES: yaml.safe_dump(values, sort_keys=False)}


MUTATIONS: dict[str, Callable[[], dict[str, str]]] = {
    'config_map_without_source': _manifest_mutation(_config_map_without_source),
    'recovery_without_audience': _manifest_mutation(_recovery_without_audience),
    'recovery_to_sync': _manifest_mutation(_recovery_to_sync),
    'integration_timeout_300': _manifest_mutation(_integration_timeout_300),
    'unparseable_boolean': _manifest_mutation(_unparseable_boolean),
    'unparseable_named_set_boolean': _manifest_mutation(_unparseable_named_set_boolean),
    'sync_handler_wrong_route': _manifest_mutation(_sync_handler_wrong_route),
    'recovery_audience_with_path': _manifest_mutation(_recovery_audience_with_path),
    'backfill_audience_mismatch': _manifest_mutation(_backfill_audience_mismatch),
    'typoed_sync_host': _manifest_mutation(_typoed_sync_host),
    'uid_literal': _manifest_mutation(_uid_literal),
    'uid_allowlist_appended': _manifest_mutation(_uid_allowlist_appended),
    'prod_url_in_dev': _manifest_mutation(_prod_url_in_dev),
    'worker_without_head_priority': _worker_without_head_priority,
}
HELM_MUTATIONS = {'worker_without_head_priority'}


@dataclass
class Results:
    baseline: contract.Context
    baseline_new: list[contract.Violation]
    mutations: dict[str, list[contract.Violation]]


@pytest.fixture(scope='module')
def results(tmp_path_factory: pytest.TempPathFactory) -> Results:
    gaps = contract.load_known_gaps()
    baseline = contract.build_context(contract.Source())
    baseline_new, _, _ = contract.partition(contract.evaluate(baseline), gaps)
    mutations: dict[str, list[contract.Violation]] = {}
    for name, overrides in MUTATIONS.items():
        if name in HELM_MUTATIONS and not HAS_HELM:
            continue
        source = OverlaySource(tmp_path_factory.mktemp(name), overrides())
        context = contract.build_context(source, readers=baseline.readers)
        mutations[name], _, _ = contract.partition(contract.evaluate(context), gaps)
    return Results(baseline=baseline, baseline_new=baseline_new, mutations=mutations)


def test_current_manifests_add_no_violation_beyond_known_gaps(results: Results) -> None:
    assert not results.baseline_new, (
        'new cross-service violations:\n'
        + '\n'.join(map(str, results.baseline_new))
        + (
            '\n\nFix the wiring, or (only for an intentional, reviewed exception) add the key with a `why` to '
            'backend/deploy/cross_service_known_gaps.json.'
        )
    )


def test_known_gaps_carry_reasons_and_no_values() -> None:
    gaps = contract.load_known_gaps()
    assert gaps, 'baseline is unexpectedly empty'
    for key, why in gaps.items():
        assert why.strip(), key
        assert not contract.FIREBASE_UID_PATTERN.search(key), 'known gaps must name keys, never identifiers'


def test_renders_every_backend_process(results: Results) -> None:
    for env in contract.ENVS:
        model = results.baseline.models[env]
        assert not model.render_errors, model.render_errors
        expected = {
            'cloud_run/backend',
            'cloud_run/backend-sync',
            'cloud_run/backend-integration',
            'gke/backend-listen',
        }
        assert expected <= set(model.deployments)
        assert model.deployments['cloud_run/backend-integration'].url_hosts, 'recovery tasks must trace to integration'
    if HAS_HELM:
        assert 'helm/batch-pipeline-worker' in results.baseline.models['prod'].deployments


def test_config_map_entry_without_source_fails_like_22098(results: Results) -> None:
    invariants = {(v.invariant, v.env) for v in results.mutations['config_map_without_source']}
    assert ('config-map-source', 'prod') in invariants
    assert ('renders', 'prod') in invariants


def test_recovery_task_without_audience_fails_like_22149(results: Results) -> None:
    found = results.mutations['recovery_without_audience']
    assert any(
        v.invariant == 'task-edge' and v.scope == 'cloud_run/backend-integration->batch-quarantine-recovery'
        for v in found
    ), found


def test_recovery_task_to_host_without_recovery_audience_fails_like_22149(results: Results) -> None:
    messages = [v.message for v in results.mutations['recovery_to_sync'] if v.invariant == 'task-edge']
    # A recorded on-policy drains even after the receiver's mode changes. The
    # receiving route still must verify the dispatcher's audience and identity.
    assert any('verifies BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE' in m for m in messages), messages


def test_recovery_handler_timeout_below_deadline_fails(results: Results) -> None:
    found = results.mutations['integration_timeout_300']
    assert any(v.invariant == 'handler-timeout' and 'backend-integration' in v.scope for v in found), found


@pytest.mark.skipif(not HAS_HELM, reason='Helm unavailable; worker chart render runs where helm is installed')
def test_worker_missing_head_priority_fails_like_22121(results: Results) -> None:
    # The chart default renders the key as 'false'; the real pre-fix commit had no env line at all, which
    # reader-split also catches (see the opt-in commit replay).
    found = {(v.invariant, v.scope) for v in results.mutations['worker_without_head_priority']}
    assert ('coupled-flag', 'BATCH_PIPELINE_HEAD_PRIORITY_ENABLED') in found


def test_unparseable_boolean_value_fails(results: Results) -> None:
    assert any(
        v.invariant == 'boolean-token'
        and v.scope.endswith('backend-integration/BATCH_PIPELINE_SERVING_ENABLED')  # pragma: allowlist secret
        for v in results.mutations['unparseable_boolean']
    )


def test_unparseable_named_set_boolean_fails(results: Results) -> None:
    # LIVE_CAPTURE_WINDOW_RETENTION is read via ``in _TRUTHY`` (a named frozenset); the scanner must
    # resolve named collections or this deployed flag is invisible to boolean-token.
    assert any(
        v.invariant == 'boolean-token' and v.scope.endswith('/LIVE_CAPTURE_WINDOW_RETENTION')
        for v in results.mutations['unparseable_named_set_boolean']
    ), results.mutations['unparseable_named_set_boolean']


def test_wrong_handler_route_fails(results: Results) -> None:
    # Correct host, wrong path: every sync task would 404.
    assert any(
        v.invariant == 'task-edge' and 'not the handler route' in v.message
        for v in results.mutations['sync_handler_wrong_route']
    ), results.mutations['sync_handler_wrong_route']


def test_append_route_edge_with_path_fails(results: Results) -> None:
    # Recovery/worker edges join their RPC path onto the URL; a configured path would double it.
    assert any(
        v.invariant == 'task-edge' and 'bare origin' in v.message
        for v in results.mutations['recovery_audience_with_path']
    ), results.mutations['recovery_audience_with_path']


def test_audience_pair_mismatch_fails(results: Results) -> None:
    # Dispatcher mints one audience, target verifies another: every task rejected 403.
    assert any(
        v.invariant == 'task-edge' and 'dispatcher mints' in v.message
        for v in results.mutations['backfill_audience_mismatch']
    ), results.mutations['backfill_audience_mismatch']


def test_typoed_service_host_fails(results: Results) -> None:
    # Service-name prefix matches but the hash is wrong: the manifest itself disagrees on the service's
    # canonical host, and no task edge may silently adopt the typo'd alias.
    invariants = {v.invariant for v in results.mutations['typoed_sync_host']}
    assert 'canonical-host' in invariants, invariants


def test_uid_appended_to_accepted_cohort_fails(results: Results) -> None:
    # The ratchet's gap identity carries a non-sensitive count: appending a UID must not stay "known".
    hits = [v for v in results.mutations['uid_allowlist_appended'] if v.invariant == 'no-uid-literals']
    assert hits, results.mutations['uid_allowlist_appended']
    assert all('uids=2' in v.key for v in hits), [v.key for v in hits]


def test_new_uid_literal_fails_without_echoing_it(results: Results) -> None:
    hits = [v for v in results.mutations['uid_literal'] if v.invariant == 'no-uid-literals']
    assert hits
    assert all(SYNTHETIC_UID not in str(v) for v in hits)


def test_prod_service_url_in_dev_fails(results: Results) -> None:
    assert any(v.invariant == 'cross-env-url' for v in results.mutations['prod_url_in_dev'])


def test_constant_named_env_reads_are_resolved(results: Results) -> None:
    # Read through SMART_MERGE_FLATTEN_ENV; a literal-only scanner would call this kill switch dead.
    assert 'CONVERSATION_SMART_MERGE_FLATTEN_ENABLED' in results.baseline.readers.all_reads


# Real pre-fix commits from the 2026-10-18 rollout, each with the invariant that must catch it and its fix:
# #22098 → #22138, #22121's first commit → its fix, #22149's FIX-FIRST head → its fix. Commit SHAs, not secrets.
REPLAYS = (
    ('2f1416c413e2c463867840b5ea905a068d3f9904', 'e11a6850177', 'config-map-source'),  # pragma: allowlist secret
    ('2db920a724e7f6199ea917ef6f8d6bb32b9754a8', 'bd6d1625ee4', 'coupled-flag'),  # pragma: allowlist secret
    ('9a5231de4837ca6391fd42e87ef2cabcd4ef47b4', '11aa6faf410', 'task-edge'),  # pragma: allowlist secret
)


def _has_commit(ref: str) -> bool:
    result = subprocess.run(['git', '-C', str(REPO_ROOT), 'cat-file', '-e', f'{ref}^{{commit}}'], capture_output=True)
    return result.returncode == 0


@pytest.mark.skipif(os.environ.get('CROSS_SERVICE_CONTRACT_REPLAY') != '1', reason='opt-in: needs git history')
def test_pre_fix_commit_fails_and_fix_clears_it(replayed_pair) -> None:
    invariant, broken, fixed = replayed_pair
    assert invariant in broken
    assert invariant not in fixed


@pytest.fixture(scope='module', params=REPLAYS)
def replayed_pair(request):
    broken, fixed, invariant = request.param
    if not (_has_commit(broken) and _has_commit(fixed)):
        pytest.skip('commit not in this clone')

    def invariants_at(ref: str) -> set[str]:
        source = contract.Source(ref=ref)
        try:
            return {v.invariant for v in contract.evaluate(contract.build_context(source))}
        finally:
            source.close()

    return invariant, invariants_at(broken), invariants_at(fixed)
