"""Advice feedback: database.set_advice_feedback and POST /v1/advice/{advice_id}/feedback.

Users rate a proactive-coaching advice item (1 = helpful, -1 = not helpful, 0 = clear), with an
optional reason, stored as a `feedback` object on the advice doc. This mirrors the existing chat
message feedback channel and reuses update_advice's deletion-race hardening (existence check ->
NotFound guard -> None on re-read), so a delete concurrent with the rating yields 404, not 500.

Test isolation: database.advice and routers.advice import cleanly, so the modules are imported
normally and the collection is patched via patch.object(advice, '_user_col') (no sys.modules).
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from google.api_core.exceptions import NotFound
from pydantic import ValidationError

import database.advice as advice
import routers.advice as r
from models.advice import Advice, AdviceFeedback


def _snap(exists, data=None):
    snap = MagicMock()
    snap.exists = exists
    snap.to_dict.return_value = data
    return snap


def _wire(get_results, update_exc=None):
    """A mocked advice collection whose document().get() yields the given snapshots in order."""
    ref = MagicMock()
    ref.get.side_effect = list(get_results)
    if update_exc is not None:
        ref.update.side_effect = update_exc
    col = MagicMock()
    col.document.return_value = ref
    return col, ref


# --- database.set_advice_feedback ---


class TestSetAdviceFeedback:
    def test_thumbs_up_stores_rating_and_reason(self):
        col, ref = _wire([_snap(True), _snap(True, {"content": "x", "is_read": False})])
        with patch.object(advice, "_user_col", return_value=col):
            result = advice.set_advice_feedback("u", "a1", rating=1, reason="great tip")
        assert result["id"] == "a1"
        payload = ref.update.call_args.args[0]
        assert payload["feedback"]["rating"] == 1
        assert payload["feedback"]["reason"] == "great tip"
        assert "rated_at" in payload["feedback"]
        assert "updated_at" in payload

    def test_thumbs_down(self):
        col, ref = _wire([_snap(True), _snap(True, {"content": "x"})])
        with patch.object(advice, "_user_col", return_value=col):
            advice.set_advice_feedback("u", "a1", rating=-1, reason="not useful")
        assert ref.update.call_args.args[0]["feedback"]["rating"] == -1

    def test_rating_zero_clears_feedback(self):
        col, ref = _wire([_snap(True), _snap(True, {"content": "x"})])
        with patch.object(advice, "_user_col", return_value=col):
            advice.set_advice_feedback("u", "a1", rating=0)
        assert ref.update.call_args.args[0]["feedback"] is None

    def test_missing_advice_returns_none_without_writing(self):
        col, ref = _wire([_snap(False)])
        with patch.object(advice, "_user_col", return_value=col):
            assert advice.set_advice_feedback("u", "a1", rating=1) is None
        ref.update.assert_not_called()

    def test_deleted_before_update_returns_none(self):
        col, ref = _wire([_snap(True)], update_exc=NotFound("gone"))
        with patch.object(advice, "_user_col", return_value=col):
            assert advice.set_advice_feedback("u", "a1", rating=1) is None

    def test_deleted_after_update_returns_none(self):
        col, ref = _wire([_snap(True), _snap(False, None)])
        with patch.object(advice, "_user_col", return_value=col):
            assert advice.set_advice_feedback("u", "a1", rating=1) is None


# --- POST /v1/advice/{advice_id}/feedback ---


class TestFeedbackEndpoint:
    def test_returns_updated_advice(self):
        payload = {"id": "a1", "content": "x", "feedback": {"rating": 1}}
        with patch.object(r.advice_db, "set_advice_feedback", return_value=payload) as helper:
            result = r.submit_advice_feedback("a1", r.AdviceFeedbackRequest(rating=1, reason="ok"), uid="u1")
        assert result == payload
        helper.assert_called_once_with("u1", "a1", rating=1, reason="ok")

    def test_404_when_advice_missing(self):
        with patch.object(r.advice_db, "set_advice_feedback", return_value=None):
            with pytest.raises(HTTPException) as ei:
                r.submit_advice_feedback("a1", r.AdviceFeedbackRequest(rating=-1), uid="u1")
        assert ei.value.status_code == 404

    @pytest.mark.parametrize("bad", [2, -2, 5])
    def test_model_rejects_out_of_range_rating(self, bad):
        with pytest.raises(ValidationError):
            r.AdviceFeedbackRequest(rating=bad)

    @pytest.mark.parametrize("bad", [True, False])
    def test_model_rejects_bool_rating(self, bad):
        # A stray bool must not coerce to 1/0 (StrictInt) — false -> 0 would silently clear feedback.
        with pytest.raises(ValidationError):
            r.AdviceFeedbackRequest(rating=bad)

    def test_model_rejects_overlong_reason(self):
        with pytest.raises(ValidationError):
            r.AdviceFeedbackRequest(rating=1, reason="x" * 501)


# --- Advice response model exposes the stored feedback (GET /v1/advice read path) ---


class TestAdviceResponseModelFeedback:
    def _advice_dict(self, feedback):
        return {
            "id": "a1",
            "content": "drink some water",
            "category": "health",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "feedback": feedback,
        }

    def test_stored_feedback_survives_response_model(self):
        # GET /v1/advice serializes the stored advice dicts through response_model=list[Advice]. Before
        # the fix, Advice had no feedback field, so Pydantic filtered the saved feedback out of the read
        # path and the OpenAPI schema. It must now round-trip with rating/reason/rated_at intact.
        rated_at = datetime.now(timezone.utc)
        stored = {"rating": 1, "reason": "great tip", "rated_at": rated_at}
        advice_obj = Advice.model_validate(self._advice_dict(stored))
        assert isinstance(advice_obj.feedback, AdviceFeedback)
        assert advice_obj.feedback.rating == 1
        assert advice_obj.feedback.reason == "great tip"
        assert advice_obj.feedback.rated_at == rated_at
        dumped = advice_obj.model_dump()  # what the client actually receives
        assert dumped["feedback"]["rating"] == 1
        assert dumped["feedback"]["reason"] == "great tip"

    def test_advice_without_feedback_is_none(self):
        assert Advice.model_validate(self._advice_dict(None)).feedback is None
        # Advice documents that never carried a feedback key at all also read cleanly.
        without_key = self._advice_dict(None)
        del without_key["feedback"]
        assert Advice.model_validate(without_key).feedback is None
