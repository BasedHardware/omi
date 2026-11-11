"""Realtime-voice usage: response lifecycle on the provider-native wire, and modality pricing.

Two provider protocols reach Omi's realtime surfaces — OpenAI Realtime and
Gemini Live. Both are opaque to the relay that carries them, so the only way to
attribute a session's spend is to recognise the provider's own lifecycle and
usage events in the frames flowing back to the client.

OpenAI
    ``response.created`` opens a response (several may be open at once —
    out-of-band responses, barge-in); ``response.done`` closes the one it names
    with a final ``usage`` block and a ``status``: completed, cancelled (with
    ``status_details.reason`` — ``turn_detected`` is the server's own barge-in),
    incomplete, or failed. Each response is one ledger row.

Gemini
    ``usageMetadata`` is the tokens the *session* has used so far (Google's Live
    reference; the Windows client documents the same). A turn's usage is the
    field-wise delta from the previous block; a field that goes down is a
    provider-side reset and counts absolute. ``serverContent.turnComplete``
    closes a turn; because ``usageMetadata`` is an independent optional field
    that may trail the boundary, a completed turn is held until the next server
    activity (or the session end) so trailing usage folds into it. Model output
    (``modelTurn``) or ``interrupted`` marks a turn in flight, so a disconnect
    mid-turn still records the attempt.

Pricing is per provider *model* and per modality (text / audio / image), with
cached input priced at the cached rate and subtracted from the modality it was
counted in — cached tokens are a subset of input on both protocols. A row is
priced only when the provider reported the modality split (and the cached
split when there is more than one input modality); an aggregate-only usage
block, an unknown model, or tool-use prompt tokens (priced differently and
undocumented for Live) leave the row ``unpriced`` rather than guessed. Rates
are integers in micro-USD per million tokens and cost rounds half-up, like the
gateway's rate cards; the YAML cards cannot express modality rates.

Pure module: no I/O, no clients, safe to import anywhere. Every public entry
point is total over untrusted frame content: malformed input yields nothing,
never an exception.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from llm_gateway.gateway.accounting import CacheStatus, PricedUsage, ProviderResponseMetadata, ProviderUsage

OPENAI_REALTIME_PROVIDER = 'openai'
GEMINI_LIVE_PROVIDER = 'gemini'
REALTIME_PROVIDERS = frozenset({OPENAI_REALTIME_PROVIDER, GEMINI_LIVE_PROVIDER})

MICRO_USD_PER_USD = 1_000_000
TOKENS_PER_MILLION = 1_000_000

# Bounded outcome vocabulary, matching the gateway ledger's `outcome` values
# (success | error | cancelled) with the detail in `error_class`.
OUTCOME_SUCCESS = 'success'
OUTCOME_ERROR = 'error'
OUTCOME_CANCELLED = 'cancelled'
ERROR_NONE = 'none'
ERROR_CLIENT_CANCELLED = 'client_cancelled'
ERROR_INTERRUPTED = 'interrupted'
ERROR_INCOMPLETE = 'incomplete'
ERROR_PROVIDER = 'provider_error'
ERROR_CLIENT_DISCONNECTED = 'client_disconnected'


@dataclass(frozen=True)
class RealtimeRates:
    """Micro-USD per 1M tokens for one realtime model, by modality.

    ``cached_*`` is the rate for the cached subset of that modality's input.
    Where a provider publishes no cached rate the full rate is repeated, so a
    cached token is never priced below what the provider documents. Reasoning
    (thinking) output bills at the text output rate.
    """

    rate_card_id: str
    input_text: int
    cached_text: int
    input_audio: int
    cached_audio: int
    input_image: int
    cached_image: int
    output_text: int
    output_audio: int


# Sources, read 2026-09-01 (USD per 1M tokens):
#   OpenAI  developers.openai.com/api/docs/models/gpt-realtime-2 — text $4 / $0.4 cached / $24 out;
#           audio $32 / $0.4 cached / $64 out; image $5 / $0.5 cached.
#   Gemini  ai.google.dev/gemini-api/docs/pricing (Live API, paid tier) —
#           gemini-3.1-flash-live-preview: text $0.75, audio $3.00, image/video $1.00, out text $4.50, out audio $12.00;
#           gemini-2.5-flash-native-audio-preview-12-2025: text $0.50, audio/video $3.00, out text $2.00, out audio $12.00.
#           No Live cached-input rate is published; cached tokens keep the full rate.
_OPENAI_GPT_REALTIME_2 = RealtimeRates(
    rate_card_id='openai.gpt-realtime-2.modality.2026-09-01',
    input_text=4_000_000,
    cached_text=400_000,
    input_audio=32_000_000,
    cached_audio=400_000,
    input_image=5_000_000,
    cached_image=500_000,
    output_text=24_000_000,
    output_audio=64_000_000,
)
_GEMINI_31_FLASH_LIVE = RealtimeRates(
    rate_card_id='gemini.gemini-3.1-flash-live-preview.modality.2026-09-01',
    input_text=750_000,
    cached_text=750_000,
    input_audio=3_000_000,
    cached_audio=3_000_000,
    input_image=1_000_000,
    cached_image=1_000_000,
    output_text=4_500_000,
    output_audio=12_000_000,
)
_GEMINI_25_NATIVE_AUDIO = RealtimeRates(
    rate_card_id='gemini.gemini-2.5-flash-native-audio-preview-12-2025.modality.2026-09-01',
    input_text=500_000,
    cached_text=500_000,
    input_audio=3_000_000,
    cached_audio=3_000_000,
    input_image=3_000_000,
    cached_image=3_000_000,
    output_text=2_000_000,
    output_audio=12_000_000,
)
REALTIME_RATE_CARDS: dict[tuple[str, str], RealtimeRates] = {
    (OPENAI_REALTIME_PROVIDER, 'gpt-realtime-2'): _OPENAI_GPT_REALTIME_2,
    (GEMINI_LIVE_PROVIDER, 'gemini-3.1-flash-live-preview'): _GEMINI_31_FLASH_LIVE,
    (GEMINI_LIVE_PROVIDER, 'gemini-2.5-flash-native-audio-preview-12-2025'): _GEMINI_25_NATIVE_AUDIO,
}
# The model each realtime surface serves when the caller names none
# (`routers/desktop_realtime.py` _OPENAI_REALTIME_MODEL / _GEMINI_LIVE_MODEL).
DEFAULT_REALTIME_MODELS: dict[str, str] = {
    OPENAI_REALTIME_PROVIDER: 'gpt-realtime-2',
    GEMINI_LIVE_PROVIDER: 'gemini-3.1-flash-live-preview',
}
REALTIME_COST_BASIS = 'realtime_modality_rates_cached_subset_discounted'

_OPENAI_PARSE_MARKERS = (b'response.done', b'response.created')
_GEMINI_PARSE_MARKERS = (b'turnComplete', b'usageMetadata', b'interrupted')
# Model activity is recognised by substring only: audio frames are the bulk of
# a session and are never JSON-parsed. A tool call is activity too — it opens
# a turn the same way model output does.
_GEMINI_ACTIVITY_MARKERS = (b'"modelTurn"', b'"toolCall"')
# Google sends this when the client interrupts a server turn mid tool call;
# it is the interruption signal for that shape of turn.
_GEMINI_INTERRUPTION_MARKER = b'"toolCallCancellation"'
_SETUP_MARKERS = (b'"setup"', b'"session"')
# Frames are provider-native JSON that can carry base64 audio. A frame is only
# parsed when it carries a lifecycle marker; Gemini may put final audio and
# the turn boundary in one frame, so marker-bearing frames parse up to a hard
# ceiling that exists only to bound a hostile upstream.
_MAX_PARSED_FRAME_BYTES = 8 * 1024 * 1024
_MAX_MODEL_CHARS = 128
# Open response identities are retained through the same bound as completed
# ones. The relay ends any session that has started this many responses
# (MAX_RESPONSES_PER_SESSION below) and makes it reconnect with a fresh
# observer, so no session — whatever its plan or how many month resets it
# spans — ever reaches the identity-less overflow tally. The tally remains
# only as a defensive floor for a caller that does not enforce that limit.
_MAX_OPEN_RESPONSES = 1024
# Exported for the relay: the per-session response limit that keeps identity
# exact. One below the identity capacity, so the response that trips the limit
# — observed, counted for admission, then refused — still has its identity.
MAX_RESPONSES_PER_SESSION = _MAX_OPEN_RESPONSES - 1
# A provider response id is a short token; anything longer is not one and is
# replaced by an anonymous key so hostile frames cannot park bytes in memory
# or in the ledger.
_MAX_RESPONSE_ID_CHARS = 256
# Terminal ids remembered so a replayed `response.done` is not a second row
# or a second start. Sized past the largest hard-capped question allowance
# (1,000) plus grace, so identity stays exact for every response a session
# on a hard-capped plan can be admitted for; beyond `_MAX_OPEN_RESPONSES`
# concurrently open responses the overflow count is a tally, not identities.
_MAX_COMPLETED_IDS = 1024
# A flush at session end emits at most this many cancelled rows; the rest are
# counted, not built, so a flood of open responses cannot turn teardown into
# unbounded work. Sixteen concurrent responses is already far past any client.
_MAX_FLUSH_ROWS = 16


def canonical_realtime_model(model: str | None) -> str:
    """``models/gemini-x`` and ``gemini-x`` are the same model."""
    if not isinstance(model, str):
        return ''
    name = model.strip()
    if name.startswith('models/'):
        name = name[len('models/') :]
    return name[:_MAX_MODEL_CHARS]


def realtime_rates_for(provider: str, model: str | None) -> RealtimeRates | None:
    return REALTIME_RATE_CARDS.get((provider, canonical_realtime_model(model)))


@dataclass(frozen=True)
class RealtimeTurnUsage:
    """One provider response: modality-split counts, what the provider vouched for, and its outcome.

    ``cached_*`` counts are subsets of the matching ``input_*`` counts.
    ``modality_split_reported`` is true only when the provider itself split
    input and output by modality; ``cached_split_reported`` when it split the
    cached subset too, or there was nothing to split (no cached tokens, or a
    single input modality). Pricing requires both.
    """

    provider: str
    outcome: str = OUTCOME_SUCCESS
    error_class: str = ERROR_NONE
    input_text_tokens: int = 0
    input_audio_tokens: int = 0
    input_image_tokens: int = 0
    cached_text_tokens: int = 0
    cached_audio_tokens: int = 0
    cached_image_tokens: int = 0
    output_text_tokens: int = 0
    output_audio_tokens: int = 0
    reasoning_tokens: int = 0
    tool_use_prompt_tokens: int = 0
    usage_reported: bool = False
    modality_split_reported: bool = False
    cached_split_reported: bool = False
    provider_response_id: str | None = None
    # Position of this response in the session, assigned by the observer as it
    # is emitted. Rows are keyed on it, so it is carried on the turn rather than
    # read from a counter that a multi-response flush has already advanced.
    ordinal: int = 0

    @property
    def input_tokens(self) -> int:
        return self.input_text_tokens + self.input_audio_tokens + self.input_image_tokens

    @property
    def input_cached_tokens(self) -> int:
        return self.cached_text_tokens + self.cached_audio_tokens + self.cached_image_tokens

    @property
    def output_tokens(self) -> int:
        return self.output_text_tokens + self.output_audio_tokens

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.reasoning_tokens + self.tool_use_prompt_tokens

    @property
    def has_tokens(self) -> bool:
        return self.total_tokens > 0

    @property
    def priceable(self) -> bool:
        """Whether the provider reported enough structure to price this honestly."""
        return (
            self.usage_reported
            and self.modality_split_reported
            and self.cached_split_reported
            and self.tool_use_prompt_tokens == 0
        )


_COUNT_FIELDS = (
    'input_text_tokens',
    'input_audio_tokens',
    'input_image_tokens',
    'cached_text_tokens',
    'cached_audio_tokens',
    'cached_image_tokens',
    'output_text_tokens',
    'output_audio_tokens',
    'reasoning_tokens',
    'tool_use_prompt_tokens',
)


def split_cached_across_modalities(cached_total: int, *, text: int, audio: int, image: int = 0) -> tuple[int, int, int]:
    """Attribute an unsplit cached total to modalities, text first, never past each count.

    Used by the client-reported hub path, which carries only a cached grand
    total. Text first because that is the modality a stable prefix
    (instructions, tools) lives in.
    """
    remaining = max(cached_total, 0)
    cached_text = min(remaining, max(text, 0))
    remaining -= cached_text
    cached_audio = min(remaining, max(audio, 0))
    remaining -= cached_audio
    cached_image = min(remaining, max(image, 0))
    return cached_text, cached_audio, cached_image


def realtime_turn_cost_micro_usd(turn: RealtimeTurnUsage, rates: RealtimeRates) -> int:
    """Price one response on a rate table, half-up in micro-USD.

    Cached subsets bill at the cached rate, the remainder of each modality at
    full; reasoning bills as text output.
    """
    uncached_text = max(turn.input_text_tokens - turn.cached_text_tokens, 0)
    uncached_audio = max(turn.input_audio_tokens - turn.cached_audio_tokens, 0)
    uncached_image = max(turn.input_image_tokens - turn.cached_image_tokens, 0)
    numerator = (
        uncached_text * rates.input_text
        + max(turn.cached_text_tokens, 0) * rates.cached_text
        + uncached_audio * rates.input_audio
        + max(turn.cached_audio_tokens, 0) * rates.cached_audio
        + uncached_image * rates.input_image
        + max(turn.cached_image_tokens, 0) * rates.cached_image
        + max(turn.output_text_tokens, 0) * rates.output_text
        + max(turn.reasoning_tokens, 0) * rates.output_text
        + max(turn.output_audio_tokens, 0) * rates.output_audio
    )
    return (numerator + TOKENS_PER_MILLION // 2) // TOKENS_PER_MILLION


def realtime_turn_cost_usd(turn: RealtimeTurnUsage, rates: RealtimeRates) -> float:
    """USD form of :func:`realtime_turn_cost_micro_usd` for the ``llm_usage`` telemetry path."""
    return realtime_turn_cost_micro_usd(turn, rates) / MICRO_USD_PER_USD


def client_reported_turn(
    provider: str,
    *,
    input_text_tokens: int,
    input_audio_tokens: int,
    input_cached_tokens: int,
    output_text_tokens: int,
    output_audio_tokens: int,
) -> RealtimeTurnUsage:
    """Normalise the shape ``/v2/realtime/usage`` receives from the desktop client.

    The client already split modalities but reports one cached grand total; it
    is attributed text-first. This is telemetry for ``llm_usage`` and keeps its
    historical heuristic; the relay's wire-observed rows do not use it.
    """
    text = max(input_text_tokens, 0)
    audio = max(input_audio_tokens, 0)
    cached_text, cached_audio, _ = split_cached_across_modalities(input_cached_tokens, text=text, audio=audio)
    return RealtimeTurnUsage(
        provider=provider,
        input_text_tokens=text,
        input_audio_tokens=audio,
        cached_text_tokens=cached_text,
        cached_audio_tokens=cached_audio,
        output_text_tokens=max(output_text_tokens, 0),
        output_audio_tokens=max(output_audio_tokens, 0),
        usage_reported=True,
        modality_split_reported=True,
        cached_split_reported=True,
    )


def client_reported_cost_usd(provider: str, model: str | None, turn: RealtimeTurnUsage) -> float:
    """Cost for the client-reported hub path.

    That path predates model-keyed tables and must keep producing a number for
    the ``llm_usage`` telemetry it feeds, so an unrecognised model prices on the
    provider's default realtime model; an unknown provider prices as Gemini,
    exactly as the endpoint always did.
    """
    if provider not in REALTIME_PROVIDERS:
        provider = GEMINI_LIVE_PROVIDER
    rates = realtime_rates_for(provider, model) or realtime_rates_for(provider, DEFAULT_REALTIME_MODELS[provider])
    assert rates is not None  # every provider has a default table
    return realtime_turn_cost_usd(turn, rates)


def price_realtime_turn(turn: RealtimeTurnUsage, model: str | None) -> PricedUsage | None:
    """The ledger cost for an observed turn, or ``None`` when it cannot be priced honestly."""
    if not turn.priceable:
        return None
    rates = realtime_rates_for(turn.provider, model)
    if rates is None:
        return None
    return PricedUsage(
        micro_usd=realtime_turn_cost_micro_usd(turn, rates),
        rate_card_id=rates.rate_card_id,
        cost_basis=REALTIME_COST_BASIS,
    )


def realtime_turn_metadata(turn: RealtimeTurnUsage) -> ProviderResponseMetadata:
    """Normalise a turn into the gateway's provider-neutral usage shape."""
    if not turn.usage_reported:
        return ProviderResponseMetadata(provider_response_id=turn.provider_response_id)
    prompt = turn.input_tokens
    cached = min(prompt, turn.input_cached_tokens)
    if prompt == 0:
        cache_status = CacheStatus.NOT_APPLICABLE
    elif cached == prompt:
        cache_status = CacheStatus.HIT
    elif cached:
        cache_status = CacheStatus.PARTIAL_HIT
    else:
        cache_status = CacheStatus.MISS
    return ProviderResponseMetadata(
        usage=ProviderUsage(
            prompt_tokens=prompt,
            cached_input_tokens=cached,
            uncached_input_tokens=prompt - cached,
            output_tokens=turn.output_tokens,
            reasoning_tokens=turn.reasoning_tokens,
            output_tokens_include_reasoning=False,
            tool_use_prompt_tokens=turn.tool_use_prompt_tokens,
            total_tokens=turn.total_tokens,
            cache_status=cache_status,
        ),
        provider_response_id=turn.provider_response_id,
    )


