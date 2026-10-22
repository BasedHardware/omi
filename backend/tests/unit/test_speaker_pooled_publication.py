"""Pooled teaching uses the existing version/receipt-fenced transaction."""

from copy import deepcopy

import numpy as np
import pytest

from database import users
from tests.unit.test_taught_speaker_persistence import world, teach


def test_pooled_publication_and_correction_keep_unrelated_contribution(world, monkeypatch):
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', 'serve')
    teach()
    account, person = world.person_path[1], world.person_path[-1]
    original = world.conversation_path[-1]
    source = world.store.rows[world.conversation_path]
    world.store.rows[(*world.conversation_path[:-1], 'second')] = deepcopy(source)
    row = world.store.rows[world.person_path]
    retired = users.replace_person_speech_profile(
        account,
        person,
        row.get('updated_at'),
        'second.wav',
        '',
        [0, 1, 0],
        'second',
        ['s1', 's2'],
        expected_receipt_generation=0,
    )
    row = world.store.rows[world.person_path]
    assert retired == []
    assert np.allclose(row['speaker_embedding'], [2**-0.5, 2**-0.5, 0])
    assert len(row['person_voice_confirmations']) == 2
    removed = users.invalidate_person_speech_profile(account, person, original, ['s1'])
    row = world.store.rows[world.person_path]
    assert removed == world.uploads
    assert row['speaker_embedding'] == [0, 1, 0]
    assert row['speech_samples'] == ['second.wav']
    assert users.remove_person_speech_sample(account, person, 'second.wav')
    assert world.store.rows[world.person_path]['speaker_embedding'] is None


@pytest.mark.parametrize('mode', ['off', 'shadow'])
def test_legacy_replacement_keeps_serving_outside_cohort(world, monkeypatch, mode):
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', mode)
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE_SERVE_PERCENT', '0')
    teach()
    assert 'person_voice_confirmations' not in world.store.rows[world.person_path]


def test_rollback_replacement_retires_pool_metadata(world, monkeypatch):
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', 'serve')
    teach()
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', 'off')
    account, person = world.person_path[1], world.person_path[-1]
    row = world.store.rows[world.person_path]
    users.replace_person_speech_profile(
        account,
        person,
        row['updated_at'],
        'new.wav',
        '',
        [0, 1, 0],
        world.conversation_path[-1],
        ['s1', 's2'],
        expected_receipt_generation=0,
    )
    row = world.store.rows[world.person_path]
    assert row['person_voice_confirmations'] is None
    assert row['speaker_embedding'] == [0, 1, 0]
    assert users.invalidate_person_speech_profile(account, person, world.conversation_path[-1], ['s1']) == ['new.wav']
