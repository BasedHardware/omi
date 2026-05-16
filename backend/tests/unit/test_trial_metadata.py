"""Tests for the trial metadata endpoint and get_trial_metadata logic (#7329).

Validates:
- get_trial_metadata returns correct timing for active trial users
- get_trial_metadata returns expired=True after trial window
- Paid-plan users get trial_expired=False (trial is moot)
- BYOK users get trial_expired=False (trial is moot)
- Firebase lookup failure fails open (trial_expired=False)
- TRIAL_LENGTH_SECONDS is env-configurable
- TrialMetadata model fields are correct
- Endpoint returns correct response shape
"""

import os
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from models.users import TrialMetadata, PlanType

# ── Source-level tests: verify the endpoint and function exist correctly ──────


def _read_source(path):
    with open(path) as f:
        return f.read()


SUBSCRIPTION_SRC_PATH = 'utils/subscription.py'
USERS_ROUTER_SRC_PATH = 'routers/users.py'


class TestTrialEndpointExists:
    """Verify the /v1/users/me/trial endpoint is wired correctly."""

    def test_endpoint_route_registered(self):
        src = _read_source(USERS_ROUTER_SRC_PATH)
        assert "/v1/users/me/trial" in src

    def test_endpoint_uses_get_trial_metadata(self):
        src = _read_source(USERS_ROUTER_SRC_PATH)
        assert "get_trial_metadata" in src

    def test_endpoint_response_model_is_trial_metadata(self):
        src = _read_source(USERS_ROUTER_SRC_PATH)
        assert "response_model=TrialMetadata" in src

    def test_trial_metadata_imported_in_router(self):
        src = _read_source(USERS_ROUTER_SRC_PATH)
        assert "TrialMetadata" in src


class TestTrialLengthConfigurable:
    """Verify TRIAL_LENGTH_SECONDS is env-configurable."""

    def test_trial_length_uses_env_var(self):
        src = _read_source(SUBSCRIPTION_SRC_PATH)
        assert "os.getenv('TRIAL_LENGTH_SECONDS'" in src

    def test_trial_length_default_is_3_days(self):
        src = _read_source(SUBSCRIPTION_SRC_PATH)
        assert "3 * 24 * 60 * 60" in src


class TestGetTrialMetadataExists:
    """Verify get_trial_metadata function signature and structure."""

    def test_function_defined(self):
        src = _read_source(SUBSCRIPTION_SRC_PATH)
        assert "def get_trial_metadata(uid: str)" in src

    def test_returns_trial_metadata(self):
        src = _read_source(SUBSCRIPTION_SRC_PATH)
        func_start = src.index('def get_trial_metadata(')
        func_body = src[func_start : src.index('\ndef ', func_start + 1)]
        assert "TrialMetadata(" in func_body

    def test_checks_paid_plan(self):
        src = _read_source(SUBSCRIPTION_SRC_PATH)
        func_start = src.index('def get_trial_metadata(')
        func_body = src[func_start : src.index('\ndef ', func_start + 1)]
        assert "PlanType.basic" in func_body

    def test_checks_byok(self):
        src = _read_source(SUBSCRIPTION_SRC_PATH)
        func_start = src.index('def get_trial_metadata(')
        func_body = src[func_start : src.index('\ndef ', func_start + 1)]
        assert "is_byok_active" in func_body

    def test_uses_firebase_creation_timestamp(self):
        src = _read_source(SUBSCRIPTION_SRC_PATH)
        func_start = src.index('def get_trial_metadata(')
        func_body = src[func_start : src.index('\ndef ', func_start + 1)]
        assert "creation_timestamp" in func_body

    def test_fails_open_on_exception(self):
        src = _read_source(SUBSCRIPTION_SRC_PATH)
        func_start = src.index('def get_trial_metadata(')
        func_body = src[func_start : src.index('\ndef ', func_start + 1)]
        assert "except Exception" in func_body
        assert "trial_expired=False" in func_body


# ── Behavioral tests: compile and run get_trial_metadata with mocked deps ─────