class RealtimeRelayObserver:
    """Recognise provider responses in the frames a relay forwards, without retaining them.

    Feed every client→upstream frame to :meth:`observe_client_frame` (it learns
    the model from the session setup) and every upstream→client frame to
    :meth:`observe_upstream_frame`, which returns the responses that became
    final on that frame (usually none, sometimes one, occasionally two). Call
    :meth:`flush` once when the relay ends: it returns the held completed turn
    and every response still in flight, the latter as cancelled.

    Audio frames dominate a session; they are matched by substring only and
    never parsed. No frame content is stored beyond token counts and response
    ids. Every method is total: bad input yields nothing.
    """

    def __init__(self, provider: str, *, model: str | None = None) -> None:
        if provider not in REALTIME_PROVIDERS:
            raise ValueError(f'unsupported realtime provider: {provider!r}')
        self.provider = provider
        self.model = canonical_realtime_model(model)
        self.turns = 0
        # Open responses a flush could not afford to emit (see _MAX_FLUSH_ROWS).
        self.dropped_at_flush = 0
        # Provider responses that have STARTED — OpenAI `response.created` (or
        # a `response.done` never announced), Gemini's first activity after a
        # boundary. Quota admission is enforced on this, on the frame that
        # opens the response, so a client that disconnects before the terminal
        # frame has already been counted for the work the provider began.
        self.starts = 0
        # OpenAI: responses opened by `response.created` and not yet closed.
        self._openai_open: dict[str, None] = {}
        self._openai_completed: dict[str, None] = {}
        self._openai_anonymous = 0
        # Responses opened past the tracking cap: still attempts, still
        # flushed as cancelled, just without their ids.
        self._openai_overflow = 0
        # Gemini: session-cumulative baseline, the delta for the turn in
        # progress, whether that turn has shown any activity, whether it was
        # interrupted, and a completed turn held for trailing usage.
        self._gemini_baseline: RealtimeTurnUsage | None = None
        self._gemini_pending: RealtimeTurnUsage | None = None
        self._gemini_in_flight = False
        self._gemini_interrupted = False
        self._gemini_completed: RealtimeTurnUsage | None = None

    # -- client → upstream ---------------------------------------------------------

    def observe_client_frame(self, frame: object) -> None:
        try:
            raw = _as_bytes(frame)
            if raw is None or not any(marker in raw for marker in _SETUP_MARKERS):
                return
            payload = _parse_json_object(raw)
            if payload is None:
                return
            if self.provider == GEMINI_LIVE_PROVIDER:
                setup = payload.get('setup')
                model = setup.get('model') if isinstance(setup, Mapping) else None
            else:
                session = payload.get('session')
                model = session.get('model') if isinstance(session, Mapping) else None
            name = canonical_realtime_model(model)
            if name:
                self.model = name
        except Exception:
            return

    # -- upstream → client ---------------------------------------------------------

    def observe_upstream_frame(self, frame: object) -> tuple[RealtimeTurnUsage, ...]:
        try:
            raw = _as_bytes(frame)
            if raw is None:
                return ()
            if self.provider == OPENAI_REALTIME_PROVIDER:
                return self._observe_openai(raw)
            return self._observe_gemini(raw)
        except Exception:
            return ()

    def flush(self) -> tuple[RealtimeTurnUsage, ...]:
        """Everything outstanding when the relay ends: held completed turns as they are, in-flight ones as cancelled."""
        try:
            if self.provider == OPENAI_REALTIME_PROVIDER:
                open_ids = list(self._openai_open) + [''] * self._openai_overflow
                self._openai_open.clear()
                self._openai_overflow = 0
                if len(open_ids) > _MAX_FLUSH_ROWS:
                    self.dropped_at_flush += len(open_ids) - _MAX_FLUSH_ROWS
                    open_ids = open_ids[:_MAX_FLUSH_ROWS]
                return tuple(
                    self._emit(
                        RealtimeTurnUsage(
                            provider=OPENAI_REALTIME_PROVIDER,
                            outcome=OUTCOME_CANCELLED,
                            error_class=ERROR_CLIENT_DISCONNECTED,
                            provider_response_id=_public_response_id(response_id),
                        )
                    )
                    for response_id in open_ids
                )
            emitted: list[RealtimeTurnUsage] = []
            held = self._take_completed()
            if held is not None:
                emitted.append(held)
            pending = self._gemini_pending
            in_flight = self._gemini_in_flight or (pending is not None and pending.has_tokens)
            interrupted = self._gemini_interrupted
            self._gemini_pending = None
            self._gemini_in_flight = False
            self._gemini_interrupted = False
            if in_flight:
                base = pending or RealtimeTurnUsage(provider=GEMINI_LIVE_PROVIDER)
                emitted.append(
                    self._emit(
                        replace(
                            base,
                            outcome=OUTCOME_CANCELLED,
                            error_class=ERROR_INTERRUPTED if interrupted else ERROR_CLIENT_DISCONNECTED,
                        )
                    )
                )
            return tuple(emitted)
        except Exception:
            return ()

    def _emit(self, turn: RealtimeTurnUsage) -> RealtimeTurnUsage:
        self.turns += 1
        return replace(turn, ordinal=self.turns)

    # -- OpenAI ------------------------------------------------------------------

    def _observe_openai(self, raw: bytes) -> tuple[RealtimeTurnUsage, ...]:
        if not any(marker in raw for marker in _OPENAI_PARSE_MARKERS):
            return ()
        payload = _parse_json_object(raw)
        if payload is None:
            return ()
        event_type = payload.get('type')
        response = _mapping(payload.get('response'))
        response_id = _bounded_response_id(response.get('id'))
        if event_type == 'response.created':
            # A start is one per response identity: a replayed `created` for
            # an id already open (or already finished) is not a new response.
            if response_id is not None and (response_id in self._openai_open or response_id in self._openai_completed):
                return ()
            if len(self._openai_open) < _MAX_OPEN_RESPONSES:
                self._openai_open[response_id or self._anonymous_key()] = None
            else:
                self._openai_overflow += 1
            self.starts += 1
            return ()
        if event_type != 'response.done':
            return ()
        if response_id is not None and response_id in self._openai_completed:
            return ()  # a replayed terminal frame: already a row, already counted
        if response_id is not None and response_id in self._openai_open:
            self._openai_open.pop(response_id)
        elif response_id is None and self._openai_open:
            # An anonymous terminal closes an anonymous open response, if any.
            anonymous = next((key for key in self._openai_open if key.startswith('anonymous:')), None)
            if anonymous is not None:
                self._openai_open.pop(anonymous)
            elif self._openai_overflow:
                self._openai_overflow -= 1
            else:
                self.starts += 1
        elif self._openai_overflow:
            # One of the responses opened past the tracking cap is finishing.
            self._openai_overflow -= 1
        else:
            # A response whose identity was never announced still started —
            # even while other responses are open, which it does not close.
            self.starts += 1
        if response_id is not None:
            self._openai_completed[response_id] = None
            if len(self._openai_completed) > _MAX_COMPLETED_IDS:
                self._openai_completed.pop(next(iter(self._openai_completed)))
        outcome, error_class = _openai_outcome(response)
        turn = RealtimeTurnUsage(
            provider=OPENAI_REALTIME_PROVIDER,
            outcome=outcome,
            error_class=error_class,
            provider_response_id=response_id,
        )
        usage = response.get('usage')
        if isinstance(usage, Mapping):
            turn = replace(turn, **_openai_counts(usage), usage_reported=True)
        return (self._emit(turn),)

    def _anonymous_key(self) -> str:
        self._openai_anonymous += 1
        return f'anonymous:{self._openai_anonymous}'

    # -- Gemini ------------------------------------------------------------------

    def _observe_gemini(self, raw: bytes) -> tuple[RealtimeTurnUsage, ...]:
        emitted: list[RealtimeTurnUsage] = []
        has_output = any(marker in raw for marker in _GEMINI_ACTIVITY_MARKERS)
        has_lifecycle = any(marker in raw for marker in _GEMINI_PARSE_MARKERS)
        tool_call_cancelled = _GEMINI_INTERRUPTION_MARKER in raw
        if not has_output and not has_lifecycle and not tool_call_cancelled:
            return ()
        payload = _parse_json_object(raw) if has_lifecycle else None
        server_content = _mapping(payload.get('serverContent')) if payload is not None else {}
        usage = payload.get('usageMetadata') if payload is not None else None
        interrupted = server_content.get('interrupted') is True or tool_call_cancelled
        turn_complete = server_content.get('turnComplete') is True
        usage_only = isinstance(usage, Mapping) and not (has_output or interrupted or turn_complete)

        # New activity releases a held turn; trailing usage folds into it instead.
        if self._gemini_completed is not None and not usage_only:
            emitted.append(self._take_completed_unchecked())

        if isinstance(usage, Mapping):
            cumulative = _gemini_turn(usage)
            delta = _gemini_delta(cumulative, self._gemini_baseline)
            self._gemini_baseline = cumulative
            if usage_only and self._gemini_completed is not None:
                self._gemini_completed = _gemini_add(self._gemini_completed, delta)
            else:
                self._gemini_pending = _gemini_add(self._gemini_pending, delta)
                # A usage block that adds nothing is not evidence of a response.
                if delta.has_tokens:
                    self._mark_gemini_in_flight()
        if has_output:
            self._mark_gemini_in_flight()
        if interrupted:
            self._mark_gemini_in_flight()
            self._gemini_interrupted = True
        if turn_complete:
            base = self._gemini_pending or RealtimeTurnUsage(provider=GEMINI_LIVE_PROVIDER)
            if not self._gemini_in_flight and base.has_tokens:
                # Usage arrived only with the boundary: the response still happened.
                self.starts += 1
            if self._gemini_interrupted:
                base = replace(base, outcome=OUTCOME_CANCELLED, error_class=ERROR_INTERRUPTED)
            self._gemini_completed = base
            self._gemini_pending = None
            self._gemini_in_flight = False
            self._gemini_interrupted = False
        return tuple(emitted)

    def _mark_gemini_in_flight(self) -> None:
        if not self._gemini_in_flight:
            self._gemini_in_flight = True
            self.starts += 1

    def _take_completed(self) -> RealtimeTurnUsage | None:
        if self._gemini_completed is None:
            return None
        return self._take_completed_unchecked()

    def _take_completed_unchecked(self) -> RealtimeTurnUsage:
        held = self._gemini_completed
        assert held is not None
        self._gemini_completed = None
        return self._emit(held)


