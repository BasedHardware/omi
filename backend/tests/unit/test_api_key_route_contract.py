import pytest
from fastapi import status
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from backend.routers.api_key_management import create_mcp_key_endpoint, create_developer_key_endpoint
from backend.models.api_key_models import ApiKeyValidationError

client = TestClient()

@pytest.mark.parametrize("test_input,expected_masked", [
    ("Invalid key format: abc123", "Invalid key format: [MASKED]"),
    ("Missing permissions: [user_id=123]", "Missing permissions: [user_id=[MASKED]]"),
    ("Key too short: 123", "Key too short: [MASKED]")
])
@patch('backend.routers.api_key_management.create_mcp_key')
def test_mcp_key_validation_sanitization(mock_create, test_input, expected_masked):
    mock_create.side_effect = ApiKeyValidationError(test_input)
    response = client.post("/api/keys/mcp", headers={"X-API-Key": "test"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert expected_masked in response.json()['error']

@pytest.mark.parametrize("test_input,expected_masked", [
    ("Invalid developer key: sensitive_data=abc123", "Invalid developer key: sensitive_data=[MASKED]"),
    ("Permission denied: user=test_user", "Permission denied: user=[MASKED]")
])
@patch('backend.routers.api_key_management.create_developer_key')
def test_developer_key_validation_sanitization(mock_create, test_input, expected_masked):
    mock_create.side_effect = ApiKeyValidationError(test_input)
    response = client.post("/api/keys/developer", headers={"X-API-Key": "test"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert expected_masked in response.json()['error']

def test_audit_logs_contain_masked_data(caplog):
    with patch('backend.routers.api_key_management.create_mcp_key') as mock_create:
        mock_create.side_effect = ApiKeyValidationError("Invalid key: user=john_doe, token=abc123")
        client.post("/api/keys/mcp", headers={"X-API-Key": "test"})

        log_record = caplog.records[-1]
        assert "user=[MASKED]" in log_record.message
        assert "token=[MASKED]" in log_record.message