def _get_trial_metadata_fn():
    """Extract get_trial_metadata from subscription.py source and compile it."""
    source = (Path(__file__).resolve().parents[2] / "utils" / "subscription.py").read_text()
    func_start = source.index('def get_trial_metadata(')
    next_func = source.index('\ndef ', func_start + 1)
    func_source = source[func_start:next_func]

    # Need the TRIAL_FEATURES constant too
    features_start = source.index('TRIAL_FEATURES = [')
    features_end = source.index(']', features_start) + 1
    features_source = source[features_start:features_end]

    # Get TRIAL_LENGTH_SECONDS
    tls_line = [l for l in source.split('\n') if l.startswith('TRIAL_LENGTH_SECONDS')][0]

    namespace = {
        'PlanType': PlanType,
        'TrialMetadata': TrialMetadata,
        'time': time,
        'os': os,
        'users_db': MagicMock(),
        'firebase_auth': MagicMock(),
        'logger': MagicMock(),
        'get_plan_display_name': lambda p: 'Free' if p == PlanType.basic else p.value.capitalize(),
        'FREE_CHAT_QUESTIONS_PER_MONTH': 30,
    }
    # Execute TRIAL_LENGTH_SECONDS
    exec(compile(tls_line, '<subscription.py>', 'exec'), namespace)
    # Execute TRIAL_FEATURES
    exec(compile(features_source, '<subscription.py>', 'exec'), namespace)
    # Execute function
    exec(compile(func_source, '<subscription.py>', 'exec'), namespace)
    return namespace['get_trial_metadata'], namespace


