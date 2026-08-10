"""Two-stage AI user profile synthesis is return-only through get_llm('memories')."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from utils.llm import ai_user_profile


@contextmanager
def _fake_track_usage(*_args, **_kwargs):
    yield


def _patch(monkeypatch, replies: list[str], captured: list[list[tuple[str, str]]]):
    class FakeLLM:
        def invoke(self, messages):
            captured.append(messages)
            return SimpleNamespace(content=replies[len(captured) - 1])

    monkeypatch.setattr(ai_user_profile, 'get_llm', lambda feature: FakeLLM())
    monkeypatch.setattr(ai_user_profile, 'track_usage', _fake_track_usage)


def test_stage_prompts_keep_their_hallucination_and_merge_guards():
    stage1 = ai_user_profile._STAGE1_SYSTEM_PROMPT
    assert 'third person' in stage1
    assert 'ONLY include facts that are directly evidenced' in stage1
    assert 'NEVER fabricate email addresses' in stage1
    assert 'under 2000 characters' in stage1

    stage2 = ai_user_profile._STAGE2_SYSTEM_PROMPT
    assert 'MERGE RULES' in stage2
    assert 'Do NOT hallucinate' in stage2
    assert 'under 2000 characters' in stage2


def test_no_source_items_returns_none():
    empty = ai_user_profile.ProfileSources(memories=['  '], tasks=[])
    assert ai_user_profile.synthesize_ai_user_profile('uid', empty) is None


def test_single_stage_when_no_past_profiles(monkeypatch):
    captured: list[list[tuple[str, str]]] = []
    _patch(monkeypatch, ['- User is an engineer'], captured)

    result = ai_user_profile.synthesize_ai_user_profile(
        'uid',
        ai_user_profile.ProfileSources(memories=['[work] engineer'], goals=['ship the desktop app']),
    )

    assert result is not None
    assert result.profile_text == '- User is an engineer'
    assert result.data_sources_used == ['memories', 'goals']
    assert result.item_count == 2
    assert len(captured) == 1
    stage1_user = captured[0][1][1]
    assert '## Memories about the user' in stage1_user
    assert '## Active goals' in stage1_user
    assert '## Recent tasks' not in stage1_user


def test_consolidates_with_past_profiles(monkeypatch):
    captured: list[list[tuple[str, str]]] = []
    _patch(monkeypatch, ['- fresh fact', '- merged fact'], captured)

    result = ai_user_profile.synthesize_ai_user_profile(
        'uid',
        ai_user_profile.ProfileSources(memories=['[work] engineer']),
        past_profiles=['- old fact', '  '],
    )

    assert result is not None
    assert result.profile_text == '- merged fact'
    assert len(captured) == 2
    stage2_user = captured[1][1][1]
    assert '- fresh fact' in stage2_user
    assert '- old fact' in stage2_user


def test_empty_stage1_content_returns_none(monkeypatch):
    captured: list[list[tuple[str, str]]] = []
    _patch(monkeypatch, ['   '], captured)

    assert (
        ai_user_profile.synthesize_ai_user_profile('uid', ai_user_profile.ProfileSources(memories=['[work] engineer']))
        is None
    )


def test_empty_stage2_content_keeps_stage1(monkeypatch):
    captured: list[list[tuple[str, str]]] = []
    _patch(monkeypatch, ['- fresh fact', ''], captured)

    result = ai_user_profile.synthesize_ai_user_profile(
        'uid',
        ai_user_profile.ProfileSources(memories=['[work] engineer']),
        past_profiles=['- old fact'],
    )

    assert result is not None
    assert result.profile_text == '- fresh fact'


def test_profile_text_is_hard_capped(monkeypatch):
    captured: list[list[tuple[str, str]]] = []
    _patch(monkeypatch, ['x' * (ai_user_profile.MAX_PROFILE_CHARS + 500)], captured)

    result = ai_user_profile.synthesize_ai_user_profile(
        'uid', ai_user_profile.ProfileSources(memories=['[work] engineer'])
    )

    assert result is not None
    assert len(result.profile_text) == ai_user_profile.MAX_PROFILE_CHARS
