"""On-open Standard notes through the existing prompt/pipeline seam.

Section events use the chat line protocol. Only a complete, revision-fenced
result is stored; cancellation releases the same lease as background notes.
"""

from database import conversations_v3_leases as leases

from database import conversations_v3_processing as writers

import asyncio
import base64
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from fastapi import HTTPException

from config.conversations_v3 import live_recap_enabled
from config.llm_spend import background_flex_retry_enabled, v3_summary_first_open_gating_enabled
from database import conversations_v3 as store
from models.conversation import Conversation
from utils.conversations.v3 import models, planner, policy, recap_telemetry, visibility
from utils.conversations.v3.triggers import enqueue
from utils.observability.fallback import record_fallback
from utils.executors import run_blocking, db_executor, llm_executor
from utils.subscription import should_skip_omi_paid_postprocessing


def fresh(row):
    covers, end = row.get('summary_covers_through'), row.get('finished_at')
    return bool(covers and end and end - covers < timedelta(minutes=5))


def needs_open_reconcile(row):
    return row.get('v3_derived') and (
        row.get('status') == 'in_progress'
        or row.get('v3_unlocked')
        or (v3_summary_first_open_gating_enabled() and row.get('v3_process_failure_reason') == 'outline')
    )


def summary_eligible(row):
    if row.get('processing_tier') == 'historical':
        # Historical rows summarize only through POST .../summary/open (its caps and gates).
        return False
    return not row.get('v3_derived') or (
        row.get('kind') not in {'media', 'background'}
        and (
            policy.manual_intent(row)
            or planner.word_count(row.get('transcript_segments') or []) >= visibility.MIN_HOME_WORDS
        )
    )


def done(row):
    content = {'structured': row.get('structured') or {}, 'summary_covers_through': row.get('summary_covers_through')}
    return 'done: ' + base64.b64encode(json.dumps(content, default=str).encode()).decode() + '\n\n'


def write(uid, row, emit):
    # Preserve the Q12-owned notes pipeline rather than duplicating its prompt.
    from utils.conversations.process_conversation import _get_structured  # pyright: ignore[reportPrivateUsage]
    from utils.generated_compute import generated_compute_scope

    with generated_compute_scope(uid), models.notes_mode(
        uid, foreground=True, emit=emit, backfilled=bool(row.get('v3_derived') and row.get('backfilled'))
    ):
        structured, _discarded = _get_structured(
            uid, row.get('language') or 'en', Conversation(**row), live_recap=recap_telemetry.active()
        )
    if row.get('title_locked') or (
        not recap_telemetry.active() and row.get('v3_unlocked') and (row.get('structured') or {}).get('title')
    ):
        structured.title = (row.get('structured') or {}).get('title', '')
        structured.emoji = (row.get('structured') or {}).get('emoji', '💬')
    # Stream final sections too when the existing notes writer returned a cache
    # or deterministic minimum and produced no token callback.
    return structured.model_dump()


def section_frame(markdown: str) -> str:
    """One streamed section in the chat SSE framing: newlines travel as __CRLF__, which the app decodes."""
    return 'data: ' + markdown.replace('\n', '__CRLF__') + '\n\n'


def paid_notes_refused(uid, row):
    """The custom-STT allowance that process_conversation applies before Omi-paid notes."""
    if row.get('uses_custom_stt') is not True:
        return False
    source = row.get('source')
    return should_skip_omi_paid_postprocessing(
        uid, uses_custom_stt=True, source=getattr(source, 'value', source) if source is not None else None
    )


_LIVE_UNAVAILABLE = 'error: {"detail":"live_recap_unavailable"}\n\n'


def _record(observation: recap_telemetry.RecapObservation | None, outcome: str) -> None:
    if observation is not None:
        observation.record(outcome)


