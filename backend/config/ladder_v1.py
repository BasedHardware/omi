"""Ladder cutover switches. Read at call time; unset and malformed values are OFF."""

import os
from typing import Any, Mapping

from config.plan_catalog import get_entitlement_version, resolve_subscription_entitlements


def enabled(flag: str) -> bool:
    return os.getenv(flag, 'false') == 'true'


def entitlements(subscription: Any) -> Mapping[str, Any] | None:
    resolved = resolve_subscription_entitlements(subscription or {'plan': 'basic'})
    if resolved['plan_id'] == 'basic':
        return get_entitlement_version('basic', 'ladder_v1')
    return resolved if resolved['entitlement_version'] == 'ladder_v1' else None


def pro_trigger(feature: str) -> str | None:
    if any(word in feature for word in ('screen', 'livenotes')):
        return 'screen_context'
    if feature.startswith(('proactiv', 'desktop_proactiv', 'mentor', 'commitment')):
        return 'proactive_agent'
    return None


def budget_enforcement_enabled() -> bool:
    return os.getenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'false') == 'true'


def mcp_daily_caps_enabled() -> bool:
    return os.getenv('LADDER_V1_MCP_DAILY_CAPS_ENABLED', 'false') == 'true'
