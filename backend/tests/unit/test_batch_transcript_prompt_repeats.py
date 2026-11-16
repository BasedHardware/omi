"""Prompt canonicalization keeps original stored objects and genuine repetition."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from utils.conversations.transcript_repeats import canonical_prompt_segments

WORDS = 'The revised project proposal needs another detailed planning meeting before delivery'


def segment(key, start=0, *, scope='final:batch:native', text=WORDS, **extra):
    return dict(id=key, start=start, end=start + 10, text=text, speaker_id_scope=scope, is_user=False, **extra)


def test_placed_batch_copy_wins_over_retimed_unplaced_copy_without_mutating_storage():
    original = [segment('sync', -20, scope='final:batch:sync', audio_alignment='unplaced'), segment('native')]
    before = deepcopy(original)
    assert canonical_prompt_segments(original) == [original[1]]
    assert original == before
    assert canonical_prompt_segments(original)[0] is original[1]


@pytest.mark.parametrize('change', [' not', ' 42', ' tomorrow'])
def test_novel_words_negations_numbers_remain(change):
    original = [segment('native'), segment('sync', scope='final:batch:sync', text=WORDS + change)]
    selected = canonical_prompt_segments(original)
    assert original[1] in selected
    if change.strip() in {'not', '42'}:
        assert selected == original


@pytest.mark.parametrize('extra', [{'speaker_label_source': 'manual'}, {'translations': [{'text': 'edited'}]}])
def test_manual_or_translated_duplicate_is_retained(extra):
    original = [segment('native'), segment('sync', scope='final:batch:sync', **extra)]
    selected = canonical_prompt_segments(original)
    assert original[1] in selected


def test_same_scope_later_occurrence_and_short_repetition_remain():
    same = [segment('a'), segment('b', start=15)]
    assert canonical_prompt_segments(same) == same
    distant = [segment('a'), segment('b', start=100, scope='final:batch:other')]
    assert canonical_prompt_segments(distant) == distant
    short = [segment('a', text='yes please'), segment('b', scope='final:batch:other', text='yes please')]
    assert canonical_prompt_segments(short) == short


def test_distinct_known_speakers_are_not_collapsed():
    original = [segment('a', person_id='one'), segment('b', scope='final:batch:other', person_id='two')]
    assert canonical_prompt_segments(original) == original


def test_anonymous_attribute_objects_and_kill_switch(monkeypatch):
    original = [SimpleNamespace(**segment('a')), SimpleNamespace(**segment('b', scope='final:batch:other'))]
    assert len(canonical_prompt_segments(original)) == 1
    monkeypatch.setenv('SYNC_LINEAGE_LIVE_DEDUPE_ENABLED', 'off')
    assert canonical_prompt_segments(original) == original


def test_over_budget_and_unscoped_content_are_preserved():
    original = [segment(str(i), scope='') for i in range(4097)]
    assert canonical_prompt_segments(original) == original


def test_both_summary_renderers_share_canonical_segment_ids(monkeypatch):
    from models.transcript_segment import TranscriptSegment
    from utils.conversations import transcript_for_llm as render

    monkeypatch.setattr(render, 'get_user_name', lambda *args, **kwargs: 'Test User')
    monkeypatch.setattr(render, 'serving_for', lambda *args: False)
    segments = [TranscriptSegment(**segment('a')), TranscriptSegment(**segment('b', scope='final:batch:other'))]
    conversation = SimpleNamespace(transcript_segments=segments)
    normal = render.conversation_transcript_for_llm('synthetic', conversation)
    compact, speakers = render.conversation_transcript_and_speaker_map('synthetic', conversation)
    assert normal.count(WORDS) == compact.count(WORDS) == 1
    assert '[a ' in compact and '[b ' not in compact
    assert len(conversation.transcript_segments) == 2


def test_short_exact_cross_scope_copy_is_only_omitted_at_the_same_time():
    original = [
        segment('a', text='Please send the proposal'),
        segment('b', scope='final:batch:other', text='Please send the proposal'),
    ]
    assert canonical_prompt_segments(original) == [original[0]]
    original[1]['start'] += 2
    original[1]['end'] += 2
    assert canonical_prompt_segments(original) == original


@pytest.mark.parametrize('start', [None, True, 'invalid', float('nan'), float('inf')])
def test_malformed_clock_is_preserved_instead_of_certifying_a_repeat(start):
    original = [segment('a'), segment('b', scope='final:batch:other')]
    original[1]['start'] = start
    assert canonical_prompt_segments(original) == original
