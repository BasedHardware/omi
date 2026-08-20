"""Contract tests for Vertex Provisioned Throughput routing policy.

These lock the cost invariants that survive a PT migration. The point of the
policy module is that re-pointing the reservation cannot silently re-point
overflow onto it, so most of these assert behaviour across BOTH PT states.
"""

import pytest

from utils.llm import vertex_pt_routing as ptr


def test_pt_model_defaults_to_the_currently_provisioned_order():
    assert ptr.resolve_pt_model(target_dedicated_ready=False) == 'gemini-2.5-flash'


def test_pt_model_promotes_itself_once_target_capacity_answers():
    assert ptr.resolve_pt_model(target_dedicated_ready=True) == 'gemini-3.1-flash-lite'


@pytest.mark.parametrize('ready', [False, True])
def test_operator_override_pins_the_pt_model_in_either_direction(ready):
    """The emergency flag must beat auto-detection, including a false positive."""
    assert ptr.resolve_pt_model(target_dedicated_ready=ready, override='gemini-2.5-flash') == 'gemini-2.5-flash'


def test_overflow_prefers_3_1_flash_lite_while_flash_holds_the_reservation():
    assert ptr.resolve_overflow_model(pt_model='gemini-2.5-flash') == 'gemini-3.1-flash-lite'


def test_overflow_steps_past_the_reservation_after_migration():
    """FC-degraded-fallback-consumes-protected-budget.

    Once 3.1-flash-lite IS the prepaid model, sending overflow to it would
    convert the quota into unmetered consumption of the reservation.
    """
    assert ptr.resolve_overflow_model(pt_model='gemini-3.1-flash-lite') == 'gemini-2.5-flash-lite'


@pytest.mark.parametrize('pt_model', ['gemini-2.5-flash', 'gemini-3.1-flash-lite', 'gemini-2.5-flash-lite'])
def test_overflow_is_never_the_protected_model(pt_model):
    assert ptr.resolve_overflow_model(pt_model=pt_model) != pt_model


def test_overflow_override_cannot_alias_the_protected_model():
    with pytest.raises(ValueError, match='protected reservation'):
        ptr.resolve_overflow_model(pt_model='gemini-2.5-flash', override='gemini-2.5-flash')


def test_dedicated_is_requested_only_for_the_provisioned_model():
    assert ptr.request_type_for(model='gemini-2.5-flash', pt_model='gemini-2.5-flash') == 'dedicated'
    assert ptr.request_type_for(model='gemini-3.1-flash-lite', pt_model='gemini-2.5-flash') == 'shared'


def test_overflow_traffic_is_explicitly_shared_after_migration():
    """The overflow model must not inherit `dedicated` when PT moves."""
    pt = 'gemini-3.1-flash-lite'
    overflow = ptr.resolve_overflow_model(pt_model=pt)
    assert ptr.request_type_for(model=overflow, pt_model=pt) == 'shared'


def test_thinking_budget_is_the_one_option_both_families_accept():
    """Measured 2026-08-18, not read from documentation.

    gemini-3.1-flash-lite honors `thinkingBudget` on the global endpoint
    (budget 0 -> thoughts 0; budget 1024 -> thoughts 278), and 2.5 models
    reject `thinkingLevel` with HTTP 400 'thinking_level is not supported by
    this model'. So `thinkingBudget` works on both families and `thinkingLevel`
    works on neither universally: there is no family split to make.
    """
    assert ptr.thinking_config_for(budget=1024) == {'thinkingBudget': 1024}
    assert ptr.thinking_config_for(budget=0) == {'thinkingBudget': 0}


def test_no_model_is_ever_sent_a_thinking_level():
    """A 2.5 model answers 400 to `thinkingLevel`, so emitting one anywhere
    would break every request that crossed onto the 2.5 family."""
    assert 'thinkingLevel' not in ptr.thinking_config_for(budget=1024)


def test_saturated_reservation_is_distinguished_from_generic_rate_limiting():
    assert ptr.is_provisioned_capacity_exhausted(429, 'Too many requests. Exceeded the Provisioned Throughput.')
    assert not ptr.is_provisioned_capacity_exhausted(429, 'Quota exceeded for requests per minute')
    assert not ptr.is_provisioned_capacity_exhausted(200, 'Exceeded the Provisioned Throughput')


