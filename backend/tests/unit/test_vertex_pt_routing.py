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


def test_2_5_family_keeps_an_integer_thinking_budget():
    assert ptr.thinking_config_for('gemini-2.5-flash', budget=1024) == {'thinkingBudget': 1024}
    assert ptr.thinking_config_for('gemini-2.5-flash-lite', budget=0) == {'thinkingBudget': 0}


def test_3_x_family_gets_a_thinking_level_never_a_budget():
    """thinkingBudget is schema-valid on 3.x and then ignored, so an unbounded
    reasoning trace would bill as output at $1.50/1M."""
    config = ptr.thinking_config_for('gemini-3.1-flash-lite', budget=1024)
    assert config == {'thinkingLevel': 'minimal'}
    assert 'thinkingBudget' not in config


def test_migration_target_never_receives_a_thinking_budget():
    assert 'thinkingBudget' not in ptr.thinking_config_for(ptr.PT_MODEL_TARGET, budget=1024)


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
