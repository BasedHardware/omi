"""Spend attribution for the two surfaces that bypass the LLM gateway.

Shard S0 of the local-models free tier: a synthetic direct desktop-proxy call
and a synthetic realtime relay turn must land in the gateway's own
``llm_gateway_attempts`` ledger and be answerable per uid, per feature. Each
test here pins one link of that chain; the two end-to-end tests are the
shard's proof run hermetically against a fake Firestore.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest
from google.api_core.exceptions import AlreadyExists
from starlette.requests import Request

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import database._client as firestore_client_module
from database.llm_gateway_accounting import ATTEMPTS_COLLECTION
from llm_gateway.gateway.accounting import CostStatus, PricedUsage, ProviderResponseMetadata, ProviderUsage, UsageStatus
from routers import desktop_proxy, omni_relay
from utils.llm import managed_spend_ledger as ledger
from utils.llm.managed_spend_ledger import (
    DESKTOP_PROXY_CALLER,
    DESKTOP_REALTIME_FEATURE,
    OMNI_RELAY_CALLER,
    ManagedAttempt,
)

UID = 'user-s0'
TODAY = datetime.now(timezone.utc).date().isoformat()


# --- fakes -------------------------------------------------------------------


class _FakeSnapshot:
    def __init__(self, data: dict[str, Any] | None) -> None:
        self.exists = data is not None
        self._data = data

    def to_dict(self) -> dict[str, Any] | None:
        return self._data


class _FakeDocument:
    def __init__(self, documents: dict[str, dict[str, Any]], document_id: str) -> None:
        self._documents = documents
        self._id = document_id

    def create(self, data: dict[str, Any]) -> None:
        if self._id in self._documents:
            raise AlreadyExists('attempt already exists')
        self._documents[self._id] = dict(data)

    def get(self, _fields: list[str] | None = None) -> _FakeSnapshot:
        return _FakeSnapshot(self._documents.get(self._id))


class _FakeCollection:
    def __init__(self, documents: dict[str, dict[str, Any]]) -> None:
        self.documents = documents

    def document(self, document_id: str) -> _FakeDocument:
        return _FakeDocument(self.documents, document_id)


class _FakeFirestoreClient:
    def __init__(self, *, subscription_plan: str | None = 'basic') -> None:
        users = {UID: {'subscription': {'plan': subscription_plan}}} if subscription_plan else {}
        self.collections: dict[str, dict[str, dict[str, Any]]] = {ATTEMPTS_COLLECTION: {}, 'users': users}

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self.collections.setdefault(name, {}))

    def spend_rows(self, *, uid: str, feature: str, date: str = TODAY) -> list[dict[str, Any]]:
        """The per-uid-per-feature query the proofs run (three equality filters)."""
        return [
            row
            for row in self.collections[ATTEMPTS_COLLECTION].values()
            if row.get('user_uid') == uid and row.get('feature') == feature and row.get('date') == date
        ]


@pytest.fixture
def ledger_client(monkeypatch) -> _FakeFirestoreClient:
    """Accounting on, writes routed to a fake customer-plane Firestore."""
    client = _FakeFirestoreClient()
    monkeypatch.setenv(ledger.ACCOUNTING_ENABLED_ENV_VAR, 'true')
    monkeypatch.setattr(firestore_client_module, 'get_customer_firestore_client', lambda: client)
    return client


def _attempt(**overrides: Any) -> ManagedAttempt:
    base: dict[str, Any] = dict(
        request_id='req-1',
        caller=DESKTOP_PROXY_CALLER,
        user_uid=UID,
        feature='desktop_proactivity',
        api_surface='gemini_generateContent',
        payer='omi',
        provider='gemini',
        configured_model='gemini-2.5-flash',
        outcome='success',
    )
    base.update(overrides)
    return ManagedAttempt(**base)


# --- event construction ----------------------------------------------------------


def test_event_carries_attribution_and_groups_by_invocation_ordinal() -> None:
    event = ledger.build_managed_attempt_event(_attempt(invocation_id='session-1', ordinal=3))

    assert event.attempt_id == 'session-1:3'
    assert event.invocation_id == 'session-1'
    assert (event.user_uid, event.feature, event.caller, event.payer) == (
        UID,
        'desktop_proactivity',
        'desktop_proxy',
        'omi',
    )
    assert event.app_platform == 'desktop'
    assert event.usage_status == UsageStatus.NOT_REPORTED
    assert event.cost_status == CostStatus.UNPRICED


def test_reported_usage_is_priced_on_the_gateway_rate_card() -> None:
    usage = ProviderUsage(
        prompt_tokens=1_000_000, uncached_input_tokens=1_000_000, output_tokens=0, total_tokens=1_000_000
    )
    event = ledger.build_managed_attempt_event(_attempt(metadata=ProviderResponseMetadata(usage=usage)))

    assert event.usage_status == UsageStatus.CONFIRMED
    assert event.cost_status == CostStatus.ESTIMATED
    assert event.rate_card_id == 'vertex.gemini-2.5-flash.2026-07-17'
    assert event.estimated_cost_micro_usd and event.estimated_cost_micro_usd > 0


def test_caller_priced_usage_replaces_a_missing_rate_card() -> None:
    priced = PricedUsage(
        micro_usd=1234, rate_card_id='openai.realtime.modality-rates.2026-09-01', cost_basis='realtime'
    )
    event = ledger.build_managed_attempt_event(
        _attempt(provider='openai', configured_model='gpt-realtime-2', priced=priced)
    )

    assert event.cost_status == CostStatus.ESTIMATED
    assert event.estimated_cost_micro_usd == 1234
    assert event.rate_card_id == priced.rate_card_id
    assert event.cost_basis == 'realtime'


def test_byok_stays_not_omi_cost_even_when_the_caller_priced_it() -> None:
    priced = PricedUsage(micro_usd=1234, rate_card_id='x', cost_basis='y')
    event = ledger.build_managed_attempt_event(_attempt(payer='byok', priced=priced))

    assert event.cost_status == CostStatus.NOT_OMI_COST
    assert event.estimated_cost_micro_usd == 0


def test_env_contract_is_the_gateway_sinks() -> None:
    from llm_gateway.gateway import accounting_sink

    assert ledger.ACCOUNTING_ENABLED_ENV_VAR == accounting_sink.ACCOUNTING_ENABLED_ENV_VAR
    assert ledger.ACCOUNTING_WRITE_TIMEOUT_SECONDS_ENV_VAR == accounting_sink.ACCOUNTING_WRITE_TIMEOUT_SECONDS_ENV_VAR
    assert ledger.ACCOUNTING_MAX_PENDING_TRACES_ENV_VAR == accounting_sink.ACCOUNTING_MAX_PENDING_TRACES_ENV_VAR


# --- persistence policy ------------------------------------------------------------


def test_record_writes_one_immutable_row_with_the_tier_snapshot(ledger_client) -> None:
    attempt = _attempt(invocation_id='inv-1')

    assert ledger.record_managed_attempt(attempt) is True
    assert ledger.record_managed_attempt(attempt) is False  # idempotent by attempt id

    rows = ledger_client.spend_rows(uid=UID, feature='desktop_proactivity')
    assert len(rows) == 1
    assert rows[0]['subscription_tier'] == 'basic'
    assert rows[0]['plan_id'] == 'basic'
    assert rows[0]['caller'] == 'desktop_proxy'


def test_schedule_is_inert_when_accounting_is_off(monkeypatch) -> None:
    monkeypatch.delenv(ledger.ACCOUNTING_ENABLED_ENV_VAR, raising=False)
    calls: list[ManagedAttempt] = []
    monkeypatch.setattr(ledger, 'record_managed_attempt', lambda attempt, **_: calls.append(attempt))

    async def run() -> bool:
        return ledger.schedule_managed_attempt(_attempt())

    assert asyncio.run(run()) is False
    assert calls == []


def test_schedule_without_an_event_loop_drops_instead_of_raising(monkeypatch) -> None:
    monkeypatch.setenv(ledger.ACCOUNTING_ENABLED_ENV_VAR, 'true')
    assert ledger.schedule_managed_attempt(_attempt()) is False


@pytest.mark.asyncio
async def test_schedule_persists_in_the_background_and_a_failure_never_raises(monkeypatch) -> None:
    monkeypatch.setenv(ledger.ACCOUNTING_ENABLED_ENV_VAR, 'true')
    seen: list[str] = []

    def writer(attempt: ManagedAttempt, **_: Any) -> bool:
        seen.append(attempt.request_id)
        if attempt.request_id == 'boom':
            raise RuntimeError('firestore unavailable')
        return True

    monkeypatch.setattr(ledger, 'record_managed_attempt', writer)

    assert ledger.schedule_managed_attempt(_attempt(request_id='ok')) is True
    assert ledger.schedule_managed_attempt(_attempt(request_id='boom')) is True
    await ledger.drain_pending_writes()

    assert sorted(seen) == ['boom', 'ok']
    assert not ledger._pending_writes


@pytest.mark.asyncio
async def test_shutdown_drains_and_closes_the_pool_but_allows_a_later_lifespan(monkeypatch) -> None:
    monkeypatch.setenv(ledger.ACCOUNTING_ENABLED_ENV_VAR, 'true')
    seen: list[str] = []
    monkeypatch.setattr(ledger, 'record_managed_attempt', lambda attempt, **_: seen.append(attempt.request_id) or True)

    assert ledger.schedule_managed_attempt(_attempt(request_id='before-shutdown')) is True
    await ledger.shutdown_managed_spend_ledger()
    assert seen == ['before-shutdown']
    assert ledger._ledger_executor is None

    assert ledger.schedule_managed_attempt(_attempt(request_id='after-shutdown')) is True
    await ledger.shutdown_managed_spend_ledger()
    assert seen == ['before-shutdown', 'after-shutdown']
    assert ledger._ledger_executor is None


@pytest.mark.slow
@pytest.mark.asyncio
async def test_the_pending_cap_counts_writes_until_firestore_actually_returns(monkeypatch) -> None:
    import threading

    monkeypatch.setenv(ledger.ACCOUNTING_ENABLED_ENV_VAR, 'true')
    monkeypatch.setenv(ledger.ACCOUNTING_WRITE_TIMEOUT_SECONDS_ENV_VAR, '0.01')
    monkeypatch.setenv(ledger.ACCOUNTING_MAX_PENDING_TRACES_ENV_VAR, '2')
    release = threading.Event()

    def hung_writer(attempt: ManagedAttempt, **_: Any) -> bool:
        release.wait(timeout=5)
        return True

    monkeypatch.setattr(ledger, 'record_managed_attempt', hung_writer)
    try:
        assert ledger.schedule_managed_attempt(_attempt(request_id='a')) is True
        assert ledger.schedule_managed_attempt(_attempt(request_id='b')) is True
        assert len(ledger._pending_writes) == 2
        assert ledger.schedule_managed_attempt(_attempt(request_id='c')) is False  # cap holds
    finally:
        release.set()
        await ledger.drain_pending_writes()
    assert not ledger._pending_writes


# --- desktop proxy: direct routes only -------------------------------------------------


def _request(body: bytes = b'{"contents":[{"parts":[{"text":"hello"}]}]}') -> Request:
    sent = False
    pending = asyncio.Event()

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {'type': 'http.request', 'body': body, 'more_body': False}
        await pending.wait()

    return Request(
        {
            'type': 'http',
            'method': 'POST',
            'path': '/v1/proxy/gemini/models/gemini-2.5-flash:generateContent',
            'query_string': b'',
            'headers': [(b'x-omi-request-id', b'request-12345678')],
        },
        receive,
    )


async def _never_disconnects(_request: Request) -> None:
    """Stand-in for the proxy's disconnect poll.

    The real poll cancels Starlette's ``receive`` inside an anyio scope on every
    tick; racing that with the proxy's own cancel on a second dispatch can
    swallow the cancellation and hang the test. The seam under test here is the
    ledger, not the disconnect race, so the poll is a plainly cancellable wait.
    """
    await asyncio.Event().wait()


def _telemetry(provider: str, *, uid: str | None = UID, payer: str = 'omi') -> desktop_proxy.ProxyTelemetry:
    telemetry = desktop_proxy.ProxyTelemetry(_request(), streaming=False)
    telemetry.uid = uid
    telemetry.payer = payer
    telemetry.model = 'gemini-2.5-flash'
    telemetry.action = 'generateContent'
    route = desktop_proxy.UpstreamRoute('https://provider.invalid', {}, {}, provider, 'adc', 'us-central1')
    telemetry.set_route(route)
    telemetry.note_dispatch(route)
    return telemetry


@pytest.fixture
def scheduled(monkeypatch) -> list[ManagedAttempt]:
    calls: list[ManagedAttempt] = []
    monkeypatch.setattr(desktop_proxy, 'schedule_managed_attempt', lambda attempt: calls.append(attempt) or True)
    monkeypatch.setattr(desktop_proxy.sys, 'stdout', io.StringIO())
    return calls


@pytest.mark.parametrize('provider', ['vertex_ai', 'ai_studio', 'ai_studio_byok'])
def test_direct_routes_write_one_ledger_attempt_at_the_terminal_point(scheduled, provider) -> None:
    telemetry = _telemetry(provider)
    telemetry.observe_gemini_response(
        {'usageMetadata': {'promptTokenCount': 120, 'cachedContentTokenCount': 80, 'candidatesTokenCount': 14}}
    )

    telemetry.complete(outcome='success', status_code=200, retryable=False, phase='body')
    telemetry.complete(outcome='success', status_code=200, retryable=False, phase='body')  # second call is a no-op

    assert len(scheduled) == 1
    attempt = scheduled[0]
    assert attempt.user_uid == UID
    assert attempt.feature == 'desktop_proactivity'
    assert attempt.caller == 'desktop_proxy'
    assert attempt.provider == 'gemini'
    assert attempt.configured_model == 'gemini-2.5-flash'
    assert attempt.api_surface == 'gemini_generateContent'
    assert attempt.route_artifact_id == f'desktop_proxy.{provider}'
    assert attempt.request_id == 'request-12345678'
    assert (attempt.invocation_id, attempt.ordinal, attempt.retry_ordinal, attempt.fallback_reason) == (
        telemetry.invocation_id,
        1,
        1,
        None,
    )
    assert attempt.metadata is not None and attempt.metadata.usage is not None
    assert attempt.metadata.usage.prompt_tokens == 120
    assert attempt.metadata.usage.cached_input_tokens == 80
    assert attempt.metadata.usage.output_tokens == 14


def test_a_failed_direct_attempt_is_still_an_attempt(scheduled) -> None:
    _telemetry('vertex_ai').complete(outcome='provider_error', status_code=502, retryable=False, phase='body')

    assert [(a.outcome, a.error_class) for a in scheduled] == [('error', 'provider_error')]
    assert scheduled[0].metadata is None


@pytest.mark.parametrize('provider', ['llm_gateway', 'offline_stub', 'unselected'])
def test_gateway_stub_and_unrouted_requests_write_nothing_here(scheduled, provider) -> None:
    # Positive control: the same telemetry on a direct route does write.
    _telemetry('vertex_ai').complete(outcome='success', status_code=200, retryable=False, phase='body')
    assert len(scheduled) == 1

    _telemetry(provider).complete(outcome='success', status_code=200, retryable=False, phase='body')
    assert len(scheduled) == 1


def test_a_request_with_no_uid_is_never_attributed(scheduled) -> None:
    _telemetry('vertex_ai', uid=None).complete(outcome='success', status_code=200, retryable=False, phase='body')
    assert scheduled == []


def test_a_failure_before_any_dispatch_is_not_an_attempt(scheduled) -> None:
    telemetry = desktop_proxy.ProxyTelemetry(_request(), streaming=False)
    telemetry.uid = UID
    telemetry.set_route(desktop_proxy.UpstreamRoute('https://provider.invalid', {}, {}, 'vertex_ai', 'adc', 'us'))
    # Route chosen, credentials resolved, but the body was rejected before any request left.
    telemetry.complete(outcome='validation_rejected', status_code=400, retryable=False, phase='routing')
    assert scheduled == []


def test_a_client_cancel_is_a_cancelled_attempt(scheduled) -> None:
    _telemetry('vertex_ai').complete(
        outcome='client_cancelled', status_code=499, retryable=False, phase='client_disconnect'
    )
    assert [(a.outcome, a.error_class) for a in scheduled] == [('cancelled', 'client_cancelled')]


def test_overflow_recovery_records_every_dispatch_under_one_invocation(scheduled) -> None:
    telemetry = _telemetry('vertex_ai')  # attempt 1: the reservation, came back full
    telemetry.record_attempt('error', 'provider_rate_limited')
    telemetry.model = 'gemini-3.1-flash-lite'
    telemetry.note_dispatch(desktop_proxy.UpstreamRoute('https://provider.invalid', {}, {}, 'vertex_ai', 'adc', 'us'))
    telemetry.observe_gemini_response({'usageMetadata': {'promptTokenCount': 10, 'candidatesTokenCount': 2}})
    telemetry.complete(outcome='success', status_code=200, retryable=False, phase='body')

    assert [(a.ordinal, a.retry_ordinal, a.outcome, a.error_class, a.fallback_reason) for a in scheduled] == [
        (1, 1, 'error', 'provider_rate_limited', None),
        (2, 2, 'success', 'none', 'overflow_recovery'),
    ]
    assert {a.invocation_id for a in scheduled} == {telemetry.invocation_id}
    assert scheduled[0].metadata is None  # usage belongs to the dispatch that produced it
    assert scheduled[1].metadata is not None and scheduled[1].configured_model == 'gemini-3.1-flash-lite'


def test_streaming_usage_observer_stops_at_a_bounded_buffer() -> None:
    telemetry = desktop_proxy.ProxyTelemetry(_request(), streaming=True)
    observer = desktop_proxy._StreamingUsageObserver(telemetry)
    observer.feed(b'data: ' + b'A' * (observer.MAX_EVENT_BYTES + 1))
    assert observer.disabled and not observer.buffer
    observer.feed(b'data: {"usageMetadata": {"promptTokenCount": 5}}\n\n')
    observer.finish()
    assert telemetry.provider_metadata is None


@pytest.mark.asyncio
async def test_synthetic_direct_proxy_call_lands_in_the_per_uid_per_feature_query(monkeypatch, ledger_client) -> None:
    """S0 proof, proxy half: one company-paid Vertex call → one queryable ledger row."""

    class VertexClient:
        async def post(self, url, *, params, content, headers):
            return httpx.Response(
                200,
                request=httpx.Request('POST', url),
                json={
                    'candidates': [{'content': {'parts': [{'text': 'hi'}]}, 'finishReason': 'STOP'}],
                    'usageMetadata': {
                        'promptTokenCount': 120,
                        'cachedContentTokenCount': 80,
                        'candidatesTokenCount': 14,
                    },
                    'modelVersion': 'gemini-2.5-flash-001',
                    'trafficType': 'PROVISIONED_THROUGHPUT',
                },
            )

    async def route(path, _model, _action, _query):
        return desktop_proxy.UpstreamRoute('https://provider.invalid', {}, {}, 'vertex_ai', 'adc', 'us-central1')

    async def meter(_uid, path, _model, _action):
        return path

    monkeypatch.setattr(desktop_proxy.sys, 'stdout', io.StringIO())
    monkeypatch.setattr(desktop_proxy, '_wait_for_disconnect', _never_disconnects)
    monkeypatch.setattr(desktop_proxy, 'get_byok_key', lambda _: None)
    monkeypatch.setattr(desktop_proxy, '_meter_server_request', meter)
    monkeypatch.setattr(desktop_proxy, '_upstream', route)
    monkeypatch.setattr(desktop_proxy, 'get_desktop_gemini_client', lambda: VertexClient())
    monkeypatch.setattr(desktop_proxy, 'get_desktop_gemini_semaphore', lambda: asyncio.Semaphore(1))
    monkeypatch.setattr(desktop_proxy.desktop_gemini_gateway, 'should_route_features_through_gateway', lambda: False)

    response = await desktop_proxy._proxy(_request(), 'models/gemini-2.5-flash:generateContent', False, UID)
    await ledger.drain_pending_writes()

    assert response.status_code == 200
    rows = ledger_client.spend_rows(uid=UID, feature='desktop_proactivity')
    assert len(rows) == 1
    row = rows[0]
    assert row['caller'] == 'desktop_proxy'
    assert row['payer'] == 'omi'
    assert row['provider'] == 'gemini'
    assert row['actual_model_version'] == 'gemini-2.5-flash-001'
    assert row['traffic_type'] == 'PROVISIONED_THROUGHPUT'
    assert (row['prompt_tokens'], row['cached_input_tokens'], row['output_tokens']) == (120, 80, 14)
    assert row['cost_status'] == 'estimated'
    assert row['estimated_cost_micro_usd'] > 0
    assert row['cost_attribution_status'] == 'complete'
    assert row['subscription_tier'] == 'basic'
    assert ledger_client.spend_rows(uid='someone-else', feature='desktop_proactivity') == []


@pytest.mark.asyncio
async def test_a_saturated_reservation_leaves_one_row_per_dispatch(monkeypatch, ledger_client) -> None:
    """Attempt 1 (PT reservation) comes back full, attempt 2 (shared capacity) succeeds: two rows, one invocation."""
    statuses = iter([429, 200])

    class Client:
        async def post(self, url, *, params, content, headers):
            status = next(statuses)
            if status == 429:
                return httpx.Response(
                    429,
                    request=httpx.Request('POST', url),
                    json={
                        'error': {
                            'code': 429,
                            'status': 'RESOURCE_EXHAUSTED',
                            'message': 'Provisioned throughput exhausted',
                        }
                    },
                )
            return httpx.Response(
                200,
                request=httpx.Request('POST', url),
                json={
                    'candidates': [{'finishReason': 'STOP'}],
                    'usageMetadata': {'promptTokenCount': 9, 'candidatesTokenCount': 3},
                },
            )

    async def route(path, model, _action, _query, request_type=None):
        return desktop_proxy.UpstreamRoute('https://provider.invalid', {}, {}, 'vertex_ai', 'adc', 'us-central1')

    async def meter(_uid, path, _model, _action):
        return path

    monkeypatch.setattr(desktop_proxy.sys, 'stdout', io.StringIO())
    monkeypatch.setattr(desktop_proxy, '_wait_for_disconnect', _never_disconnects)
    monkeypatch.setattr(desktop_proxy, 'get_byok_key', lambda _: None)
    monkeypatch.setattr(desktop_proxy, '_meter_server_request', meter)
    monkeypatch.setattr(desktop_proxy, '_upstream', route)
    monkeypatch.setattr(desktop_proxy, '_recovery_plan', lambda *_: [('gemini-2.5-flash', 'shared')])
    monkeypatch.setattr(desktop_proxy, 'get_desktop_gemini_client', lambda: Client())
    monkeypatch.setattr(desktop_proxy, 'get_desktop_gemini_semaphore', lambda: asyncio.Semaphore(1))
    monkeypatch.setattr(desktop_proxy.desktop_gemini_gateway, 'should_route_features_through_gateway', lambda: False)

    response = await desktop_proxy._proxy(_request(), 'models/gemini-2.5-flash:generateContent', False, UID)
    await ledger.drain_pending_writes()

    assert response.status_code == 200
    rows = sorted(ledger_client.spend_rows(uid=UID, feature='desktop_proactivity'), key=lambda r: r['retry_ordinal'])
    assert [(r['retry_ordinal'], r['outcome'], r['error_class'], r['fallback_reason']) for r in rows] == [
        (1, 'error', 'provider_capacity', None),
        (2, 'success', 'none', 'overflow_recovery'),
    ]
    assert {r['invocation_id'] for r in rows} == {rows[0]['invocation_id']}
    assert rows[0]['usage_status'] == 'not_reported' and rows[1]['prompt_tokens'] == 9


# --- omni relay: one row per observed provider turn ---------------------------------------


class _FakeUpstream:
    """The provider socket: records what the client sent, replays canned frames."""

    def __init__(self, frames: list[str | bytes], drained: asyncio.Event) -> None:
        self.frames = frames
        self.sent: list[str | bytes] = []
        self._drained = drained

    async def send(self, message: str | bytes) -> None:
        self.sent.append(message)

    def __aiter__(self):
        return self._replay()

    async def _replay(self):
        for frame in self.frames:
            yield frame
        self._drained.set()
        await asyncio.Event().wait()  # stay open until the client hangs up


class _FakeConnect:
    def __init__(self, upstream: _FakeUpstream) -> None:
        self.upstream = upstream

    async def __aenter__(self) -> _FakeUpstream:
        return self.upstream

    async def __aexit__(self, *_: object) -> None:
        return None


def _client_socket(
    provider: str,
    *,
    model: str | None,
    client_frames: list[str],
    drained: asyncio.Event,
    fail_downstream_send: bool = False,
):
    class Socket:
        headers = {'authorization': 'Bearer token'}
        query_params = {'provider': provider, **({'model': model} if model else {})}

        def __init__(self) -> None:
            self.sent: list[Any] = []
            self._pending = list(client_frames)
            self._fail_downstream_send = fail_downstream_send

        async def accept(self) -> None:
            return None

        async def close(self, **_: Any) -> None:
            return None

        async def send_text(self, text: str) -> None:
            if self._fail_downstream_send:
                raise RuntimeError('downstream closed')
            self.sent.append(text)

        async def send_bytes(self, data: bytes) -> None:
            if self._fail_downstream_send:
                raise RuntimeError('downstream closed')
            self.sent.append(data)

        async def receive(self) -> dict[str, Any]:
            if self._pending:
                return {'type': 'websocket.receive', 'text': self._pending.pop(0)}
            await drained.wait()
            return {'type': 'websocket.disconnect'}

    return Socket()


async def _passthrough(_executor, fn, *args, **kwargs):
    return fn(*args, **kwargs)


async def _run_relay(
    monkeypatch,
    *,
    provider: str,
    model: str | None,
    client_frames: list[str],
    upstream_frames: list[str | bytes],
    byok: bool = False,
    byok_enrolled: bool | None = None,
    fail_downstream_send: bool = False,
) -> tuple[Any, _FakeUpstream]:
    from models.users import PlanType

    drained = asyncio.Event()
    upstream = _FakeUpstream(upstream_frames, drained)
    validated = {provider: 'sk-user'} if byok else {}
    monkeypatch.setattr(omni_relay, 'raise_if_gateway_feature_mode_blocks_direct_model_surface', lambda _surface: None)
    monkeypatch.setattr(omni_relay, 'run_blocking', _passthrough)
    monkeypatch.setattr(omni_relay, '_verify_ws_auth', lambda _authz: UID)
    monkeypatch.setattr(omni_relay, 'extract_byok_from_websocket', lambda _ws: dict(validated))
    monkeypatch.setattr(omni_relay, 'validate_byok_websocket_keys', lambda _uid, keys: (dict(keys), None))
    monkeypatch.setattr(omni_relay, 'set_validated_byok_keys', lambda _keys, _uid: None)
    monkeypatch.setattr(omni_relay, 'is_trial_paywalled', lambda *_a, **_k: False)
    monkeypatch.setattr(
        omni_relay.users_db, 'is_byok_active', lambda _uid: byok if byok_enrolled is None else byok_enrolled
    )
    monkeypatch.setattr(
        omni_relay, 'get_chat_quota_snapshot', lambda *_a, **_k: {'plan': PlanType.basic, 'allowed': True}
    )
    monkeypatch.setattr(omni_relay, 'get_customer_firestore_client', lambda: object())
    # S15's quota machinery is a different seam (test_realtime_quota_counter.py); keep it inert here.
    monkeypatch.setattr(omni_relay, '_relay_responses_this_month', lambda _uid: 0)
    monkeypatch.setattr(
        omni_relay,
        '_count_relay_response',
        lambda _uid: (0, {'plan': PlanType.basic, 'allowed': True, 'unit': 'questions', 'used': 0.0, 'limit': 30.0}),
    )
    monkeypatch.setattr(omni_relay, '_upstream', lambda _provider, _model: (('wss://upstream.invalid', {}), None))
    monkeypatch.setattr(omni_relay.websockets, 'connect', lambda *_a, **_k: _FakeConnect(upstream))
    socket = _client_socket(
        provider,
        model=model,
        client_frames=client_frames,
        drained=drained,
        fail_downstream_send=fail_downstream_send,
    )
    await omni_relay.omni_relay(socket)
    return socket, upstream


_OPENAI_DONE = json.dumps(
    {
        'type': 'response.done',
        'response': {
            'id': 'resp_1',
            'status': 'completed',
            'usage': {
                'input_tokens': 300,
                'output_tokens': 120,
                'input_token_details': {
                    'text_tokens': 100,
                    'audio_tokens': 200,
                    'cached_tokens': 50,
                    'cached_tokens_details': {'text_tokens': 50, 'audio_tokens': 0},
                },
                'output_token_details': {'text_tokens': 20, 'audio_tokens': 100},
            },
        },
    }
)


@pytest.mark.asyncio
async def test_synthetic_relay_turn_lands_in_the_per_uid_per_feature_query(monkeypatch, ledger_client) -> None:
    """S0 proof, relay half: one OpenAI response.done on the wire → one queryable ledger row."""
    socket, upstream = await _run_relay(
        monkeypatch,
        provider='openai',
        model=None,
        client_frames=[json.dumps({'type': 'session.update', 'session': {'voice': 'alloy'}})],
        upstream_frames=[json.dumps({'type': 'session.updated'}), _OPENAI_DONE],
    )
    await ledger.drain_pending_writes()

    # The relay still relayed: both frames reached the client, the setup reached the provider.
    assert len(socket.sent) == 2
    assert len(upstream.sent) == 1

    rows = ledger_client.spend_rows(uid=UID, feature=DESKTOP_REALTIME_FEATURE)
    assert len(rows) == 1
    row = rows[0]
    assert row['caller'] == OMNI_RELAY_CALLER
    assert row['payer'] == 'omi'
    assert row['provider'] == 'openai'
    assert row['configured_model'] == 'gpt-realtime-2'
    assert row['api_surface'] == 'openai_realtime_websocket'
    assert row['provider_response_id'] == 'resp_1'
    assert (row['prompt_tokens'], row['cached_input_tokens'], row['output_tokens']) == (300, 50, 120)
    assert row['cost_status'] == 'estimated'
    # cached 50 is a subset of the 100 text tokens: 50*4 + 50*0.4 + 200*32 + 20*24 + 100*64 = 13,500 micro-USD
    assert row['estimated_cost_micro_usd'] == 13_500
    assert row['rate_card_id'] == 'openai.gpt-realtime-2.modality.2026-09-01'
    assert row['attempt_id'] == f"{row['invocation_id']}:1"
    assert row['request_id'] == row['invocation_id']


@pytest.mark.asyncio
async def test_relay_accounts_terminal_frame_when_downstream_send_fails(monkeypatch, ledger_client) -> None:
    socket, _ = await _run_relay(
        monkeypatch,
        provider='openai',
        model=None,
        client_frames=[],
        upstream_frames=[_OPENAI_DONE],
        fail_downstream_send=True,
    )
    await ledger.drain_pending_writes()

    assert socket.sent == []
    rows = ledger_client.spend_rows(uid=UID, feature=DESKTOP_REALTIME_FEATURE)
    assert len(rows) == 1
    assert rows[0]['provider_response_id'] == 'resp_1'


@pytest.mark.asyncio
async def test_each_relay_turn_is_its_own_ordinal_and_byok_is_not_omi_cost(monkeypatch, ledger_client) -> None:
    await _run_relay(
        monkeypatch,
        provider='openai',
        model='gpt-realtime-2',
        client_frames=[],
        # Two distinct responses: a replayed terminal frame for the same id is deliberately one row.
        upstream_frames=[_OPENAI_DONE, _OPENAI_DONE.replace('resp_1', 'resp_2')],
        byok=True,
    )
    await ledger.drain_pending_writes()

    rows = sorted(ledger_client.spend_rows(uid=UID, feature=DESKTOP_REALTIME_FEATURE), key=lambda r: r['attempt_id'])
    assert [row['attempt_id'].rsplit(':', 1)[1] for row in rows] == ['1', '2']
    assert {row['invocation_id'] for row in rows} == {rows[0]['invocation_id']}
    assert {row['payer'] for row in rows} == {'byok'}
    assert {row['cost_status'] for row in rows} == {'not_omi_cost'}
    assert {row['cost_attribution_status'] for row in rows} == {'excluded'}


@pytest.mark.asyncio
async def test_payer_follows_the_credential_the_relay_selected_not_enrollment(monkeypatch, ledger_client) -> None:
    """A valid provider key from an unenrolled user still rides that key upstream, so the provider bills them."""
    await _run_relay(
        monkeypatch,
        provider='openai',
        model=None,
        client_frames=[],
        upstream_frames=[_OPENAI_DONE],
        byok=True,
        byok_enrolled=False,
    )
    await ledger.drain_pending_writes()

    rows = ledger_client.spend_rows(uid=UID, feature=DESKTOP_REALTIME_FEATURE)
    assert [(r['payer'], r['cost_status']) for r in rows] == [('byok', 'not_omi_cost')]


@pytest.mark.asyncio
async def test_gemini_turns_are_deltas_of_the_session_cumulative_usage(monkeypatch, ledger_client) -> None:
    setup = json.dumps({'setup': {'model': 'models/gemini-3.1-flash-live-preview', 'generationConfig': {}}})
    audio = json.dumps(
        {'serverContent': {'modelTurn': {'parts': [{'inlineData': {'mimeType': 'audio/pcm', 'data': 'AAAA'}}]}}}
    )
    turn1 = json.dumps(
        {
            'serverContent': {'turnComplete': True},
            'usageMetadata': {
                'promptTokenCount': 40,
                'cachedContentTokenCount': 8,
                'cacheTokensDetails': [{'modality': 'TEXT', 'tokenCount': 8}],
                'promptTokensDetails': [
                    {'modality': 'TEXT', 'tokenCount': 10},
                    {'modality': 'AUDIO', 'tokenCount': 30},
                ],
                'responseTokensDetails': [{'modality': 'AUDIO', 'tokenCount': 25}],
            },
        }
    )
    # Session totals so far, not this turn's: 40 → 100 prompt (text 20, audio 80), 25 → 60 audio out.
    turn2_usage = json.dumps(
        {
            'usageMetadata': {
                'promptTokenCount': 100,
                'cachedContentTokenCount': 8,
                'cacheTokensDetails': [{'modality': 'TEXT', 'tokenCount': 8}],
                'promptTokensDetails': [
                    {'modality': 'TEXT', 'tokenCount': 20},
                    {'modality': 'AUDIO', 'tokenCount': 80},
                ],
                'responseTokensDetails': [{'modality': 'AUDIO', 'tokenCount': 60}],
            }
        }
    )
    turn2_end = json.dumps({'serverContent': {'turnComplete': True}})
    await _run_relay(
        monkeypatch,
        provider='gemini',
        model=None,
        client_frames=[setup],
        upstream_frames=[
            b'{"setupComplete": {}}',
            audio.encode(),
            turn1.encode(),
            audio.encode(),  # turn 2 opens with model output before its usage arrives, as on the wire
            turn2_usage.encode(),
            turn2_end.encode(),
        ],
    )
    await ledger.drain_pending_writes()

    rows = sorted(ledger_client.spend_rows(uid=UID, feature=DESKTOP_REALTIME_FEATURE), key=lambda r: r['attempt_id'])
    assert [r['configured_model'] for r in rows] == ['gemini-3.1-flash-live-preview'] * 2
    assert [(r['prompt_tokens'], r['cached_input_tokens'], r['output_tokens']) for r in rows] == [
        (40, 8, 25),
        (60, 0, 35),
    ]
    # turn 1: 8 cached text at the (undiscounted) text rate + 2 text + 30 audio + 25 audio out
    #   = 8*0.75 + 2*0.75 + 30*3.0 + 25*12 = 397.5 → 398 micro-USD
    # turn 2: 10 text + 50 audio + 35 audio out = 10*0.75 + 50*3.0 + 35*12 = 577.5 → 578 micro-USD
    assert [r['estimated_cost_micro_usd'] for r in rows] == [398, 578]
    assert {r['rate_card_id'] for r in rows} == {'gemini.gemini-3.1-flash-live-preview.modality.2026-09-01'}


@pytest.mark.asyncio
async def test_interrupted_and_cancelled_responses_are_not_successes(monkeypatch, ledger_client) -> None:
    cancelled = json.dumps(
        {
            'type': 'response.done',
            'response': {
                'id': 'resp_c',
                'status': 'cancelled',
                'usage': {
                    'input_tokens': 30,
                    'output_tokens': 0,
                    'input_token_details': {'audio_tokens': 30},
                    'output_token_details': {},
                },
            },
        }
    )
    await _run_relay(monkeypatch, provider='openai', model=None, client_frames=[], upstream_frames=[cancelled])
    interrupted = json.dumps(
        {
            'serverContent': {'interrupted': True},
            'usageMetadata': {
                'promptTokenCount': 12,
                'promptTokensDetails': [{'modality': 'AUDIO', 'tokenCount': 12}],
                'responseTokensDetails': [{'modality': 'AUDIO', 'tokenCount': 4}],
            },
        }
    )
    done = json.dumps({'serverContent': {'turnComplete': True}})
    await _run_relay(
        monkeypatch,
        provider='gemini',
        model='gemini-3.1-flash-live-preview',
        client_frames=[],
        upstream_frames=[interrupted.encode(), done.encode()],
    )
    await ledger.drain_pending_writes()

    rows = ledger_client.spend_rows(uid=UID, feature=DESKTOP_REALTIME_FEATURE)
    assert sorted((r['provider'], r['outcome'], r['error_class']) for r in rows) == [
        ('gemini', 'cancelled', 'interrupted'),
        ('openai', 'cancelled', 'client_cancelled'),
    ]
    assert all(r['cost_status'] == 'estimated' for r in rows)  # the tokens were still spent


@pytest.mark.asyncio
async def test_a_turn_without_usage_stays_unpriced(monkeypatch, ledger_client) -> None:
    done = json.dumps({'type': 'response.done', 'response': {'id': 'resp_x', 'status': 'completed'}})
    await _run_relay(monkeypatch, provider='openai', model=None, client_frames=[], upstream_frames=[done])
    await ledger.drain_pending_writes()

    rows = ledger_client.spend_rows(uid=UID, feature=DESKTOP_REALTIME_FEATURE)
    assert [
        (r['usage_status'], r['cost_status'], r['estimated_cost_micro_usd'], r['cost_attribution_status']) for r in rows
    ] == [('not_reported', 'unpriced', None, 'missing')]


@pytest.mark.asyncio
async def test_an_unknown_model_stays_unpriced_but_attributed(monkeypatch, ledger_client) -> None:
    await _run_relay(
        monkeypatch, provider='openai', model='gpt-realtime-mini', client_frames=[], upstream_frames=[_OPENAI_DONE]
    )
    await ledger.drain_pending_writes()

    rows = ledger_client.spend_rows(uid=UID, feature=DESKTOP_REALTIME_FEATURE)
    assert [(r['configured_model'], r['usage_status'], r['cost_status'], r['prompt_tokens']) for r in rows] == [
        ('gpt-realtime-mini', 'confirmed', 'unpriced', 300)
    ]


@pytest.mark.asyncio
async def test_a_response_in_flight_at_disconnect_is_recorded_as_cancelled(monkeypatch, ledger_client) -> None:
    created = json.dumps({'type': 'response.created', 'response': {'id': 'resp_inflight'}})
    await _run_relay(monkeypatch, provider='openai', model=None, client_frames=[], upstream_frames=[created])
    await ledger.drain_pending_writes()

    rows = ledger_client.spend_rows(uid=UID, feature=DESKTOP_REALTIME_FEATURE)
    assert [(r['outcome'], r['error_class'], r['provider_response_id'], r['usage_status']) for r in rows] == [
        ('cancelled', 'client_disconnected', 'resp_inflight', 'not_reported')
    ]


@pytest.mark.asyncio
async def test_relay_frames_without_a_turn_write_nothing(monkeypatch, ledger_client) -> None:
    await _run_relay(
        monkeypatch,
        provider='openai',
        model=None,
        client_frames=[],
        upstream_frames=[json.dumps({'type': 'response.output_audio.delta', 'delta': 'AAAA'})],
    )
    await ledger.drain_pending_writes()

    assert ledger_client.spend_rows(uid=UID, feature=DESKTOP_REALTIME_FEATURE) == []


# --- deploy contract ------------------------------------------------------------------


@pytest.mark.slow
def test_the_accounting_switch_reaches_every_serving_identity_of_both_surfaces() -> None:
    """The manifest declares the flag; these are the files that actually put it on the pod/revision."""
    backend = Path(__file__).resolve().parents[2]
    repo = backend.parent
    for relative in (
        'backend/charts/backend-listen/prod_omi_backend_listen_values.yaml',
        'backend/charts/backend-listen/dev_omi_backend_listen_values.yaml',
        '.github/workflows/desktop_backend_prod.yml',
        '.github/workflows/desktop_backend_auto_dev.yml',
    ):
        path = repo / relative
        if not path.exists():
            pytest.skip(f'{relative} is not present in this checkout')
        text = path.read_text(encoding='utf-8')
        # Workflow form `NAME=true`; Helm form `- name: NAME` followed by `value: "true"` on the next line.
        assert re.search(r'LLM_GATEWAY_ACCOUNTING_ENABLED(=true\b|\s*\n\s*value:\s*"true")', text), relative
    manifest = (backend / 'deploy' / 'runtime_env.yaml').read_text(encoding='utf-8')
    assert manifest.count('LLM_GATEWAY_ACCOUNTING_ENABLED') >= 6  # backend, backend-listen, desktop_backend × dev, prod


@pytest.mark.asyncio
async def test_two_open_responses_at_disconnect_are_two_distinct_rows(monkeypatch, ledger_client) -> None:
    """Out-of-band responses can overlap; a flush must not collapse them onto one attempt id."""
    created_a = json.dumps({'type': 'response.created', 'response': {'id': 'resp_a'}})
    created_b = json.dumps({'type': 'response.created', 'response': {'id': 'resp_b'}})
    await _run_relay(
        monkeypatch, provider='openai', model=None, client_frames=[], upstream_frames=[created_a, created_b]
    )
    await ledger.drain_pending_writes()

    rows = sorted(ledger_client.spend_rows(uid=UID, feature=DESKTOP_REALTIME_FEATURE), key=lambda r: r['attempt_id'])
    assert [(r['attempt_id'].rsplit(':', 1)[1], r['provider_response_id'], r['outcome']) for r in rows] == [
        ('1', 'resp_a', 'cancelled'),
        ('2', 'resp_b', 'cancelled'),
    ]
