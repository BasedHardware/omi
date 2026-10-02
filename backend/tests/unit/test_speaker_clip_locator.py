"""Synthetic text-location safety contracts; no user recordings or providers."""

import math

import pytest

from utils.speaker_clip_locator import locate_text

PHRASE = 'amber bronze coral denim emerald fuchsia gold hazel indigo jade khaki lilac'


def words(text=PHRASE, start=0.0):
    return [
        {'text': word, 'timestamp': [start + index, start + index + 0.9], 'speaker': 'SPEAKER_00'}
        for index, word in enumerate(text.split())
    ]


def test_locates_absolute_entry_boundaries_without_stored_clock():
    location, reason = locate_text(PHRASE, [(words(start=294.0), 400.0)], complete=True)
    assert reason == 'located'
    assert location.start == 294.0
    assert location.end == 305.9


@pytest.mark.parametrize('complete', [False])
def test_incomplete_search_never_establishes_unique_match(complete):
    assert locate_text(PHRASE, [(words(), 15.0)], complete=complete) == (None, 'budget_exhausted')


@pytest.mark.parametrize(
    'sources',
    [
        [(words() + words(start=20), 40)],
        [(words(), 15), (words(), 15)],
        [(words(), 15), (words(PHRASE.replace('lilac', 'magenta')), 15)],
    ],
)
def test_distinct_repeated_and_near_duplicate_occurrences_are_ambiguous(sources):
    assert locate_text(PHRASE, sources, complete=True) == (None, 'ambiguous')


def test_coarse_segment_keeps_its_real_boundaries():
    location, _ = locate_text(PHRASE, [([{'text': PHRASE, 'timestamp': [2, 24]}], 30)], complete=True)
    assert (location.start, location.end) == (2, 24)


def test_matching_subphrase_does_not_invent_word_times_inside_coarse_segment():
    entries = [{'text': PHRASE + ' maroon navy ochre pink quartz red silver teal', 'timestamp': [2, 24]}]
    assert locate_text(PHRASE, [(entries, 30)], complete=True) == (None, 'invalid_timing')


@pytest.mark.parametrize('timestamp', [[0, 0], [-1, 12], [0, 31], [math.nan, 12], [0, math.inf], [3]])
def test_invalid_or_untimed_response_declines_entire_index(timestamp):
    assert locate_text(PHRASE, [([{'text': PHRASE, 'timestamp': timestamp}], 30)], complete=True) == (
        None,
        'invalid_timing',
    )


@pytest.mark.parametrize('phrase', ['yes please thanks', 'one two ' * 12])
def test_short_or_generic_phrases_decline(phrase):
    assert locate_text(phrase, [(words(), 15)], complete=True) == (None, 'short_or_generic')


def test_matching_cannot_cross_blobs():
    a, b = words()[:6], words()[6:]
    assert locate_text(PHRASE, [(a, 15), (b, 15)], complete=True) == (None, 'not_found')


def test_unrelated_untimed_text_does_not_discard_valid_timed_hit():
    location, reason = locate_text(
        PHRASE, [(words(), 15), ([{'text': 'unrelated', 'timestamp': [0, 0]}], 30)], complete=True
    )
    assert location is not None and reason == 'located'


def test_matching_untimed_competitor_blocks_valid_timed_hit():
    assert locate_text(PHRASE, [(words(), 15), ([{'text': PHRASE, 'timestamp': [0, 0]}], 30)], complete=True) == (
        None,
        'ambiguous',
    )


def test_shortened_repeat_remains_a_competitor():
    assert locate_text(PHRASE, [(words(), 15), (words()[:9], 15)], complete=True) == (None, 'ambiguous')


def test_substitution_competitor_without_any_trigram_is_detected():
    # Insertions every two words preserve .8 similarity without exact triples.
    altered = []
    for index, token in enumerate(PHRASE.split()):
        altered.append(token)
        if index % 2 == 1 and index < 10:
            altered.append('replacement')
    assert locate_text(PHRASE, [(words(), 15), (words(' '.join(altered)), 25)], complete=True) == (None, 'ambiguous')


def test_exact_competitor_threshold_is_not_lost_to_float_rounding():
    assert locate_text(PHRASE, [(words(), 15), (words()[:8], 15)], complete=True) == (None, 'ambiguous')
