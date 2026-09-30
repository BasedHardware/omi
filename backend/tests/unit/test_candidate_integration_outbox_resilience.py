from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest

from database.candidate_integration_outbox import (
    CANDIDATE_INTEGRATION_POLICY,
    _clean_id,
    _ensure_utc,
    claim_candidate_integration_dispatch,
    complete_candidate_integration_dispatch,
    dead_letter_malformed_candidate_integration,
    list_candidate_integration_dispatches,
    redrive_candidate_integration_dead_letter,
)


class TestCleanId:
    def test_valid(self):
        assert _clean_id("user123") == "user123"
        assert _clean_id("  candidate_abc  ") == "candidate_abc"

    def test_empty_or_whitespace_raises(self):
        with pytest.raises(ValueError, match="Identifier must be a non-empty string"):
            _clean_id("")
        with pytest.raises(ValueError, match="Identifier must be a non-empty string"):
            _clean_id("   ")

    def test_non_string_raises(self):
        with pytest.raises(ValueError, match="Identifier must be a non-empty string"):
            _clean_id(None)
        with pytest.raises(ValueError, match="Identifier must be a non-empty string"):
            _clean_id(12345)


class TestEnsureUtc:
    def test_none_returns_utc_now(self):
        dt = _ensure_utc(None)
        assert isinstance(dt, datetime)
        assert dt.tzinfo is not None

    def test_naive_datetime_gets_utc(self):
        naive = datetime(2026, 9, 30, 10, 0, 0)
        utc_dt = _ensure_utc(naive)
        assert utc_dt.tzinfo == timezone.utc

    def test_aware_datetime_preserved(self):
        aware = datetime(2026, 9, 30, 10, 0, 0, tzinfo=timezone.utc)
        assert _ensure_utc(aware) == aware

    def test_iso_string(self):
        iso_str = "2026-09-30T10:00:00Z"
        dt = _ensure_utc(iso_str)
        assert dt.tzinfo == timezone.utc
        assert dt.year == 2026


class TestCandidateOutboxValidation:
    def test_claim_validation(self):
        with pytest.raises(ValueError, match="Identifier must be a non-empty string"):
            claim_candidate_integration_dispatch("", "cand1", account_generation=1)
        with pytest.raises(ValueError, match="Identifier must be a non-empty string"):
            claim_candidate_integration_dispatch("uid1", "", account_generation=1)

    def test_complete_validation(self):
        with pytest.raises(ValueError, match="Identifier must be a non-empty string"):
            complete_candidate_integration_dispatch("", "cand1", account_generation=1, lease_token="tok", succeeded=True)
        with pytest.raises(ValueError, match="Identifier must be a non-empty string"):
            complete_candidate_integration_dispatch("uid1", "", account_generation=1, lease_token="tok", succeeded=True)
        # Empty lease token returns False gracefully
        assert complete_candidate_integration_dispatch("uid1", "cand1", account_generation=1, lease_token="", succeeded=True) is False

    def test_redrive_validation(self):
        with pytest.raises(ValueError, match="Identifier must be a non-empty string"):
            redrive_candidate_integration_dead_letter("", "cand1", account_generation=1)
        with pytest.raises(ValueError, match="Identifier must be a non-empty string"):
            redrive_candidate_integration_dead_letter("uid1", "", account_generation=1)

    def test_dead_letter_validation(self):
        with pytest.raises(ValueError, match="Identifier must be a non-empty string"):
            dead_letter_malformed_candidate_integration("", "cand1", account_generation=1, error_text="err")
        with pytest.raises(ValueError, match="Identifier must be a non-empty string"):
            dead_letter_malformed_candidate_integration("uid1", "", account_generation=1, error_text="err")

    def test_list_validation(self):
        with pytest.raises(ValueError, match="Identifier must be a non-empty string"):
            list_candidate_integration_dispatches("", account_generation=1)


class TestCandidateOutboxExecution:
    @patch("database.candidate_integration_outbox.db")
    def test_claim_execution(self, mock_db):
        mock_outbox_doc = MagicMock()
        mock_control_doc = MagicMock()
        mock_db.collection.return_value.document.return_value.collection.return_value.document.side_effect = [
            mock_outbox_doc,
            mock_control_doc,
        ]

        mock_snap = MagicMock()
        mock_snap.exists = True
        mock_snap.to_dict.return_value = {
            "account_generation": 1,
            "status": "pending",
            "attempt_count": 0,
        }
        mock_ctrl_snap = MagicMock()
        mock_ctrl_snap.exists = True
        mock_ctrl_snap.to_dict.return_value = {"account_generation": 1}

        mock_tx = MagicMock()
        mock_outbox_doc.get.return_value = mock_snap
        mock_control_doc.get.return_value = mock_ctrl_snap
        mock_db.transaction.return_value = mock_tx

        token = claim_candidate_integration_dispatch("user_abc", "cand_123", account_generation=1)
        assert token is not None
        assert len(token) == 32  # uuid4 hex
        mock_tx.update.assert_called_once()
