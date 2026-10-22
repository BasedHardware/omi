"""Shutdown-drain refusal regression: submitting during drain must not crash the caller.

Prod pusher, deploy drain window 2026-10-21 23:00Z (both signatures in the same
30-min window, Loop S feed):

    ERROR:utils.conversations.process_conversation:Error creating audio files:
    cannot schedule new futures after shutdown                       (x9/30m)
    ERROR:utils.llm.gateway_error_contract:Conversation processing
    failed: RuntimeError                                             (x14/30m)

Root cause: ``shutdown_executors()`` (deploy drain) refuses every later
``executor.submit`` with ``RuntimeError: cannot schedule new futures after
shutdown``. Conversation finalization was still running and submitted its
background fan-out (vector save, action items, goals, webhook, audio precache)
to the shared pools; that refusal raced out of the audio block as the
``Error creating audio files`` degrade and out of the whole composition
boundary as the ``Conversation processing failed: RuntimeError`` 500. The fix
classifies the drain refusal at the shared submit boundary: fire-and-forget
work resolves to a no-op future with one bounded INFO; result-consuming
callers keep the real exception. Raw fire-and-forget ``executor.submit``
call sites migrated onto the boundary are pinned by source (repo precedent:
test_wrapped_error_sanitization.py).

The ``cannot schedule new futures`` message string is CPython's
``concurrent.futures`` shutdown guard; the suites below drive both the real
boundary against a genuinely shut-down pool and the exact refusal text.

Failure-Class: FC-drain-refusal-crashes-fire-and-forget-caller — a
fire-and-forget executor submit raised the shutdown drain's refusal
(``RuntimeError: cannot schedule new futures after shutdown``) into its
caller instead of being classified as the bounded drain it is. The caller
chain turned every deploy into user-visible failures for otherwise-successful
conversations: the conversation-created webhook, structured vector save,
action items, goal updates and the audio precache fan-out all cross the
shared pools, so the audio block degraded (``Error creating audio files:
cannot schedule new futures after shutdown``, pusher x9/30m) and the
composition boundary failed (``Conversation processing failed: RuntimeError``,
pusher x14/30m) in the same drain window. Fixed by classifying the refusal at
the shared ``submit_with_context`` boundary — a drained submit resolves to a
no-op future with one bounded INFO — migrating every fire-and-forget raw
submit onto that boundary, and downgrading the same refusal in a task body's
background-failure log. Result-consuming submits intentionally keep raising.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "fake-key-for-hermetic-tests")

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from utils import executors
from utils.executors import MonitoredThreadPoolExecutor, submit_with_context

_BACKEND = Path(__file__).resolve().parents[2]
_DRAIN_MESSAGE = 'cannot schedule new futures after shutdown'


def _drained_pool() -> ThreadPoolExecutor:
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='drain-test')
    pool.shutdown(wait=True, cancel_futures=True)
    return pool


def test_submit_during_drain_resolves_to_noop_future_instead_of_runtime_error():
    """The x9/x14 crash arm: submit on a drained pool returns a resolved future."""
    pool = _drained_pool()
    executed = []
    future = submit_with_context(pool, lambda: executed.append(1))
    assert future.done() and future.exception() is None and future.result() is None
    assert executed == []


def test_submit_during_drain_is_bounded_info_not_error(caplog):
    """The refusal is the drain, not a fault: one INFO, no traceback payload."""
    pool = MonitoredThreadPoolExecutor(name='drain-test', max_workers=1)
    pool.shutdown(wait=True, cancel_futures=True)

    def work():
        raise AssertionError('drained submit must never execute')

    with caplog.at_level(logging.DEBUG, logger='utils.executors'):
        submit_with_context(pool, work)
    infos = [r for r in caplog.records if r.levelno == logging.INFO and 'executor_drained' in r.message]
    errors = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(infos) == 1
    assert 'drain-test' in infos[0].message  # the executor name is attributed
    assert errors == []


def test_submit_during_drain_never_invokes_the_task_body():
    pool = _drained_pool()
    entered = threading.Event()

    def work():
        entered.set()

    future = submit_with_context(pool, work)
    assert future.result(timeout=1) is None
    assert not entered.is_set()


def test_submit_result_caller_still_gets_task_exception():
    """Result-consuming callers keep the task's own failure (unchanged contract)."""
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='result-test')

    def boom():
        raise ValueError('task fault')

    try:
        with pytest.raises(ValueError, match='task fault'):
            submit_with_context(pool, boom).result(timeout=2)
    finally:
        pool.shutdown(wait=True)


def test_submit_normal_path_unchanged():
    """The happy path still executes with a live future."""
    pool = MonitoredThreadPoolExecutor(name='happy', max_workers=1)
    marker = threading.Event()
    try:
        future = submit_with_context(pool, marker.set)
        assert future.result(timeout=2) is None
        assert marker.is_set()
    finally:
        pool.shutdown(wait=True)


def test_non_drain_runtime_error_still_raises():
    """Only the shutdown guard is absorbed; any other RuntimeError propagates."""

    class HostilePool:
        name = 'hostile'

        def submit(self, *args, **kwargs):
            raise RuntimeError('executor is on fire for another reason')

    with pytest.raises(RuntimeError, match='on fire'):
        submit_with_context(HostilePool(), lambda: None)  # type: ignore[arg-type]


