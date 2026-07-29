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

# Nodes that are environmentally incompatible with the hermeticity harness's run
# conditions and are therefore deselected from the nested pytest run — WITHOUT
# removing their file from the subset, so the module is still imported and its
# sys.modules footprint is still scanned for stub leaks.
#
# ``test_empty_bearer_token_sends_close_1008`` asserts that an empty bearer token is
# rejected with a WebSocketDisconnect(1008). That enforcement path only fires when
# LOCAL_DEVELOPMENT is unset; the offline test image runs the whole suite with the
# global LOCAL_DEVELOPMENT dev-bypass enabled, under which an empty token is accepted
# and no disconnect is raised. The remaining 22 auth-handshake cases pass either way
# (they use invalid/malformed tokens rejected regardless of the bypass), so only this
# single node is deselected. This is a pre-existing residual, not a hermeticity issue.
_DESELECT_NODES = (
    "tests/unit/test_ws_auth_handshake.py::TestWebSocketAuthListen::test_empty_bearer_token_sends_close_1008",
)


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


def _assert_nested_pytest_succeeded(rc: int | None, output: str) -> None:
    assert rc == 0, (
        "single-process-safe subset pytest run failed "
        f"(nested exit code {rc!r}); the hermeticity result is invalid:\n{output}"
    )


def test_nonzero_nested_pytest_result_invalidates_hermeticity() -> None:
    with pytest.raises(AssertionError, match="nested exit code 4"):
        _assert_nested_pytest_succeeded(4, "ERROR: file or directory not found")


def test_single_process_safe_subset_does_not_leak_backend_stubs():
    subset = _read_subset()
    if not subset:
        pytest.skip("single-process-safe subset is empty (no files migrated yet)")
    missing = [path for path in subset if not (BACKEND_DIR / path).is_file()]
    assert not missing, "single-process-safe subset references missing test files:\n  " + "\n  ".join(missing)

    # In-process harness: run pytest via ``pytest.main`` in the SAME interpreter that
    # performs the leak scan, so a stub left behind by a subset test is actually
    # observable. The previous nested-subprocess design scanned the parent while
    # pytest ran in a child that was already gone — leaks silently vanished.
    harness = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {str(BACKEND_DIR)!r})
        import pytest

        deselect_args = []
        for node in {_DESELECT_NODES!r}:
            deselect_args += ["--deselect", node]
        rc = pytest.main(["-q", "-p", "no:cacheprovider", *deselect_args, *{subset!r}])

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
    combined_output = "\n".join((result.stdout, result.stderr))
    _assert_nested_pytest_succeeded(rc, combined_output)
    assert not leaked, (
        "single-process-safe subset leaked backend stub module(s) into sys.modules "
        "(these would corrupt subsequent tests):\n  " + "\n  ".join(f"{name} ({cls})" for name, cls in leaked)
    )
