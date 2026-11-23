"""Every 503 the from-segments route returns names its raise site, once.

The route's 503s come from its dependency chain as well as its handler, and the
response body is not in Cloud Logging, so the only way to attribute one is a log
line emitted at the route boundary. These tests pin: one WARNING per 503, the
tagged raise site, the serialized body length, no line for a non-503, and an
unchanged response.
"""

import json
import logging

import pytest
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from utils.llm import gateway_error_contract
from utils.other import endpoints
from utils.other.from_segments_503 import (
    FROM_SEGMENTS_503_EVENT,
    FROM_SEGMENTS_PATH,
    FromSegments503Route,
)
from utils.other.raise_site import (
    UNATTRIBUTED_RAISE_SITE,
    raise_site_of,
    serialized_detail_bytes,
    tag_raise_site,
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
    assert record.status == 503
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


def test_untagged_503_is_named_unattributed(caplog):
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
    assert lines[0].raise_site == UNATTRIBUTED_RAISE_SITE
    assert lines[0].body_bytes == 64


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
