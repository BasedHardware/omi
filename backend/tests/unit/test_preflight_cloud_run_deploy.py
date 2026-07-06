from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

from tests.unit.memory_import_isolation import restore_sys_modules, snapshot_sys_modules

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = BACKEND_ROOT / 'scripts' / 'preflight-cloud-run-deploy.py'
PREFLIGHT_MODULE_NAMES = (
    'preflight_cloud_run_deploy',
    'render_backend_runtime_env',
    'repair_cloud_run_traffic',
)


def load_preflight():
    saved = snapshot_sys_modules(PREFLIGHT_MODULE_NAMES)
    spec = importlib.util.spec_from_file_location('preflight_cloud_run_deploy', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    restore_sys_modules(saved)
    return module


def test_check_rendered_secrets_reports_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    preflight = load_preflight()
    monkeypatch.setattr(preflight, '_secret_exists', lambda **kwargs: False)

    missing = preflight.check_rendered_secrets(
        env='prod',
        manifest_path=BACKEND_ROOT / 'deploy/runtime_env.yaml',
        project='based-hardware',
    )

    secret_names = {item.secret_name for item in missing}
    assert 'ENCRYPTION_SECRET' in secret_names
    assert 'GOOGLE_CLIENT_ID' in secret_names


def test_check_rendered_secrets_passes_when_secrets_exist(monkeypatch: pytest.MonkeyPatch) -> None:
    preflight = load_preflight()
    monkeypatch.setattr(preflight, '_secret_exists', lambda **kwargs: True)

    missing = preflight.check_rendered_secrets(
        env='prod',
        manifest_path=BACKEND_ROOT / 'deploy/runtime_env.yaml',
        project='based-hardware',
    )

    assert missing == []


def test_parse_revision_targets_rejects_blank_values() -> None:
    preflight = load_preflight()

    with pytest.raises(ValueError, match='non-empty SERVICE and REVISION'):
        preflight._parse_revision_targets(['backend='])


def test_parse_revision_targets_rejects_missing_equals() -> None:
    preflight = load_preflight()

    with pytest.raises(ValueError, match='SERVICE=REVISION'):
        preflight._parse_revision_targets(['backend'])
