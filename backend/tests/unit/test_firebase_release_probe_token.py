import importlib.util
import base64
import io
import json
import stat
import subprocess
import sys
import urllib.error
from pathlib import Path


def _load_module():
    backend = Path(__file__).resolve().parents[2]
    script_path = backend / 'scripts' / 'firebase_release_probe_token.py'
    spec = importlib.util.spec_from_file_location('firebase_release_probe_token', script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _id_token(*, aud='based-hardware', sub='omi-release-probe'):
    claims = {
        'aud': aud,
        'iss': f'https://securetoken.google.com/{aud}',
        'sub': sub,
    }
    encoded = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')
    return f'header.{encoded}.signature'


def test_mint_probe_token_uses_fixed_uid_short_lived_custom_claims_and_discards_refresh(monkeypatch):
    module = _load_module()
    commands = []
    requests = []

    def fake_run(args, *, stage):
        commands.append((args, stage))
        if stage == 'secret_access':
            return 'firebase-api-key-that-must-not-leak'
        if stage == 'service_account':
            return 'deployer@omi-prod.iam.gserviceaccount.com'
        return 'gcp-access-token-that-must-not-leak'

    def fake_request(url, *, body, access_token, stage):
        requests.append((url, body, access_token, stage))
        if stage == 'custom_token_signing':
            return {'signedJwt': 'custom-token-that-must-not-leak'}
        return {
            'idToken': _id_token(),
            'refreshToken': 'refresh-token-that-must-not-leak',
        }

    monkeypatch.setattr(module, '_run_gcloud', fake_run)
    monkeypatch.setattr(module, '_request_json', fake_request)
    monkeypatch.setattr(module.time, 'time', lambda: 1_700_000_000)

    assert module.mint_probe_token('based-hardware-dev', 'based-hardware') == _id_token()
    assert commands[0][0][0:5] == ['gcloud', 'secrets', 'versions', 'access', 'latest']
    signing_url, signing_body, signing_access_token, signing_stage = requests[0]
    claims = json.loads(signing_body['payload'])
    assert signing_url.endswith(':signJwt')
    assert signing_access_token == 'gcp-access-token-that-must-not-leak'
    assert signing_stage == 'custom_token_signing'
    assert claims['uid'] == module.PROBE_UID
    assert claims['claims'] == {'release_probe': True}
    assert 'release_probe' not in claims
    assert claims['exp'] - claims['iat'] == module.CUSTOM_TOKEN_TTL_SECONDS
    exchange_url, exchange_body, exchange_access_token, exchange_stage = requests[1]
    assert 'firebase-api-key-that-must-not-leak' in exchange_url
    assert exchange_body == {'token': 'custom-token-that-must-not-leak', 'returnSecureToken': True}
    assert exchange_access_token is None
    assert exchange_stage == 'firebase_token_exchange'


def test_token_acquisition_failure_is_redacted_and_does_not_create_output(monkeypatch, tmp_path, capsys):
    module = _load_module()
    output = tmp_path / 'probe-token'
    monkeypatch.setattr(
        module,
        'mint_probe_token',
        lambda _secret_project, _firebase_project, **_kwargs: (_ for _ in ()).throw(
            module.ProbeTokenError('secret_access')
        ),
    )

    exit_code = module.main(
        ['--secret-project', 'omi-prod', '--firebase-project', 'based-hardware', '--token-output', str(output)]
    )

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert report == {
        'suite': 'omi_firebase_release_probe_token',
        'stage': 'secret_access',
        'error_class': 'operation_failed',
        'status': 'FAIL',
    }
    assert not output.exists()


def test_firebase_auth_exchange_failure_is_redacted(monkeypatch):
    module = _load_module()
    monkeypatch.setattr(
        module,
        '_request_json',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(module.ProbeTokenError('firebase_token_exchange')),
    )

    try:
        module._exchange_custom_token('custom-token-that-must-not-leak', 'api-key-that-must-not-leak')
    except module.ProbeTokenError as error:
        assert error.stage == 'firebase_token_exchange'
    else:
        raise AssertionError('expected a redacted Firebase exchange failure')


def test_write_token_uses_owner_only_permissions(tmp_path):
    module = _load_module()
    output = tmp_path / 'probe-token'

    module.write_token(output, 'firebase-id-token-that-must-not-leak')

    assert output.read_text(encoding='utf-8') == 'firebase-id-token-that-must-not-leak'
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_mint_probe_token_rejects_a_token_for_a_different_firebase_auth_project(monkeypatch):
    module = _load_module()
    monkeypatch.setattr(module, '_access_secret', lambda _project: 'api-key-that-must-not-leak')
    monkeypatch.setattr(module, '_active_service_account', lambda: 'deployer@omi-prod.iam.gserviceaccount.com')
    monkeypatch.setattr(module, '_access_token', lambda: 'access-token-that-must-not-leak')
    monkeypatch.setattr(module, '_signed_custom_token', lambda _account, _token: 'custom-token-that-must-not-leak')
    monkeypatch.setattr(module, '_exchange_custom_token', lambda _custom, _key: _id_token(aud='wrong-project'))

    try:
        module.mint_probe_token('based-hardware-dev', 'based-hardware')
    except module.ProbeTokenError as error:
        assert error.stage == 'firebase_token_claims'
    else:
        raise AssertionError('expected Firebase auth-project mismatch')


def test_local_signer_uses_matching_service_account_without_remote_iam(monkeypatch, tmp_path):
    module = _load_module()
    credentials = tmp_path / 'firebase-signer.json'
    credentials.write_text(
        json.dumps(
            {
                'type': 'service_account',
                'project_id': 'based-hardware',
                'private_key_id': 'fixed-key-id',
                'private_key': '-----BEGIN PRIVATE KEY-----\nnot-a-real-key\n-----END PRIVATE KEY-----\n',
                'client_email': 'firebase-probe@based-hardware.iam.gserviceaccount.com',
            }
        ),
        encoding='utf-8',
    )
    credentials.chmod(0o600)
    monkeypatch.setattr(
        module.subprocess,
        'run',
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args, returncode=0, stdout=b'signature', stderr=b''),
    )
    monkeypatch.setattr(module.time, 'time', lambda: 1_700_000_000)

    token = module._signed_custom_token_locally(credentials, 'based-hardware')
    header_part, claims_part, signature_part = token.split('.')
    header = json.loads(base64.urlsafe_b64decode(header_part + '=' * (-len(header_part) % 4)))
    claims = json.loads(base64.urlsafe_b64decode(claims_part + '=' * (-len(claims_part) % 4)))

    assert header == {'alg': 'RS256', 'kid': 'fixed-key-id', 'typ': 'JWT'}
    assert claims['iss'] == 'firebase-probe@based-hardware.iam.gserviceaccount.com'
    assert claims['sub'] == claims['iss']
    assert claims['uid'] == module.PROBE_UID
    assert claims['claims'] == {'release_probe': True}
    assert claims['exp'] - claims['iat'] == module.CUSTOM_TOKEN_TTL_SECONDS
    assert base64.urlsafe_b64decode(signature_part + '=' * (-len(signature_part) % 4)) == b'signature'


