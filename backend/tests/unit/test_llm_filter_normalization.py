import pytest

from utils.llm.chat import normalize_filter


@pytest.mark.parametrize(
    'value, expected',
    [
        ('', ''),
        ('   ', ''),
        ('\t\n', ''),
        ('!@#$%', ''),
        ('  Project Apollo Mission  ', 'project apollo'),
        ('Artificial Intelligence', 'ai'),
        ('Machine Learning', 'ml'),
        ('Natural Language Processing', 'nlp'),
        ('the great big important topic', 'great big'),
        ('Bank of America', 'bank america'),
        ('University of California', 'university california'),
        ("New York City!", 'new york'),
    ],
)
def test_normalize_filter(value, expected):
    assert normalize_filter(value) == expected
