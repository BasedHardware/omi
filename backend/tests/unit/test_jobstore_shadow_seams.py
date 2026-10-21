"""The four A2 shadow seams (lead ruling 2026-10-19 14:41Z) stay plain Firestore unless staging opts in.

Each seam builds its store as ``shadow_from_env(FirestoreStore(...))``. The AST test pins that shape at the
exact call sites; the behaviour tests run each module's own bound names: with the mode unset, and with the
prod namespace even when every shadow setting is present, the seam yields the plain ``FirestoreStore``.
"""

from __future__ import annotations

import ast
import inspect
import sys

import pytest

import diarizer.batch_pipeline_runtime  # noqa: F401  (imported at collection: the timing budget is per test)
import utils.batch_pipeline.intake  # noqa: F401
import utils.batch_pipeline.live  # noqa: F401
import utils.batch_pipeline.serving  # noqa: F401
from database import batch_pipeline_shadow_hook as hook
from database.batch_pipeline_store import FirestoreStore
from database.jobstore import dual_store
from database.jobstore.dual_store import DualStore

SEAMS = [
    ('diarizer.batch_pipeline_runtime', 'main'),
    ('utils.batch_pipeline.serving', 'serving_for_stage'),
    ('utils.batch_pipeline.live', 'register_recording'),
    ('utils.batch_pipeline.intake', 'accept_upload'),
]


def _module(name: str):
    return sys.modules[name]


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(dual_store, '_SHADOWED', {})
    for name in ('BATCH_JOBSTORE_MODE', 'JOBSTORE_PG_HOST', 'JOBSTORE_PG_DATABASE', 'JOBSTORE_PG_USER'):
        monkeypatch.delenv(name, raising=False)


def _shadow_settings(monkeypatch):
    monkeypatch.setenv('BATCH_JOBSTORE_MODE', 'shadow')
    monkeypatch.setenv('JOBSTORE_PG_HOST', '10.0.0.1')
    monkeypatch.setenv('JOBSTORE_PG_DATABASE', 'jobstore_staging')
    monkeypatch.setenv('JOBSTORE_PG_USER', 'svc@example.iam')


@pytest.mark.parametrize('module_name, function', SEAMS)
def test_every_store_construction_in_the_seam_is_wrapped(module_name, function):
    module = _module(module_name)
    tree = ast.parse(inspect.getsource(getattr(module, function)))
    wrapped, bare = 0, 0
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'FirestoreStore':
            parent = parents.get(node)
            if isinstance(parent, ast.Call) and getattr(parent.func, 'id', None) == 'shadow_from_env':
                wrapped += 1
            else:
                bare += 1
    assert wrapped == 1, f'{module_name}.{function}: expected exactly one shadow_from_env(FirestoreStore(...))'
    if module_name == 'diarizer.batch_pipeline_runtime':
        # main() validates the namespace with a bare FirestoreStore before any client exists; the store it
        # keeps is the wrapped one.
        assert bare == 1
    else:
        assert bare == 0
    assert module.shadow_from_env is hook.shadow_from_env  # the light seam: no job-store import in firestore mode
    assert module.FirestoreStore is FirestoreStore


@pytest.mark.parametrize('module_name, _function', SEAMS)
def test_seam_is_plain_firestore_when_the_mode_is_unset(module_name, _function, monkeypatch):
    module = _module(module_name)
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('JOBSTORE_PG_HOST', '10.0.0.1')  # configured, but no mode
    store = module.shadow_from_env(module.FirestoreStore('batch_pipeline_dev'))
    assert type(store) is FirestoreStore


@pytest.mark.parametrize('module_name, _function', SEAMS)
def test_seam_is_plain_firestore_in_prod_even_with_every_shadow_setting(module_name, _function, monkeypatch):
    module = _module(module_name)
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    _shadow_settings(monkeypatch)
    store = module.shadow_from_env(module.FirestoreStore('batch_pipeline_prod'))
    assert type(store) is FirestoreStore


@pytest.mark.parametrize('module_name, _function', SEAMS)
def test_seam_shadows_only_when_staging_opts_in(module_name, _function, monkeypatch):
    module = _module(module_name)
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    _shadow_settings(monkeypatch)
    store = module.shadow_from_env(module.FirestoreStore('batch_pipeline_dev'))
    assert isinstance(store, DualStore) and type(store.primary) is FirestoreStore


def test_seam_failure_keeps_the_plain_primary(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    _shadow_settings(monkeypatch)
    monkeypatch.setattr(dual_store, 'shadow_from_env', lambda _p: (_ for _ in ()).throw(RuntimeError('x')))
    primary = FirestoreStore('batch_pipeline_dev')
    assert hook.shadow_from_env(primary) is primary


@pytest.mark.parametrize(
    'module_name, function',
    [
        ('utils.batch_pipeline.provider_stt', '_service_stage'),
        ('utils.batch_pipeline.intake', 'get_durable_job_status'),
    ],
)
def test_secondary_writer_stores_are_the_shadow_seam(module_name, function):
    """Provider-STT start/settle and the durable-status redrive write batch rows through ``store.run``."""
    import importlib

    module = importlib.import_module(module_name)

    tree = ast.parse(inspect.getsource(getattr(module, function)))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'FirestoreStore'
    ]
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    assert len(calls) == 1 and getattr(parents[calls[0]].func, 'id', None) == 'shadow_from_env'