def test_monitored_executor_drain_refusal_is_absorbed_by_the_boundary():
    """MonitoredThreadPoolExecutor.submit is the CPython guard, unmodified."""
    pool = MonitoredThreadPoolExecutor(name='monitored-drain', max_workers=1)
    pool.shutdown(wait=True, cancel_futures=True)
    with pytest.raises(RuntimeError, match=_DRAIN_MESSAGE):
        pool.submit(lambda: None)
    # ... and the shared boundary absorbs exactly that refusal.
    executed = []
    future = submit_with_context(pool, lambda: executed.append(1))
    assert future.done() and executed == []


def test_background_failure_log_downgrades_drain_refusal_to_info(caplog):
    """A task body whose own fan-out hit the drain logs one INFO, no traceback."""
    error = RuntimeError(_DRAIN_MESSAGE)
    future: Future = Future()
    future.set_exception(error)
    with caplog.at_level(logging.DEBUG, logger='utils.executors'):
        executors._log_background_failure('fanned-out-task', future)  # noqa: SLF001
    infos = [r for r in caplog.records if r.levelno == logging.INFO and 'executor_drained' in r.message]
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(infos) == 1
    assert errors == []


def test_background_failure_log_keeps_real_failures_at_error(caplog):
    error = RuntimeError('real background failure')
    future: Future = Future()
    future.set_exception(error)
    with caplog.at_level(logging.DEBUG, logger='utils.executors'):
        executors._log_background_failure('real-task', future)  # noqa: SLF001
    assert any(r.levelno >= logging.ERROR and 'real background failure' in r.message for r in caplog.records)


def test_precache_conversation_audio_during_drain_returns_instead_of_raising():
    """The x9 crash site itself: the audio precache fan-out during a drain.

    ``precache_conversation_audio`` ran inside ``process_conversation``'s audio
    block; its ``postprocess_executor.submit`` refusal is exactly the
    ``Error creating audio files: cannot schedule new futures after shutdown``
    line. Against the real module (GCS client is lazy at import time), the
    drained postprocess pool now yields a silent, bounded skip and the caller's
    playback enrichment is simply deferred, not crashed.
    """
    from utils.other import storage as storage_mod

    pool = _drained_pool()
    with patch.object(storage_mod, 'postprocess_executor', pool), patch.object(
        storage_mod, 'is_audio_merge_dispatch_enabled', return_value=False
    ):
        storage_mod.precache_conversation_audio(
            'drain-uid', 'drain-conv', [{'id': 'af-1', 'chunk_timestamps': [1.0, 2.0]}]
        )


def test_precache_conversation_audio_happy_path_still_fans_out():
    """Unchanged behavior off the drain: the fan-out is submitted to postprocess."""
    from utils.other import storage as storage_mod

    submitted = []

    def fake_submit(fn, *a, **k):
        submitted.append((fn, a, k))
        future: Future = Future()
        future.set_result(None)
        return future

    pool = SimpleNamespace(submit=fake_submit)
    with patch.object(storage_mod, 'postprocess_executor', pool), patch.object(
        storage_mod, 'is_audio_merge_dispatch_enabled', return_value=False
    ):
        storage_mod.precache_conversation_audio('u', 'c', [{'id': 'af-1', 'chunk_timestamps': [1.0]}])
    assert len(submitted) == 1
    _ctx_run, submitted_args, _submitted_kwargs = submitted[0]
    assert submitted_args[0].__name__ == '_precache_all'


def test_wrapped_generation_start_during_drain_still_answers_processing():
    """The wrapped router returns its PROCESSING response instead of a 500."""
    from routers import wrapped as wrapped_router

    pool = _drained_pool()
    created = []
    with patch.object(wrapped_router, 'llm_executor', pool), patch.object(
        wrapped_router.wrapped_db, 'get_wrapped', return_value=None
    ), patch.object(
        wrapped_router.wrapped_db, 'create_wrapped', side_effect=lambda uid, year: created.append((uid, year))
    ):
        response = wrapped_router.generate_wrapped(2025, uid='drain-uid')
    assert response.status == wrapped_router.WrappedStatus.PROCESSING
    assert created == [('drain-uid', 2025)]


def test_wrapped_generation_task_body_still_runs_off_drain():
    pool = MonitoredThreadPoolExecutor(name='wrapped-off-drain', max_workers=1)
    started = threading.Event()
    try:
        from routers import wrapped as wrapped_router

        with patch.object(wrapped_router, 'llm_executor', pool), patch.object(
            wrapped_router.wrapped_db, 'get_wrapped', return_value=None
        ), patch.object(wrapped_router.wrapped_db, 'create_wrapped', lambda uid, year: None), patch.object(
            wrapped_router, '_run_wrapped_generation', lambda uid, year: started.set()
        ):
            response = wrapped_router.generate_wrapped(2025, uid='uid-off-drain')
        assert response.status == wrapped_router.WrappedStatus.PROCESSING
        assert started.wait(timeout=2)
    finally:
        pool.shutdown(wait=True)


