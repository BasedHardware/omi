"""_add_sample_transaction pads/aligns speech_sample_transcripts (migrated to the WP2 storage port).

The transaction body now takes a neutral transaction handle + logical path, so the test drives it
with the in-memory FakeDocumentStore (which satisfies the get/update surface) and asserts on the
resulting document state. Real-backend parity is covered by the live contract test.
"""

import os

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import database.users as users_db
from tests.store_fakes import FakeDocumentStore

_PATH = 'users/u1/people/p1'


def _add(person_data, sample, transcript, max_samples, *, exists=True):
    store = FakeDocumentStore()
    if exists:
        store.set(_PATH, person_data)
    result = users_db._add_sample_transaction(store, _PATH, sample, transcript, max_samples)
    doc = store.get(_PATH).to_dict() if store.exists(_PATH) else None
    return result, doc


def test_add_sample_transaction_pads_transcripts_for_v1_samples():
    result, doc = _add(
        {'speech_samples': ['sample-a.wav', 'sample-b.wav'], 'speech_sample_transcripts': []},
        'sample-c.wav',
        transcript='we ride at dawn',
        max_samples=5,
    )
    assert result is True
    assert doc['speech_samples'] == ['sample-a.wav', 'sample-b.wav', 'sample-c.wav']
    assert doc['speech_sample_transcripts'] == ['', '', 'we ride at dawn']
    assert doc['speech_samples_version'] == 3
    assert 'updated_at' in doc


def test_add_sample_transaction_already_aligned_transcripts():
    result, doc = _add(
        {'speech_samples': ['sample-a.wav', 'sample-b.wav'], 'speech_sample_transcripts': ['first', 'second']},
        'sample-c.wav',
        transcript='third',
        max_samples=5,
    )
    assert result is True
    assert doc['speech_samples'] == ['sample-a.wav', 'sample-b.wav', 'sample-c.wav']
    assert doc['speech_sample_transcripts'] == ['first', 'second', 'third']
    assert doc['speech_samples_version'] == 3


def test_add_sample_transaction_max_samples_reached():
    result, doc = _add(
        {'speech_samples': ['a.wav', 'b.wav'], 'speech_sample_transcripts': ['a', 'b']},
        'c.wav',
        transcript='c',
        max_samples=2,
    )
    assert result is False
    assert doc['speech_samples'] == ['a.wav', 'b.wav']  # unchanged
    assert 'speech_samples_version' not in doc


def test_add_sample_transaction_person_not_found():
    result, doc = _add({}, 'sample-x.wav', transcript='ghost', max_samples=5, exists=False)
    assert result is False
    assert doc is None