class TestGetTrialMetadataBehavior:
    """Behavioral tests for get_trial_metadata with controlled dependencies."""

    def setup_method(self):
        self.fn, self.ns = _get_trial_metadata_fn()

    def _mock_user_in_trial(self, age_seconds=3600):
        """Mock a basic-plan user who is still in their trial."""
        sub = MagicMock()
        sub.plan = PlanType.basic
        self.ns['users_db'].get_user_valid_subscription.return_value = sub
        self.ns['users_db'].is_byok_active.return_value = False
        creation_ms = (time.time() - age_seconds) * 1000
        user_record = MagicMock()
        user_record.user_metadata.creation_timestamp = creation_ms
        self.ns['firebase_auth'].get_user.return_value = user_record

    def _mock_user_expired(self, age_seconds=4 * 24 * 3600):
        """Mock a basic-plan user whose trial has expired."""
        sub = MagicMock()
        sub.plan = PlanType.basic
        self.ns['users_db'].get_user_valid_subscription.return_value = sub
        self.ns['users_db'].is_byok_active.return_value = False
        creation_ms = (time.time() - age_seconds) * 1000
        user_record = MagicMock()
        user_record.user_metadata.creation_timestamp = creation_ms
        self.ns['firebase_auth'].get_user.return_value = user_record

    def _mock_paid_user(self):
        """Mock a paid-plan user."""
        sub = MagicMock()
        sub.plan = PlanType.operator
        self.ns['users_db'].get_user_valid_subscription.return_value = sub
        self.ns['users_db'].is_byok_active.return_value = False

    def _mock_byok_user(self):
        """Mock a BYOK user on basic plan."""
        sub = MagicMock()
        sub.plan = PlanType.basic
        self.ns['users_db'].get_user_valid_subscription.return_value = sub
        self.ns['users_db'].is_byok_active.return_value = True

    def test_active_trial_returns_correct_timing(self):
        """User 1 hour into trial: trial_expired=False, remaining > 0."""
        self._mock_user_in_trial(age_seconds=3600)
        result = self.fn('uid_test')
        assert result.trial_expired is False
        assert result.trial_remaining_seconds > 0
        assert result.trial_started_at is not None
        assert result.trial_ends_at is not None
        assert result.trial_ends_at > result.trial_started_at

    def test_expired_trial_returns_zero_remaining(self):
        """User 4 days old: trial_expired=True, remaining=0."""
        self._mock_user_expired()
        result = self.fn('uid_test')
        assert result.trial_expired is True
        assert result.trial_remaining_seconds == 0

    def test_paid_user_trial_not_expired(self):
        """Paid-plan user: trial_expired=False (trial is moot)."""
        self._mock_paid_user()
        result = self.fn('uid_test')
        assert result.trial_expired is False
        assert result.trial_started_at is None
        assert result.trial_ends_at is None

    def test_byok_user_trial_not_expired(self):
        """BYOK user: trial_expired=False (trial is moot)."""
        self._mock_byok_user()
        result = self.fn('uid_test')
        assert result.trial_expired is False
        assert result.trial_started_at is None

    def test_firebase_failure_fails_open(self):
        """Firebase lookup failure: trial_expired=False."""
        sub = MagicMock()
        sub.plan = PlanType.basic
        self.ns['users_db'].get_user_valid_subscription.return_value = sub
        self.ns['users_db'].is_byok_active.return_value = False
        self.ns['firebase_auth'].get_user.side_effect = Exception("Firebase unavailable")
        result = self.fn('uid_test')
        assert result.trial_expired is False

    def test_trial_features_present(self):
        """Result always includes trial_features list."""
        self._mock_user_in_trial()
        result = self.fn('uid_test')
        assert len(result.trial_features) > 0
        assert 'unlimited_listening' in result.trial_features

    def test_plan_after_trial_is_free(self):
        """plan_after_trial is always 'Free'."""
        self._mock_user_in_trial()
        result = self.fn('uid_test')
        assert result.plan_after_trial == 'Free'

    def test_trial_duration_seconds_matches_config(self):
        """trial_duration_seconds reflects TRIAL_LENGTH_SECONDS config."""
        self._mock_user_in_trial()
        result = self.fn('uid_test')
        assert result.trial_duration_seconds == self.ns['TRIAL_LENGTH_SECONDS']

    def test_no_creation_timestamp_fails_open(self):
        """User with no creation_timestamp: trial_expired=False."""
        sub = MagicMock()
        sub.plan = PlanType.basic
        self.ns['users_db'].get_user_valid_subscription.return_value = sub
        self.ns['users_db'].is_byok_active.return_value = False
        user_record = MagicMock()
        user_record.user_metadata.creation_timestamp = None
        self.ns['firebase_auth'].get_user.return_value = user_record
        result = self.fn('uid_test')
        assert result.trial_expired is False

    def test_trial_remaining_never_negative(self):
        """trial_remaining_seconds is always >= 0, never negative."""
        self._mock_user_expired(age_seconds=30 * 24 * 3600)  # 30 days past
        result = self.fn('uid_test')
        assert result.trial_remaining_seconds == 0
        assert result.trial_remaining_seconds >= 0


class TestTrialMetadataModel:
    """Verify TrialMetadata model has correct fields and defaults."""

    def test_default_values(self):
        m = TrialMetadata()
        assert m.trial_started_at is None
        assert m.trial_ends_at is None
        assert m.trial_remaining_seconds == 0
        assert m.trial_expired is False
        assert m.trial_duration_seconds == 0
        assert m.trial_features == []
        assert m.plan_after_trial == 'Free'

    def test_full_construction(self):
        m = TrialMetadata(
            trial_started_at=1000000,
            trial_ends_at=1259200,
            trial_remaining_seconds=100000,
            trial_expired=False,
            trial_duration_seconds=259200,
            trial_features=['unlimited_listening'],
            plan_after_trial='Free',
        )
        assert m.trial_started_at == 1000000
        assert m.trial_ends_at == 1259200
        assert m.trial_remaining_seconds == 100000
        assert m.trial_expired is False

    def test_json_serialization(self):
        m = TrialMetadata(
            trial_started_at=1000000,
            trial_ends_at=1259200,
            trial_remaining_seconds=100000,
            trial_expired=False,
            trial_duration_seconds=259200,
            trial_features=['unlimited_listening', 'unlimited_transcription'],
            plan_after_trial='Free',
        )
        d = m.dict()
        assert d['trial_started_at'] == 1000000
        assert d['trial_features'] == ['unlimited_listening', 'unlimited_transcription']
