"""Chat turn service shared by the app route and messaging workers."""

from config.messaging import cohort_enabled
from utils.messaging import app_awareness
from utils.messaging.projection import surface_runtime
from utils.messaging.contracts import ReentryEvent

from dataclasses import dataclass, field, replace
from typing import Any, Mapping, cast
import logging
import asyncio
import json
import uuid
import re
import base64
from datetime import datetime, timezone
from typing import Optional
from utils.executors import db_executor, llm_executor, run_blocking
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from starlette.concurrency import iterate_in_threadpool
import database.chat as chat_db
import database.notifications as notification_db
from utils.chat_session_target import resolve_chat_target
import database.llm_usage as llm_usage_db
from database.apps import record_app_usage
from models.app import App, UsageHistoryType
from models.chat import (
    ChatEvidenceEnvelope,
    ChatSession,
    Message,
    MessageSender,
    MessageType,
    SendMessageRequest,
    ResponseMessage,
    MessageConversation,
)
from utils.apps import get_available_app_by_id
from utils.conversation_helpers import extract_memory_ids
from utils.chat import acquire_chat_session, emit_stream_error_fallback
from utils.llm.goals import extract_and_update_goal_progress
from database.redis_db import try_acquire_goal_extraction_lock
from utils.llm.gateway_client import CHAT_AGENT_ROUTE_DIRECT, get_chat_agent_route
from utils.subscription import enforce_chat_quota
from utils.other.chat_file import safe_file_chats
from utils.retrieval.graph import execute_chat_stream
from utils.llm.usage_tracker import set_usage_context, reset_usage_context, Features
from utils.log_sanitizer import sanitize_pii
from utils.chat_followup import followup_content_blocks
from utils.observability.fallback import record_fallback
from utils.journey_metrics_contract import ClientKind, resolve_client_kind_from_headers
from utils.product_metrics import record_product_event
from utils.observability.journeys import ClientJourneyAttempt, JourneyAttempt

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TurnOptions:
    plugin_id: str | None = None
    app_id: str | None = None
    platform: str | None = None
    headers: Mapping[str, str] = field(default_factory=dict)
    app_store: Any = None
    app_lease: str | None = None
    request: Any = None  # Optional analytics context; never required by background callers.


class MobileReplySink:
    def response(self, stream, *, media_type):
        return StreamingResponse(stream, media_type=media_type)


def _mobile_chat_stream_succeeded(frame: str) -> bool:
    """A mobile answer succeeds only at a terminal frame with renderable text."""

    if not frame.startswith('done: '):
        return False
    try:
        payload = json.loads(base64.b64decode(frame.removeprefix('done: ').strip()).decode('utf-8'))
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    answer = payload.get('text') if isinstance(payload, dict) else None
    return isinstance(answer, str) and bool(answer.strip())


def _mobile_chat_stream_failed(frame: str) -> bool:
    """Typed in-band errors are failures even when a fallback done frame follows."""

    return frame.lstrip().startswith('error: ')


def _build_quota_exceeded_reply(
    uid: str,
    data: SendMessageRequest,
    compat_app_id: Optional[str],
    detail: dict,
    chat_session: Optional[ChatSession] = None,
) -> ResponseMessage:
    """Persist the user's question + a canned AI reply and return it.

    Both messages join `chat_session` when the request named one. Without it the
    turn is stored unthreaded: the client shows it optimistically against the
    session the user is looking at, and then it disappears on the next history
    load, because that read is scoped to the session and these rows belong to no
    session at all.

    Mobile clients render the reply as a normal AI message, so users on
    older builds without structured 402 handling at least see *why* nothing
    happened instead of a silent failure. Desktop never reaches this path —
    its client-side quota pre-check in AgentBridge throws BridgeError.quotaExceeded
    before the request fires.
    """
    now = datetime.now(timezone.utc)
    user_msg = Message(
        id=str(uuid.uuid4()),
        text=data.text,
        created_at=now,
        sender=MessageSender.human,
        type=MessageType.text,
        app_id=compat_app_id,
        chat_session_id=chat_session.id if chat_session else None,
    )
    _persist_message(uid, user_msg.model_dump())
    if chat_session:
        chat_db.add_message_to_chat_session(uid, chat_session.id, user_msg.id)

    plan = detail.get('plan') or 'Free'
    unit = detail.get('unit')
    limit = detail.get('limit')
    reset_at = detail.get('reset_at')
    if unit == 'cost_usd' and isinstance(limit, (int, float)):
        limit_phrase = f"your ${int(limit)} monthly AI compute budget"
    elif isinstance(limit, (int, float)):
        limit_phrase = f"your {int(limit)} monthly chat question limit"
    else:
        limit_phrase = "your monthly chat limit"
    reset_phrase = ''
    if reset_at:
        try:
            reset_dt = datetime.fromtimestamp(int(reset_at), tz=timezone.utc)
            reset_phrase = f' Your limit resets on {reset_dt.strftime("%B %-d")}.'
        except (TypeError, ValueError):
            pass

    canned = (
        f"You've reached {limit_phrase} on the {plan} plan.{reset_phrase}\n\n"
        "Upgrade your plan to keep chatting, or bring your own API keys in Settings "
        "to use Omi free."
    )
    ai_msg = Message(
        id=str(uuid.uuid4()),
        text=canned,
        created_at=datetime.now(timezone.utc),
        sender=MessageSender.ai,
        type=MessageType.text,
        app_id=compat_app_id,
        chat_session_id=chat_session.id if chat_session else None,
    )
    _persist_message(uid, ai_msg.model_dump())
    if chat_session:
        chat_db.add_message_to_chat_session(uid, chat_session.id, ai_msg.id)
    return ResponseMessage(**ai_msg.model_dump(), ask_for_nps=False)


