"""Tests for sync endpoint fair-use gates (#5854)."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest

import utils.fair_use as fair_use_mod
from utils.sync.rate_limit import (
    DEFAULT_FAIR_USE_RETRY_AFTER_SECONDS,
    FAIR_USE_RATE_LIMIT_CODE,
    FAIR_USE_RATE_LIMIT_REASON_HEADER,
    MAX_FAIR_USE_RETRY_AFTER_SECONDS,
    bounded_fair_use_retry_after,
    build_sync_rate_limit_event,
    emit_sync_rate_limit_event,
    fair_use_rate_limit_headers,
    validated_correlation_id,
)


class TestSyncRateLimitContract:
    def test_retry_after_uses_bounded_fallback_for_missing_legacy_deadline(self):
        assert bounded_fair_use_retry_after(None) == DEFAULT_FAIR_USE_RETRY_AFTER_SECONDS
        assert bounded_fair_use_retry_after('invalid') == DEFAULT_FAIR_USE_RETRY_AFTER_SECONDS
        assert bounded_fair_use_retry_after(0) == 1
        assert bounded_fair_use_retry_after(MAX_FAIR_USE_RETRY_AFTER_SECONDS + 1) == MAX_FAIR_USE_RETRY_AFTER_SECONDS

    def test_fair_use_headers_always_include_reason_and_retry_after(self):
        headers = fair_use_rate_limit_headers(None, {'Deprecation': 'true'})
        assert headers == {
            'Deprecation': 'true',
            FAIR_USE_RATE_LIMIT_REASON_HEADER: 'fair_use',
            'Retry-After': str(DEFAULT_FAIR_USE_RETRY_AFTER_SECONDS),
        }

    def test_structured_event_has_fixed_parsed_fields(self):
        event = build_sync_rate_limit_event(
            uid='uid-123',
            device_hash='a1b2c3d4',
            app_platform='ios',
            app_version='1.0.543+992',
            subscription_plan='operator',
            subscription_status='active',
            fair_use_stage='restrict',
            classifier_type='prerecorded',
            retry_after=321,
            backend_revision='backend-sync-00042-abc',
            correlation_id='5d55a970-f41c-4e18-9c20-7e7c6fb9d48d',
        )

        assert event == {
            'severity': 'WARNING',
            'message': 'sync_rate_limit_rejected',
            'event': 'sync_rate_limit_rejected',
            'uid': 'uid-123',
            'device_id_hash': 'a1b2c3d4',
            'app_platform': 'ios',
            'app_version': '1.0.543+992',
            'reason_code': FAIR_USE_RATE_LIMIT_CODE,
            'subscription_plan': 'operator',
            'subscription_status': 'active',
            'fair_use_stage': 'restrict',
            'classifier_type': 'prerecorded',
            'retry_after': 321,
            'backend_revision': 'backend-sync-00042-abc',
            'correlation_id': '5d55a970-f41c-4e18-9c20-7e7c6fb9d48d',
        }

    def test_untrusted_metadata_is_strictly_redacted(self):
        event = build_sync_rate_limit_event(
            uid='uid-123',
            device_hash='raw-device-id@example.com',
            app_platform='ios@example.com',
            app_version='1.0.543@example.com',
            subscription_plan='operator@example.com',
            subscription_status='active@example.com',
            fair_use_stage='restrict@example.com',
            classifier_type='prerecorded@example.com',
            retry_after=None,
            backend_revision='backend-sync@example.com',
            correlation_id='person@example.com',
        )

        serialized = json.dumps(event)
        assert 'example.com' not in serialized
        for key in (
            'device_id_hash',
            'app_platform',
            'app_version',
            'subscription_plan',
            'subscription_status',
            'fair_use_stage',
            'classifier_type',
            'backend_revision',
            'correlation_id',
        ):
            assert event[key] == 'unknown'
        assert event['retry_after'] == DEFAULT_FAIR_USE_RETRY_AFTER_SECONDS

    def test_correlation_accepts_only_uuid_or_cloud_trace_format(self):
        request_id = '5d55a970-f41c-4e18-9c20-7e7c6fb9d48d'
        cloud_trace = '105445aa7843bc8bf206b12000100000/1;o=1'
        assert validated_correlation_id(request_id) == request_id
        assert validated_correlation_id(cloud_trace) == cloud_trace
        assert validated_correlation_id('request-123') is None
        assert validated_correlation_id('person@example.com') is None

    def test_emitter_writes_exact_json_object(self, capsys):
        event = build_sync_rate_limit_event(
            uid='uid-123',
            device_hash='a1b2c3d4',
            app_platform='android',
            app_version='1.0.543+992',
            subscription_plan='basic',
            subscription_status='active',
            fair_use_stage='restrict',
            classifier_type='free_exhausted',
            retry_after=None,
            backend_revision='backend-sync-00042-abc',
            correlation_id='5d55a970-f41c-4e18-9c20-7e7c6fb9d48d',
        )
        emit_sync_rate_limit_event(event)
        output = capsys.readouterr().out
        assert json.loads(output) == event
        assert output.count('\n') == 1


class TestRecordSpeechMsSource:
    """Test lane-specific speech accounting keys."""

    @pytest.fixture(autouse=True)
    def mock_redis(self, monkeypatch):
        self._mock_redis = MagicMock()
        self._mock_redis.pipeline.return_value = MagicMock()
        self._mock_redis.zrangebyscore.return_value = []
        monkeypatch.setattr(fair_use_mod, 'redis_client', self._mock_redis)

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    def test_source_defaults_to_realtime(self):
        """Calling without source uses 'realtime' default."""
        fair_use_mod.record_speech_ms('user1', 5000)
        pipe = self._mock_redis.pipeline.return_value
        pipe.hincrby.assert_called_once()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    def test_source_sync_accepted(self):
        """The legacy sync alias maps to the fresh lane."""
        fair_use_mod.record_speech_ms('user1', 5000, source='sync')
        pipe = self._mock_redis.pipeline.return_value
        pipe.hincrby.assert_called_once()
        call_args = pipe.hincrby.call_args
        assert 'fair_use:v2:bucket:sync_fresh:user1' in str(call_args)

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    def test_source_separates_live_and_fresh_redis_keys(self):
        """Realtime and fresh sync usage remain independently queryable."""
        pipe_mock = MagicMock()
        self._mock_redis.pipeline.return_value = pipe_mock

        with patch.object(fair_use_mod.time, 'time', return_value=1_800_000_000):
            fair_use_mod.record_speech_ms('user1', 1000, source='realtime')
            realtime_calls = [str(c) for c in pipe_mock.method_calls]

            pipe_mock.reset_mock()
            self._mock_redis.pipeline.return_value = pipe_mock

            fair_use_mod.record_speech_ms('user1', 1000, source='sync')
            sync_calls = [str(c) for c in pipe_mock.method_calls]

        assert realtime_calls != sync_calls
        assert any('fair_use:v2:bucket:realtime:user1' in call for call in realtime_calls)
        assert any('fair_use:v2:bucket:sync_fresh:user1' in call for call in sync_calls)

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    def test_backfill_uses_non_live_key(self):
        fair_use_mod.record_speech_ms('user1', 1000, source='sync_backfill')
        call_args = self._mock_redis.pipeline.return_value.hincrby.call_args
        assert 'fair_use:v2:bucket:sync_backfill:user1' in str(call_args)


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


class TestHardRestrictionRetryAfter:
    """Test Retry-After calculation for hard-restricted sync users."""

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_KILL_SWITCH', False)
    @patch.object(fair_use_mod, 'FAIR_USE_EXEMPT_UIDS', set())
    @patch.object(
        fair_use_mod,
        'get_rolling_speech_ms',
        return_value={'daily_ms': 999999999, 'three_day_ms': 0, 'weekly_ms': 0},
    )
    @patch.object(fair_use_mod, 'fair_use_db')
    def test_returns_seconds_until_restrict_until(self, mock_fair_use_db, mock_speech):
        mock_fair_use_db.get_fair_use_state.return_value = {
            'stage': 'restrict',
            'restrict_until': datetime.utcnow() + timedelta(seconds=120),
        }

        retry_after = fair_use_mod.get_hard_restriction_retry_after_seconds('user1')

        assert retry_after is not None
        assert 1 <= retry_after <= 120

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_KILL_SWITCH', False)
    @patch.object(fair_use_mod, 'FAIR_USE_EXEMPT_UIDS', set())
    @patch.object(
        fair_use_mod,
        'get_rolling_speech_ms',
        return_value={'daily_ms': 999999999, 'three_day_ms': 0, 'weekly_ms': 0},
    )
    @patch.object(fair_use_mod, 'fair_use_db')
    def test_supports_aware_utc_datetimes(self, mock_fair_use_db, mock_speech):
        mock_fair_use_db.get_fair_use_state.return_value = {
            'stage': 'restrict',
            'restrict_until': datetime.now(timezone.utc) + timedelta(seconds=60),
        }

        retry_after = fair_use_mod.get_hard_restriction_retry_after_seconds('user1')

        assert retry_after is not None
        assert 1 <= retry_after <= 60

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_KILL_SWITCH', False)
    @patch.object(fair_use_mod, 'FAIR_USE_EXEMPT_UIDS', set())
    @patch.object(
        fair_use_mod,
        'get_rolling_speech_ms',
        return_value={'daily_ms': 999999999, 'three_day_ms': 0, 'weekly_ms': 0},
    )
    @patch.object(fair_use_mod, 'fair_use_db')
    def test_supports_aware_non_utc_datetimes(self, mock_fair_use_db, mock_speech):
        offset = timezone(timedelta(hours=5, minutes=30))
        restrict_until = (datetime.now(timezone.utc) + timedelta(seconds=90)).astimezone(offset)
        mock_fair_use_db.get_fair_use_state.return_value = {
            'stage': 'restrict',
            'restrict_until': restrict_until,
        }

        retry_after = fair_use_mod.get_hard_restriction_retry_after_seconds('user1')

        assert retry_after is not None
        assert 1 <= retry_after <= 90

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_KILL_SWITCH', False)
    @patch.object(fair_use_mod, 'FAIR_USE_EXEMPT_UIDS', set())
    @patch.object(
        fair_use_mod,
        'get_rolling_speech_ms',
        return_value={'daily_ms': 999999999, 'three_day_ms': 0, 'weekly_ms': 0},
    )
    @patch.object(fair_use_mod, 'fair_use_db')
    def test_status_returns_retry_after_with_single_state_read(self, mock_fair_use_db, mock_speech):
        mock_fair_use_db.get_fair_use_state.return_value = {
            'stage': 'restrict',
            'restrict_until': datetime.utcnow() + timedelta(seconds=120),
        }

        restricted, retry_after = fair_use_mod.get_hard_restriction_status('user1')

        assert restricted is True
        assert retry_after is not None
        assert 1 <= retry_after <= 120
        mock_fair_use_db.get_fair_use_state.assert_called_once_with('user1')

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_KILL_SWITCH', False)
    @patch.object(fair_use_mod, 'FAIR_USE_EXEMPT_UIDS', set())
    @patch.object(fair_use_mod, 'fair_use_db')
    def test_returns_none_when_stage_is_not_restrict(self, mock_fair_use_db):
        mock_fair_use_db.get_fair_use_state.return_value = {
            'stage': 'throttle',
            'restrict_until': datetime.utcnow() + timedelta(seconds=120),
        }

        assert fair_use_mod.get_hard_restriction_retry_after_seconds('user1') is None

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_KILL_SWITCH', False)
    @patch.object(fair_use_mod, 'FAIR_USE_EXEMPT_UIDS', set())
    @patch.object(
        fair_use_mod,
        'get_rolling_speech_ms',
        return_value={'daily_ms': 999999999, 'three_day_ms': 0, 'weekly_ms': 0},
    )
    @patch.object(fair_use_mod, 'fair_use_db')
    def test_returns_none_when_restrict_until_is_missing_or_expired(self, mock_fair_use_db, mock_speech):
        mock_fair_use_db.get_fair_use_state.return_value = {'stage': 'restrict'}
        assert fair_use_mod.get_hard_restriction_retry_after_seconds('user1') is None

        mock_fair_use_db.get_fair_use_state.return_value = {
            'stage': 'restrict',
            'restrict_until': datetime.utcnow() - timedelta(seconds=1),
        }
        assert fair_use_mod.get_hard_restriction_retry_after_seconds('user1') is None

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_KILL_SWITCH', False)
    @patch.object(fair_use_mod, 'FAIR_USE_EXEMPT_UIDS', set())
    @patch.object(fair_use_mod, 'fair_use_db')
    def test_returns_none_when_state_read_fails(self, mock_fair_use_db):
        mock_fair_use_db.get_fair_use_state.side_effect = RuntimeError('firestore timeout')

        assert fair_use_mod.get_hard_restriction_retry_after_seconds('user1') is None


class TestSyncEndpointImports:
    """Verify that all fair-use imports are available from utils.fair_use."""

    def test_all_required_functions_importable(self):
        """All functions needed by sync.py are importable from utils.fair_use."""
        assert callable(fair_use_mod.record_speech_ms)
        assert callable(fair_use_mod.get_rolling_speech_ms)
        assert callable(fair_use_mod.check_soft_caps)
        assert callable(fair_use_mod.is_hard_restricted)
        assert callable(fair_use_mod.get_hard_restriction_status)
        assert callable(fair_use_mod.get_hard_restriction_retry_after_seconds)
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
        from models.conversation import Conversation, CreateConversation
        from models.structured import Structured
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
        with open(sync_path, encoding='utf-8') as f:
            return f.read()

    @staticmethod
    def _read_pipeline_source():
        import os

        pipeline_path = os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'sync', 'pipeline.py')
        with open(pipeline_path, encoding='utf-8') as f:
            return f.read()

    @staticmethod
    def _function_body(source, marker):
        start = source.find(marker)
        assert start != -1, f'{marker} not found in sync.py'
        end = source.find('\n@router.', start + 1)
        if end == -1:
            end = len(source)
        return source[start:end]

    def _sync_local_files_bodies(self):
        source = self._read_sync_source()
        return '\n'.join(
            [
                self._function_body(source, 'async def sync_local_files('),
                self._function_body(source, 'async def sync_local_files_v2('),
            ]
        )

    def test_no_402_block(self):
        """sync-local-files must not raise 402 (lock instead of block)."""
        source = self._sync_local_files_bodies()
        assert 'status_code=402' not in source

    def test_should_lock_flag_exists(self):
        """sync.py must use should_lock flag for credit-exhausted locking."""
        source = self._read_sync_source()
        assert 'should_lock' in source

    def test_is_locked_passed_to_create_conversation(self):
        """sync pipeline passes is_locked to CreateConversation."""
        source = self._read_pipeline_source()
        assert 'is_locked=is_locked' in source

    def test_hard_restricted_gate_exists(self):
        """sync.py must check hard restriction status once."""
        source = self._read_sync_source()
        assert 'get_hard_restriction_status(uid)' in source

    def test_hard_restricted_429_uses_retry_after_headers(self):
        """Hard-restricted sync responses share an explicit machine-readable contract."""
        source = self._read_sync_source()
        assert 'get_hard_restriction_retry_after_seconds' not in source
        assert 'FAIR_USE_RATE_LIMIT_CODE' in source
        assert 'headers = fair_use_rate_limit_headers(safe_retry_after, base_headers)' in source
        assert source.count('return await _fair_use_restriction_response(') >= 3
        assert 'retry_after=retry_after' in self._function_body(source, 'async def sync_local_files_v2(')
        assert 'run_blocking(critical_executor, fair_use_rate_limit_headers' not in source

    def test_v2_propagates_app_version_into_rejection_telemetry(self):
        source = self._function_body(self._read_sync_source(), 'async def sync_local_files_v2(')
        assert "x_app_version: Optional[str] = Header(None, alias='X-App-Version')" in source
        assert 'x_app_version=x_app_version if isinstance(x_app_version, str) else None' in source
        assert 'app_version=client_device_context.app_version' in source

    def test_zero_speech_skips_recording(self):
        """Verify zero-speech guard in code: only records when total_speech_ms > 0."""
        source = self._read_sync_source()
        assert 'total_speech_ms > 0' in source

    def test_soft_cap_does_not_lock(self):
        """Soft cap trigger must NOT set should_lock — only classifier/stage should lock."""
        source = self._read_sync_source()
        # Find the soft cap block: between 'if triggered_caps:' and the next unindented line
        lines = source.split('\n')
        in_triggered_block = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('if triggered_caps:'):
                in_triggered_block = True
                continue
            if in_triggered_block:
                if stripped and not stripped.startswith('#') and not line.startswith(' ' * 16):
                    break  # exited the block
                assert (
                    'should_lock' not in stripped
                ), "soft cap trigger must not set should_lock — matches transcribe.py behavior"


class TestLockDecisionBehavior:
    """Behavioral tests: verify lock decision logic matches intended design.

    Simulates the sync endpoint lock decision flow:
        should_lock = not has_transcription_credits(uid)
        ... fair-use soft cap check (should NOT change should_lock) ...
        is_locked = should_lock
    """

    @staticmethod
    def _compute_lock_decision(has_credits: bool, fair_use_enabled: bool, triggered_caps: list) -> bool:
        """Reproduce the sync endpoint lock decision logic."""
        should_lock = not has_credits

        if fair_use_enabled and triggered_caps:
            # Per fix: soft cap trigger must NOT set should_lock
            # Only record + trigger classifier (side effects not modeled here)
            pass

        return should_lock

    def test_credits_available_soft_cap_triggered_no_lock(self):
        """Unlimited user with credits who triggers soft cap must NOT be locked."""
        is_locked = self._compute_lock_decision(
            has_credits=True, fair_use_enabled=True, triggered_caps=[{'trigger': 'daily'}]
        )
        assert is_locked is False, "Soft cap trigger must not lock when user has credits"

    def test_credits_exhausted_no_soft_cap_locks(self):
        """User with exhausted credits must be locked even without soft cap."""
        is_locked = self._compute_lock_decision(has_credits=False, fair_use_enabled=True, triggered_caps=[])
        assert is_locked is True, "Credit exhaustion must lock regardless of soft caps"

    def test_credits_exhausted_with_soft_cap_locks(self):
        """User with exhausted credits AND soft cap trigger must be locked (from credits, not caps)."""
        is_locked = self._compute_lock_decision(
            has_credits=False, fair_use_enabled=True, triggered_caps=[{'trigger': 'daily'}]
        )
        assert is_locked is True, "Credit exhaustion locks; soft cap is independent"

    def test_credits_available_fair_use_disabled_no_lock(self):
        """With fair-use disabled and credits available, no lock."""
        is_locked = self._compute_lock_decision(has_credits=True, fair_use_enabled=False, triggered_caps=[])
        assert is_locked is False

    def test_credits_available_no_caps_no_lock(self):
        """Normal unlimited user with no caps triggered: no lock."""
        is_locked = self._compute_lock_decision(has_credits=True, fair_use_enabled=True, triggered_caps=[])
        assert is_locked is False


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
        assert result == [], f"Expected no caps triggered at exact threshold, got: {result}"
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
