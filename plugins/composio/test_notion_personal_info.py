"""Keyword matching must be case-insensitive (#13302)."""

from src.notion import contains_personal_info, format_as_memory


def test_detects_mixed_case_keywords_after_lowercasing_input():
    assert contains_personal_info("I like reading science fiction books on weekends")
    assert contains_personal_info("i like reading")


def test_format_memory_replaces_like():
    out = format_as_memory("I like reading science fiction books on weekends")
    assert "User likes" in out
