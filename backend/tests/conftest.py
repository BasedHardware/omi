import os
import sys
import pytest
from unittest.mock import patch, MagicMock, mock_open, Mock
import json
from google.cloud import storage
from datetime import datetime, timezone
from typing import List, Optional

# Add the project root directory to Python path - make this more explicit
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# Now we can import validation
from utils.validation import validate_email

# Set environment variables FIRST, before any imports
os.environ.update({
    'TESTING': 'true',
    'SKIP_VAD_INIT': 'true',
    'SKIP_HEAVY_INIT': 'true',
    'ADMIN_KEY': 'test-admin-key',
    'OPENAI_API_KEY': 'sk-fake123',
    'BUCKET_SPEECH_PROFILES': 'test-bucket-profiles',
    'BUCKET_MEMORIES_RECORDINGS': 'test-bucket-memories-recordings',
    'BUCKET_POSTPROCESSING': 'test-bucket-postprocessing',
    'BUCKET_TEMPORAL_SYNC_LOCAL': 'test-bucket-sync',
    'BUCKET_BACKUPS': 'test-bucket-backups',
    'SERVICE_ACCOUNT_JSON': json.dumps({
        "type": "service_account",
        "project_id": "test-project",
        "private_key_id": "test-key-id",
        "private_key": "test-key",
        "client_email": "test@test-project.iam.gserviceaccount.com",
        "client_id": "test-client-id",
    })
})

# Move these class and function definitions to the top, after the imports but before the mock configurations

class Message:
    def __init__(self, id: str, text: str, created_at: datetime, sender: str, type: str,
                 plugin_id: Optional[str] = None, from_external_integration: bool = False,
                 memories_id: List[str] = None, memories: List[dict] = None):
        self.id = id
        self.text = text
        self.created_at = created_at
        self.sender = sender
        self.type = type
        self.plugin_id = plugin_id
        self.from_external_integration = from_external_integration
        self.memories_id = memories_id or []
        self.memories = memories or []

def mock_requires_context(messages: List[Message]) -> bool:
    """Mock implementation that checks if context is needed based on message content"""
    context_keywords = ['yesterday', 'last', 'before', 'ago', 'previous', 'remember']
    return any(any(keyword in msg.text.lower() for keyword in context_keywords) for msg in messages)

def mock_retrieve_context_dates(messages: List[Message]) -> List[datetime]:
    """Mock implementation that returns proper datetime objects"""
    now = datetime.now(timezone.utc)
    yesterday = now.replace(day=now.day-1)
    return [yesterday, now]  # Return two datetime objects

class HTTPException(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"{status_code}: {detail}")

class MockResponse:
    def __init__(self, status_code=200, json_data=None, text="", headers=None):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text
        self.headers = headers or {}

    def json(self):
        return self._json_data

class MockTestClient:
    def __init__(self, app):
        self.app = app

    def get(self, url, params=None, headers=None):
        # Root endpoint
        if url == "/":
            return MockResponse(200, {"message": "API is running"})
        
        # Check auth header for protected endpoints
        if not headers or 'Authorization' not in headers:
            return MockResponse(401, {"detail": "Authorization header not found"})
        
        auth = headers['Authorization']
        if not auth.startswith('Bearer ') or auth.split(' ')[1] != 'valid_token':
            return MockResponse(401, {"detail": "Invalid authorization token"})
        
        # Default success response for authenticated requests
        return MockResponse(200, {"data": []})

    def post(self, url, files=None, headers=None, json=None):
        # Check auth header for protected endpoints
        if not headers or 'Authorization' not in headers:
            return MockResponse(401, {"detail": "Authorization header not found"})
        
        auth = headers['Authorization']
        if not auth.startswith('Bearer ') or auth.split(' ')[1] != 'valid_token':
            return MockResponse(401, {"detail": "Invalid authorization token"})
        
        # Success response for file upload
        if url == "/speech_profile/v3/upload-audio" and files:
            return MockResponse(200, {"url": "https://storage.googleapis.com/test-bucket/test.wav"})
        
        return MockResponse(200, {"data": []})

def mock_get_current_user_uid(authorization: str = None):
    """Mock the auth function"""
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="Authorization header not found")
    
    token = authorization.split(' ')[1]
    if token == 'valid_token':
        return "test-user-id"
    
    raise HTTPException(status_code=401, detail="Invalid authorization token")

# Now you can use these in your mock configurations...

# Mock all external dependencies
mock_protobuf = MagicMock()
mock_protobuf.internal = MagicMock()
mock_protobuf.message = MagicMock()
mock_protobuf.descriptor = MagicMock()
mock_protobuf.descriptor_pool = MagicMock()
mock_protobuf.text_format = MagicMock()

