"""Index-mode selection preserves the dark default, namespace fence, mirror refresh and live rollback."""

from types import SimpleNamespace

import pytest

from database import batch_pipeline_shadow_hook as hook
from database.jobstore import dual_store, index_config
from database.jobstore.dual_store import DualStore
from database.jobstore.index_store import INDEX_PRIMARY_SCAN_SUCCESS_TIMESTAMP, INDEX_READS_TOTAL, IndexStore


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('BATCH_JOBSTORE_MODE', 'index')
    monkeypatch.setenv('JOBSTORE_SHADOW_NAMESPACES', 'batch_pipeline_dev,batch_pipeline_prod')
    for name in (
        'JOBSTORE_INDEX_QUERIES',
        'JOBSTORE_INDEX_READS',
        'JOBSTORE_SHADOW_WRITES',
        'JOBSTORE_SHADOW_QUERY_PARITY',
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(dual_store, '_SHADOWED', {})
    monkeypatch.setattr(index_config, '_INDEXED', {})
    primary = SimpleNamespace(namespace='batch_pipeline_dev', due=lambda *_args: ['primary'])
    shadow = SimpleNamespace(namespace=primary.namespace, pool=SimpleNamespace())
    mirror = DualStore(primary, shadow)
    monkeypatch.setattr(dual_store, '_configured_copy', lambda _primary: mirror)
    return primary, mirror


def test_index_mode_is_an_explicit_selection_and_caches_the_sweep(configured, monkeypatch):
    primary, mirror = configured
    store = hook.shadow_from_env(primary)
    assert isinstance(store, IndexStore)
    assert store.enabled_queries == frozenset({'due_leased'})
    assert store.mirror is mirror
    assert store.due('leased', 1) == ['primary']
    assert hook.shadow_from_env(primary) is store
    assert 'due_leased' in store._last_sweep
    monkeypatch.setenv('BATCH_JOBSTORE_MODE', 'shadow')
    assert hook.shadow_from_env(primary) is mirror
    monkeypatch.delenv('BATCH_JOBSTORE_MODE')
    assert hook.shadow_from_env(primary) is primary


@pytest.mark.parametrize('queries', ['', '*', 'due_leased,oldest', 'control_candidates', 'projection_page'])
def test_unknown_or_empty_query_allowlist_keeps_firestore_answers(configured, monkeypatch, queries):
    primary, mirror = configured
    monkeypatch.setenv('JOBSTORE_INDEX_QUERIES', queries)
    assert hook.shadow_from_env(primary) is mirror


@pytest.mark.parametrize('switch', ['JOBSTORE_INDEX_READS', 'JOBSTORE_SHADOW_WRITES'])
@pytest.mark.parametrize('value', ['off', 'false', '0', 'no', ' OFF '])
def test_both_live_kill_paths_disable_existing_and_new_index_stores(configured, monkeypatch, switch, value):
    primary, mirror = configured
    store = hook.shadow_from_env(primary)
    assert store.enabled()
    monkeypatch.setenv(switch, value)
    assert not store.enabled()
    assert store.due('leased', 1) == ['primary']
    assert hook.shadow_from_env(primary) is store


def test_disabled_index_mode_keeps_a_measurable_primary_baseline(configured, monkeypatch):
    primary, mirror = configured
    monkeypatch.setenv('JOBSTORE_INDEX_READS', 'off')
    store = hook.shadow_from_env(primary)
    assert isinstance(store, IndexStore) and store.mirror is mirror
    metric = INDEX_READS_TOTAL.labels(query='due_leased', source='firestore', reason='disabled', outcome='returned')
    before = metric._value.get()
    assert store.due('leased', 1) == ['primary']
    assert metric._value.get() == before + 1


def test_query_ramp_replaces_wrapper_without_reactivating_an_old_selection(configured, monkeypatch):
    primary, mirror = configured
    first = hook.shadow_from_env(primary)
    monkeypatch.setenv('JOBSTORE_INDEX_QUERIES', 'due_leased,due_retry')
    second = hook.shadow_from_env(primary)
    assert second is not first and second.mirror is mirror
    assert not first.enabled() and second.enabled()


def test_index_mode_does_not_open_the_production_namespace(configured, monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('OMI_DEPLOYMENT', 'prod')
    monkeypatch.setenv('FIRESTORE_DATABASE_ID', '(default)')
    primary = SimpleNamespace(namespace='batch_pipeline_prod')
    monkeypatch.setattr(dual_store, '_configured_copy', lambda _p: pytest.fail('production copy constructed'))
    assert hook.shadow_from_env(primary) is primary


def test_index_mode_preserves_the_outside_transaction_mirror_refresh(configured, monkeypatch):
    primary, mirror = configured
    hook.shadow_from_env(primary)
    seen = []
    monkeypatch.setattr(mirror, 'refresh', lambda keys: seen.extend(keys))
    hook.mirror_refresh(primary.namespace, [('jobs', 'synthetic')])
    assert seen == [('jobs', 'synthetic')]


def test_first_outside_transaction_refresh_keeps_the_new_cold_cache_mirror(configured, monkeypatch):
    primary, mirror = configured
    seen = []
    monkeypatch.setattr(mirror, 'refresh', lambda keys: seen.extend(keys))
    assert not dual_store._SHADOWED
    hook.mirror_refresh(primary.namespace, [('jobs', 'synthetic')])
    assert dual_store._SHADOWED[primary.namespace] is mirror
    assert seen == [('jobs', 'synthetic')]


@pytest.mark.parametrize('mode', ['index', ' INDEX '])
@pytest.mark.parametrize('disabled_switch', [None, 'JOBSTORE_INDEX_READS', 'JOBSTORE_SHADOW_WRITES'])
def test_private_worker_registry_exports_index_and_existing_parity_collectors(
    configured, monkeypatch, mode, disabled_switch
):
    monkeypatch.setenv('BATCH_JOBSTORE_MODE', mode)
    if disabled_switch:
        monkeypatch.setenv(disabled_switch, 'off')
    collectors = hook.shadow_parity_collectors()
    assert INDEX_READS_TOTAL in collectors
    assert INDEX_PRIMARY_SCAN_SUCCESS_TIMESTAMP in collectors
    assert dual_store.SHADOW_PARITY_TOTAL in collectors


@pytest.mark.parametrize('mode', ['shadow', 'firestore', 'unknown', ''])
def test_private_worker_registry_keeps_other_modes_separate(configured, monkeypatch, mode):
    monkeypatch.setenv('BATCH_JOBSTORE_MODE', mode)
    collectors = hook.shadow_parity_collectors()
    assert INDEX_READS_TOTAL not in collectors
    assert INDEX_PRIMARY_SCAN_SUCCESS_TIMESTAMP in collectors
    if mode == 'shadow':
        assert dual_store.SHADOW_PARITY_TOTAL in collectors
    else:
        from database.batch_pipeline_recovery_metrics import RECOVERY_COLLECTORS

        assert collectors == RECOVERY_COLLECTORS


def test_index_answers_preserve_optional_async_serving_parity(configured, monkeypatch):
    primary, mirror = configured
    queued = []
    monkeypatch.setattr(mirror, '_observe_query', lambda *args: queued.append(args))
    monkeypatch.setenv('JOBSTORE_SHADOW_QUERY_PARITY', 'on')
    store = hook.shadow_from_env(primary)
    assert store.due('leased', 1) == ['primary']
    assert queued == [('due', ('leased', 1, 100), {})]


@pytest.mark.parametrize('bps', ['', 'invalid', '100', '10000'])
def test_production_copy_policy_cannot_certify_unpartitioned_query_coverage(configured, monkeypatch, bps):
    primary, mirror = configured
    primary.namespace = mirror.shadow.namespace = 'batch_pipeline_prod'
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('JOBSTORE_PRODUCTION_MIRROR_SAMPLE_BPS', bps)
    # Grant even the factory's configuration check: it is not coverage proof.
    monkeypatch.setattr(index_config, 'jobstore_production_mirror_configured', lambda: True)
    store = index_config.index_from_env(mirror)
    monkeypatch.setattr(store._index, 'due', lambda *_args: pytest.fail('incomplete PG answer admitted'))
    metric = INDEX_READS_TOTAL.labels(
        query='due_leased', source='firestore', reason='coverage_unknown', outcome='returned'
    )
    before = metric._value.get()
    assert store.due('leased', 1) == ['primary']
    assert store.due('leased', 2) == ['primary']
    assert metric._value.get() == before + 2
