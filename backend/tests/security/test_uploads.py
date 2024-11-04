import pytest
import os
import wave
import tempfile

@pytest.mark.asyncio
async def test_upload_requires_auth(client):
    """Test that upload endpoint requires authentication"""
    files = {"file": ("test.wav", b"test", "audio/wav")}
    response = client.post("/speech_profile/v3/upload-audio", files=files)
    assert response.status_code == 401
    assert response.json()["detail"] == "Authorization header not found"

@pytest.mark.asyncio
async def test_upload_with_valid_auth(client):
    """Test that upload works with valid auth"""
    # Create a valid WAV file
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_wav:
        with wave.open(temp_wav.name, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            wav_file.writeframes(b'\x00' * 16000)  # 1 second of silence
    
    try:
        with open(temp_wav.name, 'rb') as wav_file:
            files = {"file": ("test.wav", wav_file, "audio/wav")}
            # Make sure the Authorization header is properly set
            headers = {
                "Authorization": "Bearer valid_token",
                "Accept": "application/json"
            }
            response = client.post(
                "/speech_profile/v3/upload-audio",
                files=files,
                headers=headers
            )
            print(f"\nUpload response: {response.status_code}")
            print(f"Response body: {response.text}")
            print(f"Response headers: {response.headers}")
            
            assert response.status_code == 200, f"Upload failed with status {response.status_code}: {response.text}"
            response_data = response.json()
            assert "url" in response_data, "Response should contain a URL"
            assert response_data["url"].startswith("https://"), "URL should be HTTPS"
    finally:
        os.unlink(temp_wav.name)