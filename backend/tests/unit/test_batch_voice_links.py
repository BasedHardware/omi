"""Synthetic durable voice continuity, abstention and privacy contracts."""

from copy import deepcopy
from datetime import datetime, timezone
import json
import math

import pytest

from utils.stt.batch_voice_links import (
    FIELD,
    MAX_BINDINGS,
    MAX_VOICES,
    arbitrate_linked_owner_claims,
    decode_registry,
    encode_registry,
    link_unit_voices,
)
from utils.stt.speaker_identity import ConversationSpeakerIdAllocator
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_batch_pipeline_live import recording, incoming
from tests.unit.test_sync_cross_job_assignment import chunk, intake


def evidence(unit, vectors, generation=0):
    return {
        'scope': f'final:batch:{unit}',
        'privacy_generation': generation,
        'embedding_space': 'synthetic:v2',
        'provenance': {'embedding_model': 'synthetic', 'embedding_revision': 'immutable'},
        'centroids': {name: {'embedding': vector, 'evidence_seconds': 10} for name, vector in vectors.items()},
    }


def run(state, unit, vectors, *, existing=(), receipt=None, enabled=True, generation=0):
    allocator = ConversationSpeakerIdAllocator()
    allocator.hydrate(existing)
    allocator.hydrate_receipt(receipt)
    segments = [
        {'id': unit + name, 'speaker': name, 'speaker_id': i, 'speaker_id_scope': f'final:batch:{unit}'}
        for i, name in enumerate(vectors)
    ]
    state = link_unit_voices(
        state,
        evidence(unit, vectors, generation),
        segments,
        allocator,
        receipt=receipt,
        existing=existing,
        enabled=enabled,
    )
    for segment in segments:
        allocator.assign(segment)
    return state, segments


def test_cross_unit_restart_replay_and_kill_switch():
    state, first = run({}, 'a', {'SPEAKER_00': [1.0, 0.0]})
    # No in-process allocator survives; the registry and transcript are enough.
    state = decode_registry(encode_registry(state, 'synthetic-user'), 'synthetic-user')
    state, second = run(state, 'b', {'SPEAKER_08': [1.0, 0.01]}, existing=first)
    assert second[0]['speaker_id'] == first[0]['speaker_id']
    before = deepcopy(state)
    state, retry = run(state, 'b', {'SPEAKER_08': [0.0, 1.0]}, existing=first + second, enabled=False)
    assert retry == second and state == before
    _, third = run(state, 'c', {'SPEAKER_08': [1.0, 0.0]}, existing=first + second, enabled=False)
    assert third[0]['speaker_id'] != first[0]['speaker_id']


def test_same_unit_cannot_link_and_competition_abstains():
    state, first = run({}, 'a', {'SPEAKER_00': [1.0, 0.0]})
    state, second = run(state, 'b', {'SPEAKER_00': [1.0, 0.0], 'SPEAKER_01': [1.0, 0.01]}, existing=first)
    assert len({s['speaker_id'] for s in first + second}) == 3
    # A later multipart part carrying a new unit voice cannot reuse that unit's voice.
    _, third = run(state, 'b', {'SPEAKER_02': [1.0, 0.01]}, existing=first + second)
    assert third[0]['speaker_id'] not in {s['speaker_id'] for s in second}


def test_ambiguous_two_anchors_abstains():
    state, first = run({}, 'a', {'SPEAKER_00': [1.0, 0.0], 'SPEAKER_01': [1.0, 0.1]})
    _, second = run(state, 'b', {'SPEAKER_00': [1.0, 0.05]}, existing=first)
    assert second[0]['speaker_id'] not in {s['speaker_id'] for s in first}


@pytest.mark.parametrize('bad', [[0.0, 0.0], [math.nan, 1], [math.inf], [], ['1'], [True]])
def test_invalid_or_short_evidence_never_links(bad):
    state, first = run({}, 'a', {'SPEAKER_00': [1.0, 0.0]})
    _, second = run(state, 'b', {'SPEAKER_00': bad}, existing=first)
    assert second[0]['speaker_id'] != first[0]['speaker_id']
    allocator = ConversationSpeakerIdAllocator()
    allocator.hydrate(first)
    incoming = [{'speaker': 'SPEAKER_00', 'speaker_id_scope': 'final:batch:c'}]
    value = evidence('c', {'SPEAKER_00': [1.0, 0.0]})
    value['centroids']['SPEAKER_00']['evidence_seconds'] = 4.99
    link_unit_voices(state, value, incoming, allocator)
    allocator.assign(incoming[0])
    assert incoming[0]['speaker_id'] != first[0]['speaker_id']


