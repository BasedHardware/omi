"""Firebase Auth emulator identities and runtime guard for Chat-first E2E.

The Firebase Auth emulator assigns the authenticated ``localId``.  It does not
reliably honour a caller-provided ``localId`` during seed, so fixture access
resolves two logical synthetic principals through the dev-harness manifest
instead of relying on a production-like auth bypass or hard-coded UID.
"""

import json
import os
from pathlib import Path

CHAT_FIRST_E2E_ENABLED_PRINCIPAL = 'omi-chat-first-e2e-enabled'
CHAT_FIRST_E2E_OUT_OF_COHORT_PRINCIPAL = 'omi-chat-first-e2e-out-of-cohort'
_LOCAL_E2E_STAGES = frozenset({'local', 'offline'})
_AUTH_UID_MANIFEST_NAME = 'canonical-auth-uids.json'


def is_chat_first_e2e_harness_runtime(*, stage: str | None = None) -> bool:
    """Return whether the harness may exist in this process at all.

    This uses the existing backend stage boundary rather than a deployable
    feature flag.  The router is not registered outside local/offline, and its
    handlers repeat this check before doing any fixture work.
    """

    runtime_stage = (os.getenv('OMI_ENV_STAGE') if stage is None else stage) or ''
    return runtime_stage.strip().lower() in _LOCAL_E2E_STAGES


def _fixture_auth_uids(*, state_root: str | None = None) -> dict[str, str]:
    """Resolve the two real Auth emulator UIDs from harness-owned state.

    Missing or malformed local state is fail-closed: fixture identities are
    never recognized by their logical names and never available in deployable
    environments.  ``state_root`` is injectable solely for hermetic tests.
    """

    root = (os.getenv('OMI_HARNESS_STATE_ROOT') if state_root is None else state_root) or ''
    if not root.strip():
        return {}
    manifest_path = Path(root).expanduser() / 'manifests' / _AUTH_UID_MANIFEST_NAME
    try:
        payload = json.loads(manifest_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}
    users = payload.get('users') if isinstance(payload, dict) else None
    if not isinstance(users, dict):
        return {}
    resolved: dict[str, str] = {}
    for principal in (CHAT_FIRST_E2E_ENABLED_PRINCIPAL, CHAT_FIRST_E2E_OUT_OF_COHORT_PRINCIPAL):
        uid = users.get(principal)
        if isinstance(uid, str) and uid.strip():
            resolved[principal] = uid.strip()
    return resolved


def fixture_uid_for_principal(principal: str, *, state_root: str | None = None) -> str | None:
    """Return the Auth emulator UID for one logical fixture principal."""

    return _fixture_auth_uids(state_root=state_root).get(principal)


def is_chat_first_e2e_enabled_fixture(uid: str, *, stage: str | None = None) -> bool:
    """Return whether one local-only fixture identity is in the test cohort."""

    return is_chat_first_e2e_harness_runtime(stage=stage) and uid == fixture_uid_for_principal(
        CHAT_FIRST_E2E_ENABLED_PRINCIPAL
    )


def is_chat_first_e2e_fixture_uid(uid: str, *, stage: str | None = None) -> bool:
    """Return whether ``uid`` is one of the two isolated E2E accounts."""

    return is_chat_first_e2e_harness_runtime(stage=stage) and uid in set(_fixture_auth_uids().values())


__all__ = [
    'CHAT_FIRST_E2E_ENABLED_PRINCIPAL',
    'CHAT_FIRST_E2E_OUT_OF_COHORT_PRINCIPAL',
    'fixture_uid_for_principal',
    'is_chat_first_e2e_enabled_fixture',
    'is_chat_first_e2e_fixture_uid',
    'is_chat_first_e2e_harness_runtime',
]
