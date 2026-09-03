import asyncio
import logging
import os
from typing import cast
from urllib.parse import quote
from uuid import uuid4

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, WebSocketException

from utils.byok import (
    BYOK_HEADERS,
    extract_byok_from_websocket,
    get_byok_key,
    set_validated_byok_keys,
    validate_byok_websocket_keys,
)
from utils.async_tasks import drain_tasks
from utils.executors import critical_executor, db_executor, run_blocking
from utils.llm.gateway_client import raise_if_gateway_feature_mode_blocks_direct_model_surface
from utils.llm.managed_spend_ledger import (
    DESKTOP_REALTIME_FEATURE,
    OMNI_RELAY_CALLER,
    ManagedAttempt,
    schedule_managed_attempt,
)
from utils.llm.realtime_usage import (
    DEFAULT_REALTIME_MODELS,
    MAX_RESPONSES_PER_SESSION,
    RealtimeRelayObserver,
    RealtimeTurnUsage,
    price_realtime_turn,
    realtime_turn_metadata,
)
from utils.observability.fallback import record_fallback
from utils.other.endpoints import _verify_ws_auth  # type: ignore[reportPrivateUsage]  # shared WS auth helper, intentionally reused cross-module
import database.llm_usage as llm_usage_db
import database.user_usage as user_usage_db
import database.users as users_db
from config.plan_catalog import plan_uses_overage
from database._client import get_customer_firestore_client
from utils.subscription import get_chat_quota_snapshot, is_trial_paywalled

router = APIRouter()
logger = logging.getLogger(__name__)


# Realtime "omni" relay.
#
# The desktop floating bar connects here (authenticated, like /v4/listen) and we
# pipe every frame, verbatim, to the chosen provider's realtime WebSocket. This
# exists because:
#   1) Apple's WebSocket stacks (URLSessionWebSocketTask / Network.framework)
#      cannot hold a direct connection to Gemini's Live endpoint (Google's
#      frontend resets them); a server-side `websockets` client connects fine.
#   2) Provider API keys stay server-side instead of shipping in the client.
#
# Protocol is provider-native and opaque to the relay — the desktop speaks raw
# OpenAI Realtime / Gemini Live JSON; we just forward bytes both ways.

# Leftover AI Studio Live websocket. Vertex Live is not wired here; this is
# not the $1k/day Flash text bill. See backend/docs/vertex-pt-flash.md.
GEMINI_URL = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key={key}"
)
OPENAI_URL = "wss://api.openai.com/v1/realtime?model={model}"
OPENAI_DEFAULT_MODEL = DEFAULT_REALTIME_MODELS["openai"]
# Decision 8 (2026-08-29): a push-to-talk turn is one chat question on every
# plan. The relay is the voice shell only — the desktop client sends the
# transcript through desktop chat, and THAT request debits the question
# (`desktop_chat_completions:{request_id}`). The relay therefore never debits;
# it gates at connect on every plan and re-reads the quota after each provider
# response so an Omi-paid session cannot keep buying transcription past a
# hard cap. Both checks fail closed: a quota read that cannot be answered ends
# a managed session rather than letting it run unmetered.


def _quota_exhausted(snapshot: dict) -> bool:
    """The one exhaustion predicate for the relay: hard-capped plans stop, overage plans keep going."""
    return not snapshot["allowed"] and not plan_uses_overage(snapshot["plan"])


# Bound on Omi-paid provider responses per user per month on a hard-capped
# plan, over the plan's question allowance. The question counter advances
# only when the client sends the turn's chat request; a client that never
# does would otherwise buy transcription for free, and a per-socket budget
# would reset on reconnect. So every response is also counted in a persisted
# monthly telemetry bucket and checked against the allowance with a fresh
# snapshot at each turn boundary. A legitimate turn is one response and one
# question, so honest users reach the chat gate first; the grace absorbs a
# barge-in or a retried response at the very end of the allowance.
RELAY_RESPONSE_BUCKET = "realtime_relay"
RESPONSES_GRACE_PAST_CAP = 2


def _relay_responses_allowed(snapshot: dict) -> int | None:
    """How many relay responses this month the plan allows, or ``None`` for overage plans."""
    if plan_uses_overage(snapshot["plan"]):
        return None
    limit = snapshot.get("limit")
    if snapshot.get("unit") != "questions" or not isinstance(limit, (int, float)):
        # A plan with no question allowance to measure against: the grace only.
        return RESPONSES_GRACE_PAST_CAP
    return int(limit) + RESPONSES_GRACE_PAST_CAP