def test_revision_and_privacy_generation_fence():
    state, first = run({}, 'a', {'SPEAKER_00': [1.0, 0.0]})
    allocator = ConversationSpeakerIdAllocator()
    allocator.hydrate(first)
    value = evidence('b', {'SPEAKER_00': [1.0, 0.0]})
    value['provenance']['embedding_revision'] = 'other'
    second = [{'speaker': 'SPEAKER_00', 'speaker_id_scope': 'final:batch:b'}]
    link_unit_voices(state, value, second, allocator)
    allocator.assign(second[0])
    assert second[0]['speaker_id'] != first[0]['speaker_id']
    fresh, third = run(state, 'c', {'SPEAKER_00': [1.0, 0.0]}, existing=first, generation=1)
    assert fresh['privacy_generation'] == 1
    assert third[0]['speaker_id'] != first[0]['speaker_id']
    assert not any(key.startswith('final:batch:a/') for key in fresh['bindings'])


def test_manual_conflicting_name_prevents_link():
    state, first = run({}, 'a', {'SPEAKER_00': [1.0, 0.0]})
    receipt = {
        'speakers': {str(first[0]['speaker_id']): {'person_id': 'person-a'}},
        'segments': {'bSPEAKER_00': {'person_id': 'person-b'}},
    }
    _, second = run(state, 'b', {'SPEAKER_00': [1.0, 0.0]}, existing=first, receipt=receipt)
    assert second[0]['speaker_id'] != first[0]['speaker_id']


def test_registry_is_encrypted_at_every_level_and_wrong_user_abstains():
    state, _ = run({}, 'a', {'SPEAKER_00': [1.0, 0.0]})
    encoded = encode_registry(state, 'synthetic-user')
    assert 'embedding' not in encoded
    assert decode_registry(encoded, 'synthetic-user') == state
    assert decode_registry(encoded, 'different-user') == {}
    assert decode_registry(state, 'synthetic-user') == {}
    assert decode_registry(json.dumps(state), 'synthetic-user') == {}


def test_bounded_registry_keeps_committed_mapping():
    state, first = run({}, 'a', {'SPEAKER_00': [1.0, 0.0]})
    for i in range(MAX_BINDINGS + 3):
        state, new = run(state, f'u{i}', {'SPEAKER_00': [0.0, 1.0]}, existing=first, enabled=False)
    assert len(state['bindings']) <= MAX_BINDINGS
    assert len(state['voices']) <= MAX_VOICES
    _, retry = run(state, 'a', {'SPEAKER_00': [0.0, 1.0]}, existing=first)
    assert retry[0]['speaker_id'] == first[0]['speaker_id']


def test_owner_claims_are_arbitrated_after_linking():
    segments = [{'speaker_id': 1, 'is_user': True}, {'speaker_id': 2, 'is_user': True}]
    assert not any(s['is_user'] for s in arbitrate_linked_owner_claims(segments, {}))
    receipt = {'speakers': {'1': {'is_user': True}}}
    result = arbitrate_linked_owner_claims(segments, receipt)
    assert [s['is_user'] for s in result] == [True, False]
    assert all(s['is_user'] for s in arbitrate_linked_owner_claims([segments[0], dict(segments[0])], {}))


@pytest.mark.parametrize('reverse', [False, True])
def test_assignment_atomic_continuity_and_private_evidence_consumed(reverse):

    store = StrictFirestore()
    chunks = [chunk('a', 1000, text='First synthetic sentence.'), chunk('b', 1060, text='Second synthetic sentence.')]
    for item in chunks:
        item['_batch_voice_evidence'] = evidence(item['id'], {'SPEAKER_00': [1.0, 0.0]})
        item['transcript_segments'][0].update(speaker='SPEAKER_00', speaker_id_scope='final:batch:' + item['id'])
    for item in reversed(chunks) if reverse else chunks:
        result, _, _ = intake(store, item)
    assert len({s['speaker_id'] for s in result['transcript_segments']}) == 1
    assert '_batch_voice_evidence' not in result
    assert isinstance(result[FIELD], str)
    before = {s['speaker_id_scope']: s['speaker_id'] for s in result['transcript_segments']}
    for item in chunks:
        result, _, survivors = intake(store, item)
        assert not survivors
        assert {s['speaker_id_scope']: s['speaker_id'] for s in result['transcript_segments']} == before
    stored = [row for key, row in store.rows.items() if key[2] == 'conversations' and not row.get('deleted')]
    assert all('_batch_voice_evidence' not in row and isinstance(row[FIELD], str) for row in stored)


def test_allocator_never_overwrites_existing_scope_binding():
    allocator = ConversationSpeakerIdAllocator()
    allocator.bind('final:batch:a', 'SPEAKER_00', 3)
    allocator.bind('final:batch:a', 'SPEAKER_0', 5)
    assert allocator.lookup('final:batch:a', 'SPEAKER_0') == 3