_MIGRATED_CALL_SITES = [
    # (module, raw-submit pattern that must NOT reappear fire-and-forget)
    ('utils/chat_turn.py', 'llm_executor.submit(extract_and_update_goal_progress'),
    ('routers/wrapped.py', 'llm_executor.submit(_run_wrapped_generation'),
    ('routers/mcp.py', 'postprocess_executor.submit(update_personas_async'),
    ('routers/developer.py', 'postprocess_executor.submit(update_personas_async'),
    ('routers/imports.py', 'storage_executor.submit(process_limitless_import'),
    ('utils/other/storage.py', 'postprocess_executor.submit(_precache_all)'),
    ('utils/other/storage.py', 'storage_executor.submit(_upload_to_cache)'),
]


@pytest.mark.parametrize('relative_path,raw_pattern', _MIGRATED_CALL_SITES)
def test_fire_and_forget_call_sites_go_through_the_drain_tolerant_boundary(relative_path, raw_pattern):
    """Every migrated fire-and-forget submit must ride submit_with_context.

    A raw ``executor.submit`` in these spots re-introduces the x9/x14 crash the
    boundary exists to prevent: the drain refusal would escape the caller
    (router 500, audio-block degrade) instead of resolving to a no-op future.
    Source-pinned like test_wrapped_error_sanitization.py.
    """
    source = (_BACKEND / relative_path).read_text(encoding='utf-8')
    assert raw_pattern not in source, f'{relative_path} re-introduced raw fire-and-forget submit: {raw_pattern}'


def test_chat_turn_goal_extraction_rides_the_boundary():
    """The chat-turn goal fan-out is drain-tolerant end to end (boundary level)."""
    import utils.chat_turn as chat_turn

    pool = _drained_pool()
    executed = []
    # The migrated callsite is submit_with_context(llm_executor, ...); against a
    # drained pool the boundary must resolve quietly — the exact turn path the
    # production drain window walked.
    with patch.object(chat_turn, 'llm_executor', pool):
        future = chat_turn.submit_with_context(
            chat_turn.llm_executor, chat_turn.extract_and_update_goal_progress, 'drain-uid', 'walked the dog today'
        )
        assert future.done() and future.result() is None
    assert executed == []


def test_chat_turn_goal_extraction_task_runs_off_drain():
    """Off the drain the same fan-out executes the real goal extractor."""
    import utils.chat_turn as chat_turn

    pool = MonitoredThreadPoolExecutor(name='goals-off-drain', max_workers=1)
    executed = []
    try:
        with patch.object(chat_turn, 'llm_executor', pool), patch.object(
            chat_turn, 'extract_and_update_goal_progress', side_effect=lambda *a: executed.append(a)
        ):
            future = chat_turn.submit_with_context(
                chat_turn.llm_executor, chat_turn.extract_and_update_goal_progress, 'uid', 'text about goals'
            )
            assert future.result(timeout=2) is None
        assert executed == [('uid', 'text about goals')]
    finally:
        pool.shutdown(wait=True)


def test_refusal_message_variants_are_all_absorbed():
    """Every CPython wording of the shutdown guard matches the classifier."""
    variants = [
        'cannot schedule new futures after interpreter shutdown',
        'cannot schedule new futures after shutdown',
    ]
    for message in variants:

        class GuardPool:
            name = 'variant'

            def submit(self, *args, **kwargs):
                raise RuntimeError(message)

        future = submit_with_context(GuardPool(), lambda: 'never')  # type: ignore[arg-type]
        assert future.done() and future.result() is None


def test_runtime_error_subclass_from_task_body_is_not_absorbed_at_submit_time():
    """Absorption is submit-time only; a running task's own failure is untouched."""

    class FinePool:
        name = 'fine'

        def submit(self, fn, *args, **kwargs):
            future: Future = Future()
            try:
                future.set_result(fn(*args))
            except Exception as error:
                future.set_exception(error)
            return future

    def raise_drain_from_body():
        raise RuntimeError(_DRAIN_MESSAGE)

    with pytest.raises(RuntimeError, match=_DRAIN_MESSAGE):
        submit_with_context(FinePool(), raise_drain_from_body).result(timeout=1)


def test_drain_refusal_future_is_usable_by_result_waiters():
    """A caller that waits on the returned future gets a prompt resolution."""
    pool = _drained_pool()
    future = submit_with_context(pool, lambda: 'unused')
    assert future.result(timeout=0.1) is None
    assert not future.cancelled()
    assert future.running() is False and future.done()


def test_drain_refusal_attribution_names_task_and_pool(caplog):
    """The one INFO line attributes both the skipped task and its pool."""
    pool = MonitoredThreadPoolExecutor(name='attribution-pool', max_workers=1)
    pool.shutdown(wait=True, cancel_futures=True)

    def distinctive_task_name():
        return None

    with caplog.at_level(logging.DEBUG, logger='utils.executors'):
        submit_with_context(pool, distinctive_task_name)
    record = next(r for r in caplog.records if 'executor_drained' in r.message)
    assert 'distinctive_task_name' in record.getMessage()
    assert 'attribution-pool' in record.getMessage()


