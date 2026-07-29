"""Tests for the Firebase session the bridge borrows from the desktop app.

Two things make this module worth testing hard despite its size. It is the only
place the bridge holds long-lived credentials, so anything that leaks token
material into a log or an exception message is a real incident. And it is the
first thing that runs on every request path, so a failure here must arrive as
an actionable `AuthError` -- "sign in to the desktop app once" -- rather than as
whatever exception happened to escape.

Nothing here touches the Keychain (`conftest._no_keychain` stubs the dump) or
the network (`conftest._no_network`); Firebase is a `MockTransport`.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import omi_auth  # noqa: E402
from conftest import install_mock_transport  # noqa: E402
from omi_auth import AuthError, OmiAuth, _parse_session_file, _session_file  # noqa: E402

REFRESH_TOKEN = 'AMf-vBz-REFRESH-TOKEN-SECRET-0123456789'
ID_TOKEN = 'eyJhbGciOiJSUzI1NiIsImtpZCI6IklEIFRPS0VOIn0.payload.signature'


def dump_shape(**values) -> str:
    """The `{key: {type, value}}` layout `omi-auth-dump.sh` writes."""
    return json.dumps({key: {'type': 'string', 'value': value} for key, value in values.items()})


@pytest.fixture
def session_file(tmp_path, monkeypatch):
    path = tmp_path / 'desktop-auth.json'
    monkeypatch.setenv('OMI_SESSION_FILE', str(path))
    return path


def firebase_ok(**overrides):
    body = {
        'id_token': ID_TOKEN,
        'refresh_token': REFRESH_TOKEN,
        'expires_in': '3600',
        'user_id': 'firebase-uid-1',
        **overrides,
    }

    def handler(request):
        return httpx.Response(200, json=body)

    return handler


# --------------------------------------------------------------------------
# _parse_session_file
# --------------------------------------------------------------------------


def test_the_dump_shape_is_flattened(tmp_path):
    path = tmp_path / 'auth.json'
    path.write_text(dump_shape(auth_idToken=ID_TOKEN, auth_refreshToken=REFRESH_TOKEN, auth_userId='uid-1'))
    assert _parse_session_file(path) == {
        'auth_idToken': ID_TOKEN,
        'auth_refreshToken': REFRESH_TOKEN,
        'auth_userId': 'uid-1',
    }


def test_plain_values_pass_through_unwrapped(tmp_path):
    path = tmp_path / 'auth.json'
    path.write_text(json.dumps({'auth_refreshToken': REFRESH_TOKEN, 'count': 3, 'flag': True}))
    assert _parse_session_file(path) == {'auth_refreshToken': REFRESH_TOKEN, 'count': 3, 'flag': True}


def test_a_wrapper_without_a_value_key_becomes_none(tmp_path):
    path = tmp_path / 'auth.json'
    path.write_text(json.dumps({'auth_refreshToken': {'type': 'string'}}))
    assert _parse_session_file(path) == {'auth_refreshToken': None}


def test_an_empty_object_is_an_empty_mapping(tmp_path):
    path = tmp_path / 'auth.json'
    path.write_text('{}')
    assert _parse_session_file(path) == {}


def test_a_missing_file_is_none_not_an_exception(tmp_path):
    assert _parse_session_file(tmp_path / 'nope.json') is None


def test_a_directory_is_none_not_an_exception(tmp_path):
    assert _parse_session_file(tmp_path) is None


@pytest.mark.parametrize('raw', ['', 'not json', '{"unterminated', '\x00\x01'])
def test_unparseable_content_is_none(tmp_path, raw):
    path = tmp_path / 'auth.json'
    path.write_text(raw)
    assert _parse_session_file(path) is None


@pytest.mark.parametrize('raw', ['[1, 2, 3]', '"a bare string"', 'null', '42'])
def test_valid_json_that_is_not_an_object_is_none(tmp_path, raw):
    """Regression: `.items()` was called unconditionally, so a session file
    pointed at the wrong JSON raised AttributeError instead of degrading into
    the actionable "no signed-in session" error.
    """
    path = tmp_path / 'auth.json'
    path.write_text(raw)
    assert _parse_session_file(path) is None


def test_session_file_honours_the_override_and_expands_home(monkeypatch):
    monkeypatch.setenv('OMI_SESSION_FILE', '~/custom/auth.json')
    assert _session_file() == Path.home() / 'custom' / 'auth.json'


# --------------------------------------------------------------------------
# _load_session
# --------------------------------------------------------------------------


def test_a_session_file_with_a_refresh_token_is_loaded(session_file):
    session_file.write_text(
        dump_shape(auth_idToken=ID_TOKEN, auth_refreshToken=REFRESH_TOKEN, auth_tokenUserId='uid-7')
    )
    session = OmiAuth()._load_session()
    assert session.refresh_token == REFRESH_TOKEN
    assert session.id_token == ID_TOKEN
    assert session.uid == 'uid-7'


def test_the_stored_expiry_is_ignored_so_a_stale_dump_cannot_401_mid_conversation(session_file):
    session_file.write_text(
        json.dumps(
            {
                'auth_refreshToken': {'type': 'string', 'value': REFRESH_TOKEN},
                'auth_tokenExpiry': {'type': 'double', 'value': time.time() + 86400},
            }
        )
    )
    assert OmiAuth()._load_session().expires_at == 0.0


def test_uid_falls_back_to_the_legacy_key(session_file):
    session_file.write_text(dump_shape(auth_refreshToken=REFRESH_TOKEN, auth_userId='legacy-uid'))
    assert OmiAuth()._load_session().uid == 'legacy-uid'


def test_a_session_without_an_id_token_still_loads(session_file):
    """Only the refresh token matters -- the ID token is minted on first use."""
    session_file.write_text(dump_shape(auth_refreshToken=REFRESH_TOKEN))
    session = OmiAuth()._load_session()
    assert session.id_token == ''
    assert session.refresh_token == REFRESH_TOKEN


def test_no_session_anywhere_raises_an_actionable_auth_error(session_file):
    with pytest.raises(AuthError) as excinfo:
        OmiAuth()._load_session()

    message = str(excinfo.value)
    assert 'com.omi.desktop-dev' in message, 'the operator needs to know what was tried'
    assert str(session_file) in message
    assert 'Sign in to the Omi macOS app' in message


def test_a_session_file_without_a_refresh_token_triggers_a_re_export(session_file, monkeypatch):
    """A dump that predates a bundle-id change is present but useless."""
    session_file.write_text(dump_shape(auth_idToken=ID_TOKEN))
    dumped = []

    def fake_dump(bundle_id, out_path):
        dumped.append(bundle_id)
        Path(out_path).write_text(dump_shape(auth_refreshToken=REFRESH_TOKEN, auth_userId='re-exported'))
        return True

    monkeypatch.setattr(omi_auth, '_run_dump', fake_dump)
    session = OmiAuth()._load_session()

    assert dumped == ['com.omi.desktop-dev']
    assert session.uid == 're-exported'


def test_a_dump_that_succeeds_but_yields_nothing_useful_still_raises(session_file, monkeypatch):
    def fake_dump(bundle_id, out_path):
        Path(out_path).write_text(dump_shape(auth_idToken=ID_TOKEN))
        return True

    monkeypatch.setattr(omi_auth, '_run_dump', fake_dump)
    with pytest.raises(AuthError):
        OmiAuth()._load_session()


def test_bundles_are_tried_in_order_until_one_works(session_file, monkeypatch):
    tried = []

    def fake_dump(bundle_id, out_path):
        tried.append(bundle_id)
        if bundle_id != 'com.omi.second':
            return False
        Path(out_path).write_text(dump_shape(auth_refreshToken=REFRESH_TOKEN))
        return True

    monkeypatch.setattr(omi_auth, '_run_dump', fake_dump)
    OmiAuth(bundles=('com.omi.first', 'com.omi.second', 'com.omi.third'))._load_session()
    assert tried == ['com.omi.first', 'com.omi.second']


def test_the_source_bundle_env_var_overrides_the_defaults(monkeypatch):
    monkeypatch.setenv('OMI_SOURCE_BUNDLE', 'com.omi.omi-even-test')
    assert OmiAuth(bundles=('com.omi.ignored',))._bundles == ('com.omi.omi-even-test',)


def test_the_prod_bundle_is_not_tried_by_default():
    """Reading the prod entry can sit behind a Keychain ACL dialog that blocks
    indefinitely, and it is the user's real installed app.
    """
    assert OmiAuth()._bundles == ('com.omi.desktop-dev',)
    assert 'com.omi.computer-macos' not in OmiAuth()._bundles


# --------------------------------------------------------------------------
# _refresh
# --------------------------------------------------------------------------


@pytest.fixture
def loaded_auth(session_file):
    session_file.write_text(dump_shape(auth_refreshToken=REFRESH_TOKEN, auth_userId='uid-file'))
    return OmiAuth()


@pytest.mark.asyncio
async def test_refresh_exchanges_the_refresh_token_for_an_id_token(loaded_auth, monkeypatch):
    requests = install_mock_transport(monkeypatch, firebase_ok())
    token = await loaded_auth.id_token()

    assert token == ID_TOKEN
    assert len(requests) == 1
    request = requests[0]
    assert request.method == 'POST'
    assert request.url.host == 'securetoken.googleapis.com'
    assert request.headers['content-type'] == 'application/x-www-form-urlencoded'

    body = request.content.decode()
    assert 'grant_type=refresh_token' in body
    # In the body, never the query string: URLs end up in proxy access logs.
    assert REFRESH_TOKEN.replace('-', '%2D') in body or REFRESH_TOKEN in body
    assert REFRESH_TOKEN not in str(request.url)


@pytest.mark.asyncio
async def test_a_rotated_refresh_token_replaces_the_old_one(loaded_auth, monkeypatch):
    install_mock_transport(monkeypatch, firebase_ok(refresh_token='AMf-vBz-ROTATED'))
    await loaded_auth.id_token()
    assert loaded_auth._session.refresh_token == 'AMf-vBz-ROTATED'


@pytest.mark.asyncio
async def test_an_absent_refresh_token_keeps_the_current_one(loaded_auth, monkeypatch):
    def handler(request):
        return httpx.Response(200, json={'id_token': ID_TOKEN, 'expires_in': '3600'})

    install_mock_transport(monkeypatch, handler)
    await loaded_auth.id_token()
    assert loaded_auth._session.refresh_token == REFRESH_TOKEN


@pytest.mark.asyncio
async def test_the_expiry_comes_from_the_server_quoted_lifetime(loaded_auth, monkeypatch):
    install_mock_transport(monkeypatch, firebase_ok(expires_in='1800'))
    before = time.time()
    await loaded_auth.id_token()
    assert before + 1800 <= loaded_auth._session.expires_at <= time.time() + 1800


@pytest.mark.asyncio
async def test_a_missing_expiry_defaults_to_an_hour(loaded_auth, monkeypatch):
    def handler(request):
        return httpx.Response(200, json={'id_token': ID_TOKEN})

    install_mock_transport(monkeypatch, handler)
    await loaded_auth.id_token()
    assert loaded_auth._session.expires_at >= time.time() + 3500


@pytest.mark.asyncio
async def test_the_uid_comes_from_the_refresh_response(loaded_auth, monkeypatch):
    install_mock_transport(monkeypatch, firebase_ok(user_id='firebase-uid-9'))
    assert await loaded_auth.uid() == 'firebase-uid-9'


@pytest.mark.asyncio
async def test_the_uid_falls_back_to_the_file_when_firebase_omits_it(loaded_auth, monkeypatch):
    def handler(request):
        return httpx.Response(200, json={'id_token': ID_TOKEN, 'expires_in': '3600'})

    install_mock_transport(monkeypatch, handler)
    assert await loaded_auth.uid() == 'uid-file'


@pytest.mark.asyncio
async def test_a_refresh_failure_raises_an_actionable_auth_error(loaded_auth, monkeypatch):
    def handler(request):
        return httpx.Response(400, json={'error': {'message': 'TOKEN_EXPIRED', 'code': 400}})

    install_mock_transport(monkeypatch, handler)
    with pytest.raises(AuthError) as excinfo:
        await loaded_auth.id_token()

    message = str(excinfo.value)
    assert '400' in message
    assert 'TOKEN_EXPIRED' in message
    assert 'sign in again' in message


@pytest.mark.asyncio
async def test_a_refresh_failure_never_echoes_token_material(loaded_auth, monkeypatch):
    """Firebase error bodies can contain the credential that was rejected."""

    def handler(request):
        return httpx.Response(
            400,
            json={'error': {'message': 'INVALID_REFRESH_TOKEN', 'token': REFRESH_TOKEN}, 'raw': REFRESH_TOKEN},
        )

    install_mock_transport(monkeypatch, handler)
    with pytest.raises(AuthError) as excinfo:
        await loaded_auth.id_token()

    assert REFRESH_TOKEN not in str(excinfo.value)
    assert REFRESH_TOKEN not in repr(excinfo.value)


@pytest.mark.asyncio
async def test_a_non_json_error_body_still_raises_an_auth_error(loaded_auth, monkeypatch):
    def handler(request):
        return httpx.Response(502, text='<html>Bad Gateway</html>')

    install_mock_transport(monkeypatch, handler)
    with pytest.raises(AuthError, match='502'):
        await loaded_auth.id_token()


# --------------------------------------------------------------------------
# Caching, margins and concurrency
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_valid_token_is_reused_rather_than_re_minted(loaded_auth, monkeypatch):
    requests = install_mock_transport(monkeypatch, firebase_ok())
    for _ in range(5):
        assert await loaded_auth.id_token() == ID_TOKEN
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_an_expired_token_is_refreshed(loaded_auth, monkeypatch):
    requests = install_mock_transport(monkeypatch, firebase_ok())
    await loaded_auth.id_token()
    loaded_auth._session.expires_at = time.time() - 1
    await loaded_auth.id_token()
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_a_token_inside_the_safety_margin_is_refreshed_early(loaded_auth, monkeypatch):
    """Refreshing exactly at expiry loses the race against clock skew and the
    round trip of the request the token is about to be used for.
    """
    requests = install_mock_transport(monkeypatch, firebase_ok())
    await loaded_auth.id_token()

    loaded_auth._session.expires_at = time.time() + omi_auth._REFRESH_MARGIN_SECONDS - 10
    await loaded_auth.id_token()
    assert len(requests) == 2

    loaded_auth._session.expires_at = time.time() + omi_auth._REFRESH_MARGIN_SECONDS + 60
    await loaded_auth.id_token()
    assert len(requests) == 2, 'a token outside the margin must not be re-minted'


@pytest.mark.asyncio
async def test_concurrent_callers_mint_exactly_one_token(loaded_auth, monkeypatch):
    """The three consumers of this bridge start at once; without the lock they
    each burn a refresh and the last one wins.
    """

    def handler(request):
        return httpx.Response(200, json={'id_token': ID_TOKEN, 'refresh_token': REFRESH_TOKEN, 'expires_in': '3600'})

    requests = install_mock_transport(monkeypatch, handler)
    tokens = await asyncio.gather(*(loaded_auth.id_token() for _ in range(10)))

    assert tokens == [ID_TOKEN] * 10
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_auth_header_is_a_bearer_header(loaded_auth, monkeypatch):
    install_mock_transport(monkeypatch, firebase_ok())
    assert await loaded_auth.auth_header() == {'Authorization': f'Bearer {ID_TOKEN}'}


@pytest.mark.asyncio
async def test_a_load_failure_surfaces_on_every_call(session_file, monkeypatch):
    install_mock_transport(monkeypatch, firebase_ok())
    auth = OmiAuth()
    for _ in range(2):
        with pytest.raises(AuthError):
            await auth.auth_header()


# --------------------------------------------------------------------------
# describe()
# --------------------------------------------------------------------------


def test_describe_before_any_session_is_loaded():
    assert OmiAuth().describe() == {'loaded': False}


@pytest.mark.asyncio
async def test_describe_reports_status_without_token_material(loaded_auth, monkeypatch):
    install_mock_transport(monkeypatch, firebase_ok())
    await loaded_auth.id_token()
    described = loaded_auth.describe()

    assert described['loaded'] is True
    assert described['uid'] == 'firebase-uid-1'
    assert 0 < described['expires_in'] <= 3600

    serialised = json.dumps(described)
    assert ID_TOKEN not in serialised
    assert REFRESH_TOKEN not in serialised
    assert 'eyJ' not in serialised, 'no JWT fragment may reach a health endpoint'


@pytest.mark.asyncio
async def test_describe_never_reports_a_negative_lifetime(loaded_auth, monkeypatch):
    install_mock_transport(monkeypatch, firebase_ok())
    await loaded_auth.id_token()
    loaded_auth._session.expires_at = time.time() - 10_000
    assert loaded_auth.describe()['expires_in'] == 0