def _bounded_response_id(value: object) -> str | None:
    if not isinstance(value, str) or not value or len(value) > _MAX_RESPONSE_ID_CHARS:
        return None
    return value


def _public_response_id(key: str) -> str | None:
    """Only real provider ids reach the ledger; anonymous tracking keys do not."""
    return key if key and not key.startswith('anonymous:') else None


def _openai_outcome(response: Mapping[str, Any]) -> tuple[str, str]:
    status = response.get('status')
    if status in (None, 'completed'):
        return OUTCOME_SUCCESS, ERROR_NONE
    if status == 'cancelled':
        details = _mapping(response.get('status_details'))
        if details.get('reason') == 'turn_detected':
            return OUTCOME_CANCELLED, ERROR_INTERRUPTED
        return OUTCOME_CANCELLED, ERROR_CLIENT_CANCELLED
    if status == 'incomplete':
        return OUTCOME_ERROR, ERROR_INCOMPLETE
    return OUTCOME_ERROR, ERROR_PROVIDER


def _openai_counts(usage: Mapping[str, Any]) -> dict[str, Any]:
    input_details = usage.get('input_token_details')
    output_details = usage.get('output_token_details')
    input_details_present = isinstance(input_details, Mapping)
    output_details_present = isinstance(output_details, Mapping)
    input_details = _mapping(input_details)
    output_details = _mapping(output_details)
    text = _count(input_details, 'text_tokens')
    audio = _count(input_details, 'audio_tokens')
    image = _count(input_details, 'image_tokens')
    input_detail_tokens = text + audio + image
    if text + audio + image == 0:
        text = _count(usage, 'input_tokens')
    output_text = _count(output_details, 'text_tokens')
    output_audio = _count(output_details, 'audio_tokens')
    reasoning = _count(output_details, 'reasoning_tokens')
    output_detail_tokens = output_text + output_audio + reasoning
    if output_text + output_audio + reasoning == 0:
        output_text = _count(usage, 'output_tokens')
    input_total = _count(usage, 'input_tokens')
    output_total = _count(usage, 'output_tokens')
    # An empty details object is not a provider-vouched split when the
    # aggregate side contains tokens. Aggregate-only input/output must remain
    # unpriced rather than being silently treated as text.
    input_split = input_total == 0 or (input_details_present and input_detail_tokens > 0)
    output_split = output_total == 0 or (output_details_present and output_detail_tokens > 0)
    split_reported = input_split and output_split
    cached_total = _count(input_details, 'cached_tokens')
    cached_details = input_details.get('cached_tokens_details')
    cached_details_present = isinstance(cached_details, Mapping)
    cached_details = _mapping(cached_details)
    cached_detail_text = _count(cached_details, 'text_tokens')
    cached_detail_audio = _count(cached_details, 'audio_tokens')
    cached_detail_image = _count(cached_details, 'image_tokens')
    if cached_details_present and cached_detail_text + cached_detail_audio + cached_detail_image > 0:
        cached_text = min(cached_detail_text, text)
        cached_audio = min(cached_detail_audio, audio)
        cached_image = min(cached_detail_image, image)
        cached_split = True
    else:
        cached_text, cached_audio, cached_image = split_cached_across_modalities(
            cached_total, text=text, audio=audio, image=image
        )
        cached_split = cached_total == 0 or _single_modality(text, audio, image)
    return dict(
        input_text_tokens=text,
        input_audio_tokens=audio,
        input_image_tokens=image,
        cached_text_tokens=cached_text,
        cached_audio_tokens=cached_audio,
        cached_image_tokens=cached_image,
        output_text_tokens=output_text,
        output_audio_tokens=output_audio,
        reasoning_tokens=reasoning,
        modality_split_reported=split_reported,
        cached_split_reported=cached_split,
    )


