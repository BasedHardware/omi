"""summarize_experience_text must give the model a current-date reference.

When extracting Calendar Events from a text memory, the model needs to know what
"today" is to resolve relative dates ("tomorrow", "next week"); without it, extracted
event dates anchor to the model's training cutoff. The sibling get_message_structure
already grounds this via the message's started_at. This test asserts the current date
reaches the prompt sent to the LLM.
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from datetime import datetime, timezone  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402

import pytz  # noqa: E402

import utils.llm.external_integrations as ext  # noqa: E402


def _capture_prompt(text, **kwargs):
    """Call summarize_experience_text with a mocked LLM and return the prompt it built."""
    captured = {}
    fake_response = MagicMock()
    fake_response.action_items = []

    chain = MagicMock()
    chain.invoke.side_effect = lambda prompt: captured.__setitem__('prompt', prompt) or fake_response
    llm = MagicMock()
    llm.with_structured_output.return_value = chain

    with patch.object(ext, 'get_llm', return_value=llm):
        ext.summarize_experience_text(text, **kwargs)
    return captured['prompt']


def test_summarize_experience_grounds_prompt_in_current_date():
    prompt = _capture_prompt('I have a dentist appointment tomorrow')
    assert 'today is' in prompt.lower()
    # No timezone passed -> anchor to today's UTC date, labeled UTC.
    assert datetime.now(timezone.utc).strftime('%Y-%m-%d') in prompt
    assert '(UTC)' in prompt


def test_summarize_experience_uses_provided_timezone():
    prompt = _capture_prompt('dentist tomorrow', tz='Asia/Tokyo')
    # The anchor date is computed in the user's timezone, which can differ from UTC near midnight.
    assert datetime.now(pytz.timezone('Asia/Tokyo')).strftime('%Y-%m-%d') in prompt
    assert 'Asia/Tokyo' in prompt


def test_summarize_experience_falls_back_to_utc_on_invalid_timezone():
    prompt = _capture_prompt('dentist tomorrow', tz='Not/ARealZone')
    assert datetime.now(timezone.utc).strftime('%Y-%m-%d') in prompt
    assert '(UTC)' in prompt
