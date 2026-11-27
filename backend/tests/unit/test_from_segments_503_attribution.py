"""Every 503 the from-segments route returns names its raise site, once.

The route's 503s come from its dependency chain as well as its handler, and the
response body is not in Cloud Logging, so the only way to attribute one is a log
line emitted at the route boundary. These tests pin: one line per 503, the
tagged raise site, the serialized body length, no line for a non-503, and an
unchanged response. Every reachable site is tagged; an untagged 503 is a defect
logged at ERROR, never an accepted outcome.
"""

import json
import logging

import httpx
import pytest
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from utils.conversations.processing_metrics import FROM_SEGMENTS_METRIC_ROUTE, RETRYABLE_PROCESSING_RESPONSES_TOTAL
from utils.llm import gateway_error_contract
from utils.other import endpoints
from utils.other.from_segments_503 import (
    FROM_SEGMENTS_503_EVENT,
    FROM_SEGMENTS_503_UNATTRIBUTED_EVENT,
    FROM_SEGMENTS_PATH,
    FromSegments503Route,
)
from utils.other.raise_site import (
    UNATTRIBUTED_RAISE_SITE,
    raise_site_of,
    serialized_detail_bytes,
    tag_raise_site,
)
from utils.other.request_deadline import (
    RequestDeadlineExceeded,
    reset_request_deadline,
    set_request_deadline,
)

LOGGER_NAME = 'utils.other.from_segments_503'


def _app(*, dependency_503: bool = False, handler_503: bool = True, status: int = 503) -> FastAPI:
    app = FastAPI()
    router = APIRouter(route_class=FromSegments503Route)

    def _dependency() -> None:
        if dependency_503:
            raise tag_raise_site(
                HTTPException(status_code=503, detail={'code': 'auth_deadline_exceeded', 'retryable': True}),
                'auth_deadline_exceeded',
            )

    @router.post(FROM_SEGMENTS_PATH)
    def _route(_guard: None = Depends(_dependency)) -> dict:
        if handler_503:
            raise tag_raise_site(
                HTTPException(
                    status_code=status,
                    detail=gateway_error_contract.RETRYABLE_CONVERSATION_PROCESSING_ERROR_DETAIL,
                    headers={'Retry-After': '2'},
                ),
                'conversation_processing_retryable',
            )
        return {'ok': True}

    app.include_router(router)
    return app


def _lines(caplog) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == LOGGER_NAME]


def test_handler_503_logs_one_line_with_site_and_body_bytes(caplog):
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)
    response = TestClient(_app()).post(FROM_SEGMENTS_PATH, json={})

    assert response.status_code == 503
    assert response.headers['Retry-After'] == '2'
    lines = _lines(caplog)
    assert len(lines) == 1
    record = lines[0]
    assert record.levelno == logging.WARNING
    assert record.event == FROM_SEGMENTS_503_EVENT
    assert record.route == FROM_SEGMENTS_PATH
    assert record.http_status == 503
    assert record.raise_site == 'conversation_processing_retryable'
    assert record.body_bytes == serialized_detail_bytes(
        gateway_error_contract.RETRYABLE_CONVERSATION_PROCESSING_ERROR_DETAIL
    )
    assert record.body_bytes == len(response.content)


def test_dependency_503_is_attributed_too(caplog):
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)
    response = TestClient(_app(dependency_503=True, handler_503=False)).post(FROM_SEGMENTS_PATH, json={})

    assert response.status_code == 503
    lines = _lines(caplog)
    assert len(lines) == 1
    assert lines[0].raise_site == 'auth_deadline_exceeded'
    assert lines[0].body_bytes == len(response.content)


@pytest.mark.parametrize(
    ('error_factory', 'failure_class'),
    [
        (
            lambda: gateway_error_contract.retryable_processing_response('from_segments_processing_in_flight'),
            'other',
        ),
        (lambda: gateway_error_contract.retryable_processing_response('request_budget_exhausted'), 'timeout'),
        (lambda: gateway_error_contract.conversation_processing_http_exception(TimeoutError('slow')), 'timeout'),
        (lambda: gateway_error_contract.conversation_processing_http_exception(httpx.ReadError('lost')), 'transport'),
    ],
    ids=['in-flight', 'request-budget', 'provider-timeout', 'provider-transport'],
)
def test_from_segments_counts_each_retryable_response_once(error_factory, failure_class):
    app = FastAPI()
    router = APIRouter(route_class=FromSegments503Route)

    @router.post(FROM_SEGMENTS_PATH)
    def _route():
        raise error_factory()

    app.include_router(router)
    metric = RETRYABLE_PROCESSING_RESPONSES_TOTAL.labels(failure_class=failure_class, route=FROM_SEGMENTS_METRIC_ROUTE)
    generic = RETRYABLE_PROCESSING_RESPONSES_TOTAL.labels(failure_class=failure_class, route='conversation_processing')
    before = metric._value.get()
    generic_before = generic._value.get()

    response = TestClient(app).post(FROM_SEGMENTS_PATH)

    assert response.status_code == 503
    assert response.headers['Retry-After'] == '2'
    assert response.json() == {'detail': gateway_error_contract.RETRYABLE_CONVERSATION_PROCESSING_ERROR_DETAIL}
    assert metric._value.get() == before + 1
    assert generic._value.get() == generic_before


