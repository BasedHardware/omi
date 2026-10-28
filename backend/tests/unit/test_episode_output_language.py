"""The episode prompt consumes L3's authority without a second model call."""

import sys
from datetime import datetime, timezone
from types import ModuleType
from unittest.mock import Mock

import pytest

from config import episodes as episodes_config
from database import users as users_db
from utils.episodes import incremental, output_language as episode_language
from utils.episodes.output_language import resolved_invoke
from utils.llm.output_language import normalize_language, resolve_output_language

NOW = datetime(2026, 10, 28, 9, 0, tzinfo=timezone.utc)


def test_episode_language_comes_from_l3_only_for_serve(monkeypatch):
    authority = ModuleType('utils.llm.output_language')
    authority.resolve_output_language = Mock(return_value='English')
    monkeypatch.setitem(sys.modules, 'utils.llm.output_language', authority)
    invoke = Mock(return_value='fixture')
    monkeypatch.setenv('LIFECYCLE_V2_MODE', 'shadow')
    assert resolved_invoke('test-account', 'en', invoke) is invoke
    authority.resolve_output_language.assert_not_called()
    monkeypatch.setenv('LIFECYCLE_V2_MODE', 'serve')
    call = resolved_invoke('test-account', 'en', invoke)
    assert call('test-account', [('system', 'fixture prompt')]) == 'fixture'
    authority.resolve_output_language.assert_called_once_with('test-account', 'en')
    invoke.assert_called_once()
    assert invoke.call_args.args[1][-1] == ('system', 'Write all episode output in English.')


@pytest.mark.parametrize(
    'raw,expected',
    [
        ('en', 'en'),
        (' vi ', 'vi'),
        ('EN', 'en'),
        ('multi', ''),
        ('MULTI', ''),
        ('auto', ''),
        ('unknown', ''),
        ('none', ''),
        ('', ''),
        (None, ''),
    ],
)
def test_normalize_language_drops_sentinels(raw, expected):
    assert normalize_language(raw) == expected


@pytest.mark.parametrize(
    'preference,conversation,expected',
    [('en', 'vi', 'en'), ('', 'vi', 'vi'), ('', 'multi', 'en'), ('multi', 'vi', 'vi'), ('', None, 'en')],
)
def test_resolve_prefers_preference_then_normalized_conversation(monkeypatch, preference, conversation, expected):
    monkeypatch.setattr(users_db, 'get_user_language_preference', lambda *_args: preference)
    assert resolve_output_language('uid-lang', conversation) == expected


def test_resolve_survives_a_preference_read_outage(monkeypatch):
    def boom(_uid):
        raise RuntimeError('no credentials')

    monkeypatch.setattr(users_db, 'get_user_language_preference', boom)
    assert resolve_output_language('uid-lang', 'vi') == 'vi'
    assert resolve_output_language('uid-lang', None) == 'en'


@pytest.mark.parametrize(
    'preference,stored,conversation,expected',
    [
        ('en', 'vi', 'vi', 'en'),  # The explicit preference always wins.
        ('', 'vi', 'en', 'vi'),  # No preference: the episode's running language beats the newest conversation tag.
        ('', '', 'vi', 'vi'),  # First moment: the conversation's dominant language.
        ('', '', 'multi', 'en'),  # A sentinel tag counts as unset.
        ('', '', None, 'en'),
    ],
)
def test_episode_resolution_order(preference, stored, conversation, expected):
    episode = {'output_language': stored} if stored else {}
    assert (
        episode_language.resolve_episode_language('uid-lang', episode, conversation, preference=preference) == expected
    )


def test_state_language_answers_from_the_stamp_or_detects_the_text():
    assert episode_language.state_language({'output_language': 'vi', 'title': 'anything'}) == 'vi'
    vietnamese = {'title': 'Trao đổi công việc', 'bullets': ['Hẹn ăn trưa lúc 12:30', 'Đặt bàn cho nhóm']}
    assert episode_language.state_language(vietnamese) == 'vi'
    assert episode_language.state_language({'title': '', 'bullets': []}) == ''


def test_repair_instruction_names_both_languages_and_keeps_names():
    directive = episode_language.repair_instruction('vi', 'en')
    assert 'written in vi' in directive and 'in en' in directive and 'verbatim' in directive


def test_the_pin_is_a_kill_switch_on_by_default(monkeypatch):
    assert episodes_config.episode_output_language_pinned() is True
    monkeypatch.setenv(episodes_config.EPISODE_OUTPUT_LANGUAGE_PIN_ENV, 'off')
    assert episodes_config.episode_output_language_pinned() is False
    monkeypatch.setenv(episodes_config.EPISODE_OUTPUT_LANGUAGE_PIN_ENV, 'not-a-word')
    assert episodes_config.episode_output_language_pinned() is True


def test_run_incremental_update_pins_the_resolved_language_by_default(monkeypatch):
    monkeypatch.setattr(users_db, 'get_user_language_preference', lambda *_args: 'en')
    seen = []

    def invoke(uid, messages):
        seen.append(messages)
        return Mock(content='{"title": "Lunch", "bullets": ["A"]}', usage_metadata=None)

    incremental.run_incremental_update(
        'uid-lang', '{}', 'Owner: một khoảnh khắc tiếng Việt', known_item_ids=[], now=NOW, tz_name='UTC', invoke=invoke
    )
    assert seen[0][0] == ('system', incremental._moment_prompt('en'))


def test_the_kill_switch_restores_the_cohort_gated_prompt(monkeypatch):
    monkeypatch.setenv(episodes_config.EPISODE_OUTPUT_LANGUAGE_PIN_ENV, 'off')
    monkeypatch.delenv('NOTES_PACKET_V2_MODE', raising=False)
    monkeypatch.delenv('NOTES_PACKET_V2_MODE_SERVE_PERCENT', raising=False)
    monkeypatch.delenv('NOTES_PACKET_V2_MODE_SERVE_UID_SHA256S', raising=False)
    seen = []

    def invoke(uid, messages):
        seen.append(messages)
        return Mock(content='{"title": "Lunch", "bullets": ["A"]}', usage_metadata=None)

    incremental.run_incremental_update(
        'uid-lang', '{}', 'Owner: x', known_item_ids=[], now=NOW, tz_name='UTC', invoke=invoke
    )
    assert seen[0][0] == ('system', incremental.PROMPT_PREFIX)
    monkeypatch.setenv('NOTES_PACKET_V2_MODE', 'serve')
    incremental.run_incremental_update(
        'uid-lang', '{}', 'Owner: x', known_item_ids=[], now=NOW, tz_name='UTC', invoke=invoke
    )
    assert seen[1][0] == ('system', incremental._moment_prompt('en'))


def test_build_messages_carries_the_repair_line_in_the_volatile_block():
    messages = incremental.build_messages(
        '{"topic":"A"}',
        'Owner: x',
        now=NOW,
        tz_name='UTC',
        output_language='en',
        repair_instruction=episode_language.repair_instruction('vi', 'en'),
    )
    body = messages[1][1]
    assert (
        body.index('Local time now:')
        < body.index('written in vi')
        < body.index('Episode state so far')
        < body.index('Newest moment')
    )
    assert messages[0][1] == incremental._moment_prompt('en')
