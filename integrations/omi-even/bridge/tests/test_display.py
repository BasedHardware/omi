"""Tests for the G2 display adapter.

The samples below are written to look like real Omi chat answers -- markdown
headings, mixed bullet styles, inline citations with no space before the
bracket, links, fenced code and emoji -- because that is exactly what the
bridge receives and what a naive adapter mangles.
"""

import json
import random
import re
import string
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from display import (  # noqa: E402
    DEFAULT_LIMIT,
    DEFAULT_PAGE_SIZE,
    fit_for_glasses,
    openai_chat_completion,
    paginate,
)

# --------------------------------------------------------------------------
# Representative Omi output
# --------------------------------------------------------------------------

OMI_STANDUP = """## Your morning so far

You spent most of the standup on the **firmware OTA rollout** with Sarah[1].
The team agreed to *hold* the release until the battery regression is
reproduced[2][3].

Action items:
- Reply to Marcus about the `battery_drain` metric
- [ ] File the regression in [the tracker](https://github.com/omi/omi/issues/42)
* Ping Sarah before 4pm
1. Draft the changelog entry

> Sarah: "we should not ship this blind"

More context: https://linear.app/omi/issue/OMI-1234 and www.notion.so/omi/notes
"""

OMI_CODE_ANSWER = """Here is the fix 🎉

```python
# retry with backoff
def fetch(url):
    return requests.get(url, timeout=5)
```

That handles the timeout you hit yesterday[1]. See the ~~old~~ new docs at
<https://docs.omi.me/retries> for the ___full___ story.
"""

OMI_EMOJI_ANSWER = 'Great news 🎉! Your meeting with Sarah 👩‍💻 is confirmed ✅ for 3pm — bring the “battery” notes.'

OMI_LONG_ANSWER = (
    'You have three things left today. First, Marcus is waiting on the battery '
    'regression writeup and said he would block the release without it. Second, '
    'the design review moved to 4pm because Priya had a conflict with the '
    'investor call. Third, you promised Sarah a decision on the firmware '
    'rollout before end of day. Everything else on the list can slip to '
    'tomorrow without anyone noticing.'
)


def assert_display_safe(text):
    """Every guarantee the firmware relies on, asserted in one place."""
    assert isinstance(text, str)
    assert text == text.strip(), 'leading/trailing whitespace leaks to the display'
    for char in text:
        assert char == '\n' or ' ' <= char <= '~', f'unsafe character {char!r} for the G2 font'
    assert '\n\n\n' not in text, 'more than one blank line'


# --------------------------------------------------------------------------
# Markdown stripping
# --------------------------------------------------------------------------


def test_headings_are_stripped():
    out = fit_for_glasses('## Your morning so far\n\nYou had two meetings.')
    assert '#' not in out
    assert out.startswith('Your morning so far')


def test_bold_italic_and_code_markers_are_stripped():
    out = fit_for_glasses('The **firmware OTA** rollout is *held* until `battery_drain` drops.')
    assert out == 'The firmware OTA rollout is held until battery_drain drops.'


def test_bold_italic_combined_and_underscore_emphasis():
    out = fit_for_glasses('That is ___really___ __important__ and _urgent_.')
    assert out == 'That is really important and urgent.'


def test_snake_case_identifiers_survive_italic_stripping():
    out = fit_for_glasses('Check the some_var_name field in battery_drain_v2.')
    assert 'some_var_name' in out
    assert 'battery_drain_v2' in out


def test_fenced_code_keeps_the_code_and_drops_the_fences():
    out = fit_for_glasses(OMI_CODE_ANSWER)
    assert '```' not in out
    assert 'def fetch(url):' in out
    assert 'requests.get(url, timeout=5)' in out


def test_blockquote_marker_is_stripped():
    out = fit_for_glasses('> Sarah: "we should not ship this blind"')
    assert out.startswith('Sarah:')
    assert '>' not in out


def test_all_bullet_styles_normalise_to_one_marker():
    out = fit_for_glasses('- dash item\n* star item\n+ plus item\n1. numbered item\n2) paren item')
    assert out.splitlines() == [
        '- dash item',
        '- star item',
        '- plus item',
        '- numbered item',
        '- paren item',
    ]


def test_task_list_checkboxes_are_stripped():
    out = fit_for_glasses('- [ ] File the regression\n- [x] Reply to Marcus')
    assert out.splitlines() == ['- File the regression', '- Reply to Marcus']


def test_horizontal_rules_are_removed():
    out = fit_for_glasses('Before\n\n---\n\nAfter')
    assert out == 'Before\n\nAfter'


def test_strikethrough_keeps_the_words():
    out = fit_for_glasses('See the ~~old~~ new docs.')
    assert out == 'See the old new docs.'


