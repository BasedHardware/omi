"""End-to-end tests for Omi Recall. Run: pytest test_main.py -v"""

import os
import tempfile
import zipfile

os.environ["RECALL_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["OPENAI_API_KEY"] = ""  # force heuristic path in tests

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

client = TestClient(main.app)
UID = "test_user_123"

SAMPLE_CONVERSATION = {
    "id": "conv_abc",
    "structured": {
        "title": "Learning about transformers",
        "overview": (
            "The user discussed machine learning with a mentor. "
            "The transformer architecture was invented by Google researchers in 2017. "
            "Attention is a mechanism that lets a model weigh the relevance of each token. "
            "GPT means Generative Pre-trained Transformer and was released by OpenAI."
        ),
    },
    "transcript_segments": [
        {"text": "So the key idea is that self-attention scales quadratically with sequence length.", "is_user": False, "start": 0, "end": 5},
        {"text": "Right, and that is why long-context models are expensive to run.", "is_user": True, "start": 5, "end": 9},
    ],
}


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_manifest_has_four_tools():
    tools = client.get("/.well-known/omi-tools.json").json()["tools"]
    names = {t["name"] for t in tools}
    assert names == {"quiz_me", "reveal_answer", "grade_card", "deck_stats"}
    for tool in tools:
        assert tool["endpoint"].startswith("/tools/")
        assert tool["method"] == "POST"


def test_webhook_creates_cards():
    resp = client.post(f"/webhook?uid={UID}", json=SAMPLE_CONVERSATION)
    assert resp.status_code == 200
    assert resp.json()["cards_created"] > 0


def test_quiz_returns_due_cards():
    resp = client.post("/tools/quiz_me", json={"uid": UID, "limit": 5})
    result = resp.json()["result"]
    assert "card_id=" in result


def _first_card_id() -> str:
    result = client.post("/tools/quiz_me", json={"uid": UID}).json()["result"]
    line = next((l for l in result.split("\n") if "card_id=" in l), None)
    assert line is not None, (
        f"No due cards found for {UID}. "
        "Ensure test_webhook_creates_cards has been called before using _first_card_id()."
    )
    return line.split("card_id=")[1].split(":")[0].split(" ")[0]


def test_reveal_answer():
    card_id = _first_card_id()
    resp = client.post("/tools/reveal_answer", json={"uid": UID, "card_id": card_id})
    assert resp.json()["result"].startswith("Answer:")


def test_grade_good_schedules_next_review():
    card_id = _first_card_id()
    resp = client.post("/tools/grade_card", json={"uid": UID, "card_id": card_id, "grade": "good"})
    assert "Next review in 1 day" in resp.json()["result"]
    # The card must no longer be due
    result = client.post("/tools/quiz_me", json={"uid": UID, "limit": 10}).json()["result"]
    assert f"card_id={card_id}" not in result


def test_grade_again_keeps_card_in_learning():
    card_id = _first_card_id()
    resp = client.post("/tools/grade_card", json={"uid": UID, "card_id": card_id, "grade": "again"})
    assert "10 minutes" in resp.json()["result"]


def test_sm2_intervals_grow():
    state = {"ease": 2.5, "interval_days": 0, "reps": 0, "lapses": 0}
    intervals = []
    for _ in range(4):
        state = main.sm2_update(state["ease"], state["interval_days"], state["reps"], state["lapses"], "good")
        intervals.append(state["interval_days"])
    assert intervals[0] == 1 and intervals[1] == 6
    assert intervals[2] > intervals[1] and intervals[3] > intervals[2]


def test_deck_stats_includes_export_link():
    resp = client.post("/tools/deck_stats", json={"uid": UID})
    assert f"/deck/{UID}.apkg" in resp.json()["result"]


def test_anki_export_is_valid_apkg():
    resp = client.get(f"/deck/{UID}.apkg")
    assert resp.status_code == 200
    assert resp.headers["content-disposition"].endswith('.apkg"')
    # .apkg files are zip archives containing an Anki SQLite collection.
    # Write, close, and reopen by path (Windows locks open file handles,
    # so we can't reopen a still-open NamedTemporaryFile there).
    fd, path = tempfile.mkstemp(suffix=".apkg")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(resp.content)
        assert zipfile.is_zipfile(path)
    finally:
        os.remove(path)


def test_empty_conversation_creates_nothing():
    resp = client.post("/webhook?uid=empty_user", json={"structured": {}, "transcript_segments": []})
    assert resp.json()["cards_created"] == 0


def test_unknown_user_deck_404():
    assert client.get("/deck/nobody.apkg").status_code == 404