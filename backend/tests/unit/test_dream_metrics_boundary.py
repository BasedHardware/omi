"""Cheap write signals must stay independent of Dream orchestration telemetry."""

from pathlib import Path
from types import ModuleType

from database import dream_store
from testing.import_isolation import load_module_fresh, stub_modules


def test_repeated_datastore_import_needs_no_prometheus_or_metrics():
    prometheus = ModuleType('prometheus_client')
    # Intentionally lacks both Counter and REGISTRY, like lightweight write-path tests.
    with stub_modules({'prometheus_client': prometheus, 'utils.dream_metrics': None, 'database.dream_metrics': None}):
        for _ in range(2):
            fresh = load_module_fresh('database.dream_store', str(Path(dream_store.__file__)))
            assert callable(fresh.acquire)
            assert callable(fresh.mark_dirty)
