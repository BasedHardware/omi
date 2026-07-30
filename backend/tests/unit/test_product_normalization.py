"""Regression tests for `X-App-Product` normalization and cohort fields."""

from database.user_product import normalize_product


def test_context_for_claude_is_allowed():
    assert normalize_product('context-for-claude') == 'context-for-claude'
    assert normalize_product('  Context-For-Claude  ') == 'context-for-claude'


def test_omi_product_surfaces_are_allowed():
    assert normalize_product('omi-desktop') == 'omi-desktop'
    assert normalize_product('omi-mobile') == 'omi-mobile'
    assert normalize_product('omi-web') == 'omi-web'


def test_unknown_product_is_rejected():
    assert normalize_product('macos') is None
    assert normalize_product('desktop') is None
    assert normalize_product('earshot') is None
    assert normalize_product('') is None
    assert normalize_product(None) is None
