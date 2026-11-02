"""Revision-drain harness: request-backed work survives a Cloud Run revision replacement.

Fire-and-forget work still running at SIGKILL is flagged lost (the 2026-10-18
paid-recovery incident shape, fixed for quarantine recovery by #22149).
"""

import asyncio
import threading
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import BackgroundTasks, FastAPI

from tests.unit.fixtures.revision_drain import (
    COMPLETED,
    EXECUTOR,
    FIRE_AND_FORGET,
    KILLED,
    POST_RESPONSE,
    REQUEST_SCOPED,
    RevisionDrainHarness,
    RevisionDraining,
    TASK,
)
from routers import batch_pipeline as routes
from tests.unit import test_batch_pipeline_quarantine_recovery as recovery_tests
from utils.batch_pipeline import quarantine_recovery as module
from utils.batch_pipeline.serving import Serving
from utils.executors import run_blocking, start_background_task, submit_with_context, sync_executor

row = recovery_tests.row
setup = recovery_tests.setup  # shared pytest fixture, bound by name for injection


def _synthetic_app(release: threading.Event) -> FastAPI:
    app = FastAPI()

    async def slow_coroutine():
        await asyncio.sleep(0.05)
        return 'done'

    def slow_blocking():
        assert release.wait(2)
        return 'done'

    @app.post('/awaited')
    async def awaited():
        child = asyncio.create_task(slow_coroutine(), name='awaited-child')
        await child
        await run_blocking(sync_executor, slow_blocking)
        return {'status': 'ok'}

    @app.post('/fire-and-forget')
    async def fire_and_forget():
        start_background_task(asyncio.sleep(30), name='synthetic-background-coroutine')
        submit_with_context(sync_executor, slow_blocking)
        return {'status': 'accepted'}

    @app.post('/fast-fire-and-forget')
    async def fast_fire_and_forget():
        start_background_task(asyncio.sleep(0.01), name='synthetic-quick-background')
        return {'status': 'accepted'}

    @app.post('/background-tasks')
    async def background_tasks(tasks: BackgroundTasks):
        tasks.add_task(asyncio.sleep, 30)
        return {'status': 'accepted'}

    return app


async def test_awaited_work_survives_drain_of_an_in_flight_request():
    release = threading.Event()
    async with RevisionDrainHarness(_synthetic_app(release)) as harness:
        unit = harness.request('POST', '/awaited')
        await asyncio.sleep(0.01)
        drain = asyncio.create_task(harness.replace_revision(drain_timeout=2, grace_seconds=0.05))
        await asyncio.sleep(0.02)
        assert not drain.done()  # The in-flight request keeps the old revision alive.
        with pytest.raises(RevisionDraining):
            harness.request('POST', '/awaited')
        release.set()
        report = await drain

    assert (await harness.response(unit)).json() == {'status': 'ok'}
    report.assert_no_lost_work()
    assert report.one('POST /awaited').outcome == COMPLETED
    child = report.one('awaited-child')
    assert (child.kind, child.scope, child.outcome) == (TASK, REQUEST_SCOPED, COMPLETED)
    blocking = report.one('slow_blocking')
    assert (blocking.kind, blocking.scope, blocking.outcome) == (EXECUTOR, REQUEST_SCOPED, COMPLETED)


async def test_fire_and_forget_work_running_at_kill_is_flagged_lost():
    release = threading.Event()
    try:
        async with RevisionDrainHarness(_synthetic_app(release)) as harness:
            unit = harness.request('POST', '/fire-and-forget')
            assert (await harness.response(unit)).json() == {'status': 'accepted'}
            report = await harness.replace_revision(grace_seconds=0.05)
    finally:
        release.set()

    assert report.one('POST /fire-and-forget').outcome == COMPLETED
    coroutine = report.one('synthetic-background-coroutine')
    assert (coroutine.kind, coroutine.scope, coroutine.outcome) == (TASK, FIRE_AND_FORGET, KILLED)
    thread = report.one('slow_blocking')
    assert (thread.kind, thread.scope, thread.outcome) == (EXECUTOR, FIRE_AND_FORGET, KILLED)
    assert {unit.name for unit in report.lost} == {'synthetic-background-coroutine', thread.name}
    with pytest.raises(AssertionError, match='fire-and-forget work killed'):
        report.assert_no_lost_work()


async def test_fire_and_forget_that_beats_the_grace_period_is_unprotected_not_lost():
    async with RevisionDrainHarness(_synthetic_app(threading.Event())) as harness:
        await harness.response(harness.request('POST', '/fast-fire-and-forget'))
        report = await harness.replace_revision(grace_seconds=0.5)

    quick = report.one('synthetic-quick-background')
    assert (quick.scope, quick.outcome) == (FIRE_AND_FORGET, COMPLETED)
    assert quick in report.survived_by_luck
    report.assert_no_lost_work()


