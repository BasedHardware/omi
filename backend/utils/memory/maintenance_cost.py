"""Luna Flex cost model for canonical short-term maintenance (dreaming).

Rates match ``openai.gpt-5.6-luna.2026-07-30`` short-context prices. Flex is
priced at the gateway's batch/Flex multiplier (50%). Token defaults are
planning estimates for one required-processing call and one consolidation
batch; live spend is the gateway ``llm_gateway_attempts`` ledger after a job run.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

LUNA_SHORT_INPUT_USD_PER_MILLION = 0.20
LUNA_SHORT_OUTPUT_USD_PER_MILLION = 1.20
FLEX_MULTIPLIER = 0.50

DEFAULT_L2_INPUT_TOKENS = 2_500
DEFAULT_L2_OUTPUT_TOKENS = 400
DEFAULT_CONSOLIDATION_INPUT_TOKENS = 8_000
DEFAULT_CONSOLIDATION_OUTPUT_TOKENS = 1_200

CONSOLIDATION_BATCH_SIZE = 20
MAX_CONSOLIDATION_BATCHES_PER_PASS = 25


@dataclass(frozen=True)
class MaintenancePassEstimate:
    l2_calls: int
    consolidation_calls: int
    input_tokens: int
    output_tokens: int
    usd: float


def usd_for_tokens(input_tokens: int, output_tokens: int, *, flex: bool = True) -> float:
    multiplier = FLEX_MULTIPLIER if flex else 1.0
    return multiplier * (
        input_tokens * LUNA_SHORT_INPUT_USD_PER_MILLION / 1_000_000
        + output_tokens * LUNA_SHORT_OUTPUT_USD_PER_MILLION / 1_000_000
    )


def estimate_pass(
    *,
    pending_l2: int,
    pending_consolidation: int,
    flex: bool = True,
    l2_input_tokens: int = DEFAULT_L2_INPUT_TOKENS,
    l2_output_tokens: int = DEFAULT_L2_OUTPUT_TOKENS,
    consolidation_input_tokens: int = DEFAULT_CONSOLIDATION_INPUT_TOKENS,
    consolidation_output_tokens: int = DEFAULT_CONSOLIDATION_OUTPUT_TOKENS,
) -> MaintenancePassEstimate:
    """Estimate one dreamed-user maintenance pass.

    The job no longer issues a standalone L2 call. Pending required
    submissions share the consolidation batch with processed Short-term
    rows, one cached 20-item Luna call at a time, up to 25 calls in a pass.
    """
    queued = max(0, pending_l2) + max(0, pending_consolidation)
    l2_calls = 0
    consolidation_calls = 0
    if queued > 0:
        consolidation_calls = min(
            MAX_CONSOLIDATION_BATCHES_PER_PASS,
            ceil(queued / CONSOLIDATION_BATCH_SIZE),
        )
    input_tokens = l2_calls * l2_input_tokens + consolidation_calls * consolidation_input_tokens
    output_tokens = l2_calls * l2_output_tokens + consolidation_calls * consolidation_output_tokens
    return MaintenancePassEstimate(
        l2_calls=l2_calls,
        consolidation_calls=consolidation_calls,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        usd=usd_for_tokens(input_tokens, output_tokens, flex=flex),
    )