def test_processing_counter_excludes_other_responses():
    def sample():
        return {
            tuple(sorted(item.labels.items())): item.value
            for metric in RETRYABLE_PROCESSING_RESPONSES_TOTAL.collect()
            for item in metric.samples
            if item.name.endswith('_total')
        }

    app = FastAPI()
    router = APIRouter(route_class=FromSegments503Route)

    @router.post(FROM_SEGMENTS_PATH)
    def _route():
        # Mapping a provider failure that never leaves the route is not a 503 response.
        gateway_error_contract.conversation_processing_http_exception(TimeoutError('handled'))
        return {'ok': True}

    app.include_router(router)
    before = sample()

    assert TestClient(app).post(FROM_SEGMENTS_PATH).status_code == 200
    assert TestClient(_app(dependency_503=True)).post(FROM_SEGMENTS_PATH).status_code == 503
    assert TestClient(_app(status=422)).post(FROM_SEGMENTS_PATH).status_code == 422
    assert sample() == before


def test_untagged_503_is_a_defect_marker_not_an_accepted_outcome(caplog):
    """Every reachable site is tagged; an untagged 503 is alertable, not normal."""
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)
    app = FastAPI()
    router = APIRouter(route_class=FromSegments503Route)

    @router.post(FROM_SEGMENTS_PATH)
    def _route() -> dict:
        raise HTTPException(status_code=503, detail='Service temporarily unavailable. Try again shortly.')

    app.include_router(router)
    response = TestClient(app).post(FROM_SEGMENTS_PATH, json={})

    assert response.status_code == 503
    lines = _lines(caplog)
    assert len(lines) == 1
    assert lines[0].levelno == logging.ERROR
    assert lines[0].event == FROM_SEGMENTS_503_UNATTRIBUTED_EVENT
    assert lines[0].raise_site == UNATTRIBUTED_RAISE_SITE
    assert lines[0].body_bytes == 64


def test_every_reachable_503_site_is_tagged():
    """The route's dependency chain has no untagged 503 left."""
    for expected, exc in _reachable_503_sites().items():
        assert exc.status_code == 503, expected
        assert raise_site_of(exc) == expected
        assert raise_site_of(exc) != UNATTRIBUTED_RAISE_SITE


def test_no_reachable_503_logs_unattributed(caplog):
    """Drive each enumerated site through the route hook and read the line."""
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)
    for expected, exc in _reachable_503_sites().items():
        caplog.clear()
        app = FastAPI()
        router = APIRouter(route_class=FromSegments503Route)

        def _make_route(error: HTTPException):
            def _route() -> dict:
                raise error

            return _route

        router.add_api_route(FROM_SEGMENTS_PATH, _make_route(exc), methods=['POST'])
        app.include_router(router)
        response = TestClient(app).post(FROM_SEGMENTS_PATH, json={})

        assert response.status_code == 503, expected
        lines = _lines(caplog)
        assert len(lines) == 1, expected
        assert lines[0].raise_site == expected
        assert lines[0].raise_site != UNATTRIBUTED_RAISE_SITE


def _account_deletion_503():
    from utils.other import endpoints as endpoints_module

    original = endpoints_module.get_user_deletion_wipe_status

    def _boom(uid):
        raise RuntimeError('authority down')

    endpoints_module.get_user_deletion_wipe_status = _boom
    try:
        with pytest.raises(HTTPException) as raised:
            endpoints_module._account_deletion_status('uid1')
    finally:
        endpoints_module.get_user_deletion_wipe_status = original
    return raised.value


def _directory_routing_503():
    from database import directory as directory_module

    original_active = directory_module.router.routing_active
    original_resolve = directory_module.router.resolve

    def _active():
        return True

    def _resolve(*args, **kwargs):
        raise directory_module.router.DirectoryRoutingUnavailable('down')

    directory_module.router.routing_active = _active
    directory_module.router.resolve = _resolve
    try:
        with pytest.raises(HTTPException) as raised:
            endpoints._resolve_request_plane_or_503('uid1')
    finally:
        directory_module.router.routing_active = original_active
        directory_module.router.resolve = original_resolve
    return raised.value


def _rate_limiter_503():
    with pytest.raises(HTTPException) as raised:
        endpoints._enforce_rate_limit('key', 'conversations:from-segments', fail_closed=True)
    return raised.value


