"""Real bounded projection-debt writes must work through the hermetic store API."""

from datetime import datetime

import pytest


def test_real_projection_debt_writer_accepts_explicit_no_retry(fake_firestore):
    from database import record_projection_rebuild as debt

    debt.mark_due('synthetic-owner', 'synthetic-capture', firestore_client=fake_firestore)
    row = (
        fake_firestore.collection(debt.COLLECTION)
        .document(debt.marker_id('synthetic-owner', 'synthetic-capture'))
        .get()
        .to_dict()
    )
    assert row['kind'] == debt.KIND
    assert row['owner_id'] == 'synthetic-owner'
    assert row['conversation_id'] == 'synthetic-capture'
    assert isinstance(row['requested_at'], datetime)


def test_explicit_no_retry_preserves_parent_merge_and_children(fake_firestore):
    parent = fake_firestore.collection('synthetic-parents').document('parent')
    parent.collection('children').document('child').set({'retained': True})
    parent.set({'first': 1}, merge=True, timeout=5, retry=None)
    parent.set({'second': 2}, merge=True, timeout=5, retry=None)
    row = parent.get().to_dict()
    assert row['first'] == 1 and row['second'] == 2
    assert parent.collection('children').document('child').get().to_dict() == {'retained': True}


def test_retry_policy_is_not_silently_simulated(fake_firestore):
    ref = fake_firestore.collection('synthetic-parents').document('unsupported')
    with pytest.raises(NotImplementedError, match='retry policies'):
        ref.set({'value': 1}, retry=object())
    assert not ref.get().exists