def _build_quota_accounting_unavailable_reply(compat_app_id: Optional[str]) -> ResponseMessage:
    """SSE-visible retry copy when Free-plan counter persistence fails.

    Returned as an in-memory ``done:`` frame only — do not persist a human or AI
    message here. Persisting before accounting succeeds would orphan user text on
    retries (fresh message ids / idempotency keys under the same outage).
    """
    ai_msg = Message(
        id=str(uuid.uuid4()),
        text=("Usage accounting is temporarily unavailable. Please retry in a moment — " "your message was not saved."),
        created_at=datetime.now(timezone.utc),
        sender=MessageSender.ai,
        type=MessageType.text,
        app_id=compat_app_id,
    )
    return ResponseMessage(**ai_msg.model_dump(), ask_for_nps=False)


def _record_chat_quota_question(
    uid: str,
    *,
    idempotency_key: str,
    source: str,
    message_id: Optional[str] = None,
    chat_session_id: Optional[str] = None,
    platform: Optional[str] = None,
) -> None:
    """Persist the free-plan question counter. Callers that are about to invoke a
    billable provider must treat failures as request failures (fail-closed)."""
    llm_usage_db.record_chat_quota_question(
        uid,
        idempotency_key=idempotency_key,
        source=source,
        message_id=message_id,
        chat_session_id=chat_session_id,
        platform=platform,
    )


def record_chat_quota_question_best_effort(
    uid: str,
    *,
    idempotency_key: str,
    source: str,
    message_id: Optional[str] = None,
    chat_session_id: Optional[str] = None,
    platform: Optional[str] = None,
) -> None:
    """Best-effort counter write for paths where the billable work already happened
    (e.g. voice stream after a visible ``message:`` frame)."""
    try:
        _record_chat_quota_question(
            uid,
            idempotency_key=idempotency_key,
            source=source,
            message_id=message_id,
            chat_session_id=chat_session_id,
            platform=platform,
        )
    except Exception:
        logger.exception('Failed to record chat quota question source=%s uid=%s', source, uid)


async def _release_chat_quota_question_best_effort(
    uid: str,
    *,
    idempotency_key: str,
) -> None:
    """Best-effort release for a question charged up front when the turn fails
    terminally (provider error, empty answer) — the user keeps the question.
    A release failure must never mask the original stream failure, and a retry
    is idempotent on the same event doc."""
    try:
        await run_blocking(db_executor, llm_usage_db.release_chat_quota_question, uid, idempotency_key)
    except Exception:
        logger.exception('Failed to release chat quota question uid=%s', uid)


def _required_chat_quota_provider() -> str | None:
    # Direct agent chat consumes managed Anthropic unless an Anthropic BYOK key
    # is on the request. Other BYOK providers must stay metered on this path.
    return 'anthropic' if get_chat_agent_route() == CHAT_AGENT_ROUTE_DIRECT else None


