from __future__ import annotations

import pytest

from utils.llm import chat
from utils.llm.chat import ExtractedInformation


class FakeParser:
    def __init__(self, response):
        self.response = response

    def invoke(self, prompt):
        return self.response


class FakeLLM:
    def __init__(self, response):
        self.response = response

    def with_structured_output(self, output_model):
        return FakeParser(self.response)


@pytest.fixture
def stored_items(monkeypatch):
    stored = []

    def fake_get_llm(feature):
        response = ExtractedInformation(
            people=['New York City!', 'John Patrick Doe'],
            topics=['Artificial Intelligence Research', 'the great big topic'],
            entities=['Bank of America', 'Natural Language Processing'],
            dates=[],
        )
        return FakeLLM(response)

    monkeypatch.setattr(chat, 'get_llm', fake_get_llm)
    monkeypatch.setattr(chat, 'add_filter_category_item', lambda uid, cat, item: stored.append((cat, item)))
    return stored


def test_stored_filters_are_normalized_at_storage_boundary(monkeypatch, stored_items) -> None:
    metadata = chat._process_extracted_metadata('uid-1', prompt='ignored', reference_date='2026-08-16')

    assert metadata['people'] == ['new york city', 'john patrick doe']
    assert metadata['topics'] == ['ai research', 'great big topic']
    assert metadata['entities'] == ['bank america', 'nlp']

    assert sorted(stored_items) == [
        ('entities', 'bank america'),
        ('entities', 'nlp'),
        ('people', 'john patrick doe'),
        ('people', 'new york city'),
        ('topics', 'ai research'),
        ('topics', 'great big topic'),
    ]


@pytest.mark.parametrize(
    'value, expected',
    [
        ('', ''),
        ('   ', ''),
        ('\t\n', ''),
        ('!@#$%', ''),
        ('  Project Apollo Mission  ', 'project apollo mission'),
        ('Artificial Intelligence', 'ai'),
        ('Machine Learning', 'ml'),
        ('Natural Language Processing', 'nlp'),
        ('the great big important topic', 'great big topic'),
        ('Bank of America', 'bank america'),
        ('University of California', 'university california'),
        ("New York City!", 'new york city'),
        ('John Patrick Doe', 'john patrick doe'),
        ('Martin Luther King', 'martin luther king'),
        ('John Michael Patrick Doe', 'john michael doe'),
        ('東京の会議', '東京の会議'),
        ('José Álvarez', 'josé álvarez'),
        ('Jean-Luc Picard', 'jean-luc picard'),
        ('COVID-19', 'covid-19'),
    ],
)
def test_normalize_filter(value, expected):
    assert chat.normalize_filter(value) == expected
