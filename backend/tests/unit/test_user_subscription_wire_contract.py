import pytest
from pydantic import ValidationError

from models.users import PlanType, Subscription, UserSubscriptionResponse


def _response(plan: PlanType) -> UserSubscriptionResponse:
    return UserSubscriptionResponse(
        subscription=Subscription(plan=plan),
        transcription_seconds_used=0,
        transcription_seconds_limit=0,
        words_transcribed_used=0,
        words_transcribed_limit=0,
        insights_gained_used=0,
        insights_gained_limit=0,
    )


def test_subscription_response_accepts_released_client_plan_values():
    response = _response(PlanType.unlimited)

    assert response.subscription.plan is PlanType.unlimited


@pytest.mark.parametrize("plan", [PlanType.plus, PlanType.unlimited_v2])
def test_subscription_response_rejects_unshipped_mobile_plan_values(plan: PlanType):
    with pytest.raises(ValidationError):
        _response(plan)
