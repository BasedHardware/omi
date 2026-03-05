"""Tests for POST /v1/conversations/from-segments endpoint models and validation."""
import sys
from unittest.mock import MagicMock
from datetime import datetime, timezone, timedelta

import pytest

# Stub ALL heavy dependencies before any import that could transitively pull them in.
# Order matters: stub parent packages before child packages.
for mod_name in [
    'firebase_admin', 'firebase_admin.auth', 'firebase_admin.firestore', 'firebase_admin.messaging',
    'google.cloud', 'google.cloud.exceptions', 'google.cloud.firestore', 'google.cloud.firestore_v1',
    'google.cloud.firestore_v1.base_query', 'google.cloud.firestore_v1.query',
    'google.cloud.storage', 'google.cloud.storage.blob', 'google.cloud.storage.bucket',
    'google.auth', 'google.auth.transport', 'google.auth.transport.requests',
    'google.oauth2', 'google.oauth2.service_account',
    'pinecone',
    'typesense',
]:
    sys.modules.setdefault(mod_name, MagicMock())

from routers.conversations import (
    FromSegmentsTranscriptSegment,
    CreateConversationFromSegmentsRequest,
    FromSegmentsResponse,
)


@pytest.fixture
def valid_segments():
    return [
        FromSegmentsTranscriptSegment(text="Hello there", speaker="SPEAKER_00", is_user=True, start=0.0, end=2.5),
        FromSegmentsTranscriptSegment(text="Hi, how are you?", speaker="SPEAKER_01", is_user=False, start=2.8, end=5.2),
    ]


class TestFromSegmentsModels:
    def test_segment_defaults(self):
        seg = FromSegmentsTranscriptSegment(text="Hello", start=0.0, end=1.0)
        assert seg.speaker == "SPEAKER_00"
        assert seg.is_user is False
        assert seg.person_id is None
        assert seg.speaker_id is None

    def test_request_defaults(self, valid_segments):
        req = CreateConversationFromSegmentsRequest(transcript_segments=valid_segments)
        assert req.source == "desktop"
        assert req.language == "en"
        assert req.started_at is None
        assert req.finished_at is None
        assert req.timezone is None
        assert req.input_device_name is None

    def test_response_model(self):
        resp = FromSegmentsResponse(id="conv123", status="completed", discarded=False)
        assert resp.id == "conv123"
        assert resp.status == "completed"
        assert resp.discarded is False


class TestFromSegmentsValidation:
    def test_segment_with_all_fields(self):
        seg = FromSegmentsTranscriptSegment(
            text="Hello",
            speaker="SPEAKER_01",
            speaker_id=1,
            is_user=True,
            person_id="person123",
            start=10.5,
            end=15.3,
        )
        assert seg.speaker_id == 1
        assert seg.person_id == "person123"

    def test_desktop_source_default(self, valid_segments):
        req = CreateConversationFromSegmentsRequest(transcript_segments=valid_segments)
        assert req.source == "desktop"

    def test_custom_source(self, valid_segments):
        req = CreateConversationFromSegmentsRequest(transcript_segments=valid_segments, source="phone")
        assert req.source == "phone"

    def test_timezone_and_input_device_accepted(self, valid_segments):
        req = CreateConversationFromSegmentsRequest(
            transcript_segments=valid_segments,
            timezone="America/New_York",
            input_device_name="MacBook Pro Microphone",
        )
        assert req.timezone == "America/New_York"
        assert req.input_device_name == "MacBook Pro Microphone"

    def test_started_finished_at(self, valid_segments):
        now = datetime.now(timezone.utc)
        later = now + timedelta(minutes=5)
        req = CreateConversationFromSegmentsRequest(
            transcript_segments=valid_segments,
            started_at=now,
            finished_at=later,
        )
        assert req.started_at == now
        assert req.finished_at == later

    def test_500_segments_accepted(self):
        segs = [FromSegmentsTranscriptSegment(text=f"seg {i}", start=float(i), end=float(i + 1)) for i in range(500)]
        req = CreateConversationFromSegmentsRequest(transcript_segments=segs)
        assert len(req.transcript_segments) == 500

    def test_geolocation_accepted(self, valid_segments):
        req = CreateConversationFromSegmentsRequest(
            transcript_segments=valid_segments,
            geolocation={'latitude': 37.7749, 'longitude': -122.4194},
        )
        assert req.geolocation is not None


