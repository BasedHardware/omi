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

import utils.llm.external_integrations as ext  # noqa: E402


def test_summarize_experience_grounds_prompt_in_current_date():
    captured = {}
    fake_response = MagicMock()
    fake_response.action_items = []

    chain = MagicMock()
    chain.invoke.side_effect = lambda prompt: captured.__setitem__('prompt', prompt) or fake_response
    llm = MagicMock()
    llm.with_structured_output.return_value = chain

    with patch.object(ext, 'get_llm', return_value=llm):
        ext.summarize_experience_text('I have a dentist appointment tomorrow')

    prompt = captured['prompt']
    assert 'today is' in prompt.lower()
    assert datetime.now(timezone.utc).strftime('%Y-%m-%d') in prompt
