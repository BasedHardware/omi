"""Notes must survive the unescaped prose quotes the structure model returns.

Prod raised OutputParserException from langchain json.py:91 on a completion
starting `{"title": "Fish identification", "overview": ...}`. A quoted phrase
inside a string had no backslashes, so the strict parser dropped the summary.
"""

import pytest
from langchain_core.exceptions import OutputParserException
from langchain_core.output_parsers import PydanticOutputParser

from models.structured_extraction import StructuredExtraction
from utils.llm.conversation_processing import _parse_notes_model_output


def _parser() -> PydanticOutputParser:
    return PydanticOutputParser(pydantic_object=StructuredExtraction)


def test_unescaped_prose_quotes_parse_as_part_of_the_string():
    parsed = _parse_notes_model_output(
        _parser(),
        '{"title": "Fish identification", "overview": "User asked "what fish?" today"}',
    )

    assert parsed.title == 'Fish identification'
    assert parsed.overview == 'User asked "what fish?" today'


def test_unescaped_quotes_inside_a_section_body_parse():
    parsed = _parse_notes_model_output(
        _parser(),
        '{"title": "Fish identification", "sections": [{"heading": "Look", "body_markdown": "He said "hi" there"}]}',
    )

    assert parsed.sections[0].body_markdown == 'He said "hi" there'


def test_valid_and_already_escaped_json_round_trips():
    parsed = _parse_notes_model_output(
        _parser(),
        '{"title": "Fish identification", "overview": "already \\"quoted\\""}',
    )

    assert parsed.overview == 'already "quoted"'


def test_a_missing_comma_still_raises():
    with pytest.raises(OutputParserException):
        _parse_notes_model_output(_parser(), '{"title": "a" "overview": "b"}')
