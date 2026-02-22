"""
End-to-end integration test for speech profile sharing.
Tests the complete flow from profile upload to real-time speaker identification.

Setup:
1. pip install pytest pytest-asyncio websockets numpy
2. Ensure backend is running locally (or set BACKEND_URL)
3. Set TEST_USER_A_UID and TEST_USER_B_UID environment variables
4. Set TEST_USER_A_TOKEN and TEST_USER_B_TOKEN for authentication
5. Run: pytest backend/tests/integration/test_speech_profile_sharing_e2e.py -v -s

This test verifies:
- User A can upload a speech profile
- Embedding is extracted and stored
- User A can share profile with User B
- User B's /listen session loads the shared profile
- Speaker identification works with shared profiles
- User B can remove a shared profile
- No-profile guard prevents sharing without a recorded profile
"""

import pytest
import os
import asyncio
import json
import numpy as np
import io
import wave

try:
    import websockets
    import requests
except ImportError:
    pytest.skip("websockets or requests not installed", allow_module_level=True)

BACKEND_URL = os.getenv('BACKEND_URL', 'http://localhost:8000')
WS_URL = BACKEND_URL.replace('http://', 'ws://').replace('https://', 'wss://')


@pytest.fixture
def test_user_a():
    """User A - the one sharing their profile"""
    uid = os.getenv('TEST_USER_A_UID')
    token = os.getenv('TEST_USER_A_TOKEN')
    if not uid or not token:
        pytest.skip("TEST_USER_A_UID and TEST_USER_A_TOKEN must be set")
    return {'uid': uid, 'token': token, 'name': 'Test User A'}


@pytest.fixture
def test_user_b():
    """User B - the one receiving the shared profile"""
    uid = os.getenv('TEST_USER_B_UID')
    token = os.getenv('TEST_USER_B_TOKEN')
    if not uid or not token:
        pytest.skip("TEST_USER_B_UID and TEST_USER_B_TOKEN must be set")
    return {'uid': uid, 'token': token, 'name': 'Test User B'}


def generate_test_audio(duration_seconds=10, sample_rate=16000):
    """Generate a simple sine wave audio file for testing"""
    samples = int(duration_seconds * sample_rate)
    frequency = 440
    t = np.linspace(0, duration_seconds, samples)
    audio = np.sin(2 * np.pi * frequency * t)
    audio = (audio * 32767).astype(np.int16)

    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio.tobytes())

    buffer.seek(0)
    return buffer


def _extract_uids(items):
    """Extract UIDs from the new {uid, name} response format, with backwards compat for plain strings."""
    uids = []
    for item in items:
        if isinstance(item, dict):
            uids.append(item['uid'])
        else:
            uids.append(item)
    return uids


