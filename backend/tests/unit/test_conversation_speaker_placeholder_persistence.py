"""Legacy summary writers must never persist Speaker N placeholders (SCA-395).

`sanitize_structured_speaker_placeholders` (#12503) only ran inside the v2 note
path (`get_conversation_notes`). At the time, prod ran `CONVERSATION_NOTES_V2_ENABLED=false`,
so the legacy writers produced most summaries — and could persist
`Speaker 1` / `SPEAKER_00` verbatim. The legacy structure writers are retired; the
action-item extractor below remains. Speaker N is a diarization placeholder that
is not stable across conversations; it must never reach the saved Structured.

Each test drives the real writer with a mocked LLM chain whose response carries
placeholder tokens with NO calendar context, then asserts the returned model is
clean. Red on origin/main before the sanitizer call was added to these writers.
"""

import re
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# firebase_admin reaches google.auth.credentials lazily; same guard as test_conversation_notes_v2.
import google.auth.credentials  # noqa: F401

from testing.import_isolation import stub_modules


@pytest.fixture(scope='module', autouse=True)
def isolated_imports():
    with stub_modules({}):
        # Import the production module under test inside the isolation context.
        import utils.llm.conversation_processing  # noqa: F401

        yield


_SPEAKER_LEFTOVER = re.compile(r'(?i)\b(?:speaker[ _]\d+|SPEAKER_\d+)\b')

_STARTED_AT = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)


def _conv_proc():
    from utils.llm import conversation_processing

    return conversation_processing


def _run_with_chain(response, fn, **kwargs):
    """Run a writer end-to-end with the LLM chain mocked to return `response`."""
    conv_proc = _conv_proc()

    mock_chain = MagicMock()
    mock_chain.invoke.return_value = response
    mock_chain.__or__ = MagicMock(return_value=mock_chain)

    mock_llm = MagicMock()
    mock_llm.__or__ = MagicMock(return_value=mock_chain)

    mock_prompt = MagicMock()
    mock_prompt.__or__ = MagicMock(return_value=mock_chain)

    with patch.object(conv_proc, 'get_llm', return_value=mock_llm), patch.object(
        conv_proc, 'ChatPromptTemplate'
    ) as mock_prompt_cls:
        mock_prompt_cls.from_messages.return_value = mock_prompt
        result = fn(**kwargs)

    return result, mock_prompt_cls


def _system_text(mock_prompt_cls):
    parts = []
    for message in mock_prompt_cls.from_messages.call_args[0][0]:
        if isinstance(message, tuple):
            parts.append(message[1])
        else:
            parts.append(str(getattr(message, 'content', message)))
    return '\n'.join(parts)


def test_extract_action_items_strips_speaker_placeholders(monkeypatch):
    from models.structured_extraction import ActionItemsExtraction, ExtractedActionItem

    conv_proc = _conv_proc()
    monkeypatch.setattr(conv_proc, '_should_run_conversation_action_items_shadow', lambda *a, **k: False)

    poisoned = ActionItemsExtraction(
        action_items=[
            ExtractedActionItem(
                description='Follow up with Speaker 1 about SPEAKER_00 budget',
                owner_name='Speaker 1',
                context='Speaker 1: raised the delay',
            )
        ]
    )

    items, _prompt_cls = _run_with_chain(
        poisoned,
        conv_proc.extract_action_items,
        transcript='Speaker 0: Send the budget numbers. Speaker 1: They are late.',
        started_at=_STARTED_AT,
        language_code='en',
        tz='UTC',
    )

    assert len(items) == 1
    assert _SPEAKER_LEFTOVER.search(items[0].description) is None
    assert _SPEAKER_LEFTOVER.search(items[0].context) is None
    assert items[0].owner_name is None
    assert 'budget' in items[0].description.lower()


def test_legacy_prompts_forbid_placeholders_unconditionally(monkeypatch):
    """The prompt rule must not be gated on calendar context (the #12503 leak)."""
    conv_proc = _conv_proc()
    monkeypatch.setattr(conv_proc, '_should_run_conversation_action_items_shadow', lambda *a, **k: False)

    common = dict(
        transcript='Speaker 0: Send the budget. Speaker 1: It is late.',
        started_at=_STARTED_AT,
        language_code='en',
        tz='UTC',
    )

    from models.structured_extraction import ActionItemsExtraction

    _result, actions_cls = _run_with_chain(
        ActionItemsExtraction(action_items=[]), conv_proc.extract_action_items, **common
    )
    actions_text = _system_text(actions_cls)
    assert 'when participant names are available' not in actions_text
    assert 'with or without calendar context' in actions_text