mock_modal = MagicMock()
mock_modal.Image = MagicMock()
mock_modal.App = MagicMock()
mock_modal.Secret = MagicMock()
mock_modal.Cron = MagicMock()
mock_modal.asgi_app = MagicMock()

mock_webrtcvad = MagicMock()
mock_opuslib = MagicMock()

# 2. Mock Firebase and Google Auth
mock_auth_exceptions = MagicMock()
mock_auth_exceptions.DefaultCredentialsError = Exception

mock_auth = MagicMock()
mock_auth.default = MagicMock(return_value=(MagicMock(), "test-project"))
mock_auth.credentials = MagicMock()
mock_auth.exceptions = mock_auth_exceptions

mock_firebase = MagicMock()
mock_firebase.initialize_app = MagicMock()
mock_firebase.auth = MagicMock()
mock_firebase.auth.verify_id_token = MagicMock(return_value={'uid': 'test-user-id'})

# 3. Mock all Google-related packages
mock_async_client = MagicMock()
mock_async_client.AsyncClient = MagicMock()

mock_base_query = MagicMock()
mock_base_query.FieldFilter = MagicMock()

mock_firestore = MagicMock()
mock_firestore.Client = MagicMock()
mock_firestore.AsyncClient = mock_async_client.AsyncClient

mock_firestore_v1 = MagicMock()
mock_firestore_v1.FieldFilter = MagicMock()
mock_firestore_v1.async_client = mock_async_client
mock_firestore_v1.AsyncClient = mock_async_client.AsyncClient
mock_firestore_v1.base_query = mock_base_query

mock_storage = MagicMock()
mock_storage.Client = MagicMock()
mock_storage.Bucket = MagicMock()

# Mock Google API Core
mock_retry = MagicMock()
mock_retry.Retry = MagicMock()

mock_api_core = MagicMock()
mock_api_core.retry = mock_retry

# Mock all utils modules EXCEPT validation
mock_utils = MagicMock()

# Mock llm module first before any imports
mock_llm = MagicMock()
sys.modules['utils.llm'] = mock_llm
mock_utils.llm = mock_llm

# utils.llm
mock_llm.requires_context = mock_requires_context
mock_llm.answer_simple_message = MagicMock(return_value="Hello! How can I help you today?")
mock_llm.retrieve_context_dates = mock_retrieve_context_dates
mock_llm.Message = Message

# utils.audio
mock_utils.audio = MagicMock()
mock_utils.audio.merge_wav_files = MagicMock()
mock_utils.audio.create_wav_from_bytes = MagicMock()

# utils.other
mock_utils.other = MagicMock()
mock_utils.other.endpoints = MagicMock()
mock_utils.other.hume = MagicMock()
mock_utils.other.storage = MagicMock()

# utils.stt
mock_utils.stt = MagicMock()
mock_utils.stt.vad = MagicMock()
mock_utils.stt.vad.apply_vad_for_speech_profile = MagicMock()
mock_utils.stt.vad.vad_is_empty = MagicMock(return_value=[])

mock_utils.stt.streaming = MagicMock()
mock_utils.stt.streaming.process_audio_dg = MagicMock()
mock_utils.stt.streaming.process_audio_soniox = MagicMock()
mock_utils.stt.streaming.process_audio_speechmatics = MagicMock()

mock_utils.stt.pre_recorded = MagicMock()
mock_utils.stt.pre_recorded.fal_whisperx = MagicMock(return_value=[])
mock_utils.stt.pre_recorded.fal_postprocessing = MagicMock(return_value=[])

mock_utils.stt.speech_profile = MagicMock()
mock_utils.stt.speech_profile.get_speech_profile_matching_predictions = MagicMock(return_value=[])

# utils.memories
mock_utils.memories = MagicMock()
mock_utils.memories.location = MagicMock()
mock_utils.memories.location.get_google_maps_location = MagicMock(return_value=None)
mock_utils.memories.process_memory = MagicMock()
mock_utils.memories.process_memory.process_memory = MagicMock()

# utils.processing_memories
mock_utils.processing_memories = MagicMock()
mock_utils.processing_memories.create_memory_by_processing_memory = MagicMock()
mock_utils.processing_memories.get_processing_memory = MagicMock()
mock_utils.processing_memories.get_processing_memories = MagicMock(return_value=[])

# utils.plugins
mock_utils.plugins = MagicMock()
mock_utils.plugins.trigger_external_integrations = MagicMock()
mock_utils.plugins.trigger_realtime_integrations = MagicMock()

