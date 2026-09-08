import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'rebuild_workstream_association_index.py'


def _load_script():
    spec = importlib.util.spec_from_file_location('rebuild_workstream_association_index_under_test', SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCRIPT_MODULE = _load_script()


def test_all_users_rejects_inventory_that_would_be_truncated(monkeypatch):
    module = SCRIPT_MODULE
    monkeypatch.setenv(
        'WORKSTREAM_ASSOCIATION_UID_INVENTORY',
        ','.join(f'user-{index}' for index in range(module.MAX_INDEX_REBUILD_UIDS + 1)),
    )
    monkeypatch.setattr(sys, 'argv', ['rebuild_workstream_association_index.py', '--all-users'])

    with pytest.raises(SystemExit, match='exceeding the per-run bound'):
        module.main()
