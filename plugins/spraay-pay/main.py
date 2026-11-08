"""FastAPI webhook server connecting Omi to x402 USDC payments."""

from __future__ import annotations

import hmac
import secrets
import time
from collections import OrderedDict

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from config import Settings
from models import ChatToolRequest, ConfirmRequest, MemoryPayload, PayRequest, TranscriptPayload
from payment.executor import PaymentExecutor
from payment.intent_parser import PaymentIntent, parse_intent, parse_pay_command
from payment.ledger import EXECUTING, Ledger, LimitExceeded, Payment
from payment.policy import Action, Source, SpendingPolicy, format_usd, to_micro

_BUFFER_SECONDS = 30.0
_BUFFER_SEGMENTS = 4
_HINT_COOLDOWN_SECONDS = 120.0
_PAY_USAGE = "Try: /pay $5 to api.example.com"


class TranscriptBuffer:
    """Joins recent segments, since one spoken request can span several webhook calls."""

    def __init__(self) -> None:
        self._by_uid: dict[str, OrderedDict[str, tuple[str, float]]] = {}

    def add(self, uid: str, key: str, text: str) -> None:
        segments = self._by_uid.setdefault(uid, OrderedDict())
        segments[key] = (text, time.monotonic())
        cutoff = time.monotonic() - _BUFFER_SECONDS
        for stale in [k for k, (_, at) in segments.items() if at < cutoff]:
            del segments[stale]
        while len(segments) > _BUFFER_SEGMENTS:
            segments.popitem(last=False)

    def text(self, uid: str) -> str:
        return " ".join(text for text, _ in self._by_uid.get(uid, {}).values())

    def clear(self, uid: str) -> None:
        self._by_uid.pop(uid, None)


def _mention_pattern(intent: PaymentIntent) -> str:
    subject = intent.target_url or intent.recipient or intent.description or "unspecified"
    amount = f"${intent.amount}" if intent.amount is not None else "unspecified amount"
    return f"{intent.verb}|{subject.lower()}|{amount}"