def test_absent_capacity_is_not_read_as_exhausted_capacity():
    absent = 'Provisioned Throughput order not found for this model'
    assert ptr.is_provisioned_capacity_absent(404, absent)
    assert not ptr.is_provisioned_capacity_absent(429, 'Exceeded the Provisioned Throughput.')


def test_pt_constants_stay_distinct():
    assert ptr.PT_MODEL_CURRENT != ptr.PT_MODEL_TARGET
    assert ptr.PT_MODEL_TARGET in ptr.OVERFLOW_PREFERENCE


# --- Endpoint selection ----------------------------------------------------


def test_gemini_3_x_is_addressed_on_the_us_multi_region_endpoint():
    """Measured 2026-08-18: gemini-3.1-flash-lite answers 200 on locations/us
    and locations/global, and 404s on us-central1, us-east5, us-west1,
    europe-west4 and asia-northeast1. The 404 was an endpoint-shape error,
    never an access gap.

    `us` rather than `global` is a data-residency choice: `global` may serve a
    request from anywhere in the world, while every other server-paid call in
    this service runs in us-central1. The host is plain
    `aiplatform.googleapis.com` — `us-aiplatform.googleapis.com` is not a valid
    host (400 Invalid hostname).
    """
    assert ptr.vertex_endpoint(model='gemini-3.1-flash-lite', regional_location='us-central1') == (
        'aiplatform.googleapis.com',
        'us',
    )


def test_the_multi_region_default_is_us_and_stays_operator_overridable():
    assert ptr.MULTI_REGION_LOCATION == 'us'
    assert ptr.vertex_endpoint(
        model='gemini-3.1-flash-lite', regional_location='us-central1', multi_region_location='global'
    ) == ('aiplatform.googleapis.com', 'global')


def test_the_reservation_model_stays_regional_even_though_global_would_answer():
    """FC-degraded-fallback-consumes-protected-budget, and the 2026-08-04
    double-pay incident.

    gemini-2.5-flash ALSO answers on locations/us and locations/global
    (measured: 200, trafficType=ON_DEMAND). Routing it there would bypass the
    5 GSU us-central1 Provisioned Throughput order and bill on-demand while the
    reservation kept charging ~$290/day — paying twice for the same tokens,
    which is exactly what backend/docs/vertex-pt-flash.md records for
    2026-08-04. The endpoint rule is therefore by model FAMILY, never
    'multi-region for anything that answers multi-region'.
    """
    assert ptr.vertex_endpoint(model=ptr.PT_MODEL_CURRENT, regional_location='us-central1') == (
        'us-central1-aiplatform.googleapis.com',
        'us-central1',
    )
    assert ptr.uses_multi_region_endpoint(ptr.PT_MODEL_CURRENT) is False


@pytest.mark.parametrize(
    'model', ['gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemini-2.5-pro', 'gemini-embedding-001']
)
def test_every_non_3_x_model_keeps_the_regional_endpoint(model):
    host, location = ptr.vertex_endpoint(model=model, regional_location='us-central1')
    assert host == 'us-central1-aiplatform.googleapis.com'
    assert location == 'us-central1'


def test_location_is_resolved_per_model_not_once_per_process():
    """A fallback chain crosses families, so the reservation and the model that
    absorbs its overflow can legitimately live on different endpoints."""
    reserved = ptr.vertex_endpoint(model='gemini-2.5-flash', regional_location='us-central1')
    overflow = ptr.vertex_endpoint(model='gemini-3.1-flash-lite', regional_location='us-central1')
    assert reserved != overflow


# --- Fallback chains -------------------------------------------------------


def test_every_declared_fallback_is_itself_a_declared_model():
    """A chain that names an undeclared model has no chain of its own, so a
    second failure on it would have nowhere to go."""
    for model, chain in ptr.MODEL_FALLBACKS.items():
        for rung in chain:
            assert rung in ptr.MODEL_FALLBACKS, f'{model} falls back to undeclared {rung}'


def test_no_chain_contains_its_own_head():
    for model, chain in ptr.MODEL_FALLBACKS.items():
        assert model not in chain


