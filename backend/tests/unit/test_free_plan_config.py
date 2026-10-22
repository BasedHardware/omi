"""The Free-plan env switches default off and treat malformed values as off (fail closed)."""

import pytest

from config import free_plan


@pytest.mark.parametrize(
    'name', ['FREE_RETENTION_LOCK_DAYS', 'FREE_TRANSCRIPTION_HARD_PAUSE', 'FREE_CHAT_QUESTIONS_PER_DAY']
)
def test_unset_is_off(monkeypatch, name):
    monkeypatch.delenv(name, raising=False)
    assert free_plan.free_retention_lock_days() == 0
    assert free_plan.free_transcription_hard_pause() is False
    assert free_plan.free_chat_questions_per_day() == 0


@pytest.mark.parametrize(
    'raw, expected', [('30', 30), (' 7 ', 7), ('0', 0), ('-3', 0), ('abc', 0), ('', 0), ('1.5', 0)]
)
def test_integer_switches_parse_strictly(monkeypatch, raw, expected):
    monkeypatch.setenv('FREE_RETENTION_LOCK_DAYS', raw)
    monkeypatch.setenv('FREE_CHAT_QUESTIONS_PER_DAY', raw)
    assert free_plan.free_retention_lock_days() == expected
    assert free_plan.free_chat_questions_per_day() == expected


@pytest.mark.parametrize(
    'raw, expected',
    [('true', True), ('1', True), ('YES', True), ('on', True), ('false', False), ('0', False), ('maybe', False)],
)
def test_hard_pause_parses_booleans(monkeypatch, raw, expected):
    monkeypatch.setenv('FREE_TRANSCRIPTION_HARD_PAUSE', raw)
    assert free_plan.free_transcription_hard_pause() is expected
