"""Regression tests for `X-App-Product` normalization and cohort fields."""

from database.users import _normalize_product


def test_context_for_claude_is_allowed():
    assert _normalize_product('context-for-claude') == 'context-for-claude'
    assert _normalize_product('  Context-For-Claude  ') == 'context-for-claude'


def test_omi_product_surfaces_are_allowed():
    assert _normalize_product('omi-desktop') == 'omi-desktop'
    assert _normalize_product('omi-mobile') == 'omi-mobile'
    assert _normalize_product('omi-web') == 'omi-web'


def test_unknown_product_is_rejected():
    assert _normalize_product('macos') is None
    assert _normalize_product('desktop') is None
    assert _normalize_product('earshot') is None
    assert _normalize_product('') is None
    assert _normalize_product(None) is None
