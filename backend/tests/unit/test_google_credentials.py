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


def test_customer_data_service_account_requires_project_id(monkeypatch, tmp_path):
    credentials_path = tmp_path / 'google-credentials.json'
    monkeypatch.setattr(google_credentials, 'RUNTIME_GOOGLE_CREDENTIALS_PATH', credentials_path)
    monkeypatch.setenv('SERVICE_ACCOUNT_JSON', '{"client_email": "unused@example.com"}')
    monkeypatch.delenv('GOOGLE_APPLICATION_CREDENTIALS', raising=False)

    with pytest.raises(RuntimeError, match='missing project_id'):
        google_credentials.customer_data_service_account()


def test_customer_data_service_account_returns_none_without_service_account_json(monkeypatch):
    monkeypatch.delenv('SERVICE_ACCOUNT_JSON', raising=False)
    monkeypatch.delenv('GOOGLE_APPLICATION_CREDENTIALS', raising=False)
    monkeypatch.delenv('OMI_CUSTOMER_DATA_PROJECT', raising=False)

    assert google_credentials.customer_data_service_account() is None


@requires_owner_only_permissions
def test_customer_data_service_account_pins_json_identity_and_project(monkeypatch, tmp_path):
    credentials_path = tmp_path / 'google-credentials.json'
    monkeypatch.setattr(google_credentials, 'RUNTIME_GOOGLE_CREDENTIALS_PATH', credentials_path)
    monkeypatch.setenv(
        'SERVICE_ACCOUNT_JSON',
        '{"type":"service_account","project_id":"based-hardware","client_email":"nik-164@based-hardware.iam.gserviceaccount.com"}',
    )
    # Host/compute project must not become the customer-data project.
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'based-hardware-dev')
    monkeypatch.setenv('GOOGLE_APPLICATION_CREDENTIALS', '/var/run/secrets/pack-wi.json')

    fake_credentials = object()

    def fake_from_info(info):
        assert info['project_id'] == 'based-hardware'
        assert info['client_email'] == 'nik-164@based-hardware.iam.gserviceaccount.com'
        return fake_credentials

    monkeypatch.setattr(
        'google.oauth2.service_account.Credentials.from_service_account_info',
        fake_from_info,
    )

    credentials, project_id = google_credentials.customer_data_service_account()

    assert project_id == 'based-hardware'
    assert credentials is fake_credentials
    assert os.environ['GOOGLE_APPLICATION_CREDENTIALS'] == str(credentials_path)


def test_customer_entitlement_service_account_reads_auth_file_without_adc(monkeypatch, tmp_path):
    credentials_path = tmp_path / 'firebase-auth.json'
    credentials_path.write_text(
        '{"type":"service_account","project_id":"based-hardware","client_email":"nik-164@based-hardware.iam.gserviceaccount.com"}',
        encoding='utf-8',
    )
    monkeypatch.delenv('SERVICE_ACCOUNT_JSON', raising=False)
    monkeypatch.delenv('GOOGLE_APPLICATION_CREDENTIALS', raising=False)
    monkeypatch.setenv('FIREBASE_AUTH_CREDENTIALS_PATH', str(credentials_path))
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'based-hardware-dev')
    monkeypatch.delenv('OMI_CUSTOMER_DATA_PROJECT', raising=False)

    fake_credentials = object()

    def fake_from_info(info):
        assert info['project_id'] == 'based-hardware'
        return fake_credentials

    monkeypatch.setattr(
        'google.oauth2.service_account.Credentials.from_service_account_info',
        fake_from_info,
    )

    credentials, project_id = google_credentials.customer_entitlement_service_account()

    assert project_id == 'based-hardware'
    assert credentials is fake_credentials
    assert 'GOOGLE_APPLICATION_CREDENTIALS' not in os.environ
    assert google_credentials.customer_data_service_account() is None


def test_customer_data_pin_selects_adc_without_service_account_json(monkeypatch):
    monkeypatch.delenv('SERVICE_ACCOUNT_JSON', raising=False)
    monkeypatch.delenv('GOOGLE_APPLICATION_CREDENTIALS', raising=False)
    monkeypatch.setenv('OMI_CUSTOMER_DATA_PROJECT', ' based-hardware ')
    # The compute project must not become the customer-data project.
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'based-hardware-dev')

    assert google_credentials.customer_data_service_account() == (None, 'based-hardware')
    assert google_credentials.customer_entitlement_service_account() == (None, 'based-hardware')


@requires_owner_only_permissions
def test_service_account_json_wins_over_customer_data_pin(monkeypatch, tmp_path):
    monkeypatch.setattr(google_credentials, 'RUNTIME_GOOGLE_CREDENTIALS_PATH', tmp_path / 'google-credentials.json')
    monkeypatch.setenv('SERVICE_ACCOUNT_JSON', '{"type":"service_account","project_id":"json-project"}')
    monkeypatch.delenv('GOOGLE_APPLICATION_CREDENTIALS', raising=False)
    monkeypatch.setenv('OMI_CUSTOMER_DATA_PROJECT', 'pinned-project')
    fake_credentials = object()
    monkeypatch.setattr(
        'google.oauth2.service_account.Credentials.from_service_account_info',
        lambda _info: fake_credentials,
    )

    assert google_credentials.customer_data_service_account() == (fake_credentials, 'json-project')


def test_keyless_entitlement_pins_adc_to_the_data_plane_project(monkeypatch):
    for name in ('SERVICE_ACCOUNT_JSON', 'GOOGLE_APPLICATION_CREDENTIALS', 'FIREBASE_AUTH_CREDENTIALS_PATH'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv('OMI_CUSTOMER_DATA_PROJECT', raising=False)
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'based-hardware-dev')
    monkeypatch.setenv('OMI_FIRESTORE_DATA_PLANE_PROJECT', 'based-hardware')

    assert google_credentials.customer_data_service_account() is None
    assert google_credentials.customer_entitlement_service_account() == (None, 'based-hardware')


def test_no_pin_and_no_key_keeps_bare_adc(monkeypatch):
    for name in (
        'SERVICE_ACCOUNT_JSON',
        'GOOGLE_APPLICATION_CREDENTIALS',
        'FIREBASE_AUTH_CREDENTIALS_PATH',
        'OMI_CUSTOMER_DATA_PROJECT',
        'OMI_FIRESTORE_DATA_PLANE_PROJECT',
    ):
        monkeypatch.delenv(name, raising=False)

    assert google_credentials.customer_data_service_account() is None
    assert google_credentials.customer_entitlement_service_account() is None
