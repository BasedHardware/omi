import unittest
from datetime import datetime, timezone
from pydantic import ValidationError

from models.feedback import (
    FeedbackContextPointer,
    FeedbackEvent,
    FeedbackReason,
    FeedbackReport,
    FeedbackSurface,
    FeedbackTargetKind,
    MobileFeedbackKind,
    MobileFeedbackReason,
    MobileFeedbackRequest,
)


class TestFeedbackModelValidation(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 14, 12, 0, 0, tzinfo=timezone.utc)

    def test_feedback_event_valid(self):
        ev = FeedbackEvent(
            id="  ev_123  ",
            uid="  usr_456  ",
            surface=FeedbackSurface.chat_text,
            target_kind=FeedbackTargetKind.chat_message,
            target_id="  msg_789  ",
            value=1,
            created_at=self.now,
            reason=FeedbackReason.too_verbose,
            comment="  Great answer!  ",
        )
        self.assertEqual(ev.id, "ev_123")
        self.assertEqual(ev.uid, "usr_456")
        self.assertEqual(ev.target_id, "msg_789")
        self.assertEqual(ev.value, 1)
        self.assertEqual(ev.comment, "Great answer!")

    def test_feedback_event_whitespace_comment_normalized_to_none(self):
        ev = FeedbackEvent(
            id="ev_123",
            uid="usr_456",
            surface=FeedbackSurface.chat_text,
            target_kind=FeedbackTargetKind.chat_message,
            target_id="msg_789",
            value=0,
            created_at=self.now,
            comment="   ",
        )
        self.assertIsNone(ev.comment)

    def test_feedback_event_blank_identifiers_rejected(self):
        with self.assertRaises(ValidationError):
            FeedbackEvent(
                id="   ",
                uid="usr_456",
                surface=FeedbackSurface.chat_text,
                target_kind=FeedbackTargetKind.chat_message,
                target_id="msg_789",
                value=1,
                created_at=self.now,
            )

        with self.assertRaises(ValidationError):
            FeedbackEvent(
                id="ev_123",
                uid="   ",
                surface=FeedbackSurface.chat_text,
                target_kind=FeedbackTargetKind.chat_message,
                target_id="msg_789",
                value=1,
                created_at=self.now,
            )

        with self.assertRaises(ValidationError):
            FeedbackEvent(
                id="ev_123",
                uid="usr_456",
                surface=FeedbackSurface.chat_text,
                target_kind=FeedbackTargetKind.chat_message,
                target_id="   ",
                value=1,
                created_at=self.now,
            )

    def test_feedback_event_value_out_of_bounds_rejected(self):
        with self.assertRaises(ValidationError):
            FeedbackEvent(
                id="ev_123",
                uid="usr_456",
                surface=FeedbackSurface.chat_text,
                target_kind=FeedbackTargetKind.chat_message,
                target_id="msg_789",
                value=2,
                created_at=self.now,
            )

        with self.assertRaises(ValidationError):
            FeedbackEvent(
                id="ev_123",
                uid="usr_456",
                surface=FeedbackSurface.chat_text,
                target_kind=FeedbackTargetKind.chat_message,
                target_id="msg_789",
                value=-2,
                created_at=self.now,
            )

    def test_mobile_feedback_request_comment_normalization(self):
        req = MobileFeedbackRequest(
            feedback_id="fb_123",
            kind=MobileFeedbackKind.summary_helpfulness,
            target_id="conv_123",
            value=1,
            comment="  Needs more detail  ",
        )
        self.assertEqual(req.comment, "Needs more detail")

        req_empty = MobileFeedbackRequest(
            feedback_id="fb_123",
            kind=MobileFeedbackKind.summary_helpfulness,
            target_id="conv_123",
            value=1,
            comment="    ",
        )
        self.assertIsNone(req_empty.comment)

    def test_feedback_event_non_string_comment_rejected(self):
        with self.assertRaises(ValidationError):
            FeedbackEvent(
                id="ev_123",
                uid="usr_456",
                surface=FeedbackSurface.chat_text,
                target_kind=FeedbackTargetKind.chat_message,
                target_id="msg_789",
                value=1,
                created_at=self.now,
                comment=123,
            )

    def test_mobile_feedback_request_non_string_comment_rejected(self):
        with self.assertRaises(ValidationError):
            MobileFeedbackRequest(
                feedback_id="fb_123",
                kind=MobileFeedbackKind.summary_helpfulness,
                target_id="conv_123",
                value=1,
                comment=123,
            )

    def test_feedback_context_pointer_bounds(self):
        ptr = FeedbackContextPointer(
            event_id="ev_1",
            uid="usr_1",
            target_kind=FeedbackTargetKind.chat_message,
            target_id="msg_1",
            follow_up_count=0,
            follow_up_window_seconds=0,
        )
        self.assertEqual(ptr.follow_up_count, 0)
        self.assertEqual(ptr.follow_up_window_seconds, 0)

        with self.assertRaises(ValidationError):
            FeedbackContextPointer(
                event_id="ev_1",
                uid="usr_1",
                target_kind=FeedbackTargetKind.chat_message,
                target_id="msg_1",
                follow_up_count=-1,
            )

        with self.assertRaises(ValidationError):
            FeedbackContextPointer(
                event_id="ev_1",
                uid="usr_1",
                target_kind=FeedbackTargetKind.chat_message,
                target_id="msg_1",
                follow_up_window_seconds=-10,
            )

    def test_feedback_report_bounds(self):
        rep = FeedbackReport(
            date="2026-10-14",
            generated_at=self.now,
            total_negative=0,
        )
        self.assertEqual(rep.total_negative, 0)

        with self.assertRaises(ValidationError):
            FeedbackReport(
                date="2026-10-14",
                generated_at=self.now,
                total_negative=-1,
            )


if __name__ == "__main__":
    unittest.main()
