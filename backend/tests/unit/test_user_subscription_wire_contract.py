import pytest
from pydantic import ValidationError

from config.plan_catalog import PLAN_TYPE_VALUES
from models.users import HeldAudioSummary, PlanType, Subscription, UserSubscriptionResponse
from routers.payment import PaymentSubscriptionResponse


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


@pytest.mark.parametrize("plan", list(PlanType))
def test_subscription_response_accepts_every_catalog_plan_value(plan: PlanType):
    response = _response(plan)

    assert response.subscription.plan is plan


@pytest.mark.parametrize("plan", ["unknown", "invalid"])
def test_subscription_response_rejects_values_outside_catalog(plan: str):
    with pytest.raises(ValidationError):
        _response(plan)


def test_flag_off_subscription_json_omits_held_audio():
    payload = _response(PlanType.basic).model_dump(mode='json')
    assert 'held_audio' not in payload


def test_held_audio_is_present_when_the_server_sets_it():
    response = _response(PlanType.basic)
    response.held_audio = HeldAudioSummary(seconds=12, reset_at=1, retain_live=True, count=3)
    payload = response.model_dump(mode='json')
    assert payload['held_audio']['seconds'] == 12
    assert payload['held_audio']['count'] == 3


def test_subscription_schema_uses_the_catalog_enum():
    schema = Subscription.model_json_schema()

    assert schema['properties']['plan']['$ref'] == '#/$defs/PlanType'
    assert 'enum' not in schema['properties']['plan']
    assert set(schema['$defs']['PlanType']['enum']) == set(PLAN_TYPE_VALUES)


@pytest.mark.parametrize('plan', ['plus', 'unlimited_v2'])
def test_payment_response_already_accepts_catalog_ids(plan):
    assert PaymentSubscriptionResponse(plan=plan).model_dump()['plan'] == plan


def test_export_publishes_capable_catalog_schema_and_preserves_checked_legacy_response():
    import copy
    from fastapi import FastAPI
    from scripts import export_openapi, check_app_client_openapi_compatibility
    from config.plan_catalog import LEGACY_WIRE_PLAN_VALUES

    app = FastAPI()
    app.add_api_route('/v1/users/me/subscription', lambda: None, response_model=UserSubscriptionResponse)
    schema = app.openapi()
    base = copy.deepcopy(schema)
    base['components']['schemas']['Subscription']['properties']['plan']['enum'] = list(LEGACY_WIRE_PLAN_VALUES)
    export_openapi._publish_negotiated_plan_identity(schema)
    components = schema['components']['schemas']
    assert components['Subscription']['properties']['plan']['enum'] == list(LEGACY_WIRE_PLAN_VALUES)
    assert 'enum' not in components['PlanIdentitySubscription']['properties']['plan']
    assert set(components['PlanType']['enum']) == set(PLAN_TYPE_VALUES)
    operation = schema['paths']['/v1/users/me/subscription']['get']
    assert operation['responses']['200']['content']['application/json']['schema']['$ref'].endswith(
        '/UserSubscriptionResponse'
    )
    assert operation['x-omi-plan-identity-response']['schema']['$ref'].endswith('/PlanIdentityUserSubscriptionResponse')
    assert check_app_client_openapi_compatibility.compare_specs(base, schema) == []
    # The default released response is still fully checked, not exempted.
    components['Subscription']['properties']['plan']['enum'].append('plus')
    assert check_app_client_openapi_compatibility.compare_specs(base, schema)


@pytest.mark.parametrize('flag', ['false', 'true'])
def test_actual_subscription_http_serialization_preserves_other_nulls(monkeypatch, flag):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import users as route
    from utils.sync import held_audio_summary

    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', flag)
    monkeypatch.setattr(route, '_user_subscription_response', lambda *a: _response(PlanType.basic))
    allowance = SimpleNamespace(
        managed=True,
        remaining_seconds=None,
        limit_seconds=None,
        as_dict=lambda: {'mode': 'managed', 'remaining_seconds': None, 'reason': 'available'},
    )
    monkeypatch.setattr(route, 'resolve_transcription_allowance', lambda *a, **kw: allowance)
    monkeypatch.setattr(route.funded_processing, 'allowance', lambda *a, **kw: allowance)
    monkeypatch.setattr(route.processing_backlog.store, 'read', lambda uid: {})
    monkeypatch.setattr(route, 'fresh_cache_reads', lambda *a: nullcontext())
    monkeypatch.setattr(held_audio_summary, '_load_summary', lambda uid: {'version': 2, 'seconds': 12, 'count': 1})
    monkeypatch.setattr(held_audio_summary, '_load_rows', lambda uid: [{'id': 'a', 'started_at': 20, 'seconds': 12}])
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route.auth.get_current_user_uid_no_byok_validation] = lambda: 'synthetic'
    with TestClient(app) as client:
        response = client.get('/v1/users/me/subscription')
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['phone_call_quota'] is None  # Do not globally exclude nulls.
    if flag == 'true':
        assert payload['held_audio']['state'] == 'recovering'
        assert payload['held_audio']['seconds'] == 12
        assert payload['processing_backlog']['state'] == 'waiting_choice'
    else:
        assert 'held_audio' not in payload
