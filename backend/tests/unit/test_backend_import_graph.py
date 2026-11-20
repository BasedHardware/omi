"""Import-graph test selection: which tests can load a changed module or data file."""

import importlib
import sys
import textwrap
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Imported by real module name: the process pool pickles its worker function
# by module path, exactly as the selector imports it.
graph_module = importlib.import_module("scripts.backend_import_graph")


def _load(name: str):
    return importlib.import_module(f"scripts.{name}")


def _tree(root: Path, files: dict) -> Path:
    for relative, body in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(body))
    return root


@pytest.fixture(autouse=True)
def graph_selection_on(monkeypatch):
    monkeypatch.setenv("BACKEND_UNIT_GRAPH_SELECTION", "1")


@pytest.fixture
def graph(tmp_path):
    root = _tree(
        tmp_path,
        {
            "core/__init__.py": "from core.flags import FLAG\n",
            "core/flags.py": "FLAG = 1\n",
            "core/store.py": "import json\n",
            "core/lazy_target.py": "X = 1\n",
            "core/deep_lazy.py": "Y = 1\n",
            "core/data_reader.py": "PATH = 'fixtures/limits.json'\n",
            "svc/__init__.py": "",
            "svc/api.py": """
                from . import helpers
                import core.store

                @helpers.decorate
                def handler(value=helpers.DEFAULT):
                    from core import lazy_target
                    return lazy_target.X
            """,
            "svc/helpers.py": """
                DEFAULT = 0
                def decorate(fn):
                    return fn
                def later():
                    import core.deep_lazy
            """,
            "fixtures/limits.json": "{}",
            "tests/conftest.py": "",
            "tests/unit/conftest.py": "from core import flags\n",
            "tests/unit/test_api.py": "from svc import api\n",
            "tests/unit/test_reader.py": "import core.data_reader\n",
            "tests/unit/test_plain.py": "def test_x():\n    assert True\n",
            "tests/other/test_store.py": "from core.store import json\n",
            "tests/other/test_helpers_lazy.py": "def test_y():\n    import svc.helpers\n",
            "broken.py": "def (:\n",
        },
    )
    return graph_module.build_import_graph(root, workers=1)


TESTS = [
    "tests/unit/test_api.py",
    "tests/unit/test_reader.py",
    "tests/unit/test_plain.py",
    "tests/other/test_store.py",
    "tests/other/test_helpers_lazy.py",
]


def test_module_level_imports_reach_transitively(graph):
    assert graph.dependent_tests("core/store.py", TESTS) == {"tests/unit/test_api.py", "tests/other/test_store.py"}


def test_decorators_and_defaults_are_import_time(graph):
    # svc/api.py uses helpers in a decorator and a default value only.
    assert "tests/unit/test_api.py" in graph.dependent_tests("svc/helpers.py", TESTS)


def test_lazy_import_counts_one_hop_only(graph):
    # api.handler lazily imports lazy_target: api's importers are selected.
    assert graph.dependent_tests("core/lazy_target.py", TESTS) == {"tests/unit/test_api.py"}
    # helpers.later lazily imports deep_lazy; helpers is imported by api at
    # module level, so test_api is selected, and test_helpers_lazy imports
    # helpers only inside a test function (one lazy hop from helpers, not two).
    assert graph.dependent_tests("core/deep_lazy.py", TESTS) == {"tests/unit/test_api.py"}


def test_package_init_and_conftest_dependencies(graph):
    # tests/unit/conftest.py imports core.flags, so every test under tests/unit/ depends on it.
    assert graph.dependent_tests("core/flags.py", TESTS) == {
        "tests/unit/test_api.py",
        "tests/unit/test_reader.py",
        "tests/unit/test_plain.py",
        # core/__init__ re-exports flags, and test_store imports core.store
        "tests/other/test_store.py",
    }


def test_data_files_select_tests_reaching_modules_that_name_them(graph):
    assert graph.dependent_tests("fixtures/limits.json", TESTS) == {"tests/unit/test_reader.py"}
    assert graph.dependent_tests("fixtures/unnamed.json", TESTS) == set()


def test_unparseable_modules_are_recorded(graph):
    assert "broken.py" in graph.unparseable
    assert graph.module_for_path("broken.py") == "broken"


def test_parallel_and_serial_builds_agree(tmp_path, graph):
    # min_parallel_files=0 forces the process-pool branch on the small fixture.
    parallel = graph_module.build_import_graph(graph.backend_dir, workers=2, min_parallel_files=0)
    assert parallel.importers == graph.importers
    assert parallel.lazy_importers == graph.lazy_importers


@pytest.fixture(scope="module")
def selector_and_all_tests():
    selector = _load("select_backend_unit_tests")
    return selector, selector.discover_all_tests()


def test_test_support_module_selects_its_importers_not_the_full_suite(selector_and_all_tests):
    selector, all_tests = selector_and_all_tests
    support = "backend/tests/support/sync_legacy_ratchet_scope.py"
    assert (BACKEND_DIR.parent / support).is_file()
    selected, reason = selector.tests_for_changed_paths([support], all_tests)
    assert selected != all_tests
    assert "tests/unit/test_sync_legacy_import_ratchet.py" in selected
    assert "import graph" in reason


def test_deleted_or_non_python_unknowns_keep_the_full_suite(selector_and_all_tests):
    selector, all_tests = selector_and_all_tests
    for path in (
        "backend/tests/support/deleted_helper.py",
        "backend/database/deleted_module.py",
        "backend/brand_new_unnamed_data.yaml",
    ):
        selected, _ = selector.tests_for_changed_paths([path], all_tests)
        assert selected == all_tests, path


