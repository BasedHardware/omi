import os
import sys
from unittest.mock import MagicMock

# Mock heavy dependencies before importing the module under test.
# These modules pull in Firebase / Google Cloud clients at import time.
# NOTE: utils.speaker_identification_names is intentionally NOT mocked --
# it is a pure-Python frozenset used by the gazetteer phase.
for mod in [
    'database',
    'database.conversations',
    'database.users',
    'utils.other',
    'utils.other.storage',
    'utils.speaker_sample',
    'utils.speaker_sample_migration',
    'utils.stt',
    'utils.stt.speaker_embedding',
]:
    sys.modules[mod] = MagicMock()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from utils.speaker_identification import detect_speaker_from_text

# ---------------------------------------------------------------------------
# Phase 1 -- regex-based detection (capitalised / mixed-case input)
# ---------------------------------------------------------------------------


def test_regex_im_name():
    assert detect_speaker_from_text("I'm Alice") == 'Alice'


def test_regex_my_name_is():
    assert detect_speaker_from_text('My name is Bob') == 'Bob'


def test_regex_i_am():
    assert detect_speaker_from_text('I am Charlie') == 'Charlie'


def test_regex_name_is_my_name():
    assert detect_speaker_from_text('Alice is my name') == 'Alice'


def test_regex_this_is():
    assert detect_speaker_from_text('This is Bob') == 'Bob'


def test_regex_hey_its():
    assert detect_speaker_from_text("Hey, it's Charlie") == 'Charlie'


def test_regex_call_me():
    assert detect_speaker_from_text('Call me Dave') == 'Dave'


def test_regex_you_can_call_me():
    assert detect_speaker_from_text('You can call me Eve') == 'Eve'


def test_regex_youre_speaking_with():
    assert detect_speaker_from_text("You're speaking with Sarah") == 'Sarah'


def test_regex_the_names():
    assert detect_speaker_from_text("The name's Bond") == 'Bond'


def test_regex_multi_word_name():
    # .capitalize() lowercases everything after the first character of the
    # matched group, so 'John Smith' becomes 'John smith'.
    assert detect_speaker_from_text("I'm John Smith") == 'John smith'


# Non-English patterns -------------------------------------------------------


def test_regex_french_je_suis():
    assert detect_speaker_from_text('Je suis Pierre') == 'Pierre'


def test_regex_german_ich_bin():
    assert detect_speaker_from_text('ich bin Hans') == 'Hans'


def test_regex_spanish_me_llamo():
    assert detect_speaker_from_text('Me llamo Carlos') == 'Carlos'


# ---------------------------------------------------------------------------
# Phase 2 -- gazetteer detection (handles lowercased ASR output)
# ---------------------------------------------------------------------------


def test_gazetteer_lowercased_this_is():
    assert detect_speaker_from_text('this is bob') == 'Bob'


def test_gazetteer_lowercased_im():
    assert detect_speaker_from_text("i'm alice") == 'Alice'


def test_gazetteer_lowercased_my_name_is():
    assert detect_speaker_from_text('my name is charlie') == 'Charlie'


def test_gazetteer_lowercased_call_me():
    assert detect_speaker_from_text('call me dave') == 'Dave'


def test_gazetteer_suffix_here():
    assert detect_speaker_from_text('bob here') == 'Bob'


def test_gazetteer_suffix_speaking():
    assert detect_speaker_from_text('alice speaking') == 'Alice'


def test_gazetteer_lowercased_hey_its():
    assert detect_speaker_from_text("hey, it's sarah") == 'Sarah'


# ---------------------------------------------------------------------------
# Negative cases -- should return None
# ---------------------------------------------------------------------------


def test_negative_common_word_not_a_name():
    assert detect_speaker_from_text('This is important') is None


def test_negative_day_name_not_in_gazetteer():
    assert detect_speaker_from_text('Monday here') is None


def test_negative_name_without_intro_context():
    assert detect_speaker_from_text('Alice said the project is late') is None


def test_negative_empty_string():
    assert detect_speaker_from_text('') is None


def test_negative_hello_world():
    assert detect_speaker_from_text('Hello world') is None


def test_negative_no_intro_pattern():
    assert detect_speaker_from_text('The weather is nice today') is None