def _gemini_turn(usage: Mapping[str, Any]) -> RealtimeTurnUsage:
    prompt_details = usage.get('promptTokensDetails')
    response_details = usage.get('responseTokensDetails')
    prompt_split = _gemini_modalities(prompt_details)
    prompt_text, prompt_audio, prompt_image = prompt_split.text, prompt_split.audio, prompt_split.image
    prompt_total = _count(usage, 'promptTokenCount')
    if prompt_text + prompt_audio + prompt_image == 0:
        prompt_text = prompt_total
    response_split = _gemini_modalities(response_details)
    output_text, output_audio, output_image = response_split.text, response_split.audio, response_split.image
    output_total = _count(usage, 'candidatesTokenCount') or _count(usage, 'responseTokenCount')
    output_text += output_image
    if output_text + output_audio == 0:
        output_text = output_total
    reasoning = _count(usage, 'thoughtsTokenCount')
    tool_use = _count(usage, 'toolUsePromptTokenCount')
    # The split is vouched for only when every non-zero side has populated,
    # recognized details. Empty lists and unknown modalities are not evidence.
    prompt_side_split = (prompt_total == 0 and prompt_split.valid) or (
        prompt_split.present and prompt_split.populated and prompt_split.valid
    )
    output_side_split = (output_total == 0 and response_split.valid) or (
        response_split.present and response_split.populated and response_split.valid
    )
    split_reported = prompt_side_split and output_side_split
    cache_details = usage.get('cacheTokensDetails')
    cached_total = _count(usage, 'cachedContentTokenCount')
    cache_split = _gemini_modalities(cache_details)
    cached_text, cached_audio, cached_image = cache_split.text, cache_split.audio, cache_split.image
    if cache_split.present and cache_split.populated and cache_split.valid:
        cached_split = True
    else:
        cached_text, cached_audio, cached_image = split_cached_across_modalities(
            cached_total, text=prompt_text, audio=prompt_audio, image=prompt_image
        )
        cached_split = cache_split.valid and (
            cached_total == 0 or _single_modality(prompt_text, prompt_audio, prompt_image)
        )
    return RealtimeTurnUsage(
        provider=GEMINI_LIVE_PROVIDER,
        input_text_tokens=prompt_text,
        input_audio_tokens=prompt_audio,
        input_image_tokens=prompt_image,
        cached_text_tokens=min(cached_text, prompt_text),
        cached_audio_tokens=min(cached_audio, prompt_audio),
        cached_image_tokens=min(cached_image, prompt_image),
        output_text_tokens=output_text,
        output_audio_tokens=output_audio,
        reasoning_tokens=reasoning,
        tool_use_prompt_tokens=tool_use,
        usage_reported=True,
        modality_split_reported=split_reported,
        cached_split_reported=cached_split,
    )


