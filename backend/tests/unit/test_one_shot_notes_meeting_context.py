"""The one-shot notes evidence carries the meeting background and owner corrections.

The agentic writer receives the same block as ``background`` (notes_agent_serving
build_packet); before this seam existed, one-shot notes — short meetings, BYOK,
capability mismatch — silently dropped both the background pack and every
owner-confirmed correction whenever the agent lane was unavailable.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import json

import pytest

import google.auth.credentials  # noqa: F401

from utils.llm.conversation_prompt_context import ConversationPromptPrefix

_NOTE = (
    '{"title":"Design review","overview":"The team compared the two layouts.",'
    '"emoji":"📝","category":"work","sections":[],"action_items":[],"events":[]}'
)
_STARTED = datetime(2026, 10, 23, 15, 0, tzinfo=timezone.utc)
_BACKGROUND = """BACKGROUND CONTEXT
- Prior meeting: shipping the notes context fixes (2026-10-20)

Owner-confirmed corrections (use these facts in the title and summary; do not rewrite the transcript):
Her name is Maria, not Marie."""
_CORRECTIONS_ONLY = (
    '\nOwner-confirmed corrections (use these facts in the title and summary; '
    'do not rewrite the transcript):\nWe decided Friday, not Thursday.'
)


@pytest.fixture(autouse=True)
def _one_shot_notes_transport(monkeypatch):
    @asynccontextmanager
    async def _passthrough(model):
        yield model

    monkeypatch.setattr('utils.llm.conversation_processing.isolated_notes_model', _passthrough)
    monkeypatch.setenv('OMI_SHAPED_AGENT_MODE', 'on')


class _CaptureModel:
    model_name = 'openai/gpt-5.6-luna'

    def __init__(self):
        self.messages = None

    async def ainvoke(self, messages):
        self.messages = messages
        return SimpleNamespace(content=_NOTE)


def _evidence_json(monkeypatch, **extra) -> dict:
    from utils.llm import conversation_processing

    model = _CaptureModel()
    monkeypatch.setattr(conversation_processing, 'get_llm', lambda *a, **k: model)
    result = conversation_processing.get_conversation_notes(
        ConversationPromptPrefix(
            conversation_id='conv-one-shot',
            context='FULL TRANSCRIPT\nhello there',
            shaped_context='hello there',
            has_usable_content=True,
        ),
        started_at=_STARTED,
        language_code='en',
        output_language_code='en',
        tz='UTC',
        task_intelligence_capture=False,
        **extra,
    )
    assert result.title == 'Design review'  # the one-shot call ran and won
    # run_loop sends the mount instructions first; the evidence JSON is the user message.
    user_contents = [
        message['content']
        for message in model.messages
        if isinstance(message, dict) and message.get('role') == 'user' and isinstance(message.get('content'), str)
    ]
    evidence = next(content for content in user_contents if '"capture_evidence"' in content)
    return json.loads(evidence)


def test_meeting_context_rides_the_one_shot_evidence(monkeypatch):
    packet = _evidence_json(monkeypatch, meeting_context=_BACKGROUND)
    assert packet['meeting_context'] == _BACKGROUND
    assert 'Owner-confirmed corrections' in packet['meeting_context']


def test_corrections_only_still_ride_without_a_background_pack(monkeypatch):
    packet = _evidence_json(monkeypatch, meeting_context=_CORRECTIONS_ONLY)
    assert packet['meeting_context'] == _CORRECTIONS_ONLY


def test_no_meeting_context_means_no_key(monkeypatch):
    packet = _evidence_json(monkeypatch)
    assert 'meeting_context' not in packet


def test_empty_meeting_context_means_no_key(monkeypatch):
    packet = _evidence_json(monkeypatch, meeting_context='')
    assert 'meeting_context' not in packet
