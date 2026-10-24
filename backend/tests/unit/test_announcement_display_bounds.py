import unittest
from datetime import datetime, timezone
from pydantic import ValidationError

from models.announcement import Announcement, Display


class TestDisplayBoundsValidation(unittest.TestCase):
    def test_display_valid_dates(self):
        start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        expires = datetime(2026, 1, 2, 0, 0, 0, tzinfo=timezone.utc)
        disp = Display(start_at=start, expires_at=expires)
        self.assertEqual(disp.start_at, start)
        self.assertEqual(disp.expires_at, expires)

    def test_display_equal_start_and_expires(self):
        ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        disp = Display(start_at=ts, expires_at=ts)
        self.assertEqual(disp.start_at, ts)
        self.assertEqual(disp.expires_at, ts)

    def test_display_only_start_or_expires(self):
        ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        disp1 = Display(start_at=ts)
        self.assertEqual(disp1.start_at, ts)
        self.assertIsNone(disp1.expires_at)

        disp2 = Display(expires_at=ts)
        self.assertIsNone(disp2.start_at)
        self.assertEqual(disp2.expires_at, ts)

    def test_display_start_after_expires_raises_validation_error(self):
        start = datetime(2026, 1, 5, 0, 0, 0, tzinfo=timezone.utc)
        expires = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        with self.assertRaises(ValidationError) as ctx:
            Display(start_at=start, expires_at=expires)
        self.assertIn("display start_at must not exceed expires_at", str(ctx.exception))

    def test_announcement_from_dict_drops_inverted_display_subdoc(self):
        doc = {
            "id": "ann-inverted-display",
            "type": "announcement",
            "created_at": "2026-01-01T00:00:00Z",
            "display": {
                "start_at": "2026-01-10T00:00:00Z",
                "expires_at": "2026-01-05T00:00:00Z",
            },
        }
        ann = Announcement.from_dict(doc)
        self.assertEqual(ann.id, "ann-inverted-display")
        self.assertIsNone(ann.display)


if __name__ == "__main__":
    unittest.main()
