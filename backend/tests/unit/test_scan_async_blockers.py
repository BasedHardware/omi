import importlib.util
import textwrap
from pathlib import Path
from types import ModuleType

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
SCANNER_PATH = BACKEND_DIR / "scripts" / "scan_async_blockers.py"


@pytest.fixture
def scanner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("scan_async_blockers_interprocedural_test", SCANNER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _scan_source(scanner: ModuleType, tmp_path: Path, source: str):
    source_path = tmp_path / "sample.py"
    source_path.write_text(textwrap.dedent(source), encoding="utf-8")
    return source_path, scanner.scan_dirs([str(tmp_path)])


def test_direct_local_sync_wrapper_is_reported_at_async_call_site(scanner, tmp_path):
    _source_path, results = _scan_source(
        scanner,
        tmp_path,
        """
        import asyncio

        def read_payload():
            return open("payload.json").read()

        @router.get("/payload")
        async def endpoint():
            await asyncio.sleep(0)
            return read_payload()
        """,
    )

    assert len(results["medium_file_io"]) == 1
    call = results["medium_file_io"][0]["calls"][0]
    assert call["call"] == "read_payload() -> open()"
    assert call["via"] == ["read_payload"]
    assert call["line"] != call["sink_line"]


def test_transitive_local_sync_wrappers_preserve_full_blocking_path(scanner, tmp_path):
    _source_path, results = _scan_source(
        scanner,
        tmp_path,
        """
        import asyncio
        import requests

        def request_remote():
            return requests.get("https://example.test")

        def load_remote():
            return request_remote()

        @router.get("/remote")
        async def endpoint():
            await asyncio.sleep(0)
            return load_remote()
        """,
    )

    assert len(results["high_network_io"]) == 1
    call = results["high_network_io"][0]["calls"][0]
    assert call["call"] == "load_remote() -> request_remote() -> requests.get()"
    assert call["via"] == ["load_remote", "request_remote"]
    assert len(call["chain_lines"]) == 3


def test_safe_local_sync_helper_does_not_create_a_finding(scanner, tmp_path):
    _source_path, results = _scan_source(
        scanner,
        tmp_path,
        """
        import asyncio

        def normalize(value):
            return value.strip().lower()

        @router.get("/normalize")
        async def endpoint():
            await asyncio.sleep(0)
            return normalize(" Safe ")
        """,
    )

    assert results["high_network_io"] == []
    assert results["medium_file_io"] == []
    assert results["time_sleep"] == []
    assert results["mixed_await_sync_db"] == []
    assert results["async_helpers_with_blocking"] == []


def test_recursive_helper_cycle_reaches_blocking_sink_without_looping(scanner, tmp_path):
    _source_path, results = _scan_source(
        scanner,
        tmp_path,
        """
        import asyncio

        def first(depth):
            if depth:
                return second(depth - 1)
            return open("payload.json").read()

        def second(depth):
            return first(depth - 1) if depth else "done"

        @router.get("/recursive")
        async def endpoint():
            await asyncio.sleep(0)
            return second(2)
        """,
    )

    call = results["medium_file_io"][0]["calls"][0]
    assert call["call"] == "second() -> first() -> open()"
    assert call["via"] == ["second", "first"]


def test_safe_recursive_helper_cycle_has_no_effect(scanner, tmp_path):
    _source_path, results = _scan_source(
        scanner,
        tmp_path,
        """
        import asyncio

        def first(depth):
            return second(depth - 1) if depth else "done"

        def second(depth):
            return first(depth - 1) if depth else "done"

        @router.get("/recursive")
        async def endpoint():
            await asyncio.sleep(0)
            return first(2)
        """,
    )

    assert results["high_network_io"] == []
    assert results["medium_file_io"] == []
    assert results["async_helpers_with_blocking"] == []


def test_local_sync_helper_passed_to_run_blocking_is_safe(scanner, tmp_path):
    _source_path, results = _scan_source(
        scanner,
        tmp_path,
        """
        def read_payload():
            return open("payload.json").read()

        async def helper():
            return await run_blocking(storage_executor, read_payload)
        """,
    )

    assert results["async_helpers_with_blocking"] == []


def test_diff_scope_includes_changed_transitive_helper_lines(scanner, tmp_path):
    source_path, results = _scan_source(
        scanner,
        tmp_path,
        """
        import asyncio

        def read_payload():
            return open("payload.json").read()

        @router.get("/payload")
        async def endpoint():
            await asyncio.sleep(0)
            return read_payload()
        """,
    )
    finding = results["medium_file_io"][0]
    sink_line = finding["calls"][0]["sink_line"]
    scope = {
        "ranges": {str(source_path): [(sink_line, sink_line)]},
        "import_changed_files": set(),
    }

    assert scanner.finding_in_changed_scope(finding, scope)
