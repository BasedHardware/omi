import contextvars
from typing import Optional, Tuple
from datetime import datetime

import database.users as users_db
import logging

logger = logging.getLogger(__name__)

try:
    from utils.retrieval.agentic import agent_config_context
except ImportError:
    agent_config_context = contextvars.ContextVar('agent_config', default=None)


def resolve_config_uid(config: Optional[dict]) -> Tuple[Optional[str], Optional[str]]:
    if config is None:
        try:
            config = agent_config_context.get()
        except LookupError:
            config = None
    if config is None:
        return None, "Error: Configuration not available"
    try:
        uid = config.get('configurable', {}).get('user_id')
    except Exception:
        return None, "Error: Configuration not available"
    if not uid:
        return None, "Error: User ID not found in configuration"
    return uid, None


def get_integration_checked(
    uid: str,
    key: str,
    connection_name: str,
    not_connected_msg: str,
    error_prefix: str,
) -> Tuple[Optional[dict], Optional[str]]:
    try:
        integration = users_db.get_integration(uid, key)
    except Exception as e:
        return None, f"{error_prefix}: {str(e)}"
    if not integration or not integration.get('connected'):
        return None, not_connected_msg
    return integration, None


def get_access_token_checked(integration: dict, missing_msg: str) -> Tuple[Optional[str], Optional[str]]:
    token = integration.get('access_token') if integration else None
    if not token:
        return None, missing_msg
    return token, None


def cap_limit(value: int, cap: int) -> int:
    return value if value <= cap else cap


def ensure_capped(value: int, cap: int, warn_msg: str) -> int:
    if value > cap:
        try:
            logger.info(warn_msg.format(value, cap))
        except Exception:
            logger.info(warn_msg)
        return cap
    return value


def parse_iso_with_tz(
    field_name: str, value: Optional[str], tz_required_msg: str
) -> Tuple[Optional[datetime], Optional[str]]:
    if not value:
        return None, None
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            return None, f"Error: {field_name} must include timezone {tz_required_msg}: {value}"
        return dt, None
    except ValueError as e:
        return None, f"Error: Invalid {field_name} format. Expected {tz_required_msg}: {value} - {str(e)}"


def prepare_access(
    config: Optional[dict],
    provider_key: str,
    provider_label: str,
    not_connected_msg: str,
    missing_token_msg: str,
    error_prefix: str,
) -> Tuple[Optional[str], Optional[dict], Optional[str], Optional[str]]:
    uid, uid_err = resolve_config_uid(config)
    if uid_err:
        return None, None, None, uid_err
    integration, int_err = get_integration_checked(
        uid,
        provider_key,
        provider_label,
        not_connected_msg,
        error_prefix,
    )
    if int_err:
        return uid, None, None, int_err
    token, token_err = get_access_token_checked(integration, missing_token_msg)
    if token_err:
        return uid, integration, None, token_err
    return uid, integration, token, None


def retry_on_auth(
    call_fn,
    call_kwargs: dict,
    refresh_fn,
    uid: str,
    integration: dict,
    expired_msg: str,
    markers: Tuple[str, ...] = (
        "Authentication failed",
        "401",
        "token may be expired",
        "token may be expired or invalid",
    ),
):
    try:
        return call_fn(**call_kwargs), None
    except Exception as e:
        msg = str(e)
        if any(m in msg for m in markers):
            new_token = refresh_fn(uid, integration)
            if new_token:
                call_kwargs = dict(call_kwargs)
                call_kwargs['access_token'] = new_token
                try:
                    return call_fn(**call_kwargs), None
                except Exception as e2:
                    return None, f"Error after token refresh: {str(e2)}"
            return None, expired_msg
        return None, f"Error: {msg}"