async def prepare(
    uid, row, *, live=False, promote_llm=False, observation: recap_telemetry.RecapObservation | None = None
):
    def check_cohort():
        if live and not live_recap_enabled(uid):
            _record(observation, 'cohort_revoked')
            raise HTTPException(404, 'live_recap_unavailable')

    check_cohort()
    is_fresh = (
        bool(await run_blocking(db_executor, writers.read_live_summary, uid, row, exact=True)) if live else fresh(row)
    )
    check_cohort()
    if is_fresh or not summary_eligible(row):
        return None
    if await run_blocking(db_executor, paid_notes_refused, uid, row):
        _record(observation, 'paid_notes_refused')
        # No foreground model work: the stream serves the stored row, as processing would.
        return None
    check_cohort()
    if promote_llm and background_flex_retry_enabled() and not live:
        token = await run_blocking(db_executor, writers.acquire_open_summary, uid, row['id'])
    else:
        token = await run_blocking(db_executor, leases.acquire, uid, 'summary-' + row['id'])
    if token is None:
        _record(observation, 'lease_conflict')
        raise HTTPException(409, 'summary_in_progress')
    if live and not live_recap_enabled(uid):
        await run_blocking(db_executor, leases.release, uid, 'summary-' + row['id'], token)
        _record(observation, 'cohort_revoked')
        raise HTTPException(404, 'live_recap_unavailable')
    return token