def _count_relay_response(uid: str) -> tuple[int, dict]:
    """Runs on the DB executor: persist one more relay response, then read the month and the quota fresh.

    Resolving the customer client here keeps first-use credential parsing off
    the event loop.
    """
    client = get_customer_firestore_client()
    # An admission count, not spend: its provider cost is in the managed-spend
    # ledger (S0), so the plan's cost metadata records it as excluded, not missing.
    llm_usage_db.record_llm_usage_bucket(
        uid,
        input_tokens=0,
        output_tokens=0,
        bucket=RELAY_RESPONSE_BUCKET,
        account="omi",
        cost_status="excluded",
        cost_exclusion="relay_response_admission_counter",
        firestore_client=client,
    )
    responses = user_usage_db.get_monthly_bucket_call_count(uid, RELAY_RESPONSE_BUCKET, firestore_client=client)
    snapshot = get_chat_quota_snapshot(uid, "desktop", firestore_client=client)
    return responses, snapshot


# Admission is a read of a persisted count, not a reservation, so sockets
# opened concurrently while the count sits just under the allowance can race
# one another at a response start. A strict per-user cap on open Omi-paid
# hard-capped relay sockets in this process bounds that race: at most this
# many per serving replica, each cut at the first frame of the offending
# response. Two, not one, so a reconnect can overlap the socket it replaces.
# BYOK-served and overage sessions are not subject to it — nothing here caps
# them.
MAX_OPEN_RELAY_SOCKETS_PER_USER = 2
_open_relay_sockets: dict[str, int] = {}


def _admit_relay_socket(uid: str) -> bool:
    open_count = _open_relay_sockets.get(uid, 0)
    if open_count >= MAX_OPEN_RELAY_SOCKETS_PER_USER:
        return False
    _open_relay_sockets[uid] = open_count + 1
    return True


def _release_relay_socket(uid: str) -> None:
    remaining = _open_relay_sockets.get(uid, 0) - 1
    if remaining > 0:
        _open_relay_sockets[uid] = remaining
    else:
        _open_relay_sockets.pop(uid, None)


def _relay_responses_this_month(uid: str) -> int:
    """Runs on the DB executor: the connect-time read of the persisted admission count."""
    return user_usage_db.get_monthly_bucket_call_count(
        uid, RELAY_RESPONSE_BUCKET, firestore_client=get_customer_firestore_client()
    )


def _relay_turn_attempt(
    *,
    session_id: str,
    uid: str,
    provider: str,
    model: str,
    payer: str,
    ordinal: int,
    turn: RealtimeTurnUsage,
) -> ManagedAttempt:
    """The ledger row for one provider response observed on the relay.

    Every turn of a session shares one invocation id and takes the next
    ordinal, so a session's turns group in the ledger the way a gateway
    request's retries do.
    """
    return ManagedAttempt(
        request_id=session_id,
        caller=OMNI_RELAY_CALLER,
        user_uid=uid,
        feature=DESKTOP_REALTIME_FEATURE,
        api_surface=f"{provider}_realtime_websocket",
        payer=payer,
        provider=provider,
        configured_model=model or "unknown",
        outcome=turn.outcome,
        error_class=turn.error_class,
        route_artifact_id=f"{OMNI_RELAY_CALLER}.{provider}",
        metadata=realtime_turn_metadata(turn),
        # None when usage was not reported or the model has no rate table: the
        # row stays `unpriced` rather than a confident zero.
        priced=price_realtime_turn(turn, model),
        invocation_id=session_id,
        ordinal=ordinal,
    )


def _upstream(provider: str, model: str | None) -> tuple[tuple[str, dict[str, str]], None] | tuple[None, str]:
    """Return (url, headers) for the chosen provider, or (None, reason).

    Prefers the caller's BYOK key (so BYOK users pay their own way, same as the
    rest of the API); falls back to the platform key for entitled non-BYOK users.
    """
    if provider == "gemini":
        key = get_byok_key("gemini") or os.getenv("GEMINI_API_KEY")
        if not key:
            return None, "no Gemini key (BYOK or platform)"
        return (GEMINI_URL.format(key=key), {}), None
    if provider == "openai":
        key = get_byok_key("openai") or os.getenv("OPENAI_API_KEY")
        if not key:
            return None, "no OpenAI key (BYOK or platform)"
        # URL-encode the client-supplied model so it can't inject extra query params.
        url = OPENAI_URL.format(model=quote(model or "gpt-realtime-2", safe=""))
        return (url, {"Authorization": f"Bearer {key}"}), None
    return None, f"unsupported provider: {provider}"