def test_context_is_copied_before_the_drain_check_not_after():
    """No contextvars work happens on the drain path (nothing executes at all)."""
    pool = _drained_pool()

    class ExplodingContext:
        def run(self, fn, *args, **kwargs):
            raise AssertionError('ctx.run must never be reached on a drained pool')

    exploded = ExplodingContext()
    with patch.object(executors.contextvars, 'copy_context', return_value=exploded):
        future = submit_with_context(pool, lambda: None)
    assert future.done() and future.result() is None


@pytest.mark.parametrize('executor_attr,task_name', [('llm_executor', 'extract_and_update_goal_progress')])
def test_chat_turn_module_binds_the_boundary_import(executor_attr, task_name):
    """chat_turn's imported boundary is the real utils.executors function."""
    import utils.chat_turn as chat_turn

    assert chat_turn.submit_with_context is executors.submit_with_context


def test_wrapped_router_module_binds_the_boundary_import():
    from routers import wrapped as wrapped_router

    assert wrapped_router.submit_with_context is executors.submit_with_context


def test_mcp_router_module_binds_the_boundary_import():
    from routers import mcp as mcp_router

    assert mcp_router.submit_with_context is executors.submit_with_context


def test_developer_router_module_binds_the_boundary_import():
    from routers import developer as developer_router

    assert developer_router.submit_with_context is executors.submit_with_context


def test_imports_router_module_binds_the_boundary_import():
    from routers import imports as imports_router

    assert imports_router.submit_with_context is executors.submit_with_context


def test_storage_module_binds_the_boundary_import():
    from utils.other import storage as storage_mod

    assert storage_mod.submit_with_context is executors.submit_with_context


def test_result_consuming_submits_are_not_migrated():
    """RAG/KG/speaker-tag callers need the real failure — they must keep raw submit."""
    rag_source = (_BACKEND / 'utils/retrieval/rag.py').read_text(encoding='utf-8')
    kg_source = (_BACKEND / 'utils/llm/knowledge_graph.py').read_text(encoding='utf-8')
    speaker_source = (_BACKEND / 'utils/speaker_tag_prompts/service.py').read_text(encoding='utf-8')
    assert 'db_executor.submit(retrieve_for_topic' in rag_source
    assert 'llm_executor.submit(process_memory' in kg_source
    assert 'speaker_tag_verify_executor.submit(verify_in_context)' in speaker_source
    assert 'speaker_tag_verify_executor.submit(evidence_in_context)' in speaker_source


def test_boundary_helper_is_internal_and_resolved():
    """The refusal future arrives resolved; the helper is a module detail."""
    future = executors._drain_refusal_future('any')  # noqa: SLF001
    assert future.done() and future.result() is None


def test_background_failure_log_ignores_cancelled_futures(caplog):
    """Cancelled futures stay silent through the new branch (no false drain INFO)."""
    future: Future = Future()
    future.cancel()
    with caplog.at_level(logging.DEBUG, logger='utils.executors'):
        executors._log_background_failure('cancelled-task', future)  # noqa: SLF001
    assert caplog.records == []


def test_imports_router_pending_response_contract_unchanged():
    """The limitless kick-off's response shape is untouched by the migration."""
    from routers import imports as imports_router

    field_names = set(imports_router.ImportJobResponse.model_fields.keys())
    assert {'job_id', 'status'} <= field_names


def test_process_conversation_audio_block_wiring_is_the_boundary():
    """The audio block's precache entry point runs inside the drained boundary.

    End-to-end shape of the x9 site: precache during drain resolves quietly
    (no raise) and the merge-dispatch branch is not entered — the exact
    production path, at function level with the real module.
    """
    from utils.other import storage as storage_mod

    pool = _drained_pool()
    enqueued = []
    with patch.object(storage_mod, 'postprocess_executor', pool), patch.object(
        storage_mod, 'is_audio_merge_dispatch_enabled', return_value=False
    ), patch.object(storage_mod, 'enqueue_conversation_audio_merge', side_effect=lambda *a, **k: enqueued.append(a)):
        storage_mod.precache_conversation_audio('uid', 'conv', [{'id': 'af', 'chunk_timestamps': [1.0, 2.0, 3.0]}])
    assert enqueued == []


def test_precedent_boundary_behavior_destructive_operation_still_first(caplog):
    """The DestructiveOperationInProgress arm keeps precedence over the new one."""
    error = type('DestructiveOperationInProgress', (RuntimeError,), {})('fenced')
    future: Future = Future()
    future.set_exception(error)
    with caplog.at_level(logging.DEBUG, logger='utils.executors'):
        executors._log_background_failure('fenced-task', future)  # noqa: SLF001
    infos = [r for r in caplog.records if 'destructive_operation' in r.message]
    assert len(infos) == 1
    assert not any('executor_drained' in r.message for r in caplog.records)


def test_wrapped_stuck_restart_branch_survives_drain():
    """The stuck-generation restart arm answers PROCESSING through a drained pool."""
    from routers import wrapped as wrapped_router

    pool = _drained_pool()
    resets = []
    stuck = {'status': wrapped_router.WrappedStatus.PROCESSING, 'progress': {'pct': 10}}
    with patch.object(wrapped_router, 'llm_executor', pool), patch.object(
        wrapped_router.wrapped_db, 'get_wrapped', return_value=stuck
    ), patch.object(wrapped_router.wrapped_db, 'is_wrapped_stuck', return_value=True), patch.object(
        wrapped_router.wrapped_db, 'reset_wrapped_for_regeneration', side_effect=lambda uid, year: resets.append(year)
    ):
        response = wrapped_router.generate_wrapped(2025, uid='drain-uid')
    assert response.status == wrapped_router.WrappedStatus.PROCESSING
    assert resets == [2025]


