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


def test_concurrent_targets_are_ambiguous_even_when_text_similarity_differs():
    old = [segment('source', 0, 10, 'this phrase matches the first target')]
    new = [
        segment('first', 0, 10, 'this phrase matches the first target'),
        segment('second', 2, 8, 'entirely unrelated words'),
    ]
    plan = plan_segment_remap(old, new, offset_seconds=0)
    assert plan.ids == {}
    assert plan.ambiguous == ('source',)
    receipt = {'segments': {'source': {'person_id': 'synthetic-person', 'is_user': False}}}
    with pytest.raises(ValueError, match='no safe target'):
        remap_receipt(receipt, old, new, plan)
    with pytest.raises(ValueError, match='no safe target'):
        remap_source_ids(['source'], plan)


@pytest.mark.parametrize('offset', [None, 0])
def test_sequential_filler_cannot_inherit_a_matching_sources_annotations(offset):
    old = [segment('source', 0, 10, 'the distinctly blue harbor crane')]
    new = [
        segment('matching', 0, 5, 'the distinctly blue harbor crane'),
        segment('filler', 5, 10, 'yeah'),
    ]
    plan = plan_segment_remap(old, new, offset_seconds=offset)
    assert not plan.safe
    assert 'filler' not in plan.ids.get('source', ())
    with pytest.raises(ValueError, match='no safe target'):
        remap_source_ids(['source'], plan)


@pytest.mark.parametrize('offset', [None, 0])
def test_extra_speech_inside_matching_target_blocks_annotation_remap(offset):
    old = [
        segment('source', 0, 10, 'the distinctly blue harbor crane'),
        segment('anchor', 20, 25, 'a unique clock anchor phrase'),
    ]
    new = [
        segment('expanded', 0, 10, 'the distinctly blue harbor crane yeah'),
        segment('fixed', 20, 25, 'a unique clock anchor phrase'),
    ]
    plan = plan_segment_remap(old, new, offset_seconds=offset)
    assert not plan.safe
    assert plan.unresolved == ('source',)
    assert 'source' not in plan.ids
    with pytest.raises(ValueError, match='no safe target'):
        remap_receipt({'segments': {'source': {'person_id': 'synthetic-person'}}}, old, new, plan)
    with pytest.raises(ValueError, match='no safe target'):
        remap_source_ids(['source'], plan)


def test_long_target_allows_one_asr_difference_within_ten_percent():
    old = [segment('source', 0, 10, 'the distinctly blue harbor crane stands beside the old stone bridge today')]
    new = [segment('target', 0, 10, 'the distinctly blue harbor crane stands beside the old stone bridge now')]
    plan = plan_segment_remap(old, new, offset_seconds=0)
    assert plan.safe
    assert plan.ids == {'source': ('target',)}


def test_real_text_partition_can_inherit_both_split_targets():
    old = [segment('source', 0, 10, 'the distinctly blue harbor crane')]
    new = [segment('left', 0, 5, 'the distinctly blue'), segment('right', 5, 10, 'harbor crane')]
    plan = plan_segment_remap(old, new, offset_seconds=0)
    assert plan.safe
    assert plan.ids == {'source': ('left', 'right')}


def test_random_sequential_fillers_never_receive_annotations_while_safe():
    rng = random.Random(19231)
    for _ in range(100):
        old = []
        new = []
        for index in range(rng.randrange(1, 12)):
            start = float(index * 12)
            phrase = f'the distinct harbor crane number {index}'
            old.append(segment(f'source-{index}', start, start + 8, phrase))
            new.append(segment(f'matching-{index}', start, start + 4, phrase))
            filler_start = start + rng.choice((4, 8))
            new.append(segment(f'filler-{index}', filler_start, filler_start + 4, rng.choice(('yeah', 'okay', 'no'))))
        plan = plan_segment_remap(old, new, offset_seconds=0)
        if plan.safe:
            receipt = {'segments': {item['id']: {'person_id': 'synthetic-person'} for item in old}}
            carried = remap_receipt(receipt, old, new, plan)
            assert all(not tid.startswith('filler-') for tid in carried['segments'])
        assert all(not tid.startswith('filler-') for targets in plan.ids.values() for tid in targets)


def test_large_disjoint_plan_uses_time_index():
    old = [segment(f'source-{i}', float(i * 2), float(i * 2 + 1)) for i in range(4000)]
    new = [segment(f'target-{i}', float(i * 2), float(i * 2 + 1)) for i in range(4000)]
    plan = plan_segment_remap(old, new, offset_seconds=0)
    assert plan.safe
    assert len(plan.ids) == len(old)