@router.websocket("/v1/omni/relay")
async def omni_relay(websocket: WebSocket):
    try:
        raise_if_gateway_feature_mode_blocks_direct_model_surface('omni_realtime.provider_websocket')
    except RuntimeError as exc:
        await websocket.close(code=1013, reason=str(exc)[:120])
        return

    # Manual auth (read the header directly so we control logging and avoid any
    # WS header-DI surprises). Token first, then BYOK validate, then the gate.
    authz = websocket.headers.get("authorization")
    byok_present = [p for p, h in BYOK_HEADERS.items() if websocket.headers.get(h)]
    logger.info(
        f"omni relay connect: auth_present={bool(authz)} byok={byok_present} "
        f"provider={websocket.query_params.get('provider')}"
    )
    try:
        uid = await run_blocking(critical_executor, _verify_ws_auth, cast(str, authz))
    except WebSocketException as e:
        logger.warning(f"omni relay auth rejected: code={e.code} reason={e.reason}")
        await websocket.close(code=e.code, reason=e.reason or "unauthorized")
        return

    # BYOK: validate forwarded keys (same as /v4/listen). Keys then resolve via get_byok_key.
    byok = extract_byok_from_websocket(websocket)
    validated_byok, byok_err = await run_blocking(critical_executor, validate_byok_websocket_keys, uid, byok)
    if byok_err:
        logger.warning(f"omni relay BYOK invalid uid={uid}: {byok_err}")
        await websocket.close(code=4003, reason=byok_err)
        return
    set_validated_byok_keys(validated_byok, uid)

    provider = websocket.query_params.get("provider", "gemini")
    if provider not in {"gemini", "openai"}:
        await websocket.close(code=1011, reason=f"unsupported provider: {provider}"[:120])
        return

    # Same desktop gate as /v4/listen: Operator/Architect + BYOK pass; un-entitled
    # desktop users past their trial are paywalled.
    if await run_blocking(db_executor, is_trial_paywalled, uid, "desktop", required_byok_provider=provider):
        logger.info(f"omni relay paywalled uid={uid}")
        await websocket.close(code=1008, reason="trial_expired")
        return

    await _relay_entitled(websocket, uid, provider, validated_byok)


async def _relay_entitled(websocket: WebSocket, uid: str, provider: str, validated_byok: dict[str, str]) -> None:
    """The relay past auth and the paywall: quota admission, then the pumps."""

    # Monthly free-tier chat quota: realtime turns count as questions, so they
    # must also be blocked past the cap. Exempt only when THIS session will
    # ride the user's own key for the chosen provider AND the user is genuinely
    # BYOK-enrolled — mirrors enforce_chat_quota's rule; a deepgram-only (or
    # forged) BYOK header must not skip the gate while _upstream falls back to
    # Omi's platform key.
    try:
        byok_enrolled = await run_blocking(db_executor, users_db.is_byok_active, uid)
    except Exception as exc:
        logger.warning("omni relay BYOK classification unavailable uid=%s: %s", uid, type(exc).__name__)
        await websocket.close(code=1008, reason="quota_unavailable")
        return
    byok_serves_session = bool(validated_byok.get(provider)) and byok_enrolled
    if byok_enrolled and not byok_serves_session:
        record_fallback(
            component='realtime_hub',
            from_mode=f'byok_{provider}',
            to_mode='managed',
            reason='capability_mismatch',
            outcome='degraded',
            log=logger,
        )
    if not byok_serves_session:
        try:
            snapshot = await run_blocking(db_executor, get_chat_quota_snapshot, uid, "desktop")
        except Exception as exc:
            logger.warning("omni relay quota snapshot unavailable uid=%s: %s", uid, type(exc).__name__)
            await websocket.close(code=1008, reason="quota_unavailable")
            return
        # Every plan: PTT and text chat share one quota (decision 8). Plans
        # whose catalog policy is overage are served and billed, like text chat.
        if _quota_exhausted(snapshot):
            logger.info(f"omni relay quota exceeded uid={uid} plan={snapshot['plan']}")
            await websocket.close(code=1008, reason="quota_exceeded")
            return
        # The month's relay allowance is admission too: a client that spent it
        # without ever sending a chat request is refused here, not one response
        # later on a fresh socket. A count that cannot be read refuses as well.
        allowed = _relay_responses_allowed(snapshot)
        if allowed is not None:
            try:
                responses = await run_blocking(db_executor, _relay_responses_this_month, uid)
            except Exception as exc:
                logger.warning("omni relay admission count unavailable uid=%s: %s", uid, type(exc).__name__)
                await websocket.close(code=1008, reason="quota_unavailable")
                return
            if responses >= allowed:
                logger.info(f"omni relay monthly response allowance spent at connect uid={uid} responses={responses}")
                await websocket.close(code=1008, reason="quota_exceeded")
                return
            if not _admit_relay_socket(uid):
                logger.info(f"omni relay session limit uid={uid}")
                await websocket.close(code=1008, reason="session_limit")
                return
            await _relay_session(websocket, uid, provider, validated_byok, capped=True)
            return
    await _relay_session(websocket, uid, provider, validated_byok, capped=False)