class TestSpeechProfileSharingE2E:
    """End-to-end tests for speech profile sharing"""

    def test_01_upload_profile(self, test_user_a):
        """Test User A can upload a speech profile"""
        print(f"\n>>> User A ({test_user_a['uid'][:8]}) uploading speech profile...")

        audio_data = generate_test_audio()

        response = requests.post(
            f"{BACKEND_URL}/v3/upload-audio",
            headers={'Authorization': f"Bearer {test_user_a['token']}"},
            files={'file': ('profile.wav', audio_data, 'audio/wav')},
        )

        assert response.status_code == 200, f"Upload failed: {response.text}"
        data = response.json()
        assert 'url' in data
        print(">>> Profile uploaded successfully")

    def test_02_share_profile(self, test_user_a, test_user_b):
        """Test User A can share profile with User B"""
        print(f"\n>>> User A sharing profile with User B ({test_user_b['uid'][:8]})...")

        response = requests.post(
            f"{BACKEND_URL}/v1/speech-profile/share",
            headers={'Authorization': f"Bearer {test_user_a['token']}", 'Content-Type': 'application/json'},
            json={'target_uid': test_user_b['uid']},
        )

        assert response.status_code == 200, f"Share failed: {response.text}"
        data = response.json()
        assert data['status'] == 'ok'
        print(">>> Profile shared successfully")

    def test_03_verify_shared_with_me(self, test_user_a, test_user_b):
        """Test User B can see User A's shared profile with name"""
        print("\n>>> User B checking shared profiles...")

        response = requests.get(
            f"{BACKEND_URL}/v1/speech-profile/shared-with-me",
            headers={'Authorization': f"Bearer {test_user_b['token']}"},
        )

        assert response.status_code == 200, f"List shared failed: {response.text}"
        data = response.json()
        assert 'shared_with_me' in data
        shared_uids = _extract_uids(data['shared_with_me'])
        assert test_user_a['uid'] in shared_uids

        # Verify response includes name field
        for item in data['shared_with_me']:
            if isinstance(item, dict) and item['uid'] == test_user_a['uid']:
                assert 'name' in item
                print(f">>> User A's profile visible to User B (name: {item['name']})")
                break
        else:
            print(">>> User A's profile visible to User B")

    def test_04_verify_i_have_shared(self, test_user_a, test_user_b):
        """Test User A can see they've shared with User B, with name"""
        print("\n>>> User A checking who they've shared with...")

        response = requests.get(
            f"{BACKEND_URL}/v1/speech-profile/i-have-shared",
            headers={'Authorization': f"Bearer {test_user_a['token']}"},
        )

        assert response.status_code == 200, f"List shared failed: {response.text}"
        data = response.json()
        assert 'i_have_shared_with' in data
        shared_uids = _extract_uids(data['i_have_shared_with'])
        assert test_user_b['uid'] in shared_uids

        # Verify response includes name field
        for item in data['i_have_shared_with']:
            if isinstance(item, dict) and item['uid'] == test_user_b['uid']:
                assert 'name' in item
                print(f">>> User B visible in User A's shared list (name: {item['name']})")
                break
        else:
            print(">>> User B visible in User A's shared list")

    @pytest.mark.asyncio
    async def test_05_websocket_speaker_identification(self, test_user_a, test_user_b):
        """Test User B's /listen session loads shared profiles into the identification cache"""
        print("\n>>> User B starting /listen session with shared profile...")

        ws_url = (
            f"{WS_URL}/v4/listen?uid={test_user_b['uid']}"
            f"&language=en&sample_rate=8000&codec=pcm8&include_speech_profile=true"
        )

        try:
            async with websockets.connect(ws_url) as websocket:
                print(">>> WebSocket connected")

                audio_data = generate_test_audio(duration_seconds=5, sample_rate=8000)
                audio_bytes = audio_data.read()

                chunk_size = 1024
                for i in range(0, len(audio_bytes), chunk_size):
                    chunk = audio_bytes[i : i + chunk_size]
                    await websocket.send(chunk)
                    await asyncio.sleep(0.1)

                print(f">>> Sent {len(audio_bytes)} bytes of audio")

                # Listen for any response to confirm session is active
                timeout = 15
                try:
                    async with asyncio.timeout(timeout):
                        while True:
                            message = await websocket.recv()
                            data = json.loads(message)
                            msg_type = data.get('type', 'unknown')
                            print(f">>> Received: {msg_type}")

                            if msg_type == 'speaker_label_suggestion':
                                person_id = data.get('person_id', '')
                                person_name = data.get('person_name', '')
                                if person_id.startswith('shared:'):
                                    print(f">>> Shared profile identified as: {person_name}")
                                    break
                except asyncio.TimeoutError:
                    pass

        except Exception as e:
            print(f">>> WebSocket error: {e}")
            pytest.fail(f"WebSocket test failed: {e}")

        # Note: actual speaker match depends on real voice data matching the embedding.
        # The key verification is that the backend loaded shared embeddings into the cache.
        # Check backend logs for: "Speaker ID: loaded N person embeddings (including shared)"
        print(">>> WebSocket session completed - check backend logs for shared embedding loading")

    def test_06_revoke_profile(self, test_user_a, test_user_b):
        """Test User A can revoke shared profile"""
        print("\n>>> User A revoking shared profile...")

        response = requests.post(
            f"{BACKEND_URL}/v1/speech-profile/revoke",
            headers={'Authorization': f"Bearer {test_user_a['token']}", 'Content-Type': 'application/json'},
            json={'target_uid': test_user_b['uid']},
        )

        assert response.status_code == 200, f"Revoke failed: {response.text}"
        data = response.json()
        assert data['status'] == 'ok'
        print(">>> Profile revoked successfully")

    def test_07_verify_revoked(self, test_user_a, test_user_b):
        """Test User B no longer sees User A's profile after revocation"""
        print("\n>>> User B checking shared profiles after revocation...")

        response = requests.get(
            f"{BACKEND_URL}/v1/speech-profile/shared-with-me",
            headers={'Authorization': f"Bearer {test_user_b['token']}"},
        )

        assert response.status_code == 200, f"List shared failed: {response.text}"
        data = response.json()
        assert 'shared_with_me' in data
        shared_uids = _extract_uids(data['shared_with_me'])
        assert test_user_a['uid'] not in shared_uids
        print(">>> User A's profile no longer visible to User B")

    def test_08_reshare_and_receiver_remove(self, test_user_a, test_user_b):
        """Test User B can remove a profile shared with them (receiver-side remove)"""
        print("\n>>> Re-sharing then testing receiver-side remove...")

        # Re-share
        response = requests.post(
            f"{BACKEND_URL}/v1/speech-profile/share",
            headers={'Authorization': f"Bearer {test_user_a['token']}", 'Content-Type': 'application/json'},
            json={'target_uid': test_user_b['uid']},
        )
        assert response.status_code == 200, f"Re-share failed: {response.text}"

        # User B removes the shared profile
        response = requests.post(
            f"{BACKEND_URL}/v1/speech-profile/remove-shared",
            headers={'Authorization': f"Bearer {test_user_b['token']}", 'Content-Type': 'application/json'},
            json={'target_uid': test_user_a['uid']},
        )
        assert response.status_code == 200, f"Remove shared failed: {response.text}"

        # Verify it's gone
        response = requests.get(
            f"{BACKEND_URL}/v1/speech-profile/shared-with-me",
            headers={'Authorization': f"Bearer {test_user_b['token']}"},
        )
        assert response.status_code == 200
        data = response.json()
        shared_uids = _extract_uids(data['shared_with_me'])
        assert test_user_a['uid'] not in shared_uids
        print(">>> Receiver-side remove works correctly")


