"""Idempotent onboarding for code-whitelisted canonical-memory users.

The canonical cohort is code-owned, while the per-user rollout document is
durable Firestore state.  This module reconciles that boundary without
activating a user: a missing document is created with the existing inert
enrollment builder, and an existing document is validated and left untouched.
It intentionally does not create or inspect memory heads, projections, items,
or global rollout gates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from google.api_core.exceptions import AlreadyExists, Conflict

from config.memory_rollout import MemoryRolloutMode
from database.memory_collections import MemoryCollections
from utils.memory.default_read_rollout import (
    DEFAULT_READ_ROLLOUT_SCHEMA_VERSION,
    normalize_default_read_rollout_decision,
)
from utils.memory.memory_system import list_canonical_cohort_uids
from utils.memory.v3.limited_rollout_config import build_whitelisted_user_control_state

ONBOARDING_ACCOUNT_GENERATION = 0
OnboardingAction = Literal['created', 'preserved']


class CanonicalMemoryOnboardingValidationError(RuntimeError):
    """An existing canonical-memory control document cannot be trusted."""

    def __init__(self, *, uid: str, reason: str):
        self.uid = uid
        self.reason = reason
        super().__init__(f'canonical memory onboarding validation failed for uid={uid}: {reason}')


@dataclass(frozen=True)
class CanonicalMemoryOnboardingUserResult:
    uid: str
    action: OnboardingAction
    control_state_path: str


@dataclass(frozen=True)
class CanonicalMemoryOnboardingReport:
    users: tuple[CanonicalMemoryOnboardingUserResult, ...]

    @property
    def created_uids(self) -> tuple[str, ...]:
        return tuple(user.uid for user in self.users if user.action == 'created')

    @property
    def preserved_uids(self) -> tuple[str, ...]:
        return tuple(user.uid for user in self.users if user.action == 'preserved')


def _control_state_path(uid: str) -> str:
    return MemoryCollections(uid=uid).memory_control_state


def _validate_existing_control_state(*, uid: str, path: str, payload: object) -> None:
    """Validate through the existing rollout reader/model contract.

    The normalized decision constructs ``MemoryRolloutState`` and checks the
    persisted UID and schema.  It deliberately does not require the state to be
    activated or projection-ready; those are separate rollout decisions.
    """

    decision = normalize_default_read_rollout_decision(
        uid=uid,
        source_path=path,
        consumer='omi_chat',
        data=payload,
    )
    if decision.reason != 'ok':
        raise CanonicalMemoryOnboardingValidationError(uid=uid, reason=decision.reason)


def _safe_onboarding_payload(uid: str) -> dict[str, Any]:
    """Build the inert state with the canonical enrollment policy.

    Generation zero is an explicit unknown-generation fence.  It permits a
    scheduler to establish durable rollout state without claiming a trusted
    account head that this reconciler neither reads nor creates.
    """

    payload = build_whitelisted_user_control_state(
        uid=uid,
        account_generation=ONBOARDING_ACCOUNT_GENERATION,
        mode=MemoryRolloutMode.off,
        projection_ready=False,
        default_memory_grant=False,
        archive_grant=False,
    )
    if payload.get('schema_version') != DEFAULT_READ_ROLLOUT_SCHEMA_VERSION:
        raise RuntimeError('canonical enrollment builder returned an unsupported rollout schema')
    return payload


def _existing_snapshot_payload(*, uid: str, snapshot: Any) -> object:
    if getattr(snapshot, 'exists', False) is not True:
        raise CanonicalMemoryOnboardingValidationError(uid=uid, reason='control_state_disappeared_after_create_race')
    try:
        return snapshot.to_dict()
    except Exception:
        raise CanonicalMemoryOnboardingValidationError(uid=uid, reason='control_state_read_failed') from None


def _reconcile_user(db_client: Any, *, uid: str) -> CanonicalMemoryOnboardingUserResult:
    if not uid.strip():
        raise ValueError('canonical cohort contains a blank uid')

    path = _control_state_path(uid)
    control_ref = db_client.document(path)
    snapshot = control_ref.get()
    if getattr(snapshot, 'exists', False) is True:
        payload = _existing_snapshot_payload(uid=uid, snapshot=snapshot)
        _validate_existing_control_state(uid=uid, path=path, payload=payload)
        return CanonicalMemoryOnboardingUserResult(uid=uid, action='preserved', control_state_path=path)

    payload = _safe_onboarding_payload(uid)
    try:
        # Firestore create is an atomic exists=false compare-and-create.  Never
        # use merge/set here: a concurrent rollout writer must win unchanged.
        control_ref.create(payload)
    except (AlreadyExists, Conflict):
        raced_snapshot = control_ref.get()
        raced_payload = _existing_snapshot_payload(uid=uid, snapshot=raced_snapshot)
        _validate_existing_control_state(uid=uid, path=path, payload=raced_payload)
        return CanonicalMemoryOnboardingUserResult(uid=uid, action='preserved', control_state_path=path)

    return CanonicalMemoryOnboardingUserResult(uid=uid, action='created', control_state_path=path)


def reconcile_canonical_memory_onboarding(
    db_client: Any,
) -> CanonicalMemoryOnboardingReport:
    """Ensure inert control state exists for every canonical cohort UID.

    Membership always comes from ``list_canonical_cohort_uids()`` so a scheduler
    cannot accidentally create state for a UID outside the code-owned selector.
    """

    uids = list_canonical_cohort_uids()
    if any(not uid.strip() for uid in uids):
        raise ValueError('canonical cohort contains a blank uid')
    results = tuple(_reconcile_user(db_client, uid=uid) for uid in sorted(set(uids)))
    return CanonicalMemoryOnboardingReport(users=results)


__all__ = [
    'CanonicalMemoryOnboardingReport',
    'CanonicalMemoryOnboardingUserResult',
    'CanonicalMemoryOnboardingValidationError',
    'ONBOARDING_ACCOUNT_GENERATION',
    'reconcile_canonical_memory_onboarding',
]
