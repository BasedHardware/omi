import pytest

from desktop_backend import _cors_allowed_origins_from_env
from utils.env_loader import load_backend_env


def test_desktop_backend_cors_reads_allowlist_from_backend_env_file(tmp_path, monkeypatch):
    (tmp_path / '.env').write_text(
        'CORS_ALLOWED_ORIGINS=https://app.example, https://admin.example\n',
        encoding='utf-8',
    )
    monkeypatch.delenv('CORS_ALLOWED_ORIGINS', raising=False)
    monkeypatch.delenv('OMI_ENV_STAGE', raising=False)

    load_backend_env(tmp_path)

    assert _cors_allowed_origins_from_env() == ['https://app.example', 'https://admin.example']


def test_desktop_backend_cors_rejects_wildcard(monkeypatch):
    monkeypatch.setenv('CORS_ALLOWED_ORIGINS', 'https://app.example, *')

    with pytest.raises(RuntimeError, match='must not contain'):
        _cors_allowed_origins_from_env()
