"""Tests for billable_transcription_seconds (#4700).

Listening minutes kept increasing while the Omi device was off: client
keepalive pings hold the /v4/listen socket open after audio stops, and usage
was billed as raw wall-clock time since the last record. Billing must be
clamped to the last audio byte actually received.
"""

import os
import re
import sys
import types

import pytest

# Stub the Firestore-backed module so importing utils.analytics does not
# instantiate a real client (pattern from test_action_item_idempotency.py).
_fake_user_usage = types.ModuleType('database.user_usage')
_fake_user_usage.update_hourly_usage = lambda *args, **kwargs: None
_fake_database = types.ModuleType('database')
_fake_database.user_usage = _fake_user_usage
sys.modules.setdefault('database', _fake_database)
sys.modules['database.user_usage'] = _fake_user_usage

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from utils.analytics import billable_transcription_seconds


class TestBillableTranscriptionSeconds:
    def test_no_usage_record_timestamp_bills_nothing(self):
        assert billable_transcription_seconds(None, 1000.0, 1060.0) == 0

    def test_continuous_audio_bills_full_interval(self):
        # Audio still flowing: last audio ~= now, behavior unchanged.
        assert billable_transcription_seconds(1000.0, 1060.0, 1060.0) == 60

    def test_audio_stopped_mid_interval_bills_only_until_last_audio(self):
        # Audio stopped 20s into the 60s interval.
        assert billable_transcription_seconds(1000.0, 1020.0, 1060.0) == 20

    def test_idle_socket_bills_zero(self):
        # The #4700 case: device off, socket kept alive by keepalive pings.
        # Last audio predates the last usage record; hours can pass.
        assert billable_transcription_seconds(1060.0, 1020.0, 1060.0 + 3 * 3600) == 0

    def test_no_audio_timestamp_falls_back_to_wall_clock(self):
        # Defensive: billing only starts on the first audio byte, which also
        # sets last_audio_received_time, but None must not crash or zero out.
        assert billable_transcription_seconds(1000.0, None, 1060.0) == 60

    def test_clock_skew_never_negative(self):
        assert billable_transcription_seconds(1060.0, 1000.0, 1050.0) == 0


class TestTranscribeUsesClampedBilling:
    """Structural guard: transcribe.py must not bill raw wall-clock time."""

    @staticmethod
    def _transcribe_source():
        path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'transcribe.py')
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()

    def test_no_raw_wall_clock_billing(self):
        source = self._transcribe_source()
        raw = re.findall(r'transcription_seconds\s*=\s*int\(.*last_usage_record_timestamp\)', source)
        assert not raw, f'raw wall-clock billing reintroduced: {raw}'

    def test_both_billing_sites_use_helper(self):
        source = self._transcribe_source()
        calls = re.findall(r'transcription_seconds\s*=\s*billable_transcription_seconds\(', source)
        # Periodic 60s tick + session-end flush.
        assert len(calls) == 2, f'expected 2 clamped billing sites, found {len(calls)}'