def test_precache_alive_postprocess_drained_storage_downgrades_to_info(caplog):
    """The precache fan-out arm hitting a drained storage pool logs INFO, no ERROR.

    Real end-to-end shape: postprocess alive runs ``_precache_all``; its inner
    ``storage_executor.submit`` refusal propagates as the future's exception,
    and ``_log_background_failure`` downgrades it — the production couplet
    would previously have printed a full traceback per refused arm.
    """
    from utils.other import storage as storage_mod

    alive = MonitoredThreadPoolExecutor(name='precache-alive', max_workers=1)
    drained = _drained_pool()
    try:
        with patch.object(storage_mod, 'postprocess_executor', alive), patch.object(
            storage_mod, 'storage_executor', drained
        ), patch.object(storage_mod, 'is_audio_merge_dispatch_enabled', return_value=False), caplog.at_level(
            logging.DEBUG, logger='utils.executors'
        ):
            storage_mod.precache_conversation_audio('u', 'c', [{'id': 'af', 'chunk_timestamps': [1.0, 2.0]}])
            alive.shutdown(wait=True)
        errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
        infos = [r for r in caplog.records if 'executor_drained' in r.message]
        assert errors == []
        assert infos, 'the refused arm must stay observable at INFO'
    finally:
        alive.shutdown(wait=True)


def test_real_pool_task_body_drain_refusal_logs_info_not_error(caplog):
    """A live pool executing a task whose fan-out hits a drained pool: INFO only."""
    alive = MonitoredThreadPoolExecutor(name='body-alive', max_workers=1)
    drained = _drained_pool()

    def task_that_fans_out():
        submit_with_context(drained, lambda: None)

    try:
        with caplog.at_level(logging.DEBUG, logger='utils.executors'):
            future = submit_with_context(alive, task_that_fans_out)
            future.result(timeout=2)
    finally:
        alive.shutdown(wait=True)
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR and 'task_that_fans_out' in r.message]
    assert errors == []


def test_concurrent_drained_submits_all_resolve():
    """A burst of drained submits resolves every future (no race, no leak)."""
    pool = _drained_pool()
    futures = [submit_with_context(pool, lambda: None) for _ in range(32)]
    assert all(f.done() and f.exception() is None for f in futures)


def test_refusal_does_not_wire_the_background_failure_callback():
    """The refusal path returns before add_done_callback (nothing can log it)."""
    pool = _drained_pool()
    with patch.object(
        executors, '_log_background_failure', side_effect=AssertionError('must not be wired')
    ) as spy:  # noqa: SLF001
        future = submit_with_context(pool, lambda: None)
    assert future.done()
    assert not spy.called


def test_boundary_returns_a_future_instance_even_on_refusal():
    pool = _drained_pool()
    assert isinstance(submit_with_context(pool, lambda: None), Future)


def test_refusal_log_is_info_without_traceback(caplog):
    """Exactly INFO level, and no exc_info payload (no traceback in Cloud Logging)."""
    pool = MonitoredThreadPoolExecutor(name='info-level', max_workers=1)
    pool.shutdown(wait=True, cancel_futures=True)
    with caplog.at_level(logging.DEBUG, logger='utils.executors'):
        submit_with_context(pool, lambda: None)
    record = next(r for r in caplog.records if 'executor_drained' in r.message)
    assert record.levelno == logging.INFO
    assert record.exc_info is None


def test_runtime_error_subclass_with_drain_message_is_absorbed():
    class DrainError(RuntimeError):
        pass

    class SubclassPool:
        name = 'subclass'

        def submit(self, *args, **kwargs):
            raise DrainError(_DRAIN_MESSAGE)

    future = submit_with_context(SubclassPool(), lambda: None)  # type: ignore[arg-type]
    assert future.done() and future.result() is None


def test_lambda_task_attribution_falls_back_to_repr(caplog):
    pool = MonitoredThreadPoolExecutor(name='lambda-pool', max_workers=1)
    pool.shutdown(wait=True, cancel_futures=True)
    with caplog.at_level(logging.DEBUG, logger='utils.executors'):
        submit_with_context(pool, lambda: None)
    assert '<lambda>' in next(r for r in caplog.records if 'executor_drained' in r.message).getMessage()


def test_monitored_active_count_unchanged_by_refusal():
    """A refused submit consumes no active slot the pool can no longer release."""
    pool = MonitoredThreadPoolExecutor(name='slots', max_workers=2, max_queue_size=4)
    pool.shutdown(wait=True, cancel_futures=True)
    before = pool.active_count
    for _ in range(6):
        submit_with_context(pool, lambda: None)
    assert pool.active_count == before == 0


def test_drain_refusal_future_supports_caller_done_callbacks():
    """Callers may attach their own done-callback to the resolved refusal."""
    pool = _drained_pool()
    seen = []
    future = submit_with_context(pool, lambda: None)
    future.add_done_callback(lambda f: seen.append(f.done()))
    assert seen == [True]


