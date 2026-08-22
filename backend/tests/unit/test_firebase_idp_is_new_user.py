"""``exchange_idp_credential`` must carry ``isNewUser`` out of signInWithIdp, not just the uid.

The port used to return a bare uid string. Upstream's referral entitlement is granted only on a
genuinely first sign-in and reads that flag straight off the Firebase response, so a port that dropped
it would have made the trial ungrantable through the neutral path — and reconstructing it caller-side
is not the same question ("we have no user document" would hand a trial to an existing user whose
document went missing).

The flag is read as ``is True`` rather than truthily on purpose: signInWithIdp returns a real boolean,
so anything else — absent, null, the string "true" from a future wire change — means "this response
does not say so", and the safe reading of that is NOT new. A trial not granted is a support ticket; one
granted twice is a payout, and the second grant also RESTARTS the 30-day window.
"""

import httpx
import pytest

from utils.auth.adapters.firebase import FirebaseAuthProvider


class _Resp:
    status_code = 200

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


def _exchange(monkeypatch, body):
    monkeypatch.setenv('FIREBASE_API_KEY', 'test-key')
    monkeypatch.setattr(httpx, 'post', lambda *_a, **_kw: _Resp(body))
    return FirebaseAuthProvider().exchange_idp_credential('google', id_token='tok')


def test_a_first_sign_in_reports_a_new_user(monkeypatch):
    identity = _exchange(monkeypatch, {'localId': 'uid-abc', 'isNewUser': True})

    assert identity.uid == 'uid-abc'
    assert identity.is_new_user is True


def test_a_returning_sign_in_does_not(monkeypatch):
    assert _exchange(monkeypatch, {'localId': 'uid-abc', 'isNewUser': False}).is_new_user is False


@pytest.mark.parametrize(
    'flag',
    [
        pytest.param({}, id='absent'),
        pytest.param({'isNewUser': None}, id='null'),
        pytest.param({'isNewUser': 'true'}, id='the string true'),
        pytest.param({'isNewUser': 1}, id='the integer one'),
    ],
)
def test_anything_that_is_not_the_boolean_true_reads_as_not_new(monkeypatch, flag):
    """The conservative direction, and the only one a caller can afford: every one of these is truthy
    or absent, and a truthiness test would grant a paid trial on three of the four."""
    assert _exchange(monkeypatch, {'localId': 'uid-abc', **flag}).is_new_user is False


def test_a_missing_uid_is_still_the_error_it_was(monkeypatch):
    """The flag is additive: an exchange with no uid must keep failing, not return an identity with an
    empty one."""
    from utils.auth import errors

    with pytest.raises(errors.AuthError, match='no uid returned'):
        _exchange(monkeypatch, {'isNewUser': True})