class TestFromSegmentsEndpoint:
    """Endpoint-level tests using FastAPI TestClient with mocked auth and processing."""

    def _make_app(self):
        from fastapi import FastAPI
        from routers.conversations import router
        app = FastAPI()
        app.include_router(router)
        return app

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        return TestClient(self._make_app())

    def test_successful_creation(self, client):
        with (
            patch('routers.conversations.auth.get_current_user_uid', return_value='test-uid-123'),
            patch('routers.conversations.process_conversation') as mock_process,
            patch('routers.conversations.get_google_maps_location'),
        ):
            mock_conv = MagicMock()
            mock_conv.id = 'conv-abc'
            mock_conv.status.value = 'completed'
            mock_conv.discarded = False
            mock_process.return_value = mock_conv

            response = client.post(
                '/v1/conversations/from-segments',
                json={
                    'transcript_segments': [
                        {'text': 'Hello there', 'speaker': 'SPEAKER_00', 'is_user': True, 'start': 0.0, 'end': 2.5},
                        {'text': 'Hi!', 'speaker': 'SPEAKER_01', 'is_user': False, 'start': 2.8, 'end': 5.2},
                    ],
                    'source': 'desktop',
                    'language': 'en',
                },
                headers={'Authorization': 'Bearer test-token'},
            )
            assert response.status_code == 200
            data = response.json()
            assert data['id'] == 'conv-abc'
            assert data['status'] == 'completed'
            assert data['discarded'] is False
            mock_process.assert_called_once()

    def test_invalid_segment_times_returns_422(self, client):
        with patch('routers.conversations.auth.get_current_user_uid', return_value='test-uid-123'):
            response = client.post(
                '/v1/conversations/from-segments',
                json={'transcript_segments': [{'text': 'Hello', 'start': 5.0, 'end': 3.0}]},
                headers={'Authorization': 'Bearer test-token'},
            )
            assert response.status_code == 422

    def test_empty_text_returns_422(self, client):
        with patch('routers.conversations.auth.get_current_user_uid', return_value='test-uid-123'):
            response = client.post(
                '/v1/conversations/from-segments',
                json={'transcript_segments': [{'text': '   ', 'start': 0.0, 'end': 1.0}]},
                headers={'Authorization': 'Bearer test-token'},
            )
            assert response.status_code == 422

    def test_negative_start_returns_422(self, client):
        with patch('routers.conversations.auth.get_current_user_uid', return_value='test-uid-123'):
            response = client.post(
                '/v1/conversations/from-segments',
                json={'transcript_segments': [{'text': 'Hello', 'start': -1.0, 'end': 1.0}]},
                headers={'Authorization': 'Bearer test-token'},
            )
            assert response.status_code == 422

    def test_finished_at_auto_calculated(self, client):
        with (
            patch('routers.conversations.auth.get_current_user_uid', return_value='test-uid-123'),
            patch('routers.conversations.process_conversation') as mock_process,
            patch('routers.conversations.get_google_maps_location'),
        ):
            mock_conv = MagicMock()
            mock_conv.id = 'conv-calc'
            mock_conv.status.value = 'completed'
            mock_conv.discarded = False
            mock_process.return_value = mock_conv

            response = client.post(
                '/v1/conversations/from-segments',
                json={'transcript_segments': [{'text': 'Hello', 'start': 0.0, 'end': 30.0}], 'source': 'desktop'},
                headers={'Authorization': 'Bearer test-token'},
            )
            assert response.status_code == 200
            create_obj = mock_process.call_args[0][2]
            assert create_obj.finished_at > create_obj.started_at

    def test_source_defaults_to_desktop(self, client):
        with (
            patch('routers.conversations.auth.get_current_user_uid', return_value='test-uid-123'),
            patch('routers.conversations.process_conversation') as mock_process,
            patch('routers.conversations.get_google_maps_location'),
        ):
            mock_conv = MagicMock()
            mock_conv.id = 'conv-def'
            mock_conv.status.value = 'completed'
            mock_conv.discarded = False
            mock_process.return_value = mock_conv

            response = client.post(
                '/v1/conversations/from-segments',
                json={'transcript_segments': [{'text': 'Hello', 'start': 0.0, 'end': 1.0}]},
                headers={'Authorization': 'Bearer test-token'},
            )
            assert response.status_code == 200
            create_obj = mock_process.call_args[0][2]
            assert create_obj.source.value == 'desktop'


# Keep patch import at module scope for the with-statement usage
from unittest.mock import patch
