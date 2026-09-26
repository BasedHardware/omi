from utils.stt.voiceprints import usable_person_voiceprint


def test_usable_person_voiceprint_valid_v3():
    emb = [0.1, 0.2, 0.3]
    person = {'speaker_embedding': emb, 'speech_samples': ['sample1.wav'], 'speech_samples_version': 3}
    assert usable_person_voiceprint(person) == emb


def test_usable_person_voiceprint_higher_version():
    emb = [0.1, 0.2, 0.3]
    person = {'speaker_embedding': emb, 'speech_samples': ['sample1.wav'], 'speech_samples_version': 4}
    assert usable_person_voiceprint(person) == emb


def test_usable_person_voiceprint_older_version():
    emb = [0.1, 0.2, 0.3]
    person = {'speaker_embedding': emb, 'speech_samples': ['sample1.wav'], 'speech_samples_version': 2}
    assert usable_person_voiceprint(person) is None


def test_usable_person_voiceprint_null_version_does_not_raise():
    emb = [0.1, 0.2, 0.3]
    person = {'speaker_embedding': emb, 'speech_samples': ['sample1.wav'], 'speech_samples_version': None}
    assert usable_person_voiceprint(person) is None


def test_usable_person_voiceprint_missing_version_defaults_safely():
    emb = [0.1, 0.2, 0.3]
    person = {'speaker_embedding': emb, 'speech_samples': ['sample1.wav']}
    assert usable_person_voiceprint(person) is None


def test_usable_person_voiceprint_non_int_version():
    emb = [0.1, 0.2, 0.3]
    person = {'speaker_embedding': emb, 'speech_samples': ['sample1.wav'], 'speech_samples_version': '3'}
    assert usable_person_voiceprint(person) is None
    person_bool = {'speaker_embedding': emb, 'speech_samples': ['sample1.wav'], 'speech_samples_version': True}
    assert usable_person_voiceprint(person_bool) is None


def test_usable_person_voiceprint_missing_samples_or_embedding():
    emb = [0.1, 0.2, 0.3]
    assert (
        usable_person_voiceprint({'speaker_embedding': emb, 'speech_samples': [], 'speech_samples_version': 3}) is None
    )
    assert (
        usable_person_voiceprint(
            {'speaker_embedding': None, 'speech_samples': ['sample1.wav'], 'speech_samples_version': 3}
        )
        is None
    )
    assert usable_person_voiceprint({'speech_samples': ['sample1.wav'], 'speech_samples_version': 3}) is None