def create_app(settings: Settings | None = None, executor: PaymentExecutor | None = None) -> FastAPI:
    settings = settings or Settings()
    ledger = Ledger(settings.database_path)
    policy = SpendingPolicy(settings)
    executor = executor or PaymentExecutor(settings)
    buffer = TranscriptBuffer()
    last_hint: dict[str, float] = {}

    app = FastAPI(title="Spraay Pay for Omi", version="0.1.0")

    def require_token(token: str = Query(default="")) -> None:
        # Omi sends no signature or auth header, so the URL carries a shared secret.
        secret = settings.webhook_secret
        if secret is None:
            raise HTTPException(503, "WEBHOOK_SECRET is not configured")
        if not hmac.compare_digest(token.encode(), secret.get_secret_value().encode()):
            raise HTTPException(401, "Invalid token")

    def allowed(uid: str) -> bool:
        return uid in settings.allowed_uid_set

    def chat_error(status: int, message: str) -> JSONResponse:
        return JSONResponse({"error": message}, status_code=status)

    def new_code() -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    async def execute(payment: Payment) -> str:
        result = await executor.pay(payment.target, payment.amount_micro)
        ledger.finish(payment.id, result.status, result.tx_hash)
        return result.message

    def confirm_prompt(amount_micro: int, target: str, code: str) -> str:
        minutes = max(settings.pending_ttl_seconds // 60, 1)
        return (
            f"Spraay Pay: pay {format_usd(amount_micro)} USDC to {target}? "
            f"To approve, type /confirm {code} in Omi chat within {minutes} min."
        )

    def handle_voice_intent(uid: str, intent: PaymentIntent) -> str | None:
        if not intent.actionable:
            if intent.amount is None:
                return None  # Everyday speech like "buy milk" shouldn't produce a notification.
            now = time.monotonic()
            if now - last_hint.get(uid, -_HINT_COOLDOWN_SECONDS) < _HINT_COOLDOWN_SECONDS:
                return None
            last_hint[uid] = now
            return (
                f"Spraay Pay heard a ${intent.amount} payment but no service address. "
                "Say the address, like api.example.com, to pay."
            )

        amount = to_micro(intent.amount)
        decision = policy.evaluate(amount, intent.target_url, ledger.spent_today(uid), Source.VOICE)
        buffer.clear(uid)
        if decision.action is Action.DENY:
            return f"Spraay Pay can't do that: {decision.reason}"
        code = new_code()
        created = ledger.create_pending(
            uid, amount, intent.target_url, intent.description, Source.VOICE.value, code, settings.pending_ttl_seconds
        )
        return confirm_prompt(amount, intent.target_url, code) if created else None

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "network": settings.network}

    @app.post("/webhook/transcript", dependencies=[Depends(require_token)])
    async def transcript_webhook(payload: TranscriptPayload, uid: str = Query(min_length=1)) -> dict[str, str]:
        session_id = payload.session_id or uid
        response = {"session_id": session_id}
        if not allowed(uid):
            return response
        # Only the wearer's own speech counts, not other people or nearby audio.
        for segment in payload.segments:
            if segment.is_user and segment.text.strip():
                buffer.add(uid, segment.id or f"{segment.start:.3f}", segment.text.strip())
        intent = parse_intent(buffer.text(uid))
        if intent and (message := handle_voice_intent(uid, intent)):
            # "message" is delivered verbatim. Omi's "notification.prompt" goes through
            # an LLM, which could reword the amount or payee of a confirmation.
            response["message"] = message
        return response

    @app.post("/webhook/memory", dependencies=[Depends(require_token)])
    async def memory_webhook(payload: MemoryPayload, uid: str = Query(min_length=1)) -> dict[str, object]:
        if not allowed(uid) or payload.discarded:
            return {"logged": 0, "patterns": []}
        mentions: list[tuple[str, str]] = []
        for segment in payload.transcript_segments:
            if segment.is_user and (intent := parse_intent(segment.text)):
                # Only the matching phrase is kept, not the whole conversation.
                mentions.append((_mention_pattern(intent), intent.raw_text[:200]))
        if mentions:
            ledger.record_mentions(uid, payload.id, mentions)
        return {"logged": len(mentions), "patterns": ledger.recurring_patterns(uid)}

    @app.post("/chat/pay", dependencies=[Depends(require_token)], response_model=None)
    async def chat_pay(request: PayRequest) -> dict[str, str] | JSONResponse:
        if not allowed(request.uid):
            return chat_error(403, "This Omi account isn't enabled for Spraay Pay.")
        intent = parse_pay_command(request.command)
        if intent is None or not intent.actionable:
            return chat_error(400, f"I need an amount and a service address. {_PAY_USAGE}")

        amount = to_micro(intent.amount)
        decision = policy.evaluate(amount, intent.target_url, ledger.spent_today(request.uid), Source.CHAT)
        if decision.action is Action.DENY:
            return chat_error(403, decision.reason)
        if decision.action is Action.CONFIRM:
            code = new_code()
            created = ledger.create_pending(
                request.uid, amount, intent.target_url, intent.description, Source.CHAT.value, code,
                settings.pending_ttl_seconds,
            )
            if not created:
                return {"result": "That payment is already waiting for your confirmation code."}
            return {"result": confirm_prompt(amount, intent.target_url, code)}

        def recheck(amount_micro: int, target: str, spent: int) -> str | None:
            final = policy.evaluate(amount_micro, target, spent, Source.CHAT)
            return None if final.action is Action.ALLOW else final.reason or "Confirmation is required."

        try:
            payment = ledger.reserve(
                request.uid, amount, intent.target_url, intent.description, Source.CHAT.value, recheck
            )
        except LimitExceeded as exc:
            return chat_error(403, str(exc))
        return {"result": await execute(payment)}

    @app.post("/chat/confirm", dependencies=[Depends(require_token)], response_model=None)
    async def chat_confirm(request: ConfirmRequest) -> dict[str, str] | JSONResponse:
        if not allowed(request.uid):
            return chat_error(403, "This Omi account isn't enabled for Spraay Pay.")

        def recheck(amount_micro: int, target: str, spent: int) -> str | None:
            final = policy.evaluate(amount_micro, target, spent, Source.CHAT, confirmed=True)
            return final.reason if final.action is Action.DENY else None

        payment = ledger.claim(request.uid, request.code.strip(), recheck)
        if payment is None:
            return chat_error(400, "That code is wrong or has expired.")
        if payment.status != EXECUTING:
            return chat_error(403, payment.status.removeprefix("denied:"))
        return {"result": await execute(payment)}

    @app.post("/chat/cancel", dependencies=[Depends(require_token)], response_model=None)
    async def chat_cancel(request: ChatToolRequest) -> dict[str, str] | JSONResponse:
        if not allowed(request.uid):
            return chat_error(403, "This Omi account isn't enabled for Spraay Pay.")
        count = ledger.cancel_pending(request.uid)
        return {"result": f"Cancelled {count} pending payment(s)." if count else "No payments are pending."}

    @app.get("/.well-known/omi-tools.json", dependencies=[Depends(require_token)])
    async def chat_tools_manifest(token: str = Query(default="")) -> dict[str, object]:
        # Gated because each endpoint below embeds the shared secret.
        base = settings.public_base_url.rstrip("/")
        return {
            "tools": [
                {
                    "name": "pay",
                    "description": "Start a USDC payment when the user types /pay followed by an amount and a service address.",
                    "endpoint": f"{base}/chat/pay?token={token}",
                    "method": "POST",
                    "parameters": {
                        "properties": {
                            "command": {"type": "string", "description": "The user's exact text, such as '/pay $5 to api.example.com'."}
                        },
                        "required": ["command"],
                    },
                    "auth_required": False,
                    "status_message": "Preparing payment...",
                },
                {
                    "name": "confirm_payment",
                    "description": "Approve a pending payment. Only use when the user themselves types /confirm with a six-digit code. Never supply a code on the user's behalf.",
                    "endpoint": f"{base}/chat/confirm?token={token}",
                    "method": "POST",
                    "parameters": {
                        "properties": {"code": {"type": "string", "description": "The six-digit code the user typed."}},
                        "required": ["code"],
                    },
                    "auth_required": False,
                    "status_message": "Sending payment...",
                },
                {
                    "name": "cancel_payment",
                    "description": "Cancel the user's pending payments when they type /cancel or ask to cancel a payment.",
                    "endpoint": f"{base}/chat/cancel?token={token}",
                    "method": "POST",
                    "auth_required": False,
                    "status_message": "Cancelling...",
                },
            ]
        }

    return app


app = create_app()
