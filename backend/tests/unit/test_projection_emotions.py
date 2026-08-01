"""Rating the week's emotional charge, and consolidating it into one state.

The parts pinned here are the ones that are not the model's judgment: that the inventory is the
instrument's own twenty families, that independent completions are averaged rather than trusted
singly, that a blend is only claimed when a second family nearly ties the first, that a level
week can say so, and that a failed rating degrades to an unlit projection rather than losing a
grounded one.

Both mitigations under test are published rather than invented — averaging completions reduces
rating error by about 30%, and blends are a minority event, so the default is one term.
"""

from unittest.mock import patch

import pytest

from utils.projections import emotions as emotions_module
from utils.projections.emotions import (
    GEW_FAMILIES,
    NEGATIVE_FAMILIES,
    POSITIVE_FAMILIES,
    EmotionProfile,
    build_rating_prompt,
    consolidate,
    rate_emotions,
)


def test_the_inventory_is_the_instruments_own_twenty_families():
    # Twenty is a ceiling rather than a target: rateability degrades measurably above it, for
    # human raters and models alike.
    assert len(GEW_FAMILIES) == 20
    assert len(set(GEW_FAMILIES)) == 20
    assert len(POSITIVE_FAMILIES) == 10 and len(NEGATIVE_FAMILIES) == 10


def test_completions_are_averaged_rather_than_trusted_singly():
    profile = consolidate([{'fear': 4.0}, {'fear': 2.0}, {'fear': 3.0}])

    assert profile.primary == 'fear'
    assert profile.intensity == pytest.approx(3.0)
    # Spread across completions is the confidence signal, and the statistic the secondary
    # threshold should eventually be derived from instead of guessed.
    assert profile.dispersion == pytest.approx(2.0)
    assert profile.samples == 3


def test_one_dominant_family_is_named_alone():
    profile = consolidate([{'fear': 4.0, 'interest': 1.0}])

    assert profile.primary == 'fear'
    assert profile.secondary is None


def test_a_second_family_is_kept_only_when_it_nearly_ties():
    profile = consolidate([{'fear': 4.0, 'interest': 3.6}])

    assert profile.primary == 'fear'
    assert profile.secondary == 'interest'


def test_a_level_week_is_a_real_answer():
    # The published failure mode this guards: neutral text read as emotional rises from 28% to
    # 45% as inventories grow. A week with no charge must be expressible as having none.
    profile = consolidate([{}, {}])

    assert profile.is_empty
    assert 'no clear emotional charge' in profile.as_prompt_text()


def test_the_charge_reaches_the_prompt_named_but_never_coloured():
    profile = EmotionProfile(primary='fear', secondary='interest', intensity=3.4, dispersion=1.0, vector={}, samples=5)
    text = profile.as_prompt_text()

    assert 'fear at 3.4 of 5' in text
    assert 'interest' in text
    # The mapping from charge to hue is not supported by the evidence, so this layer must not
    # assert one — it names the charge and leaves colour to the image model.
    for colour in ('blue', 'grey', 'gray', 'gold', 'red', 'violet'):
        assert colour not in text.lower()


def test_the_rating_pass_asks_for_every_family_and_allows_none():
    prompt = build_rating_prompt('the move', ('Circling the move again',), 'their material')

    for family in GEW_FAMILIES:
        assert family in prompt
    assert 'none_apply' in prompt
    assert 'the move' in prompt


def test_a_failed_rating_leaves_the_projection_unlit_rather_than_refused():
    # A grounded projection is worth shipping without a measured charge; losing it because the
    # rating pass failed would be the tail wagging the dog.
    with patch.object(emotions_module, 'get_llm', side_effect=RuntimeError('gateway down')):
        profile = rate_emotions('the move', ('evidence',), 'material')

    assert profile.is_empty