async def stream(
    uid: str,
    row: dict[str, Any],
    *,
    token=None,
    live=False,
    allow_generation=True,
    observation: recap_telemetry.RecapObservation | None = None
):
    async def cohort_revoked():
        if not live or live_recap_enabled(uid):
            return False
        if token:
            await run_blocking(db_executor, leases.release, uid, 'summary-' + row['id'], token)
        _record(observation, 'cohort_revoked')
        return True

    if await cohort_revoked():
        yield _LIVE_UNAVAILABLE
        return
    cached = await run_blocking(db_executor, writers.read_live_summary, uid, row, exact=True) if live else None
    if await cohort_revoked():
        yield _LIVE_UNAVAILABLE
        return
    is_fresh = bool(cached) if live else fresh(row)
    if live and token is None and not is_fresh and summary_eligible(row):
        yield _LIVE_UNAVAILABLE
        return
    if is_fresh or not summary_eligible(row):
        if token:
            await run_blocking(db_executor, leases.release, uid, 'summary-' + row['id'], token)
        if live and not live_recap_enabled(uid):
            _record(observation, 'cohort_revoked')
            yield _LIVE_UNAVAILABLE
            return
        _record(observation, 'cache_hit' if cached else 'no_eligible_input')
        yield done((cached or {}) if live else row)
        return
    if not allow_generation:
        # Ordinary reads may stream the stored projection, but cannot acquire
        # a writer or start paid work. An explicit detail open opts in above.
        yield done((cached or {}) if live else row)
        return
    token = token or await prepare(uid, row)
    if token is None:
        # prepare() returns no lease only when the custom-STT allowance refuses Omi-paid notes:
        # serve the stored row and spend no model work.
        yield done(row)
        return
    cid = row['id']
    fallback_open = not live and bool(row.get('v3_unlocked'))
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue(maxsize=128)
    sent = set()

    def deliver(text):
        if text not in sent and not queue.full():
            sent.add(text)
            queue.put_nowait(text)

    def emit(text):
        if not live and row.get(policy.NATIVE_MANUAL_BINDING) is None:
            loop.call_soon_threadsafe(deliver, text)

    def write_live():
        if not live_recap_enabled(uid):
            return None
        with recap_telemetry.scoped(uid, observation):
            return write(uid, row, emit)

    worker = None
    try:
        snapshot = await run_blocking(
            db_executor, lambda: store.user_conversations(store.get_firestore_client(), uid).document(cid).get()
        )
        if not snapshot.exists or (snapshot.to_dict() or {}).get('deleted'):
            yield 'error: {"detail":"Conversation not found"}\n\n'
            return
        decoded = await run_blocking(db_executor, store.decode_row, uid, snapshot)
        if decoded is None:
            yield 'error: {"detail":"Conversation not found"}\n\n'
            return
        if not live and policy.live_summary_target(decoded) and not decoded.get('v3_unlocked'):
            yield 'error: {"detail":"Conversation not available"}\n\n'
            return
        if live:
            if not live_recap_enabled(uid):
                _record(observation, 'cohort_revoked')
                yield _LIVE_UNAVAILABLE
                return
            if not policy.live_summary_target(decoded) or decoded.get('id') != cid:
                _record(observation, 'stale_target')
                yield 'error: {"detail":"Conversation not available"}\n\n'
                return
            cached = await run_blocking(db_executor, writers.read_live_summary, uid, decoded, exact=True)
            if not live_recap_enabled(uid):
                _record(observation, 'cohort_revoked')
                yield _LIVE_UNAVAILABLE
                return
            if cached:
                _record(observation, 'cache_hit')
                yield done(cached)
                return
            if not summary_eligible(decoded):
                _record(observation, 'no_eligible_input')
                yield done({})
                return
            if decoded.get('uses_custom_stt') != row.get('uses_custom_stt') and await run_blocking(
                db_executor, paid_notes_refused, uid, decoded
            ):
                _record(observation, 'paid_notes_refused')
                yield _LIVE_UNAVAILABLE
                return
        row = decoded
        if row.get('recording') or row.get('is_locked'):
            yield 'error: {"detail":"Conversation not available"}\n\n'
            return
        if not live and (fresh(row) or not summary_eligible(row)):
            await run_blocking(db_executor, leases.release, uid, 'summary-' + cid, token)
            token = None
            yield done(row)
            return
        if row.get(policy.NATIVE_MANUAL_BINDING) is not None and not await run_blocking(
            db_executor, writers.admit_native_summary, uid, cid, token, snapshot.update_time
        ):
            yield 'error: {"detail":"Summary unavailable; poll conversation detail"}\n\n'
            return
        # run_blocking is awaited by a tracked task and never holds a DB worker
        # while waiting on a model. Request cancellation cannot authorize a write.
        from utils.executors import start_background_task

        work = run_blocking(llm_executor, write_live) if live else run_blocking(llm_executor, write, uid, row, emit)
        worker = start_background_task(work, name='v3-summary-open')
        from utils.conversations.v3.service import renew_until_done

        keeper = start_background_task(renew_until_done(uid, 'summary-' + cid, token, worker), name='v3-summary-lease')
        while not worker.done() or not queue.empty():
            try:
                section = await asyncio.wait_for(queue.get(), timeout=1)
                yield section_frame(section)
            except asyncio.TimeoutError:
                if not worker.done():
                    yield ': heartbeat\n\n'
        structured = await worker
        await keeper
        if structured is None or (live and not live_recap_enabled(uid)):
            _record(observation, 'cohort_revoked')
            yield _LIVE_UNAVAILABLE
            return
        armed = await run_blocking(
            db_executor,
            writers.store_summary,
            uid,
            row['id'],
            token,
            snapshot.update_time,
            structured,
            row.get('finished_at'),
            **({'live_input': row} if live else {}),
        )
        if live and not live_recap_enabled(uid):
            _record(observation, 'cohort_revoked')
            yield _LIVE_UNAVAILABLE
            return
        _record(observation, 'notes_committed')
        if armed or fallback_open:
            await _wake_created(uid)
        for section in structured.get('sections') or []:
            text = (
                '## '
                + str(section.get('heading') or section.get('title') or '')
                + '\n\n'
                + str(section.get('body_markdown') or '')
            )
            if text not in sent:
                yield section_frame(text)
        yield done({**row, 'structured': structured, 'summary_covers_through': row.get('finished_at')})
    except asyncio.CancelledError:
        _record(observation, 'cancelled')
        if worker and not worker.done():
            # The blocking model thread cannot be cancelled. Retain its lease
            # until it exits, without publishing its result after disconnect.
            await asyncio.shield(worker)
        raise
    except (models.BackfillNotesDeletionBlocked, models.BackfillNotesAdmissionTimeout):
        yield 'error: {"detail":"Summary unavailable; poll conversation detail"}\n\n'
    except Exception:
        _record(observation, 'stream_failed')
        if not live and row.get('v3_derived') and not needs_open_reconcile(row):
            try:
                await run_blocking(
                    db_executor,
                    writers.fail_processing,
                    uid,
                    cid,
                    token,
                    row.get('sync_content_revision'),
                    content_hash=await run_blocking(db_executor, writers.processing_hash, row),
                )
            except store.Conflict:
                pass  # A newer owner/content revision keeps its own presentation.
        yield 'error: {"detail":"Summary unavailable; poll conversation detail"}\n\n'
    finally:
        if token is not None:
            await run_blocking(db_executor, leases.release, uid, 'summary-' + cid, token)


async def _wake_created(uid):
    """The builder drain delivers the created fanout; a lost wake waits for the owner's next reconcile."""
    try:
        await run_blocking(db_executor, enqueue, uid, at=datetime.now(timezone.utc) + timedelta(minutes=1))
    except Exception as error:
        logging.getLogger(__name__).warning(
            'event=v3_created_wake outcome=deferred exception_type=%s', type(error).__name__
        )
        record_fallback(
            component='other', from_mode='dispatch', to_mode='none', reason='enqueue_failed', outcome='degraded'
        )
