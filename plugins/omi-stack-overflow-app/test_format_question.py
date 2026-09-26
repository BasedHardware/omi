"""Unit tests for accepted-answer labeling (issue #13246)."""

from main import _format_question


def test_format_question_uses_accepted_answer_id_not_is_answered():
    item = {
        "title": "How do I parse JSON?",
        "question_id": 1,
        "score": 3,
        "answer_count": 2,
        "view_count": 10,
        # Answered, but nobody accepted an answer.
        "is_answered": True,
        "accepted_answer_id": None,
        "tags": ["python"],
        "link": "https://stackoverflow.com/q/1",
    }
    out = _format_question(item, 1, "stackoverflow")
    assert "| not accepted" in out
    assert out.count("accepted") == 1  # only inside "not accepted"


def test_format_question_marks_accepted_when_id_present():
    item = {
        "title": "How do I parse JSON?",
        "question_id": 1,
        "score": 3,
        "answer_count": 2,
        "view_count": 10,
        "is_answered": True,
        "accepted_answer_id": 99,
        "tags": ["python"],
        "link": "https://stackoverflow.com/q/1",
    }
    out = _format_question(item, 1, "stackoverflow")
    assert "accepted" in out
    assert "not accepted" not in out
