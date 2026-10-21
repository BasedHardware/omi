import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[3] / 'migrations' / '008_external_oauth_legacy_disposition.py'


def _module():
    spec = importlib.util.spec_from_file_location('external_oauth_legacy_disposition', MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_plaintext_legacy_google_grant_requires_revoke_and_reconsent():
    module = _module()
    classified = module.classify_legacy_grant(
        'google_calendar',
        {
            'access_token': 'never-export-this',
            'refresh_token': 'never-export-this-either',
            'granted_scopes': [
                'https://www.googleapis.com/auth/calendar',
                'https://www.googleapis.com/auth/gmail.readonly',
            ],
        },
    )
    assert classified.disposition.value == 'revoke_and_reconsent'
    assert module.public_inventory_row(classified) == {
        'integration_key': 'google_calendar',
        'has_credential': True,
        'has_calendar_scope': True,
        'has_gmail_scope': True,
        'disposition': 'revoke_and_reconsent',
    }


def test_public_inventory_never_contains_secret_values():
    module = _module()
    row = module.public_inventory_row(module.classify_legacy_grant('google_calendar', {'refresh_token': 'top-secret'}))
    assert 'top-secret' not in repr(row)
    assert not set(row) & module.SECRET_FIELDS