def _gemini_delta(cumulative: RealtimeTurnUsage, baseline: RealtimeTurnUsage | None) -> RealtimeTurnUsage:
    """Field-wise ``cumulative - baseline``; a field that went down is a reset and counts absolute."""
    if baseline is None:
        return cumulative
    counts: dict[str, Any] = {}
    for field in _COUNT_FIELDS:
        new_value = getattr(cumulative, field)
        old_value = getattr(baseline, field)
        counts[field] = new_value - old_value if new_value >= old_value else new_value
    return replace(cumulative, **counts)


def _gemini_add(pending: RealtimeTurnUsage | None, delta: RealtimeTurnUsage) -> RealtimeTurnUsage:
    """Accumulate a delta into the turn in progress; the split is vouched for only if every block was."""
    if pending is None:
        return delta
    counts: dict[str, Any] = {field: getattr(pending, field) + getattr(delta, field) for field in _COUNT_FIELDS}
    return replace(
        pending,
        usage_reported=True,
        modality_split_reported=pending.modality_split_reported and delta.modality_split_reported,
        cached_split_reported=pending.cached_split_reported and delta.cached_split_reported,
        **counts,
    )


@dataclass(frozen=True)
class _GeminiModalitySplit:
    text: int = 0
    audio: int = 0
    image: int = 0
    present: bool = False
    populated: bool = False
    valid: bool = True


