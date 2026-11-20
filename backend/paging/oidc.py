"""Verify Google ID tokens with a bounded, per-worker signing certificate cache."""

from concurrent.futures import ThreadPoolExecutor
import json
import re
from threading import Lock
from time import monotonic
from types import SimpleNamespace

from cryptography import x509
from google.auth import exceptions as auth_errors, jwt
from google.oauth2 import id_token
import httpx

_CERT_URL = 'https://www.googleapis.com/oauth2/v1/certs'
_CERT_TIMEOUT = 2.0
_MAX_CERT_BYTES = 64 * 1024
_JWT = re.compile(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+')


class OIDCVerifier:
    def __init__(self, client_factory=None, *, clock=monotonic):
        self.client_factory = client_factory if client_factory is not None else lambda: httpx.Client(trust_env=False)
        self.clock = clock
        self.lock = Lock()
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pager-oidc")
        self.refresh = None
        self.certs = None
        self.expires_at = 0

    def __call__(self, authorization, audience, principal):
        token = authorization[7:]
        if not authorization.startswith('Bearer ') or len(token) > 8192 or not _JWT.fullmatch(token):
            return False
        try:
            header = jwt.decode_header(token)
            claims = jwt.decode(token, verify=False)
            if (
                header.get('alg') not in ('RS256', 'ES256')
                or ('kid' in header and not (isinstance(header['kid'], str) and header['kid']))
                or any(not isinstance(claims.get(name), str) for name in ('iss', 'aud', 'email'))
                or any(type(claims.get(name)) is not int for name in ('iat', 'exp'))
            ):
                return False
            verified = id_token.verify_oauth2_token(token, self.certificates, audience=audience)
        except (ValueError, RecursionError, auth_errors.GoogleAuthError):
            return False
        return verified.get('email') == principal and verified.get('email_verified') is True

    def fetch(self, deadline):
        started_at = self.clock()
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError()
        with self.client_factory() as client:
            with client.stream('GET', _CERT_URL, timeout=remaining, follow_redirects=False) as response:
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes():
                    if monotonic() >= deadline:
                        raise TimeoutError()
                    if len(body) + len(chunk) > _MAX_CERT_BYTES:
                        raise auth_errors.TransportError('pager signing certificate response exceeded size budget')
                    body.extend(chunk)
                if monotonic() >= deadline:
                    raise TimeoutError()
                return bytes(body), response.headers, started_at

    def certificates(self, url, method):
        deadline = monotonic() + _CERT_TIMEOUT
        if (url, method) != (_CERT_URL, 'GET') or not self.lock.acquire(timeout=_CERT_TIMEOUT):
            raise auth_errors.TransportError('pager signing certificates unavailable')
        try:
            if self.certs is not None and self.clock() < self.expires_at:
                return self.certs
            self.certs = None
            # Keep the slot occupied if the caller times out during a blocking
            # resolver call. Later requests can wait on it but cannot queue more.
            if self.refresh is None:
                self.refresh = self.worker.submit(self.fetch, deadline)
            try:
                body, headers, started_at = self.refresh.result(timeout=max(0, deadline - monotonic()))
            finally:
                if self.refresh.done():
                    self.refresh = None
            certs = json.loads(body)
            if not isinstance(certs, dict) or not certs:
                raise ValueError('empty signing certificate map')
            for cert in certs.values():
                if not isinstance(cert, str):
                    raise ValueError('invalid signing certificate')
                x509.load_pem_x509_certificate(cert.encode())

            control = headers.get('cache-control', '').lower()
            max_age = re.search(r'(?:^|,)\s*max-age=(\d{1,10})\s*(?:,|$)', control)
            age = headers.get('age', '0')
            cacheable = not {'no-cache', 'no-store'}.intersection(part.strip() for part in control.split(','))
            result = SimpleNamespace(status=200, data=body)
            if cacheable and max_age and re.fullmatch(r'\d{1,10}', age):
                self.expires_at = started_at + min(3600, int(max_age[1]) - int(age))
                self.certs = result
            return result
        except (ValueError, RecursionError, TimeoutError, httpx.HTTPError) as error:
            raise auth_errors.TransportError('pager signing certificates unavailable') from error
        finally:
            self.lock.release()
