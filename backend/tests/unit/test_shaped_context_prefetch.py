"""Context reads overlap setup; fresh mount fences and continuity outcomes stay bounded."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from utils.messaging import context


@pytest.fixture
def reads(monkeypatch):
    outcomes, overlaps = [], []
    monkeypatch.setattr(
        context,
        'CONTEXT_TURNS',
        SimpleNamespace(labels=lambda surface, outcome: SimpleNamespace(inc=lambda: outcomes.append(outcome))),
    )
    monkeypatch.setattr(
        context,
        'CONTEXT_SETUP_OVERLAP',
        SimpleNamespace(labels=lambda surface: SimpleNamespace(observe=overlaps.append)),
    )
    monkeypatch.setattr(context, 'record_fallback', lambda **kw: None)
    return outcomes, overlaps


def install_reads(
    monkeypatch, summary_gate, digest_gate, *, failure=None, summary_text='Saved continuity', validation_failure=None
):
    store = SimpleNamespace(load_for_turn=lambda *a: None, validate_for_turn=lambda *a: None)
    monkeypatch.setattr(context, 'ChatContextStore', lambda: store)
    started = set()

    async def blocking(executor, function, *args):
        if function is context.ChatContextStore:
            return store
        if function == store.load_for_turn:
            started.add('summary')
            await summary_gate.wait()
            if failure:
                raise failure
            return {'summary': summary_text}
        if function == store.validate_for_turn:
            if validation_failure is not None:
                raise validation_failure
            return None
        assert function is context.recent_activity
        started.add('digest')
        await digest_gate.wait()
        return [{'created_at': datetime(2026, 10, 16, tzinfo=timezone.utc), 'text': 'Other activity'}]

    monkeypatch.setattr(context, 'run_blocking', blocking)
    return started


async def settle():
    # wait_for creates child tasks; let both independent readers publish results.
    for _ in range(8):
        await asyncio.sleep(0)


@pytest.mark.parametrize(
    'summary_ready,digest_ready,outcome',
    [
        (True, True, 'summary'),
        (True, False, 'digest_degraded'),
        (False, True, 'summary_pending'),
        (False, False, 'summary_pending'),
    ],
)
def test_model_mount_samples_without_waiting_and_counts_once(monkeypatch, reads, summary_ready, digest_ready, outcome):
    async def run():
        summary, digest = asyncio.Event(), asyncio.Event()
        install_reads(monkeypatch, summary, digest)
        async with context.preparation_scope('u', 's', ['m']) as pending:
            if summary_ready:
                summary.set()
            if digest_ready:
                digest.set()
            await settle()
            result = await context.take_prepared('u', 's')
            assert result is not None
            assert result['summary'] == ('Saved continuity' if summary_ready else '')
            assert bool(result['digest']) == (summary_ready and digest_ready)
            assert await context.take_prepared('u', 's') is result
            assert reads[0] == [outcome] and len(reads[1]) == 1
        assert all(task.done() for task in pending.tasks)
        assert await context.take_prepared('u', 's') is None

    asyncio.run(run())


def test_failed_security_guard_discards_ready_digest_without_exception_payload(monkeypatch, reads, caplog):
    async def run():
        summary, digest = asyncio.Event(), asyncio.Event()
        install_reads(monkeypatch, summary, digest, failure=PermissionError('private synthetic payload'))
        summary.set()
        digest.set()
        async with context.preparation_scope('u', 's', ['m']):
            await settle()
            assert await context.take_prepared('u', 's') == {'summary': '', 'digest': ''}
        assert reads[0] == ['degraded']

    asyncio.run(run())
    assert 'phase=summary_load error_type=PermissionError' in caplog.text
    assert 'private synthetic payload' not in caplog.text


def test_unscoped_and_wrong_identity_never_read_or_consume(monkeypatch, reads):
    monkeypatch.setattr(context, 'run_blocking', lambda *a: pytest.fail('unscoped IO'))

    async def run():
        async with context.preparation_scope('u', 's', []):
            assert await context.take_prepared('other', 's') is None
            assert await context.take_prepared('u', 'other') is None
            assert await context.take_prepared('u', 's') == {'summary': '', 'digest': ''}
        assert reads == (['unscoped'], [])

    asyncio.run(run())


def test_nested_scopes_restore_identity_and_cancel_unfinished_reads(monkeypatch, reads):
    async def run():
        install_reads(monkeypatch, asyncio.Event(), asyncio.Event())
        async with context.preparation_scope('u', 's', ['m']) as outer:
            async with context.preparation_scope('u', 't', ['m']) as inner:
                await settle()
                assert await context.take_prepared('u', 's') is None
            assert all(task.cancelled() for task in inner.tasks)
            assert await context.take_prepared('u', 's') == {'summary': '', 'digest': ''}
        assert all(task.cancelled() for task in outer.tasks)

    asyncio.run(run())


@pytest.fixture
def graph():
    from utils.retrieval import graph

    return graph


def test_real_router_overlaps_reads_slower_than_old_budgets(monkeypatch, reads, graph):
    async def run():
        summary, digest = asyncio.Event(), asyncio.Event()
        started = install_reads(monkeypatch, summary, digest)
        monkeypatch.setattr(graph, 'route_for_uid', lambda uid: 'new')
        loop = asyncio.get_running_loop()

        async def metadata(*args, **kwargs):
            await settle()
            assert started == {'summary', 'digest'}
            # Real observed p95s exceed both retired foreground deadlines.
            loop.call_later(0.1, digest.set)
            loop.call_later(0.27, summary.set)
            await summary.wait()
            await settle()
            return '', 'UTC'

        async def model(uid, messages, app, **kwargs):
            result = await context.take_prepared(uid, kwargs['chat_session'].id)
            assert result is not None
            assert result['summary'] == 'Saved continuity' and result['digest']
            yield 'first token'

        monkeypatch.setattr(graph, '_current_prompt_metadata', metadata)
        monkeypatch.setattr(graph, 'execute_agentic_chat_stream', model)
        chunks = [
            chunk
            async for chunk in graph.execute_chat_stream(
                'u',
                [SimpleNamespace(id='m')],
                chat_session=SimpleNamespace(id='s'),
                shaped_invocation=True,
            )
        ]
        assert chunks == ['first token'] and reads[0] == ['summary']
        assert reads[1][0] >= 0.27

    asyncio.run(run())


@pytest.mark.parametrize('route', ['old', 'shadow'])
def test_old_and_shadow_router_start_no_context_reads(monkeypatch, reads, graph, route):
    monkeypatch.setattr(graph, 'route_for_uid', lambda uid: route)
    monkeypatch.setattr(context, 'run_blocking', lambda *a: pytest.fail('non-shaped IO'))

    async def metadata(*args, **kwargs):
        return '', 'UTC'

    async def model(*args, **kwargs):
        assert await context.take_prepared('u', 's') is None
        yield 'unchanged'

    monkeypatch.setattr(graph, '_current_prompt_metadata', metadata)
    monkeypatch.setattr(graph, 'execute_agentic_chat_stream', model)

    async def run():
        return [
            chunk
            async for chunk in graph.execute_chat_stream(
                'u',
                [SimpleNamespace(id='m')],
                chat_session=SimpleNamespace(id='s'),
                shaped_invocation=True,
            )
        ]

    assert asyncio.run(run()) == ['unchanged'] and reads == ([], [])


@pytest.mark.parametrize('exit_mode', ['setup_timeout', 'cancel', 'close'])
def test_router_cleans_up_reads_on_every_early_exit(monkeypatch, reads, graph, exit_mode):
    async def run():
        started = install_reads(monkeypatch, asyncio.Event(), asyncio.Event())
        monkeypatch.setattr(graph, 'route_for_uid', lambda uid: 'new')
        captured = []
        original = context.ContextPreparation

        def capture(*args, **kwargs):
            pending = original(*args, **kwargs)
            captured.append(pending)
            return pending

        monkeypatch.setattr(context, 'ContextPreparation', capture)
        ready = asyncio.Event()

        async def metadata(*args, **kwargs):
            await settle()
            ready.set()
            if exit_mode == 'setup_timeout':
                raise TimeoutError()
            if exit_mode == 'cancel':
                await asyncio.Event().wait()
            return '', 'UTC'

        async def model(*args, **kwargs):
            yield 'token'
            await asyncio.Event().wait()

        monkeypatch.setattr(graph, '_current_prompt_metadata', metadata)
        monkeypatch.setattr(graph, 'execute_agentic_chat_stream', model)
        stream = graph.execute_chat_stream(
            'u',
            [SimpleNamespace(id='m')],
            chat_session=SimpleNamespace(id='s'),
            shaped_invocation=True,
        )
        if exit_mode == 'cancel':
            task = asyncio.create_task(anext(stream))
            await ready.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        elif exit_mode == 'close':
            assert await anext(stream) == 'token'
            await stream.aclose()
        else:
            assert [chunk async for chunk in stream][-1] is None
        assert started == {'summary', 'digest'}
        assert all(task.done() for task in captured[0].tasks)
        assert await context.take_prepared('u', 's') is None

    asyncio.run(run())


def test_real_shaped_runner_streams_with_ready_summary_while_digest_is_pending(monkeypatch, reads):
    from utils.retrieval import agentic, shaped_chat

    async def run():
        summary, digest = asyncio.Event(), asyncio.Event()
        install_reads(monkeypatch, summary, digest)
        summary.set()
        captured = []

        class Model:
            model_name = 'gpt-5.6'

            def bind(self, **kwargs):
                return self

            async def astream(self, messages):
                assert not digest.is_set()
                captured.append(str(messages))
                yield SimpleNamespace(content='Answer', tool_calls=[], tool_call_chunks=[], additional_kwargs={})

        async def forbidden(*args, **kwargs):
            pytest.fail('prefetched turn must never join foreground prepare')

        monkeypatch.setattr(context, 'prepare', forbidden)
        monkeypatch.setattr(context, 'schedule_refresh', lambda *args: None)
        monkeypatch.setattr(agentic, 'get_llm', lambda *args, **kwargs: Model())
        monkeypatch.setattr(agentic, 'gpt56_explicit_cache_enabled', lambda: False)
        async with context.preparation_scope('u', 's', ['m']):
            await settle()
            output = []
            await asyncio.create_task(
                shaped_chat.run_shaped_chat_stream(
                    '',
                    [{'role': 'user', 'content': 'Request'}],
                    [],
                    {},
                    agentic.AsyncStreamingCallback(),
                    output,
                    agentic.AgentSafetyGuard(),
                    {'user_id': 'u', 'chat_session_id': 's', 'context_message_ids': ['m']},
                )
            )
            assert output == ['Answer']
            assert 'Saved continuity' in captured[0] and 'Activity elsewhere' not in captured[0]
            assert reads[0] == ['digest_degraded']

    asyncio.run(run())


def test_ready_empty_state_and_pending_digest_have_distinct_outcome(monkeypatch, reads):
    async def run():
        summary, digest = asyncio.Event(), asyncio.Event()
        install_reads(monkeypatch, summary, digest, summary_text='')
        summary.set()
        async with context.preparation_scope('u', 's', ['m']):
            await settle()
            assert await context.take_prepared('u', 's') == {'summary': '', 'digest': ''}
            assert reads[0] == ['empty_digest_degraded']

    asyncio.run(run())


@pytest.mark.parametrize(
    'failure,outcome',
    [
        (TimeoutError(), 'summary_pending'),
        (context.ExecutorSaturatedError('synthetic saturation'), 'summary_pending'),
        (PermissionError('synthetic revoke'), 'degraded'),
    ],
)
def test_unchecked_ready_summary_and_digest_are_never_injected(monkeypatch, reads, failure, outcome):
    async def run():
        summary, digest = asyncio.Event(), asyncio.Event()
        install_reads(monkeypatch, summary, digest, validation_failure=failure)
        summary.set()
        digest.set()
        async with context.preparation_scope('u', 's', ['m']):
            await settle()
            assert await context.take_prepared('u', 's') == {'summary': '', 'digest': ''}
            assert await context.take_prepared('u', 's') == {'summary': '', 'digest': ''}
            assert reads[0] == [outcome]

    asyncio.run(run())
