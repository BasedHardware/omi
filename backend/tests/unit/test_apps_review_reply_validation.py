"""reply_to_review must return 422 (not 500) when the 'response' field is missing/empty.

routers/apps.py imports cleanly thanks to Tier-1 import purity (lazy clients) plus the
conftest tiktoken stub. We import it directly and call reply_to_review with its
collaborators patched.
"""

from unittest.mock import MagicMock, patch

import pydantic
import pytest
from fastapi import HTTPException

from routers import apps as apps_mod
from routers.apps import ReplyToReviewRequest


def _call(data):
    """Drive reply_to_review past the app/owner/reviewer gates so we reach the response check."""
    with patch.object(apps_mod, 'get_available_app_by_id', return_value={'id': 'app-1', 'uid': 'uid1'}), patch.object(
        apps_mod, 'App', return_value=MagicMock(uid='uid1', private=False, name='Test App')
    ), patch.object(apps_mod, 'get_specific_user_review', return_value={'uid': 'r1', 'score': 5}), patch.object(
        apps_mod, 'set_app_review'
    ), patch.object(
        apps_mod, 'send_app_review_reply_notification'
    ):
        return apps_mod.reply_to_review('app-1', data, uid='uid1')


def test_missing_response_rejected_by_pydantic():
    # FastAPI returns 422 automatically; at model level Pydantic raises ValidationError.
    with pytest.raises(pydantic.ValidationError):
        ReplyToReviewRequest(reviewer_uid='r1')


def test_empty_or_blank_response_returns_422():
    for bad in ('', '   '):
        with pytest.raises(HTTPException) as e:
            _call(ReplyToReviewRequest(reviewer_uid='r1', response=bad))
        assert e.value.status_code == 422


def test_non_string_response_rejected_by_pydantic():
    with pytest.raises(pydantic.ValidationError):
        ReplyToReviewRequest(reviewer_uid='r1', response=123)


def test_valid_response_succeeds():
    result = _call(ReplyToReviewRequest(reviewer_uid='r1', response='Thanks for the feedback'))
    assert result['status'] == 'ok'
