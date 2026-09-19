"""Lab-local token pricing. Copied rates, not a production import.

Uses the same Luna short-context list prices as the maintenance planner
(``openai.gpt-5.6-luna.2026-07-30``) so harness cost notes stay comparable
to other backend planning estimates without pulling production modules.
"""

from __future__ import annotations

from dataclasses import dataclass

LUNA_SHORT_INPUT_USD_PER_MILLION = 0.20
LUNA_SHORT_OUTPUT_USD_PER_MILLION = 1.20
DEFAULT_MODEL = 'omi:auto:conversation-notes'


@dataclass(frozen=True)
class CostEstimate:
    model: str
    input_tokens: int
    output_tokens: int
    usd: float

    def as_dict(self) -> dict[str, object]:
        return {
            'model': self.model,
            'input_tokens': self.input_tokens,
            'output_tokens': self.output_tokens,
            'usd': round(self.usd, 6),
        }


def estimate_usd(
    input_tokens: int,
    output_tokens: int,
    *,
    model: str = DEFAULT_MODEL,
    input_usd_per_million: float = LUNA_SHORT_INPUT_USD_PER_MILLION,
    output_usd_per_million: float = LUNA_SHORT_OUTPUT_USD_PER_MILLION,
) -> CostEstimate:
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError('token counts must be non-negative')
    usd = input_tokens * input_usd_per_million / 1_000_000 + output_tokens * output_usd_per_million / 1_000_000
    return CostEstimate(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        usd=usd,
    )
