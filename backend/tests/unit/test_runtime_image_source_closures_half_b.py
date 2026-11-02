"""Source-closure checks for the runtime image contracts, half B.

``test_runtime_image_contracts.py`` grew to ~183s of CI wall, dominated by
``check_source_closures`` staging and AST-walking every registered image
contract in one test. The walk is split over two files by parity of the
sorted contract name: every registered image is checked exactly once across
``...half_a.py`` and ``...half_b.py``, and a newly registered contract lands
in exactly one half by construction, so deleting either file loses real
coverage.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
SCRIPT_PATH = BACKEND_DIR / 'scripts' / 'runtime_image_contracts.py'
HALF_INDEX = 1


def _load_contract_module():
    spec = importlib.util.spec_from_file_location('runtime_image_contracts_for_test', SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def contracts_module():
    return _load_contract_module()


def _half(contracts_module):
    names = sorted(contract.name for contract in contracts_module.load_contracts())
    return [name for index, name in enumerate(names) if index % 2 == HALF_INDEX]


def test_registered_runtime_image_sources_are_closed(contracts_module):
    half = _half(contracts_module)
    contracts = [contract for contract in contracts_module.load_contracts() if contract.name in half]
    assert len(contracts) == len(half)
    assert contracts_module.check_source_closures(contracts) == []
