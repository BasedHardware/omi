import os
import sys
from unittest.mock import MagicMock

import pytest

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
    # _normalize_name title-cases each word, so multi-word names round-trip to
    # the same form they're stored as in Person records ('John Smith').
    assert detect_speaker_from_text("I'm John Smith") == 'John Smith'


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


# ---------------------------------------------------------------------------
# Stopword guard -- run-on / garbled transcripts must not leak pronouns or
# fillers as speaker names (would create phantom contacts "It"/"You"/"Them").
# Phase 1 returns on first match, so the guard must live there (#5223).
# ---------------------------------------------------------------------------

STOPWORD_RUNON_CASES = [
    'And I am It was great',
    "I'm You know, the guy",
    "Yeah, I'm Them and the others",
    'My name is It',
    'I am Sorry about that',
    "I'm Just saying",
    'i am Gonna do it',
]


@pytest.mark.parametrize('text', STOPWORD_RUNON_CASES)
def test_stopword_not_leaked_as_name(text):
    assert detect_speaker_from_text(text) is None


def test_real_name_still_detected_after_guard():
    # The guard must reject fillers without suppressing genuine introductions.
    assert detect_speaker_from_text('I am John') == 'John'
    assert detect_speaker_from_text('My name is Alice') == 'Alice'


# ---------------------------------------------------------------------------
# Multi-word name normalization -- title-case every word so the result matches
# how a Person is stored ("John Smith"), not capitalize()'s "John smith".
# ---------------------------------------------------------------------------


def test_multi_word_name_titlecased_this_is():
    assert detect_speaker_from_text('This is John Smith') == 'John Smith'


def test_multi_word_name_titlecased_my_name_is():
    assert detect_speaker_from_text('My name is Sarah Connor') == 'Sarah Connor'


# ---------------------------------------------------------------------------
# Audit round 2 -- phantom-speaker hardening (regex phase)
# ---------------------------------------------------------------------------


# #15 -- multi-word capture must apply the stopword filter per token
@pytest.mark.parametrize(
    'text',
    ['This is It Works', "I'm Not Sure", "I'm So Sorry", "I'm You Know", 'This is It Is Me'],
)
def test_multiword_stopword_bypass_rejected(text):
    assert detect_speaker_from_text(text) is None


# #4 -- Phase 2 gazetteer path must honor the stopword set ('my' is in both)
@pytest.mark.parametrize('text', ['this is my friend', "it's my turn", 'this is my', "hey it's my dog"])
def test_phase2_pronoun_my_rejected(text):
    assert detect_speaker_from_text(text) is None


# #5 -- honorifics/titles are stripped, never returned as the name
def test_honorific_title_stripped():
    assert detect_speaker_from_text("I'm Dr. Smith") == 'Smith'
    assert detect_speaker_from_text('This is Mr. Lee') == 'Lee'
    assert detect_speaker_from_text("I'm Doctor Smith") == 'Smith'
    assert detect_speaker_from_text('This is Mrs. Johnson') == 'Johnson'


# #3 -- suffix cues ('here/speaking/calling') must not fire on questions/negations/idioms
@pytest.mark.parametrize('text', ['is bob here?', 'no bob here', 'Bob, here you go', 'where is bob calling from'])
def test_suffix_context_misfire_rejected(text):
    assert detect_speaker_from_text(text) is None


def test_suffix_genuine_intro_still_detected():
    assert detect_speaker_from_text('bob here') == 'Bob'
    assert detect_speaker_from_text('sarah speaking, how can i help') == 'Sarah'


# #13 -- possessive constructions don't make the possessor the speaker
@pytest.mark.parametrize('text', ["This is John's car", "I'm Bob's brother", "This is Sarah's mom"])
def test_possessive_rejected(text):
    assert detect_speaker_from_text(text) is None


# #11 -- a trailing capitalized 'I' must not be absorbed into the name
def test_trailing_pronoun_i_not_absorbed():
    assert detect_speaker_from_text("I'm Anna I will call you") == 'Anna'
    assert detect_speaker_from_text('My name is Sofia I am new') == 'Sofia'


# #14 -- normalization preserves intentional interior capitals and short acronyms
def test_normalize_preserves_interior_caps():
    assert detect_speaker_from_text("I'm DeShawn") == 'DeShawn'
    assert detect_speaker_from_text('This is McKenzie') == 'McKenzie'
    assert detect_speaker_from_text('Call me DJ') == 'DJ'


# Recall guard -- real names that are also common words must STILL be detected
# (we deliberately did not denylist them; this locks in that decision).
def test_recall_common_word_names_preserved():
    assert detect_speaker_from_text("I'm June") == 'June'
    assert detect_speaker_from_text('This is Grace') == 'Grace'
    assert detect_speaker_from_text("I'm Will") == 'Will'
    assert detect_speaker_from_text("I'm Mary Jo") == 'Mary Jo'


# Verification round -- regressions surfaced by the adversarial check, now locked in.


# "<name> calling from/about <x>" is a genuine phone self-intro, not an idiom
@pytest.mark.parametrize(
    'text,expected',
    [
        ('mike calling from the office', 'Mike'),
        ('dave calling from acme', 'Dave'),
        ('jen calling about the meeting', 'Jen'),
    ],
)
def test_suffix_calling_intro_detected(text, expected):
    assert detect_speaker_from_text(text) == expected


# A question/negation clause earlier in run-on ASR must not suppress a later intro
def test_suffix_question_guard_scoped_to_local_clause():
    assert detect_speaker_from_text('is this thing on? sarah speaking') == 'Sarah'
    assert detect_speaker_from_text('are you there? bob here') == 'Bob'
    # ...while a real question about the name is still suppressed
    assert detect_speaker_from_text('is bob here?') is None
    assert detect_speaker_from_text('where is bob calling from') is None


# A real surname that coincides with a stopword (Good/Well/Right/Fine) is kept
def test_multiword_surname_stopword_collision_preserved():
    assert detect_speaker_from_text("I'm DeShawn Good") == 'DeShawn Good'
    assert detect_speaker_from_text('My name is DeShawn Good') == 'DeShawn Good'
    # ...but a leading pronoun/filler is still rejected
    assert detect_speaker_from_text('This is It Works') is None
    assert detect_speaker_from_text("I'm Not Sure") is None