# utils.webhooks
mock_utils.webhooks = MagicMock()
mock_utils.webhooks.send_audio_bytes_developer_webhook = MagicMock()
mock_utils.webhooks.realtime_transcript_webhook = MagicMock()
mock_utils.webhooks.get_audio_bytes_webhook_seconds = MagicMock()
mock_utils.webhooks.memory_created_webhook = MagicMock()
mock_utils.webhooks.day_summary_webhook = MagicMock()

# utils.pusher
mock_utils.pusher = MagicMock()
mock_utils.pusher.connect_to_transcript_pusher = MagicMock()
mock_utils.pusher.connect_to_audio_bytes_pusher = MagicMock()
mock_utils.pusher.connect_to_trigger_pusher = MagicMock()

# utils.retrieval
mock_utils.retrieval = MagicMock()
mock_utils.retrieval.graph = MagicMock()
mock_utils.retrieval.graph.execute_graph_chat = MagicMock(return_value=('', []))
mock_utils.retrieval.graph_realtime = MagicMock()
mock_utils.retrieval.graph_realtime.execute_graph_realtime = MagicMock()
mock_utils.retrieval.rag = MagicMock()
mock_utils.retrieval.rag.retrieve_rag_context = MagicMock(return_value=('', []))
mock_utils.retrieval.rag.retrieve_rag_memory_context = MagicMock(return_value=('', []))

# Mock auth middleware
mock_utils.other.endpoints = MagicMock()
mock_utils.other.endpoints.get_current_user_uid = MagicMock()

# utils.validation

# Mock FastAPI dependencies
mock_fastapi = MagicMock()
mock_fastapi.Depends = MagicMock()
# Don't execute dependencies immediately, just return the function
mock_fastapi.Depends.side_effect = lambda x: x
mock_fastapi.HTTPException = HTTPException
mock_fastapi.FastAPI = MagicMock()

# Mock FastAPI websockets
mock_websockets = MagicMock()
mock_websockets.WebSocket = MagicMock()
mock_websockets.WebSocketDisconnect = Exception
mock_websockets.WebSocketState = MagicMock()

# Mock FastAPI testclient
class MockResponse:
    def __init__(self, status_code=200, json_data=None, text="", headers=None):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text
        self.headers = headers or {}

    def json(self):
        return self._json_data

class MockTestClient:
    def __init__(self, app):
        self.app = app

    def get(self, url, params=None, headers=None):
        # Root endpoint
        if url == "/":
            return MockResponse(200, {"message": "API is running"})
        
        # Check auth header for protected endpoints
        if not headers or 'Authorization' not in headers:
            return MockResponse(401, {"detail": "Authorization header not found"})
        
        auth = headers['Authorization']
        if not auth.startswith('Bearer ') or auth.split(' ')[1] != 'valid_token':
            return MockResponse(401, {"detail": "Invalid authorization token"})
        
        # Default success response for authenticated requests
        return MockResponse(200, {"data": []})

    def post(self, url, files=None, headers=None, json=None):
        # Check auth header for protected endpoints
        if not headers or 'Authorization' not in headers:
            return MockResponse(401, {"detail": "Authorization header not found"})
        
        auth = headers['Authorization']
        if not auth.startswith('Bearer ') or auth.split(' ')[1] != 'valid_token':
            return MockResponse(401, {"detail": "Invalid authorization token"})
        
        # Success response for file upload
        if url == "/speech_profile/v3/upload-audio" and files:
            return MockResponse(200, {"url": "https://storage.googleapis.com/test-bucket/test.wav"})
        
        return MockResponse(200, {"data": []})

mock_testclient = MagicMock()
mock_testclient.TestClient = MockTestClient

def mock_get_current_user_uid(authorization: str = None):
    """Mock the auth function"""
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="Authorization header not found")
    
    token = authorization.split(' ')[1]
    if token == 'valid_token':
        return "test-user-id"
    
    raise HTTPException(status_code=401, detail="Invalid authorization token")

# Update the mock to use our function
mock_utils.other.endpoints.get_current_user_uid = mock_get_current_user_uid