def test_rotation_slices_partition_the_full_suite(selector_and_all_tests):
    selector, _ = selector_and_all_tests
    tests = selector.discover_unit_tests()
    slices = [[test for test in tests if selector.rotation_slice(test, 8) == index] for index in range(8)]
    assert sorted(test for chunk in slices for test in chunk) == sorted(tests)
    assert all(len(chunk) > len(tests) / 16 for chunk in slices)
    # Pinned: crc32 is stable across processes and Python versions, unlike hash().
    assert selector.rotation_slice("tests/unit/test_x.py", 8) == 0x4248F0ED % 8


def test_workflow_passes_both_kill_switches_and_keeps_the_full_suite_paths():
    workflow = (BACKEND_DIR.parent / ".github/workflows/backend-unit-tests.yml").read_text(encoding="utf-8")
    assert "BACKEND_UNIT_GRAPH_SELECTION: ${{ vars.BACKEND_UNIT_GRAPH_SELECTION }}" in workflow
    assert "MAIN_SELECTION: ${{ vars.BACKEND_UNIT_MAIN_SELECTION }}" in workflow
    assert "bash scripts/run-unit-ci.sh --all --shard 8/${{ matrix.shard }}" in workflow
    assert 'git merge-base --is-ancestor "$UNIT_MAIN_BASE" HEAD' in workflow
    assert "BACKEND_UNIT_FORCE_TYPECHECK=1" in workflow


def test_test_code_naming_a_module_selects_it_even_when_the_module_has_importers(tmp_path):
    root = _tree(
        tmp_path,
        {
            "db/__init__.py": "",
            "db/rows.py": "X = 1\n",
            "svc.py": "import db.rows\n",
            "tests/unit/test_svc.py": "import svc\n",
            # Loads the file directly (spec_from_file_location / runpy style).
            "tests/unit/test_rows_fresh.py": "PATH = 'db/rows.py'\n",
            # Production code naming the file is a path table, not a loader.
            "tables.py": "PATHS = ['db/rows.py']\n",
            "tests/unit/test_tables.py": "import tables\n",
        },
    )
    graph = graph_module.build_import_graph(root, workers=1)
    tests = ["tests/unit/test_svc.py", "tests/unit/test_rows_fresh.py", "tests/unit/test_tables.py"]
    assert graph.dependent_tests("db/rows.py", tests) == {"tests/unit/test_svc.py", "tests/unit/test_rows_fresh.py"}


def test_python_source_scanners_are_found_directly_and_through_helpers(tmp_path):
    root = _tree(
        tmp_path,
        {
            "tests/support/inventory.py": "def modules(root):\n    return sorted(root.rglob('*.py'))\n",
            "tests/unit/test_boundary.py": "from tests.support import inventory\n",
            "tests/unit/test_walk.py": "import os\nfor r, _, fs in os.walk('utils'):\n    names = [f for f in fs if f.endswith('.py')]\n",
            "tests/unit/test_fixture_listing.py": "FILES = sorted(DIR.glob('*.json'))\n",
            "tests/unit/test_plain.py": "X = 1\n",
        },
    )
    graph = graph_module.build_import_graph(root, workers=1)
    tests = [
        "tests/unit/test_boundary.py",
        "tests/unit/test_walk.py",
        "tests/unit/test_fixture_listing.py",
        "tests/unit/test_plain.py",
    ]
    assert graph.tree_scan_tests(tests) == {"tests/unit/test_boundary.py", "tests/unit/test_walk.py"}


def test_unmapped_utils_change_still_runs_whole_tree_ratchets(selector_and_all_tests):
    selector, all_tests = selector_and_all_tests
    selected, reason = selector.tests_for_changed_paths(["backend/utils/metrics.py"], all_tests)
    assert "import graph" in reason
    assert {"tests/unit/test_utils_import_boundary.py", "tests/unit/test_http_timeout_defaults.py"} <= set(selected)


def test_integration_only_change_does_not_run_the_unit_suite(selector_and_all_tests):
    selector, all_tests = selector_and_all_tests
    path = "backend/tests/integration/test_home_feed_emulator.py"
    assert (BACKEND_DIR.parent / path).is_file()
    selected, _ = selector.tests_for_changed_paths([path], all_tests)
    # Only unit tests that name or import it (contract inventories) plus the
    # source-scan ratchets; never the 2,900-file suite.
    assert 0 < len(selected) < 100


def test_unreferenced_integration_test_selects_nothing_by_itself(tmp_path, monkeypatch, selector_and_all_tests):
    selector, all_tests = selector_and_all_tests
    graph = selector.import_graph()
    monkeypatch.setattr(graph, "dependent_tests", lambda path, tests: set())
    selected, reason = selector.tests_for_changed_paths(
        ["backend/tests/integration/test_home_feed_emulator.py"], all_tests
    )
    assert selected != all_tests
    assert reason.startswith("only integration/e2e test files outside unit discovery changed")


def test_module_loaded_by_file_in_a_test_is_selected(selector_and_all_tests):
    selector, all_tests = selector_and_all_tests
    selected, _ = selector.tests_for_changed_paths(["backend/database/conversations.py"], all_tests)
    assert "tests/unit/test_conversation_archive_filter_contract.py" in selected
