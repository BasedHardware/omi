"""Minimal GoAffPro API client.

Three credentials, as GoAffPro defines them:
- admin token: store-wide reads and writes (`/admin/*`)
- public token: the store's SDK surface (`/sdk/*`)
- an affiliate's login token: that affiliate's own SDK reads

An affiliate's login token is a long-lived credential. It is fetched through the
admin API, kept in process memory for a few minutes, and never returned to a
client or logged.
"""

import logging
import threading
import time
from typing import Any, Optional
from urllib.parse import urlencode

import httpx

from config.affiliate import goaffpro_access_token, goaffpro_public_token

logger = logging.getLogger(__name__)

BASE_URL = 'https://api.goaffpro.com/v1'
BLOCKED_STATUSES = frozenset({'blocked', 'suspended'})
_LOGIN_TOKEN_TTL_SECONDS = 300
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class GoAffProError(Exception):
    def __init__(self, status_code: int, operation: str):
        super().__init__(f'GoAffPro {operation} failed status={status_code}')
        self.status_code = status_code
        self.operation = operation


_client: Optional[httpx.Client] = None
_client_lock = threading.Lock()
_login_tokens: dict[str, tuple[str, float]] = {}
_login_tokens_lock = threading.Lock()


def _http() -> httpx.Client:
    global _client
    with _client_lock:
        if _client is None:
            _client = httpx.Client(
                base_url=BASE_URL,
                timeout=httpx.Timeout(10.0, connect=3.0),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=5),
            )
        return _client


def _request(
    method: str,
    path: str,
    *,
    operation: str,
    headers: dict[str, str],
    params: Optional[dict[str, Any]] = None,
    json: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    url = path if not params else f'{path}?{urlencode(params)}'
    attempts = 2 if method == 'GET' else 1
    for attempt in range(attempts):
        try:
            response = _http().request(method, url, headers={'Content-Type': 'application/json', **headers}, json=json)
        except httpx.HTTPError as error:
            logger.warning('goaffpro request error operation=%s error_type=%s', operation, type(error).__name__)
            if attempt + 1 < attempts:
                continue
            raise GoAffProError(0, operation) from error
        if response.status_code in _RETRY_STATUSES and attempt + 1 < attempts:
            time.sleep(0.5)
            continue
        if response.status_code >= 400:
            logger.warning('goaffpro request failed operation=%s status=%s', operation, response.status_code)
            raise GoAffProError(response.status_code, operation)
        try:
            body = response.json()
        except ValueError as error:
            raise GoAffProError(response.status_code, operation) from error
        return body if isinstance(body, dict) else {'data': body}
    raise GoAffProError(0, operation)


def _admin_headers() -> dict[str, str]:
    return {'x-goaffpro-access-token': goaffpro_access_token()}


def _sdk_headers(login_token: Optional[str] = None) -> dict[str, str]:
    headers = {'x-goaffpro-public-token': goaffpro_public_token()}
    if login_token:
        headers['Authorization'] = f'Bearer {login_token}'
    return headers


def is_blocked(status: Any) -> bool:
    return isinstance(status, str) and status.lower() in BLOCKED_STATUSES


# ----------------------------------------------------------------------------- admin


def find_affiliate_by_email(email: str) -> Optional[dict[str, Any]]:
    body = _request(
        'GET',
        '/admin/affiliates',
        operation='admin_find_by_email',
        headers=_admin_headers(),
        params={'email': email, 'fields': 'id,email,status,email_verified', 'limit': 1},
    )
    affiliates = body.get('affiliates') or []
    return affiliates[0] if affiliates else None


def get_affiliate(affiliate_id: str, fields: str = 'id,name,email,status,ref_code,coupon') -> Optional[dict[str, Any]]:
    body = _request(
        'GET',
        '/admin/affiliates',
        operation='admin_get',
        headers=_admin_headers(),
        params={'id': affiliate_id, 'fields': fields, 'limit': 1},
    )
    affiliates = body.get('affiliates') or []
    return affiliates[0] if affiliates else None


def create_affiliate(name: str, email: str) -> str:
    body = _request(
        'POST',
        '/admin/affiliates',
        operation='admin_create',
        headers=_admin_headers(),
        json={'name': name, 'email': email, 'status': 'approved'},
    )
    affiliate_id = body.get('affiliate_id')
    if not affiliate_id:
        raise GoAffProError(200, 'admin_create')
    return str(affiliate_id)


def ref_code_taken_by_other(ref_code: str, affiliate_id: str) -> bool:
    body = _request(
        'GET',
        '/admin/affiliates',
        operation='admin_find_by_ref_code',
        headers=_admin_headers(),
        params={'ref_code': ref_code, 'fields': 'id,ref_code'},
    )
    return any(str(a.get('id')) != str(affiliate_id) for a in body.get('affiliates') or [])


def update_affiliate(affiliate_id: str, patch: dict[str, Any]) -> None:
    _request(
        'PATCH', f'/admin/affiliates/{affiliate_id}', operation='admin_update', headers=_admin_headers(), json=patch
    )


def payment_admin_notes(payment_ids: list[str]) -> dict[str, str]:
    if not payment_ids:
        return {}
    body = _request(
        'GET',
        '/admin/payments',
        operation='admin_payments',
        headers=_admin_headers(),
        params={'id': ','.join(payment_ids), 'fields': 'id,admin_note'},
    )
    return {str(p.get('id')): p.get('admin_note') or '' for p in body.get('payments') or []}


def login_token(affiliate_id: str) -> str:
    now = time.monotonic()
    with _login_tokens_lock:
        cached = _login_tokens.get(affiliate_id)
        if cached and cached[1] > now:
            return cached[0]
    affiliate = get_affiliate(affiliate_id, fields='id,login_token')
    token = (affiliate or {}).get('login_token')
    if not token:
        raise GoAffProError(404, 'admin_login_token')
    with _login_tokens_lock:
        _login_tokens[affiliate_id] = (token, now + _LOGIN_TOKEN_TTL_SECONDS)
    return token


# ----------------------------------------------------------------------------- sdk


def verify_credentials(email: str, password: str) -> bool:
    """True when GoAffPro accepts this affiliate email/password."""
    try:
        body = _request(
            'POST',
            '/sdk/user/login',
            operation='sdk_login',
            headers=_sdk_headers(),
            json={'email': email, 'password': password},
        )
    except GoAffProError as error:
        if error.status_code in (400, 401, 403, 404, 422):
            return False
        raise
    return bool(body.get('access_token'))


def user_get(affiliate_id: str, path: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    return _request(
        'GET', path, operation=f'sdk_get{path}', headers=_sdk_headers(login_token(affiliate_id)), params=params
    )


def user_post(affiliate_id: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    return _request(
        'POST', path, operation=f'sdk_post{path}', headers=_sdk_headers(login_token(affiliate_id)), json=payload
    )
