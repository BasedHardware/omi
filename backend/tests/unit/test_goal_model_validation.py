import unittest
from pydantic import ValidationError

from models.goal import (
    GoalCreate,
    GoalFocusRequest,
    GoalProgressEventCreate,
    GoalProgressEventKind,
    GoalUpdate,
)


class TestGoalModelValidation(unittest.TestCase):
    def test_goal_create_valid_why_it_matters_and_unit(self):
        goal = GoalCreate(
            title="  Run 5k  ",
            why_it_matters="  Stay healthy  ",
            unit="  km  ",
        )
        self.assertEqual(goal.title, "Run 5k")
        self.assertEqual(goal.why_it_matters, "Stay healthy")
        self.assertEqual(goal.unit, "km")

    def test_goal_create_blank_why_it_matters_rejected(self):
        with self.assertRaises(ValidationError):
            GoalCreate(title="Run 5k", why_it_matters="   ")

    def test_goal_update_valid_why_it_matters_and_unit(self):
        update = GoalUpdate(
            why_it_matters="  Updated reason  ",
            unit="  miles  ",
        )
        self.assertEqual(update.why_it_matters, "Updated reason")
        self.assertEqual(update.unit, "miles")

    def test_goal_update_blank_why_it_matters_rejected(self):
        with self.assertRaises(ValidationError):
            GoalUpdate(why_it_matters="   ")

    def test_goal_focus_request_valid_replacement_goal_id(self):
        req = GoalFocusRequest(replacement_goal_id="  goal_123  ", focus_rank=2)
        self.assertEqual(req.replacement_goal_id, "goal_123")
        self.assertEqual(req.focus_rank, 2)

    def test_goal_focus_request_blank_replacement_goal_id_rejected(self):
        with self.assertRaises(ValidationError):
            GoalFocusRequest(replacement_goal_id="   ")

    def test_goal_focus_request_non_string_replacement_goal_id_rejected(self):
        with self.assertRaises(ValidationError):
            GoalFocusRequest(replacement_goal_id=123)

    def test_goal_progress_event_create_valid(self):
        event = GoalProgressEventCreate(
            kind=GoalProgressEventKind.milestone,
            summary="  Completed first 5k run  ",
        )
        self.assertEqual(event.summary, "Completed first 5k run")

    def test_goal_progress_event_create_blank_summary_rejected(self):
        with self.assertRaises(ValidationError):
            GoalProgressEventCreate(
                kind=GoalProgressEventKind.milestone,
                summary="   ",
            )

    def test_goal_progress_event_create_non_string_summary_rejected(self):
        with self.assertRaises(ValidationError):
            GoalProgressEventCreate(
                kind=GoalProgressEventKind.milestone,
                summary=12345,
            )


if __name__ == "__main__":
    unittest.main()
