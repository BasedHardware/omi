import unittest
from pydantic import ValidationError

from models.frame_request import (
    CreateFrameRequest,
    FrameRequestPromotion,
    FrameRequestState,
    FrameRequestStateUpdate,
)


class TestFrameRequestModelValidation(unittest.TestCase):
    def test_create_frame_request_valid(self):
        req = CreateFrameRequest(
            device_id="  dev_123  ",
            dedupe_key="  key_abc  ",
            conversation_id="  conv_xyz  ",
            screenshot_id="   ",
        )
        self.assertEqual(req.device_id, "dev_123")
        self.assertEqual(req.dedupe_key, "key_abc")
        self.assertEqual(req.conversation_id, "conv_xyz")
        self.assertIsNone(req.screenshot_id)

    def test_create_frame_request_blank_device_id_rejected(self):
        with self.assertRaises(ValidationError):
            CreateFrameRequest(
                device_id="   ",
                dedupe_key="key_abc",
            )

    def test_create_frame_request_blank_dedupe_key_rejected(self):
        with self.assertRaises(ValidationError):
            CreateFrameRequest(
                device_id="dev_123",
                dedupe_key="   ",
            )

    def test_frame_request_state_update_valid(self):
        update = FrameRequestStateUpdate(
            state=FrameRequestState.failed,
            device_id="  dev_123  ",
            terminal_reason="  quota exceeded  ",
        )
        self.assertEqual(update.device_id, "dev_123")
        self.assertEqual(update.terminal_reason, "quota exceeded")

    def test_frame_request_state_update_blank_device_id_rejected(self):
        with self.assertRaises(ValidationError):
            FrameRequestStateUpdate(
                state=FrameRequestState.failed,
                device_id="   ",
                terminal_reason="failed",
            )

    def test_frame_request_promotion_valid(self):
        promo = FrameRequestPromotion(
            device_id="  dev_123  ",
            conversation_id="  conv_456  ",
        )
        self.assertEqual(promo.device_id, "dev_123")
        self.assertEqual(promo.conversation_id, "conv_456")

    def test_frame_request_promotion_blank_device_id_rejected(self):
        with self.assertRaises(ValidationError):
            FrameRequestPromotion(
                device_id="   ",
                conversation_id="conv_456",
            )

    def test_frame_request_promotion_blank_conversation_id_rejected(self):
        with self.assertRaises(ValidationError):
            FrameRequestPromotion(
                device_id="dev_123",
                conversation_id="   ",
            )

    def test_frame_request_instantiation_and_compatibility(self):
        from datetime import datetime, timezone
        from models.frame_request import FrameRequest

        now = datetime(2026, 10, 14, 12, 0, 0, tzinfo=timezone.utc)
        req = FrameRequest(
            request_id="req_123",
            uid="uid_123",
            device_id="dev_123",
            dedupe_key="key_123",
            created_at=now,
            expires_at=now,
        )
        self.assertEqual(req.request_id, "req_123")
        self.assertEqual(req.uid, "uid_123")
        self.assertEqual(req.device_id, "dev_123")
        self.assertEqual(req.dedupe_key, "key_123")


if __name__ == "__main__":
    unittest.main()
