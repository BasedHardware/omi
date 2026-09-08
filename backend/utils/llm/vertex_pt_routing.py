"""Vertex Provisioned Throughput routing policy for company-paid Gemini text.

Pure decision logic: which model serves company-paid text, which endpoint a
model is addressed at, which models may absorb its traffic when it cannot serve
it, and when a pending PT order has become live. No I/O, no clock, no Redis —
the proxy injects observations and owns every side effect, so every rule here
is unit-testable without a network.

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

from collections.abc import Iterable

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

# --- Fallback chains -------------------------------------------------------
# Output price per 1M tokens (Vertex list, captured 2026-08-18). Declared here
# so the cost direction of every chain is checkable rather than asserted in
# prose. Embedding has no output tokens and no substitute, so it is absent.
PRICE_PER_MTOK_OUT: dict[str, float] = {
    'gemini-2.5-flash-lite': 0.40,
    'gemini-3.1-flash-lite': 1.50,
    'gemini-2.5-flash': 2.50,
    'gemini-2.5-pro': 10.00,
}

# Every model the proxy can route to declares, as data, the ordered models that
# may serve its traffic when it cannot serve it itself. One reviewable table
# beats per-model conditionals scattered through the proxy.
#
# Three invariants, all enforced by tests rather than convention:
#   * every chain is non-increasing in output price, so a degraded request can
#     never cost more than the request it replaces;
#   * a chain never contains its own head, so a dead model cannot retry itself;
#   * the model currently holding Provisioned Throughput is filtered out at
#     resolution time (FC-degraded-fallback-consumes-protected-budget) —
#     degraded traffic must not consume the reservation the quota protects.
#
# An empty chain means terminal: the model is the cheapest option in its lane
# and there is nothing left to fall back to. `gemini-2.5-flash-lite` is the
# floor of the text ladder and is also the model clients pin directly, so
# giving it a chain would promote those lanes onto costlier models.
MODEL_FALLBACKS: dict[str, tuple[str, ...]] = {
    'gemini-2.5-pro': ('gemini-3.1-flash-lite', 'gemini-2.5-flash-lite'),
    'gemini-2.5-flash': ('gemini-3.1-flash-lite', 'gemini-2.5-flash-lite'),
    'gemini-3.1-flash-lite': ('gemini-2.5-flash-lite',),
    'gemini-2.5-flash-lite': (),
    'gemini-embedding-001': (),
}

# --- Where a model is served ----------------------------------------------
# Vertex publishes most models on regional endpoints
# (`{loc}-aiplatform.googleapis.com` + `locations/{loc}`). The Gemini 3.x
# family is not served regionally at all: it needs the un-prefixed host plus a
# multi-region `locations/{loc}` segment.
#
# Measured 2026-08-18 on `based-hardware` with credentials that can invoke
# inference:
#
#     locations/us      gemini-3.1-flash-lite  -> 200 ON_DEMAND
#     locations/global  gemini-3.1-flash-lite  -> 200 ON_DEMAND
#     locations/us      + `dedicated` header   -> 429 provisioned throughput
#     us-central1 / us-east5 / us-west1 / europe-west4 / asia-northeast1 -> 404
#
# So the 404 is an endpoint-shape error, not a project access gap — reading it
# as "the project cannot call 3.x" sends you looking for an allowlist that does
# not exist. The host is always plain `aiplatform.googleapis.com`;
# `us-aiplatform.googleapis.com` is not a valid host (400 Invalid hostname),
# only the `locations/{loc}` path segment changes.
MULTI_REGION_ENDPOINT_FAMILIES = ('gemini-3',)
MULTI_REGION_HOST = 'aiplatform.googleapis.com'
# `us`, not `global`. Both answer, but `global` may serve a request from
# anywhere in the world while `us` is the US multi-region. This product
# processes users' personal conversations, transcripts and memories, and every
# other server-paid Gemini call runs in `us-central1`, so `us` preserves the
# existing data-residency posture. Widening it is a deliberate decision, not
# something a routing change should make implicitly — which is why this is a
# named default an operator can flip rather than a literal in a URL.
MULTI_REGION_LOCATION = 'us'

# Vertex routes a request to prepaid or on-demand capacity by header.
# `dedicated` returns 429 instead of silently spilling to pay-as-you-go.
REQUEST_TYPE_HEADER = 'X-Vertex-AI-LLM-Request-Type'
REQUEST_TYPE_DEDICATED = 'dedicated'
REQUEST_TYPE_SHARED = 'shared'

# Operator env knobs, named here so the desktop BFF's kill-switch path and the
# gateway's Vertex adapter read the same strings instead of redeclaring them.
PT_MODEL_OVERRIDE_ENV = 'OMI_VERTEX_PT_MODEL'
OVERFLOW_MODEL_OVERRIDE_ENV = 'OMI_GEMINI_OVERFLOW_MODEL'
OVERFLOW_ENABLED_ENV = 'OMI_GEMINI_OVERFLOW_ENABLED'
MULTI_REGION_LOCATION_ENV = 'OMI_VERTEX_GLOBAL_LOCATION'
REGIONAL_LOCATION_ENV = 'GCP_LOCATION'


def _normalize(model: str) -> str:
    return (model or '').strip()


def uses_multi_region_endpoint(model: str) -> bool:
    """Whether a model is served only on the multi-region Vertex endpoint.

    Decided by model FAMILY, never by what happens to answer. `gemini-2.5-flash`
    also returns 200 on `locations/us` and `locations/global`, but sending it
    there would bypass the regional Provisioned Throughput order and bill
    on-demand while the reservation kept charging — the 2026-08-04 double-pay
    incident. "Route whatever works multi-region to multi-region" is the
    simplification that reintroduces it.
    """
    return _normalize(model).startswith(MULTI_REGION_ENDPOINT_FAMILIES)


def vertex_endpoint(
    *,
    model: str,
    regional_location: str,
    multi_region_location: str = MULTI_REGION_LOCATION,
) -> tuple[str, str]:
    """Return the (host, location) pair a model must be addressed with.

    Location is resolved PER MODEL, never once per process: a fallback chain
    routinely crosses families, so the reservation model and the model that
    absorbs its overflow can legitimately live on different endpoints. Building
    one regional URL for everything is what made every Gemini 3.x request 404.
    """
    if uses_multi_region_endpoint(model):
        return MULTI_REGION_HOST, _normalize(multi_region_location) or MULTI_REGION_LOCATION
    location = _normalize(regional_location)
    return f'{location}-aiplatform.googleapis.com', location


def thinking_config_for(*, budget: int) -> dict[str, object]:
    """Return the thinkingConfig body to send, for every model.

    There is deliberately no per-family branch here. Measured 2026-08-18 on the
    global endpoint, `gemini-3.1-flash-lite` HONORS `thinkingBudget`:

        thinkingBudget: 0        -> thoughts=0    output=64
        thinkingBudget: 1024     -> thoughts=278  output=77
        thinkingLevel: 'minimal' -> thoughts=0    output=75
        thinkingLevel: 'high'    -> thoughts=603  output=76
        (no thinking config)     -> thoughts=0    output=64

    while 2.5-family models reject `thinkingLevel` outright with HTTP 400
    ('thinking_level is not supported by this model'). `thinkingBudget` is
    therefore the one option both families accept, and `thinkingLevel` is the
    one that works on neither universally. An earlier revision split on family
    from documentation rather than measurement and had it backwards; the split
    is gone rather than inverted, so a fallback chain that crosses families
    needs no body rewriting at all.
    """
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


def resolve_overflow_ladder(*, pt_model: str, override: str = '') -> tuple[str, ...]:
    """Every on-demand model that may absorb work, best first.

    A ladder rather than a single model so a rung that cannot be called at all
    falls through to one that can, instead of failing the request. Never
    includes `pt_model` (FC-degraded-fallback-consumes-protected-budget).
    """
    protected = _normalize(pt_model)
    pinned = _normalize(override)
    if pinned:
        if pinned == protected:
            raise ValueError(
                f'overflow override {pinned!r} equals the provisioned model; '
                'overflow must never consume the protected reservation'
            )
        return (pinned,)
    ladder = tuple(c for c in OVERFLOW_PREFERENCE if c != protected)
    if not ladder:
        raise ValueError(f'no overflow model available outside the provisioned model {protected!r}')
    return ladder


def resolve_fallback_chain(
    *,
    model: str,
    pt_model: str,
    unreachable: Iterable[str] = (),
    override: str = '',
) -> tuple[str, ...]:
    """Models that may serve `model`'s traffic when `model` itself cannot, best first.

    Generalizes the overflow ladder to every routable model. Two filters apply
    to the declared chain:

      * `pt_model` is removed — a degraded request must never be answered out
        of the prepaid reservation
        (FC-degraded-fallback-consumes-protected-budget).
      * `unreachable` is removed — models a real `generateContent` attempt has
        already proved uncallable. Keeping such a rung would spend a round trip
        to fail on every request.

    `override` is the operator pin and replaces the whole chain, which is what
    makes a bad table correctable without a deploy. It is still refused when it
    aliases the reservation, and it can never point a model at itself.
    """
    protected = _normalize(pt_model)
    head = _normalize(model)
    dead = {_normalize(name) for name in unreachable}
    pinned = _normalize(override)
    if pinned:
        if pinned == protected:
            raise ValueError(
                f'fallback override {pinned!r} equals the provisioned model; '
                'fallback must never consume the protected reservation'
            )
        chain: tuple[str, ...] = (pinned,)
    else:
        chain = MODEL_FALLBACKS.get(head, ())
    return tuple(rung for rung in chain if rung != protected and rung != head and rung not in dead)


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


def is_model_unavailable(status: int, message: str) -> bool:
    """Whether a model is not reachable at the endpoint the request used.

    Distinct from both exhaustion and absent capacity: those mean "the model
    works but prepaid throughput did not serve this request". This means the
    publisher model does not exist at the host/location that was addressed, so
    every identically-routed request to it fails.

    The 2026-08-18 production case was exactly this: `gemini-3.1-flash-lite` is
    served only on the global endpoint, so every regional URL returned 404
    while the model itself was callable. `vertex_endpoint` is the fix; this
    predicate is the safety net for the next model whose serving surface does
    not match the URL the proxy builds.
    """
    if status != 404:
        return False
    text = (message or '').casefold()
    return 'publisher model' in text


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


# --- Desktop company-paid lane contract ------------------------------------
# The desktop BFF stays the auth/limit boundary, but the serving decision for
# company-paid Gemini text lives here (single policy module): it is consumed by
# the LLM gateway's Vertex adapter (`VertexGeminiProvider`) and mirrored by the
# gateway lane generator, never forked at the BFF.

# Gateway auto-lane id per desktop-requested text model. Lane ids cannot carry
# dots (LaneId schema), so each anchor model gets a stable semantic slug.
DESKTOP_TEXT_LANES: dict[str, str] = {
    PT_MODEL_CURRENT: 'omi:auto:desktop-vertex-flash',
    'gemini-2.5-pro': 'omi:auto:desktop-vertex-pro',
    PT_MODEL_TARGET: 'omi:auto:desktop-vertex-target',
    'gemini-2.5-flash-lite': 'omi:auto:desktop-vertex-flash-lite',
}
DESKTOP_EMBEDDING_MODEL = 'gemini-embedding-001'


def desktop_text_lane_id(model: str) -> str | None:
    """Gateway lane id for a desktop-requested company-paid text model."""
    return DESKTOP_TEXT_LANES.get(_normalize(model))


def desktop_serving_model(model: str, *, target_dedicated_ready: bool, override: str = '') -> str:
    """The model that actually serves a company-paid desktop request for `model`.

    The pin policy the desktop proxy ran in-process before the gateway move:
      * `gemini-2.5-pro`    -> the migration target (never the $10/M on-demand pro)
      * `PT_MODEL_CURRENT`  -> whichever model currently owns prepaid capacity
      * client-pinned models serve as themselves (flash-lite stays the cheap floor;
        3.1-flash-lite becomes `dedicated` automatically once it holds the order)
    """
    normalized = _normalize(model)
    if normalized == 'gemini-2.5-pro':
        return PT_MODEL_TARGET
    if normalized == PT_MODEL_CURRENT:
        return resolve_pt_model(target_dedicated_ready=target_dedicated_ready, override=override)
    return normalized