def test_link_becomes_its_label():
    out = fit_for_glasses('File it in [the tracker](https://github.com/omi/omi/issues/42) today.')
    assert out == 'File it in the tracker today.'


def test_images_are_dropped_entirely():
    out = fit_for_glasses('Chart: ![battery graph](https://cdn.omi.me/g.png) looks flat.')
    assert 'battery graph' not in out
    assert out == 'Chart: looks flat.'


def test_full_standup_sample_has_no_markdown_left():
    out = fit_for_glasses(OMI_STANDUP, limit=2000)
    assert_display_safe(out)
    for marker in ('**', '```', '](', '#', '>', '~~'):
        assert marker not in out, f'{marker!r} survived'
    # The words themselves must all still be there.
    for word in ('firmware', 'Sarah', 'battery_drain', 'tracker', 'changelog'):
        assert word in out


# --------------------------------------------------------------------------
# URLs, citations, emoji
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    'raw',
    [
        'Details at https://linear.app/omi/issue/OMI-1234 today.',
        'Details at http://example.com/a/b?c=d#frag today.',
        'Details at www.notion.so/omi/notes today.',
        'Details at <https://docs.omi.me/retries> today.',
    ],
)
def test_bare_urls_are_removed(raw):
    out = fit_for_glasses(raw)
    assert 'http' not in out
    assert 'www.' not in out
    assert out == 'Details at today.'


def test_url_removal_leaves_no_empty_brackets():
    out = fit_for_glasses('Read it (https://docs.omi.me/retries) when you can.')
    assert '()' not in out
    assert out == 'Read it when you can.'


@pytest.mark.parametrize(
    'raw,expected',
    [
        ('You discussed firmware yesterday[1].', 'You discussed firmware yesterday.'),
        ('You discussed firmware yesterday[1][2].', 'You discussed firmware yesterday.'),
        ('Hold the release[12][3] until Monday[7].', 'Hold the release until Monday.'),
    ],
)
def test_omi_citation_markers_are_removed(raw, expected):
    assert fit_for_glasses(raw) == expected


def test_citation_removal_does_not_eat_markdown_links_with_numeric_labels():
    out = fit_for_glasses('See [1](https://omi.me/one) for context.')
    assert out == 'See 1 for context.'


def test_emoji_are_dropped_and_words_preserved():
    out = fit_for_glasses(OMI_EMOJI_ANSWER)
    assert_display_safe(out)
    assert out == 'Great news! Your meeting with Sarah is confirmed for 3pm - bring the "battery" notes.'


def test_smart_punctuation_is_converted_to_ascii():
    raw = 'She said “ship it” — it’s ready… → today ½ done ≥ 90%.'
    out = fit_for_glasses(raw)
    assert_display_safe(out)
    assert out == 'She said "ship it" - it\'s ready... -> today 1/2 done >= 90%.'


def test_accented_latin_is_transliterated_not_dropped():
    out = fit_for_glasses('Meet Renee at the café in Zürich nächste Woche.')
    assert out == 'Meet Renee at the cafe in Zurich nachste Woche.'


def test_emoji_only_input_returns_empty_string():
    assert fit_for_glasses('🎉🎉🎉 👩‍💻 ✅') == ''


def test_cjk_only_input_does_not_crash():
    assert fit_for_glasses('こんにちは世界') == ''


def test_bullet_whose_content_was_only_a_url_disappears():
    out = fit_for_glasses('- https://linear.app/omi/OMI-1\n- Reply to Marcus')
    assert out == '- Reply to Marcus'


def test_zero_width_and_nbsp_characters_are_neutralised():
    out = fit_for_glasses('Ship​it now﻿.')
    assert_display_safe(out)
    assert out == 'Shipit now.'


# --------------------------------------------------------------------------
# Whitespace
# --------------------------------------------------------------------------


def test_whitespace_runs_collapse_and_blank_lines_are_capped():
    out = fit_for_glasses('One    two\t\tthree\n\n\n\n\nfour')
    assert out == 'One two three\n\nfour'


def test_crlf_input_is_normalised():
    out = fit_for_glasses('One\r\n\r\nTwo\r\n')
    assert out == 'One\n\nTwo'


# --------------------------------------------------------------------------
# Truncation
# --------------------------------------------------------------------------


def test_truncation_lands_on_a_sentence_boundary():
    text = 'First sentence here. Second sentence here. Third sentence here.'
    out = fit_for_glasses(text, limit=30)
    assert out == 'First sentence here...'
    assert len(out) <= 30


def test_truncation_prefers_the_last_sentence_that_fits():
    out = fit_for_glasses(OMI_LONG_ANSWER, limit=200)
    assert len(out) <= 200
    assert out.endswith('...')
    assert out.startswith('You have three things left today.')
    # Cut after a complete sentence, so the next sentence's opener is absent.
    assert 'Second,' not in out


