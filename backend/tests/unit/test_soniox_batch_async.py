"""Async provider waits borrow no executor or HTTP permit between requests."""

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from utils.stt import soniox_batch as module
from tests.unit.test_soniox_batch import FILE, TRANSCRIPTION, TRANSCRIPT


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setenv('SONIOX_API_KEY', 'synthetic-only-key')
    monkeypatch.setenv('BATCH_PIPELINE_INDEPENDENT_LANGUAGE_RECOVERY_ENABLED', 'true')


@pytest.mark.asyncio
async def test_poll_wait_releases_http_permit_and_never_repeats_submission():
    calls, sleeps, semaphore = [], [], asyncio.Semaphore(1)
    statuses = iter(['processing', 'completed'])

    async def handler(request):
        calls.append((request.method, request.url.path))
        assert request.headers['authorization'] == 'Bearer synthetic-only-key'
        if request.method == 'DELETE':
            return httpx.Response(204)
        if request.url.path == '/v1/files':
            return httpx.Response(201, json={'id': FILE})
        if request.method == 'POST':
            return httpx.Response(201, json={'id': TRANSCRIPTION, 'status': 'queued'})
        if request.url.path.endswith('/transcript'):
            return httpx.Response(200, json=TRANSCRIPT)
        return httpx.Response(200, json={'status': next(statuses)})

    async def sleep(seconds):
        assert semaphore._value == 1
        sleeps.append(seconds)
        await asyncio.sleep(0)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        words, language = await module.transcribe_async(
            b'synthetic', 5, client=client, semaphore=semaphore, sleep=sleep
        )
    assert [word['text'] for word in words] == ['Synthetic', 'fixture.'] and language == 'vi'
    assert sum(method == 'POST' for method, _ in calls) == 2
    assert len(sleeps) == 2
    assert calls[-2:] == [('DELETE', f'/v1/transcriptions/{TRANSCRIPTION}'), ('DELETE', f'/v1/files/{FILE}')]


@pytest.mark.asyncio
async def test_queued_deadline_is_bounded_without_retry():
    now, calls = [0.0], []

    async def handler(request):
        calls.append(request.method)
        if request.method == 'DELETE':
            return httpx.Response(204)
        if request.url.path == '/v1/files':
            return httpx.Response(201, json={'id': FILE})
        return httpx.Response(200, json={'id': TRANSCRIPTION, 'status': 'queued'})

    async def sleep(seconds):
        now[0] += seconds
        await asyncio.sleep(0)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(module.SonioxBatchError):
            await module.transcribe_async(b'synthetic', 5, client=client, clock=lambda: now[0], sleep=sleep)
    assert calls.count('POST') == 2 and calls.count('GET') < 60
    assert now[0] == 120


@pytest.mark.asyncio
async def test_cancelled_poll_cleans_only_its_resources_without_resubmission():
    entered, calls = asyncio.Event(), []

    async def handler(request):
        calls.append((request.method, request.url.path))
        if request.method == 'DELETE':
            return httpx.Response(204)
        if request.url.path == '/v1/files':
            return httpx.Response(201, json={'id': FILE})
        if request.method == 'POST':
            return httpx.Response(201, json={'id': TRANSCRIPTION, 'status': 'queued'})
        entered.set()
        await asyncio.Event().wait()

    async def sleep(_):
        await asyncio.sleep(0)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        task = asyncio.create_task(module.transcribe_async(b'synthetic', 5, client=client, sleep=sleep))
        await asyncio.wait_for(entered.wait(), 10)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert sum(method == 'POST' for method, _ in calls) == 2
    assert sum(method == 'DELETE' for method, _ in calls) == 2


@pytest.mark.asyncio
async def test_http_queue_wait_counts_against_deadline(monkeypatch):
    # Only the timeout path is exercised: the semaphore never opens. Keep the
    # real-clock budget large enough for loaded CI runners (#22758/#22767).
    monkeypatch.setattr(module, 'DEADLINE_SECONDS', 1.0)
    client = AsyncMock()
    with pytest.raises(module.SonioxBatchError):
        await module.transcribe_async(b'synthetic', 5, client=client, semaphore=asyncio.Semaphore(0))
    client.request.assert_not_called()


@pytest.mark.asyncio
async def test_default_off_prevents_even_an_upload(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_INDEPENDENT_LANGUAGE_RECOVERY_ENABLED')
    client = AsyncMock()
    with pytest.raises(module.SonioxBatchError):
        await module.transcribe_async(b'synthetic', 5, client=client)
    client.request.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('stage', ['upload', 'create', 'poll', 'transcript'])
async def test_async_http_error_never_becomes_empty_or_retried(stage, caplog):
    calls = []

    async def handler(request):
        calls.append((request.method, request.url.path))
        if request.method == 'DELETE':
            return httpx.Response(204)
        point = (
            'upload'
            if request.url.path == '/v1/files'
            else (
                'create'
                if request.method == 'POST'
                else 'transcript' if request.url.path.endswith('/transcript') else 'poll'
            )
        )
        if point == stage:
            return httpx.Response(500, text='PRIVATE_SENTINEL')
        if point == 'upload':
            return httpx.Response(201, json={'id': FILE})
        return httpx.Response(200, json={'id': TRANSCRIPTION, 'status': 'queued' if stage == 'poll' else 'completed'})

    async def sleep(_):
        await asyncio.sleep(0)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(module.SonioxBatchError):
            await module.transcribe_async(b'synthetic', 5, client=client, sleep=sleep)
    assert sum(method == 'POST' for method, _ in calls) <= 2
    assert 'PRIVATE_SENTINEL' not in caplog.text
