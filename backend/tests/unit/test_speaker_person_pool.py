from utils.speakers.person_pool import MAX_CONTRIBUTIONS, pool_profile, retract_profile
import numpy as np
import pytest


def profile(conversation, vector):
    return {
        'speech_sample_source': {'conversation_id': conversation, 'segment_ids': ['s']},
        'speaker_embedding': vector,
        'speech_samples': [f'{conversation}.wav'],
        'speech_sample_transcripts': [''],
    }


def test_quality_rejection_labels_are_bounded():
    from utils.speakers.person_pool import QUALITY, PersonVoiceQualityError, reject

    unknown = QUALITY.labels(outcome='unknown')._value.get()
    with pytest.raises(PersonVoiceQualityError):
        reject('unrecognized_synthetic_reason')
    assert QUALITY.labels(outcome='unknown')._value.get() == unknown + 1
    assert ('unrecognized_synthetic_reason',) not in QUALITY._metrics


def test_pool_is_centroid_retry_idempotent_and_undo_restores_other_voice_evidence():
    person, removed = pool_profile({}, profile('a', [1, 0]))
    assert removed == []
    person, removed = pool_profile(person, profile('b', [0.8, 0.6]))
    assert np.allclose(person['speaker_embedding'], np.array([1.8, 0.6]) / np.linalg.norm([1.8, 0.6]))
    assert removed == []
    person, removed = pool_profile(person, profile('b', [0.8, 0.6]))
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
    person, _ = pool_profile(legacy, profile('new', [0.8, 0.6]))
    update, removed = retract_profile(person, ['legacy'], ['s'])
    assert np.allclose(update['speaker_embedding'], [0.8, 0.6]) and removed == ['legacy.wav']
    enrolled = {'speaker_embedding': [1, 0], 'speech_samples': ['base.wav'], 'speech_samples_version': 3}
    person, _ = pool_profile(enrolled, profile('new', [0.8, 0.6]))
    update, removed = retract_profile(person, ['new'], ['s'])
    assert update['speaker_embedding'] == [1, 0] and removed == ['new.wav']


def test_pre_v3_print_never_contaminates_pool():
    person, removed = pool_profile(
        {'speaker_embedding': [1, 0], 'speech_samples': ['old.wav'], 'speech_samples_version': 2},
        profile('new', [0.8, 0.6]),
    )
    assert np.allclose(person['speaker_embedding'], [0.8, 0.6]) and removed == ['old.wav']


def test_sample_deletion_retracts_only_its_vector():
    from utils.speakers.person_pool import remove_sample

    person, _ = pool_profile({}, profile('a', [1, 0]))
    person, _ = pool_profile(person, profile('b', [0.8, 0.6]))
    update = remove_sample(person, 'a.wav')
    assert np.allclose(update['speaker_embedding'], [0.8, 0.6])
    assert update['speech_samples'] == ['b.wav']


def test_manual_correction_retracts_donor_contribution_without_erasing_other_samples():
    from datetime import datetime, timezone
    from utils.person_evidence import person_updates_for_assignment

    person, _ = pool_profile({}, profile('donor', [1, 0]))
    person, _ = pool_profile(person, profile('other', [0.8, 0.6]))
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
    assert np.allclose(updates['p']['speaker_embedding'], [0.8, 0.6])
    assert removed == ['donor.wav']


def test_legacy_multisample_provenance_is_retained_and_sample_removal_keeps_remaining_source():
    from utils.speakers.person_pool import remove_sample

    legacy = {
        **profile('legacy', [1, 0]),
        'speech_samples_version': 3,
        'speech_samples': ['old-a.wav', 'old-b.wav'],
        'speech_sample_transcripts': ['', ''],
    }
    pooled, removed = pool_profile(legacy, profile('new', [0.8, 0.6]))
    assert removed == []
    assert pooled['speech_samples'] == ['old-a.wav', 'old-b.wav', 'new.wav']
    remaining = remove_sample(pooled, 'new.wav')
    assert remaining['speech_sample_source'] == legacy['speech_sample_source']
    assert remaining['speaker_embedding'] == [1, 0]


def test_migrated_legacy_aggregate_retracts_and_replaces_as_one_conversation_contribution():
    legacy = {
        **profile('legacy', [1, 0]),
        'speech_samples_version': 3,
        'speech_samples': ['old-a.wav', 'old-b.wav'],
        'speech_sample_transcripts': ['', ''],
    }
    pooled, _ = pool_profile(legacy, profile('new', [0.8, 0.6]))
    from utils.speech_profile_deletion import teaching_segment_ids_for_deleted_sample

    assert teaching_segment_ids_for_deleted_sample(pooled, 'legacy') == ['s']
    undone, removed = retract_profile(pooled, ['legacy'], ['s'])
    assert np.allclose(undone['speaker_embedding'], [0.8, 0.6])
    assert set(removed) == {'old-a.wav', 'old-b.wav'}
    replaced, removed = pool_profile(legacy, profile('legacy', [0.8, 0.6]))
    assert np.allclose(replaced['speaker_embedding'], [0.8, 0.6])
    assert set(removed) == {'old-a.wav', 'old-b.wav'}
