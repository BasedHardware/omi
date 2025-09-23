import pytest
from utils.speaker_identification import detect_speaker_from_text

@pytest.mark.parametrize("text,lang,expected", [
    # English
    ("Hi, I'm Alice and I'll be your guide today.", "en", "Alice"),
    ("My name is Bob.", "en", "Bob"),
    ("Alice will now explain the next steps.", "en", "Alice"),
    # Spanish
    ("Hola, me llamo Carlos y soy el doctor.", "es", "Carlos"),
    ("Carlos es mi nombre.", "es", "Carlos"),
    # French
    ("Je vous présente Marie, notre experte.", "fr", "Marie"),
    ("Je m'appelle Marie.", "fr", "Marie"),
    # Chinese
    ("王伟会为大家解答问题。", "zh", "王伟"),
    ("我是王伟。", "zh", "王伟"),
    # Negative case
    ("Let's get started with the meeting.", "en", None),
])
def test_detect_speaker_from_text(text, lang, expected):
    result = detect_speaker_from_text(text, lang)
    if expected is None:
        assert result is None
    else:
        assert result is not None
        assert expected in result
