"""signInWithIdp postBody must URL-encode its fields so opaque Google/Apple provider
tokens containing form-reserved characters (& = + space) do not corrupt the exchange
(cubic review PR 10887, backend/utils/auth/adapters/firebase.py)."""

from urllib.parse import parse_qs

import httpx

from utils.auth.adapters.firebase import FirebaseAuthProvider


class _Resp:
    status_code = 200

    def json(self):
        return {'localId': 'uid-abc'}


def test_idp_postbody_url_encodes_reserved_characters(monkeypatch):
    monkeypatch.setenv('FIREBASE_API_KEY', 'test-key')
    captured = {}

    def fake_post(url, *, json, timeout):
        captured['postBody'] = json['postBody']
        return _Resp()

    monkeypatch.setattr(httpx, 'post', fake_post)

    uid = FirebaseAuthProvider().exchange_idp_credential(
        'google', id_token='a+b&c=d e', access_token='x&y=z'
    )

    assert uid == 'uid-abc'
    # Round-trip: the raw reserved characters survive intact only if each field was encoded.
    parsed = parse_qs(captured['postBody'], keep_blank_values=True)
    assert parsed['id_token'] == ['a+b&c=d e']
    assert parsed['access_token'] == ['x&y=z']
    assert parsed['providerId'] == ['google.com']
