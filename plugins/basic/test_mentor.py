"""Hermetic tests for plugins/basic/mentor.py.

Exercises session bounds, TTL eviction, segment normalization, and codeword handling
without requiring external network or runtime services.
"""
import time
import unittest
from unittest.mock import patch, MagicMock

from fastapi import HTTPException
from models import TranscriptSegment, RealtimePluginRequest
from plugins.basic import mentor


class DummySegment:
    def __init__(self, text=""):
        self.text = text


class DummyRequest:
    def __init__(self, session_id="user1", segments=None):
        self.session_id = session_id
        self.segments = segments or []


class TestMentorPlugin(unittest.TestCase):
    def setUp(self):
        mentor.scan_segment_session.clear()

    def test_codeword_triggered_success(self):
        segments = [DummySegment("Hello"), DummySegment("Hey Omi what do you think?")]
        req = DummyRequest(session_id="user1", segments=segments)
        with patch.object(mentor, "get_upsert_segment_to_transcript_plugin", return_value=segments):
            res = mentor.mentoring(req, uid="user1")
            self.assertIn("notification", res)
            self.assertEqual(res["session_id"], "user1")
            self.assertIn("prompt", res["notification"])

    def test_session_mismatch_raises_403(self):
        req = DummyRequest(session_id="intruder", segments=[])
        with self.assertRaises(HTTPException) as ctx:
            mentor.mentoring(req, uid="user1")
        self.assertEqual(ctx.exception.status_code, 403)

    def test_codeword_not_triggered_returns_empty(self):
        req = DummyRequest(session_id="user1", segments=[DummySegment("General discussion")])
        with patch.object(mentor, "get_upsert_segment_to_transcript_plugin", return_value=req.segments):
            res = mentor.mentoring(req, uid="user1")
            self.assertEqual(res, {})

    def test_null_and_empty_segment_texts_do_not_crash(self):
        bad_segments = [DummySegment(None), DummySegment(""), DummySegment(123)]
        req = DummyRequest(session_id="user1", segments=bad_segments)
        with patch.object(mentor, "get_upsert_segment_to_transcript_plugin", return_value=bad_segments):
            res = mentor.mentoring(req, uid="user1")
            self.assertEqual(res, {})

    def test_stale_session_cleanup_eviction(self):
        now = time.time()
        mentor.scan_segment_session["expired_user"] = (5, now - 4000)
        mentor.scan_segment_session["fresh_user"] = (2, now)

        mentor._cleanup_stale_sessions()
        self.assertNotIn("expired_user", mentor.scan_segment_session)
        self.assertIn("fresh_user", mentor.scan_segment_session)

    def test_max_session_cap_enforcement(self):
        now = time.time()
        with patch.object(mentor, "MAX_MENTOR_SESSIONS", 3):
            mentor.scan_segment_session["u1"] = (0, now - 100)
            mentor.scan_segment_session["u2"] = (0, now - 50)
            mentor.scan_segment_session["u3"] = (0, now - 20)
            mentor.scan_segment_session["u4"] = (0, now - 10)

            mentor._cleanup_stale_sessions()
            self.assertLessEqual(len(mentor.scan_segment_session), 3)
            self.assertNotIn("u1", mentor.scan_segment_session)

    def test_setup_mentor_endpoint(self):
        res = mentor.is_setup_completed("user1")
        self.assertTrue(res.get("is_setup_completed"))


if __name__ == "__main__":
    unittest.main()
