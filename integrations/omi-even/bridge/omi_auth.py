"""Firebase session for the Omi bridge, borrowed from the desktop app.

Omi's chat endpoint (`POST /v2/messages`) and the capture socket (`WS /v4/listen`)
accept **only** a Firebase ID token -- no `omi_mcp_`, `omi_dev_`, or app key works
(`backend/utils/other/endpoints.py:81`). Rather than run a browser OAuth flow, this
reuses the session the macOS desktop app already holds and mints fresh ID tokens
from its long-lived refresh token.

ID tokens last an hour; refresh tokens last a year, so the bridge stays signed in
with no user interaction as long as the desktop app was signed in once.

The session is obtained through the repo's own `desktop/macos/scripts/omi-auth-dump.sh`,
which is the sanctioned way to export a signed-in desktop session (its header
documents this exact use). Going through that script rather than reimplementing the
Keychain lookup keeps one source of truth for the team+bundle scoped service name,
which the desktop app derives at runtime and has already changed once.

Token material is held in memory and never logged. `describe()` reports status
without exposing values.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

# Public Firebase Web API key for the `based-hardware` project. Firebase API keys
# identify a project, they do not authorize -- they ship in every public build.
# This is the unrestricted (Windows) key: a referrer-locked web key 403s from a
# non-browser client with API_KEY_HTTP_REFERRER_BLOCKED. Same key omi-cli uses
# (sdks/python-cli/omi_cli/auth/oauth.py).
_FIREBASE_API_KEY = 'AIzaSyA88gHcmiAxjN_aE23tHRWXOgFfapyO6dk'
_FIREBASE_REFRESH_URL = f'https://securetoken.googleapis.com/v1/token?key={_FIREBASE_API_KEY}'

# Bundles to try, in order. Only the dev bundle is attempted by default: reading the
# prod bundle's entry can sit behind a Keychain ACL dialog that blocks indefinitely,
# and prod is the user's real installed app which we never want to disturb.
_DEFAULT_BUNDLES = ('com.omi.desktop-dev',)

# Refresh this far before the server-quoted expiry, to absorb clock skew and the
# round trip of the request the token is about to be used for.
_REFRESH_MARGIN_SECONDS = 120

# The dump shells out to `security`, which can block on an ACL prompt. A short
# timeout turns that into a fast, reportable failure instead of a hung bridge.
_DUMP_TIMEOUT_SECONDS = 30


class AuthError(RuntimeError):
    """Raised when no usable Omi session can be established."""


@dataclass
class _Session:
    id_token: str
    refresh_token: str
    expires_at: float
    uid: str


def _repo_root() -> Path:
    """Walk up to the repository root that contains desktop/macos/scripts."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / 'desktop' / 'macos' / 'scripts' / 'omi-auth-dump.sh').exists():
            return parent
    raise AuthError(f'could not locate the omi repo root above {here}')


def _session_file() -> Path:
    override = os.getenv('OMI_SESSION_FILE')
    if override:
        return Path(override).expanduser()
    # The dump script's own default, which the repo gitignores.
    return _repo_root() / 'desktop' / 'tmp' / 'desktop-auth.json'


def _run_dump(bundle_id: str, out_path: Path) -> bool:
    """Export a signed-in desktop session via the repo's sanctioned script."""
    script = _repo_root() / 'desktop' / 'macos' / 'scripts' / 'omi-auth-dump.sh'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            ['bash', str(script), bundle_id, str(out_path)],
            capture_output=True,
            text=True,
            timeout=_DUMP_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        # Almost always a Keychain ACL dialog waiting on a human.
        log.warning('auth dump for %s timed out (Keychain prompt?) -- skipping', bundle_id)
        return False
    except OSError as exc:
        log.debug('auth dump for %s failed to start: %s', bundle_id, exc)
        return False

    if result.returncode != 0:
        log.debug('auth dump for %s exited %s: %s', bundle_id, result.returncode, result.stderr.strip()[:200])
        return False
    return out_path.exists()


