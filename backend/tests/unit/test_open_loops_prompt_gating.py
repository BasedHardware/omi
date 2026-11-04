"""OPEN_LOOPS_ENABLED gates the notes prompt bytes and the extraction sink.

On: the one-shot instructions carry the open-loop rules and schema, and a
fresh parse lands in the mutable sink the pipeline persists. Off: the prompt
carries neither (byte-identical to the pre-feature contract — the fields live
on schema subclasses the flag-off path never parses) and the sink stays empty.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import google.auth.credentials  # noqa: F401

from utils.llm.conversation_prompt_context import ConversationPromptPrefix

_NOTE_WITH_LOOPS = '''{
"title":"Vendor sync","overview":"Maya will send the write-up.","emoji":"📝","category":"work",
"sections":[],"action_items":[],"events":[],
"delegated_by_user":[{"who":"Maya","what":"send the vendor write-up","by_when":null,
"evidence":"I will send it over tomorrow","work_related":true}],
"commitments_by_others":[],
"observed_issue_or_blocker":{"kind":"work_defect","what":"File the login-screen crash bug",
"by_when":null,"evidence":"crash shown during the call","work_related":true}}'''
_STARTED = datetime(2026, 10, 23, 15, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _one_shot_notes_transport(monkeypatch):
    @asynccontextmanager
    async def _passthrough(model):
        yield model

    monkeypatch.setattr('utils.llm.conversation_processing.isolated_notes_model', _passthrough)
    monkeypatch.setenv('OMI_SHAPED_AGENT_MODE', 'on')
    monkeypatch.delenv('OPEN_LOOPS_ENABLED', raising=False)


class _CaptureModel:
    model_name = 'openai/gpt-5.6-luna'

    def __init__(self, content: str):
        self.content = content
        self.messages = None

    async def ainvoke(self, messages):
        self.messages = messages
        return SimpleNamespace(content=self.content)


def _run(monkeypatch, *, sink=None):
    from utils.llm import conversation_processing

    model = _CaptureModel(_NOTE_WITH_LOOPS)
    monkeypatch.setattr(conversation_processing, 'get_llm', lambda *a, **k: model)
    sink = {} if sink is None else sink
    result = conversation_processing.get_conversation_notes(
        ConversationPromptPrefix(
            conversation_id='conv-open-loops',
            context='FULL TRANSCRIPT\nMaya will send the write-up. The login screen crashed.',
            shaped_context='Maya will send the write-up. The login screen crashed.',
            has_usable_content=True,
        ),
        started_at=_STARTED,
        language_code='en',
        output_language_code='en',
        tz='UTC',
        task_intelligence_capture=False,
        open_loop_out=sink,
    )
    assert result.title == 'Vendor sync'
    blocks = []
    for message in model.messages:
        if not (isinstance(message, dict) and message.get('role') == 'system'):
            continue
        content = message.get('content')
        if isinstance(content, str):
            blocks.append(content)
        elif isinstance(content, list):
            blocks.extend(part.get('text', '') for part in content if isinstance(part, dict))
    instructions = '\n'.join(blocks)
    return instructions, sink


def test_enabled_appends_rules_and_captures_extraction(monkeypatch):
    instructions, sink = _run(monkeypatch)
    assert 'OPEN LOOP EXTRACTION RULES' in instructions
    assert 'delegated_by_user' in instructions  # the parser schema carries the fields
    assert 'ACTION ITEM EXTRACTION RULES' in instructions  # undisturbed
    payload = sink['extractions']
    assert payload['delegated_by_user'][0]['who'] == 'Maya'
    assert payload['observed_issue_or_blocker']['kind'] == 'work_defect'


def test_disabled_keeps_prompt_bytes_and_sink_untouched(monkeypatch):
    monkeypatch.setenv('OPEN_LOOPS_ENABLED', 'off')
    instructions, sink = _run(monkeypatch)
    assert 'OPEN LOOP EXTRACTION RULES' not in instructions
    assert 'delegated_by_user' not in instructions
    assert 'commitments_by_others' not in instructions
    assert 'observed_issue_or_blocker' not in instructions
    # The flag-off schema ignores the fields, and nothing is captured to persist.
    assert sink == {}


def test_enabled_with_empty_result_records_clearing_null(monkeypatch):
    empty_note = _NOTE_WITH_LOOPS.replace(
        _NOTE_WITH_LOOPS[_NOTE_WITH_LOOPS.index('"delegated_by_user"') :],
        '"delegated_by_user":[],"commitments_by_others":[],"observed_issue_or_blocker":null}',
    )
    from utils.llm import conversation_processing

    model = _CaptureModel(empty_note)
    monkeypatch.setattr(conversation_processing, 'get_llm', lambda *a, **k: model)
    sink: dict = {}
    conversation_processing.get_conversation_notes(
        ConversationPromptPrefix(
            conversation_id='conv-open-loops-empty',
            context='FULL TRANSCRIPT\nsmall talk',
            shaped_context='small talk',
            has_usable_content=True,
        ),
        started_at=_STARTED,
        language_code='en',
        output_language_code='en',
        tz='UTC',
        task_intelligence_capture=False,
        open_loop_out=sink,
    )
    assert sink == {'extractions': None}


def test_switch_values():
    from config.open_loops import card_polish_enabled, open_loops_enabled

    assert open_loops_enabled({}) is True  # ship-on-by-default
    assert open_loops_enabled({'OPEN_LOOPS_ENABLED': 'false'}) is False
    assert open_loops_enabled({'OPEN_LOOPS_ENABLED': '0'}) is False
    assert open_loops_enabled({'OPEN_LOOPS_ENABLED': 'off'}) is False
    assert open_loops_enabled({'OPEN_LOOPS_ENABLED': 'on'}) is True
    assert open_loops_enabled({'OPEN_LOOPS_ENABLED': 'nonsense'}) is True  # on unless set off

    assert card_polish_enabled({}) is False
    assert card_polish_enabled({'OPEN_LOOPS_CARD_POLISH_ENABLED': 'true'}) is True