def test_local_signer_rejects_cross_project_credentials_before_signing(monkeypatch, tmp_path):
    module = _load_module()
    credentials = tmp_path / 'firebase-signer.json'
    credentials.write_text(
        json.dumps(
            {
                'type': 'service_account',
                'project_id': 'based-hardware-dev',
                'private_key_id': 'fixed-key-id',
                'private_key': '-----BEGIN PRIVATE KEY-----\nnot-a-real-key\n-----END PRIVATE KEY-----\n',
                'client_email': 'firebase-probe@based-hardware-dev.iam.gserviceaccount.com',
            }
        ),
        encoding='utf-8',
    )
    credentials.chmod(0o600)
    monkeypatch.setattr(
        module.subprocess,
        'run',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError('openssl must not run')),
    )

    try:
        module._signed_custom_token_locally(credentials, 'based-hardware')
    except module.ProbeTokenError as error:
        assert error.stage == 'signer_credentials'
        assert error.error_class == 'project_mismatch'
    else:
        raise AssertionError('expected signer project mismatch')


def test_remote_signing_permission_denial_has_bounded_classification(monkeypatch):
    module = _load_module()
    upstream_body = io.BytesIO(b'credential and request details that must not be read or printed')
    monkeypatch.setattr(
        module.urllib.request,
        'urlopen',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            urllib.error.HTTPError('https://iamcredentials.googleapis.com', 403, 'forbidden', {}, upstream_body)
        ),
    )

    try:
        module._request_json(
            'https://iamcredentials.googleapis.com',
            body={'payload': 'must-not-leak'},
            access_token='must-not-leak',
            stage='custom_token_signing',
        )
    except module.ProbeTokenError as error:
        assert error.stage == 'custom_token_signing'
        assert error.error_class == 'permission_denied'
        assert upstream_body.tell() == 0
    else:
        raise AssertionError('expected permission denial')


def test_mint_probe_token_prefers_explicit_local_signer(monkeypatch, tmp_path):
    module = _load_module()
    signer = tmp_path / 'signer.json'
    signer.write_text('{}', encoding='utf-8')
    calls = []
    monkeypatch.setattr(module, '_access_secret', lambda project: calls.append(('secret', project)) or 'api-key')
    monkeypatch.setattr(
        module,
        '_signed_custom_token_locally',
        lambda path, project: calls.append(('local_signer', path, project)) or 'custom-token',
    )
    monkeypatch.setattr(
        module,
        '_active_service_account',
        lambda: (_ for _ in ()).throw(AssertionError('active deploy identity must not be selected')),
    )
    monkeypatch.setattr(
        module, '_exchange_custom_token', lambda token, key: calls.append(('exchange', token, key)) or _id_token()
    )

    assert (
        module.mint_probe_token('based-hardware-dev', 'based-hardware', signer_credentials_file=signer) == _id_token()
    )
    assert calls == [
        ('secret', 'based-hardware-dev'),
        ('local_signer', signer, 'based-hardware'),
        ('exchange', 'custom-token', 'api-key'),
    ]
