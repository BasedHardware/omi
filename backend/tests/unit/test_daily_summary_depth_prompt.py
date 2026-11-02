"""The saved depth changes the real daily-summary LLM request, not just settings UI."""

from unittest.mock import MagicMock

import pytest

from tests.unit.test_daily_summary_zero_coordinate_locations import _Convo, _configure, ext


@pytest.mark.parametrize(
    ('stored_depth', 'expected_text', 'excluded_text'),
    [
        ('brief', 'highlights: Max 4. One sentence each.', 'No fixed item count'),
        ('normal', 'Include up to 8 genuinely useful items per section', 'highlights: Max 4'),
        ('deep', 'Do not impose a fixed item count', 'highlights: Max 4'),
        ('not-a-depth', 'highlights: Max 4. One sentence each.', 'No fixed item count'),
    ],
)
def test_generation_uses_account_depth(ext, stored_depth, expected_text, excluded_text):
    _configure(ext)
    ext.users_db.get_user_profile = MagicMock(
        return_value={'time_zone': 'UTC', 'language': 'en', 'daily_summary_depth': stored_depth}
    )

    ext.generate_comprehensive_daily_summary('user-1', [_Convo('conversation-1')], '2026-09-30')

    prompt = ext.get_llm.return_value.invoke.call_args.args[0]
    assert expected_text in prompt
    assert excluded_text not in prompt
    assert 'Respond with ONLY valid JSON' in prompt
    if stored_depth == 'deep':
        assert 'A real decision with two to four sentences explaining the evidence and significance' in prompt
    if stored_depth == 'brief':
        assert "Short question that wasn't answered" in prompt
    if stored_depth != 'deep':
        ext.daily_summaries_db.get_daily_summaries.assert_not_called()
        ext.goals_db.get_user_goals.assert_not_called()


def test_deep_reflection_uses_only_earlier_recaps_and_active_goals(ext):
    _configure(ext)
    ext.users_db.get_user_profile = MagicMock(
        return_value={'time_zone': 'UTC', 'language': 'en', 'daily_summary_depth': 'deep'}
    )
    ext.daily_summaries_db.get_daily_summaries.return_value = [
        {'date': '2026-09-29', 'headline': 'Made progress', 'overview': 'Shipped the first prototype.'}
    ]
    ext.goals_db.get_user_goals.return_value = [
        {'title': 'Finish the project', 'description': 'Ship a working release'}
    ]

    ext.generate_comprehensive_daily_summary('user-1', [_Convo('conversation-1')], '2026-09-30')

    prompt = ext.get_llm.return_value.invoke.call_args.args[0]
    assert '2026-09-29: Made progress — Shipped the first prototype.' in prompt
    assert 'Finish the project: Ship a working release' in prompt
    ext.daily_summaries_db.get_daily_summaries.assert_called_once_with('user-1', limit=3, end_date='2026-09-29')
    ext.goals_db.get_user_goals.assert_called_once_with('user-1', limit=3)


def test_daily_recap_normalizes_a_sentinel_language_to_english(ext):
    _configure(ext)
    ext.users_db.get_user_profile = MagicMock(
        return_value={'time_zone': 'UTC', 'language': 'multi', 'daily_summary_depth': 'normal'}
    )

    ext.generate_comprehensive_daily_summary('user-1', [_Convo('conversation-1')], '2026-09-30')

    prompt = ext.get_llm.return_value.invoke.call_args.args[0]
    assert 'OUTPUT LANGUAGE: en.' in prompt
    assert 'OUTPUT LANGUAGE: multi.' not in prompt


def test_shared_kill_switch_restores_comprehensive_recap_language_prompt(ext, monkeypatch):
    _configure(ext)
    monkeypatch.setenv('EPISODE_OUTPUT_LANGUAGE_PIN', 'off')
    ext.users_db.get_user_profile = MagicMock(
        return_value={'time_zone': 'UTC', 'language': 'ja', 'daily_summary_depth': 'normal'}
    )

    ext.generate_comprehensive_daily_summary('user-1', [_Convo('conversation-1')], '2026-09-30')

    prompt = ext.get_llm.return_value.invoke.call_args.args[0]
    assert 'You MUST write every word of this summary in ja' in prompt
    assert 'Keep names and quoted words verbatim.' not in prompt


def test_shared_kill_switch_restores_simple_recap_language_prompt(ext, monkeypatch):
    _configure(ext)
    monkeypatch.setenv('EPISODE_OUTPUT_LANGUAGE_PIN', 'off')
    ext.users_db.get_user_language_preference = MagicMock(return_value='ja')

    ext.get_conversation_summary('user-1', [_Convo('conversation-1')])

    prompt = ext.get_llm.return_value.invoke.call_args.args[0]
    assert 'You MUST respond entirely in ja. Do NOT respond in English.' in prompt
    assert 'Write all output in ja.' not in prompt


def test_deep_reflection_missing_optional_context_still_generates(ext):
    _configure(ext)
    ext.users_db.get_user_profile = MagicMock(
        return_value={'time_zone': 'UTC', 'language': 'en', 'daily_summary_depth': 'deep'}
    )
    ext.daily_summaries_db.get_daily_summaries.side_effect = RuntimeError('unavailable')

    ext.generate_comprehensive_daily_summary('user-1', [_Convo('conversation-1')], '2026-09-30')

    assert 'Do not impose a fixed item count' in ext.get_llm.return_value.invoke.call_args.args[0]
    ext.record_fallback.assert_called_once()
    assert ext.record_fallback.call_args.kwargs['component'] == 'daily_summary'
    assert ext.record_fallback.call_args.kwargs['outcome'] == 'degraded'