def test_truncation_fills_the_screen_when_the_sentence_boundary_is_far_back():
    """Bullet lists have no terminal punctuation, so a strict sentence cut

    would strand half the screen. The action items are the useful part of a
    standup answer -- they must survive.
    """
    out = fit_for_glasses(OMI_STANDUP, limit=DEFAULT_LIMIT)
    assert len(out) <= DEFAULT_LIMIT
    assert len(out) > DEFAULT_LIMIT * 0.8, f'wasted {DEFAULT_LIMIT - len(out)} chars of screen'
    assert 'Reply to Marcus' in out


def test_truncation_never_produces_four_dots():
    out = fit_for_glasses('Done. And more text that will certainly not fit here.', limit=12)
    assert out.endswith('...')
    assert not out.endswith('....')


def test_truncation_falls_back_to_a_word_boundary():
    text = 'alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima'
    out = fit_for_glasses(text, limit=30)
    assert len(out) <= 30
    assert out.endswith('...')
    body = out[:-3]
    # No partial word: every emitted word is one of the originals.
    assert set(body.split()) <= set(text.split())


def test_truncation_length_includes_the_ellipsis():
    for limit in range(4, 120):
        out = fit_for_glasses(OMI_LONG_ANSWER, limit=limit)
        assert len(out) <= limit, f'limit={limit} produced {len(out)} chars'
        assert out.endswith('...')


def test_short_text_is_returned_untouched_without_ellipsis():
    out = fit_for_glasses('All clear.', limit=DEFAULT_LIMIT)
    assert out == 'All clear.'
    assert not out.endswith('...')


def test_default_limit_is_respected_on_a_real_sample():
    out = fit_for_glasses(OMI_STANDUP)
    assert len(out) <= DEFAULT_LIMIT
    assert_display_safe(out)


def test_output_never_exceeds_limit_property():
    """Property: for arbitrary markdown-ish input and limit, len(out) <= limit."""
    rng = random.Random(20240727)
    vocabulary = [
        'meeting',
        'Sarah',
        '**bold**',
        '*held*',
        '`code`',
        '[label](https://omi.me/x)',
        'yesterday[1]',
        'https://linear.app/omi/OMI-9',
        '🎉',
        'don’t',
        '- bullet',
        '# heading',
        'supercalifragilisticexpialidocious',
        'end.',
        'Next?',
        'wow!',
        '\n',
        '\n\n',
    ]
    for _ in range(400):
        words = [rng.choice(vocabulary) for _ in range(rng.randint(0, 120))]
        raw = ' '.join(words)
        limit = rng.randint(1, 500)
        out = fit_for_glasses(raw, limit=limit)
        assert len(out) <= limit, f'limit={limit} produced {len(out)} chars from {raw!r}'
        assert_display_safe(out)


def test_random_unicode_input_never_crashes_or_overflows():
    rng = random.Random(7)
    for _ in range(300):
        raw = ''.join(chr(rng.randint(1, 0x2FFFF)) for _ in range(rng.randint(0, 200)))
        out = fit_for_glasses(raw, limit=rng.randint(1, 400))
        assert_display_safe(out)


# --------------------------------------------------------------------------
# Edge cases
# --------------------------------------------------------------------------


@pytest.mark.parametrize('raw', ['', '   ', '\n\n', '\t \n \t', '\r\n'])
def test_empty_and_whitespace_only_input_returns_empty_string(raw):
    assert fit_for_glasses(raw) == ''


def test_markdown_only_input_returns_empty_string():
    assert fit_for_glasses('## \n\n---\n\n> \n\n- \n') == ''


def test_single_word_longer_than_limit_is_cut_to_fit():
    word = 'a' * 500
    out = fit_for_glasses(word, limit=50)
    assert len(out) == 50
    assert out == 'a' * 47 + '...'


def test_limit_smaller_than_the_ellipsis_still_holds_the_cap():
    for limit in (1, 2, 3):
        out = fit_for_glasses('hello world', limit=limit)
        assert len(out) <= limit


def test_non_positive_limit_returns_empty_string():
    assert fit_for_glasses('hello world', limit=0) == ''
    assert fit_for_glasses('hello world', limit=-5) == ''


# --------------------------------------------------------------------------
# Pagination
# --------------------------------------------------------------------------


@pytest.mark.parametrize('raw', ['', '   ', '\n\n'])
def test_paginate_empty_input_returns_empty_list(raw):
    assert paginate(raw) == []


def test_paginate_short_text_is_a_single_page():
    assert paginate('All clear.') == ['All clear.']


