"""Transient recovery HTTP failures retry within one paid transcription."""

import asyncio
from collections import Counter

import httpx
import pytest

from tests.unit.test_soniox_batch import FILE, TRANSCRIPTION, TRANSCRIPT, client as sync_client
from utils.stt import soniox_batch as module

# SCA-1998: first-call CPU cost flakes under load; keep coverage on every main
# push in backend-slow-timing-tests.yml until the deterministic rewrite lands.
pytestmark = pytest.mark.slow


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setenv('SONIOX_API_KEY', 'synthetic-only-key')
    monkeypatch.setenv('BATCH_PIPELINE_INDEPENDENT_LANGUAGE_RECOVERY_ENABLED', 'true')


def provider(stage, failures, status=503):
    calls = Counter()

    def handler(request):
        point = (
            'cleanup'
            if request.method == 'DELETE'
            else (
                'upload'
                if request.url.path == '/v1/files'
                else (
                    'create'
                    if request.method == 'POST'
                    else 'transcript' if request.url.path.endswith('/transcript') else 'poll'
                )
            )
        )
        calls[point] += 1
        if point == 'cleanup':
            return httpx.Response(204)
        if point == stage and calls[point] <= failures:
            if status == 'timeout':
                raise httpx.ReadTimeout('PRIVATE_SENTINEL', request=request)
            return httpx.Response(status, text='PRIVATE_SENTINEL')
        if point == 'upload':
            return httpx.Response(201, json={'id': FILE})
        if point == 'create':
            return httpx.Response(201, json={'id': TRANSCRIPTION, 'status': 'queued'})
        if point == 'poll':
            return httpx.Response(200, json={'status': 'completed'})
        return httpx.Response(200, json=TRANSCRIPT)

    return handler, calls


@pytest.mark.parametrize('asynchronous', [False, True])
@pytest.mark.parametrize(
    'stage,status',
    [
        (stage, status)
        for stage in ('upload', 'create', 'poll', 'transcript')
        for status in (429, 503, 'timeout')
        if (stage, status) not in {('create', 503), ('create', 'timeout')}
    ],
)
@pytest.mark.asyncio
async def test_transient_rejection_recovers_with_bounded_backoff(asynchronous, stage, status, caplog):
    handler, calls = provider(stage, 2, status)
    sleeps = []
    semaphore = asyncio.Semaphore(1)

    async def sleep(seconds):
        assert semaphore._value == 1
        sleeps.append(seconds)

    if asynchronous:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            words, _ = await module.transcribe_async(b'synthetic', 5, client=client, semaphore=semaphore, sleep=sleep)
    else:
        words, _ = module.transcribe(b'synthetic', 5, client_factory=sync_client(handler), sleep=sleeps.append)
    assert len(words) == 2
    assert calls[stage] == 3
    assert calls['create'] == (3 if stage == 'create' else 1)
    assert sleeps.count(1) == 1 and sleeps.count(2) >= 1
    assert 'PRIVATE_SENTINEL' not in caplog.text


@pytest.mark.parametrize('asynchronous', [False, True])
@pytest.mark.parametrize(
    'status,kind', [(401, 'error'), (402, 'credit_refusal'), (429, 'rate_limited'), (503, 'error_5xx')]
)
@pytest.mark.asyncio
async def test_exhausted_or_permanent_error_remains_typed_and_never_empty(asynchronous, status, kind, caplog):
    handler, calls = provider('transcript', 100, status)
    if asynchronous:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(module.SonioxBatchError) as raised:
                await module.transcribe_async(b'synthetic', 5, client=client, sleep=lambda _: asyncio.sleep(0))
    else:
        with pytest.raises(module.SonioxBatchError) as raised:
            module.transcribe(b'synthetic', 5, client_factory=sync_client(handler), sleep=lambda _: None)
    assert raised.value.kind == kind
    assert raised.value.submitted is True
    assert calls['transcript'] == (3 if status in {429, 503} else 1)
    assert calls['create'] == 1
    assert 'PRIVATE_SENTINEL' not in caplog.text


@pytest.mark.parametrize('asynchronous', [False, True])
@pytest.mark.asyncio
async def test_uncertain_paid_submit_is_never_reissued(asynchronous):
    handler, calls = provider('create', 100, 'timeout')
    if asynchronous:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(module.SonioxBatchError) as raised:
                await module.transcribe_async(b'synthetic', 5, client=client, sleep=lambda _: asyncio.sleep(0))
    else:
        with pytest.raises(module.SonioxBatchError) as raised:
            module.transcribe(b'synthetic', 5, client_factory=sync_client(handler), sleep=lambda _: None)
    assert calls['create'] == 1
    assert raised.value.kind == 'timeout' and raised.value.submitted is True


@pytest.mark.parametrize('asynchronous', [False, True])
@pytest.mark.asyncio
async def test_paid_submit_5xx_is_uncertain_and_never_reissued(asynchronous):
    handler, calls = provider('create', 100, 503)
    if asynchronous:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(module.SonioxBatchError) as raised:
                await module.transcribe_async(b'synthetic', 5, client=client, sleep=lambda _: asyncio.sleep(0))
    else:
        with pytest.raises(module.SonioxBatchError) as raised:
            module.transcribe(b'synthetic', 5, client_factory=sync_client(handler), sleep=lambda _: None)
    assert calls['create'] == 1
    assert raised.value.kind == 'error_5xx' and raised.value.submitted is True


@pytest.mark.parametrize('asynchronous', [False, True])
@pytest.mark.asyncio
async def test_backoff_cannot_extend_the_original_deadline(asynchronous, monkeypatch):
    monkeypatch.setattr(module, 'DEADLINE_SECONDS', 3)
    now, sleeps = [0.0], []
    handler, calls = provider('poll', 100, 503)

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    async def async_sleep(seconds):
        sleep(seconds)

    if asynchronous:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(module.SonioxBatchError) as raised:
                await module.transcribe_async(b'synthetic', 5, client=client, clock=lambda: now[0], sleep=async_sleep)
    else:
        with pytest.raises(module.SonioxBatchError) as raised:
            module.transcribe(b'synthetic', 5, client_factory=sync_client(handler), clock=lambda: now[0], sleep=sleep)
    assert sleeps == [2, 1] and now[0] == 3
    assert calls['create'] == calls['poll'] == 1
    assert raised.value.kind == 'timeout' and raised.value.submitted is True


@pytest.mark.asyncio
async def test_cancel_during_backoff_releases_permit_and_never_submits_again():
    handler, calls = provider('transcript', 100, 503)
    semaphore = asyncio.Semaphore(1)

    async def sleep(seconds):
        if seconds == 1:
            assert semaphore._value == 1
            raise asyncio.CancelledError()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(asyncio.CancelledError):
            await module.transcribe_async(b'synthetic', 5, client=client, semaphore=semaphore, sleep=sleep)
    assert calls['create'] == calls['transcript'] == 1
    assert calls['cleanup'] == 2 and semaphore._value == 1
