"""Source-closure checks for the runtime image contracts, half A.

``test_runtime_image_contracts.py`` grew to ~183s of CI wall, dominated by
``check_source_closures`` staging and AST-walking every registered image
contract in one test. The walk is split over two files by parity of the
sorted contract name: every registered image is checked exactly once across
``...half_a.py`` and ``...half_b.py``, and a newly registered contract lands
in exactly one half by construction, so deleting either file loses real
coverage.
"""

import importlib.util
import json
from functools import lru_cache
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
SCRIPT_PATH = BACKEND_DIR / 'scripts' / 'runtime_image_contracts.py'
HALF_INDEX = 0


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


def _registered_half_names():
    names = sorted(image['name'] for image in json.loads((BACKEND_DIR / 'runtime_images.json').read_text())['images'])
    return [name for index, name in enumerate(names) if index % 2 == HALF_INDEX]


@pytest.fixture(scope='module')
def prepared_closures(contracts_module, tmp_path_factory, request):
    # Staging and parsing are immutable checkout setup. Each parametrized call
    # still runs the real layer and closure checks over the exact staged image.
    half = _half(contracts_module)
    assert half == _registered_half_names()
    trees = {}
    surfaces = {}
    prepared = {}
    # These helpers only read the immutable checkout/staged inputs. Cache their
    # real answers, not the closure verdict; the test still traverses every
    # reachable import and rejects any missing staged dependency.
    patch = pytest.MonkeyPatch()
    request.addfinalizer(patch.undo)
    for name in ('_module_path', '_find_module_source', '_module_or_namespace_exists', '_imported_modules'):
        patch.setattr(contracts_module, name, lru_cache(maxsize=None)(getattr(contracts_module, name)))
    for contract in contracts_module.load_contracts():
        if contract.name not in half:
            continue
        contracts_module.first_party_import_closure(contract, contract.entrypoints, _import_trees=trees)
        key = (
            contract.build_context,
            contract.workdir,
            tuple(contracts_module.final_stage_copy_instructions(contract.dockerfile, contract.target)),
        )
        if key not in surfaces:
            staged = tmp_path_factory.mktemp('runtime-surface')
            contracts_module.stage_runtime_sources(contract, staged)
            surfaces[key] = staged
        prepared[contract.name] = (contract, surfaces[key])
        contracts_module.source_closure_errors(contract, _import_trees=trees, _runtime_root=surfaces[key])
    return prepared, trees


@pytest.mark.parametrize('contract_name', _registered_half_names())
def test_registered_runtime_image_sources_are_closed(contracts_module, prepared_closures, contract_name):
    prepared, trees = prepared_closures
    contract, staged = prepared[contract_name]
    assert contracts_module.final_stage_layer_errors(contract) == []
    assert contracts_module.source_closure_errors(contract, _import_trees=trees, _runtime_root=staged) == []
