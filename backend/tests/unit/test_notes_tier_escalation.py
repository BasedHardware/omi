"""Screen-volume gate for shaped notes effort. Default off; foreground deadline unchanged."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
from types import SimpleNamespace

import pytest

import google.auth.credentials  # noqa: F401

from utils.llm.conversation_prompt_context import ConversationPromptPrefix
from utils.llm.meeting_notes_rich_prompts import NotesFrameImage
from utils.llm.model_config import FOREGROUND_REQUEST_TIMEOUT_SECONDS

_NOTE = (
    '{"title":"Design review","overview":"The team compared the two layouts.",'
    '"emoji":"📝","category":"work","sections":[],"action_items":[],"events":[]}'
)
_STARTED = datetime(2026, 10, 9, 15, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _passthrough_notes_transport(monkeypatch):
    @asynccontextmanager
    async def _passthrough(model):
        yield model

    monkeypatch.setattr(
        'utils.llm.conversation_processing.isolated_notes_model',
        _passthrough,
    )


@pytest.fixture(autouse=True)
def _shaped_notes(monkeypatch):
    monkeypatch.setenv('OMI_SHAPED_AGENT_MODE', 'on')
    monkeypatch.delenv('NOTES_TIER_ESCALATION_ENABLED', raising=False)


class _Model:
    def __init__(self, name: str, *, allow_bind: bool):
        self.model_name = name
        self.allow_bind = allow_bind
        self.bound_kwargs = None
        self.invocations = 0

    def bind(self, **kwargs):
        if not self.allow_bind:
            raise AssertionError(f'unsupported model was rebound: {kwargs}')
        self.bound_kwargs = kwargs
        parent = self

        class _Bound:
            async def ainvoke(self, messages):
                parent.invocations += 1
                return SimpleNamespace(content=_NOTE)

        return _Bound()

    async def ainvoke(self, messages):
        self.invocations += 1
        return SimpleNamespace(content=_NOTE)


def _words(count: int, token: str = 'word') -> str:
    return ' '.join([token] * count)


def _frames(count: int) -> tuple[NotesFrameImage, ...]:
    return tuple(
        NotesFrameImage(frame_id=f'f{index}', offset_label=f'{index}s', data_url='data:image/png;base64,AA')
        for index in range(count)
    )


def _prefix(words: int, *, shaped_context: str | None = None, context: str | None = None) -> ConversationPromptPrefix:
    return ConversationPromptPrefix(
        conversation_id='conv-tier',
        context=context if context is not None else 'unused preamble',
        shaped_context=shaped_context if shaped_context is not None else _words(words),
        has_usable_content=True,
    )


def _receipt_fields(caplog) -> dict[str, str]:
    lines = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith('conversation_notes_receipt ')
    ]
    assert len(lines) == 1
    return dict(part.split('=', 1) for part in lines[0].split() if '=' in part)


def _run(monkeypatch, caplog, prefix, screens: int, *, model: _Model):
    from utils.llm import conversation_processing

    captured = {}

    def fake_get_llm(feature, **kwargs):
        captured['feature'] = feature
        captured['request_timeout'] = kwargs.get('request_timeout')
        return model

    monkeypatch.setattr(conversation_processing, 'get_llm', fake_get_llm)
    caplog.set_level(logging.INFO, logger='utils.llm.notes_observability')
    result = conversation_processing.get_conversation_notes(
        prefix,
        started_at=_STARTED,
        language_code='en',
        output_language_code='en',
        tz='UTC',
        task_intelligence_capture=False,
        screen_frames=_frames(screens),
    )
    assert result.title == 'Design review'
    assert captured['feature'] == 'conv_structure'
    assert captured['request_timeout'] == conversation_processing.CONVERSATION_STRUCTURE_TIMEOUT_SECONDS
    assert captured['request_timeout'] == FOREGROUND_REQUEST_TIMEOUT_SECONDS
    assert model.invocations == 1
    return _receipt_fields(caplog)


@pytest.mark.parametrize(
    ('words', 'screens', 'flag', 'escalated', 'reason'),
    [
        pytest.param(1499, 5, 'true', False, 'below_threshold', id='words-just-below'),
        pytest.param(1500, 4, 'true', False, 'below_threshold', id='screens-just-below'),
        pytest.param(5000, 0, 'true', False, 'below_threshold', id='long-without-screens'),
        pytest.param(1500, 5, 'true', True, 'screen_volume', id='exact-threshold'),
        pytest.param(1501, 6, 'true', True, 'screen_volume', id='above-threshold'),
        pytest.param(1500, 5, 'false', False, 'below_threshold', id='flag-false'),
        pytest.param(1500, 5, None, False, 'below_threshold', id='flag-unset'),
        pytest.param(1500, 5, 'maybe', False, 'below_threshold', id='flag-unknown'),
    ],
)
def test_screen_volume_gate(monkeypatch, caplog, words, screens, flag, escalated, reason):
    if flag is None:
        monkeypatch.delenv('NOTES_TIER_ESCALATION_ENABLED', raising=False)
    else:
        monkeypatch.setenv('NOTES_TIER_ESCALATION_ENABLED', flag)
    model = _Model('openai/gpt-5.6-luna', allow_bind=escalated)
    fields = _run(monkeypatch, caplog, _prefix(words), screens, model=model)
    assert fields['escalated'] == ('true' if escalated else 'false')
    assert fields['escalation_reason'] == reason
    assert fields['words'] == str(words)
    assert fields['screen_count'] == str(screens)
    assert fields['arm'] == 'baseline'
    assert fields['selection'] == 'none'
    assert fields['claims_enabled'] == 'False'
    if escalated:
        assert model.bound_kwargs == {'reasoning_effort': 'xhigh'}
        assert fields['effort'] == 'xhigh'
        assert fields['requested_effort'] == 'xhigh'
    else:
        assert model.bound_kwargs is None
        assert fields['effort'] == 'default'
        assert fields['requested_effort'] == 'default'


def test_word_count_uses_shaped_context_when_present(monkeypatch, caplog):
    monkeypatch.setenv('NOTES_TIER_ESCALATION_ENABLED', 'true')
    prefix = _prefix(0, shaped_context=_words(10), context=_words(2000, 'speech'))
    model = _Model('openai/gpt-5.6-luna', allow_bind=False)
    fields = _run(monkeypatch, caplog, prefix, 5, model=model)
    assert fields['words'] == '10'
    assert fields['screen_count'] == '5'
    assert fields['escalated'] == 'false'
    assert fields['escalation_reason'] == 'below_threshold'
    assert model.bound_kwargs is None


def test_word_count_uses_the_transcript_section_of_prefix_context(monkeypatch, caplog):
    monkeypatch.setenv('NOTES_TIER_ESCALATION_ENABLED', 'true')
    preamble = _words(20, 'preamble')
    body = _words(1498)
    prefix = ConversationPromptPrefix(
        conversation_id='conv-tier',
        context=f'{preamble}\nFULL TRANSCRIPT\n{body}',
        shaped_context=None,
        has_usable_content=True,
    )
    model = _Model('openai/gpt-5.6-luna', allow_bind=True)
    fields = _run(monkeypatch, caplog, prefix, 5, model=model)
    assert fields['words'] == '1500'
    assert fields['escalated'] == 'true'
    assert fields['escalation_reason'] == 'screen_volume'
    assert model.bound_kwargs == {'reasoning_effort': 'xhigh'}


def test_byok_model_keeps_its_options_and_records_effort_unsupported(monkeypatch, caplog):
    monkeypatch.setenv('NOTES_TIER_ESCALATION_ENABLED', 'true')
    model = _Model('vendor/claude-sonnet', allow_bind=False)
    fields = _run(monkeypatch, caplog, _prefix(1500), 5, model=model)
    assert model.bound_kwargs is None
    assert fields['escalated'] == 'true'
    assert fields['escalation_reason'] == 'screen_volume'
    assert fields['words'] == '1500'
    assert fields['screen_count'] == '5'
    assert fields['effort'] == 'default'
    assert fields['requested_effort'] == 'xhigh'
    assert 'effort_unsupported_model' in fields['violations'].split(',')


def test_receipt_includes_escalation_fields_below_threshold(monkeypatch, caplog):
    monkeypatch.setenv('NOTES_TIER_ESCALATION_ENABLED', 'true')
    model = _Model('openai/gpt-5.6-luna', allow_bind=False)
    fields = _run(monkeypatch, caplog, _prefix(1499), 5, model=model)
    assert fields['escalated'] == 'false'
    assert fields['escalation_reason'] == 'below_threshold'
    assert fields['words'] == '1499'
    assert fields['screen_count'] == '5'
    assert fields['violations'] == 'none'
