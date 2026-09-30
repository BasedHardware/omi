"""
Unit tests for feedback validation and boundary guards.
"""
import pytest
from fastapi.testclient import TestClient

from backend.database.feedback import (
    _idempotent_event_id,
    _normalize_id,
    get_feedback_event,
    list_negative_events,
    record_feedback_event,
    save_report,
)
from backend.main import app


class TestNormalizeId:
    def test_valid_id(self):
        assert _normalize_id("  user123  ") == "user123"

    def test_empty_string(self):
        with pytest.raises(ValueError, match="ID cannot be empty"):
            _normalize_id("   ")

    def test_whitespace_only(self):
        with pytest.raises(ValueError, match="ID cannot be empty"):
            _normalize_id("\t\n")

    def test_non_string(self):
        with pytest.raises(ValueError, match="Expected string"):
            _normalize_id(123)


class TestIdempotentEventId:
    def test_consistent_hash(self):
        uid = "user1"
        feedback_id = "fb1"
        hash1 = _idempotent_event_id(uid, feedback_id)
        hash2 = _idempotent_event_id(uid, feedback_id)
        assert hash1 == hash2

    def test_whitespace_normalization(self):
        hash1 = _idempotent_event_id(" user1 ", " fb1 ")
        hash2 = _idempotent_event_id("user1", "fb1")
        assert hash1 == hash2

    def test_invalid_uid(self):
        with pytest.raises(ValueError):
            _idempotent_event_id("", "fb1")

    def test_invalid_feedback_id(self):
        with pytest.raises(ValueError):
            _idempotent_event_id("user1", "   ")


class TestRecordFeedbackEvent:
    def test_valid_feedback(self, monkeypatch):
        def mock_set(*args, **kwargs):
            pass
        
        monkeypatch.setattr(
            "backend.database.feedback.get_db",
            lambda: type("MockDB", (), {
                "collection": lambda self, _: type("MockCollection", (), {
                    "document": lambda self, _: type("MockDoc", (), {
                        "set": mock_set
                    })()
                })()
            })()
        )
        
        result = record_feedback_event(
            uid="user1",
            target_id="target1",
            feedback_type="positive"
        )
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hex length

    def test_whitespace_handling(self, monkeypatch):
        mock_set_calls = []
        
        def mock_set(data, **kwargs):
            mock_set_calls.append(data)
        
        monkeypatch.setattr(
            "backend.database.feedback.get_db",
            lambda: type("MockDB", (), {
                "collection": lambda self, _: type("MockCollection", (), {
                    "document": lambda self, _: type("MockDoc", (), {
                        "set": mock_set
                    })()
                })()
            })()
        )
        
        record_feedback_event(
            uid="  user1  ",
            target_id=" target1 ",
            feedback_type="positive"
        )
        
        assert mock_set_calls[0]["uid"] == "user1"
        assert mock_set_calls[0]["target_id"] == "target1"

    def test_invalid_uid(self):
        with pytest.raises(ValueError):
            record_feedback_event(
                uid="",
                target_id="target1",
                feedback_type="positive"
            )


class TestGetFeedbackEvent:
    def test_valid_feedback_id(self, monkeypatch):
        mock_doc = type("MockDoc", (), {
            "exists": True,
            "to_dict": lambda self: {"uid": "user1", "target_id": "target1"}
        })()
        
        monkeypatch.setattr(
            "backend.database.feedback.get_db",
            lambda: type("MockDB", (), {
                "collection": lambda self, _: type("MockCollection", (), {
                    "document": lambda self, _: mock_doc
                })()
            })()
        )
        
        result = get_feedback_event("fb1")
        assert result == {"uid": "user1", "target_id": "target1"}

    def test_nonexistent_feedback(self, monkeypatch):
        mock_doc = type("MockDoc", (), {"exists": False})()
        
        monkeypatch.setattr(
            "backend.database.feedback.get_db",
            lambda: type("MockDB", (), {
                "collection": lambda self, _: type("MockCollection", (), {
                    "document": lambda self, _: mock_doc
                })()
            })()
        )
        
        result = get_feedback_event("nonexistent")
        assert result is None

    def test_invalid_feedback_id(self):
        with pytest.raises(ValueError):
            get_feedback_event("")


class TestSaveReport:
    def test_valid_report(self, monkeypatch):
        mock_set_calls = []
        
        def mock_set(data, **kwargs):
            mock_set_calls.append(data)
        
        monkeypatch.setattr(
            "backend.database.feedback.get_db",
            lambda: type("MockDB", (), {
                "collection": lambda self, _: type("MockCollection", (), {
                    "document": lambda self, _: type("MockDoc", (), {
                        "set": mock_set
                    })()
                })()
            })()
        )
        
        save_report("report1", {"data": "test"})
        assert mock_set_calls[0] == {"data": "test"}

    def test_invalid_report_id(self):
        with pytest.raises(ValueError):
            save_report("", {"data": "test"})

    def test_non_dict_data(self):
        with pytest.raises(ValueError):
            save_report("report1", "not a dict")


class TestListNegativeEvents:
    def test_valid_uid(self, monkeypatch):
        mock_stream = [
            type("MockDoc", (), {"to_dict": lambda self: {"id": "1"}})(),
            type("MockDoc", (), {"to_dict": lambda self: {"id": "2"}})(),
        ]
        
        monkeypatch.setattr(
            "backend.database.feedback.get_db",
            lambda: type("MockDB", (), {
                "collection": lambda self, _: type("MockCollection", (), {
                    "where": lambda *args, **kwargs: type("MockQuery", (), {
                        "order_by": lambda *args, **kwargs: type("MockQuery", (), {
                            "limit": lambda *args, **kwargs: type("MockQuery", (), {
                                "stream": lambda self: mock_stream
                            })()
                        })()
                    })()
                })()
            })()
        )
        
        result = list_negative_events("user1")
        assert len(result) == 2

    def test_invalid_uid(self):
        with pytest.raises(ValueError):
            list_negative_events("")

    def test_invalid_limit(self):
        with pytest.raises(ValueError):
            list_negative_events("user1", limit=-1)


class TestMobileFeedbackRouter:
    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_submit_feedback_success(self, client, monkeypatch):
        def mock_record(*args, **kwargs):
            return "mock_feedback_id"
        
        monkeypatch.setattr(
            "backend.routers.mobile_feedback.record_feedback_event",
            mock_record
        )
        
        response = client.post(
            "/api/v1/mobile/feedback/submit",
            json={
                "uid": "user1",
                "target_id": "target1",
                "feedback_type": "positive"
            }
        )
        
        assert response.status_code == 200
        assert response.json()["feedback_id"] == "mock_feedback_id"

    def test_submit_feedback_invalid_uid(self, client, monkeypatch):
        def mock_record(*args, **kwargs):
            raise ValueError("ID cannot be empty or whitespace-only")
        
        monkeypatch.setattr(
            "backend.routers.mobile_feedback.record_feedback_event",
            mock_record
        )
        
        response = client.post(
            "/api/v1/mobile/feedback/submit",
            json={
                "uid": "",
                "target_id": "target1",
                "feedback_type": "positive"
            }
        )
        
        assert response.status_code == 400
        assert "ID cannot be empty" in response.json()["detail"]

    def test_submit_feedback_missing_field(self, client, monkeypatch):
        response = client.post(
            "/api/v1/mobile/feedback/submit",
            json={
                "target_id": "target1",
                "feedback_type": "positive"
            }
        )
        
        assert response.status_code == 400
        assert "Missing required field" in response.json()["detail"]