def test_time_index_agrees_with_overlap_rules_for_unsorted_nested_intervals():
    rng = random.Random(2048)
    for _ in range(100):
        old = [segment('source', 10, 15)]
        new = []
        for index in range(40):
            start = rng.uniform(0, 25)
            new.append(segment(f'target-{index}', start, start + rng.uniform(0.1, 12)))
        rng.shuffle(new)
        expected = [
            item
            for item in new
            if max(0, min(15, item['end']) - max(10, item['start'])) / min(5, item['end'] - item['start']) >= 0.5
        ]
        plan = plan_segment_remap(old, new, offset_seconds=0)
        if not expected:
            assert plan.unresolved == ('source',)
        elif any(
            right['start'] < left['end']
            for left, right in zip(
                sorted(expected, key=lambda item: item['start']), sorted(expected, key=lambda item: item['start'])[1:]
            )
        ):
            assert plan.ambiguous == ('source',)
        else:
            assert plan.ids == {'source': tuple(item['id'] for item in expected)}


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


def test_repeated_identical_text_with_fifteen_second_offset_maps_by_order_but_cannot_verify_clock():
    phrase = 'he began a confused complaint against the wizard who had vanished behind the curtain on the left'
    old = [segment(f'live-{i}', 2 + i * 5, 6 + i * 5, phrase) for i in range(8)]
    new = [segment(f'pass-{i}', 17 + i * 5, 21 + i * 5, phrase) for i in range(8)]
    plan = plan_segment_remap(old, new)
    assert plan.offset_seconds == 15
    assert plan.ids == {f'live-{i}': (f'pass-{i}',) for i in range(8)}
    assert plan.success_rate == 1.0
    assert not plan.safe
    assert not plan.offset_verified


def test_single_repeated_phrase_has_competing_placements_and_cannot_carry_references():
    phrase = 'he began a confused complaint against the wizard'
    old = [segment('live', 2, 6, phrase, translations=[{'lang': 'es', 'text': 'fixture'}])]
    new = [segment(f'pass-{i}', 17 + i * 5, 21 + i * 5, phrase) for i in range(8)]
    plan = plan_segment_remap(old, new)
    assert plan.ids == {}
    assert plan.ambiguous == ('live',)
    assert plan.success_rate == 0
    assert not plan.safe
    with pytest.raises(ValueError, match='no safe target'):
        remap_source_ids(['live'], plan)
    with pytest.raises(ValueError, match='no safe target'):
        remap_receipt({'segments': {'live': {'person_id': 'person'}}}, old, new, plan)
    with pytest.raises(ValueError, match='translation segmentation'):
        remap_translations(old, plan)


def test_repeated_short_words_are_ambiguous_without_a_unique_anchor():
    old = [segment('live', 1, 2, 'yeah')]
    new = [segment(f'pass-{i}', 10 + 3 * i, 11 + 3 * i, 'yeah') for i in range(4)]
    plan = plan_segment_remap(old, new)
    assert plan.ambiguous == ('live',)
    assert plan.ids == {}
    assert not plan.safe


def test_near_tied_short_phrase_placements_are_ambiguous_within_score_margin():
    old = [segment('live', 1, 2, 'yeah okay')]
    new = [segment('first', 10, 11, 'yeah okay'), segment('second', 20, 21, 'yeah okays')]
    plan = plan_segment_remap(old, new)
    assert plan.ambiguous == ('live',)
    assert plan.ids == {}
    assert not plan.safe


def test_unique_anchor_resolves_repeated_words_at_constant_offset():
    old = [
        segment('a', 1, 2, 'yeah'),
        segment('anchor', 3, 5, 'the distinct orange lighthouse'),
        segment('b', 6, 7, 'yeah'),
    ]
    new = [
        segment('x', 16, 17, 'yeah'),
        segment('fixed', 18, 20, 'the distinct orange lighthouse'),
        segment('y', 21, 22, 'yeah'),
    ]
    plan = plan_segment_remap(old, new)
    assert plan.offset_seconds == 15
    assert plan.ids == {'a': ('x',), 'anchor': ('fixed',), 'b': ('y',)}
    assert plan.safe


def test_distinct_anchors_reject_real_drift_instead_of_treating_it_as_one_offset():
    phrases = ['the distinct orange lighthouse', 'the bright green harbor crane', 'another unmistakable phrase today']
    old = [segment(f'live-{i}', 10 * i + 1, 10 * i + 3, phrase) for i, phrase in enumerate(phrases)]
    constant = [segment(f'pass-{i}', 10 * i + 16, 10 * i + 18, phrase) for i, phrase in enumerate(phrases)]
    drifting = [
        segment(f'pass-{i}', 10 * i + 16 + 3 * i, 10 * i + 18 + 3 * i, phrase) for i, phrase in enumerate(phrases)
    ]
    assert plan_segment_remap(old, constant).safe
    assert not plan_segment_remap(old, drifting).offset_verified
    assert not plan_segment_remap(old, drifting).safe


def test_auto_remap_rejects_time_overlap_without_text_agreement():
    old = [segment('live', 1, 4, 'the distinctly blue harbor crane')]
    new = [segment('pass', 1, 4, 'an entirely unrelated sentence about trains')]
    plan = plan_segment_remap(old, new)
    assert plan.success_rate == 0.0
    assert plan.unresolved == ('live',)
    assert not plan.offset_verified
    assert not plan.safe


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
