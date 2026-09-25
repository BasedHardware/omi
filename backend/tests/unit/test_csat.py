"""CSAT contract: config defaults on a missing doc, create-only ratings, error sanitization, and fallback resilience."""

from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.api_core.exceptions import AlreadyExists
import pytest

from database import csat as csat_db
from routers import csat as csat_router

UID = "uid-csat-1"
CSAT_ROUTER_FILE = Path(__file__).resolve().parents[2] / "routers" / "csat.py"


class _Snapshot:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return None if self._data is None else dict(self._data)


class _DocRef:
    def __init__(self, docs, doc_id):
        self._docs = docs
        self._doc_id = doc_id

    def get(self):
        return _Snapshot(self._doc_id, self._docs.get(self._doc_id))

    def create(self, data):
        # Same atomicity contract as Firestore: create never overwrites.
        if self._doc_id in self._docs:
            raise AlreadyExists(self._doc_id)
        self._docs[self._doc_id] = dict(data)


class _Collection:
    def __init__(self, docs):
        self._docs = docs

    def document(self, doc_id):
        return _DocRef(self._docs, doc_id)


class _FakeFirestore:
    def __init__(self):
        self._collections = {}

    def collection(self, name):
        return _Collection(self._collections.setdefault(name, {}))


class _MemoryCache:
    def __init__(self):
        self._store = {}

    def get_or_fetch(self, key, fetch, ttl=None):
        if key not in self._store:
            self._store[key] = fetch()
        return self._store[key]


def _install_fake_backend(monkeypatch):
    firestore = _FakeFirestore()
    monkeypatch.setattr(csat_db, "get_firestore_client", lambda: firestore)
    monkeypatch.setattr(csat_db, "get_memory_cache", lambda: _MemoryCache())
    return firestore


def _client(monkeypatch) -> TestClient:
    _install_fake_backend(monkeypatch)
    app = FastAPI()
    app.include_router(csat_router.router)
    app.dependency_overrides[csat_router.auth.get_current_user_uid] = lambda: UID
    return TestClient(app)


def test_get_returns_defaults_when_config_doc_is_missing(monkeypatch):
    client = _client(monkeypatch)
    response = client.get("/v1/csat/config", params={"platform": "macos"})
    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
        "title": "How would you rate Omi Desktop?",
        "body": "",
        "thank_you_text": "Thank you!",
        "refer_cta_text": "Enjoying Omi? Give a friend a free month.",
        "question_threshold": 3,
        "comment_max_score": 3,
        "revision": 0,
    }


def test_get_config_falls_back_to_defaults_on_storage_failure(monkeypatch):
    def failing_get_config(*args, **kwargs):
        raise RuntimeError("GoogleCloudError: 503 Deadline Exceeded")

    monkeypatch.setattr(csat_router.csat, "get_product_config", failing_get_config)
    client = _client(monkeypatch)
    response = client.get("/v1/csat/config", params={"platform": "macos"})
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["title"] == "How would you rate Omi Desktop?"
    assert "GoogleCloudError" not in response.text


def test_post_persists_platform_scoped_rating_and_second_post_conflicts(monkeypatch):
    firestore = _install_fake_backend(monkeypatch)
    app = FastAPI()
    app.include_router(csat_router.router)
    app.dependency_overrides[csat_router.auth.get_current_user_uid] = lambda: UID
    client = TestClient(app)

    payload = {
        "platform": "macos",
        "app_version": "1.2.3",
        "score": 2,
        "comment": "too slow",
        "revision": 1,
    }
    response = client.post("/v1/csat/ratings", json=payload)
    assert response.status_code == 201
    assert response.json() == {"id": f"macos_{UID}", "created": True}

    stored = firestore._collections[csat_db.RATINGS_COLLECTION][f"macos_{UID}"]
    assert stored["uid"] == UID
    assert stored["platform"] == "macos"
    assert stored["score"] == 2
    assert stored["comment"] == "too slow"
    assert stored["revision"] == 1
    assert stored["created_at"] > 0

    # Resubmit (client retry, double-tap): 409, and the first answer stands.
    again = client.post("/v1/csat/ratings", json={**payload, "score": 5, "comment": "changed my mind"})
    assert again.status_code == 409
    assert again.json() == {"id": f"macos_{UID}", "created": False}
    unchanged = firestore._collections[csat_db.RATINGS_COLLECTION][f"macos_{UID}"]
    assert unchanged["score"] == 2
    assert unchanged["comment"] == "too slow"


