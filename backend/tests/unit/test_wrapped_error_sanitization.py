import pytest
from fastapi.testclient import TestClient

from backend.main import app  # Assuming the FastAPI app is created here
from backend.utils.wrapped.error_sanitizer import sanitize_error
from backend.models import WrappedStatus
from backend.db import get_db_session

client = TestClient(app)


@pytest.fixture(autouse=True)
async def clean_db():
    """Ensure a clean DB state for each test."""
    async with get_db_session() as session:
        await session.execute(WrappedStatus.delete())
        await session.commit()
    yield
    async with get_db_session() as session:
        await session.execute(WrappedStatus.delete())
        await session.commit()


def test_sanitize_error_basic():
    class CustomError(Exception):
        pass

    exc = CustomError("something went wrong")
    sanitized = sanitize_error(exc)
    assert sanitized == "CustomError: something went wrong"


def test_sanitize_error_strips_traceback():
    class DummyError(Exception):
        pass

    raw_msg = "DummyError: oops\nTraceback (most recent call last):\n  File \"app.py\", line 1"
    exc = DummyError(raw_msg)
    sanitized = sanitize_error(exc)
    # The sanitizer should remove the newline and the word Traceback
    assert "Traceback" not in sanitized
    assert "\n" not in sanitized
    assert sanitized.startswith("DummyError:")


def test_get_wrapped_status_masks_legacy_error():
    # Insert a legacy raw traceback into the DB directly.
    async def _setup():
        async with get_db_session() as session:
            session.add(
                WrappedStatus(
                    year=2025,
                    status="failed",
                    error="ValueError: secret_key=abcd1234\nTraceback (most recent call last): ..."
                )
            )
            await session.commit()
    # Run the async setup synchronously for the test client.
    import asyncio
    asyncio.run(_setup())

    response = client.get("/v1/wrapped/2025")
    assert response.status_code == 200
    data = response.json()
    assert data["year"] == 2025
    assert data["status"] == "failed"
    # The error should be generic, not contain the raw traceback or secret.
    assert data["error"] == "Internal server error"
