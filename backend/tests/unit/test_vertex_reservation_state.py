"""Reservation evidence, shared storage, and state policy contracts (no network)."""

import json
import asyncio
import time
import logging

import httpx
import fakeredis.aioredis
import pytest

from config import vertex_reservations as vr
from utils.llm import vertex_pt_routing as ptr
from utils.llm.vertex_reservation_state import ReservationState, effective_states
from utils.llm.desktop_reservation_policy import desktop_lane, admission, refusal_body

OLD, NEW = 'gemini-2.5-flash', 'gemini-3.8-flash'


def failures(start=1000):
    e = vr.Evidence(success_at=100)
    for t in [start, start + 600, start + 1200, start + 1800]:
        e = vr.observe(e, now=t, outcome='capacity_error')
    return e


def test_unknown_active_inactive_and_immediate_recovery():
    assert vr.observed_state(OLD, {}, now=100)[0] == vr.State.UNKNOWN
    e = vr.observe(vr.Evidence(), now=100, outcome='dedicated_success')
    assert vr.observed_state(OLD, {OLD: e}, now=101)[0] == vr.State.ACTIVE
    observations = {OLD: failures(), NEW: vr.Evidence(success_at=2800)}
    assert vr.observed_state(OLD, observations, now=2801) == (vr.State.INACTIVE, 'exclusive_order_moved')
    observations[OLD] = vr.observe(observations[OLD], now=2802, outcome='dedicated_success')
    assert observations[OLD].failure_count == 0
    assert vr.observed_state(OLD, observations, now=2802)[0] == vr.State.ACTIVE


@pytest.mark.parametrize('initial_success', [0, 100])
def test_absent_and_saturated_429s_are_indistinguishable_and_never_confirm_absence_alone(initial_success):
    e = vr.Evidence(success_at=initial_success)
    for t in range(1000, 50000, 600):
        e = vr.observe(e, now=t, outcome='capacity_error')
        assert vr.observed_state(OLD, {OLD: e}, now=t)[0] != vr.State.INACTIVE


@pytest.mark.parametrize(
    'bad_evidence', ['burst', 'short', 'stale_old', 'stale_successor', 'gap', 'other_error', 'different_order']
)
def test_incomplete_evidence_cannot_refuse(monkeypatch, bad_evidence):
    old = failures()
    new = vr.Evidence(success_at=2800)
    now = 2801
    if bad_evidence == 'burst':
        old = vr.Evidence(success_at=100)
        for t in range(1000, 1100):
            old = vr.observe(old, now=t, outcome='capacity_error')
    elif bad_evidence == 'short':
        old = vr.Evidence(100, 1000, 2200, 4)
    elif bad_evidence == 'stale_old':
        now = 3801
        new = vr.Evidence(success_at=3800)
    elif bad_evidence == 'stale_successor':
        new = vr.Evidence(success_at=1800)
    elif bad_evidence == 'gap':
        old = vr.observe(old, now=3801, outcome='capacity_error')
    elif bad_evidence == 'other_error':
        old = vr.observe(old, now=2801, outcome='inconclusive')
    else:
        monkeypatch.setitem(vr.RESERVATIONS, NEW, vr.Reservation('second-order', 'us'))
    assert vr.observed_state(OLD, {OLD: old, NEW: new}, now=now)[0] != vr.State.INACTIVE


def test_expired_evidence_reverts_unknown_and_order_move_back_uses_same_reducer():
    observations = {NEW: failures(), OLD: vr.Evidence(success_at=2800)}
    assert vr.observed_state(NEW, observations, now=2801)[0] == vr.State.INACTIVE
    assert vr.observed_state(NEW, observations, now=90000)[0] == vr.State.UNKNOWN


@pytest.mark.parametrize('state', list(vr.State))
@pytest.mark.parametrize('lane', list(vr.POLICIES))
def test_every_lane_disposition(state, lane):
    expected = 'dedicated'
    if state == vr.State.INACTIVE:
        expected = 'refuse' if lane == 'macos_legacy_tasks' else 'shared'
    assert vr.policy(OLD, state, lane=lane).kind == expected
    assert vr.policy(NEW, state, lane=lane).kind == ('dedicated' if state == vr.State.ACTIVE else 'shared')
    assert vr.policy('gemini-2.5-flash-lite', state, lane=lane).kind == 'shared'