def test_every_chain_is_non_increasing_in_output_price():
    """A degraded request must never cost more than the request it replaces."""
    for model, chain in ptr.MODEL_FALLBACKS.items():
        prices = [ptr.PRICE_PER_MTOK_OUT[m] for m in (model, *chain) if m in ptr.PRICE_PER_MTOK_OUT]
        assert prices == sorted(prices, reverse=True), f'{model} chain {chain} climbs in price'


def test_the_cheapest_text_model_is_terminal():
    """gemini-2.5-flash-lite is the floor of the ladder AND the model the
    clients pin directly (macOS ModelQoS.lightweight, Windows
    memory/goals/insight). Any chain here would promote those lanes onto a
    costlier model."""
    assert ptr.MODEL_FALLBACKS['gemini-2.5-flash-lite'] == ()
    cheapest = min(ptr.PRICE_PER_MTOK_OUT, key=lambda m: ptr.PRICE_PER_MTOK_OUT[m])
    assert cheapest == 'gemini-2.5-flash-lite'


@pytest.mark.parametrize('pt_model', ['gemini-2.5-flash', 'gemini-3.1-flash-lite'])
@pytest.mark.parametrize('model', sorted(ptr.MODEL_FALLBACKS))
def test_no_fallback_chain_ever_routes_onto_the_reservation(model, pt_model):
    """FC-degraded-fallback-consumes-protected-budget, at every PT state."""
    assert pt_model not in ptr.resolve_fallback_chain(model=model, pt_model=pt_model)


def test_chain_steps_past_the_reservation_after_migration():
    before = ptr.resolve_fallback_chain(model='gemini-2.5-pro', pt_model='gemini-2.5-flash')
    after = ptr.resolve_fallback_chain(model='gemini-2.5-pro', pt_model='gemini-3.1-flash-lite')
    assert before == ('gemini-3.1-flash-lite', 'gemini-2.5-flash-lite')
    assert after == ('gemini-2.5-flash-lite',)


def test_unreachable_rungs_are_dropped_from_the_chain():
    chain = ptr.resolve_fallback_chain(
        model='gemini-2.5-pro',
        pt_model='gemini-2.5-flash',
        unreachable=('gemini-3.1-flash-lite',),
    )
    assert chain == ('gemini-2.5-flash-lite',)


def test_a_terminal_model_has_nowhere_to_fall_back_to():
    assert ptr.resolve_fallback_chain(model='gemini-2.5-flash-lite', pt_model='gemini-2.5-flash') == ()
    assert ptr.resolve_fallback_chain(model='gemini-embedding-001', pt_model='gemini-2.5-flash') == ()


def test_fallback_override_replaces_the_chain_but_not_the_protection():
    assert ptr.resolve_fallback_chain(
        model='gemini-2.5-flash', pt_model='gemini-2.5-flash', override='gemini-2.5-flash-lite'
    ) == ('gemini-2.5-flash-lite',)
    with pytest.raises(ValueError, match='protected reservation'):
        ptr.resolve_fallback_chain(model='gemini-2.5-pro', pt_model='gemini-2.5-flash', override='gemini-2.5-flash')


def test_override_can_never_point_a_model_at_itself():
    """Otherwise a dead model would retry itself until the plan ran out."""
    assert (
        ptr.resolve_fallback_chain(
            model='gemini-2.5-flash-lite', pt_model='gemini-2.5-flash', override='gemini-2.5-flash-lite'
        )
        == ()
    )


def test_overflow_ladder_and_the_reservation_chain_cannot_drift():
    """Two tables describing the same degraded ladder; pin them together."""
    assert ptr.MODEL_FALLBACKS[ptr.PT_MODEL_CURRENT] == ptr.OVERFLOW_PREFERENCE


def test_exhaustion_matching_is_case_insensitive():
    """The global endpoint answers with lowercase 'provisioned throughput'
    where the regional one uses title case. Measured 2026-08-18."""
    assert ptr.is_provisioned_capacity_exhausted(429, 'Too many requests. Exceeded the provisioned throughput.')
    assert ptr.is_provisioned_capacity_exhausted(429, 'Too many requests. Exceeded the Provisioned Throughput.')