def _parse_session_file(path: Path) -> dict | None:
    """Read the dump file's {key: {type, value}} shape into a flat dict."""
    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        log.debug('could not read session file %s: %s', path, exc)
        return None
    if not isinstance(raw, dict):
        # Valid JSON, wrong file. Read as "no session" so the caller re-exports
        # and ends with the actionable AuthError instead of an AttributeError.
        log.debug('session file %s is %s, not an object', path, type(raw).__name__)
        return None
    flat = {}
    for key, entry in raw.items():
        flat[key] = entry.get('value') if isinstance(entry, dict) else entry
    return flat


class OmiAuth:
    """Supplies a valid Firebase ID token, refreshing it as needed."""

    def __init__(self, bundles: tuple[str, ...] | None = None) -> None:
        env_bundle = os.getenv('OMI_SOURCE_BUNDLE')
        self._bundles = (env_bundle,) if env_bundle else (bundles or _DEFAULT_BUNDLES)
        self._session: _Session | None = None
        self._lock = asyncio.Lock()

    def _load_session(self) -> _Session:
        """Find a desktop session, re-exporting it if the cached file is unusable."""
        path = _session_file()
        flat = _parse_session_file(path) if path.exists() else None

        if not (flat or {}).get('auth_refreshToken'):
            for bundle in self._bundles:
                if _run_dump(bundle, path):
                    flat = _parse_session_file(path)
                    if (flat or {}).get('auth_refreshToken'):
                        log.info('exported Omi session from %s', bundle)
                        break
                    flat = None

        if not flat or not flat.get('auth_refreshToken'):
            raise AuthError(
                'No signed-in Omi desktop session found (tried: '
                + ', '.join(self._bundles)
                + f'; session file: {path}). Sign in to the Omi macOS app once, '
                'then restart the bridge.'
            )

        return _Session(
            id_token=flat.get('auth_idToken') or '',
            refresh_token=flat['auth_refreshToken'],
            # Ignore the stored expiry and force a refresh on first use, so a stale
            # dump can never produce a confusing 401 mid-conversation.
            expires_at=0.0,
            uid=flat.get('auth_tokenUserId') or flat.get('auth_userId') or '',
        )

    async def _refresh(self, session: _Session) -> _Session:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0)) as client:
            response = await client.post(
                _FIREBASE_REFRESH_URL,
                data={'grant_type': 'refresh_token', 'refresh_token': session.refresh_token},
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
            )
        if response.status_code != 200:
            # Body can echo the token; surface only the reason code.
            reason = ''
            try:
                reason = response.json().get('error', {}).get('message', '')
            except ValueError:
                pass
            raise AuthError(
                f'Firebase token refresh failed ({response.status_code} {reason}). '
                'The desktop session may have been revoked -- sign in again.'
            )
        payload = response.json()
        return _Session(
            id_token=payload['id_token'],
            # Firebase may rotate the refresh token; keep the newest.
            refresh_token=payload.get('refresh_token') or session.refresh_token,
            expires_at=time.time() + float(payload.get('expires_in', 3600)),
            uid=payload.get('user_id') or session.uid,
        )

    async def id_token(self) -> str:
        """Return a currently-valid Firebase ID token, refreshing if needed."""
        async with self._lock:
            if self._session is None:
                self._session = self._load_session()
            if time.time() >= self._session.expires_at - _REFRESH_MARGIN_SECONDS:
                self._session = await self._refresh(self._session)
            return self._session.id_token

    async def uid(self) -> str:
        await self.id_token()
        assert self._session is not None
        return self._session.uid

    async def auth_header(self) -> dict[str, str]:
        return {'Authorization': f'Bearer {await self.id_token()}'}

    def describe(self) -> dict[str, object]:
        """Status for health endpoints -- never includes token material."""
        if self._session is None:
            return {'loaded': False}
        return {
            'loaded': True,
            'uid': self._session.uid,
            'expires_in': max(0, int(self._session.expires_at - time.time())),
        }