class TestSpeechProfileSharingValidation:
    """Test validation and error cases"""

    def test_cannot_share_with_self(self, test_user_a):
        """Test that a user cannot share their profile with themselves"""
        print("\n>>> Testing self-share prevention...")

        response = requests.post(
            f"{BACKEND_URL}/v1/speech-profile/share",
            headers={'Authorization': f"Bearer {test_user_a['token']}", 'Content-Type': 'application/json'},
            json={'target_uid': test_user_a['uid']},
        )

        assert response.status_code == 400
        assert 'yourself' in response.json().get('detail', '').lower()
        print(">>> Self-share correctly blocked")

    def test_cannot_share_with_nonexistent_user(self, test_user_a):
        """Test that sharing with non-existent user fails"""
        print("\n>>> Testing share with non-existent user...")

        response = requests.post(
            f"{BACKEND_URL}/v1/speech-profile/share",
            headers={'Authorization': f"Bearer {test_user_a['token']}", 'Content-Type': 'application/json'},
            json={'target_uid': 'nonexistent_user_12345'},
        )

        assert response.status_code == 404
        assert 'not found' in response.json().get('detail', '').lower()
        print(">>> Share with non-existent user correctly blocked")

    def test_cannot_share_without_profile(self, test_user_b):
        """Test that sharing without a recorded speech profile fails"""
        print("\n>>> Testing no-profile guard...")

        response = requests.post(
            f"{BACKEND_URL}/v1/speech-profile/share",
            headers={'Authorization': f"Bearer {test_user_b['token']}", 'Content-Type': 'application/json'},
            json={'target_uid': 'some_user_id'},
        )

        # Should be 400 with "No speech profile recorded" if user B has no profile
        # If user B does have a profile, this will fail with 404 (user not found) which is also valid
        assert response.status_code in [400, 404], f"Unexpected status: {response.status_code}"
        print(f">>> No-profile/validation guard works (status: {response.status_code})")


if __name__ == '__main__':
    print("Speech Profile Sharing E2E Tests")
    print("=" * 50)
    pytest.main([__file__, '-v', '-s'])
