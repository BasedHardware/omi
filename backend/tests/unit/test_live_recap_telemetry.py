"""Synthetic API, SDK transport and provider-ledger evidence for beta live recap."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from starlette.datastructures import Headers
from starlette.requests import Request

from llm_gateway.gateway.accounting import AccountingContext, AttemptTrace, build_accounting_event
from llm_gateway.gateway.request_context import resolve_request_id
from models.conversation import Conversation
from models.structured import Structured
from tests.unit.test_conversations_v3_stream import catchup, routes, strict  # noqa: F401
from utils.conversations import process_conversation as process
from utils.conversations.v3 import recap_telemetry, summary
from utils.llm import shaped_notes_transport
from utils.llm.providers import get_or_create_omi_gateway_llm


def request(trigger, interval):
    client_id = str(uuid4())
    headers = {
        'x-omi-recap-trigger': trigger,
        'x-omi-recap-request': client_id,
        'x-omi-recap-interval': interval,
        'x-omi-recap-foreground': 'true',
        'x-omi-recap-speech-eligible': 'true',
    }
    scope = {
        'type': 'http',
        'headers': [(name.encode(), value.encode()) for name, value in headers.items()],
    }
    return client_id, Request(scope)


def events(caplog):
    return [
        json.loads(row.getMessage().split(' ', 1)[1])
        for row in caplog.records
        if row.name == recap_telemetry.logger.name
    ]


@pytest.fixture
def summary_open_model(monkeypatch):
    # Built in setup: the first OpenAI client construction pays one-time lazy imports
    # (~0.6 s CPU), which the fast-unit duration guard (call phase only) must not
    # charge to this test's own work.
    monkeypatch.setenv('OMI_LLM_GATEWAY_URL', 'https://synthetic.invalid')
    return get_or_create_omi_gateway_llm(
        'omi:auto:conversation-v3-summary-open', feature='conversation_v3_summary_open'
    )


@pytest.fixture
def default_summary_open_model():
    # Same setup-phase construction for the default gateway URL (a separate model cache key),
    # so no test in this file builds a gateway model inside its timed call phase.
    return get_or_create_omi_gateway_llm(
        'omi:auto:conversation-v3-summary-open', feature='conversation_v3_summary_open'
    )


@pytest.mark.asyncio
async def test_recap_provider_receipts_join_across_foreground_intervals(
    catchup, monkeypatch, caplog, summary_open_model
):
    caplog.set_level(logging.INFO, logger=recap_telemetry.logger.name)
    now = [299.0]
    monkeypatch.setattr(recap_telemetry, 'time', SimpleNamespace(time=lambda: now[0]))
    model = summary_open_model
    receipts = []
    should_fail = [False]

    def send(outbound):
        request_id = outbound.headers['X-Omi-Request-Id']
        assert resolve_request_id(request_id) == request_id
        context = AccountingContext.create(
            request_id=request_id,
            caller='backend',
            user_uid=None,
            feature='conversation_v3_summary_open',
            api_surface='chat_completions',
            payer='omi',
        )
        trace = AttemptTrace()
        for retry_ordinal in range(2 if should_fail[0] else 1):
            attempt = trace.record(
                provider='openai',
                configured_model='synthetic',
                route_artifact_id=None,
                fallback_reason=None,
                retry_ordinal=retry_ordinal,
                outcome='error' if should_fail[0] else 'success',
                error_class='status' if should_fail[0] else 'none',
            )
            receipts.append(build_accounting_event(context, attempt))
        if should_fail[0]:
            return httpx.Response(502, json={'error': {'message': 'synthetic gateway failure'}})
        return httpx.Response(
            200,
            json={
                'id': 'fake-model-response',
                'model': 'synthetic',
                'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'Synthetic notes'}}],
            },
        )

    new_client = httpx.AsyncClient

    def transport_factory(**kwargs):
        return new_client(transport=httpx.MockTransport(send), **kwargs)

    monkeypatch.setattr(shaped_notes_transport, 'httpx', SimpleNamespace(AsyncClient=transport_factory))

    def write(uid, row, emit):
        async def invoke():
            async with shaped_notes_transport.isolated_notes_model(model) as isolated:
                return await isolated.ainvoke('synthetic prompt')

        return {'overview': str(asyncio.run(invoke()).content)}

    async def blocking(pool, fn, *args, **kwargs):
        if pool is summary.llm_executor:
            return await asyncio.to_thread(fn, *args, **kwargs)
        return fn(*args, **kwargs)

    monkeypatch.setattr(summary, 'run_blocking', blocking)
    monkeypatch.setattr(summary, 'write', write)
    first_interval, second_interval = str(uuid4()), str(uuid4())
    first_id, first_request = request('first_open', first_interval)
    lease_id, lease_request = request('retry', first_interval)
    cache_id, cache_request = request('retry', first_interval)
    failed_id, failed_request = request('timed_refresh', second_interval)

    first = await routes.conversation_live_catchup_stream('live', 'synthetic', request=first_request)
    with pytest.raises(routes.HTTPException, match='summary_in_progress'):
        await routes.conversation_live_catchup_stream('live', 'synthetic', request=lease_request)
    assert not receipts
    assert [frame async for frame in first.body_iterator][-1].startswith('done:')
    assert len(receipts) == 1
    cached = await routes.conversation_live_catchup_stream('live', 'synthetic', request=cache_request)
    assert [frame async for frame in cached.body_iterator][-1].startswith('done:')
    assert len(receipts) == 1

    now[0] = 301.0
    catchup['transcript_segments'][0]['text'] = 'corrected ' * 300
    catchup['_test_revision'] += 1
    should_fail[0] = True
    failed = await routes.conversation_live_catchup_stream('live', 'synthetic', request=failed_request)
    assert [frame async for frame in failed.body_iterator][-1].startswith('error:')

    observed = events(caplog)
    dispatches = [row for row in observed if row['outcome'] == 'gateway_dispatch']
    assert [row['trigger'] for row in dispatches] == ['first_open', 'timed_refresh']
    assert len({row['interval'] for row in dispatches}) == 2
    assert set(dispatches[0]['viewer_aliases']) & set(dispatches[1]['viewer_aliases'])
    assert all(row['foreground'] and row['speech_eligible'] and row['join'] == 'correlatable' for row in observed)
    by_gateway = {
        row['gateway_request']: {
            receipt.attempt_id for receipt in receipts if receipt.request_id == row['gateway_request']
        }
        for row in dispatches
    }
    assert [len(attempts) for attempts in by_gateway.values()] == [1, 2]
    for outcome in ('lease_conflict', 'cache_hit'):
        (result,) = [row for row in observed if row['outcome'] == outcome]
        assert result['trigger'] == 'retry'
        assert not any(row['request'] == result['request'] for row in dispatches)
    assert [receipt.outcome for receipt in receipts] == ['success', 'error', 'error']
    assert any(row['outcome'] == 'stream_failed' for row in observed)
    for raw in (first_id, lease_id, cache_id, failed_id, first_interval, second_interval, 'synthetic prompt'):
        assert raw not in json.dumps(observed)


def test_recap_missing_and_malformed_diagnostics_are_unverified(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=recap_telemetry.logger.name)
    monkeypatch.delenv('ENCRYPTION_SECRET', raising=False)
    recap_telemetry.observe(
        'internal-uid',
        Headers({'x-omi-recap-trigger': 'untrusted payload', 'x-omi-recap-speech-eligible': 'false'}),
    ).record('request_received')
    (row,) = events(caplog)
    assert row['join'] == 'unverified'
    assert row['viewer_aliases'] == []
    assert row['request'] is None and row['interval'] is None and row['trigger'] is None
    assert row['speech_eligible'] is False
    assert 'internal-uid' not in caplog.text and 'untrusted payload' not in caplog.text


def test_live_recap_notes_skip_ancillary_work_and_finalize_preserves_it(monkeypatch):
    from utils.conversations.v3 import context

    def unwanted(*args, **kwargs):
        pytest.fail('live recap invoked ancillary work')

    monkeypatch.setattr(process, 'should_discard_conversation', unwanted)
    monkeypatch.setattr(process, 'jev_discard_probability', unwanted)
    monkeypatch.setattr(process, 'rich_notes_inputs', unwanted)
    monkeypatch.setattr(process, 'before_notes', unwanted)
    monkeypatch.setattr(process, '_fetch_dedup_candidates_for_query', unwanted)
    monkeypatch.setattr(process, '_proposes_task_candidates', unwanted)
    monkeypatch.setattr(context, 'summary', unwanted)
    monkeypatch.setattr(process.member_notes, 'before_model', unwanted)
    monkeypatch.setattr(process.notification_db, 'get_user_time_zone', lambda uid: 'UTC')
    monkeypatch.setattr(process, 'resolve_output_language', lambda *args: 'en')
    monkeypatch.setattr(process, 'relevance_arm', lambda *_: 'jev')
    monkeypatch.setattr(process, 'jev_tier_applies', lambda *_: True)
    monkeypatch.setattr(process, 'conversation_known_spellings', lambda _uid: '')
    monkeypatch.setattr(process, 'conversation_transcripts_for_llm', lambda *args: ('words ' * 300, 'words ' * 300, {}))
    calls = []

    def notes(prefix, **kwargs):
        calls.append(kwargs)
        return Structured(overview='Recap notes')

    monkeypatch.setattr(process, 'get_conversation_notes', notes)
    now = datetime.now(timezone.utc)
    row = Conversation(
        id='synthetic-live',
        created_at=now,
        started_at=now,
        finished_at=now,
        v3_derived=True,
        kind='conversation',
        structured=Structured(),
        transcript_segments=[
            {'text': 'Discussed the schedule and assigned owners. ' * 60, 'start': 0, 'end': 180, 'is_user': True}
        ],
    )
    assert process._get_structured('synthetic', 'en', row, live_recap=True)[0].overview == 'Recap notes'
    (args,) = calls
    assert not args['task_intelligence_capture'] and args['existing_action_items'] == []
    assert not args['meeting_context'] and not args['rich_context_enabled']

    with pytest.raises(pytest.fail.Exception, match='invoked ancillary work'):
        process._get_structured('synthetic', 'en', row, user_kept=True)


def test_recap_duplicates_and_non_v4_ids_cannot_join(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=recap_telemetry.logger.name)
    monkeypatch.setenv('ENCRYPTION_SECRET', 'synthetic-not-a-real-key')
    client_id = str(uuid4())
    headers = Headers(
        raw=[
            (b'x-omi-recap-request', client_id.encode()),
            (b'x-omi-recap-request', client_id.encode()),
            (b'x-omi-recap-interval', b'00000000-0000-1000-8000-000000000000'),
            (b'x-omi-recap-trigger', b'first_open'),
            (b'x-omi-recap-foreground', b'true'),
            (b'x-omi-recap-speech-eligible', b'true'),
        ]
    )
    recap_telemetry.observe('internal-uid', headers).record('request_received')
    (row,) = events(caplog)
    assert row['join'] == 'unverified' and len(row['viewer_aliases']) == 2
    assert row['request'] is None and row['interval'] is None
    assert client_id not in caplog.text


@pytest.mark.asyncio
async def test_recap_cohort_is_rechecked_before_outbound_dispatch(monkeypatch, caplog, default_summary_open_model):
    caplog.set_level(logging.INFO, logger=recap_telemetry.logger.name)
    monkeypatch.setenv('CONVERSATIONS_V3_LIVE_RECAP_COHORT', 'uid:synthetic')
    _, ingress = request('first_open', str(uuid4()))
    observation = recap_telemetry.observe('synthetic', ingress.headers)
    model = default_summary_open_model

    def no_dispatch(outbound):
        pytest.fail('removed beta tester dispatched provider traffic')

    new_client = httpx.AsyncClient

    def transport_factory(**kwargs):
        return new_client(transport=httpx.MockTransport(no_dispatch), **kwargs)

    monkeypatch.setattr(shaped_notes_transport, 'httpx', SimpleNamespace(AsyncClient=transport_factory))
    with recap_telemetry.scoped('synthetic', observation):
        async with shaped_notes_transport.isolated_notes_model(model) as isolated:
            monkeypatch.delenv('CONVERSATIONS_V3_LIVE_RECAP_COHORT')
            from openai import APIConnectionError

            with pytest.raises(APIConnectionError):
                await isolated.ainvoke('synthetic prompt')
    assert [row['outcome'] for row in events(caplog)] == ['cohort_revoked']