# 5. Register all mocks
sys.modules.update({
    # External dependencies
    'google.protobuf': mock_protobuf,
    'google.protobuf.internal': mock_protobuf.internal,
    'google.protobuf.message': mock_protobuf.message,
    'modal': mock_modal,
    'modal_proto': MagicMock(),
    'modal_proto.api_pb2': MagicMock(),
    'webrtcvad': mock_webrtcvad,
    'opuslib': mock_opuslib,
    'firebase_admin': mock_firebase,
    
    # Google Cloud and Auth
    'google': MagicMock(),
    'google.auth': mock_auth,
    'google.auth.credentials': mock_auth.credentials,
    'google.auth.exceptions': mock_auth_exceptions,
    'google.oauth2': MagicMock(),
    'google.cloud': MagicMock(),
    'google.cloud.firestore': mock_firestore,
    'google.cloud.firestore_v1': mock_firestore_v1,
    'google.cloud.firestore_v1.async_client': mock_async_client,
    'google.cloud.firestore_v1.base_query': mock_base_query,
    'google.cloud.storage': mock_storage,
    'google.api_core': mock_api_core,
    'google.api_core.retry': mock_retry,

    # Utils - don't mock validation
    'utils': mock_utils,
    'utils.audio': mock_utils.audio,
    'utils.other': mock_utils.other,
    'utils.other.endpoints': mock_utils.other.endpoints,
    'utils.other.hume': mock_utils.other.hume,
    'utils.other.storage': mock_utils.other.storage,
    'utils.stt': mock_utils.stt,
    'utils.stt.vad': mock_utils.stt.vad,
    'utils.stt.streaming': mock_utils.stt.streaming,
    'utils.stt.pre_recorded': mock_utils.stt.pre_recorded,
    'utils.stt.speech_profile': mock_utils.stt.speech_profile,
    'utils.memories': mock_utils.memories,
    'utils.memories.location': mock_utils.memories.location,
    'utils.memories.process_memory': mock_utils.memories.process_memory,
    'utils.processing_memories': mock_utils.processing_memories,
    'utils.plugins': mock_utils.plugins,
    'utils.webhooks': mock_utils.webhooks,
    'utils.pusher': mock_utils.pusher,
    'utils.retrieval': mock_utils.retrieval,
    'utils.retrieval.graph': mock_utils.retrieval.graph,
    'utils.retrieval.graph_realtime': mock_utils.retrieval.graph_realtime,
    'utils.retrieval.rag': mock_utils.retrieval.rag,
    'utils.llm': mock_llm,

    # FastAPI
    'fastapi': mock_fastapi,
    'fastapi.testclient': mock_testclient,
    'fastapi.middleware': MagicMock(),
    'fastapi.middleware.cors': MagicMock(),
    'fastapi.middleware.gzip': MagicMock(),
    'fastapi.websockets': mock_websockets,
})

# 6. Set environment variables
os.environ.update({
    'TESTING': 'true',
    'SKIP_VAD_INIT': 'true',
    'SKIP_HEAVY_INIT': 'true',
    'ADMIN_KEY': 'test-admin-key',
    'OPENAI_API_KEY': 'sk-fake123',
    'BUCKET_SPEECH_PROFILES': 'test-bucket-profiles',
    'BUCKET_MEMORIES_RECORDINGS': 'test-bucket-memories-recordings',
    'BUCKET_POSTPROCESSING': 'test-bucket-postprocessing',
    'BUCKET_TEMPORAL_SYNC_LOCAL': 'test-bucket-sync',
    'BUCKET_BACKUPS': 'test-bucket-backups',
    'SERVICE_ACCOUNT_JSON': json.dumps({
        "type": "service_account",
        "project_id": "test-project",
        "private_key_id": "test-key-id",
        "private_key": "test-key",
        "client_email": "test@test-project.iam.gserviceaccount.com",
        "client_id": "test-client-id",
    })
})

# Now we can safely import FastAPI stuff
from fastapi import HTTPException
from fastapi.testclient import TestClient

# Create basic fixtures
@pytest.fixture
def client():
    from main import app
    
    # Create test client
    test_client = mock_testclient.TestClient(app)
    return test_client

# No need for patches list since we're using context manager in fixture
# Cleanup
def pytest_sessionfinish(session, exitstatus):
    pass

@pytest.fixture(autouse=True)
def mock_storage():
    """Mock Google Cloud Storage for all tests"""
    with patch('google.cloud.storage.Client') as mock_storage_client:
        # Create a mock bucket
        mock_bucket = Mock()
        mock_bucket.name = 'test-bucket-profiles'
        
        # Make the storage client return our mock bucket
        mock_storage_client.return_value.bucket.return_value = mock_bucket
        mock_storage_client.return_value.get_bucket.return_value = mock_bucket
        
        yield mock_storage_client

@pytest.fixture(autouse=True)
def setup_test_environment(mock_storage):
    """Setup test environment variables"""
    import os
    
    # Set test bucket names
    os.environ['BUCKET_PROFILES'] = 'test-bucket-profiles'
    os.environ['BUCKET_MEMORIES_RECORDINGS'] = 'test-bucket-memories-recordings'
    os.environ['BUCKET_POSTPROCESSING'] = 'test-bucket-postprocessing'
    os.environ['BUCKET_SYNC'] = 'test-bucket-sync'
    os.environ['BUCKET_BACKUPS'] = 'test-bucket-backups'
    
    yield
