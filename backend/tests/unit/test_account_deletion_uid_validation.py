"""#20110 — uid validation on the deletion-marker fence.

A '/' or '\\' or traversal in uid turns document() into a subcollection path;
the fence now rejects before the path is built, and get_user_deletion_wipe_status
fails open to None rather than crashing an auth check.
"""

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import pytest

import database.account_deletion_marker as marker
import database.account_deletion_transitions as transitions

BAD_UIDS = ['', '   ', 'a/b', 'a\\b', '../x', 'a\x00b', 'a\nb', 'x' * 200, None, 42]


def test_validate_uid_rejects_unsafe():
    for bad in BAD_UIDS:
        with pytest.raises(ValueError):
            marker._validate_uid(bad)


def test_validate_uid_accepts_normal():
    assert marker._validate_uid('uid-abc_123') == 'uid-abc_123'


def test_document_ref_rejects_unsafe_uid():
    for bad in BAD_UIDS:
        with pytest.raises(ValueError):
            marker.account_deletion_document(bad, firestore_client=MagicMock())


def test_wipe_status_returns_none_on_malformed_uid():
    # The fence must not crash the auth check — malformed uid => no marker.
    for bad in BAD_UIDS:
        assert marker.get_user_deletion_wipe_status(bad, firestore_client=MagicMock()) is None


def test_migration_journals_reject_unsafe_uid():
    for bad in BAD_UIDS:
        with pytest.raises(ValueError):
            transitions.read_agent_vm_migration_journals(bad)


def test_wipe_status_reads_marker_for_valid_uid():
    snap = MagicMock()
    snap.exists = True
    snap.to_dict.return_value = {'wipe_status': 'completed'}
    coll = MagicMock()
    coll.document.return_value.get.return_value = snap
    client = MagicMock()
    client.collection.return_value = coll
    assert marker.get_user_deletion_wipe_status('u1', firestore_client=client) == 'completed'
