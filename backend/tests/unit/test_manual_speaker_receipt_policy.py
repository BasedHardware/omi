"""Pure receipt regressions; no Firestore, provider, or network dependencies."""

from copy import deepcopy
from itertools import permutations
import random

import pytest

from utils.manual_speaker_assignments import (
    acknowledged_teaching,
    apply_manual_assignments,
    manual_assignment,
    remap_absorbed_receipt,
)


def decision(generation, person_id, *, training=True):
    result = {'generation': generation, 'person_id': person_id, 'is_user': False}
    if not training:
        result['use_for_speech_training'] = False
    return result


@pytest.mark.parametrize('edges', list(permutations([('a', 'b'), ('b', 'c'), ('c', 'd')])))
def test_absorption_chains_resolve_independently_of_map_order(edges):
    receipt = {'generation': 4, 'segments': {'a': decision(4, 'alice'), 'c': decision(2, 'bob')}}
    before = deepcopy(receipt)
    result = remap_absorbed_receipt(receipt, dict(edges))
    assert result == {'generation': 4, 'segments': {'d': decision(4, 'alice')}}
    assert receipt == before
    assert remap_absorbed_receipt(result, dict(edges)) == result


@pytest.mark.parametrize('edges', [{'a': 'a'}, {'a': 'b', 'b': 'a'}, {'a': 'b', 'b': 'c', 'c': 'b'}])
def test_cyclic_absorption_fails_closed_without_mutating_receipt(edges):
    receipt = {'generation': 3, 'segments': {'a': decision(3, 'alice')}}
    before = deepcopy(receipt)
    with pytest.raises(ValueError, match='Cyclic'):
        remap_absorbed_receipt(receipt, edges)
    assert receipt == before


def test_newer_survivor_and_opt_out_keep_their_precedence():
    receipt = {'generation': 7, 'segments': {'a': decision(5, 'alice'), 'c': decision(7, None, training=False)}}
    result = remap_absorbed_receipt(receipt, {'b': 'c', 'a': 'b'})
    assert result['segments'] == {'c': decision(7, None, training=False)}


@pytest.mark.parametrize('seed', range(12))
def test_randomized_edits_agree_with_an_independent_per_segment_oracle(seed):
    """Replay commands into a simple oracle, not a second receipt implementation."""
    rng = random.Random(seed)
    conversation = {
        'id': 'conversation',
        'status': 'completed',
        'transcript_segments': [
            {
                'id': f's{i}',
                'speaker_id': i % 3,
                'text': 'Synthetic speech',
                'start': i,
                'end': i + 1,
                'is_user': False,
                'person_id': None,
            }
            for i in range(9)
        ],
    }
    expected = {s['id']: (False, None, True) for s in conversation['transcript_segments']}
    for _ in range(80):
        is_user, person_id = rng.choice([(True, None), (False, 'alice'), (False, 'bob'), (False, None)])
        training = rng.choice([True, False])
        if rng.choice([True, False]):
            speaker_id = rng.randrange(3)
            selector = {'speaker_id': speaker_id}
            targets = [s['id'] for s in conversation['transcript_segments'] if s['speaker_id'] == speaker_id]
        else:
            targets = rng.sample(list(expected), rng.randint(1, 3))
            selector = {'segment_ids': targets}
        before = deepcopy(conversation)
        segments, receipt, resolved, _ = manual_assignment(
            conversation, person_id=person_id, is_user=is_user, use_for_speech_training=training, **selector
        )
        assert conversation == before
        assert set(resolved) == set(targets)
        for sid in targets:
            expected[sid] = (is_user, person_id, training)
        conversation.update(transcript_segments=segments, manual_speaker_assignments=receipt)
        assert apply_manual_assignments(segments, receipt) == segments
        for segment in segments:
            owner, person, allow_training = expected[segment['id']]
            assert (segment['is_user'], segment['person_id']) == (owner, person)
            if person:
                assert acknowledged_teaching(conversation, person, [segment['id']]) == allow_training


def test_apply_manual_assignments_handles_missing_is_user_or_person_id():
    """Verify that legacy decisions missing is_user or person_id keys do not crash with KeyError."""
    segments = [
        {'id': 's1', 'speaker_id': 0, 'text': 'Hello'},
        {'id': 's2', 'speaker_id': 1, 'text': 'World'},
    ]
    # Receipt where speaker decision has no 'is_user' key
    receipt_no_is_user = {
        'generation': 1,
        'speakers': {'0': {'generation': 1, 'person_id': 'person_alice'}},
    }
    updated = apply_manual_assignments(segments, receipt_no_is_user)
    assert updated[0]['is_user'] is False
    assert updated[0]['person_id'] == 'person_alice'
    assert updated[0]['speaker_identity_status'] == 'not_user'

    # Receipt where segment decision has no 'person_id' key
    receipt_no_person_id = {
        'generation': 2,
        'segments': {'s2': {'generation': 2, 'is_user': True}},
    }
    updated2 = apply_manual_assignments(segments, receipt_no_person_id)
    assert updated2[1]['is_user'] is True
    assert updated2[1]['person_id'] is None
    assert updated2[1]['speaker_identity_status'] == 'user'
