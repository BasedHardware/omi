import pytest
from fastapi import HTTPException

# Import the endpoint directly – adjust the import path if necessary.
from backend.routers.conversations import send_conversation_share_email
from backend.services.email import AmbiguousDeliveryError


# --------------------------------------------------------------------------- #
# Helper mock email service
# --------------------------------------------------------------------------- #
class MockEmailService:
    def __init__(self, exc: Exception | None = None):
        self._exc = exc

    async def send_share_email(self, conversation_id: str, email: str):
        if self._exc:
            raise self._exc
        return True


# --------------------------------------------------------------------------- #
# Test cases
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exception,expected_status,expected_detail",
    [
        (
            AmbiguousDeliveryError("SMTP timeout after 30s"),
            504,
            "Email delivery timed out.",
        ),
        (ValueError("Invalid email address format"), 503, "Email service unavailable."),
        (RuntimeError("Unexpected transport error"), 502, "Email delivery failed."),
    ],
)
async def test_send_conversation_share_email_error_sanitization(
    exception, expected_status, expected_detail
):
    """
    Ensure that the endpoint does not leak raw exception details and returns
    the expected sanitized message and HTTP status code.
    """
    mock_service = MockEmailService(exc=exception)

    with pytest.raises(HTTPException) as exc_info:
        await send_conversation_share_email(
            conversation_id="conv-123",
            email="test@example.com",
            email_service=mock_service,
        )

    http_exc = exc_info.value
    assert http_exc.status_code == expected_status
    assert http_exc.detail == expected_detail
