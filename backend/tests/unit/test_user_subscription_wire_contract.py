import pytest
from pydantic import ValidationError

from config.plan_catalog import LEGACY_WIRE_PLAN_VALUES, WIRE_FALLBACK_PLAN_TYPES
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


@pytest.mark.parametrize("plan", [plan for plan in PlanType if plan not in WIRE_FALLBACK_PLAN_TYPES])
def test_subscription_response_accepts_every_released_wire_plan_value(plan: PlanType):
    response = _response(plan)

    assert response.subscription.plan is plan


@pytest.mark.parametrize("plan", list(WIRE_FALLBACK_PLAN_TYPES))
def test_subscription_response_rejects_values_outside_released_wire_contract(plan: PlanType):
    with pytest.raises(ValidationError):
        _response(plan)


def test_subscription_schema_uses_the_generated_legacy_wire_projection():
    schema = Subscription.model_json_schema()

    assert schema['properties']['plan']['$ref'] == '#/$defs/PlanType'
    assert tuple(schema['properties']['plan']['enum']) == LEGACY_WIRE_PLAN_VALUES
    assert set(schema['$defs']['PlanType']['enum']) == {plan.value for plan in PlanType}