def _gemini_modalities(details: object) -> _GeminiModalitySplit:
    """Split details while retaining whether every positive modality was recognized."""
    text = audio = image = 0
    if not isinstance(details, list):
        return _GeminiModalitySplit()
    populated = False
    valid = True
    for entry in details:
        if not isinstance(entry, Mapping):
            valid = False
            continue
        count = _count(entry, 'tokenCount')
        modality = entry.get('modality')
        modality = modality.upper() if isinstance(modality, str) else ''
        if count <= 0:
            continue
        if modality == 'TEXT':
            text += count
            populated = True
        elif modality == 'AUDIO':
            audio += count
            populated = True
        elif modality in {'IMAGE', 'VIDEO'}:
            image += count
            populated = True
        else:
            # Do not fold unknown provider modalities into text. The caller
            # carries the aggregate count for observability but marks the
            # turn unpriceable because the rate card is no longer provable.
            valid = False
    return _GeminiModalitySplit(
        text=text,
        audio=audio,
        image=image,
        present=True,
        populated=populated,
        valid=valid,
    )


def _single_modality(*counts: int) -> bool:
    return sum(1 for count in counts if count > 0) <= 1


def _as_bytes(frame: object) -> bytes | None:
    if isinstance(frame, str):
        raw = frame.encode('utf-8', errors='replace')
    elif isinstance(frame, (bytes, bytearray)):
        raw = bytes(frame)
    else:
        return None
    if not raw or len(raw) > _MAX_PARSED_FRAME_BYTES:
        return None
    return raw


def _parse_json_object(raw: bytes) -> Mapping[str, Any] | None:
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, UnicodeDecodeError, RecursionError):
        return None
    return payload if isinstance(payload, Mapping) else None


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _count(mapping: Mapping[str, Any], key: str) -> int:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    if isinstance(value, float) and not math.isfinite(value):
        return 0
    return max(int(value), 0)