def test_drain_refusal_future_full_contract():
    future = executors._drain_refusal_future('contract')  # noqa: SLF001
    assert future.done() and not future.cancelled()
    assert future.exception() is None and future.result() is None


def test_boundary_forwards_kwargs_on_the_happy_path():
    pool = MonitoredThreadPoolExecutor(name='kwargs-path', max_workers=1)
    seen = {}
    try:

        def task(*args, **kwargs):
            seen.update(args=args, kwargs=kwargs)

        submit_with_context(pool, task, 'a', key='b').result(timeout=2)
        assert seen == {'args': ('a',), 'kwargs': {'key': 'b'}}
    finally:
        pool.shutdown(wait=True)


def test_boundary_executes_functools_partial_tasks():
    import functools

    pool = MonitoredThreadPoolExecutor(name='partial-path', max_workers=1)
    try:
        future = submit_with_context(pool, functools.partial(int, '7'))
        assert future.result(timeout=2) == 7
    finally:
        pool.shutdown(wait=True)


@pytest.mark.parametrize(
    'relative_path,boundary_call',
    [
        ('utils/chat_turn.py', 'submit_with_context(llm_executor, extract_and_update_goal_progress'),
        ('routers/wrapped.py', 'submit_with_context(llm_executor, _run_wrapped_generation'),
        ('routers/mcp.py', 'submit_with_context(postprocess_executor, update_personas_async'),
        ('routers/developer.py', 'submit_with_context(postprocess_executor, update_personas_async'),
        ('routers/imports.py', 'submit_with_context(storage_executor, process_limitless_import'),
        ('utils/other/storage.py', 'submit_with_context(postprocess_executor, _precache_all)'),
        ('utils/other/storage.py', 'submit_with_context(storage_executor, _upload_to_cache)'),
    ],
)
def test_migrated_sites_call_the_boundary_by_name(relative_path, boundary_call):
    """Positive pin per migrated site: the boundary form is present verbatim."""
    source = (_BACKEND / relative_path).read_text(encoding='utf-8')
    assert boundary_call in source, f'{relative_path} lost its drain-tolerant submit: {boundary_call}'


def test_process_conversation_has_no_raw_fire_and_forget_submit():
    """The composition boundary itself never raw-submits fire-and-forget work."""
    source = (_BACKEND / 'utils/conversations/process_conversation.py').read_text(encoding='utf-8')
    for raw in (
        'postprocess_executor.submit(',
        'llm_executor.submit(',
        'storage_executor.submit(',
        'db_executor.submit(',
    ):
        assert raw not in source, f'process_conversation raw-submits via {raw}'


@pytest.mark.parametrize(
    'source_path',
    ['utils/executors.py', 'testing/live_stt_soak/app.py'],
)
def test_shutdown_executors_wiring_exists(source_path):
    """The drain is real: executors register it at exit; the soak app calls it.

    Production shape: uvicorn force-terminates a straggling deploy, the
    atexit-registered ``shutdown_executors()`` runs, and in-flight request
    threads (conversation processing) submit into the drained pools — the
    exact window the boundary now absorbs.
    """
    source = (_BACKEND / source_path).read_text(encoding='utf-8')
    assert 'shutdown_executors' in source


def test_doc_contract_documents_the_drain_boundary():
    """The pipeline doc owns the contract this change introduces."""
    doc = (_BACKEND / 'docs/listen_pusher_pipeline.mdx').read_text(encoding='utf-8')
    assert 'cannot schedule new futures after shutdown' in doc
    assert 'reason=executor_drained' in doc
    assert 'FC-drain-refusal-crashes-fire-and-forget-caller' in doc


@pytest.mark.parametrize(
    'test_id',
    [
        'tests/unit/test_executor_drain_refusal.py::test_wrapped_generation_start_during_drain_still_answers_processing',
        'tests/unit/test_executor_drain_refusal.py::test_wrapped_generation_task_body_still_runs_off_drain',
        'tests/unit/test_executor_drain_refusal.py::test_chat_turn_goal_extraction_rides_the_boundary',
        'tests/unit/test_executor_drain_refusal.py::test_precache_conversation_audio_during_drain_returns_instead_of_raising',
    ],
)
def test_import_amortization_is_allowlisted(test_id):
    """The file's import-heavy first tests stay grandfathered against the guard."""
    allowlist = (_BACKEND / 'tests/fast_unit_duration_allowlist.txt').read_text(encoding='utf-8')
    assert test_id in allowlist


def test_wrapped_double_kickoff_during_drain_is_idempotent():
    """Two drained kick-offs both resolve; the DB create runs once per call."""
    from routers import wrapped as wrapped_router

    pool = _drained_pool()
    creates = []
    with patch.object(wrapped_router, 'llm_executor', pool), patch.object(
        wrapped_router.wrapped_db, 'get_wrapped', return_value=None
    ), patch.object(wrapped_router.wrapped_db, 'create_wrapped', side_effect=lambda uid, year: creates.append(1)):
        first = wrapped_router.generate_wrapped(2025, uid='drain-uid')
        second = wrapped_router.generate_wrapped(2025, uid='drain-uid')
    assert first.status == second.status == wrapped_router.WrappedStatus.PROCESSING
    assert len(creates) == 2


