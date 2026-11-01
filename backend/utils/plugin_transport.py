"""Opt-in, per-app authenticated transport for independently deployed plugins.

Legacy apps are unchanged. Configuration is server-only, never marketplace data.
See backend/docs/plugin-transport.md for the wire contract and rollout checklist.
"""

import hashlib
import json
import os
import secrets
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import jwt

ISSUER = 'omi-plugin-transport/v1'


@dataclass(frozen=True)
class PluginTransport:
    app_id: str
    base_url: str
    key: str

    def validate_url(self, url: str) -> None:
        expected, actual = urlsplit(self.base_url), urlsplit(url)
        if (
            actual.scheme != 'https'
            or actual.netloc != expected.netloc
            or actual.username
            or actual.password
            or actual.fragment
            or not actual.path.startswith(expected.path.rstrip('/') + '/')
        ):
            raise ValueError('Configured plugin endpoint does not match its trusted transport origin')

    def health_url(self) -> str:
        """A non-mutating readiness probe on the trusted origin; deliveries stay signed."""
        return self.base_url.rstrip('/') + '/health'

    def token(self, uid: str, scope: str, *, ttl: int = 600, **claims) -> str:
        now = int(time.time())
        return jwt.encode(
            {
                **claims,
                'iss': ISSUER,
                'aud': self.app_id,
                'sub': uid,
                'scope': scope,
                'iat': now,
                'exp': now + ttl,
                'jti': secrets.token_urlsafe(24),
            },
            self.key,
            algorithm='HS256',
        )

    def decode(self, token: str, scope: str) -> dict:
        claims = jwt.decode(
            token,
            self.key,
            algorithms=['HS256'],
            audience=self.app_id,
            issuer=ISSUER,
            options={'require': ['exp', 'iat', 'sub', 'jti', 'scope']},
        )
        if claims['scope'] != scope or not isinstance(claims['sub'], str) or not claims['sub']:
            raise ValueError('Invalid plugin token scope or subject')
        return claims

    def setup_url(self, url: str, uid: str, scope: str = 'setup') -> str:
        self.validate_url(url)
        parts = urlsplit(url)
        query = [(k, v) for k, v in parse_qsl(parts.query) if k not in ('uid', 'omi_token')]
        query.extend([('uid', uid), ('omi_token', self.token(uid, scope))])
        return urlunsplit(parts._replace(query=urlencode(query)))

    def delivery_headers(self, uid: str, url: str, payload: dict) -> dict[str, str]:
        self.validate_url(url)
        digest = hashlib.sha256(canonical_payload(payload)).hexdigest()
        return {
            'X-Omi-Plugin-Authorization': self.token(
                uid, 'delivery', path=urlsplit(url).path, sha256=digest, method='POST'
            )
        }


def canonical_payload(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def plugin_transport(app_id: str) -> PluginTransport | None:
    """An absent registration retains legacy behavior; a malformed one fails closed."""
    raw = os.getenv('OMI_PLUGIN_TRANSPORT_JSON', '').strip()
    if not raw:
        return None
    config = json.loads(raw)
    if not isinstance(config, dict):
        raise ValueError('OMI_PLUGIN_TRANSPORT_JSON must be an object')
    if app_id not in config:
        return None
    entry = config[app_id]
    if not isinstance(entry, dict):
        raise ValueError('Invalid plugin transport registration')
    base_url, key = entry.get('base_url'), entry.get('key')
    if not isinstance(base_url, str) or not isinstance(key, str) or len(key.encode()) < 32:
        raise ValueError('Plugin transport needs an HTTPS origin and at least a 32-byte key')
    parts = urlsplit(base_url)
    if (
        parts.scheme != 'https'
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
    ):
        raise ValueError('Invalid plugin transport origin')
    return PluginTransport(app_id, base_url.rstrip('/'), key)


def authorize_app_setup(app, uid: str):
    """Decorate only this authenticated response; never modify cached app data."""
    transport = plugin_transport(app.id)
    if transport is None or app.external_integration is None:
        return app
    result = app.model_copy(deep=True)
    integration = result.external_integration
    for step in integration.auth_steps or []:
        step.url = transport.setup_url(step.url, uid)
    if integration.app_home_url:
        integration.app_home_url = transport.setup_url(integration.app_home_url, uid)
    if integration.setup_completed_url:
        integration.setup_completed_url = transport.setup_url(integration.setup_completed_url, uid, 'status')
    return result


def strip_launch_credentials(app_id: str, integration: dict) -> None:
    """An owner editing app details must not persist a short-lived launch grant."""
    if plugin_transport(app_id) is None:
        return
    values = [(integration, field) for field in ('app_home_url', 'setup_completed_url')]
    values.extend((step, 'url') for step in integration.get('auth_steps') or [] if isinstance(step, dict))
    for container, field in values:
        url = container.get(field)
        if isinstance(url, str):
            parts = urlsplit(url)
            query = [(key, value) for key, value in parse_qsl(parts.query) if key not in ('uid', 'omi_token')]
            container[field] = urlunsplit(parts._replace(query=urlencode(query)))
