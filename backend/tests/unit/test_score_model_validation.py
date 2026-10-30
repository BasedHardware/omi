import unittest
from pydantic import ValidationError

from models.score import DailyScore, ScorePeriod, Scores


class TestScoreModelValidation(unittest.TestCase):
    def test_daily_score_valid(self):
        ds = DailyScore(
            date="2026-10-14",
            score=75,
            completed_tasks=3,
            total_tasks=4,
        )
        self.assertEqual(ds.date, "2026-10-14")
        self.assertEqual(ds.completed_tasks, 3)
        self.assertEqual(ds.total_tasks, 4)

    def test_daily_score_invalid_date_rejected(self):
        with self.assertRaises(ValidationError):
            DailyScore(
                date="invalid-date",
                score=75,
                completed_tasks=3,
                total_tasks=4,
            )

    def test_daily_score_completed_exceeds_total_rejected(self):
        with self.assertRaises(ValidationError):
            DailyScore(
                date="2026-10-14",
                score=100,
                completed_tasks=5,
                total_tasks=4,
            )

    def test_score_period_valid(self):
        sp = ScorePeriod(
            score=80.0,
            completed_tasks=4,
            total_tasks=5,
        )
        self.assertEqual(sp.completed_tasks, 4)
        self.assertEqual(sp.total_tasks, 5)

    def test_score_period_completed_exceeds_total_rejected(self):
        with self.assertRaises(ValidationError):
            ScorePeriod(
                score=100.0,
                completed_tasks=6,
                total_tasks=5,
            )

    def test_scores_valid(self):
        sp = ScorePeriod(score=50.0, completed_tasks=1, total_tasks=2)
        scores = Scores(
            daily=sp,
            weekly=sp,
            overall=sp,
            default_tab="daily",
            date="2026-10-14",
        )
        self.assertEqual(scores.default_tab, "daily")
        self.assertEqual(scores.date, "2026-10-14")

    def test_scores_invalid_tab_rejected(self):
        sp = ScorePeriod(score=50.0, completed_tasks=1, total_tasks=2)
        with self.assertRaises(ValidationError):
            Scores(
                daily=sp,
                weekly=sp,
                overall=sp,
                default_tab="invalid_tab",
                date="2026-10-14",
            )

    def test_scores_invalid_date_rejected(self):
        sp = ScorePeriod(score=50.0, completed_tasks=1, total_tasks=2)
        with self.assertRaises(ValidationError):
            Scores(
                daily=sp,
                weekly=sp,
                overall=sp,
                default_tab="daily",
                date="14/10/2026",
            )


if __name__ == "__main__":
    unittest.main()