def test_paginate_respects_page_size_and_keeps_every_word_in_order():
    text = fit_for_glasses(OMI_STANDUP, limit=4000)
    pages = paginate(text, page_size=80)
    assert len(pages) > 1
    for page in pages:
        assert len(page) <= 80
        assert page == page.strip()
    assert ' '.join(pages).split() == text.split()


def test_paginate_prefers_paragraph_boundaries():
    text = 'First paragraph here.\n\nSecond paragraph here.\n\nThird paragraph here.'
    pages = paginate(text, page_size=50)
    # Two paragraphs fit together (21 + 2 + 22 = 45), the third starts a page.
    assert pages == ['First paragraph here.\n\nSecond paragraph here.', 'Third paragraph here.']


def test_paginate_falls_back_to_sentence_boundaries():
    text = 'Alpha one two. Bravo three four. Charlie five six. Delta seven eight.'
    pages = paginate(text, page_size=35)
    for page in pages:
        assert len(page) <= 35
    assert all(page.endswith(('.', '!', '?')) for page in pages)
    assert ' '.join(pages).split() == text.split()


def test_paginate_never_breaks_mid_word():
    rng = random.Random(99)
    words = [''.join(rng.choice(string.ascii_lowercase) for _ in range(rng.randint(1, 12))) for _ in range(400)]
    text = ' '.join(words)
    for page_size in (20, 37, 64, 100, 256, 400):
        pages = paginate(text, page_size=page_size)
        for page in pages:
            assert len(page) <= page_size
            for word in page.split():
                assert word in words, f'{word!r} is not an original word (mid-word break)'
        assert ' '.join(pages).split() == words


def test_paginate_property_over_random_sizes_and_texts():
    rng = random.Random(4242)
    for _ in range(200):
        sentences = []
        for _ in range(rng.randint(1, 20)):
            n = rng.randint(1, 12)
            sentences.append(' '.join('w' * rng.randint(1, 15) for _ in range(n)) + rng.choice('.!?'))
        paragraphs = []
        while sentences:
            take = rng.randint(1, 4)
            paragraphs.append(' '.join(sentences[:take]))
            sentences = sentences[take:]
        text = '\n\n'.join(paragraphs)
        page_size = rng.randint(20, 300)
        pages = paginate(text, page_size=page_size)
        assert all(len(p) <= page_size for p in pages)
        assert ' '.join(pages).split() == text.split()


def test_paginate_single_word_longer_than_page_is_chunked_not_dropped():
    word = 'x' * 250
    pages = paginate(word, page_size=100)
    assert [len(p) for p in pages] == [100, 100, 50]
    assert ''.join(pages) == word


def test_paginate_default_page_size_fits_the_screen():
    text = fit_for_glasses(OMI_LONG_ANSWER, limit=4000)
    pages = paginate(text)
    assert all(len(p) <= DEFAULT_PAGE_SIZE for p in pages)


def test_paginate_rejects_non_positive_page_size():
    with pytest.raises(ValueError):
        paginate('hello', page_size=0)


def test_fit_then_paginate_is_one_page_at_matching_sizes():
    out = fit_for_glasses(OMI_STANDUP, limit=DEFAULT_LIMIT)
    assert len(paginate(out, page_size=DEFAULT_PAGE_SIZE)) == 1


# --------------------------------------------------------------------------
# OpenAI response body
# --------------------------------------------------------------------------


def test_openai_chat_completion_is_structurally_valid():
    body = openai_chat_completion('All clear.')
    assert re.fullmatch(r'chatcmpl-[0-9a-f]{24}', body['id'])
    assert body['object'] == 'chat.completion'
    assert isinstance(body['created'], int) and body['created'] > 0
    assert body['model'] == 'omi'

    assert isinstance(body['choices'], list) and len(body['choices']) == 1
    choice = body['choices'][0]
    assert choice['index'] == 0
    assert choice['finish_reason'] == 'stop'
    assert choice['message'] == {'role': 'assistant', 'content': 'All clear.'}

    usage = body['usage']
    assert set(usage) == {'prompt_tokens', 'completion_tokens', 'total_tokens'}
    assert all(isinstance(v, int) and v >= 0 for v in usage.values())


def test_openai_chat_completion_is_json_serialisable():
    body = openai_chat_completion(fit_for_glasses(OMI_STANDUP))
    round_tripped = json.loads(json.dumps(body))
    assert round_tripped == body


def test_openai_chat_completion_honours_the_model_override():
    assert openai_chat_completion('hi', model='omi-standup')['model'] == 'omi-standup'


def test_openai_chat_completion_ids_are_unique():
    ids = {openai_chat_completion('hi')['id'] for _ in range(50)}
    assert len(ids) == 50


def test_openai_chat_completion_handles_empty_content():
    body = openai_chat_completion('')
    assert body['choices'][0]['message']['content'] == ''
    assert body['usage']['total_tokens'] == 0