def test_override_precedence_both_directions_unknown_and_auto():
    observed = {OLD: vr.State.INACTIVE, NEW: vr.State.ACTIVE}
    assert effective_states(observed, {}) == observed
    assert effective_states(observed, {'OMI_VERTEX_PT_MODEL': OLD}) == {OLD: vr.State.ACTIVE, NEW: vr.State.INACTIVE}
    env = {'OMI_VERTEX_PT_MODEL': NEW, vr.STATE_OVERRIDE_ENV: json.dumps({OLD: 'active', NEW: 'unknown'})}
    assert effective_states(observed, env) == {OLD: vr.State.ACTIVE, NEW: vr.State.UNKNOWN}
    assert effective_states(observed, {vr.STATE_OVERRIDE_ENV: json.dumps({OLD: 'auto'})}) == observed
    assert (
        effective_states(observed, {'OMI_VERTEX_PT_MODEL': OLD, vr.STATE_OVERRIDE_ENV: json.dumps({OLD: 'auto'})})[OLD]
        == vr.State.INACTIVE
    )
    assert (
        effective_states({OLD: vr.State.ACTIVE}, {vr.STATE_OVERRIDE_ENV: json.dumps({OLD: 'inactive'})})[OLD]
        == vr.State.INACTIVE
    )


@pytest.mark.parametrize('raw', ['oops', '[]', '{"unknown":"active"}', '{"gemini-2.5-flash":"typo"}'])
def test_bad_override_fails_open(raw):
    assert set(effective_states({OLD: vr.State.INACTIVE}, {vr.STATE_OVERRIDE_ENV: raw}).values()) == {vr.State.UNKNOWN}


@pytest.mark.asyncio
async def test_shared_success_visible_to_new_instances_and_one_global_probe_lease(monkeypatch):
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    a, b = ReservationState(client), ReservationState(client)
    calls = []

    async def probe(model, location):
        calls.append((model, location))
        return 'dedicated_success'

    states = await a.refresh(probe)
    assert states[OLD] == vr.State.ACTIVE
    states = await b.refresh(probe)
    assert states[OLD] == states[NEW] == vr.State.ACTIVE
    await a.refresh(probe)
    assert calls == [(OLD, 'us-central1'), (NEW, 'us')]
    await client.aclose()


@pytest.mark.asyncio
async def test_shared_inactive_recovers_on_first_real_dedicated_success():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    a, b = ReservationState(client), ReservationState(client)
    seconds, _ = await client.time()
    doc = {
        'evidence': {
            OLD: {
                'success_at': seconds - 3000,
                'failure_start': seconds - 2000,
                'failure_at': seconds - 200,
                'failure_count': 4,
            },
            NEW: {'success_at': seconds - 100},
        }
    }
    await client.set(a.key(), json.dumps(doc))
    assert (await b.refresh())[OLD] == vr.State.INACTIVE
    await a.record(OLD, 'shared', 200, 'ON_DEMAND')
    assert (await b.refresh())[OLD] == vr.State.INACTIVE
    await a.record(OLD, 'dedicated', 200, None)
    assert (await b.refresh())[OLD] == vr.State.INACTIVE
    await a.record(OLD, 'dedicated', 200, 'PROVISIONED_THROUGHPUT')
    assert (await b.refresh())[OLD] == vr.State.ACTIVE
    await client.aclose()


@pytest.mark.asyncio
async def test_storage_unavailable_drops_inactive_state_and_never_probes():
    class Broken:
        def pipeline(self, **kwargs):
            raise ConnectionError('synthetic')

    store = ReservationState(Broken())

    async def probe(*args):
        pytest.fail('no shared lease means no background spend')

    assert set((await store.refresh(probe)).values()) == {vr.State.UNKNOWN}


def test_fallback_excludes_all_active_orders():
    for model in [OLD, NEW]:
        assert ptr.resolve_fallback_chain(
            model=model, pt_model=OLD, protected_models={'gemini-3.1-flash-lite', OLD}
        ) == ('gemini-2.5-flash-lite',)
    assert ptr.resolve_overflow_ladder(pt_model=OLD, protected_models={'gemini-3.1-flash-lite'}) == (
        'gemini-2.5-flash-lite',
    )


def test_classification_does_not_use_screenshot_or_broad_workload_alone():
    body = {
        'tools': [
            {
                'function_declarations': [
                    {'name': n}
                    for n in ['search_similar', 'search_keywords', 'no_task_found', 'extract_task', 'reject_task']
                ]
            }
        ]
    }
    assert desktop_lane({'x-omi-workload': 'extraction'}, body) == 'macos_legacy_tasks'
    assert desktop_lane({}, body) == 'windows_tasks'
    assert desktop_lane({'x-omi-workload': 'extraction', 'x-app-platform': 'windows'}, body) == 'windows_tasks'
    assert desktop_lane({'x-omi-workload': 'extraction'}, {'contents': []}) == 'desktop_other'
    assert desktop_lane({'x-omi-lane': 'task_extraction'}, body) == 'macos_legacy_tasks'


