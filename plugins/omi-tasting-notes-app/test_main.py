"""Tests for the Omi Tasting Notes plugin."""

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Point storage at a temp dir before importing the app.
_TMP = tempfile.mkdtemp(prefix="tasting-notes-test-")
os.environ["TASTING_DATA_DIR"] = _TMP

import main as app_module  # noqa: E402

client = TestClient(app_module.app)
UID = "test-user-1"

BAROLO_TRANSCRIPT = (
    "We just got to the winery in Piedmont and the tasting room is beautiful. "
    "This Barolo Riserva 2019 has such tar and roses on the bouquet, firm tannins, "
    "long finish. I'd give it 94 points. We should definitely buy a case to take home."
)

COFFEE_TRANSCRIPT = (
    "At the roastery cupping this morning. The single origin Ethiopian pour over "
    "has bright bergamot on the nose, 4.5 stars from me, super clean finish."
)

LUNCH_TRANSCRIPT = (
    "Grabbed lunch downtown and talked about the quarterly roadmap. "
    "The new hire starts Monday. We should revisit the budget next week."
)


@pytest.fixture(autouse=True)
def clean_data_dir():
    for path in Path(_TMP).glob("*.json"):
        path.unlink()
    yield


# --- detection -------------------------------------------------------------

def test_detect_wine_conversation():
    beverage, score = app_module.detect_tasting(BAROLO_TRANSCRIPT)
    assert beverage == "wine"
    assert score >= app_module.TASTING_DETECT_THRESHOLD


def test_detect_coffee_conversation():
    beverage, score = app_module.detect_tasting(COFFEE_TRANSCRIPT)
    assert beverage == "coffee"
    assert score >= app_module.TASTING_DETECT_THRESHOLD


def test_no_detection_for_ordinary_conversation():
    beverage, score = app_module.detect_tasting(LUNCH_TRANSCRIPT)
    assert beverage is None


def test_detection_is_conservative_with_single_keyword():
    # One stray "wine" mention in an unrelated chat must not file a tasting.
    beverage, _ = app_module.detect_tasting("We had wine with dinner and talked taxes.")
    assert beverage is None


# --- score parsing ----------------------------------------------------------

def test_parse_100_point_score():
    assert app_module.parse_score("I'd give it 94 points") == 94.0


def test_parse_star_score_normalized():
    assert app_module.parse_score("4.5 stars from me") == 90.0


def test_parse_ten_point_score_normalized():
    assert app_module.parse_score("solid 9/10") == 90.0


def test_parse_score_clamped():
    assert app_module.parse_score("110 points, perfect") == 100.0


def test_parse_score_none():
    assert app_module.parse_score("it was nice") is None


# --- verdict inference ------------------------------------------------------

def test_infer_buy_verdict():
    assert app_module.infer_verdict("We should buy a case to take home") == "buy"


def test_infer_skip_verdict():
    assert app_module.infer_verdict("I wouldn't buy this one") == "skip"


def test_skip_wins_over_buy_on_negation():
    # "wouldn't buy" contains "buy" — negation must win.
    assert app_module.infer_verdict("wouldn't buy, not worth it") == "skip"


def test_no_verdict_without_purchase_language():
    assert app_module.infer_verdict("lovely tannins, long finish") is None


# --- ambient webhook --------------------------------------------------------