def test_precache_drain_emits_exactly_one_info_line(caplog):
    """Bounded logging: one submit refusal, one INFO, regardless of fan size."""
    from utils.other import storage as storage_mod

    pool = _drained_pool()
    with patch.object(storage_mod, 'postprocess_executor', pool), patch.object(
        storage_mod, 'is_audio_merge_dispatch_enabled', return_value=False
    ), caplog.at_level(logging.DEBUG, logger='utils.executors'):
        storage_mod.precache_conversation_audio(
            'u', 'c', [{'id': f'af-{i}', 'chunk_timestamps': [float(i)]} for i in range(8)]
        )
    assert len([r for r in caplog.records if 'executor_drained' in r.message]) == 1


def test_shutdown_executors_is_idempotent():
    executors.shutdown_executors()
    executors.shutdown_executors()


# The two tests below shut the REAL shared pools down (the production drain).
# They must stay last: this file runs in its own pytest process under the
# file-isolation runner, so the singletons are not shared with other files.
@pytest.mark.parametrize(
    'pool_attr',
    ['critical_executor', 'db_executor', 'llm_executor', 'postprocess_executor', 'storage_executor', 'sync_executor'],
)
def test_real_shared_pools_refuse_after_shutdown_and_boundary_absorbs(pool_attr):
    """The production drain: shutdown_executors() then every named pool refuses."""
    executors.shutdown_executors()
    pool = getattr(executors, pool_attr)
    with pytest.raises(RuntimeError, match=_DRAIN_MESSAGE):
        pool.submit(lambda: None)
    future = submit_with_context(pool, lambda: None)
    assert future.done() and future.result() is None


def test_real_precache_against_fully_drained_singletons():
    """Final end-to-end: the real audio precache path on the real drained pools."""
    executors.shutdown_executors()
    from utils.other import storage as storage_mod

    storage_mod.precache_conversation_audio('u', 'c', [{'id': 'af', 'chunk_timestamps': [1.0, 2.0]}])


def test_wrapped_year_is_forwarded_to_the_task_off_drain():
    """The kick-off forwards (uid, year) positionally to the generator."""
    from routers import wrapped as wrapped_router

    pool = MonitoredThreadPoolExecutor(name='wrapped-args', max_workers=1)
    received = []
    try:
        with patch.object(wrapped_router, 'llm_executor', pool), patch.object(
            wrapped_router.wrapped_db, 'get_wrapped', return_value=None
        ), patch.object(wrapped_router.wrapped_db, 'create_wrapped', lambda uid, year: None), patch.object(
            wrapped_router, '_run_wrapped_generation', lambda uid, year: received.append((uid, year))
        ):
            wrapped_router.generate_wrapped(2025, uid='args-uid')
            import time

            deadline = time.monotonic() + 2
            while not received and time.monotonic() < deadline:
                time.sleep(0.01)
        assert received == [('args-uid', 2025)]
    finally:
        pool.shutdown(wait=True)


def test_precache_fills_gaps_default_and_sample_rate_forwarded():
    """precache forwards fill_gaps/sample_rate into the leaf cache call (off drain)."""
    from utils.other import storage as storage_mod

    seen = {}

    def fake_get_or_create_merged_audio(**kwargs):
        seen.update(kwargs)

    # Two DISTINCT pools: _precache_all coordinates from postprocess while the
    # leaf cache work lands on storage — sharing one 1-worker pool would
    # deadlock (the coordinator waits on children queued behind it).
    coordinator = MonitoredThreadPoolExecutor(name='precache-args-post', max_workers=1)
    workers = MonitoredThreadPoolExecutor(name='precache-args-storage', max_workers=1)
    try:
        with patch.object(storage_mod, 'postprocess_executor', coordinator), patch.object(
            storage_mod, 'storage_executor', workers
        ), patch.object(storage_mod, 'is_audio_merge_dispatch_enabled', return_value=False), patch.object(
            storage_mod, 'get_or_create_merged_audio', side_effect=fake_get_or_create_merged_audio
        ):
            storage_mod.precache_conversation_audio(
                'u', 'c', [{'id': 'af', 'chunk_timestamps': [1.0]}], fill_gaps=False, sample_rate=8000
            )
            import time

            deadline = time.monotonic() + 2
            while 'fill_gaps' not in seen and time.monotonic() < deadline:
                time.sleep(0.01)
        assert seen['fill_gaps'] is False
        assert seen['sample_rate'] == 8000
        assert seen['caller'] == 'process_conversation'
    finally:
        coordinator.shutdown(wait=True)
        workers.shutdown(wait=True)


