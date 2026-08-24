from __future__ import annotations

import pytest
import utils.jit_first_open_policy as policy

from utils.jit_first_open_policy import (
    FirstOpenClientTier,
    FirstOpenOutcome,
    FirstOpenState,
    resolve_authorized_first_open_plan,
    resolve_first_open_plan,
    transition_first_open,
)


class _AuthorityDecision:
    def __init__(self, permits_work: bool) -> None:
        self.permits_work = permits_work
        self.kill_switch = "off"


def test_backend_authority_enrolls_without_a_client_cohort_input() -> None:
    async def authority(uid: str) -> _AuthorityDecision:
        assert uid == "owner"
        return _AuthorityDecision(True)

    plan = resolve_authorized_first_open_plan(uid="owner", source="desktop", authority=authority)

    assert plan.defer_derived_work is True
    assert plan.client_tier is FirstOpenClientTier.DESKTOP


def test_authority_error_fails_closed_to_legacy_eager_processing() -> None:
    async def authority(_uid: str) -> _AuthorityDecision:
        raise RuntimeError("authority unavailable")

    plan = resolve_authorized_first_open_plan(uid="owner", source="mobile", authority=authority)

    assert plan.enabled is False
    assert plan.defer_derived_work is False


def test_outstanding_obligation_forces_fresh_paid_boundary_authority(monkeypatch) -> None:
    observed: list[dict[str, object]] = []

    def resolve(**kwargs):
        observed.append(kwargs)
        return type("Plan", (), {"defer_derived_work": False})()

    monkeypatch.setattr(policy, "resolve_authorized_first_open_plan", resolve)

    assert policy.outstanding_first_open_work_permitted(uid="owner", source="desktop") is False
    assert observed == [{"uid": "owner", "source": "desktop", "force_refresh": True}]


@pytest.mark.parametrize("tier", list(FirstOpenClientTier))
@pytest.mark.parametrize("source", ["desktop", "mobile", "phone", "omi", "web", "windows"])
def test_enabled_plan_defers_all_expensive_fanout_but_keeps_cheap_projections(
    tier: FirstOpenClientTier, source: str
) -> None:
    plan = resolve_first_open_plan(feature_enabled=True, client_tier=tier, source=source)

    assert plan.enabled is True
    assert plan.defer_derived_work is True
    assert plan.summary_eager is True
    assert plan.retrieval_index_eager is True
    assert plan.folder_assignment_on_first_open is True
    assert plan.goal_progress_on_first_open is True
    assert plan.app_fanout_on_first_open is True


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"feature_enabled": False, "client_tier": "free", "source": "desktop"}, "rollout_disabled"),
        (
            {"feature_enabled": True, "kill_switch": True, "client_tier": "free", "source": "desktop"},
            "kill_switch",
        ),
        ({"feature_enabled": True, "client_tier": "unknown", "source": "desktop"}, "unsupported_tier"),
        ({"feature_enabled": True, "client_tier": "free", "source": "watch"}, "unsupported_source"),
    ],
)
def test_unknown_or_off_authority_never_partially_defers(kwargs: dict[str, object], reason: str) -> None:
    plan = resolve_first_open_plan(**kwargs)

    assert plan.enabled is False
    assert plan.reason == reason
    assert plan.defer_derived_work is False
    assert plan.summary_eager is False
    assert plan.retrieval_index_eager is False


def test_tier_and_source_normalization_is_content_free() -> None:
    plan = resolve_first_open_plan(feature_enabled=True, client_tier="  PAID ", source=" Desktop ")

    assert plan.client_tier is FirstOpenClientTier.PAID
    assert plan.source == "desktop"


def test_repeated_open_does_not_duplicate_first_open_work() -> None:
    claimed = transition_first_open(FirstOpenState.PENDING, event="open")
    repeated = transition_first_open(claimed.state, event="open", attempt=claimed.attempt)
    completed = transition_first_open(claimed.state, event="succeeded", attempt=claimed.attempt)
    after_complete = transition_first_open(completed.state, event="open", attempt=completed.attempt)

    assert claimed.outcome is FirstOpenOutcome.CLAIMED
    assert claimed.attempt == 1
    assert repeated.outcome is FirstOpenOutcome.ALREADY_IN_FLIGHT
    assert repeated.attempt == 1
    assert completed.outcome is FirstOpenOutcome.ALREADY_COMPLETE
    assert completed.state is FirstOpenState.COMPLETE
    assert after_complete.outcome is FirstOpenOutcome.ALREADY_COMPLETE


def test_failure_releases_claim_for_a_later_open_without_losing_attempt_count() -> None:
    claimed = transition_first_open("pending", event="open")
    failed = transition_first_open(claimed.state, event="failed", attempt=claimed.attempt)
    retry = transition_first_open(failed.state, event="open", attempt=failed.attempt)

    assert failed.outcome is FirstOpenOutcome.RETRY_READY
    assert failed.state is FirstOpenState.PENDING
    assert failed.attempt == 1
    assert retry.outcome is FirstOpenOutcome.CLAIMED
    assert retry.attempt == 2


@pytest.mark.parametrize("event", ["succeeded", "failed"])
def test_terminal_events_without_a_claim_fail_closed(event: str) -> None:
    transition = transition_first_open(FirstOpenState.PENDING, event=event)  # type: ignore[arg-type]

    assert transition.outcome is FirstOpenOutcome.INVALID
    assert transition.state is FirstOpenState.PENDING


def test_malformed_state_and_attempt_are_safe() -> None:
    transition = transition_first_open("future-state", event="open", attempt=-100)

    assert transition.outcome is FirstOpenOutcome.INVALID
    assert transition.state is FirstOpenState.PENDING
    assert transition.attempt == 0
