"""Hermeticity guard: prove the single-process-safe subset does not leak module stubs.

WHY: "single-process-safe" must be a *provable* property (PLAN.md P5), not "it passed
this ordering." The disease we care about is a test leaving a fake/stub module in
``sys.modules`` that shadows a real backend module for a subsequent test. This guard
runs the curated clean subset (``backend/tests/.single_process_safe_subset``) in a
fresh subprocess and asserts that every backend-owned entry in ``sys.modules``
afterward is the REAL module (has a ``__file__`` under ``backend/`` or is a package
with a real ``__path__``), never a bare ``types.ModuleType``/``AutoMockModule`` stub.

The subset starts empty and grows monotonically as files are migrated; while empty
this test is skipped. See ``backend/docs/test_isolation.md`` and
``.coordination/test-isolation/PLAN.md`` P5.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow

BACKEND_DIR = Path(__file__).resolve().parents[2]
SUBSET_FILE = BACKEND_DIR / "tests" / ".single_process_safe_subset"

BACKEND_PREFIXES = ("database.", "utils.", "models.", "routers.", "jobs.", "dependencies")

# Module type names that are unambiguously test fakes regardless of whether a real
# source file backs the name. Production code never installs these into sys.modules.
_STUB_TYPE_NAMES = frozenset({"AutoMockModule", "MagicMock", "Mock", "AsyncMock", "NonCallableMagicMock"})


def _read_subset() -> list[str]:
    if not SUBSET_FILE.exists():
        return []
    files = []
    for raw in SUBSET_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        files.append(line)
    return files


def test_single_process_safe_subset_does_not_leak_backend_stubs():
    subset = _read_subset()
    if not subset:
        pytest.skip("single-process-safe subset is empty (no files migrated yet)")

    # In-process harness: run pytest via ``pytest.main`` in the SAME interpreter that
    # performs the leak scan, so a stub left behind by a subset test is actually
    # observable. The previous nested-subprocess design scanned the parent while
    # pytest ran in a child that was already gone — leaks silently vanished.
    harness = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {str(BACKEND_DIR)!r})
        import pytest

        rc = pytest.main(["-q", "-p", "no:cacheprovider", *{subset!r}])

        # Scan sys.modules for backend-owned entries that are stubs shadowing a real
        # module (or unambiguously a test fake). A deliberately-synthetic module name
        # with no real backing source (e.g. ``utils._async_tasks_metric_cache`` created
        # at import time by production code) is NOT a leak — it shadows nothing. A
        # failing test must still not pollute, so this runs regardless of pytest's rc.
        import os
        BACKEND_DIR = {str(BACKEND_DIR)!r}
        PREFIXES = {BACKEND_PREFIXES!r}
        STUB_TYPE_NAMES = {set(_STUB_TYPE_NAMES)!r}
        leaked = []
        for name in list(sys.modules):
            if not (any(name == p.rstrip('.') or name.startswith(p) for p in PREFIXES)):
                continue
            mod = sys.modules.get(name)
            if mod is None:
                continue
            f = getattr(mod, "__file__", None)
            is_pkg = hasattr(mod, "__path__")
            type_name = type(mod).__name__
            is_plain_stub = (f is None) and (not is_pkg)
            if not is_plain_stub and type_name not in STUB_TYPE_NAMES:
                continue
            # Does a real source file back this dotted name? Only flag if it does
            # (a stub is shadowing a real module) or the type is an obvious fake.
            rel = name.replace('.', os.sep)
            real_file = (
                os.path.exists(os.path.join(BACKEND_DIR, rel + '.py'))
                or os.path.exists(os.path.join(BACKEND_DIR, rel, '__init__.py'))
            )
            if real_file or type_name in STUB_TYPE_NAMES:
                leaked.append((name, type_name))
        import json
        print("HERMETICITY_RC=" + str(rc))
        print("HERMETICITY_LEAKED=" + json.dumps(sorted(leaked)))
        sys.exit(0)
        """)
    try:
        result = subprocess.run(
            [sys.executable, "-c", harness],
            capture_output=True,
            text=True,
            cwd=str(BACKEND_DIR),
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(
            "hermeticity harness timed out after 600s running the single-process-safe subset; "
            "a subset test likely deadlocked (network wait / thread hang)."
        )

    rc = None
    leaked: list[list[str]] = []
    for line in result.stdout.splitlines() + result.stderr.splitlines():
        if line.startswith("HERMETICITY_RC="):
            rc = int(line.split("=", 1)[1])
        elif line.startswith("HERMETICITY_LEAKED="):
            import json

            leaked = json.loads(line.split("=", 1)[1])
    # Pollution is a hard failure regardless of pytest's own rc.
    assert not leaked, (
        "single-process-safe subset leaked backend stub module(s) into sys.modules "
        "(these would corrupt subsequent tests):\n  " + "\n  ".join(f"{name} ({cls})" for name, cls in leaked)
    )

    # Note: we do NOT hard-fail on pytest rc != 0 here. Subset test failures can stem
    # from runtime global state unrelated to sys.modules hermeticity (e.g. protobuf
    # descriptor-pool collisions, prometheus registry duplication across files). The
    # LEAKED assertion above is the hermeticity invariant (P5); runtime-state isolation
    # of individual files is tracked separately in the migration ledger.