def test_precache_leaf_exception_is_contained_per_file():
    """One poisoned audio file must not fail the other files' caching (off drain)."""
    from utils.other import storage as storage_mod

    calls = []

    def flaky_get_or_create_merged_audio(**kwargs):
        calls.append(kwargs['audio_file_id'])
        if kwargs['audio_file_id'] == 'bad':
            raise RuntimeError('decode failed')

    pool = MonitoredThreadPoolExecutor(name='precache-isolation-post', max_workers=2)
    leaves = MonitoredThreadPoolExecutor(name='precache-isolation-storage', max_workers=2)
    try:
        with patch.object(storage_mod, 'postprocess_executor', pool), patch.object(
            storage_mod, 'storage_executor', leaves
        ), patch.object(storage_mod, 'is_audio_merge_dispatch_enabled', return_value=False), patch.object(
            storage_mod, 'get_or_create_merged_audio', side_effect=flaky_get_or_create_merged_audio
        ):
            storage_mod.precache_conversation_audio(
                'u', 'c', [{'id': 'bad', 'chunk_timestamps': [1.0]}, {'id': 'good', 'chunk_timestamps': [2.0]}]
            )
            import time

            deadline = time.monotonic() + 2
            while sorted(calls) != ['bad', 'good'] and time.monotonic() < deadline:
                time.sleep(0.01)
        assert sorted(calls) == ['bad', 'good']
    finally:
        pool.shutdown(wait=True)
        leaves.shutdown(wait=True)


def test_boundary_absorbs_refusals_on_a_busy_context():
    """Contextvars propagation stays lazy: the refusal fires before ctx.run."""
    import contextvars

    marker = contextvars.ContextVar('drain-marker', default=None)
    pool = _drained_pool()

    def probe():
        return marker.get()

    marker.set('sentinel')
    future = submit_with_context(pool, probe)
    assert future.result() is None  # never executed, sentinel never needed


def test_shutdown_then_submit_task_never_runs_even_later():
    """No deferred execution: a refused task cannot run after the check."""
    pool = _drained_pool()
    executed = threading.Event()
    future = submit_with_context(pool, executed.set)
    threading.Event().wait(0.05)
    assert future.done() and not executed.is_set()


def test_all_named_pools_are_monitored_instances():
    """Every pool the boundary protects keeps its saturation instrumentation."""
    for pool in executors._ALL_EXECUTORS:  # noqa: SLF001
        assert isinstance(pool, executors.MonitoredThreadPoolExecutor), pool.name
        assert pool.name


def test_boundary_works_against_plain_thread_pool_executor():
    """The boundary does not require Monitored pools (test-only executors too)."""
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='plain')
    try:
        assert submit_with_context(pool, lambda: 21).result(timeout=2) == 21
    finally:
        pool.shutdown(wait=True)


def test_clean_sweep_migration_suite_still_covers_chat_and_imports():
    """The updated legacy source-pins keep their negative assertions."""
    source = (_BACKEND / 'tests/unit/test_clean_sweep_migrations.py').read_text(encoding='utf-8')
    assert "assert 'storage_executor.submit(process_limitless_import' not in src" in source
    assert 'submit_with_context(llm_executor, extract_and_update_goal_progress' in source


def test_wrapped_status_endpoint_contract_untouched():
    """The wrapped status surface keeps its response model fields."""
    from routers import wrapped as wrapped_router

    assert set(wrapped_router.WrappedStatusResponse.model_fields.keys()) >= {'status', 'year', 'result'}


def test_process_conversation_audio_block_order_is_preserved():
    """The audio block still runs after the action-item fan-out (source order).

    Regression guard for the shape that made the refusal escape as
    ``Error creating audio files``: the precache happens inside the same
    try-block region, after derived effects are submitted.
    """
    source = (_BACKEND / 'utils/conversations/process_conversation.py').read_text(encoding='utf-8')
    audio_block = source.index('create_audio_files_from_chunks(uid, conversation.id)')
    precache = source.index('precache_conversation_audio(uid, conversation.id, files_payload)')
    assert audio_block < precache


def test_gateway_error_contract_line_is_typed_not_bare():
    """The x14 sibling boundary keeps its typed %s attribution (no bare {e})."""
    source = (_BACKEND / 'utils/llm/gateway_error_contract.py').read_text(encoding='utf-8')
    assert "logger.error('Conversation processing failed: %s', type(error).__name__)" in source


def test_doc_owns_result_consuming_exception():
    """The doc contract names the submits that intentionally keep raising."""
    doc = (_BACKEND / 'docs/listen_pusher_pipeline.mdx').read_text(encoding='utf-8')
    assert 'Result-consuming submits' in doc
    assert 'keep raising' in doc


def test_allowlist_has_no_duplicate_entries():
    """The duration allowlist stays duplicate-free after this change."""
    entries = [
        line.strip()
        for line in (_BACKEND / 'tests/fast_unit_duration_allowlist.txt').read_text(encoding='utf-8').splitlines()
        if line.strip() and not line.strip().startswith('#')
    ]
    assert len(entries) == len(set(entries))


def test_new_suite_files_import_isolation_is_clean():
    """The suite never installs stub modules; it imports the real implementations.

    AST-based so the assertion inspects code, not its own docstring text.
    """
    import ast

    tree = ast.parse((_BACKEND / 'tests/unit/test_executor_drain_refusal.py').read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            assert not (node.value.id == 'sys' and node.attr == 'modules'), 'suite must not self-stub sys.modules'


def test_background_failure_logger_name_is_stable():
    """The drain INFO comes from utils.executors (attribution/alerting anchor)."""
    assert executors.logger.name == 'utils.executors'