async def _relay_session(
    websocket: WebSocket, uid: str, provider: str, validated_byok: dict[str, str], *, capped: bool
) -> None:
    """An admitted relay session: provider connection, the two pumps, accounting and quota enforcement.

    ``capped`` says whether this socket already holds one of the user's
    per-process slots (Omi-paid on a hard-capped plan at connect). A session
    that was not capped at connect enrolls the moment a fresh snapshot shows a
    hard cap — a downgrade mid-session — so the per-replica bound holds then too.
    """
    enrolled = capped
    try:

        model = websocket.query_params.get("model")
        upstream_cfg, err = _upstream(provider, model)
        if err:
            await websocket.close(code=1011, reason=err)
            return
        url, headers = cast(tuple[str, dict[str, str]], upstream_cfg)

        # Spend attribution: each billable provider response the relay forwards
        # becomes one `llm_gateway_attempts` row (best-effort, never on the audio
        # path's critical section). BYOK sessions are recorded as not Omi cost.
        session_id = str(uuid4())
        # Who the provider bills is decided by the credential `_upstream` actually
        # selects — a validated key for this provider — not by enrollment. An
        # unenrolled user with a valid key still pays the provider directly, and
        # the quota policy above is a separate question from the payer.
        payer = "byok" if validated_byok.get(provider) else "omi"
        observer = RealtimeRelayObserver(
            provider, model=(model or OPENAI_DEFAULT_MODEL) if provider == "openai" else model
        )

        class QuotaStop(Exception):
            """Raised inside the pump when the session may no longer be served on Omi's key."""

        async def enforce_quota_at_response_start() -> None:
            """When a provider response starts on an Omi-paid session, count it and stop if the plan is out.

            Runs inline on the frame that opens the response (never on a later
            audio frame), so the work the provider begins is counted before a
            client can disconnect to dodge it, and an over-allowance response is
            cut at its first frame rather than served. Two bounds, both read fresh
            and both fail closed: the plan's question quota (advanced by the chat
            request behind each turn) and the persisted monthly count of relay
            responses (advanced here, so it holds across reconnects, a month reset
            or a plan change). A read or write that cannot be completed stops the
            session too.
            """
            nonlocal enrolled
            if payer != "omi":
                return
            try:
                responses, snapshot = await run_blocking(db_executor, _count_relay_response, uid)
            except Exception as exc:
                logger.warning("omni relay quota check failed provider=%s: %s", provider, type(exc).__name__)
                raise QuotaStop("quota_unavailable") from exc
            if _quota_exhausted(snapshot):
                logger.info(f"omni relay quota exhausted mid-session uid={uid} plan={snapshot['plan']}")
                raise QuotaStop("quota_exceeded")
            allowed = _relay_responses_allowed(snapshot)
            if allowed is None:
                return
            if not enrolled:
                # Downgraded to a hard cap since connect: this socket now needs a slot.
                if not _admit_relay_socket(uid):
                    logger.info(f"omni relay session limit after plan change uid={uid}")
                    raise QuotaStop("session_limit")
                enrolled = True
            if responses >= allowed:
                logger.info(f"omni relay monthly response allowance spent uid={uid} responses={responses}")
                raise QuotaStop("quota_exceeded")

        def record_turn(turn: RealtimeTurnUsage) -> None:
            schedule_managed_attempt(
                _relay_turn_attempt(
                    session_id=session_id,
                    uid=uid,
                    provider=provider,
                    model=observer.model,
                    payer=payer,
                    ordinal=turn.ordinal,
                    turn=turn,
                )
            )

        def account_upstream_frame(message: str | bytes | bytearray) -> None:
            # Accounting never gets to end a session: it runs before the frame
            # is forwarded, and anything it throws is our bug, not the user's.
            try:
                for turn in observer.observe_upstream_frame(message):
                    record_turn(turn)
            except Exception:
                logger.warning("omni relay accounting failed provider=%s", provider)

        def account_session_end() -> None:
            try:
                for turn in observer.flush():
                    record_turn(turn)
                if observer.dropped_at_flush:
                    logger.warning(
                        "omni relay accounting dropped %d open responses at session end provider=%s",
                        observer.dropped_at_flush,
                        provider,
                    )
            except Exception:
                logger.warning("omni relay accounting flush failed provider=%s", provider)

        quota_stop_reason: str | None = None
        await websocket.accept()
        try:
            async with websockets.connect(
                url, extra_headers=headers or None, max_size=None, ping_interval=20, ping_timeout=20
            ) as upstream:

                async def client_to_upstream():
                    while True:
                        msg = await websocket.receive()
                        if msg.get("type") == "websocket.disconnect":
                            return
                        if (text := msg.get("text")) is not None:
                            await upstream.send(text)
                            observer.observe_client_frame(text)
                        elif (data := msg.get("bytes")) is not None:
                            await upstream.send(data)
                            observer.observe_client_frame(data)

                async def upstream_to_client():
                    async for message in upstream:
                        # Spend accounting is off the request path (a background
                        # write). Admission is not: when this frame opens a
                        # response, the quota round-trip runs BEFORE the frame is
                        # forwarded, so it is startup latency for that response
                        # rather than a gap in its audio, and an over-allowance
                        # response is never delivered at all.
                        starts_before = observer.starts
                        account_upstream_frame(message)
                        if observer.starts > starts_before:
                            # Admission first: the provider has started this
                            # response whatever happens next, so it is counted.
                            await enforce_quota_at_response_start()
                            if observer.starts > MAX_RESPONSES_PER_SESSION:
                                # Response identity is tracked per socket; past
                                # this many responses it would stop being exact,
                                # so the session ends and a reconnect starts a
                                # fresh observer. Every plan, every payer.
                                logger.info(f"omni relay session response limit uid={uid}")
                                raise QuotaStop("session_limit")
                        if isinstance(message, (bytes, bytearray)):
                            await websocket.send_bytes(message)
                        else:
                            await websocket.send_text(message)

                pumps = {
                    asyncio.create_task(client_to_upstream(), name=f"ws:{uid}:omni_c2u"),
                    asyncio.create_task(upstream_to_client(), name=f"ws:{uid}:omni_u2c"),
                }
                done: set[asyncio.Task[None]] = set()
                try:
                    done, _pending = await asyncio.wait(pumps, return_when=asyncio.FIRST_COMPLETED)
                finally:
                    # This handler owns the pumps: whichever way it leaves —
                    # a pump finished, or the handler itself was cancelled
                    # mid-wait — the other pump is drained, bounded, before
                    # accounting flushes, the slot is released and the socket
                    # closes, so nothing resumes on a dead session.
                    await drain_tasks(pumps, timeout=5.0, label="omni_relay_pump", cancel=True)
                for t in done:
                    exc = t.exception()
                    if isinstance(exc, QuotaStop):
                        quota_stop_reason = str(exc)
                    elif exc:
                        logger.warning(f"omni relay task ended: {exc}")
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.error(f"omni relay error (uid={uid}, provider={provider}): {e}")
        finally:
            # A response still in flight when the socket ends was a provider
            # attempt too; it is recorded as cancelled with whatever usage arrived.
            account_session_end()
            try:
                if quota_stop_reason is not None:
                    await websocket.close(code=1008, reason=quota_stop_reason)
                else:
                    await websocket.close()
            except Exception:
                pass
    finally:
        # The slot is held from admission, so it is released here no matter
        # where the session ended — a missing provider key, a failed
        # accept, a cancelled handshake or the pumps.
        if enrolled:
            _release_relay_socket(uid)