async def test_fastapi_background_tasks_run_after_the_response_and_are_lost():
    async with RevisionDrainHarness(_synthetic_app(threading.Event())) as harness:
        unit = harness.request('POST', '/background-tasks')
        assert (await harness.response(unit)).json() == {'status': 'accepted'}
        report = await harness.replace_revision(grace_seconds=0.05)

    post = report.one('post-response POST /background-tasks')
    assert (post.kind, post.scope, post.outcome) == (POST_RESPONSE, FIRE_AND_FORGET, KILLED)
    assert report.one('POST /background-tasks').outcome == COMPLETED


async def test_quick_background_task_is_still_recorded_as_post_response():
    """A BackgroundTasks callback that finishes between the response and
    ``replace_revision()`` must not vanish from the report (review finding:
    recording only at replacement time is timing-dependent)."""
    app = FastAPI()

    @app.post('/quick-background-tasks')
    async def quick_background_tasks(tasks: BackgroundTasks) -> dict:
        tasks.add_task(asyncio.sleep, 0.01)
        return {'status': 'accepted'}

    async with RevisionDrainHarness(app) as harness:
        unit = harness.request('POST', '/quick-background-tasks')
        assert (await harness.response(unit)).json() == {'status': 'accepted'}
        await asyncio.sleep(0.05)  # The callback completes long before revision replacement.
        report = await harness.replace_revision(grace_seconds=0.05)

    post = report.one('post-response POST /quick-background-tasks')
    assert (post.kind, post.scope, post.outcome) == (POST_RESPONSE, FIRE_AND_FORGET, COMPLETED)
    assert post in report.survived_by_luck


def _paid_stt(harness_ref: list, entered: threading.Event, release: threading.Event):
    def paid_call(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        harness_ref[0].checkpoint()  # A SIGKILLed process never sees the provider reply.
        return {'synthetic': True}

    return paid_call


async def test_real_recover_quarantine_handler_keeps_paid_call_inside_the_drained_request(setup, monkeypatch):

    client, store, binding, artifacts, stt, recovery = setup
    entered, release, harness_ref = threading.Event(), threading.Event(), []
    stt.side_effect = _paid_stt(harness_ref, entered, release)
    service = Serving(store, recovery=recovery)
    service.reconcile_async = AsyncMock()
    monkeypatch.setattr(routes, 'serving_for_stage', lambda stage: service)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.verify_worker] = lambda: 0

    try:
        async with RevisionDrainHarness(app) as harness:
            harness_ref.append(harness)
            unit = harness.request(
                'POST', '/v2/batch-pipeline/recover-quarantine', json={'stage': 'prod', 'segment_id': 'bad'}
            )
            assert await asyncio.to_thread(entered.wait, 2)
            drain = asyncio.create_task(harness.replace_revision(drain_timeout=3, grace_seconds=0.05))
            await asyncio.sleep(0.05)
            assert not drain.done()  # Paid provider call is in flight inside the request.
            release.set()
            report = await drain
    finally:
        release.set()

    assert (await harness.response(unit)).json() == {'status': 'recovered'}
    report.assert_no_lost_work()
    assert report.one('POST /v2/batch-pipeline/recover-quarantine').outcome == COMPLETED
    executor_work = [u for u in report.units if u.kind == EXECUTOR]
    assert executor_work and all(u.scope == REQUEST_SCOPED and u.outcome == COMPLETED for u in executor_work)
    assert row(client)['recovery_state'] == 'recovered'
    stt.assert_called_once()
    service.reconcile_async.assert_awaited_once_with(owner_id=binding.owner_id, recovered='bad')


async def test_pre_22149_inline_fire_and_forget_recovery_is_flagged_lost(setup, monkeypatch):
    """Characterize the pre-#22149 shape: the inline sweep spends paid STT off-request."""
    client, store, binding, artifacts, stt, recovery = setup
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_TASKS_ENABLED', 'false')  # Inline sweep (rollback shape).
    monkeypatch.setattr(module, 'recovery_candidates', Mock(return_value=[('bad', binding.owner_id)]))
    entered, release, harness_ref = threading.Event(), threading.Event(), []
    stt.side_effect = _paid_stt(harness_ref, entered, release)
    app = FastAPI()

    @app.post('/legacy-reconcile')
    async def legacy_reconcile():
        async def sweep():
            await run_blocking(sync_executor, recovery.sweep)

        start_background_task(sweep(), name='legacy-quarantine-sweep')
        return {'status': 'accepted'}

    try:
        async with RevisionDrainHarness(app) as harness:
            harness_ref.append(harness)
            unit = harness.request('POST', '/legacy-reconcile')
            assert (await harness.response(unit)).json() == {'status': 'accepted'}
            assert await asyncio.to_thread(entered.wait, 2)
            report = await harness.replace_revision(grace_seconds=0.05)
            release.set()
            await asyncio.sleep(0.05)
    finally:
        release.set()

    lost = {unit.name for unit in report.lost}
    assert 'legacy-quarantine-sweep' in lost
    sweep = report.one('QuarantineRecovery.sweep')
    assert sweep.kind == EXECUTOR and sweep.lost
    stt.assert_called_once()
    # The paid intent started but never settled: an uncertain, unrecoverable-by-retry obligation.
    assert row(client)['recovery_state'] == 'running'
    artifacts.persist_recovery_result.assert_not_called()
