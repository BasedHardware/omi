"""
Coding agent route — OpenAI-compatible streaming proxy to OpenRouter (qwen3.6-35b-a3b).

Flow per turn:
  1. Auth (Firebase ID token -> uid).
  2. Pre-flight balance check; 402 if below MIN_BALANCE_CENTS_TO_START.
  3. Stream SSE from OpenRouter back to the client verbatim.
  4. Once the stream closes, debit `charge_cents` (raw cost * 1.5 markup) and
     write a turn row to the user's agent_code_usage ledger.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

import database.agent_code as agent_code_db
from utils.agent_code.openrouter import StreamUsage, proxy_chat_completion
from utils.agent_code.pricing import (
    MODEL_ID,
    charge_cents_from_raw_usd,
    compute_charge_cents,
    compute_raw_cost_cents,
    usd_to_cents_half_up,
)
from utils.other.endpoints import get_current_user_uid, verify_admin_key_header

logger = logging.getLogger(__name__)
router = APIRouter()

MIN_BALANCE_CENTS_TO_START = 1
GRANT_MAX_CENTS = 100_000  # $1 000 per single grant

_verify_admin_key = verify_admin_key_header


class WalletGrantRequest(BaseModel):
    uid: str
    amount_cents: int
    reason: str

    @field_validator('uid')
    @classmethod
    def uid_not_empty(cls, v: str) -> str:
        if not v:
            raise ValueError('uid must not be empty')
        return v

    @field_validator('amount_cents')
    @classmethod
    def amount_in_range(cls, v: int) -> int:
        if v <= 0:
            raise ValueError('amount_cents must be positive')
        if v > GRANT_MAX_CENTS:
            raise ValueError(f'amount_cents exceeds per-grant cap of {GRANT_MAX_CENTS}')
        return v

    @field_validator('reason')
    @classmethod
    def reason_valid(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('reason must not be empty')
        if len(v) > 200:
            raise ValueError('reason must be 200 characters or fewer')
        return v.strip()


class AgentCompletionRequest(BaseModel):
    messages: List[Dict[str, Any]]
    session_id: Optional[str] = Field(default=None)
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Any] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None


@router.get("/v1/agent/code/wallet")
def get_wallet(uid: str = Depends(get_current_user_uid)):
    return {"balance_cents": agent_code_db.get_balance_cents(uid)}


@router.get("/v1/agent/code/wallet/{uid}", tags=["admin"])
def get_wallet_admin(uid: str, admin_id: str = Depends(_verify_admin_key)):
    """Admin: read any user's coding-agent wallet balance."""
    return {"balance_cents": agent_code_db.get_balance_cents(uid)}


@router.post("/v1/agent/code/wallet/grant", tags=["admin"])
def grant_wallet_credits(body: WalletGrantRequest, admin_id: str = Depends(_verify_admin_key)):
    """Admin: credit a user's coding-agent wallet and write an audit row.

    Used internally to seed test wallets in dev before Stripe top-up ships.
    """
    new_balance = agent_code_db.credit_balance_cents(body.uid, body.amount_cents)
    grant_id = agent_code_db.record_grant(
        uid=body.uid,
        amount_cents=body.amount_cents,
        reason=body.reason,
        granted_by_hash=admin_id,
    )
    logger.info("Admin grant: uid=%s amount_cents=%d grant_id=%s by=%s", body.uid, body.amount_cents, grant_id, admin_id)
    return {"balance_cents": new_balance, "grant_id": grant_id}


@router.post("/v1/agent/code/completions")
async def agent_code_completions(
    body: AgentCompletionRequest,
    uid: str = Depends(get_current_user_uid),
):
    if agent_code_db.get_balance_cents(uid) < MIN_BALANCE_CENTS_TO_START:
        raise HTTPException(status_code=402, detail="Insufficient agent code credits")

    session_id = body.session_id or str(uuid.uuid4())

    payload: Dict[str, Any] = {"model": MODEL_ID, "messages": body.messages}
    for field in ("tools", "tool_choice", "temperature", "top_p", "max_tokens"):
        value = getattr(body, field)
        if value is not None:
            payload[field] = value

    usage = StreamUsage()

    async def streamer():
        try:
            async for chunk in proxy_chat_completion(payload, usage):
                yield chunk
        finally:
            if usage.input_tokens or usage.output_tokens:
                if usage.cost_usd is not None:
                    # Prefer OpenRouter's reported cost — actual rates depend on
                    # which provider OpenRouter routed to (Parasail/Hyperbolic/etc.).
                    cost_cents = usd_to_cents_half_up(usage.cost_usd)
                    charge_cents = charge_cents_from_raw_usd(usage.cost_usd)
                else:
                    cost_cents = compute_raw_cost_cents(usage.input_tokens, usage.output_tokens)
                    charge_cents = compute_charge_cents(usage.input_tokens, usage.output_tokens)
                try:
                    agent_code_db.debit_balance_cents(uid, charge_cents)
                    agent_code_db.record_turn(
                        uid=uid,
                        session_id=session_id,
                        model=usage.model or MODEL_ID,
                        input_tokens=usage.input_tokens,
                        output_tokens=usage.output_tokens,
                        cost_cents=cost_cents,
                        charge_cents=charge_cents,
                    )
                except Exception as exc:
                    logger.exception("Failed to debit/record agent code usage for uid=%s: %s", uid, exc)

    return StreamingResponse(streamer(), media_type="text/event-stream")
