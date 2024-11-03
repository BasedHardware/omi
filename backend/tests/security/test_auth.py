import pytest
from fastapi import HTTPException

@pytest.mark.asyncio
async def test_root_endpoint(client):
    """Test that the root endpoint works"""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "API is running"}

@pytest.mark.asyncio
async def test_unauthorized_access(client):
    """Test that endpoints require authentication"""
    # Test a few key endpoints that should require auth
    endpoints = [
        ("/memories/v1/memories", {"limit": "10", "offset": "0"}),
        ("/facts/v1/facts", {"limit": "10", "offset": "0"}),
        ("/chat/v1/messages", {"limit": "10", "offset": "0"}),
        ("/plugins/v2/plugins", {}),
        ("/speech_profile/v3/speech-profile", None),
        ("/users/v1/users/people", None),
        ("/processing_memories/v1/processing-memories", None),
        ("/trends/v1/trends", None),
    ]
    
    for endpoint, params in endpoints:
        response = client.get(endpoint, params=params if params else {})
        print(f"Testing {endpoint}: {response.status_code}")
        assert response.status_code == 401
        assert response.json()["detail"] == "Authorization header not found"

@pytest.mark.asyncio
async def test_invalid_firebase_token(client):
    """Test invalid Firebase token handling"""
    headers = {"Authorization": "Bearer invalid_token"}
    params = {"limit": "10", "offset": "0"}
    response = client.get("/memories/v1/memories", headers=headers, params=params)
    assert response.status_code == 401
    assert response.json()["detail"] == "Authorization header not found"

@pytest.mark.asyncio
async def test_expired_token(client):
    """Test expired token handling"""
    expired_token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9..."
    headers = {"Authorization": f"Bearer {expired_token}"}
    params = {"limit": "10", "offset": "0"}
    response = client.get("/memories/v1/memories", headers=headers, params=params)
    assert response.status_code == 401
    assert response.json()["detail"] == "Authorization header not found"