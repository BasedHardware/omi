"""A deletion-feedback write with no marker raises NotFound and creates nothing.

The feedback write is update-only, so it never creates ``account_deletions/{uid}``. When
the marker is missing, the write raises ``NotFound``; ``start_account_deletion`` logs and
ignores that. This pins the contract so a later change cannot swap the update for a
create or swallow the error inside the writer.
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


def test_feedback_write_on_missing_marker_raises_not_found_for_caller_to_ignore():
    ref = MagicMock()
    ref.update.side_effect = NotFound('missing')
    with patch.object(users, 'account_deletion_document', return_value=ref):
        with pytest.raises(NotFound):
            users.set_user_deletion_feedback('uid1', None, None)

    ref.set.assert_not_called()
    ref.create.assert_not_called()
