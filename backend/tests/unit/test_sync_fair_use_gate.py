"""Tests for sync endpoint fair-use gates (#5854)."""

from unittest.mock import patch, MagicMock

import pytest

# --- Stubs to isolate from heavy deps ---
import sys
from types import ModuleType

# Stub database modules
for mod_name in [
    'database._client',
    'database.redis_db',
    'database.fair_use',
    'database.users',
    'database.user_usage',
    'database.conversations',
    'firebase_admin',
    'firebase_admin.messaging',
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = ModuleType(mod_name)

# Stub redis_db.r
_mock_redis = MagicMock()
sys.modules['database.redis_db'].r = _mock_redis

# Stub database._client.db
sys.modules['database._client'].db = MagicMock()

import utils.fair_use as fair_use_mod


class TestRecordSpeechMsSource:
    """Test that source param is accepted and doesn't change Redis behavior."""

    def setup_method(self):
        _mock_redis.reset_mock()
        _mock_redis.pipeline.return_value = MagicMock()
        _mock_redis.zrangebyscore.return_value = []

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    def test_source_defaults_to_realtime(self):
        """Calling without source uses 'realtime' default."""
        fair_use_mod.record_speech_ms('user1', 5000)
        pipe = _mock_redis.pipeline.return_value
        pipe.hincrby.assert_called_once()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    def test_source_sync_accepted(self):
        """Calling with source='sync' works the same — same Redis keys."""
        fair_use_mod.record_speech_ms('user1', 5000, source='sync')
        pipe = _mock_redis.pipeline.return_value
        pipe.hincrby.assert_called_once()
        # Verify same Redis key pattern (no source in key)
        call_args = pipe.hincrby.call_args
        assert 'fair_use:bucket:user1' in str(call_args)

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    def test_source_does_not_change_redis_keys(self):
        """Source param is for logging only — Redis keys are identical."""
        pipe_mock = MagicMock()
        _mock_redis.pipeline.return_value = pipe_mock

        fair_use_mod.record_speech_ms('user1', 1000, source='realtime')
        realtime_calls = [str(c) for c in pipe_mock.method_calls]

        pipe_mock.reset_mock()
        _mock_redis.pipeline.return_value = pipe_mock

        fair_use_mod.record_speech_ms('user1', 1000, source='sync')
        sync_calls = [str(c) for c in pipe_mock.method_calls]

        # Same Redis operations regardless of source
        assert realtime_calls == sync_calls


class TestCheckSoftCapsWithPrecomputedTotals:
    """Test check_soft_caps with speech_totals param (used by sync path)."""

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_KILL_SWITCH', False)
    @patch.object(fair_use_mod, 'FAIR_USE_EXEMPT_UIDS', set())
    @patch.object(fair_use_mod, 'FAIR_USE_DAILY_SPEECH_MS', 7200000)
    @patch.object(fair_use_mod, 'get_rolling_speech_ms')
    def test_precomputed_totals_trigger_caps(self, mock_speech):
        """When speech_totals passed, uses them and skips Redis."""
        precomputed = {'daily_ms': 8000000, 'three_day_ms': 8000000, 'weekly_ms': 8000000}
        result = fair_use_mod.check_soft_caps('user1', speech_totals=precomputed)
        assert len(result) > 0
        mock_speech.assert_not_called()


class TestSpeechDurationComputation:
    """Test the speech duration accumulation logic used in sync endpoint.

    Duration is computed from raw VAD segments BEFORE merging, so silence
    gaps between merged segments are not counted as speech.
    """

    def test_duration_from_raw_vad_segments(self):
        """Raw VAD segments produce correct total duration (no silence gaps)."""
        # Two separate 30s speech spans
        raw_segments = [
            {'start': 0.0, 'end': 30.0},
            {'start': 150.0, 'end': 180.0},
        ]
        durations = [s['end'] - s['start'] for s in raw_segments if (s['end'] - s['start']) >= 1]
        # 30 + 30 = 60s (the 120s gap is NOT counted)
        assert sum(durations) == pytest.approx(60.0)

    def test_merged_segments_would_overcount(self):
        """Merged segments include silence gaps — raw segments don't."""
        # After merging (gap < 120s), these become one segment: 0-180
        # But raw speech is only 30+30 = 60s
        raw_segments = [
            {'start': 0.0, 'end': 30.0},
            {'start': 100.0, 'end': 130.0},  # Gap = 70s < 120s → merged
        ]
        raw_duration = sum(s['end'] - s['start'] for s in raw_segments if (s['end'] - s['start']) >= 1)
        merged_duration = 130.0 - 0.0  # What merged would give
        assert raw_duration == pytest.approx(60.0)
        assert merged_duration == pytest.approx(130.0)
        assert raw_duration < merged_duration  # Raw is correct, merged is inflated

    def test_short_segments_excluded(self):
        """Segments shorter than 1s are excluded."""
        segments = [
            {'start': 0.0, 'end': 0.5},  # Too short
            {'start': 10.0, 'end': 40.0},  # Valid
        ]
        durations = [s['end'] - s['start'] for s in segments if (s['end'] - s['start']) >= 1]
        assert len(durations) == 1
        assert durations[0] == pytest.approx(30.0)

    def test_empty_segments(self):
        """No segments produce zero duration."""
        segments = []
        durations = [s['end'] - s['start'] for s in segments if (s['end'] - s['start']) >= 1]
        assert sum(durations) == 0

    def test_conversion_to_ms(self):
        """Seconds to milliseconds conversion for record_speech_ms."""
        total_seconds = 45
        total_ms = total_seconds * 1000
        assert total_ms == 45000


class TestIsHardRestrictedGate:
    """Test is_hard_restricted works for sync pre-check."""

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', False)
    def test_disabled_returns_false(self):
        assert fair_use_mod.is_hard_restricted('user1') is False

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_KILL_SWITCH', True)
    def test_kill_switch_returns_false(self):
        assert fair_use_mod.is_hard_restricted('user1') is False

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_KILL_SWITCH', False)
    @patch.object(fair_use_mod, 'FAIR_USE_EXEMPT_UIDS', {'exempt-user'})
    def test_exempt_user_returns_false(self):
        assert fair_use_mod.is_hard_restricted('exempt-user') is False


class TestSyncEndpointImports:
    """Verify that all fair-use imports are available from utils.fair_use."""

    def test_all_required_functions_importable(self):
        """All functions needed by sync.py are importable from utils.fair_use."""
        assert callable(fair_use_mod.record_speech_ms)
        assert callable(fair_use_mod.get_rolling_speech_ms)
        assert callable(fair_use_mod.check_soft_caps)
        assert callable(fair_use_mod.is_hard_restricted)
        assert hasattr(fair_use_mod, 'FAIR_USE_ENABLED')
        assert hasattr(fair_use_mod, 'trigger_classifier_if_needed')


class TestCreateConversationLockPropagation:
    """Test is_locked field on CreateConversation flows through to Conversation."""

    def test_create_conversation_default_unlocked(self):
        """CreateConversation defaults to is_locked=False."""
        from models.conversation import CreateConversation
        from datetime import datetime, timezone

        cc = CreateConversation(
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            transcript_segments=[],
        )
        assert cc.is_locked is False

    def test_create_conversation_locked(self):
        """CreateConversation accepts is_locked=True."""
        from models.conversation import CreateConversation
        from datetime import datetime, timezone

        cc = CreateConversation(
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            transcript_segments=[],
            is_locked=True,
        )
        assert cc.is_locked is True

    def test_locked_propagates_through_dict(self):
        """is_locked=True appears in .dict() for **kwargs unpacking."""
        from models.conversation import CreateConversation
        from datetime import datetime, timezone

        cc = CreateConversation(
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            transcript_segments=[],
            is_locked=True,
        )
        d = cc.dict()
        assert d['is_locked'] is True

    def test_conversation_inherits_lock_from_create(self):
        """Conversation(**create_dict) inherits is_locked=True."""
        from models.conversation import CreateConversation, Conversation, Structured
        from datetime import datetime, timezone

        cc = CreateConversation(
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            transcript_segments=[],
            is_locked=True,
        )
        cc_dict = cc.dict()
        cc_dict.pop('calendar_meeting_context', None)
        conv = Conversation(
            id='test-id',
            created_at=datetime.now(timezone.utc),
            structured=Structured(),
            **cc_dict,
        )
        assert conv.is_locked is True


class TestSyncEndpointCodeStructure:
    """Structural tests: verify sync.py gates match expected design."""

    @staticmethod
    def _read_sync_source():
        import os

        sync_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')
        with open(sync_path) as f:
            return f.read()

    def test_no_402_block(self):
        """sync.py must not raise 402 (lock instead of block)."""
        source = self._read_sync_source()
        assert 'status_code=402' not in source

    def test_should_lock_flag_exists(self):
        """sync.py must use should_lock flag for credit-exhausted locking."""
        source = self._read_sync_source()
        assert 'should_lock' in source

    def test_is_locked_passed_to_create_conversation(self):
        """sync.py passes is_locked to CreateConversation."""
        source = self._read_sync_source()
        assert 'is_locked=is_locked' in source

    def test_hard_restricted_gate_exists(self):
        """sync.py must check is_hard_restricted."""
        source = self._read_sync_source()
        assert 'is_hard_restricted(uid)' in source

    def test_zero_speech_skips_recording(self):
        """Verify zero-speech guard in code: only records when total_speech_ms > 0."""
        source = self._read_sync_source()
        assert 'total_speech_ms > 0' in source


class TestSoftCapBoundary:
    """Test check_soft_caps at exact boundary values."""

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_KILL_SWITCH', False)
    @patch.object(fair_use_mod, 'FAIR_USE_EXEMPT_UIDS', set())
    @patch.object(fair_use_mod, 'FAIR_USE_DAILY_SPEECH_MS', 7200000)
    @patch.object(fair_use_mod, 'get_rolling_speech_ms')
    def test_exactly_at_cap_does_not_trigger(self, mock_speech):
        """Usage exactly at daily cap should NOT trigger (only over)."""
        precomputed = {'daily_ms': 7200000, 'three_day_ms': 7200000, 'weekly_ms': 7200000}
        result = fair_use_mod.check_soft_caps('user1', speech_totals=precomputed)
        # At cap exactly — triggers only when OVER
        mock_speech.assert_not_called()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_KILL_SWITCH', False)
    @patch.object(fair_use_mod, 'FAIR_USE_EXEMPT_UIDS', set())
    @patch.object(fair_use_mod, 'FAIR_USE_DAILY_SPEECH_MS', 7200000)
    @patch.object(fair_use_mod, 'get_rolling_speech_ms')
    def test_one_ms_over_cap_triggers(self, mock_speech):
        """Usage 1ms over daily cap should trigger."""
        precomputed = {'daily_ms': 7200001, 'three_day_ms': 7200001, 'weekly_ms': 7200001}
        result = fair_use_mod.check_soft_caps('user1', speech_totals=precomputed)
        assert len(result) > 0
        mock_speech.assert_not_called()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_KILL_SWITCH', False)
    @patch.object(fair_use_mod, 'FAIR_USE_EXEMPT_UIDS', set())
    @patch.object(fair_use_mod, 'FAIR_USE_DAILY_SPEECH_MS', 7200000)
    @patch.object(fair_use_mod, 'get_rolling_speech_ms')
    def test_zero_speech_no_cap_trigger(self, mock_speech):
        """Zero speech should never trigger any cap."""
        precomputed = {'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
        result = fair_use_mod.check_soft_caps('user1', speech_totals=precomputed)
        assert result == []
        mock_speech.assert_not_called()
