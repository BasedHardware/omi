"""Cached real-lane scans backing the async-gate real-module grid.

The grid's cells pin literal verdicts from two module-scoped scans of the
real production batch-lane modules: the fixed posture and the posture with
the pure database-module classifier resolution ablated (the blackout
regression surface, FC-async-blocker-gate-false-positive-on-pure-db-
classifiers). Both scans run once at import; cells only read the caches.
"""

import ast
import importlib.util
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
SCANNER_PATH = BACKEND_DIR / "scripts" / "scan_async_blockers.py"
LANE_DIR = BACKEND_DIR / "utils" / "batch_pipeline"
RETRY_FILE = BACKEND_DIR / "database" / "firestore_transaction_retry.py"
PUMP_FILE = LANE_DIR / "pump.py"


def _load_scanner():
    spec = importlib.util.spec_from_file_location("scan_async_blockers_real_lane", SCANNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_scanner = _load_scanner()


def _scan(ablate: bool):
    if not ablate:
        return _scanner.scan_dirs([str(LANE_DIR), str(RETRY_FILE)])
    import unittest.mock as mock

    with mock.patch.object(_scanner, "_database_pure_callable_imports", return_value=set()):
        return _scanner.scan_dirs([str(LANE_DIR), str(RETRY_FILE)])


FIXED = _scan(False)
ABLATED = _scan(True)

_EFFECT_CACHE = {}


def _file_effect_summaries(mode_key: str, rel: str):
    """One effect analysis per (mode, file), shared by every cell on that file."""
    cache_key = (mode_key, rel)
    if cache_key in _EFFECT_CACHE:
        return _EFFECT_CACHE[cache_key]
    path = BACKEND_DIR / rel
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    db_names, db_module_aliases = _scanner.get_db_imports(source)
    storage_names = _scanner.get_storage_imports(source)
    prerecorded_names = _scanner.get_prerecorded_stt_imports(source)
    utility_db, sync_network = _scanner.get_sync_utility_imports(source)
    pure_names = set()
    cm_names = set()
    if mode_key == "FIXED":
        pure_names = _scanner._database_pure_callable_imports(tree, str(path), {})
        cm_names = _scanner._database_context_manager_imports(tree, str(path), {})
    effects = _scanner.analyze_local_sync_helpers(
        tree,
        db_names | utility_db,
        db_module_aliases,
        storage_names,
        prerecorded_names,
        sync_network,
        cm_names,
        pure_names,
    )
    summaries = {
        name: tuple(sorted({field for (field, _line, _call) in helper_effects}))
        for name, helper_effects in effects.items()
    }
    _EFFECT_CACHE[cache_key] = summaries
    return summaries


def FIXED_effect_summary(rel: str, name: str):
    return _file_effect_summaries("FIXED", rel).get(name, ())


def ABLATED_effect_summary(rel: str, name: str):
    return _file_effect_summaries("ABLATED", rel).get(name, ())


def finding_for(results, file_suffix: str, function: str):
    for finding in results["async_helpers_with_blocking"]:
        if finding["file"].endswith(file_suffix) and finding["function"] == function:
            return finding
    return None


def fixed_flagged_functions():
    return sorted({f["function"] for f in FIXED["async_helpers_with_blocking"]})


def ablated_flagged_functions():
    return sorted({f["function"] for f in ABLATED["async_helpers_with_blocking"]})


def pump_pure_exempt_names():
    tree = ast.parse(PUMP_FILE.read_text(encoding="utf-8"))
    return sorted(_scanner._database_pure_callable_imports(tree, str(PUMP_FILE), {}))


def pump_cm_exempt_names():
    tree = ast.parse(PUMP_FILE.read_text(encoding="utf-8"))
    return sorted(_scanner._database_context_manager_imports(tree, str(PUMP_FILE), {}))
