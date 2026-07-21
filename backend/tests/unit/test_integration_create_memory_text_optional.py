"""Regression: an integration may create memories from an explicit list, with no source text.

ExternalIntegrationCreateMemory declared

    text: Optional[str] = Field(description="The original text from which the fact was extracted")

Under Pydantic v2 an Optional annotation does not supply a default, so omitting `default=None`
made `text` REQUIRED. A client posting only `memories` was rejected with 422 before the handler
ran, even though the consumer is written for exactly that case:

    # Extract memories from text if provided
    if memory_data.text and len(memory_data.text.strip()) > 0:

Every sibling field in this model and in ExternalIntegrationMemory carries default=None, so this
was the lone omission rather than a deliberate contract.
"""

import pytest
from pydantic import ValidationError

from models.integrations import ExternalIntegrationCreateMemory


def test_explicit_memories_accepted_without_text():
    payload = ExternalIntegrationCreateMemory(memories=[{'content': 'likes coffee'}])

    assert payload.text is None
    assert payload.memories is not None
    assert payload.memories[0].content == 'likes coffee'


def test_text_still_accepted_when_provided():
    payload = ExternalIntegrationCreateMemory(text='some source text')

    assert payload.text == 'some source text'


def test_text_rejects_a_wrong_type():
    # Optional must not become permissive: a non-string is still a validation error.
    with pytest.raises(ValidationError):
        ExternalIntegrationCreateMemory(text=123)
