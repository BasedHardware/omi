"""Wire-facing transcription outcome vocabulary frozen by the released app-client contract.

The internal ``config.prerecorded_stt.TranscriptionOutcome`` may grow bounded
values for server-side telemetry (e.g. ``provider_budget_exhausted``). The
released app-client OpenAPI froze ``components.schemas.TranscriptionOutcome``
and its generated decoders reject unknown values, so response models carry
THIS frozen enum (same class name, so the exported ``$ref`` target is
unchanged) and routers map internal-only values onto their public counterpart
at the boundary — the free-form ``error`` string keeps the precision.
"""

from __future__ import annotations

from enum import Enum


class TranscriptionOutcome(str, Enum):
    # The docstring is the exported schema description; keep it identical to
    # the frozen one so regenerated exports stay byte-identical.
    """Closed, low-cardinality vocabulary for every accepted transcription."""

    SUCCESS = 'success'
    EXPECTED_SILENCE = 'expected_silence'
    EMPTY_UNEXPECTED = 'empty_unexpected'
    TIMEOUT = 'timeout'
    UPSTREAM_ERROR = 'upstream_error'
    CONFIG_ERROR = 'config_error'
    INVALID_INPUT = 'invalid_input'

    @classmethod
    def from_internal(cls, outcome) -> 'TranscriptionOutcome':
        """Map an internal outcome onto the frozen wire vocabulary.

        A provider's account budget being exhausted reads to a released client
        exactly like a non-retryable upstream error (the ``error`` code carries
        ``stt_provider_budget_exhausted``). An unmapped future internal value
        raises here instead of silently laundering past the frozen contract.
        """

        from config.prerecorded_stt import TranscriptionOutcome as InternalOutcome

        if outcome == InternalOutcome.PROVIDER_BUDGET_EXHAUSTED:
            return cls.UPSTREAM_ERROR
        return cls(outcome.value)
