from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = BACKEND_ROOT / 'scripts' / 'preflight-cloud-run-deploy.py'


def load_preflight():
    spec = importlib.util.spec_from_file_location('preflight_cloud_run_deploy', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
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
