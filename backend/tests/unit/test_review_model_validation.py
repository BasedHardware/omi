import sys
import types
import unittest

from pydantic import BaseModel, ValidationError

if sys.version_info < (3, 10):
    # agent_edit uses PEP 604 union syntax ('|') requiring Python 3.10+
    m_dream = types.ModuleType("models.dream_edit")
    m_dream.Edit = type("Edit", (BaseModel,), {})
    m_dream.MemoryHygieneEdit = type("MemoryHygieneEdit", (BaseModel,), {})
    m_dream.Term = type("Term", (BaseModel,), {})
    sys.modules["models.dream_edit"] = m_dream

    m_agent = types.ModuleType("models.agent_edit")
    m_agent.HarnessEdit = type("HarnessEdit", (BaseModel,), {})
    sys.modules["models.agent_edit"] = m_agent

from models.review import (
    ReviewAnswerReceipt,
    SpeakerAnswer,
    SpellingAnswer,
    TaskAnswer,
)


class TestReviewModelValidation(unittest.TestCase):
    def test_speaker_answer_valid_person_id(self):
        ans = SpeakerAnswer(person_id="  p_123  ")
        self.assertEqual(ans.person_id, "p_123")

    def test_speaker_answer_valid_new_person_name(self):
        ans = SpeakerAnswer(new_person_name="  Alice Doe  ")
        self.assertEqual(ans.new_person_name, "Alice Doe")

    def test_speaker_answer_blank_person_id_rejected(self):
        with self.assertRaises(ValidationError):
            SpeakerAnswer(person_id="   ")

    def test_speaker_answer_non_string_person_id_rejected(self):
        with self.assertRaises(ValidationError):
            SpeakerAnswer(person_id=123)

    def test_speaker_answer_blank_new_person_name_rejected(self):
        with self.assertRaises(ValidationError):
            SpeakerAnswer(new_person_name="   ")

    def test_speaker_answer_non_string_new_person_name_rejected(self):
        with self.assertRaises(ValidationError):
            SpeakerAnswer(new_person_name=123)

    def test_task_answer_valid(self):
        ans = TaskAnswer(
            decision="accept",
            edited_description="  Finish report  ",
            workstream_id="  ws_456  ",
        )
        self.assertEqual(ans.edited_description, "Finish report")
        self.assertEqual(ans.workstream_id, "ws_456")

    def test_task_answer_blank_description_rejected(self):
        with self.assertRaises(ValidationError):
            TaskAnswer(decision="accept", edited_description="   ")

    def test_task_answer_non_string_description_rejected(self):
        with self.assertRaises(ValidationError):
            TaskAnswer(decision="accept", edited_description=123)

    def test_task_answer_blank_workstream_id_rejected(self):
        with self.assertRaises(ValidationError):
            TaskAnswer(decision="accept", workstream_id="   ")

    def test_spelling_answer_valid(self):
        ans = SpellingAnswer(value="  corrected_word  ")
        self.assertEqual(ans.value, "corrected_word")

    def test_spelling_answer_blank_rejected(self):
        with self.assertRaises(ValidationError):
            SpellingAnswer(value="   ")

    def test_spelling_answer_non_string_rejected(self):
        with self.assertRaises(ValidationError):
            SpellingAnswer(value=123)

    def test_review_answer_receipt_negative_remaining_rejected(self):
        with self.assertRaises(ValidationError):
            ReviewAnswerReceipt(item_id="i1", applied=True, remaining_today=-1)


if __name__ == "__main__":
    unittest.main()
