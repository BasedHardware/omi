"""Request-scoped authorization for Omi-billed (managed) LLM compute.

Every managed call resolves ``(uid, feature, funding_owner)`` to a ``Decision``
before model resolution. Fail closed: missing config, mapping, or entitlement is
an explicit deny, never a silent fall-through to luna or a live key.

The one fail-open is plan *identification* (Target 3): a lookup error for a
known feature keeps paid-path quotas so a Firestore blip cannot strip a paid
user. Unknown features still deny. Every other dependency error denies with
``authorization_unavailable``.

The free allowlist is this module's frozenset plus the ``chat_`` prefix rule.
Plan identity comes from ``users_db.get_user_valid_subscription`` and
``config.plan_catalog.PAID_PLAN_TYPES``; an unrecognized or malformed plan
value is *not* basic — it is the bounded identification fail-open
(``plan_unknown_fail_open``). Inactive ``None`` from the lookup stays basic.
BYOK reuses ``users_db.is_byok_active`` plus the request-scoped helpers in
``utils.byok`` and ``utils.subscription.request_has_llm_byok_key``. ``system``
is uid-less background work: a system claim with a uid is denied
(``system_uid_forbidden``); omi/byok without a uid is ``uid_required``. No
quota or allowlist is read from the environment.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import database.users as users_db
from config.plan_catalog import PAID_PLAN_TYPES, PlanType, WIRE_PLAN_ALIASES
from utils.byok import get_byok_key, has_validated_byok_keys
from utils.llm.model_config import get_all_configured_features, get_provider
from utils.subscription import request_has_llm_byok_key

logger = logging.getLogger(__name__)

# Sentinel for "the caller did not pass one; read it" — distinct from None,
# which is a real answer (no valid subscription / not enrolled).
_UNRESOLVED: Any = object()

FUNDING_OWNERS: tuple[str, ...] = ('omi', 'byok', 'system')

# Exact-name free features. Everything else managed is denied for basic +
# non-BYOK, except names starting with ``chat_``. Realtime is quota-funded
# separately and is not on this list.
FREE_ALLOWLIST_FEATURES: frozenset[str] = frozenset(
    {
        'daily_summary',
        'translation',
        'session_titles',
        'fair_use',
    }
)
FREE_ALLOWLIST_PREFIX = 'chat_'

DECISION_REASONS: frozenset[str] = frozenset(
    {
        'unknown_feature',
        'invalid_funding_owner',
        'uid_required',
        'system_uid_forbidden',
        'free_allowlist',
        'system_feature_not_free',
        'byok',
        'byok_not_validated',
        'byok_not_enrolled',
        'plan_paid',
        'basic_not_entitled',
        'plan_unknown_fail_open',
        'authorization_unavailable',
    }
)


@dataclass(frozen=True)
class Decision:
    """The one answer to "may this request spend Omi-billed (or BYOK) compute?".

    ``plan`` is ``None`` only when the plan could not be identified (system
    work, unknown feature, fail-open identification, junk on the BYOK path,
    or a deny that never needed it). ``reason`` is a low-cardinality label
    from ``DECISION_REASONS``.
    """

    allowed: bool
    reason: str
    feature: str
    funding_owner: str
    plan: PlanType | None
    plan_resolved: bool

    def raise_if_denied(self) -> Decision:
        if not self.allowed:
            raise ManagedComputeDenied(self)
        return self

    def as_dict(self) -> dict[str, Any]:
        return {
            'allowed': self.allowed,
            'reason': self.reason,
            'feature': self.feature,
            'funding_owner': self.funding_owner,
            'plan': self.plan.value if self.plan is not None else None,
            'plan_resolved': self.plan_resolved,
        }


class ManagedComputeDenied(Exception):
    """Explicit deny for a managed-compute request. Callers (S2) map this to 402."""

    def __init__(self, decision: Decision):
        self.decision = decision
        super().__init__(decision.reason)


def _is_free_allowlisted(feature: str) -> bool:
    return feature in FREE_ALLOWLIST_FEATURES or feature.startswith(FREE_ALLOWLIST_PREFIX)


def _decision(
    *,
    allowed: bool,
    reason: str,
    feature: str,
    funding_owner: str,
    plan: PlanType | None,
    plan_resolved: bool,
) -> Decision:
    return Decision(
        allowed=allowed,
        reason=reason,
        feature=feature,
        funding_owner=funding_owner,
        plan=plan,
        plan_resolved=plan_resolved,
    )


def request_carries_validated_byok_key(feature: str) -> bool:
    """True when this request carries a validated key for the feature's provider.

    Reuses the existing helpers; does not re-implement fingerprint checks.
    The provider key must actually be on the request so a validated OpenAI
    header cannot fund a different provider's feature.
    """
    if not has_validated_byok_keys():
        return False
    if not get_byok_key(get_provider(feature)):
        return False
    return request_has_llm_byok_key()


class _PlanNotIdentified(Exception):
    """A subscription was present but its plan value is not a known PlanType."""


def _identified_plan(plan: Any) -> PlanType | None:
    """A known ``PlanType``, or ``None`` when the value cannot be identified.

    Unknown strings are not coerced to basic: ``PlanType``'s ``_missing_``
    returns ``None`` rather than raising, and a forward-version plan must
    take the identification fail-open instead.
    """
    if isinstance(plan, PlanType):
        return plan
    if not isinstance(plan, str):
        return None
    for member in PlanType:
        if member.value == plan:
            return member
    return WIRE_PLAN_ALIASES.get(plan)


def _resolve_plan(uid: str, subscription: Any) -> tuple[PlanType, bool]:
    """Return ``(plan, True)``. ``None`` from the lookup is inactive basic.

    An unrecognized plan value raises ``_PlanNotIdentified`` so the omi path
    can take the bounded identification fail-open rather than pretending the
    user is basic.
    """
    if subscription is _UNRESOLVED:
        subscription = users_db.get_user_valid_subscription(uid)
    if subscription is None:
        return PlanType.basic, True
    plan = _identified_plan(getattr(subscription, 'plan', None))
    if plan is None:
        raise _PlanNotIdentified
    return plan, True


def authorize_managed_compute(
    uid: str | None,
    feature: str,
    funding_owner: str,
    *,
    subscription: Any = _UNRESOLVED,
    byok_active: Any = _UNRESOLVED,
) -> Decision:
    """Allow or deny one managed-compute request. Never raises.

    ``subscription`` / ``byok_active`` let a caller that has already read the
    valid subscription (``None`` when there is none) and BYOK enrolment pass
    them in so this answer and the caller's snapshot come from the same reads.
    """
    try:
        return _authorize(
            uid,
            feature,
            funding_owner,
            subscription=subscription,
            byok_active=byok_active,
        )
    except Exception as exc:
        logger.warning('managed compute authorization unavailable: %s', type(exc).__name__)
        return _decision(
            allowed=False,
            reason='authorization_unavailable',
            feature=feature,
            funding_owner=funding_owner,
            plan=None,
            plan_resolved=False,
        )


def _authorize(
    uid: str | None,
    feature: str,
    funding_owner: str,
    *,
    subscription: Any,
    byok_active: Any,
) -> Decision:
    if feature not in get_all_configured_features():
        return _decision(
            allowed=False,
            reason='unknown_feature',
            feature=feature,
            funding_owner=funding_owner,
            plan=None,
            plan_resolved=False,
        )
    if funding_owner not in FUNDING_OWNERS:
        return _decision(
            allowed=False,
            reason='invalid_funding_owner',
            feature=feature,
            funding_owner=funding_owner,
            plan=None,
            plan_resolved=False,
        )
    if funding_owner != 'system' and not uid:
        return _decision(
            allowed=False,
            reason='uid_required',
            feature=feature,
            funding_owner=funding_owner,
            plan=None,
            plan_resolved=False,
        )
    if funding_owner == 'system':
        if uid:
            return _decision(
                allowed=False,
                reason='system_uid_forbidden',
                feature=feature,
                funding_owner=funding_owner,
                plan=None,
                plan_resolved=False,
            )
        if _is_free_allowlisted(feature):
            return _decision(
                allowed=True,
                reason='free_allowlist',
                feature=feature,
                funding_owner=funding_owner,
                plan=None,
                plan_resolved=False,
            )
        return _decision(
            allowed=False,
            reason='system_feature_not_free',
            feature=feature,
            funding_owner=funding_owner,
            plan=None,
            plan_resolved=False,
        )
    if funding_owner == 'byok':
        return _authorize_byok(
            uid or '',
            feature,
            subscription=subscription,
            byok_active=byok_active,
        )
    return _authorize_omi(uid or '', feature, subscription=subscription)


def _authorize_byok(
    uid: str,
    feature: str,
    *,
    subscription: Any,
    byok_active: Any,
) -> Decision:
    try:
        if not request_carries_validated_byok_key(feature):
            return _decision(
                allowed=False,
                reason='byok_not_validated',
                feature=feature,
                funding_owner='byok',
                plan=None,
                plan_resolved=False,
            )
        if byok_active is _UNRESOLVED:
            byok_active = users_db.is_byok_active(uid)
        if not byok_active:
            return _decision(
                allowed=False,
                reason='byok_not_enrolled',
                feature=feature,
                funding_owner='byok',
                plan=None,
                plan_resolved=False,
            )
    except Exception as exc:
        logger.warning('managed compute authorization unavailable: %s', type(exc).__name__)
        return _decision(
            allowed=False,
            reason='authorization_unavailable',
            feature=feature,
            funding_owner='byok',
            plan=None,
            plan_resolved=False,
        )
    plan, plan_resolved = _plan_if_already_read(subscription)
    return _decision(
        allowed=True,
        reason='byok',
        feature=feature,
        funding_owner='byok',
        plan=plan,
        plan_resolved=plan_resolved,
    )


def _plan_if_already_read(subscription: Any) -> tuple[PlanType | None, bool]:
    """Use a pre-read subscription on the BYOK path; never re-read.

    Inactive ``None`` is basic resolved. Unrecognized/malformed plan values
    are unresolved ``(None, False)``, never coerced to basic.
    """
    if subscription is _UNRESOLVED:
        return None, False
    if subscription is None:
        return PlanType.basic, True
    plan = _identified_plan(getattr(subscription, 'plan', None))
    if plan is None:
        return None, False
    return plan, True


def _authorize_omi(uid: str, feature: str, *, subscription: Any) -> Decision:
    try:
        plan, plan_resolved = _resolve_plan(uid, subscription)
    except Exception as exc:
        # Target 3: unknown plan at first identification → paid-path (don't
        # strip a paid user on a Firestore blip). Known feature only; unknown
        # already returned above.
        logger.warning('managed compute plan lookup failed: %s', type(exc).__name__)
        return _decision(
            allowed=True,
            reason='plan_unknown_fail_open',
            feature=feature,
            funding_owner='omi',
            plan=None,
            plan_resolved=False,
        )
    if plan in PAID_PLAN_TYPES:
        return _decision(
            allowed=True,
            reason='plan_paid',
            feature=feature,
            funding_owner='omi',
            plan=plan,
            plan_resolved=plan_resolved,
        )
    if _is_free_allowlisted(feature):
        return _decision(
            allowed=True,
            reason='free_allowlist',
            feature=feature,
            funding_owner='omi',
            plan=plan,
            plan_resolved=plan_resolved,
        )
    return _decision(
        allowed=False,
        reason='basic_not_entitled',
        feature=feature,
        funding_owner='omi',
        plan=plan,
        plan_resolved=plan_resolved,
    )


def funding_owner_for_feature(feature: str) -> str:
    """``byok`` only when this request carries a validated key for ``feature``'s provider.

    Reuses ``request_carries_validated_byok_key`` so the only dynamic
    ``get_provider(feature)`` site stays inside this module. Called only from
    inside an injected ``decision_for`` closure so a raising BYOK lookup is
    caught by the caller's exception guard.
    """
    return 'byok' if request_carries_validated_byok_key(feature) else 'omi'


def managed_compute_decision_for(uid: str) -> Callable[[str], Decision]:
    """Injected ``decision_for(feature) -> Decision`` for a free-tier policy.

    Funding owner is computed inside the closure, not before the policy call.
    A raising BYOK/provider lookup therefore becomes the policy's
    ``policy_unavailable`` (deterministic minimum / suppressed) instead of
    crashing the caller. Defined here, next to ``authorize_managed_compute``
    and the BYOK lookup it composes, so every producer of the same managed
    spend injects the same closure — the coordinator's copy moved here when
    the app-integration, X-connector and twitter-persona producers started
    consulting the memory-formation policy (flip-review F-3).
    """

    def decision_for(feature: str) -> Decision:
        owner = funding_owner_for_feature(feature)
        return authorize_managed_compute(uid, feature, owner)

    return decision_for
