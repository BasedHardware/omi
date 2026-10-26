"""Provider waits preserve paid fences without borrowing a shared blocking slot."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock

import pytest

from utils.batch_pipeline import recovery_steps as steps
from tests.unit.test_batch_pipeline_quarantine_recovery import setup, legacy_dependencies, row
from tests.unit.test_batch_language_recovery import guarded, WORDS
from tests.unit.test_batch_pipeline_shadow import repository, running, row as shadow_row
from tests.unit.test_batch_pipeline_empty_disposition import wav
from utils.batch_pipeline.recovery_disposition import MultilingualEmpty
from utils.batch_pipeline.shadow_recovery import recover_async as shadow_recover_async


@pytest.mark.asyncio
async def test_waiting_provider_leaves_a_single_blocking_slot_available(monkeypatch):
    slot, entered, release = asyncio.Semaphore(1), asyncio.Event(), asyncio.Event()
    active = [0]

    async def blocking(_, function, *arguments):
        async with slot:
            active[0] += 1
            try:
                return function(*arguments)
            finally:
                active[0] -= 1

    async def provider():
        assert active[0] == 0
        entered.set()
        await release.wait()
        return 'words'

    wrong_sync = Mock(side_effect=AssertionError('serving must use async provider'))

    def pipeline():
        reply = yield steps.ProviderStep(wrong_sync, (), provider)
        return reply.result()

    monkeypatch.setattr(steps, 'run_blocking', blocking)
    task = asyncio.create_task(steps.run_async(pipeline()))
    await asyncio.wait_for(entered.wait(), 10)
    assert await asyncio.wait_for(blocking(None, lambda: 'unrelated work'), 10) == 'unrelated work'
    release.set()
    assert await task == 'words'
    wrong_sync.assert_not_called()


@pytest.mark.parametrize('failure', [False, True])
def test_sync_operator_driver_preserves_reply_and_never_retries(failure):
    provider = Mock(side_effect=ValueError('synthetic')) if failure else Mock(return_value='words')

    def pipeline():
        reply = yield steps.ProviderStep(provider, ())
        try:
            return reply.result()
        except ValueError:
            return 'held'

    assert steps.run_sync(pipeline()) == ('held' if failure else 'words')
    provider.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('answer', ['words', 'empty', 'zero', 'error'])
async def test_async_record_recovery_keeps_existing_disposition_and_single_claim(
    setup, monkeypatch, legacy_dependencies, answer
):
    client, _, binding, artifacts, modulate, soniox, recovery, _ = guarded(
        setup, monkeypatch, legacy_dependencies, speech=0 if answer == 'zero' else 1
    )
    if answer == 'words':
        soniox.return_value = (WORDS, 'vi')
    elif answer == 'error':
        soniox.side_effect = TimeoutError('synthetic')
    expected = 'recovered' if answer in {'words', 'zero'} else 'failed_held'
    assert await recovery.recover_async('bad', binding.owner_id) == expected
    assert await recovery.recover_async('bad', binding.owner_id) == 'held'
    assert modulate.call_count == soniox.call_count == 1
    assert row(client)['recovery']['recognizers']['soniox']['outcome'] == (
        'words' if answer == 'words' else 'error' if answer == 'error' else 'empty'
    )


@pytest.mark.asyncio
async def test_cancelled_provider_keeps_running_claim_and_cannot_spend_again(setup, monkeypatch, legacy_dependencies):
    client, _, binding, _, _, _, recovery, _ = guarded(setup, monkeypatch, legacy_dependencies)
    entered = asyncio.Event()

    async def wait_for_provider(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    alternate = AsyncMock(side_effect=wait_for_provider)
    monkeypatch.setattr('utils.stt.soniox_batch.transcribe_async', alternate)
    task = asyncio.create_task(recovery.recover_async('bad', binding.owner_id))
    await asyncio.wait_for(entered.wait(), 10)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert row(client)['recovery_state'] == 'running'
    assert row(client)['recovery']['recognizers']['soniox']['outcome'] == 'started'
    assert await recovery.recover_async('bad', binding.owner_id) == 'held'
    alternate.assert_awaited_once()


def test_failed_queue_keeps_guarded_obligation_out_of_inline_executor(setup, monkeypatch, legacy_dependencies):
    client, _, binding, _, _, soniox, recovery, _ = guarded(setup, monkeypatch, legacy_dependencies)

    def failed_dispatch(*args):
        recovery.protocol.prepare('bad', binding.owner_id, 100)
        raise RuntimeError('synthetic queue outage')

    monkeypatch.setattr(recovery, '_dispatch', failed_dispatch)
    inline = Mock(side_effect=AssertionError('must not poll inside maintenance slot'))
    monkeypatch.setattr(recovery, 'recover', inline)
    assert recovery.dispatch('bad', binding.owner_id) == 'held'
    assert row(client)['recovery_state'] == 'prepared'
    inline.assert_not_called()
    soniox.assert_not_called()


@pytest.mark.asyncio
async def test_record_endpoint_awaits_coordinator_instead_of_sync_wrapper(monkeypatch):
    from routers import batch_pipeline as router

    recovery = SimpleNamespace(recover=Mock(), recover_async=AsyncMock(return_value='failed_held'))
    store = SimpleNamespace(run=lambda operation: {'owner_id': 'synthetic-owner'})
    service = SimpleNamespace(recovery=recovery, store=store)
    body = SimpleNamespace(service=lambda: service, segment_id='synthetic-unit')

    async def blocking(_, function, *arguments, **kwargs):
        return function(*arguments, **kwargs)

    monkeypatch.setattr(router, 'run_blocking', blocking)
    assert await router.recover_quarantine(body, SimpleNamespace(headers={})) == {'status': 'failed_held'}
    recovery.recover_async.assert_awaited_once_with('synthetic-unit', 'synthetic-owner')
    recovery.recover.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('words', [False, True])
async def test_async_shadow_uses_same_single_independent_intent(repository, monkeypatch, words):
    monkeypatch.setenv('SONIOX_API_KEY', 'synthetic-only-key')
    item = running(repository, duration=20, guarded=True)
    spans = [{'start': 0, 'end': 2}]
    first = Mock(side_effect=MultilingualEmpty(20, spans))
    alternate = AsyncMock(return_value=(WORDS if words else [], 'vi'))
    monkeypatch.setattr('utils.stt.soniox_batch.transcribe_async', alternate)
    artifacts = SimpleNamespace(fetch_audio=lambda _: wav(20))
    assert await shadow_recover_async(
        repository, artifacts, item.segment_id, stt=first, inspect=lambda *a: (b'', 20, spans)
    ) == ('recovered' if words else 'failed_held')
    assert shadow_row(repository, item.segment_id)['paid_providers'] == ['modulate', 'soniox']
    assert await shadow_recover_async(repository, artifacts, item.segment_id) == 'held'
    alternate.assert_awaited_once()
    first.assert_called_once()


@pytest.mark.asyncio
async def test_shadow_endpoint_awaits_coordinator_instead_of_sync_wrapper(monkeypatch):
    from routers import batch_pipeline as router

    coordinator = AsyncMock(return_value='failed_held')
    monkeypatch.setattr('utils.batch_pipeline.shadow_recovery.recover_async', coordinator)
    artifacts = Mock()
    monkeypatch.setattr('utils.batch_pipeline.artifact_policy.artifacts_for', lambda _: artifacts)
    service = SimpleNamespace(store=Mock())
    body = SimpleNamespace(service=lambda: service, segment_id='synthetic-unit')

    async def blocking(_, function, *arguments, **kwargs):
        return function(*arguments, **kwargs)

    monkeypatch.setattr(router, 'run_blocking', blocking)
    assert await router.shadow_recover(body) == {'status': 'failed_held'}
    coordinator.assert_awaited_once()
    assert coordinator.await_args.args[1:] == (artifacts, 'synthetic-unit')