def test_segment_receipt_reserves_owner_before_manual_projection():
    segments = [
        {'id': 'manual', 'speaker_id': 1, 'is_user': False},
        {'id': 'automatic', 'speaker_id': 2, 'is_user': True},
    ]
    receipt = {'segments': {'manual': {'is_user': True, 'speaker_id': 1}}}
    result = arbitrate_linked_owner_claims(segments, receipt)
    assert not result[1]['is_user']


def test_manual_owner_rejection_vetoes_owner_named_link():
    state, first = run({}, 'a', {'SPEAKER_00': [1.0, 0.0]})
    allocator = ConversationSpeakerIdAllocator()
    allocator.hydrate(first)
    second = [{'id': 'new', 'speaker': 'SPEAKER_00', 'speaker_id_scope': 'final:batch:b', 'is_user': True}]
    receipt = {'speakers': {'0': {'is_user': False, 'rejection': {'kind': 'not_me'}}}}
    link_unit_voices(
        state, evidence('b', {'SPEAKER_00': [1.0, 0.0]}), second, allocator, receipt=receipt, existing=first
    )
    allocator.assign(second[0])
    assert second[0]['speaker_id'] != first[0]['speaker_id']


def test_ciphertext_copied_to_another_conversation_cannot_import_voice_links():
    state, first = run({}, 'a', {'SPEAKER_00': [1.0, 0.0]})
    state['conversation_id'] = 'original'
    allocator = ConversationSpeakerIdAllocator()
    incoming = [{'speaker': 'SPEAKER_00', 'speaker_id_scope': 'final:batch:b'}]
    moved = link_unit_voices(
        state, evidence('b', {'SPEAKER_00': [0.0, 1.0]}), incoming, allocator, conversation_id='different'
    )
    assert moved['conversation_id'] == 'different'
    assert set(moved['bindings']) == {'final:batch:b/SPEAKER_0'}
    assert moved['voices']['0']['embedding'] == [0.0, 1.0]


@pytest.mark.parametrize('manual', [False, True])
def test_native_record_replacement_links_units_and_keeps_manual_decisions(manual):

    store = StrictFirestore()
    current = recording()
    if manual:
        current['manual_speaker_assignments'] = {'segments': {'old': {'is_user': True, 'generation': 1}}}
    store.rows[('users', 'u', 'conversations', 'record')] = current
    all_ids = []
    for index in range(2):
        value = incoming()
        value.update(id=f'unit-{index}', finished_at=datetime.fromtimestamp(102 + index * 2, timezone.utc))
        value['started_at'] = datetime.fromtimestamp(100 + index * 2, timezone.utc)
        scope = f'final:batch:unit-{index}'
        value['transcript_segments'][0].update(id=f'new-{index}', speaker_id_scope=scope)
        value['_batch_voice_evidence'] = evidence(f'unit-{index}', {'SPEAKER_00': [1.0, 0.0]})
        value['_batch_replace_live'] = {'start': 100 + index * 2, 'end': 102 + index * 2}
        result, _, _ = intake(store, value, target_id='record')
        all_ids.append(result['transcript_segments'][-1]['speaker_id'])
    assert len(set(all_ids)) == 1
    assert len(decode_registry(result[FIELD], 'u')['bindings']) == 2
    if manual:
        assert result['transcript_segments'][0]['id'] == 'old'
        assert result['transcript_segments'][0]['is_user']
    retried, _, _ = intake(store, value, target_id='record')
    assert {s['speaker_id'] for s in retried['transcript_segments']} == set(all_ids)


def test_native_unsafe_manual_remap_never_commits_unapplied_voice_anchors():

    store = StrictFirestore()
    current = recording(has_transcript_corrections=True)
    current['manual_speaker_assignments'] = {'segments': {'old': {'is_user': True, 'generation': 1}}}
    store.rows[('users', 'u', 'conversations', 'record')] = current
    value = incoming()
    value.update(id='unsafe', _batch_replace_live={'start': 100, 'end': 102})
    first = value['transcript_segments'][0]
    first.update(end=1, speaker_id_scope='final:batch:unsafe')
    value['transcript_segments'].append({**first, 'id': 'other', 'start': 1, 'end': 2, 'speaker': 'SPEAKER_01'})
    value['_batch_voice_evidence'] = evidence('unsafe', {'SPEAKER_00': [1.0, 0.0], 'SPEAKER_01': [0.0, 1.0]})
    result, _, _ = intake(store, value, target_id='record')
    assert FIELD not in result
    assert result['transcript_segments'][0]['id'] == 'old'
    assert result['transcript_segments'][0]['is_user']
    assert result['transcript_segments'][0]['speaker'].startswith('BATCH_UNASSIGNED_')