@pytest.mark.parametrize('streaming', [False, True])
def test_refusal_is_terminal_tool_shape_for_shipped_client_decoders(streaming):
    raw = refusal_body(streaming=streaming).decode()
    payload = json.loads(raw.removeprefix('data: ').strip())
    candidate = payload['candidates'][0]
    assert candidate['finishReason'] == 'STOP'
    call = candidate['content']['parts'][0]['functionCall']
    assert call == {'name': 'no_task_found', 'args': {'context_summary': '', 'current_activity': ''}}
    assert 'error' not in payload and 'usageMetadata' not in payload


def test_observe_and_enforce(caplog):
    with caplog.at_level(logging.INFO):
        assert admission(OLD, vr.State.INACTIVE, 'macos_legacy_tasks', 'observe') == 'would_refuse'
        assert admission(OLD, vr.State.INACTIVE, 'macos_legacy_tasks', 'enforce') == 'refuse'
        assert admission(OLD, vr.State.UNKNOWN, 'macos_legacy_tasks', 'enforce') == 'dedicated'
    assert 'action=would_refuse' in caplog.text


def test_declaration_change_invalidates_the_evidence_namespace(monkeypatch):
    before = ReservationState.key()
    monkeypatch.setitem(vr.RESERVATIONS, OLD, vr.Reservation('different-order', 'us-central1'))
    assert ReservationState.key() != before


def test_new_reservation_is_only_a_declaration(monkeypatch):
    model = 'gemini-2.5-flash-lite'
    monkeypatch.setitem(vr.RESERVATIONS, model, vr.Reservation('flash-5-gsu', 'us-central1'))
    assert vr.policy(model, vr.State.ACTIVE).kind == 'dedicated'
    assert vr.policy(model, vr.State.UNKNOWN).kind == 'shared'
    evidence = {NEW: failures(), model: vr.Evidence(success_at=2800)}
    assert vr.observed_state(NEW, evidence, now=2801)[0] == vr.State.INACTIVE
    assert ptr.reservation_endpoint(model, {}) == ('us-central1-aiplatform.googleapis.com', 'us-central1')


@pytest.mark.asyncio
async def test_concurrent_writers_preserve_both_models():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    a, b = ReservationState(client), ReservationState(client)
    await asyncio.gather(
        a.record(OLD, 'dedicated', 200, 'PROVISIONED_THROUGHPUT'),
        b.record(NEW, 'dedicated', 200, 'PROVISIONED_THROUGHPUT'),
    )
    states = await ReservationState(client).refresh()
    assert states == {OLD: vr.State.ACTIVE, NEW: vr.State.ACTIVE}
    await client.aclose()


@pytest.mark.asyncio
async def test_store_outage_does_not_retain_expired_local_evidence(monkeypatch):
    monkeypatch.setenv('REDIS_DB_HOST', '')
    monkeypatch.setattr(time, 'monotonic', lambda: 100000)
    store = ReservationState()
    store._positive[OLD] = 1
    assert (await store.refresh())[OLD] == vr.State.UNKNOWN


def test_pro_remap_is_a_declared_action_in_every_state():
    for state in vr.State:
        assert vr.policy('gemini-2.5-pro', state) == vr.Action('remap', 'gemini-3.1-flash-lite')


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'status,payload,expected',
    [
        (200, {'usageMetadata': {'trafficType': 'PROVISIONED_THROUGHPUT'}}, 'dedicated_success'),
        (200, {'usageMetadata': {'trafficType': 'ON_DEMAND'}}, 'inconclusive'),
        (200, {'usageMetadata': None}, 'inconclusive'),
        (302, {'usageMetadata': {'trafficType': 'PROVISIONED_THROUGHPUT'}}, 'inconclusive'),
        (429, {'error': {'message': 'Too many requests. Exceeded the provisioned throughput.'}}, 'capacity_error'),
        (429, {'error': {'message': 'rate limited'}}, 'inconclusive'),
        (403, {'error': {'message': 'PERMISSION_DENIED'}}, 'inconclusive'),
    ],
)
async def test_synthetic_probe_requires_explicit_pt_and_never_discovers_an_endpoint(
    monkeypatch, status, payload, expected
):
    from utils.llm.vertex_reservation_probe import probe_reservation

    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')

    def handle(request):
        assert request.url.host == 'us-central1-aiplatform.googleapis.com'
        assert '/locations/us-central1/' in request.url.path
        assert request.headers[ptr.REQUEST_TYPE_HEADER] == 'dedicated'
        body = json.loads(request.content)
        assert body['contents'] == [{'role': 'user', 'parts': [{'text': 'Reply OK.'}]}]
        assert body['generationConfig']['maxOutputTokens'] == 16
        return httpx.Response(status, json=payload)

    async def token():
        return 'synthetic-token'

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        assert await probe_reservation(client, token, OLD, 'us-central1') == expected