def _run_chat_turn(uid, surface, session, message, reply_sink, *, principal, options=None):
    """Shared turn preparation, quota, persistence and SSE producer; no Request required.

    Synchronous preparation must run on db_executor for background async callers.
    The returned iterator must be consumed inside the caller's surface lease.
    """
    principal.authorize(uid)
    options = options or TurnOptions()
    runtime = surface_runtime.get()
    if surface != 'app' and (runtime is None or runtime.surface != surface):
        raise PermissionError('Channel turns require an admitted surface runtime')
    if isinstance(message, ReentryEvent):
        if runtime is None or principal.task_id != message.task_id:
            raise PermissionError('Re-entry requires the originating task principal')
        data = SendMessageRequest(text=message.text)
    else:
        data = message
    request = options.request
    plugin_id, app_id = options.plugin_id, options.app_id
    chat_session_id = session
    x_app_platform = options.platform
    # Catalog hard-cap exhaustion is returned as a canned AI reply instead of a
    # raw 402 (which older mobile clients render as a generic server error).
    # Catalog overage plans return normally. Desktop pre-checks via
    # /v1/users/me/usage-quota and never reaches this path when over.
    typed_failures = options.headers.get('X-Omi-Chat-Failure-Protocol') == '1'
    try:
        enforce_chat_quota(uid, platform=x_app_platform, required_llm_provider=_required_chat_quota_provider())
    except HTTPException as exc:
        if exc.status_code != 402 or not isinstance(exc.detail, dict):
            raise
        if exc.detail.get('error') != 'quota_exceeded':
            raise
        _compat_id = app_id or plugin_id
        if _compat_id in ['null', '']:
            _compat_id = None
        # Resolved here rather than at the happy path's `_resolve_chat_session`
        # below: quota enforcement returns before that line is ever reached, and
        # the canned reply still belongs in the session the request named.
        _quota_target = resolve_chat_target(uid, _compat_id, chat_session_id)
        _assert_target_surface(surface, _quota_target.session, runtime)
        response_msg = _build_quota_exceeded_reply(
            uid,
            data,
            _quota_target.app_id,
            exc.detail,
            ChatSession(**_quota_target.session) if _quota_target.session else None,
        )

        def _quota_exceeded_stream():
            if typed_failures:
                yield 'error: {"error":"quota_exceeded","message":"quota_exceeded"}\n\n'
            encoded = base64.b64encode(bytes(response_msg.model_dump_json(), 'utf-8')).decode('utf-8')
            yield f"done: {encoded}\n\n"

        record_product_event(
            'chat_message_sent',
            request=request,
            uid=uid,
            outcome='quota_exceeded',
        )
        return reply_sink.response(_quota_exceeded_stream(), media_type="text/event-stream")

    compat_app_id = app_id or plugin_id
    logger.info(f'send_message {sanitize_pii(data.text)} {compat_app_id} {uid}')

    if compat_app_id in ['null', '']:
        compat_app_id = None

    # get chat session — a named session also decides which app this turn runs as
    target = resolve_chat_target(uid, compat_app_id, chat_session_id)
    _assert_target_surface(surface, target.session, runtime)
    compat_app_id = target.app_id
    chat_session = ChatSession(**target.session) if target.session else None

    message = Message(
        id=str(uuid.uuid4()),
        text=data.text,
        created_at=datetime.now(timezone.utc),
        sender=MessageSender.human,
        type=MessageType.text,
        app_id=compat_app_id,
    )
    # Ensure chat session exists when files are attached
    if data.file_ids and not chat_session:
        acquired_session: Any = acquire_chat_session(uid, compat_app_id)
        chat_session = ChatSession(**acquired_session) if isinstance(acquired_session, dict) else acquired_session

    if data.file_ids is not None and chat_session:
        new_file_ids = chat_session.retrieve_new_file(data.file_ids)
        chat_session.add_file_ids(data.file_ids)
        chat_db.add_files_to_chat_session(uid, chat_session.id, data.file_ids)

        if len(new_file_ids) > 0:
            message.files_id = new_file_ids
            files = chat_db.get_chat_files(uid, new_file_ids)
            files = safe_file_chats([f for f in files if f])
            message.files = files

    if chat_session:
        message.chat_session_id = chat_session.id

    # Fail-closed before persisting the human turn or starting billable work:
    # a Firestore outage must not leave Free-plan turns uncounted, orphan
    # messages on retry, or return a bare HTTP 503 that mobile SSE silently drops.
    quota_idempotency_key = f'v2_messages:{message.id}'
    try:
        _record_chat_quota_question(
            uid,
            idempotency_key=quota_idempotency_key,
            source='v2_messages',
            message_id=message.id,
            chat_session_id=message.chat_session_id,
            platform=x_app_platform,
        )
    except Exception:
        logger.exception('Failed to record chat quota question source=v2_messages uid=%s', uid)
        response_msg = _build_quota_accounting_unavailable_reply(compat_app_id)

        def _quota_accounting_unavailable_stream():
            if typed_failures:
                yield 'error: {"error":"server_error","message":"quota_accounting_unavailable"}\n\n'
            encoded = base64.b64encode(bytes(response_msg.model_dump_json(), 'utf-8')).decode('utf-8')
            yield f"done: {encoded}\n\n"

        record_product_event('chat_message_sent', request=request, uid=uid, outcome='error')
        return reply_sink.response(_quota_accounting_unavailable_stream(), media_type="text/event-stream")

    if chat_session:
        chat_db.add_message_to_chat_session(uid, chat_session.id, message.id)

    _persist_message(uid, message.model_dump())

    # Check for goal progress (background) — rate-limited to one call per user per 5 min
    if runtime is None and try_acquire_goal_extraction_lock(uid):
        llm_executor.submit(extract_and_update_goal_progress, uid, data.text)

    # Preserve the legacy optional app lookup, including its None input.
    legacy_app_id: Any = compat_app_id
    app = get_available_app_by_id(legacy_app_id, uid) if runtime is None else None
    app = App.deserialize_safe(app) if app else None

    app_id_from_app = app.id if app else None

    # Skip a malformed/legacy stored message rather than 500 the whole chat send.
    messages = list(
        reversed(
            Message.deserialize_many_safe(
                chat_db.get_cache_aligned_messages(uid, app_id=compat_app_id, chat_session_id=message.chat_session_id),
                on_error=lambda record, exc: logger.warning(
                    'Skipping malformed chat message %s for uid=%s: %s',
                    record.get('id') if isinstance(record, dict) else None,
                    uid,
                    type(exc).__name__,
                ),
            )
        )
    )

    def process_message(response: str, callback_data: dict):
        memories = callback_data.get('memories_found', [])
        ask_for_nps = callback_data.get('ask_for_nps', False)
        langsmith_run_id = callback_data.get('langsmith_run_id')
        prompt_name = callback_data.get('prompt_name')
        prompt_commit = callback_data.get('prompt_commit')
        chart_data = callback_data.get('chart_data')
        evidence_payload = callback_data.get('evidence')
        evidence = None
        if evidence_payload is not None:
            try:
                evidence = ChatEvidenceEnvelope.model_validate(evidence_payload)
            except ValueError as evidence_exc:
                # Evidence is optional UI chrome. A malformed tool reference must
                # never prevent persistence or delivery of the answer text.
                logger.warning(
                    'dropping invalid chat evidence uid=%s error_type=%s',
                    uid,
                    type(evidence_exc).__name__,
                )

        # cited extraction
        cited_conversation_idxs = {int(i) for i in re.findall(r'\[(\d+)\]', response)}
        if len(cited_conversation_idxs) > 0:
            response = re.sub(r'\[\d+\]', '', response)
        memories = [memories[i - 1] for i in cited_conversation_idxs if 0 < i and i <= len(memories)]

        memories_id = extract_memory_ids(memories) if memories else []

        ai_message_id = str(uuid.uuid4())
        ai_message = Message(
            id=ai_message_id,
            text=response,
            created_at=datetime.now(timezone.utc),
            sender=MessageSender.ai,
            app_id=app_id_from_app,
            type=MessageType.text,
            memories_id=memories_id,
            chart_data=chart_data,
            langsmith_run_id=langsmith_run_id,  # Store run_id for feedback tracking
            prompt_name=prompt_name,  # LangSmith prompt name for versioning
            prompt_commit=prompt_commit,  # LangSmith prompt commit for traceability
            evidence=evidence,
            # One grounded next question, as a chip the client can tap. Empty for
            # any turn that failed or has nothing to go one hop further into.
            content_blocks=followup_content_blocks(
                ai_message_id,
                callback_data.get('followup'),
                visible_text=response,
                failed=bool(callback_data.get('error')),
            ),
        )
        if chat_session:
            ai_message.chat_session_id = chat_session.id
            chat_db.add_message_to_chat_session(uid, chat_session.id, ai_message.id)

        _persist_message(uid, ai_message.model_dump())
        ai_message.memories = [MessageConversation(**m) for m in (memories if len(memories) < 5 else memories[:5])]
        usage_app_id = app_id_from_app or compat_app_id
        if usage_app_id and runtime is None:
            try:
                record_app_usage(
                    uid,
                    usage_app_id,
                    UsageHistoryType.chat_message_sent,
                    message_id=ai_message.id,
                )
            except Exception as analytics_exc:
                # Message is already durable; analytics must not change the client-visible id.
                logger.error(
                    'chat stream app usage recording failed for uid=%s message_id=%s: %s',
                    uid,
                    ai_message.id,
                    type(analytics_exc).__name__,
                )

        return ai_message, ask_for_nps

    journey_attempt = JourneyAttempt('chat_response')
    mobile_journey_attempt = ClientJourneyAttempt(
        'mobile_chat',
        resolve_client_kind_from_headers(options.headers),
    )

    async def generate_stream():
        callback_data = {}
        app_context = None
        app_store = None
        if runtime is None and chat_session is not None and cohort_enabled(uid):
            app_runtime, app_store, _ = await app_awareness.prepare(
                uid, chat_session, messages, principal, store=options.app_store, token=options.app_lease
            )
            if app_runtime is not None:
                app_context = surface_runtime.set(app_runtime)
        answered = False
        stream_exhausted = False
        streamed_terminal_error = False
        chat_tz = None
        if data.time_zone:
            chat_tz = await run_blocking(
                db_executor, notification_db.sync_user_time_zone_from_client, uid, data.time_zone
            )
        # Set usage context for streaming (can't use 'with' across yields)
        usage_token = set_usage_context(uid, Features.CHAT)

        async def emit_done_frame(response: str) -> str:
            """Persist a terminal answer. Typed stream errors stay failed for journey/fallback SLIs.

            If Firestore persistence fails, still emit an in-memory ``done:`` frame (same
            fail-open contract as ``emit_stream_error_fallback``) so the text client is
            not left with only an earlier ``error:`` frame.
            """
            persist_outcome = 'degraded'
            try:
                ai_message, ask_for_nps = await run_blocking(db_executor, process_message, response, callback_data)
            except Exception as persist_exc:
                logger.error(
                    'chat stream terminal answer persistence failed for uid=%s: %s',
                    uid,
                    type(persist_exc).__name__,
                )
                persist_outcome = 'exhausted'
                ai_message = Message(
                    id=str(uuid.uuid4()),
                    text=response,
                    created_at=datetime.now(timezone.utc),
                    sender=MessageSender.ai,
                    app_id=app_id_from_app,
                    type=MessageType.text,
                )
                if chat_session:
                    ai_message.chat_session_id = chat_session.id
                ask_for_nps = False
            if app_store is not None:
                assert chat_session is not None
                await app_awareness.record(app_store, uid, chat_session.id, ai_message)
            response_message = ResponseMessage(**ai_message.model_dump())
            response_message.ask_for_nps = ask_for_nps
            encoded_response = base64.b64encode(bytes(response_message.model_dump_json(), 'utf-8')).decode('utf-8')
            if callback_data.get('error'):
                journey_attempt.finish('failure')
                record_fallback(
                    component='other',
                    from_mode='llm_answer',
                    to_mode='canned_reply',
                    reason='other',
                    outcome=persist_outcome,
                )
            else:
                if persist_outcome == 'exhausted':
                    journey_attempt.finish('failure')
                    record_fallback(
                        component='other',
                        from_mode='llm_answer',
                        to_mode='canned_reply',
                        reason='other',
                        outcome='exhausted',
                    )
                else:
                    journey_attempt.finish('success')
            return f"done: {encoded_response}\n\n"

        try:
            async for chunk in execute_chat_stream(
                uid,
                messages,
                app,
                cited=True,
                callback_data=callback_data,
                chat_session=chat_session,
                context=data.context,
                platform=x_app_platform,
                client_kind=cast(ClientKind, mobile_journey_attempt.client_kind),
                client_tz=chat_tz,
                device_tool_names=set(data.device_tools or ()),
                shaped_invocation=True,
            ):
                if chunk:
                    if chunk.startswith('error: '):
                        streamed_terminal_error = True
                    msg = chunk.replace("\n", "__CRLF__")
                    yield f'{msg}\n\n'
                else:
                    response = callback_data.get('answer')
                    if response:
                        # This is the furthest server-observable client boundary:
                        # a yielded terminal frame is not a client-render acknowledgement.
                        yield await emit_done_frame(response)
                        answered = True

            if not answered:
                # Prefer a staged typed answer (timeout / gateway) even if the producer
                # forgot the None sentinel. Only emit the generic canned sorry when no
                # typed answer was staged — including persona paths that yield ``error:``
                # without setting ``callback_data['answer']`` (those still need ``done:``).
                response = callback_data.get('answer')
                if not response and runtime is not None:
                    callback_data['error'] = 'empty_answer'
                    response = 'Sorry, I could not complete this reply. Please try again.'
                if response:
                    yield await emit_done_frame(response)
                else:
                    if streamed_terminal_error:
                        logger.error(
                            'chat stream ended without an answer uid=%s reason=%s route=%s (error=%s)',
                            uid,
                            callback_data.get('error') or 'stream_failure',
                            callback_data.get('route') or 'unknown',
                            True,
                        )
                    # The turn produced no answer: release the question charged
                    # up front so the user is not billed for a failed turn.
                    await _release_chat_quota_question_best_effort(uid, idempotency_key=quota_idempotency_key)
                    yield await emit_stream_error_fallback(
                        uid,
                        app_id_from_app,
                        chat_session,
                        label='chat',
                        error_recorded=bool(callback_data.get('error')),
                        reason=callback_data.get('error'),
                        route=callback_data.get('route'),
                    )
            stream_exhausted = True
        except asyncio.CancelledError:
            journey_attempt.finish('cancelled')
            raise
        except Exception:
            journey_attempt.finish('failure')
            await _release_chat_quota_question_best_effort(uid, idempotency_key=quota_idempotency_key)
            raise
        finally:
            reset_usage_context(usage_token)
            if app_context is not None:
                surface_runtime.reset(app_context)
            if not journey_attempt.finished:
                journey_attempt.finish('failure' if stream_exhausted else 'cancelled')

    observed_stream = mobile_journey_attempt.observe_stream(
        generate_stream(),
        success_when=_mobile_chat_stream_succeeded,
        failure_when=_mobile_chat_stream_failed,
        failure_class='provider_error',
        missing_success_class='empty_answer',
    )
    record_product_event('chat_message_sent', request=request, uid=uid, outcome='ok')
    return reply_sink.response(observed_stream, media_type="text/event-stream")


