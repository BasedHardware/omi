import os
import sys
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from testing.import_isolation import AutoMockModule, stub_modules

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

_STUB_MODULES = [
    "pinecone",
    "typesense",
    "stripe",
    "pycountry",
    "firebase_admin",
    "firebase_admin.auth",
    "firebase_admin.firestore",
    "google.cloud.firestore",
    "database._client",
    "database.vector_db",
    "services.users.account_deletion",
    "services.users.data_export",
    "utils.twilio_service",
    "utils.apps",
    "utils.llm.clients",
    "anthropic",
    "openai",
]

users_router = None


@pytest.fixture(scope="module", autouse=True)
def _isolate_dependencies():
    fakes = {name: AutoMockModule(name) for name in _STUB_MODULES}
    with stub_modules(fakes):
        from routers import users as _users_router

        mod = sys.modules[__name__]
        mod.users_router = _users_router
        yield


def test_get_single_person_valid_returns_person():
    """GET /v1/users/people/{person_id} returns validated Person model for valid document."""
    valid_doc = {
        "id": "person-123",
        "name": "Jane Doe",
        "speech_samples": ["gs://bucket/sample1.wav"],
    }

    with patch.object(users_router, "get_person", return_value=valid_doc):
        person = users_router.get_single_person(
            person_id="person-123", include_speech_samples=False, uid="user-abc"
        )
        assert person.id == "person-123"
        assert person.name == "Jane Doe"
        assert person.speech_samples == ["gs://bucket/sample1.wav"]


def test_get_single_person_corrupted_missing_name_raises_502():
    """GET /v1/users/people/{person_id} raises 502 with clean detail when stored document is missing required name."""
    corrupted_doc = {
        "id": "person-corrupted-1",
        # missing required 'name' field
    }

    with (
        patch.object(users_router, "get_person", return_value=corrupted_doc),
        patch.object(users_router.logger, "error") as mock_error,
    ):
        with pytest.raises(HTTPException) as exc_info:
            users_router.get_single_person(
                person_id="person-corrupted-1",
                include_speech_samples=False,
                uid="user-abc",
            )

        assert exc_info.value.status_code == 502
        assert exc_info.value.detail == "Stored person record is malformed"
        mock_error.assert_called_once()
        log_msg = mock_error.call_args[0][0]
        assert "person-corrupted-1" in log_msg
        assert "user-abc" in log_msg


def test_get_single_person_corrupted_invalid_type_raises_502():
    """GET /v1/users/people/{person_id} raises 502 with clean detail when fields fail validation."""
    corrupted_doc = {
        "id": "person-corrupted-2",
        "name": "Valid Name",
        "speech_samples": "not-a-list-of-strings",  # expects List[str]
    }

    with (
        patch.object(users_router, "get_person", return_value=corrupted_doc),
        patch.object(users_router.logger, "error") as mock_error,
    ):
        with pytest.raises(HTTPException) as exc_info:
            users_router.get_single_person(
                person_id="person-corrupted-2",
                include_speech_samples=False,
                uid="user-abc",
            )

        assert exc_info.value.status_code == 502
        assert exc_info.value.detail == "Stored person record is malformed"
        mock_error.assert_called_once()


def test_get_single_person_not_found_raises_404():
    """GET /v1/users/people/{person_id} raises 404 when person does not exist."""
    with patch.object(users_router, "get_person", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            users_router.get_single_person(
                person_id="nonexistent-person",
                include_speech_samples=False,
                uid="user-abc",
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Person not found"


def test_get_single_person_includes_speech_samples():
    """GET /v1/users/people/{person_id} resolves signed URLs when include_speech_samples=True."""
    valid_doc = {
        "id": "person-123",
        "name": "Jane Doe",
        "speech_samples": ["gs://bucket/sample1.wav"],
    }

    with (
        patch.object(users_router, "get_person", return_value=valid_doc),
        patch.object(
            users_router,
            "get_speech_sample_signed_urls",
            return_value=["https://signed-url.example.com/sample1.wav"],
        ),
    ):
        person = users_router.get_single_person(
            person_id="person-123", include_speech_samples=True, uid="user-abc"
        )
        assert person.speech_samples == ["https://signed-url.example.com/sample1.wav"]
