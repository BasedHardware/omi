import unittest
from pydantic import ValidationError

from models.daily_summary import DailySummaryDayStats, DailySummaryLocationPin
from models.daily_summary_payload import DailySummaryDayStatsPayload, DailySummaryQuestion


class TestDailySummaryStatsValidation(unittest.TestCase):
    def test_location_pin_valid_coordinates(self):
        pin = DailySummaryLocationPin(latitude=37.7749, longitude=-122.4194, address="San Francisco")
        self.assertEqual(pin.latitude, 37.7749)
        self.assertEqual(pin.longitude, -122.4194)

    def test_location_pin_boundary_coordinates(self):
        pin_min = DailySummaryLocationPin(latitude=-90.0, longitude=-180.0)
        self.assertEqual(pin_min.latitude, -90.0)
        self.assertEqual(pin_min.longitude, -180.0)

        pin_max = DailySummaryLocationPin(latitude=90.0, longitude=180.0)
        self.assertEqual(pin_max.latitude, 90.0)
        self.assertEqual(pin_max.longitude, 180.0)

    def test_location_pin_none_coordinates(self):
        pin = DailySummaryLocationPin()
        self.assertIsNone(pin.latitude)
        self.assertIsNone(pin.longitude)

    def test_location_pin_invalid_latitude(self):
        with self.assertRaises(ValidationError):
            DailySummaryLocationPin(latitude=90.1, longitude=0.0)

        with self.assertRaises(ValidationError):
            DailySummaryLocationPin(latitude=-90.1, longitude=0.0)

    def test_location_pin_invalid_longitude(self):
        with self.assertRaises(ValidationError):
            DailySummaryLocationPin(latitude=0.0, longitude=180.1)

        with self.assertRaises(ValidationError):
            DailySummaryLocationPin(latitude=0.0, longitude=-180.1)

    def test_day_stats_valid(self):
        stats = DailySummaryDayStats(
            total_conversations=5,
            total_duration_minutes=120,
            action_items_count=3,
            memories_created=2,
            action_items_created=3,
            watching_minutes=45,
            proactive_moments=1,
        )
        self.assertEqual(stats.total_conversations, 5)
        self.assertEqual(stats.total_duration_minutes, 120)

    def test_day_stats_zero_allowed(self):
        stats = DailySummaryDayStats(
            total_conversations=0,
            total_duration_minutes=0,
        )
        self.assertEqual(stats.total_conversations, 0)
        self.assertEqual(stats.total_duration_minutes, 0)

    def test_day_stats_negative_rejected(self):
        for field in [
            "total_conversations",
            "total_duration_minutes",
            "action_items_count",
            "memories_created",
            "action_items_created",
            "watching_minutes",
            "proactive_moments",
        ]:
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    DailySummaryDayStats(**{field: -1})

    def test_day_stats_payload_negative_rejected(self):
        for field in [
            "total_conversations",
            "total_duration_minutes",
            "action_items_count",
            "memories_created",
            "action_items_created",
            "watching_minutes",
            "proactive_moments",
        ]:
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    DailySummaryDayStatsPayload(**{field: -1})

    def test_question_optional_conversation_number(self):
        q1 = DailySummaryQuestion(question="What was discussed?")
        self.assertIsNone(q1.conversation_number)

        q2 = DailySummaryQuestion(question="What was discussed?", conversation_number=42)
        self.assertEqual(q2.conversation_number, 42)


if __name__ == "__main__":
    unittest.main()
