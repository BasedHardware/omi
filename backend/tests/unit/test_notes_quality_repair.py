"""Reservation uses the strict transaction fixture; no account data or services."""

import pytest
from database import notes_quality_repair as repair
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

PATH = ('users', 'u', 'conversations', 'c')


def test_one_reservation_survives_a_failed_model_and_repeated_attempts():
    client = StrictFirestore(
        {PATH: {'sync_content_revision': 3, 'notes_llm_input_hash': 'input', 'notes_llm_output_hash': 'output'}}
    )
    arguments = dict(expected_revision=3, expected_input='input', expected_output='output', firestore_client=client)
    assert repair.claim('u', 'c', 'content-key', **arguments)
    assert not repair.claim('u', 'c', 'content-key', **arguments)
    assert client.rows[PATH]['notes_quality_repair_input_hash'] == 'content-key'
    assert len(client.transactions[0].updates) == 1
    assert not client.transactions[1].updates


@pytest.mark.parametrize(
    'change',
    [
        {'status': 'failed'},
        {'dream_duplicate_of': 'duplicate'},
        {'sync_bridge_pending': {'expires_at': 99999999999}},
        {'deleted': True},
        {'discarded': True},
        {'relevance_decision': {'verdict': 'discard'}},
        {'sync_content_revision': 4},
        {'notes_llm_input_hash': 'new'},
        {'notes_llm_output_hash': 'new'},
    ],
)
def test_hidden_or_changed_rows_cannot_reserve(change):
    client = StrictFirestore(
        {
            PATH: {
                'sync_content_revision': 3,
                'notes_llm_input_hash': 'input',
                'notes_llm_output_hash': 'output',
                **change,
            }
        }
    )
    assert not repair.claim(
        'u',
        'c',
        'content-key',
        expected_revision=3,
        expected_input='input',
        expected_output='output',
        firestore_client=client,
    )
    assert not client.transactions[0].updates
