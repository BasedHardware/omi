"""Vertex Provisioned Throughput routing policy for company-paid Gemini text.

Pure decision logic: which model serves company-paid text, which model absorbs
overflow, how thinking is configured per model family, and when a pending PT
order has become live. No I/O, no clock, no Redis — the proxy injects
observations and owns every side effect, so every rule here is unit-testable.

Prices per 1M tokens (Vertex list, captured 2026-08-18):

    gemini-2.5-flash-lite   $0.10 in / $0.40 out
    gemini-3.1-flash-lite   $0.25 in / $1.50 out
    gemini-2.5-flash        $0.30 in / $2.50 out
    gemini-2.5-pro          $1.25 in / $10.00 out

`gemini-3.1-flash-lite` is NOT the same price class as `gemini-2.5-flash-lite`
(2.5x in / 3.75x out). It is cheaper than `gemini-2.5-flash` and far cheaper
than `gemini-2.5-pro`, which is why it absorbs overflow and Pro but must never
absorb the lanes that clients already pin to `gemini-2.5-flash-lite`.
"""

from __future__ import annotations

# --- Provisioned Throughput orders ----------------------------------------
# The prepaid model today: 5 GSU, us-central1, flat ~$290.32/day until
# ~2027-05-28 whether or not traffic uses it. It must stay saturated; moving
# dedicated traffic off it pays for an idle reservation AND full on-demand.
PT_MODEL_CURRENT = 'gemini-2.5-flash'

# Migration target. A PT order for this model provisions in ~10 business days.
# Nothing needs to be redeployed when it lands: the proxy attempts `dedicated`
# on this model, and a non-429 response is the proof that capacity exists.
PT_MODEL_TARGET = 'gemini-3.1-flash-lite'

# Overflow ladder, most-capable first. Overflow is always on-demand, so this is
# also a cost ladder: 3.1-flash-lite ($1.50 out) beats 2.5-flash spillover
# ($2.50 out); 2.5-flash-lite ($0.40 out) is the floor.
#
# FC-degraded-fallback-consumes-protected-budget: overflow is resolved against
# the LIVE PT model rather than pinned, so when the reservation migrates to
# gemini-3.1-flash-lite the ladder steps past it automatically instead of
# dumping degraded traffic onto the budget the quota exists to protect.
OVERFLOW_PREFERENCE = ('gemini-3.1-flash-lite', 'gemini-2.5-flash-lite')

# Vertex routes a request to prepaid or on-demand capacity by header.
# `dedicated` returns 429 instead of silently spilling to pay-as-you-go.
REQUEST_TYPE_HEADER = 'X-Vertex-AI-LLM-Request-Type'
REQUEST_TYPE_DEDICATED = 'dedicated'
REQUEST_TYPE_SHARED = 'shared'

# Gemini 3.x replaced the integer `thinkingBudget` with a coarse
# `thinkingLevel`, and thinking cannot be disabled: the floor is 'minimal'.
# Thinking tokens bill as OUTPUT, so sending a 2.5-style budget to a 3.x model
# risks unbounded reasoning at $1.50/1M with no cap that the model honors.
_THINKING_LEVEL_FAMILIES = ('gemini-3',)
THINKING_LEVEL_MINIMAL = 'minimal'


def _normalize(model: str) -> str:
    return (model or '').strip()


def uses_thinking_level(model: str) -> bool:
    """Whether a model takes `thinkingLevel` instead of `thinkingBudget`."""
    return _normalize(model).startswith(_THINKING_LEVEL_FAMILIES)


def thinking_config_for(model: str, *, budget: int) -> dict[str, object]:
    """Return the provider-correct thinkingConfig body for a model.

    2.5-family models take an integer token budget. 3.x models take a level and
    cannot switch thinking off, so the cheapest honored setting is 'minimal'.
    Sending a budget to a 3.x model is the cost regression this guards: the
    field is schema-valid, so it is accepted and then ignored.
    """
    if uses_thinking_level(model):
        return {'thinkingLevel': THINKING_LEVEL_MINIMAL}
    return {'thinkingBudget': int(budget)}


def resolve_pt_model(*, target_dedicated_ready: bool, override: str = '') -> str:
    """Which model currently owns prepaid capacity.

    `override` is the operator escape hatch and wins unconditionally, so a bad
    auto-detection can be pinned back without a code change.
    """
    pinned = _normalize(override)
    if pinned:
        return pinned
    return PT_MODEL_TARGET if target_dedicated_ready else PT_MODEL_CURRENT


def resolve_overflow_model(*, pt_model: str, override: str = '') -> str:
    """Which model absorbs work that prepaid capacity cannot serve.

    Never returns `pt_model`: overflow exists to spare the reservation, so
    routing it back onto the reservation would defeat the quota entirely
    (FC-degraded-fallback-consumes-protected-budget).
    """
    pinned = _normalize(override)
    protected = _normalize(pt_model)
    if pinned:
        if pinned == protected:
            raise ValueError(
                f'overflow override {pinned!r} equals the provisioned model; '
                'overflow must never consume the protected reservation'
            )
        return pinned
    for candidate in OVERFLOW_PREFERENCE:
        if candidate != protected:
            return candidate
    raise ValueError(f'no overflow model available outside the provisioned model {protected!r}')


def request_type_for(*, model: str, pt_model: str) -> str:
    """Header value for a model: prepaid capacity only exists for the PT model.

    Requesting `dedicated` for the PT model converts silent spillover into a
    429 the caller can act on. Everything else is explicitly `shared` so it can
    never draw down the reservation.
    """
    return REQUEST_TYPE_DEDICATED if _normalize(model) == _normalize(pt_model) else REQUEST_TYPE_SHARED


def is_provisioned_capacity_exhausted(status: int, message: str) -> bool:
    """Whether a response means 'prepaid capacity is full', not 'slow down'.

    Vertex returns 429 for both a saturated PT order and ordinary per-project
    rate limiting. Only the former should fall back to on-demand; treating a
    generic 429 as overflow would convert real backpressure into extra spend.
    """
    if status != 429:
        return False
    text = (message or '').casefold()
    return 'provisioned throughput' in text or 'dedicated' in text


def is_provisioned_capacity_absent(status: int, message: str) -> bool:
    """Whether `dedicated` failed because no PT order exists for the model.

    Distinct from exhaustion: absence is the steady state for a migration
    target that has not provisioned yet, and must not be read as 'live'.
    """
    if status not in {400, 403, 404, 429}:
        return False
    text = (message or '').casefold()
    if 'provisioned throughput' not in text and 'dedicated' not in text:
        return False
    return any(token in text for token in ('not found', 'no provisioned', 'does not exist', 'not configured'))
