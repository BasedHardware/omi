"""Tests for BYOK security fixes (issue #6880).

Covers: Chat/transcription quota bypass and quota-boundary consistency.
"""

from unittest.mock import patch

from types import SimpleNamespace

from models.users import PlanType
import pytest

from tests.unit._byok_fixtures import _byok_isolation  # noqa: F401

# ---------------------------------------------------------------------------
# 6. Chat quota BYOK bypass
# ---------------------------------------------------------------------------


class TestChatQuotaBYOKBypass:
    @patch('utils.subscription.has_validated_byok_keys', return_value=True)
    @patch('utils.subscription.get_byok_uid', return_value='byok-user-uid')
    @patch('utils.subscription.get_cached_byok_state', return_value={'fingerprints': {'openai': 'fp'}})
    @patch('utils.subscription.get_byok_key', side_effect=lambda provider: 'sk-user' if provider == 'openai' else None)
    @patch('utils.subscription.users_db')
    @patch('utils.subscription.is_trial_paywalled', return_value=False)
    @patch('utils.subscription.get_chat_quota_snapshot')
    def test_enforce_chat_quota_bypasses_for_validated_openai_key(
        self, mock_quota_snapshot, _mock_paywalled, mock_users_db, _mock_key, _mock_state, _mock_uid, _mock_validated
    ):
        mock_users_db.is_byok_active.return_value = True
        from utils.subscription import enforce_chat_quota

        enforce_chat_quota('byok-user-uid')
        mock_users_db.is_byok_active.assert_called_once_with('byok-user-uid', firestore_client=None)
        mock_quota_snapshot.assert_not_called()

    @patch('utils.byok.get_byok_key', return_value=None)
    @patch('utils.subscription.users_db')
    @patch('utils.subscription.get_chat_quota_snapshot')
    def test_enforce_chat_quota_enforces_when_byok_active_but_no_llm_headers(
        self, mock_snapshot, mock_users_db, _mock_get_key
    ):
        """Abuse case: user activated BYOK but sends no LLM provider headers."""
        from models.users import PlanType

        mock_users_db.is_byok_active.return_value = True
        mock_snapshot.return_value = {
            'plan': PlanType.basic,
            'unit': 'questions',
            'used': 31,
            'limit': 30,
            'allowed': False,
            'reset_at': '2026-05-01',
        }
        from fastapi import HTTPException
        from utils.subscription import enforce_chat_quota

        with pytest.raises(HTTPException) as exc_info:
            enforce_chat_quota('fake-byok-uid')
        assert exc_info.value.status_code == 402

    @patch('utils.byok.get_byok_key')
    @patch('utils.subscription.users_db')
    @patch('utils.subscription.get_chat_quota_snapshot')
    def test_enforce_chat_quota_enforces_when_only_deepgram_header(self, mock_snapshot, mock_users_db, mock_get_key):
        """Partial-header abuse: only x-byok-deepgram sent, chat uses Omi's OpenAI key."""
        from models.users import PlanType

        mock_users_db.is_byok_active.return_value = True
        mock_get_key.side_effect = lambda p: 'dg-key' if p == 'deepgram' else None
        mock_snapshot.return_value = {
            'plan': PlanType.basic,
            'unit': 'questions',
            'used': 31,
            'limit': 30,
            'allowed': False,
            'reset_at': '2026-05-01',
        }
        from fastapi import HTTPException
        from utils.subscription import enforce_chat_quota

        with pytest.raises(HTTPException) as exc_info:
            enforce_chat_quota('partial-byok-uid')
        assert exc_info.value.status_code == 402

    @patch('utils.subscription.users_db')
    @patch('utils.subscription.get_chat_quota_snapshot')
    def test_enforce_chat_quota_still_enforces_for_non_byok(self, mock_snapshot, mock_users_db):
        from models.users import PlanType

        mock_users_db.is_byok_active.return_value = False
        mock_snapshot.return_value = {
            'plan': PlanType.basic,
            'unit': 'questions',
            'used': 31,
            'limit': 30,
            'allowed': False,
            'reset_at': '2026-05-01',
        }
        from fastapi import HTTPException
        from utils.subscription import enforce_chat_quota

        with pytest.raises(HTTPException) as exc_info:
            enforce_chat_quota('non-byok-uid')
        assert exc_info.value.status_code == 402

    @patch('utils.subscription.has_validated_byok_keys', return_value=False)
    @patch('utils.subscription.get_byok_key')
    @patch('utils.subscription.users_db')
    @patch('utils.subscription.get_chat_quota_snapshot')
    def test_enforce_chat_quota_does_not_bypass_on_unvalidated_raw_header(
        self, mock_snapshot, mock_users_db, mock_get_key, _mock_not_validated
    ):
        """Raw LLM header presence alone must never bypass the quota gate.

        The reviewer's gate: the paywall/chat-quota bypass must be tied to a
        *validated* enrollment, not to any non-empty LLM BYOK header. Even when
        a raw OpenAI header is present and the user is BYOK-active, an
        unvalidated request (has_validated_byok_keys() == False) must still hit
        the 402 quota gate.
        """
        from models.users import PlanType

        mock_users_db.is_byok_active.return_value = True
        mock_get_key.side_effect = lambda p: 'sk-raw-but-unvalidated' if p == 'openai' else None
        mock_snapshot.return_value = {
            'plan': PlanType.basic,
            'unit': 'questions',
            'used': 31,
            'limit': 30,
            'allowed': False,
            'reset_at': '2026-05-01',
        }
        from fastapi import HTTPException
        from utils.subscription import enforce_chat_quota

        with pytest.raises(HTTPException) as exc_info:
            enforce_chat_quota('unvalidated-header-uid')
        assert exc_info.value.status_code == 402

    @patch('utils.subscription.get_customer_firestore_client', return_value='customer-fs')
    @patch('utils.subscription.has_validated_byok_keys', return_value=True)
    @patch('utils.subscription.get_byok_key')
    @patch('utils.subscription.users_db')
    @patch('utils.subscription.get_chat_quota_snapshot')
    def test_enforce_desktop_chat_quota_requires_anthropic(
        self, mock_snapshot, mock_users_db, mock_get_key, _mock_validated, _mock_fs
    ):
        from fastapi import HTTPException
        from models.users import PlanType
        from utils.subscription import enforce_desktop_chat_quota

        mock_users_db.is_byok_active.return_value = True
        mock_get_key.side_effect = lambda p: 'sk-or' if p == 'openrouter' else None
        mock_snapshot.return_value = {
            'plan': PlanType.basic,
            'unit': 'questions',
            'used': 31,
            'limit': 30,
            'allowed': False,
            'reset_at': '2026-05-01',
        }
        with pytest.raises(HTTPException) as exc_info:
            enforce_desktop_chat_quota('or-only-uid', platform='macos')
        assert exc_info.value.status_code == 402

    @patch('utils.subscription.get_customer_firestore_client', return_value='customer-fs')
    @patch('utils.subscription.has_validated_byok_keys', return_value=True)
    @patch('utils.subscription.get_byok_key')
    @patch('utils.subscription.users_db')
    @patch('utils.subscription.is_trial_paywalled', return_value=False)
    def test_enforce_desktop_chat_quota_bypasses_for_anthropic(
        self, _mock_paywalled, mock_users_db, mock_get_key, _mock_validated, _mock_fs
    ):
        from utils.subscription import enforce_desktop_chat_quota

        mock_users_db.is_byok_active.return_value = True
        mock_get_key.side_effect = lambda p: 'sk-ant' if p == 'anthropic' else None
        enforce_desktop_chat_quota('anthropic-uid', platform='macos')
        mock_users_db.is_byok_active.assert_called_once()


