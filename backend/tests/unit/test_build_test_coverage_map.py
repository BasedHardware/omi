"""scripts/build_test_coverage_map.py: only function-body execution maps a source file to a test."""

import importlib.util
import sys
import types
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load_builder(monkeypatch, coverage_rows):
    """Load the builder with a stand-in `coverage` module whose data files report `coverage_rows`."""

    class FakeCoverageData:
        def __init__(self, basename):
            self.name = Path(basename).name

        def read(self):
            if self.name not in coverage_rows:
                raise ValueError('partial data file')

        def measured_files(self):
            return list(coverage_rows[self.name])

        def lines(self, measured):
            return coverage_rows[self.name][measured]

    monkeypatch.setitem(sys.modules, 'coverage', types.SimpleNamespace(CoverageData=FakeCoverageData))
    spec = importlib.util.spec_from_file_location(
        'build_test_coverage_map', BACKEND_DIR / 'scripts' / 'build_test_coverage_map.py'
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_import_time_lines_do_not_map_but_function_bodies_do(tmp_path, monkeypatch):
    source = BACKEND_DIR / 'scripts' / 'build_test_coverage_map.py'  # a real backend module with functions
    text = source.read_text(encoding='utf-8').splitlines()
    body_line = next(i for i, line in enumerate(text, start=1) if line.strip().startswith('lines: set[int] = set()'))
    import_line = next(i for i, line in enumerate(text, start=1) if line.startswith('import argparse'))
    rows = {
        'calls.cov': {str(source): [import_line, body_line]},
        'imports.cov': {str(source): [import_line]},
        'outside.cov': {'/usr/lib/python3/json/__init__.py': [1, 2, 3]},
    }
    builder = _load_builder(monkeypatch, rows)
    for name, test in (
        ('calls', 'tests/unit/test_calls.py'),
        ('imports', 'tests/unit/test_imports.py'),
        ('outside', 'tests/unit/test_outside.py'),
        ('crashed', 'tests/unit/test_crashed.py'),
    ):
        (tmp_path / f'{name}.cov').write_text('')
        (tmp_path / f'{name}.path').write_text(test + '\n')

    files, tests, unreadable = builder.build(tmp_path)

    assert files == {'scripts/build_test_coverage_map.py': ['tests/unit/test_calls.py']}
    assert tests == ['tests/unit/test_calls.py', 'tests/unit/test_imports.py', 'tests/unit/test_outside.py']
    assert unreadable == ['tests/unit/test_crashed.py']


def test_function_body_lines_cover_nested_bodies_not_signatures(tmp_path, monkeypatch):
    builder = _load_builder(monkeypatch, {})
    module = BACKEND_DIR / 'scripts' / 'build_test_coverage_map.py'
    lines = builder.function_body_lines('scripts/build_test_coverage_map.py')
    text = module.read_text(encoding='utf-8').splitlines()
    signature = next(i for i, line in enumerate(text, start=1) if line.startswith('def backend_relative'))
    assert signature not in lines
    assert signature + 1 in lines or signature + 2 in lines