def test_webhook_detects_and_stores_candidate():
    response = client.post(
        "/webhook/tasting-candidate",
        json={"uid": UID, "text": BAROLO_TRANSCRIPT, "conversation_id": "conv-1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["detected"] is True
    assert body["beverage_type"] == "wine"
    assert body["score_100"] == 94.0
    assert body["verdict"] == "buy"
    assert body["needs_review"] is True


def test_webhook_ignores_non_tasting():
    response = client.post(
        "/webhook/tasting-candidate", json={"uid": UID, "text": LUNCH_TRANSCRIPT}
    )
    assert response.status_code == 200
    assert response.json()["detected"] is False


def test_webhook_requires_text():
    # This codebase's convention: validation errors return 200 with an error body.
    response = client.post("/webhook/tasting-candidate", json={"uid": UID})
    assert response.status_code == 200
    assert response.json()["error"] is not None


# --- chat tools --------------------------------------------------------------

def test_log_tasting_round_trip():
    log = client.post(
        "/tools/log_tasting",
        json={
            "uid": UID,
            "beverage_type": "wine",
            "name": "Barolo Riserva",
            "producer": "G.D. Vajra",
            "vintage": "2019",
            "region": "Piedmont, Italy",
            "varietal": "Nebbiolo",
            "nose": "tar and roses",
            "palate": "firm tannins, cherry",
            "finish": "long",
            "score_100": 94,
            "verdict": "buy",
        },
    )
    assert log.status_code == 200
    assert log.json()["error"] is None
    assert "Barolo Riserva" in log.json()["result"]
    assert "94" in log.json()["result"]

    tasting_id = log.json()["result"]  # id is shown in list, fetch via list
    listing = client.post("/tools/list_tastings", json={"uid": UID})
    assert "Barolo Riserva" in listing.json()["result"]

    # Extract id from the list output and fetch full details.
    import re

    match = re.search(r"\(id: ([0-9a-f]{8})\)", listing.json()["result"])
    assert match
    detail = client.post(
        "/tools/get_tasting", json={"uid": UID, "tasting_id": match.group(1)}
    )
    assert detail.json()["error"] is None
    assert "Nebbiolo" in detail.json()["result"]
    assert tasting_id is not None


def test_log_tasting_rejects_bad_beverage():
    response = client.post(
        "/tools/log_tasting", json={"uid": UID, "beverage_type": "kombucha"}
    )
    assert response.status_code == 200
    assert "beverage_type" in response.json()["error"]


def test_log_tasting_rejects_out_of_range_score():
    response = client.post(
        "/tools/log_tasting", json={"uid": UID, "score_100": 150}
    )
    assert response.status_code == 200
    assert response.json()["error"] is not None


def test_list_tastings_empty():
    response = client.post("/tools/list_tastings", json={"uid": UID})
    assert response.json()["result"] == "No tastings logged yet."


def test_list_tastings_filters_by_beverage():
    client.post("/tools/log_tasting", json={"uid": UID, "beverage_type": "wine", "name": "Barolo"})
    client.post("/tools/log_tasting", json={"uid": UID, "beverage_type": "coffee", "name": "Ethiopian"})
    wines = client.post(
        "/tools/list_tastings", json={"uid": UID, "beverage_type": "wine"}
    )
    assert "Barolo" in wines.json()["result"]
    assert "Ethiopian" not in wines.json()["result"]


def test_get_tasting_unknown_id():
    response = client.post("/tools/get_tasting", json={"uid": UID, "tasting_id": "deadbeef"})
    assert response.json()["error"] is not None


def test_tasting_stats():
    client.post(
        "/tools/log_tasting",
        json={"uid": UID, "beverage_type": "wine", "name": "Barolo", "score_100": 94, "verdict": "buy"},
    )
    client.post(
        "/tools/log_tasting",
        json={"uid": UID, "beverage_type": "wine", "name": "Chianti", "score_100": 86, "verdict": "skip"},
    )
    response = client.post("/tools/tasting_stats", json={"uid": UID})
    result = response.json()["result"]
    assert "2 total" in result
    assert "avg 90.0/100" in result
    assert "1 buy verdicts" in result


def test_confirm_candidate_applies_corrections():
    hook = client.post(
        "/webhook/tasting-candidate", json={"uid": UID, "text": BAROLO_TRANSCRIPT}
    )
    candidate_id = hook.json()["candidate_id"]
    confirm = client.post(
        "/tools/confirm_candidate",
        json={"uid": UID, "candidate_id": candidate_id, "name": "Barolo Riserva 2019", "producer": "G.D. Vajra"},
    )
    assert confirm.json()["error"] is None
    assert "Barolo Riserva 2019" in confirm.json()["result"]

    # Candidate is consumed; confirming again must fail.
    again = client.post(
        "/tools/confirm_candidate", json={"uid": UID, "candidate_id": candidate_id}
    )
    assert again.json()["error"] is not None


def test_storage_is_per_user():
    client.post("/tools/log_tasting", json={"uid": "alice", "name": "Barolo"})
    bobs = client.post("/tools/list_tastings", json={"uid": "bob"})
    assert bobs.json()["result"] == "No tastings logged yet."


# --- manifest / health -------------------------------------------------------

def test_manifest_lists_five_tools():
    response = client.get("/.well-known/omi-tools.json")
    assert response.status_code == 200
    tools = {t["name"] for t in response.json()["tools"]}
    assert tools == {
        "log_tasting",
        "list_tastings",
        "get_tasting",
        "tasting_stats",
        "confirm_candidate",
    }


def test_health():
    assert client.get("/health").json() == {"status": "ok"}
