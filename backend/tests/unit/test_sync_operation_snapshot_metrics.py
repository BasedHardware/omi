"""Fresh config imports retain one exported avoided-read counter."""

import importlib.util
from pathlib import Path

from prometheus_client import REGISTRY


def test_fresh_imports_share_counter_and_preserve_increments():
    path = Path(__file__).resolve().parents[2] / 'config' / 'sync_operation_snapshot.py'

    def fresh_import():
        spec = importlib.util.spec_from_file_location('_snapshot_metrics_reload', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    first = fresh_import()
    second = fresh_import()
    assert second.READS_AVOIDED is first.READS_AVOIDED
    labels = {'origin': 'job:sync_operation_snapshot', 'operation': 'redirect_hydration'}
    name = 'omi_sync_operation_snapshot_reads_avoided_total'
    before = REGISTRY.get_sample_value(name, labels) or 0
    first.avoided('redirect_hydration')
    second.avoided('redirect_hydration')
    assert REGISTRY.get_sample_value(name, labels) == before + 2
