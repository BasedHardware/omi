"""Verify Google ID tokens with a bounded, per-worker signing certificate cache."""

import json
import re
import subprocess
import sys
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
_CERT_COMMAND = (sys.executable, __file__)
_JWT = re.compile(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+')


def fetch_certificates(client, timeout):
    with client.stream('GET', _CERT_URL, timeout=timeout, follow_redirects=False) as response:
        response.raise_for_status()
        body = bytearray()
        for chunk in response.iter_bytes():
            if len(body) + len(chunk) > _MAX_CERT_BYTES:
                raise auth_errors.TransportError('pager signing certificate response exceeded size budget')
            body.extend(chunk)
        return {
            'body': body.decode('utf-8'),
            'cache_control': response.headers.get('cache-control', ''),
            'age': response.headers.get('age', '0'),
        }


def fetch_in_process(timeout):
    # A timed-out process is killed and reaped, even if DNS is still blocked.
    response = subprocess.run(
        _CERT_COMMAND, stdin=subprocess.DEVNULL, env={}, capture_output=True, check=True, timeout=timeout
    )
    return json.loads(response.stdout)


class OIDCVerifier:
    def __init__(self, fetch=fetch_in_process, *, clock=monotonic):
        self.fetch = fetch
        self.clock = clock
        self.lock = Lock()
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

    def certificates(self, url, method):
        deadline = monotonic() + _CERT_TIMEOUT
        if (url, method) != (_CERT_URL, 'GET') or not self.lock.acquire(timeout=_CERT_TIMEOUT):
            raise auth_errors.TransportError('pager signing certificates unavailable')
        try:
            if self.certs is not None and self.clock() < self.expires_at:
                return self.certs
            self.certs = None
            started_at = self.clock()
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError()
            response = self.fetch(remaining)
            body = response['body'].encode('utf-8')
            certs = json.loads(body)
            if not isinstance(certs, dict) or not certs:
                raise ValueError('empty signing certificate map')
            for cert in certs.values():
                if not isinstance(cert, str):
                    raise ValueError('invalid signing certificate')
                x509.load_pem_x509_certificate(cert.encode())

            control = response['cache_control'].lower()
            max_age = re.search(r'(?:^|,)\s*max-age=(\d{1,10})\s*(?:,|$)', control)
            age = response['age']
            cacheable = not {'no-cache', 'no-store'}.intersection(part.strip() for part in control.split(','))
            result = SimpleNamespace(status=200, data=body)
            if cacheable and max_age and re.fullmatch(r'\d{1,10}', age):
                self.expires_at = started_at + min(3600, int(max_age[1]) - int(age))
                self.certs = result
            return result
        except (ValueError, RecursionError, OSError, subprocess.SubprocessError, httpx.HTTPError) as error:
            raise auth_errors.TransportError('pager signing certificates unavailable') from error
        finally:
            self.lock.release()


def main():
    with httpx.Client(trust_env=False) as client:
        sys.stdout.write(json.dumps(fetch_certificates(client, _CERT_TIMEOUT)))


if __name__ == '__main__':
    main()
