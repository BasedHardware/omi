"""Shared telemetry for reserved Gemini request-rejection recovery via Luna."""

from llm_gateway.gateway.resolver import is_lkg_eligible
from llm_gateway.gateway.schemas import CredentialMode, FailureClass, ProviderRef, RouteArtifact
from utils.observability.fallback import record_fallback


def record_reserved_rejection_fallback(
    route: RouteArtifact, reason: FailureClass | str | None, *, outcome: str
) -> None:
    if (
        reason == FailureClass.PROVIDER_INVALID_REQUEST
        and route.primary.provider == 'gemini'
        and route.provider_options.get('reserved_capacity_only') is True
    ):
        # The gateway terminal metric retains provider_invalid_request; the
        # cross-component helper buckets this reason to its fixed 'other' label.
        record_fallback(
            component='llm_gateway',
            from_mode='gemini',
            to_mode='openai',
            reason='other',
            outcome=outcome,
        )


def can_try_next_provider(route: RouteArtifact, failed: ProviderRef, reason: FailureClass | str | None) -> bool:
    if reason == FailureClass.PROVIDER_INVALID_REQUEST:
        # This exception is strictly Gemini -> Luna inside one reserved route.
        # Invalid requests remain ineligible for cross-route/LKG failover.
        return (
            route.credential_policy.mode == CredentialMode.OMI_PAID
            and failed == route.primary
            and failed.provider == 'gemini'
            and route.provider_options.get('reserved_capacity_only') is True
            and route.fallbacks == [ProviderRef(provider='openai', model='gpt-6-luna')]
            and FailureClass.PROVIDER_INVALID_REQUEST in route.fallback_policy.fallback_on
            and FailureClass.PROVIDER_INVALID_REQUEST not in route.fallback_policy.never_fallback_on
            and FailureClass.PROVIDER_INVALID_REQUEST in route.credential_policy.fallback_eligible_failure_classes
            and FailureClass.PROVIDER_INVALID_REQUEST not in route.credential_policy.never_fallback_failure_classes
        )
    return reason is not None and is_lkg_eligible(route, reason)
