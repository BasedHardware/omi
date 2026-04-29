"""
Pricing for the coding agent backend (qwen/qwen3.6-35b-a3b on OpenRouter).

Rates are env-driven so ops can adjust without a redeploy. Defaults match the
rates posted at https://openrouter.ai/qwen/qwen3.6-35b-a3b on 2026-04-28; if
OpenRouter changes them, override AGENT_CODE_INPUT_USD_PER_M /
AGENT_CODE_OUTPUT_USD_PER_M (and optionally AGENT_CODE_MARKUP) without shipping.

`raw cost` = what we pay OpenRouter; `charge` = raw * markup, what the user pays.
All math runs through Decimal and rounds half-up to whole cents.
"""

import logging
import os
from decimal import Decimal, ROUND_HALF_UP

import httpx

logger = logging.getLogger(__name__)

# Resolve in order: AGENT_CODE_MODEL_ID (explicit override) → ANTHROPIC_AGENT_MODEL
# (existing infra convention) → tool-capable default. Qwen3.6 has no
# tool-supporting providers on OpenRouter, so we cannot default to it for an
# agent that needs read/edit/bash tools.
MODEL_ID = (
    os.environ.get("AGENT_CODE_MODEL_ID")
    or os.environ.get("ANTHROPIC_AGENT_MODEL")
    or "anthropic/claude-sonnet-4.5"
)

DEFAULT_INPUT_USD_PER_M = Decimal("0.1612")
DEFAULT_OUTPUT_USD_PER_M = Decimal("0.9653")
DEFAULT_MARKUP = Decimal("1.5")


def _decimal_env(key: str, default: Decimal) -> Decimal:
    raw = os.environ.get(key)
    if not raw:
        return default
    try:
        return Decimal(raw)
    except Exception:
        logger.warning("Invalid %s=%r; falling back to %s", key, raw, default)
        return default


COST_INPUT_PER_M_USD = _decimal_env("AGENT_CODE_INPUT_USD_PER_M", DEFAULT_INPUT_USD_PER_M)
COST_OUTPUT_PER_M_USD = _decimal_env("AGENT_CODE_OUTPUT_USD_PER_M", DEFAULT_OUTPUT_USD_PER_M)
MARKUP = _decimal_env("AGENT_CODE_MARKUP", DEFAULT_MARKUP)

PRICE_INPUT_PER_M_USD = COST_INPUT_PER_M_USD * MARKUP
PRICE_OUTPUT_PER_M_USD = COST_OUTPUT_PER_M_USD * MARKUP

MIN_TURN_CHARGE_CENTS = 1

DRIFT_THRESHOLD = Decimal("0.05")
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


def _cost_cents(input_tokens: int, output_tokens: int, in_rate: Decimal, out_rate: Decimal) -> int:
    if input_tokens <= 0 and output_tokens <= 0:
        return 0
    cost_usd = Decimal(input_tokens) * in_rate / Decimal(1_000_000) + Decimal(output_tokens) * out_rate / Decimal(
        1_000_000
    )
    cents = int((cost_usd * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return cents


def compute_raw_cost_cents(input_tokens: int, output_tokens: int) -> int:
    """What we pay OpenRouter, in cents."""
    return _cost_cents(input_tokens, output_tokens, COST_INPUT_PER_M_USD, COST_OUTPUT_PER_M_USD)


def compute_charge_cents(input_tokens: int, output_tokens: int) -> int:
    """What we charge the user (post-markup), in cents. Floors non-zero turns at MIN_TURN_CHARGE_CENTS."""
    cents = _cost_cents(input_tokens, output_tokens, PRICE_INPUT_PER_M_USD, PRICE_OUTPUT_PER_M_USD)
    if cents == 0 and (input_tokens > 0 or output_tokens > 0):
        return MIN_TURN_CHARGE_CENTS
    return cents


def usd_to_cents_half_up(amount_usd: float) -> int:
    """Convert a USD float to whole cents using ROUND_HALF_UP."""
    if amount_usd <= 0:
        return 0
    return int((Decimal(str(amount_usd)) * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def charge_cents_from_raw_usd(amount_usd: float) -> int:
    """Apply markup to a raw USD cost reported by OpenRouter and return whole cents.

    Preferred over per-token math when OpenRouter's `usage.cost` is present, since
    actual rates depend on which provider OpenRouter routed the request to.
    """
    if amount_usd <= 0:
        return 0
    cents = int(
        (Decimal(str(amount_usd)) * MARKUP * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    return max(cents, MIN_TURN_CHARGE_CENTS)


def check_pricing_drift(timeout_seconds: float = 5.0) -> None:
    """Log a warning if configured rates drift >DRIFT_THRESHOLD from OpenRouter live rates.

    Pricing on OpenRouter is reported as USD-per-token; multiply by 1_000_000 for per-M.
    Best-effort: any error is swallowed (drift check must never break startup).
    """
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            resp = client.get(OPENROUTER_MODELS_URL)
            resp.raise_for_status()
            models = (resp.json() or {}).get("data") or []
        match = next((m for m in models if m.get("id") == MODEL_ID), None)
        if not match:
            logger.warning("agent_code pricing drift check: model %s not found in OpenRouter listing", MODEL_ID)
            return
        pricing = match.get("pricing") or {}
        live_in = Decimal(str(pricing.get("prompt", "0"))) * Decimal(1_000_000)
        live_out = Decimal(str(pricing.get("completion", "0"))) * Decimal(1_000_000)
        for label, configured, live in (
            ("input", COST_INPUT_PER_M_USD, live_in),
            ("output", COST_OUTPUT_PER_M_USD, live_out),
        ):
            if live <= 0:
                continue
            drift = abs(configured - live) / live
            if drift > DRIFT_THRESHOLD:
                logger.warning(
                    "agent_code pricing drift: %s configured=%s live=%s drift=%.1f%%",
                    label,
                    configured,
                    live,
                    float(drift) * 100,
                )
    except Exception as exc:
        logger.info("agent_code pricing drift check skipped: %s", exc)
