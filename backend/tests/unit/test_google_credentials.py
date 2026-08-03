import os

import pytest

from database import google_credentials

requires_owner_only_permissions = pytest.mark.skipif(
    not callable(getattr(os, 'fchmod', None)), reason='owner-only descriptor modes require POSIX fchmod'
)


@requires_owner_only_permissions
def test_service_account_json_materializes_credentials_file(monkeypatch, tmp_path):
    credentials_path = tmp_path / 'google-credentials.json'
    monkeypatch.setattr(google_credentials, 'RUNTIME_GOOGLE_CREDENTIALS_PATH', credentials_path)
    monkeypatch.setenv('SERVICE_ACCOUNT_JSON', '{"client_email": "unused@example.com"}')
    monkeypatch.delenv('GOOGLE_APPLICATION_CREDENTIALS', raising=False)

    google_credentials.prepare_google_credentials()

    assert os.environ['GOOGLE_APPLICATION_CREDENTIALS'] == str(credentials_path)
    assert credentials_path.exists()
    assert credentials_path.stat().st_mode & 0o777 == 0o600


@requires_owner_only_permissions
def test_google_application_credentials_json_materializes_credentials_file(monkeypatch, tmp_path):
    credentials_path = tmp_path / 'google-credentials.json'
    monkeypatch.setattr(google_credentials, 'RUNTIME_GOOGLE_CREDENTIALS_PATH', credentials_path)
    monkeypatch.delenv('SERVICE_ACCOUNT_JSON', raising=False)
    monkeypatch.setenv('GOOGLE_APPLICATION_CREDENTIALS', '{"client_email": "unused@example.com"}')

    google_credentials.prepare_google_credentials()

    assert os.environ['GOOGLE_APPLICATION_CREDENTIALS'] == str(credentials_path)
    assert credentials_path.exists()


def test_inline_credentials_fail_closed_when_owner_only_permissions_are_unavailable(monkeypatch, tmp_path):
    credentials_path = tmp_path / 'google-credentials.json'
    monkeypatch.setattr(google_credentials, 'RUNTIME_GOOGLE_CREDENTIALS_PATH', credentials_path)
    monkeypatch.setenv('SERVICE_ACCOUNT_JSON', '{"client_email": "unused@example.com"}')
    monkeypatch.delenv('GOOGLE_APPLICATION_CREDENTIALS', raising=False)
    monkeypatch.delattr(google_credentials.os, 'fchmod', raising=False)

    with pytest.raises(RuntimeError, match='require owner-only file permissions'):
        google_credentials.prepare_google_credentials()

    assert not credentials_path.exists()
    assert list(tmp_path.iterdir()) == []


def test_missing_google_application_credentials_path_fails_fast(monkeypatch, tmp_path):
    missing_path = tmp_path / 'missing-google-credentials.json'
    monkeypatch.delenv('SERVICE_ACCOUNT_JSON', raising=False)
    monkeypatch.setenv('GOOGLE_APPLICATION_CREDENTIALS', str(missing_path))

    with pytest.raises(RuntimeError, match='points to missing file'):
        google_credentials.prepare_google_credentials()


@requires_owner_only_permissions
def test_existing_credentials_file_is_replaced_with_private_permissions(monkeypatch, tmp_path):
    credentials_path = tmp_path / 'google-credentials.json'
    credentials_path.write_text('old credentials', encoding='utf-8')
    credentials_path.chmod(0o644)
    monkeypatch.setattr(google_credentials, 'RUNTIME_GOOGLE_CREDENTIALS_PATH', credentials_path)
    monkeypatch.setenv('SERVICE_ACCOUNT_JSON', '{"client_email": "unused@example.com"}')
    monkeypatch.delenv('GOOGLE_APPLICATION_CREDENTIALS', raising=False)

    google_credentials.prepare_google_credentials()

    assert credentials_path.read_text(encoding='utf-8') == '{"client_email": "unused@example.com"}'
    assert credentials_path.stat().st_mode & 0o777 == 0o600