def _persist_message(uid, document):
    runtime = surface_runtime.get()
    if runtime is not None and runtime.surface != 'app':
        if runtime.guard is not None:
            runtime.guard()
        document = dict(
            document,
            surface=runtime.surface,
            channel_link_id=runtime.link_id,
            plugin_id='__channel__',
            data_usage='user_serving_only',
        )
        return runtime.persist(uid, document, runtime.session_id)
    return chat_db.add_message(uid, document)


def _assert_target_surface(surface, session, runtime):
    if session and session.get('surface', 'app') != surface:
        raise HTTPException(status_code=404, detail='Chat session not found')
    if runtime is not None and runtime.session_id and (not session or session['id'] != runtime.session_id):
        raise PermissionError('Turn targets a different surface session')


class _LeasedReplySink:
    def __init__(self, delegate, store, uid, token):
        self.delegate, self.store, self.uid, self.token = delegate, store, uid, token

    def response(self, stream, *, media_type):
        async def leased():
            source = stream if hasattr(stream, '__aiter__') else iterate_in_threadpool(stream)
            async for frame in source:
                yield frame
            await run_blocking(db_executor, self.store.release, self.uid, 'app', self.token)

        return self.delegate.response(leased(), media_type=media_type)


def run_chat_turn(uid, surface, session, message, reply_sink, *, principal, options=None):
    principal.authorize(uid)
    options = options or TurnOptions()
    if surface == 'app' and cohort_enabled(uid):
        try:
            store, lease = app_awareness.acquire(uid)
        except RuntimeError:
            raise HTTPException(status_code=409, detail='A chat turn is already running') from None
        if store is not None:
            options = replace(options, app_store=store, app_lease=lease)
            reply_sink = _LeasedReplySink(reply_sink, store, uid, lease)
    return _run_chat_turn(uid, surface, session, message, reply_sink, principal=principal, options=options)
