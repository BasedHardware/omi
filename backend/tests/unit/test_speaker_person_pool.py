from utils.speakers.person_pool import MAX_CONTRIBUTIONS, pool_profile, retract_profile
import numpy as np


def profile(conversation, vector):
    return {
        'speech_sample_source': {'conversation_id': conversation, 'segment_ids': ['s']},
        'speaker_embedding': vector,
        'speech_samples': [f'{conversation}.wav'],
        'speech_sample_transcripts': [''],
    }


def test_pool_is_centroid_retry_idempotent_and_undo_restores_other_voice_evidence():
    person, removed = pool_profile({}, profile('a', [1, 0]))
    assert removed == []
    person, removed = pool_profile(person, profile('b', [0, 1]))
    assert np.allclose(person['speaker_embedding'], [2**-0.5, 2**-0.5])
    assert removed == []
    person, removed = pool_profile(person, profile('b', [0, 1]))
    assert len(person['person_voice_confirmations']) == 2
    assert removed == []
    update, removed = retract_profile(person, ['b'], ['s'])
    assert update['speaker_embedding'] == [1, 0]
    assert update['speech_samples'] == ['a.wav']
    assert removed == ['b.wav']
    assert retract_profile(person, ['other'], ['s']) == ({}, [])


def test_pool_bounded_and_evicted_sample_only_is_retired():
    person = {}
    for i in range(MAX_CONTRIBUTIONS + 1):
        person, removed = pool_profile(person, profile(str(i), [1, 0]))
    assert len(person['person_voice_confirmations']) == MAX_CONTRIBUTIONS
    assert removed == ['0.wav']


def test_legacy_taught_print_is_retractable_but_explicit_enrollment_survives():
    legacy = {**profile('legacy', [1, 0]), 'speech_samples_version': 3}
    person, _ = pool_profile(legacy, profile('new', [0, 1]))
    update, removed = retract_profile(person, ['legacy'], ['s'])
    assert update['speaker_embedding'] == [0, 1] and removed == ['legacy.wav']
    enrolled = {'speaker_embedding': [1, 0], 'speech_samples': ['base.wav'], 'speech_samples_version': 3}
    person, _ = pool_profile(enrolled, profile('new', [0, 1]))
    update, removed = retract_profile(person, ['new'], ['s'])
    assert update['speaker_embedding'] == [1, 0] and removed == ['new.wav']


def test_pre_v3_print_never_contaminates_pool():
    person, removed = pool_profile(
        {'speaker_embedding': [1, 0], 'speech_samples': ['old.wav'], 'speech_samples_version': 2},
        profile('new', [0, 1]),
    )
    assert person['speaker_embedding'] == [0, 1] and removed == ['old.wav']


def test_sample_deletion_retracts_only_its_vector():
    from utils.speakers.person_pool import remove_sample

    person, _ = pool_profile({}, profile('a', [1, 0]))
    person, _ = pool_profile(person, profile('b', [0, 1]))
    update = remove_sample(person, 'a.wav')
    assert update['speaker_embedding'] == [0, 1]
    assert update['speech_samples'] == ['b.wav']


def test_manual_correction_retracts_donor_contribution_without_erasing_other_samples():
    from datetime import datetime, timezone
    from utils.person_evidence import person_updates_for_assignment

    person, _ = pool_profile({}, profile('donor', [1, 0]))
    person, _ = pool_profile(person, profile('other', [0, 1]))
    updates, removed = person_updates_for_assignment(
        {'p': person},
        {'p'},
        None,
        [],
        'manual',
        'canonical',
        ['s'],
        datetime.now(timezone.utc),
        {},
        [],
        source_conversation_ids=['donor'],
    )
    assert updates['p']['speaker_embedding'] == [0, 1]
    assert removed == ['donor.wav']
