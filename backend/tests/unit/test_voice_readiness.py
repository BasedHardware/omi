"""Readiness derives from usable stored evidence, never an enrollment promise."""

import pytest
from models.other import Person
from routers import users


@pytest.mark.parametrize(
    'evidence,expected',
    [
        ({}, 'unknown'),
        ({'speech_samples': []}, 'not_learned'),
        ({'speech_samples': ['s']}, 'unknown'),
        ({'speech_samples': ['s'], 'speech_samples_version': 2, 'speaker_embedding': [1, 0]}, 'unknown'),
        ({'speech_samples': ['s'], 'speech_samples_version': 3}, 'saved_sample_awaiting_embedding'),
        ({'speech_samples': ['s'], 'speech_samples_version': 3, 'speaker_embedding': [1, 0]}, 'ready'),
        ({'speech_samples': ['s'], 'speech_samples_version': 3, 'speaker_embedding': [0, 0]}, 'unknown'),
        ({'speech_samples': ['s'], 'speech_samples_version': 3, 'speaker_embedding': [float('nan')]}, 'unknown'),
        ({'speech_samples': ['s'], 'speech_samples_version': 3, 'speaker_embedding': ['1']}, 'unknown'),
        (
            {
                'speech_samples': [],
                'speech_samples_version': 3,
                'speaker_embedding': [1, 0],
                'voice_readiness': 'ready',
            },
            'not_learned',
        ),
    ],
)
def test_readiness(evidence, expected):
    person = Person(id='synthetic', name='Test', **evidence)
    assert person.voice_readiness == expected
    assert 'speaker_embedding' not in person.model_dump()


def test_people_response_readiness_is_independent_of_playback_url_availability(monkeypatch):
    evidence = dict(
        id='p', name='Synthetic', speech_samples=['stored.wav'], speech_samples_version=3, speaker_embedding=[1, 0]
    )
    monkeypatch.setattr(users, 'get_people', lambda uid: [evidence])
    monkeypatch.setattr(users, 'get_person', lambda uid, pid: evidence)
    monkeypatch.setattr(users, 'get_speech_sample_signed_urls', lambda paths: [])
    listed = users.get_all_people(uid='u')
    single = users.get_single_person('p', include_speech_samples=True, uid='u')
    assert listed[0].voice_readiness == single.voice_readiness == 'ready'
    assert listed[0].speech_samples == single.speech_samples == []
    assert Person(**listed[0].model_dump()).voice_readiness == 'ready'


def test_get_all_people_skips_malformed_row(monkeypatch):
    monkeypatch.setattr(
        users,
        'get_people',
        lambda uid: [
            {'id': 'p1', 'name': 'Alex', 'speech_samples': [], 'speech_samples_version': 3},
            {'id': 'bad'},
        ],
    )
    monkeypatch.setattr(users, 'get_speech_sample_signed_urls', lambda paths: [])
    listed = users.get_all_people(uid='u', include_speech_samples=False)
    assert [person.id for person in listed] == ['p1']
