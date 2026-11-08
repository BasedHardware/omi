"""The deletion-feedback write updates an existing marker and never creates one.

A feedback-only ``account_deletions/{uid}`` document has no ``wipe_status``. The access fence
reads that as an invalid status, which denies the account with no restore path. The feedback
write therefore must not be a merge ``set``, which would create such a document when the
deletion intent write failed or had not yet run.
"""

import os
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

import pytest
from google.api_core.exceptions import NotFound

import database.users as users


def test_feedback_write_updates_and_never_sets_marker():
    ref = MagicMock()
    with patch.object(users, 'account_deletion_document', return_value=ref):
        users.set_user_deletion_feedback('uid1', 'too_expensive', 'details')

    ref.set.assert_not_called()
    ref.update.assert_called_once()
    payload = ref.update.call_args.args[0]
    assert payload['reason'] == 'too_expensive'
    assert payload['reason_details'] == 'details'
    assert 'timestamp' in payload


def test_feedback_write_on_missing_marker_raises_not_found_for_caller_to_ignore():
    ref = MagicMock()
    ref.update.side_effect = NotFound('missing')
    with patch.object(users, 'account_deletion_document', return_value=ref):
        with pytest.raises(NotFound):
            users.set_user_deletion_feedback('uid1', None, None)

    ref.set.assert_not_called()