def _cutover_503():
    from models.account_cutover import AccountCutoverClientAction
    from utils.account_cutover import access as cutover_access

    original = cutover_access.evaluate_account_cutover_access

    def _deny(*args, **kwargs):
        raise cutover_access.AccountCutoverAccessDenial(
            code='account_cutover_state_unavailable',
            detail={'code': 'account_cutover_state_unavailable', 'retryable': True},
            client_action=AccountCutoverClientAction.migration_maintenance,
        )

    cutover_access.evaluate_account_cutover_access = _deny
    try:
        with pytest.raises(HTTPException) as raised:
            cutover_access.enforce_account_cutover_http_access(
                'uid1', method='POST', path=FROM_SEGMENTS_PATH, headers={}
            )
    finally:
        cutover_access.evaluate_account_cutover_access = original
    return raised.value


def _auth_deadline_503():
    token = set_request_deadline(0.0)
    try:
        with pytest.raises(HTTPException) as raised:
            endpoints._enforce_auth_deadline()
    finally:
        reset_request_deadline(token)
    return raised.value


def _reachable_503_sites() -> dict[str, HTTPException]:
    return {
        'executor_saturated': endpoints._executor_saturated_http_exception(endpoints.ExecutorSaturatedError('full')),
        'account_deletion_state_unavailable': _account_deletion_503(),
        'directory_routing_unavailable': _directory_routing_503(),
        'rate_limiter_unavailable': _rate_limiter_503(),
        'account_cutover_state_unavailable': _cutover_503(),
        'conversation_processing_retryable': gateway_error_contract.conversation_processing_http_exception(
            TimeoutError('slow')
        ),
        'request_budget_exhausted': gateway_error_contract.conversation_processing_http_exception(
            RequestDeadlineExceeded('spent')
        ),
        'from_segments_processing_in_flight': gateway_error_contract.retryable_processing_response(
            'from_segments_processing_in_flight'
        ),
        'auth_deadline_exceeded': _auth_deadline_503(),
    }


@pytest.mark.parametrize('status', [200, 422])
def test_non_503_emits_no_line(caplog, status):
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)
    app = FastAPI()
    router = APIRouter(route_class=FromSegments503Route)

    @router.post(FROM_SEGMENTS_PATH)
    def _route() -> dict:
        raise HTTPException(status_code=status, detail='nope')

    app.include_router(router)
    TestClient(app).post(FROM_SEGMENTS_PATH, json={})

    assert _lines(caplog) == []


def test_log_line_carries_no_request_content(caplog):
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)
    TestClient(_app()).post(
        FROM_SEGMENTS_PATH,
        json={'transcript_segments': [{'text': 'private words', 'start': 0.0, 'end': 1.0}]},
        headers={'Authorization': 'Bearer secret-token'},
    )

    line = _lines(caplog)[0]
    rendered = json.dumps({key: value for key, value in line.__dict__.items() if key != 'msg'}, default=str)
    for forbidden in ('private words', 'secret-token', 'transcript_segments'):
        assert forbidden not in rendered


def test_enumerated_raise_sites_serialize_to_the_measured_lengths():
    """The evidence's 64/73/68/37/133-byte bodies, so a 279-byte body stands out."""
    assert serialized_detail_bytes('Service temporarily unavailable. Try again shortly.') == 64
    assert serialized_detail_bytes({'code': 'account_deletion_state_unavailable', 'retryable': True}) == 73
    assert serialized_detail_bytes({'code': 'directory_routing_unavailable', 'retryable': True}) == 68
    assert serialized_detail_bytes('Rate limiter unavailable') == 37
    assert serialized_detail_bytes(gateway_error_contract.RETRYABLE_CONVERSATION_PROCESSING_ERROR_DETAIL) == 133


def test_raise_site_tag_survives_the_exception_object():
    exc = tag_raise_site(HTTPException(status_code=503, detail='x'), 'executor_saturated')
    assert raise_site_of(exc) == 'executor_saturated'
    assert raise_site_of(HTTPException(status_code=503, detail='x')) == UNATTRIBUTED_RAISE_SITE


def test_endpoints_503_sites_are_tagged():
    saturated = endpoints._executor_saturated_http_exception(endpoints.ExecutorSaturatedError('full'))
    assert saturated.status_code == 503
    assert raise_site_of(saturated) == 'executor_saturated'

    with pytest.raises(HTTPException) as rate_limited:
        endpoints._enforce_rate_limit('key', 'conversations:from-segments', fail_closed=True)
    assert raise_site_of(rate_limited.value) == 'rate_limiter_unavailable'


def test_conversation_processing_503_is_tagged():
    exc = gateway_error_contract.conversation_processing_http_exception(TimeoutError('slow'))
    assert exc.status_code == 503
    assert raise_site_of(exc) == 'conversation_processing_retryable'
