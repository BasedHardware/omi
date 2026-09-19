import copy
import hashlib

import pytest

from utils.external_oauth.admission import AdmissionDenied, DeploymentFacts, admit_connector
from utils.external_oauth.contracts import Connector
from utils.external_oauth.scopes import GRANT_FAMILIES, SCOPE_REGISTRY_REVISION, scope_digest


def _entry(connector: Connector) -> dict:
    return {
        'enabled': True,
        'project_alias': GRANT_FAMILIES[connector].client_alias,
        'client_alias': GRANT_FAMILIES[connector].client_alias,
        'project_number_sha256': hashlib.sha256(b'1234').hexdigest(),
        'client_id_sha256': hashlib.sha256(b'client-id').hexdigest(),
        'redirect_uri': f'https://api.omi.me/v2/external-oauth/{connector.value}/callback',
        'scope_digest': scope_digest(GRANT_FAMILIES[connector].scopes),
        'verification': {'approved': True, 'evidence_id': 'verification-123', 'valid_through': '2027-01-01'},
        'casa': {'approved': True, 'evidence_id': 'casa-123', 'valid_through': '2027-01-01'},
    }


def _facts(connector: Connector) -> DeploymentFacts:
    return DeploymentFacts(
        environment='production',
        project_number='1234',
        oauth_client_id='client-id',
        redirect_uri=f'https://api.omi.me/v2/external-oauth/{connector.value}/callback',
    )


def _manifest() -> dict:
    return {
        'schema_version': 1,
        'scope_registry_revision': SCOPE_REGISTRY_REVISION,
        'connectors': {connector.value: _entry(connector) for connector in Connector},
    }


@pytest.mark.parametrize('connector', list(Connector))
def test_exact_current_evidence_admits_connector(connector):
    admitted = admit_connector(_manifest(), connector, _facts(connector), now_iso_date='2026-08-30')
    assert admitted.connector == connector


@pytest.mark.parametrize(
    ('field', 'value'),
    [
        ('enabled', False),
        ('project_number_sha256', 'wrong'),
        ('client_id_sha256', 'wrong'),
        ('redirect_uri', 'https://attacker.invalid/callback'),
        ('scope_digest', 'wrong'),
        ('client_alias', 'wrong'),
        ('project_alias', 'wrong'),
    ],
)
def test_identity_scope_and_kill_switch_mismatches_fail_closed(field, value):
    manifest = _manifest()
    manifest['connectors']['gmail'][field] = value
    with pytest.raises(AdmissionDenied):
        admit_connector(manifest, Connector.GMAIL, _facts(Connector.GMAIL), now_iso_date='2026-08-30')


def test_gmail_requires_current_casa_in_addition_to_verification():
    manifest = _manifest()
    manifest['connectors']['gmail']['casa']['approved'] = False
    with pytest.raises(AdmissionDenied, match='CASA'):
        admit_connector(manifest, Connector.GMAIL, _facts(Connector.GMAIL), now_iso_date='2026-08-30')


def test_calendar_does_not_require_casa_but_requires_verification():
    manifest = _manifest()
    del manifest['connectors']['google_calendar']['casa']
    admit_connector(manifest, Connector.GOOGLE_CALENDAR, _facts(Connector.GOOGLE_CALENDAR), now_iso_date='2026-08-30')
    manifest['connectors']['google_calendar']['verification']['valid_through'] = '2026-08-29'
    with pytest.raises(AdmissionDenied, match='stale'):
        admit_connector(
            manifest, Connector.GOOGLE_CALENDAR, _facts(Connector.GOOGLE_CALENDAR), now_iso_date='2026-08-30'
        )
