"""Unit tests for coding agent pricing math.

These tests assert the *formula* (markup, rounding, min-charge floor) — not the
hardcoded rate values, since rates are env-overridable. Rate values are tested
indirectly via the markup relationship.
"""

from decimal import Decimal

import pytest

from utils.agent_code.pricing import (
    COST_INPUT_PER_M_USD,
    COST_OUTPUT_PER_M_USD,
    MARKUP,
    MIN_TURN_CHARGE_CENTS,
    PRICE_INPUT_PER_M_USD,
    PRICE_OUTPUT_PER_M_USD,
    compute_charge_cents,
    compute_raw_cost_cents,
)


def test_markup_is_applied_to_both_rates():
    assert PRICE_INPUT_PER_M_USD == COST_INPUT_PER_M_USD * MARKUP
    assert PRICE_OUTPUT_PER_M_USD == COST_OUTPUT_PER_M_USD * MARKUP


def test_markup_is_strictly_above_one():
    assert MARKUP > Decimal("1.0")


def test_zero_tokens_costs_nothing():
    assert compute_raw_cost_cents(0, 0) == 0
    assert compute_charge_cents(0, 0) == 0


def test_negative_tokens_treated_as_zero():
    assert compute_raw_cost_cents(-100, -50) == 0
    assert compute_charge_cents(-100, -50) == 0


def test_min_charge_floor_applies_to_tiny_turns():
    # Any non-zero usage that would round to 0 cents floors to MIN_TURN_CHARGE_CENTS.
    assert compute_charge_cents(1, 0) == MIN_TURN_CHARGE_CENTS
    assert compute_charge_cents(0, 1) == MIN_TURN_CHARGE_CENTS


def test_min_charge_floor_does_not_inflate_real_charges():
    # 1M output tokens definitely costs more than the floor; floor should not kick in.
    assert compute_charge_cents(0, 1_000_000) > MIN_TURN_CHARGE_CENTS


@pytest.mark.parametrize(
    "in_tok,out_tok",
    [
        (1_000_000, 0),
        (0, 1_000_000),
        (50_000, 10_000),
        (250_000, 50_000),
        (1_000_000, 200_000),
    ],
)
def test_charge_always_at_least_raw(in_tok, out_tok):
    raw = compute_raw_cost_cents(in_tok, out_tok)
    charged = compute_charge_cents(in_tok, out_tok)
    assert charged >= raw, f"charged ({charged}) must be >= raw ({raw}) for {in_tok}/{out_tok}"


def test_charge_scales_linearly_with_tokens():
    a = compute_charge_cents(1_000_000, 0)
    b = compute_charge_cents(2_000_000, 0)
    # Allow ±1 cent slack from rounding.
    assert abs(b - 2 * a) <= 1


def test_input_and_output_charges_are_additive():
    in_only = compute_charge_cents(1_000_000, 0)
    out_only = compute_charge_cents(0, 1_000_000)
    combined = compute_charge_cents(1_000_000, 1_000_000)
    assert abs(combined - (in_only + out_only)) <= 1
