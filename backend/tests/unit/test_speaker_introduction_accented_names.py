import os
import sys
from unittest.mock import MagicMock
import pytest

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

# Mock deepgram if not installed so speaker_identification can be imported hermetically
if "deepgram" not in sys.modules:
    sys.modules["deepgram"] = MagicMock()

from utils.speaker_identification import detect_speaker_from_text, detect_speaker_introduction


def test_accented_latin_and_cyrillic_names_detected():
    test_cases = [
        # (input_text, expected_name, expected_explicit)
        ("Me llamo José", "José", True),
        ("Soy José", "José", False),
        ("José es mi nombre", "José", True),
        ("Ich heiße Jürgen", "Jürgen", True),
        ("Ich bin Jürgen", "Jürgen", False),
        ("Je m'appelle Hélène", "Hélène", True),
        ("Je m'appelle Émile", "Émile", True),
        ("Je suis Hélène", "Hélène", False),
        ("Nazywam się Łukasz", "Łukasz", True),
        ("Jestem Łukasz", "Łukasz", False),
        ("Jag heter Åsa", "Åsa", True),
        ("Jeg heter Øystein", "Øystein", True),
        ("Jeg hedder Søren", "Søren", True),
        ("Mă numesc Ștefan", "Ștefan", True),
        ("Benim adım Özgür", "Özgür", True),
        ("Jmenuji se Šárka", "Šárka", True),
        ("Tên tôi là Đức", "Đức", True),
        ("Tên tôi là Nguyễn Văn An", "Nguyễn", True),
        ("My name is Zoë", "Zoë", True),
        ("I'm Renée", "Renée", False),
        ("Renée is my name", "Renée", True),
        ("Меня зовут Фёдор", "Фёдор", True),
        ("Я Пётр", "Пётр", False),
        ("Меня зовут Ёла", "Ёла", True),
        ("László vagyok", "László", False),
        ("A nevem László", "László", True),
    ]

    for text, exp_name, exp_explicit in test_cases:
        detection = detect_speaker_introduction(text)
        assert detection is not None, f"Failed to detect speaker from '{text}'"
        assert detection.name == exp_name, f"Expected name '{exp_name}' for '{text}', got '{detection.name}'"
        assert detection.explicit == exp_explicit, (
            f"Expected explicit={exp_explicit} for '{text}', got {detection.explicit}"
        )


def test_detect_speaker_from_text_accented_names():
    assert detect_speaker_from_text("Me llamo José", language="es") == "José"
    assert detect_speaker_from_text("Ich heiße Jürgen", language="de") == "Jürgen"
    assert detect_speaker_from_text("Je m'appelle Émile", language="fr") == "Émile"
    assert detect_speaker_from_text("Меня зовут Фёдор", language="ru") == "Фёдор"
    assert detect_speaker_from_text("Nazywam się Łukasz", language="pl") == "Łukasz"


def test_lowercase_words_not_detected_as_names():
    assert detect_speaker_introduction("Ich bin müde") is None
    assert detect_speaker_introduction("I am happy") is None
    assert detect_speaker_introduction("Soy rápido") is None
    assert detect_speaker_introduction("Je suis fatigué") is None
