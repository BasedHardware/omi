from datetime import datetime, timezone
import unittest

from pydantic import ValidationError

from models.support import (
    SupportLookupResponse,
    SupportTraceResponse,
    SupportTraceRow,
)


class TestSupportModelValidation(unittest.TestCase):
    def test_support_lookup_response_valid(self):
        resp = SupportLookupResponse(
            uid="u1",
            email="user@example.com",
            plan="pro",
            transcription_seconds_used=120.5,
            transcription_seconds_limit=3600,
            transcription_seconds_remaining=3479.5,
            fair_use_stage="normal",
        )
        self.assertEqual(resp.transcription_seconds_used, 120.5)
        self.assertEqual(resp.transcription_seconds_limit, 3600)
        self.assertEqual(resp.transcription_seconds_remaining, 3479.5)

    def test_support_lookup_response_negative_used_rejected(self):
        with self.assertRaises(ValidationError):
            SupportLookupResponse(
                uid="u1",
                email="user@example.com",
                plan="pro",
                transcription_seconds_used=-1.0,
                fair_use_stage="normal",
            )

    def test_support_lookup_response_negative_limit_rejected(self):
        with self.assertRaises(ValidationError):
            SupportLookupResponse(
                uid="u1",
                email="user@example.com",
                plan="pro",
                transcription_seconds_used=0.0,
                transcription_seconds_limit=-100,
                fair_use_stage="normal",
            )

    def test_support_lookup_response_negative_remaining_rejected(self):
        with self.assertRaises(ValidationError):
            SupportLookupResponse(
                uid="u1",
                email="user@example.com",
                plan="pro",
                transcription_seconds_used=0.0,
                transcription_seconds_remaining=-5.0,
                fair_use_stage="normal",
            )

    def test_support_trace_row_negative_duration_rejected(self):
        with self.assertRaises(ValidationError):
            SupportTraceRow(
                conversation_id="c1",
                started_at=datetime.now(timezone.utc),
                duration_seconds=-10.0,
                status="completed",
                captured=True,
                synced=True,
                processed=True,
                saved=True,
                failed=False,
                audio_present=True,
                has_transcript=True,
            )

    def test_support_trace_response_valid_window(self):
        now = datetime.now(timezone.utc)
        resp = SupportTraceResponse(
            email="user@example.com",
            uid="u1",
            **{"from": now, "to": now},
            truncated=False,
            rows=[],
        )
        self.assertEqual(resp.window_from, now)
        self.assertEqual(resp.window_to, now)

    def test_support_trace_response_inverted_window_rejected(self):
        t1 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc)
        with self.assertRaises(ValidationError):
            SupportTraceResponse(
                email="user@example.com",
                uid="u1",
                **{"from": t1, "to": t2},
                truncated=False,
                rows=[],
            )


if __name__ == "__main__":
    unittest.main()
