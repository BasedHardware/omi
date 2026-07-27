"""Shared fixtures and fakes for the omi <-> Even Realities bridge tests.

Everything here exists to keep the suite hermetic. The bridge's entire job is
talking to `api.omi.me` over HTTP and WebSocket and to the macOS Keychain via a
shell script, so each of those three escape hatches is closed by default:

* real DNS/TCP is blocked outright (`_no_network`), so a test that forgets to
  patch a transport fails loudly instead of silently reaching production;
* `omi_auth._run_dump` is stubbed, so no test can shell out to `security` and
  pop a Keychain ACL dialog on the developer's machine;
* `OMI_SESSION_FILE` points somewhere that does not exist, so the real desktop
  session is never read.

`OMI_EVEN_TOKEN` is set before anything imports `server`: the module reads it
exactly once at import time and otherwise mints a random token that no test
could ever authenticate with.
"""

import os
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

EVEN_TOKEN = 'test-shared-secret-not-a-real-token'
os.environ['OMI_EVEN_TOKEN'] = EVEN_TOKEN
# The push loop starts on app startup; keep it asleep unless a test drives it.
os.environ.setdefault('OMI_EVEN_PUSH_INTERVAL', '3600')
os.environ['OMI_SESSION_FILE'] = str(Path(__file__).parent / 'no-such-dir' / 'desktop-auth.json')

import httpx  # noqa: E402

import omi_auth  # noqa: E402

AUTH_HEADER = {'Authorization': f'Bearer {EVEN_TOKEN}'}

# Captured before anything can patch it, so installing a second mock transport
# inside one test replaces the first instead of nesting behind it.
_REAL_ASYNC_CLIENT = httpx.AsyncClient


# --------------------------------------------------------------------------
# Hermeticity guards
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Fail any test that tries to open a real socket.

    `TestClient` and `httpx.MockTransport` are both in-process, so nothing
    legitimate in this suite resolves a hostname or connects.
    """

    def _blocked(*args, **kwargs):
        raise AssertionError('test attempted real network access -- patch the transport')

    monkeypatch.setattr(socket, 'getaddrinfo', _blocked)
    monkeypatch.setattr(socket.socket, 'connect', _blocked)
    monkeypatch.setattr(socket.socket, 'connect_ex', _blocked)


@pytest.fixture(autouse=True)
def _no_keychain(monkeypatch):
    """Never shell out to the auth dump script (it can block on a Keychain prompt)."""

    def _blocked(bundle_id, out_path):
        return False

    monkeypatch.setattr(omi_auth, '_run_dump', _blocked)


# --------------------------------------------------------------------------
# Transport fakes
# --------------------------------------------------------------------------


def install_mock_transport(monkeypatch, handler):
    """Route every `httpx.AsyncClient` through `handler`, recording requests.

    The modules under test construct their own clients internally, so there is
    no injection point -- the class itself is swapped for a factory that pins a
    `MockTransport` onto whatever the caller asked for. Returns the list of
    captured `httpx.Request` objects.

    Only the async client is patched; `TestClient` is a sync `httpx.Client` and
    keeps working.
    """
    requests: list[httpx.Request] = []

    def _record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    def factory(*args, **kwargs):
        kwargs['transport'] = httpx.MockTransport(_record)
        return _REAL_ASYNC_CLIENT(*args, **kwargs)

    monkeypatch.setattr(httpx, 'AsyncClient', factory)
    return requests


def streaming_body(chunks):
    """An async byte stream that yields exactly the chunks given, in order."""

    async def body():
        for chunk in chunks:
            yield chunk

    return body()


class FakeAuth:
    """Stands in for `OmiAuth` with no session file, Keychain or Firebase."""

    def __init__(self, token: str = 'fake-id-token', fail: Exception | None = None) -> None:
        self.token = token
        self.fail = fail
        self.header_calls = 0

    async def id_token(self) -> str:
        if self.fail:
            raise self.fail
        return self.token

    async def uid(self) -> str:
        return 'fake-uid'

    async def auth_header(self) -> dict[str, str]:
        self.header_calls += 1
        if self.fail:
            raise self.fail
        return {'Authorization': f'Bearer {self.token}'}

    def describe(self) -> dict:
        return {'loaded': True, 'uid': 'fake-uid', 'expires_in': 3000}
