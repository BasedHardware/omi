"""Cached instruction prefixes must stay byte-identical across per-call inputs.

chat_agent keeps dates out of the cached system prefix and hits ~48%. Notes v2
used to mark the unique transcript instead, so conv_structure wrote a prefix
almost no later call could read (3.7%). These tests pin the split: two
invocations that differ in transcript, timezone, or clock must share the same
marked prefix bytes.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import google.auth.credentials  # noqa: F401

from models.app import App
from testing.import_isolation import stub_modules
from utils.llm.prompt_cache import EXPLICIT_CACHE_BREAKPOINT, EXPLICIT_CACHE_MINIMUM_CHARACTERS


@pytest.fixture(scope='module', autouse=True)
def isolated_imports():
    with stub_modules({}):
        import utils.llm.conversation_processing  # noqa: F401
        import utils.llm.conversation_prompt_prefix  # noqa: F401
        import utils.llm.working_observations  # noqa: F401

        yield


def _message_text(message) -> str:
    content = message.content if hasattr(message, 'content') else message['content']
    if isinstance(content, list):
        return ''.join(part.get('text', '') for part in content if isinstance(part, dict))
    return str(content)


def _breakpoint(message):
    content = message.content if hasattr(message, 'content') else message['content']
    if not isinstance(content, list):
        return None
    for part in content:
        if isinstance(part, dict) and 'prompt_cache_breakpoint' in part:
            return part['prompt_cache_breakpoint']
    return None


def _notes_call(monkeypatch, *, transcript: str, started_at: datetime, tz: str, language: str = 'en'):
    from utils.llm import conversation_processing as conv_proc
    from utils.llm.conversation_prompt_prefix import build_conversation_prompt_prefix

    captured: dict = {}

    class Model:
        def invoke(self, messages):
            captured['messages'] = messages
            return SimpleNamespace(
                content=(
                    '{"title":"T","overview":"o","emoji":"🧠","category":"work",'
                    '"sections":[],"action_items":[],"events":[]}'
                )
            )

    def fake_get_llm(_feature, **kwargs):
        captured['kwargs'] = kwargs
        return Model()

    monkeypatch.setattr(conv_proc, 'get_llm', fake_get_llm)
    monkeypatch.setattr(conv_proc, 'shared_conversation_cache_supported', lambda: True)
    monkeypatch.setattr(conv_proc, 'explicit_cache_switch_enabled', lambda: True)
    prefix = build_conversation_prompt_prefix(
        conversation_id=f'conv-{transcript[:8]}',
        transcript=transcript,
        started_at=started_at,
        timezone_name=tz,
        language_code=language,
    )
    conv_proc.get_conversation_notes(
        prefix,
        started_at=started_at,
        language_code=language,
        output_language_code=language,
        tz=tz,
        task_intelligence_capture=True,
    )
    return captured


def test_conv_structure_static_prefix_is_byte_identical_across_per_call_inputs(monkeypatch):
    from utils.llm import conversation_processing as conv_proc

    first = _notes_call(
        monkeypatch,
        transcript='Alice and Bob planned the launch timeline for September.',
        started_at=datetime(2026, 9, 19, 14, 0, tzinfo=timezone.utc),
        tz='America/New_York',
    )
    second = _notes_call(
        monkeypatch,
        transcript='Carla reviewed the budget and asked for a follow-up on Monday.',
        started_at=datetime(2026, 9, 21, 3, 30, tzinfo=timezone.utc),
        tz='Pacific/Honolulu',
        language='fr',
    )

    first_prefix = _message_text(first['messages'][0])
    second_prefix = _message_text(second['messages'][0])

    assert first_prefix == second_prefix
    assert len(first_prefix) >= EXPLICIT_CACHE_MINIMUM_CHARACTERS
    assert _breakpoint(first['messages'][0]) == EXPLICIT_CACHE_BREAKPOINT
    assert _breakpoint(first['messages'][1]) is None
    assert first['kwargs']['cache_key'] == conv_proc.CONVERSATION_NOTES_CACHE_KEY
    assert first['kwargs']['cache_key'] == second['kwargs']['cache_key']

    volatile = _message_text(first['messages'][1])
    assert 'Alice and Bob planned the launch' in volatile
    assert 'Alice and Bob planned the launch' not in first_prefix
    assert '2026-09-19' in volatile
    assert '2026-09-19' not in first_prefix
    assert 'America/New_York' in volatile
    assert 'America/New_York' not in first_prefix
    assert 'Respond entirely in fr' in _message_text(second['messages'][1])
    assert 'Respond entirely in fr' not in second_prefix


def test_memories_static_prefix_is_byte_identical_across_transcripts():
    from utils.llm.conversation_prompt_prefix import ConversationPromptPrefix
    from utils.llm.working_observations import extract_l1_memory_archive_items_from_text

    captured: list = []

    class Model:
        def invoke(self, messages):
            captured.append(messages)
            return SimpleNamespace(content='{"items": []}')

    prefix_a = ConversationPromptPrefix(
        conversation_id='conv-a',
        context='FULL TRANSCRIPT\n[s1 0] we should ship the cache fix on friday',
    )
    prefix_b = ConversationPromptPrefix(
        conversation_id='conv-b',
        context='FULL TRANSCRIPT\n[s9 1] the dentist appointment moved to tuesday',
    )
    extract_l1_memory_archive_items_from_text(
        uid='u1',
        source_id='conv-a',
        source_type='voice_transcript',
        text=prefix_a.context,
        user_name='Alex',
        persist_route_outcomes=False,
        llm=Model(),
        prompt_prefix=prefix_a,
        prompt_cache_enabled=True,
    )
    extract_l1_memory_archive_items_from_text(
        uid='u1',
        source_id='conv-b',
        source_type='voice_transcript',
        text=prefix_b.context,
        user_name='Alex',
        persist_route_outcomes=False,
        llm=Model(),
        prompt_prefix=prefix_b,
        prompt_cache_enabled=True,
    )

    first_prefix = _message_text(captured[0][0])
    second_prefix = _message_text(captured[1][0])
    assert first_prefix == second_prefix
    assert len(first_prefix) >= EXPLICIT_CACHE_MINIMUM_CHARACTERS
    assert _breakpoint(captured[0][0]) == EXPLICIT_CACHE_BREAKPOINT
    assert 'ship the cache fix' not in first_prefix
    assert 'ship the cache fix' in str(captured[0][1:])
    assert 'dentist appointment' not in first_prefix
    assert 'dentist appointment' in str(captured[1][1:])


def test_conv_apps_prefix_path_static_instructions_are_byte_identical_across_conversations(monkeypatch):
    from utils.llm import conversation_processing as conv_proc
    from utils.llm.conversation_prompt_prefix import build_conversation_prompt_prefix

    recorded: list[dict] = []
    long_task = 'summarize the meeting and list every decision. ' * 120

    class RecordingModel:
        def invoke(self, messages):
            recorded.append({'messages': messages, 'kwargs': current['kwargs']})
            return SimpleNamespace(content='summary')

    current: dict = {}

    def _get_llm(_feature, **kwargs):
        current['kwargs'] = kwargs
        return RecordingModel()

    monkeypatch.setattr(conv_proc, 'get_llm', _get_llm)
    monkeypatch.setattr(conv_proc, 'shared_conversation_cache_supported', lambda: True)
    monkeypatch.setattr(conv_proc, 'explicit_cache_switch_enabled', lambda: True)

    app = App(
        id='app-notes',
        name='Meeting Notes',
        category='productivity',
        author='Omi',
        description='notes',
        image='/app.png',
        capabilities={'memories'},
        memory_prompt=long_task,
    )
    for transcript, started_at, language in (
        ('first conversation about hiring', datetime(2026, 9, 19, 10, 0, tzinfo=timezone.utc), 'en'),
        ('second conversation about payroll', datetime(2026, 9, 21, 18, 0, tzinfo=timezone.utc), 'fr'),
    ):
        prefix = build_conversation_prompt_prefix(
            conversation_id=transcript,
            transcript=transcript,
            started_at=started_at,
            timezone_name='UTC',
            language_code=language,
        )
        conv_proc.get_app_result(transcript, [], app, language_code=language, prompt_prefix=prefix)

    first_prefix = _message_text(recorded[0]['messages'][0])
    second_prefix = _message_text(recorded[1]['messages'][0])
    assert first_prefix == second_prefix
    assert len(first_prefix) >= EXPLICIT_CACHE_MINIMUM_CHARACTERS
    assert _breakpoint(recorded[0]['messages'][0]) == EXPLICIT_CACHE_BREAKPOINT
    assert 'first conversation about hiring' not in first_prefix
    assert any('first conversation about hiring' in _message_text(m) for m in recorded[0]['messages'][1:])
    assert 'Respond in fr' not in second_prefix
    assert any('Respond in fr' in _message_text(m) for m in recorded[1]['messages'][1:])
    assert recorded[0]['kwargs']['cache_key'] == recorded[1]['kwargs']['cache_key']
    assert recorded[0]['kwargs']['cache_key'].startswith(conv_proc.APP_RESULT_CACHE_NAMESPACE)