# ---------------------------------------------------------------------------
# 7. Transcription credit BYOK bypass
# ---------------------------------------------------------------------------


class TestTranscriptionCreditBYOKBypass:
    # These patch `utils.subscription.get_byok_key`, not `utils.byok.get_byok_key`.
    # subscription.py does `from utils.byok import get_byok_key` at import time, so
    # patching the source module leaves subscription's own binding untouched and the
    # BYOK branch never fires. These tests previously did that and still passed --
    # they fell through to the plan-limits path and returned True for an unrelated
    # reason, so the bypass they are named for had no real coverage.
    @patch('utils.subscription.get_byok_key', return_value='dg-user-key')
    @patch('utils.subscription.users_db')
    def test_has_transcription_credits_bypasses_for_byok(self, mock_users_db, _mock_get_key):
        mock_users_db.is_byok_active.return_value = True
        from utils.subscription import has_transcription_credits

        assert has_transcription_credits('byok-uid') is True
        # Proves the bypass short-circuited: the subscription was never consulted.
        mock_users_db.get_user_valid_subscription.assert_not_called()

    @patch('utils.subscription.get_byok_key', return_value='dg-user-key')
    @patch('utils.subscription.users_db')
    def test_remaining_seconds_is_none_for_byok(self, mock_users_db, _mock_get_key):
        mock_users_db.is_byok_active.return_value = True
        from utils.subscription import get_remaining_transcription_seconds

        assert get_remaining_transcription_seconds('byok-uid') is None

    @patch('utils.subscription.get_monthly_usage_for_subscription', return_value={'transcription_seconds': 10**9})
    @patch('utils.subscription.get_byok_key', return_value=None)
    @patch('utils.subscription.users_db')
    def test_transcription_not_bypassed_when_no_deepgram_header(self, mock_users_db, _mock_get_key, _mock_usage):
        """BYOK active but no x-byok-deepgram header — should NOT bypass.

        The proof that the bypass did not fire is that the plan path ran: the
        active basic subscription was read, its usage was consulted, and the
        exhausted allowance decided (one answer for both questions, shard S16).
        """
        mock_users_db.is_byok_active.return_value = True
        mock_users_db.get_user_valid_subscription.return_value = SimpleNamespace(plan=PlanType.basic)
        from utils.subscription import has_transcription_credits

        assert has_transcription_credits('fake-byok-uid') is False
        mock_users_db.get_user_valid_subscription.assert_called_once()
        _mock_usage.assert_called_once_with('fake-byok-uid')


