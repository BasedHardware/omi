"""HTTP/WS enforcement for account cutover fail-closed product traffic."""

from __future__ import annotations

import logging
import os
from typing import Any, Mapping, Optional

from fastapi import HTTPException
from fastapi import WebSocketException

from database import account_cutover as account_cutover_db
from models.account_cutover import AccountCutoverClientAction, AccountCutoverState
from utils.account_cutover.control import build_account_cutover_control, parse_client_build
from utils.account_cutover.telemetry import record_cutover_access_decision
from utils.executors import db_executor, run_blocking

logger = logging.getLogger(__name__)

WS_AUTH_CODE_ACCOUNT_CUTOVER = 4006

# Default off so accounts remaining legacy keep current main auth latency and
# behavior until operators enable enforcement after the bridge release.
_ENFORCEMENT_ENV = 'ACCOUNT_CUTOVER_ENFORCEMENT'


def cutover_enforcement_enabled() -> bool:
    return os.getenv(_ENFORCEMENT_ENV, 'off').strip().lower() in {'1', 'true', 'on', 'yes'}


# Auth, bootstrap, and cutover control remain reachable while product traffic
# is fenced. Path matching is prefix-based and intentionally narrow.
_ALWAYS_REACHABLE_PREFIXES = (
    '/v1/auth',
    '/v1/users/delete-account',  # account deletion remains independently fenced
    '/v1/account/cutover',
    '/v2/desktop/update-policy',
    '/v1/updates',
    '/health',
    '/v1/health',
)

_MUTATING_METHODS = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})


class AccountCutoverAccessDenial(Exception):
    def __init__(self, *, code: str, client_action: AccountCutoverClientAction, detail: Mapping[str, Any]):
        super().__init__(code)
        self.code = code
        self.client_action = client_action
        self.detail = dict(detail)


def is_cutover_control_path(path: str) -> bool:
    normalized = (path or '').split('?', 1)[0]
    return any(normalized == prefix or normalized.startswith(prefix + '/') for prefix in _ALWAYS_REACHABLE_PREFIXES)


def _headers_get(headers: Mapping[str, str], name: str) -> Optional[str]:
    lower = name.lower()
    for key, value in headers.items():
        if key.lower() == lower:
            return value
    return None


def evaluate_account_cutover_access(
    uid: str,
    *,
    method: str,
    path: str,
    headers: Mapping[str, str],
    firestore_client: Any = None,
    force: bool = False,
) -> None:
    """Raise AccountCutoverAccessDenial when product traffic must fail closed."""

    if not force and not cutover_enforcement_enabled():
        return

    if is_cutover_control_path(path):
        return

    record = account_cutover_db.get_account_cutover_record(uid, firestore_client=firestore_client)
    # Default legacy accounts with no floors keep main behavior.
    if record.state == AccountCutoverState.legacy and record.account_generation == 0:
        # Still enforce force-upgrade when operators configure a nonzero floor.
        platform = (_headers_get(headers, 'X-App-Platform') or '').strip().lower() or None
        build = parse_client_build(_headers_get(headers, 'X-App-Build')) or parse_client_build(
            _headers_get(headers, 'X-App-Version')
        )
        control = build_account_cutover_control(record, platform=platform, client_build=build)
        if control.client_action == AccountCutoverClientAction.force_upgrade and method.upper() in _MUTATING_METHODS:
            raise AccountCutoverAccessDenial(
                code='force_upgrade_required',
                client_action=control.client_action,
                detail={
                    'code': 'force_upgrade_required',
                    'client_action': control.client_action.value,
                    'state': record.state.value,
                    'account_generation': record.account_generation,
                    'retryable': False,
                },
            )
        return

    platform = (_headers_get(headers, 'X-App-Platform') or '').strip().lower() or None
    build = parse_client_build(_headers_get(headers, 'X-App-Build')) or parse_client_build(
        _headers_get(headers, 'X-App-Version')
    )
    control = build_account_cutover_control(record, platform=platform, client_build=build)

    if control.client_action == AccountCutoverClientAction.force_upgrade:
        raise AccountCutoverAccessDenial(
            code='force_upgrade_required',
            client_action=control.client_action,
            detail={
                'code': 'force_upgrade_required',
                'client_action': control.client_action.value,
                'state': record.state.value,
                'account_generation': record.account_generation,
                'retryable': False,
            },
        )

    if control.client_action == AccountCutoverClientAction.migration_maintenance:
        raise AccountCutoverAccessDenial(
            code='migration_maintenance',
            client_action=control.client_action,
            detail={
                'code': 'migration_maintenance',
                'client_action': control.client_action.value,
                'state': record.state.value,
                'account_generation': record.account_generation,
                'offline_queue_instruction': control.offline_queue_instruction.value,
                'stranded_new_data': control.stranded_new_data,
                'retryable': True,
            },
        )

    if record.state == AccountCutoverState.new and method.upper() in _MUTATING_METHODS:
        # New accounts must not mutate the legacy product plane. Auth/control
        # paths already returned above. Destination backend writes are out of
        # scope for this legacy foundation.
        raise AccountCutoverAccessDenial(
            code='legacy_plane_closed',
            client_action=AccountCutoverClientAction.none,
            detail={
                'code': 'legacy_plane_closed',
                'state': record.state.value,
                'account_generation': record.account_generation,
                'retryable': False,
            },
        )


def enforce_account_cutover_http_access(
    uid: str,
    *,
    method: str,
    path: str,
    headers: Mapping[str, str],
    firestore_client: Any = None,
) -> None:
    try:
        evaluate_account_cutover_access(
            uid,
            method=method,
            path=path,
            headers=headers,
            firestore_client=firestore_client,
        )
    except AccountCutoverAccessDenial as denial:
        record_cutover_access_decision(
            state=str(denial.detail.get('state') or 'unknown'),
            decision=denial.code,
            client_action=denial.client_action.value,
        )
        status_code = 426 if denial.code == 'force_upgrade_required' else 403
        raise HTTPException(status_code=status_code, detail=denial.detail) from denial


def enforce_account_cutover_ws_access(
    uid: str,
    *,
    path: str,
    headers: Mapping[str, str],
    firestore_client: Any = None,
) -> None:
    try:
        evaluate_account_cutover_access(
            uid,
            method='GET',
            path=path,
            headers=headers,
            firestore_client=firestore_client,
        )
    except AccountCutoverAccessDenial as denial:
        record_cutover_access_decision(
            state=str(denial.detail.get('state') or 'unknown'),
            decision=denial.code,
            client_action=denial.client_action.value,
        )
        raise WebSocketException(
            code=WS_AUTH_CODE_ACCOUNT_CUTOVER,
            reason=denial.code,
        ) from denial


async def enforce_account_cutover_http_access_async(
    uid: str,
    *,
    method: str,
    path: str,
    headers: Mapping[str, str],
) -> None:
    await run_blocking(
        db_executor,
        enforce_account_cutover_http_access,
        uid,
        method=method,
        path=path,
        headers=headers,
    )


__all__ = [
    'AccountCutoverAccessDenial',
    'WS_AUTH_CODE_ACCOUNT_CUTOVER',
    'cutover_enforcement_enabled',
    'enforce_account_cutover_http_access',
    'enforce_account_cutover_http_access_async',
    'enforce_account_cutover_ws_access',
    'evaluate_account_cutover_access',
    'is_cutover_control_path',
]
