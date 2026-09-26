"""Synthetic phase-2 gate cases; no customer transcript or network access."""

import random

import pytest

from utils.conversations.segment_remap import (
    estimate_offset,
    plan_segment_remap,
    remap_receipt,
    remap_source_ids,
    remap_translations,
)


def segment(sid, start, end, text='different words here', speaker_id=0, translations=None):
    return dict(id=sid, start=start, end=end, text=text, speaker_id=speaker_id, translations=translations or [])


def test_split_expands_identity_and_sources_but_refuses_unsplittable_translation():
    old = [segment('old', 0, 10, translations=[{'lang': 'fr', 'text': 'phrase'}])]
    new = [segment('left', 0, 5), segment('right', 5, 10)]
    plan = plan_segment_remap(old, new, offset_seconds=0)
    assert plan.ids == {'old': ('left', 'right')}
    receipt = {'generation': 1, 'segments': {'old': {'generation': 1, 'person_id': 'p', 'is_user': False}}}
    assert set(remap_receipt(receipt, old, new, plan)['segments']) == {'left', 'right'}
    assert remap_source_ids(['old'], plan) == ['left', 'right']
    with pytest.raises(ValueError, match='translation segmentation'):
        remap_translations(old, plan)


def test_merge_preserves_sources_and_rejects_conflicting_manual_identity():
    old = [segment('one', 0, 5), segment('two', 5, 10, speaker_id=1)]
    new = [segment('merged', 0, 10)]
    plan = plan_segment_remap(old, new, offset_seconds=0)
    assert plan.ids == {'one': ('merged',), 'two': ('merged',)}
    assert remap_source_ids(['one', 'two'], plan) == ['merged']
    with pytest.raises(ValueError, match='conflicting'):
        remap_receipt(
            {'speakers': {'0': {'person_id': 'a', 'is_user': False}, '1': {'person_id': 'b', 'is_user': False}}},
            old,
            new,
            plan,
        )


def test_one_to_one_translation_and_speaker_receipt_survive_rebase():
    old = [segment('old', 5, 8, translations=[{'lang': 'es', 'text': 'hola'}], speaker_id=3)]
    new = [segment('new', 105, 108, speaker_id=9)]
    plan = plan_segment_remap(old, new, offset_seconds=100)
    assert remap_translations(old, plan) == {'new': [{'lang': 'es', 'text': 'hola'}]}
    receipt = {'speakers': {'3': {'generation': 2, 'person_id': 'p', 'is_user': False}}}
    assert remap_receipt(receipt, old, new, plan)['segments'] == {
        'new': {'generation': 2, 'person_id': 'p', 'is_user': False}
    }


def test_gaps_empty_and_overlap_ambiguity():
    assert plan_segment_remap([], []).success_rate == 1
    assert plan_segment_remap([segment('a', 0, 1)], []).unresolved == ('a',)
    assert plan_segment_remap([segment('a', 0, 1)], [segment('b', 10, 11)], offset_seconds=0).unresolved == ('a',)
    old = [segment('a', 0, 3)]
    new = [segment('left', 0, 3), segment('right', 0, 3)]
    assert plan_segment_remap(old, new, offset_seconds=0).ambiguous == ('a',)


def test_text_anchor_estimates_rebased_clock_without_using_started_at():
    old = [
        segment('a', 10, 13, 'the distinctly blue harbor crane'),
        segment('b', 20, 24, 'a bright green lamp beside me'),
    ]
    new = [
        segment('x', 110, 113, 'the distinctly blue harbor crane'),
        segment('y', 120, 124, 'a bright green lamp beside me'),
    ]
    assert estimate_offset(old, new) == 100
    assert plan_segment_remap(old, new).ids == {'a': ('x',), 'b': ('y',)}


def test_random_monotone_resegmentation_and_rebase_property():
    rng = random.Random(91231)
    for _ in range(200):
        lengths = [rng.uniform(0.8, 8) for _ in range(rng.randrange(1, 12))]
        shift = rng.uniform(-250, 250)
        cursor = max(0.0, -shift) + 1.0
        old = []
        new = []
        for index, length in enumerate(lengths):
            start = cursor
            end = start + length
            old.append(segment(f'o{index}', start, end))
            midpoint = (start + end) / 2
            new.append(segment(f'n{index}a', start + shift, midpoint + shift))
            new.append(segment(f'n{index}b', midpoint + shift, end + shift))
            cursor = end + rng.uniform(0.1, 3)
        plan = plan_segment_remap(old, new, offset_seconds=shift)
        assert plan.safe
        assert len(plan.ids) == len(old)
        for index in range(len(old)):
            assert plan.ids[f'o{index}'] == (f'n{index}a', f'n{index}b')


def test_random_merged_segments_never_lose_source_reference():
    rng = random.Random(717)
    for _ in range(100):
        count = rng.randrange(2, 20)
        shift = rng.uniform(0, 200)
        old = [segment(f'o{i}', float(i), float(i + 1)) for i in range(count)]
        new = [segment(f'n{i // 2}', float(i) + shift, float(min(i + 2, count)) + shift) for i in range(0, count, 2)]
        plan = plan_segment_remap(old, new, offset_seconds=shift)
        assert plan.safe
        assert remap_source_ids([s['id'] for s in old], plan) == [s['id'] for s in new]


def test_duplicate_ids_and_invalid_times_fail_closed():
    with pytest.raises(ValueError, match='duplicate'):
        plan_segment_remap([segment('a', 0, 1), segment('a', 2, 3)], [])
    with pytest.raises(ValueError, match='invalid'):
        plan_segment_remap([segment('a', 1, 1)], [])