# ---------------------------------------------------------------------------
# 13. Quota boundary tests
# ---------------------------------------------------------------------------


class TestQuotaBoundaryTests:
    @patch('utils.subscription.has_validated_byok_keys', return_value=True)
    @patch('utils.subscription.get_byok_uid', return_value='anthropic-byok-uid')
    @patch('utils.subscription.get_cached_byok_state', return_value={'fingerprints': {'anthropic': 'fp'}})
    @patch(
        'utils.subscription.get_byok_key',
        side_effect=lambda provider: 'sk-ant-user' if provider == 'anthropic' else None,
    )
    @patch('utils.subscription.users_db')
    def test_chat_quota_bypasses_with_validated_anthropic_key_only(
        self, mock_users_db, _mock_key, _mock_state, _mock_uid, _mock_validated
    ):
        """Anthropic-only BYOK should also bypass chat quota."""
        mock_users_db.is_byok_active.return_value = True
        from utils.subscription import enforce_chat_quota

        enforce_chat_quota('anthropic-byok-uid')  # Should not raise

    @patch('utils.byok.get_byok_key', return_value=None)
    @patch('utils.subscription.users_db')
    @patch('utils.subscription.get_chat_quota_snapshot')
    def test_chat_quota_at_exact_limit(self, mock_snapshot, mock_users_db, _mock_get_key):
        """Usage exactly at limit should be rejected."""
        from models.users import PlanType

        mock_users_db.is_byok_active.return_value = False
        mock_snapshot.return_value = {
            'plan': PlanType.basic,
            'unit': 'questions',
            'used': 30,
            'limit': 30,
            'allowed': False,
            'reset_at': '2026-05-01',
        }
        from fastapi import HTTPException
        from utils.subscription import enforce_chat_quota

        with pytest.raises(HTTPException) as exc_info:
            enforce_chat_quota('at-limit-uid')
        assert exc_info.value.status_code == 402

    @patch('utils.byok.get_byok_key', return_value=None)
    @patch('utils.subscription.users_db')
    @patch('utils.subscription.get_chat_quota_snapshot')
    def test_chat_quota_just_below_limit(self, mock_snapshot, mock_users_db, _mock_get_key):
        """Usage below limit should pass."""
        mock_users_db.is_byok_active.return_value = False
        mock_snapshot.return_value = {
            'plan': 'basic',
            'unit': 'questions',
            'used': 29,
            'limit': 30,
            'allowed': True,
            'reset_at': '2026-05-01',
        }
        from utils.subscription import enforce_chat_quota

        enforce_chat_quota('below-limit-uid')  # Should not raise


# ---------------------------------------------------------------------------
# 14. Per-request fingerprint validation against Firestore enrollment
# ---------------------------------------------------------------------------
