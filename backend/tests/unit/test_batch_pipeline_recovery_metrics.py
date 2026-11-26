"""Required collector imports stay below caller utilities and optional drivers."""

import ast
from pathlib import Path
import subprocess
import sys

BACKEND = Path(__file__).resolve().parents[2]


def test_core_collector_import_is_module_level_and_layered():
    hook = ast.parse((BACKEND / 'database/batch_pipeline_shadow_hook.py').read_text())
    imports = [node for node in hook.body if isinstance(node, ast.ImportFrom)]
    assert any(
        node.module == 'database.batch_pipeline_recovery_metrics'
        and any(alias.name == 'RECOVERY_COLLECTORS' for alias in node.names)
        for node in imports
    )
    core = ast.parse((BACKEND / 'database/batch_pipeline_recovery_metrics.py').read_text())
    assert [node.module for node in ast.walk(core) if isinstance(node, ast.ImportFrom)] == ['prometheus_client']
    assert not any(isinstance(node, ast.Import) for node in ast.walk(core))


def test_fresh_firestore_hook_exports_default_and_private_without_optional_or_utility_imports():
    code = '''
import importlib.abc
import os
import sys
from prometheus_client import CollectorRegistry, REGISTRY, generate_latest
class RefuseOptional(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('database.jobstore', 'utils', 'psycopg')):
            raise AssertionError('unexpected dependency: ' + fullname)
sys.meta_path.insert(0, RefuseOptional())
os.environ['BATCH_JOBSTORE_MODE'] = 'firestore'
from database.batch_pipeline_shadow_hook import shadow_parity_collectors
from database.batch_pipeline_recovery_metrics import RECOVERY_COLLECTORS, RECOVERY_DISCOVERY_TOTAL
assert shadow_parity_collectors() == RECOVERY_COLLECTORS
RECOVERY_DISCOVERY_TOTAL.labels('other', 'unknown', 'entry', 'none', 'entry').inc()
private = CollectorRegistry()
for collector in RECOVERY_COLLECTORS:
    private.register(collector)
for registry in (REGISTRY, private):
    body = generate_latest(registry).decode()
    assert 'omi_jobstore_recovery_discovery_total{' in body
    assert 'omi_jobstore_index_primary_scan_success_timestamp_seconds' in body
assert not any(name.startswith(('database.jobstore', 'utils', 'psycopg')) for name in sys.modules)
'''
    result = subprocess.run([sys.executable, '-c', code], cwd=BACKEND, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_missing_required_core_dependency_is_not_suppressed():
    code = '''
import importlib.abc
import sys
class RefuseCore(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'database.batch_pipeline_recovery_metrics':
            raise ImportError('required recovery metrics unavailable')
sys.meta_path.insert(0, RefuseCore())
try:
    import database.batch_pipeline_shadow_hook
except ImportError as exc:
    assert str(exc) == 'required recovery metrics unavailable'
else:
    raise AssertionError('required dependency failure was suppressed')
'''
    result = subprocess.run([sys.executable, '-c', code], cwd=BACKEND, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_shared_recovery_contract_imports_without_callers_and_shares_reason_state():
    code = """
import importlib.abc
import sys
class RefuseCallers(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('utils', 'database.jobstore', 'psycopg')):
            raise AssertionError('unexpected recovery contract dependency: ' + fullname)
finder = RefuseCallers()
sys.meta_path.insert(0, finder)
from database import batch_pipeline_recovery_discovery as recovery
from database import batch_pipeline_recovery_metrics as metrics
from database import reason_labels as reasons
assert recovery.RECOVERY_DISCOVERY_TOTAL is metrics.RECOVERY_DISCOVERY_TOTAL
class Primary:
    namespace = 'batch_pipeline_prod'
    def due(self, *args):
        raise ValueError('synthetic primary failure')
before = recovery.primary_failure_generation('batch_pipeline_prod')
try:
    with recovery.RecoveryQuery(Primary(), 1, 100, recovery.RecoveryCaller.PUMP) as query:
        query.primary('safety_sweep')
except ValueError as exc:
    assert str(exc) == 'synthetic primary failure'
else:
    raise AssertionError('primary failure was suppressed')
assert recovery.primary_failure_generation('batch_pipeline_prod') == before + 1
assert not any(name.startswith(('utils', 'database.jobstore', 'psycopg')) for name in sys.modules)
sys.meta_path.remove(finder)
from utils.observability import reasons as public
assert public.ReasonFamily is reasons.ReasonFamily
assert public.OMI_REASON_TOTAL is reasons.OMI_REASON_TOTAL
assert public.REASON_UNKNOWN_TOTAL is reasons.REASON_UNKNOWN_TOTAL
family = reasons.ReasonFamily.FALLBACK
known = reasons.OMI_REASON_TOTAL.labels(family=family.value)._value.get()
unknown = reasons.REASON_UNKNOWN_TOTAL.labels(family=family.value)._value.get()
assert public.reason_label(family, 'private unbounded value', recovery.RecoveryDiscoveryReason) == 'unknown'
assert reasons.OMI_REASON_TOTAL.labels(family=family.value)._value.get() == known + 1
assert reasons.REASON_UNKNOWN_TOTAL.labels(family=family.value)._value.get() == unknown + 1
"""
    result = subprocess.run([sys.executable, '-c', code], cwd=BACKEND, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
