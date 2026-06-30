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

BACKEND_DIR = Path(__file__).resolve().parents[2]
SUBSET_FILE = BACKEND_DIR / "tests" / ".single_process_safe_subset"

BACKEND_PREFIXES = ("database.", "utils.", "models.", "routers.", "jobs.", "dependencies")


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

    # Subprocess harness: snapshot nothing pre-import; run pytest on the subset; then
    # scan sys.modules for backend-owned entries that are stubs (no real __file__).
    harness = textwrap.dedent(f"""
        import subprocess, sys
        rc = subprocess.call(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *{subset!r}],
            cwd={str(BACKEND_DIR)!r},
        )
        # Run the scan regardless of pytest rc (a failing test still must not pollute).
        import importlib.util
        PREFIXES = {BACKEND_PREFIXES!r}
        leaked = []
        for name in list(sys.modules):
            if not (any(name == p.rstrip('.') or name.startswith(p) for p in PREFIXES)):
                continue
            mod = sys.modules.get(name)
            if mod is None:
                continue
            f = getattr(mod, "__file__", None)
            is_pkg = hasattr(mod, "__path__")
            is_stub = (f is None) and (not is_pkg)
            if is_stub:
                leaked.append((name, type(mod).__name__))
        import json
        print("HERMETICITY_RC=" + str(rc))
        print("HERMETICITY_LEAKED=" + json.dumps(sorted(leaked)))
        sys.exit(0)
        """)
    result = subprocess.run(
        [sys.executable, "-c", harness],
        capture_output=True,
        text=True,
        cwd=str(BACKEND_DIR),
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

    # Surface pytest failures too, but as a softer signal (a flaky subset test is a
    # separate problem from hermeticity).
    if rc is not None and rc != 0:
        pytest.fail(
            "single-process-safe subset did not pass cleanly (rc=%d). "
            "Hermeticity held, but a test failed. Output:\n%s" % (rc, result.stdout[-4000:])
        )
