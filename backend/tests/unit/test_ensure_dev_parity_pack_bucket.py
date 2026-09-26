"""The dev parity-pack ensure step must not block a backend-listen deploy on a permission denial."""

import importlib.util
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'ensure_dev_parity_pack_bucket.py'


def _load():
    spec = importlib.util.spec_from_file_location('ensure_dev_parity_pack_bucket', SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _runner(stderr: str):
    def run(args, *, check=True):
        returncode = 1
        if check:
            raise subprocess.CalledProcessError(returncode, args, output='', stderr=stderr)
        return subprocess.CompletedProcess(args, returncode, stdout='', stderr=stderr)

    return run


def test_permission_denied_warns_and_exits_zero(monkeypatch, capsys):
    module = _load()
    monkeypatch.setattr(module, 'run', _runner('ERROR: (gcloud.iam.service-accounts.create) PERMISSION_DENIED: denied'))
    assert module.main() == 0
    out = capsys.readouterr().out
    assert '::warning title=Dev parity-pack bucket not ensured::' in out
    assert 'Ensured private dev parity-pack bucket' not in out


def test_other_gcloud_failure_still_fails(monkeypatch):
    module = _load()
    monkeypatch.setattr(module, 'run', _runner('ERROR: (gcloud) unexpected internal failure'))
    with pytest.raises(subprocess.CalledProcessError):
        module.main()


def test_public_bucket_still_refused(monkeypatch):
    module = _load()

    def run(args, *, check=True):
        stdout = '{"bindings": [{"members": ["allUsers"]}]}' if 'get-iam-policy' in args else ''
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr='')

    monkeypatch.setattr(module, 'run', run)
    with pytest.raises(SystemExit):
        module.main()