def test_post_sanitizes_storage_failure_to_503(monkeypatch):
    def failing_submit_rating(*args, **kwargs):
        raise RuntimeError("GoogleCloudError: 503 Deadline Exceeded on firestore write")

    monkeypatch.setattr(csat_router.csat, "submit_rating", failing_submit_rating)
    client = _client(monkeypatch)

    payload = {
        "platform": "macos",
        "app_version": "1.2.3",
        "score": 4,
        "comment": "great",
        "revision": 1,
    }
    response = client.post("/v1/csat/ratings", json=payload)
    assert response.status_code == 503
    assert response.json() == {"detail": "CSAT service temporarily unavailable"}
    assert "GoogleCloudError" not in response.text
    assert "Deadline Exceeded" not in response.text


def test_post_drops_comment_above_comment_max_score(monkeypatch):
    firestore = _install_fake_backend(monkeypatch)
    app = FastAPI()
    app.include_router(csat_router.router)
    app.dependency_overrides[csat_router.auth.get_current_user_uid] = lambda: UID
    client = TestClient(app)

    response = client.post(
        "/v1/csat/ratings",
        json={"platform": "macos", "score": 5, "comment": "love it", "revision": 0},
    )
    assert response.status_code == 201
    stored = firestore._collections[csat_db.RATINGS_COLLECTION][f"macos_{UID}"]
    # Server wins over whatever the client sends for a high score.
    assert stored["comment"] == ""


def test_post_rejects_invalid_platform_and_score(monkeypatch):
    client = _client(monkeypatch)
    assert client.post("/v1/csat/ratings", json={"platform": "web", "score": 3}).status_code == 400
    assert client.post("/v1/csat/ratings", json={"platform": "macos", "score": 0}).status_code == 400
    assert client.post("/v1/csat/ratings", json={"platform": "macos", "score": 6}).status_code == 400
    assert client.post("/v1/csat/ratings", json={"platform": "macos", "score": 3, "revision": -1}).status_code == 400
    assert (
        client.post(
            "/v1/csat/ratings",
            json={"platform": "macos", "score": 3, "revision": 1_000_000_001},
        ).status_code
        == 400
    )


def test_post_trims_and_lowercases_platform(monkeypatch):
    firestore = _install_fake_backend(monkeypatch)
    app = FastAPI()
    app.include_router(csat_router.router)
    app.dependency_overrides[csat_router.auth.get_current_user_uid] = lambda: UID
    client = TestClient(app)

    response = client.post("/v1/csat/ratings", json={"platform": "  MacOS  ", "score": 4, "revision": 0})
    assert response.status_code == 201
    stored = firestore._collections[csat_db.RATINGS_COLLECTION][f"macos_{UID}"]
    assert stored["platform"] == "macos"


def test_normalize_config_clamps_stored_doc(monkeypatch):
    normalized = csat_db.normalize_config(
        {
            "enabled": False,
            "title": "  ",
            "question_threshold": 500,
            "comment_max_score": 9,
            "revision": -3,
        }
    )
    assert normalized["enabled"] is False
    # Blank copy falls back to the default, never an empty bar.
    assert normalized["title"] == csat_db.DEFAULT_TITLE
    assert normalized["question_threshold"] == 50
    assert normalized["comment_max_score"] == 5
    assert normalized["revision"] == 0


def test_static_zero_raw_exception_reflection():
    candidates = [
        CSAT_ROUTER_FILE,
        Path(__file__).resolve().parent / "csat.py",
    ]
    target = next((p for p in candidates if p.exists()), None)
    assert target is not None, f"csat.py router file must exist"
    source = target.read_text(encoding="utf-8")
    assert "detail=str(e)" not in source
    assert "detail=str(exc)" not in source
    assert 'detail=f"{e' not in source
    assert 'detail=f"{exc' not in source
