"""Regression tests for XML-ish markup leaking onto the glasses.

Omi wraps retrieved evidence in `<cite index="8-5">...</cite>`. Nothing in the
markdown stripper touched those, so they reached the display as literal angle
brackets -- observed on real hardware in an answer about commitments to a
colleague, where roughly a fifth of a 380-character screen was spent rendering
tag syntax.

The quoted words inside the tag are the substance of the answer, so they are
kept; only the markup is removed.
"""

from __future__ import annotations

import pytest

from display import fit_for_glasses


def test_cite_tags_are_removed_but_their_quote_survives():
    raw = 'You said<cite index="8-5">WhatsApp and Telegram are next</cite> to David.'
    out = fit_for_glasses(raw)
    assert '<cite' not in out
    assert '</cite>' not in out
    assert 'index=' not in out
    assert 'WhatsApp and Telegram are next' in out


def test_opening_tag_abutting_a_word_does_not_fuse_it():
    """The live output has no space before `<cite`; naive removal glues words."""
    out = fit_for_glasses('and said<cite index="1-1">next week</cite> firmly')
    assert 'saidnext' not in out
    assert 'said next week' in out


def test_the_exact_live_answer_renders_clean():
    """Verbatim from a real answer that shipped tags to the display."""
    raw = (
        "Here's what you actually committed to David (Zhang):\n\n"
        '**1. Fix the iMessage integration**\n'
        'During your demo you said<cite index="8-5">WhatsApp and Telegram are next</cite>'
        ' - but the demo revealed<cite index="8-6">Gmail integration was not working and '
        'full disk access needed for iMessage</cite>.'
    )
    out = fit_for_glasses(raw)
    assert '<' not in out and '>' not in out
    assert 'WhatsApp and Telegram are next' in out
    assert '**' not in out


@pytest.mark.parametrize(
    'raw',
    [
        '<b>bold</b> text',
        '<span class="x">inner</span>',
        '<br/>line',
        '<UNKNOWN attr="1">kept</UNKNOWN>',
        'nested <a><b>deep</b></a> end',
    ],
)
def test_any_simple_tag_degrades_to_its_text(raw):
    out = fit_for_glasses(raw)
    assert '<' not in out and '>' not in out


@pytest.mark.parametrize(
    ('raw', 'must_keep'),
    [
        ('5 < 10 and 10 > 5', ['5', '10']),
        ('use a < b for the comparison', ['a', 'b']),
        ('x <- y assignment', ['x', 'y']),
        ('temp > 3 degrees', ['temp', '3']),
    ],
)
def test_mathematical_comparisons_are_not_mistaken_for_tags(raw, must_keep):
    """`<` followed by a non-letter is arithmetic, not markup."""
    out = fit_for_glasses(raw)
    for token in must_keep:
        assert token in out


def test_an_unterminated_tag_does_not_eat_the_rest_of_the_answer():
    """A truncated stream can end mid-tag; the visible words must survive."""
    out = fit_for_glasses('The answer is <cite index="9-9" and then it was cut off')
    assert 'The answer is' in out
    assert 'cut off' in out


def test_tag_stripping_still_respects_the_length_limit():
    raw = 'prefix ' + '<cite index="1-1">word</cite> ' * 200
    out = fit_for_glasses(raw, limit=380)
    assert len(out) <= 380
    assert '<' not in out
