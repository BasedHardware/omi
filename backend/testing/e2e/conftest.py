"""
Pytest configuration and shared fixtures for hermetic e2e tests.

The harness imports the REAL FastAPI backend and uses fake or disabled
external-service boundaries for the v1 scenarios. Tests fail on non-local
network attempts so accidental real service calls are surfaced.
"""

import json
import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

# ─── CRITICAL: Patch Google auth BEFORE any Firestore import ──────────
# database/_client.py calls firestore.Client() at MODULE level (line 14).
# If google.auth.default tries real credentials → DefaultCredentialsError.
# We intercept it here so the client constructor never hits the network.
import google.auth.credentials
import google.auth as _ga_mod

_original_ga_default = getattr(_ga_mod, 'default', None)


def _fake_google_auth_default(scopes=None, request=None, **kwargs):
    """Return anonymous credentials so Google clients can construct without ADC lookup."""
    return google.auth.credentials.AnonymousCredentials(), "test-e2e-project"


if _original_ga_default is not None:
    _ga_mod.default = _fake_google_auth_default

import dotenv
import pytest

# ─── Paths ──────────────────────────────────────────────────────────────

E2E_DIR = Path(__file__).parent
BACKEND_DIR = E2E_DIR.parent.parent
PROJECT_ROOT = BACKEND_DIR.parent

# Insert backend dir first so `from database import ...` resolves
backend_str = str(BACKEND_DIR)
if backend_str not in sys.path:
    sys.path.insert(0, backend_str)

# Also insert e2e dir for fakes package
e2e_str = str(E2E_DIR)
if e2e_str not in sys.path:
    sys.path.insert(0, e2e_str)


# ─── Environment variables (set BEFORE any omi imports) ────────────────


def _set_e2e_env():
    """Configure environment so the backend runs in hermetic test mode.

    Deliberately overwrite external-service credentials instead of using
    setdefault() so a developer's shell cannot leak real API keys into e2e runs.
    """
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    os.environ["LOCAL_DEVELOPMENT"] = "true"
    os.environ["ENCRYPTION_SECRET"] = "test-encryption-secret-for-e2e-testing-32chars!"
    os.environ["FIREBASE_PROJECT_ID"] = "test-e2e-project"
    os.environ["GOOGLE_CLOUD_PROJECT"] = "test-e2e-project"
    os.environ.pop("SERVICE_ACCOUNT_JSON", None)
    os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
    os.environ["REDIS_DB_HOST"] = "localhost"
    os.environ["REDIS_DB_PORT"] = "6379"
    os.environ["REDIS_DB_PASSWORD"] = ""
    os.environ["DEEPGRAM_API_KEY"] = "fake-deepgram-key"
    os.environ["OPENAI_API_KEY"] = "fake-openai-key"
    os.environ["ANTHROPIC_API_KEY"] = "fake-anthropic-key"
    os.environ["OPENROUTER_API_KEY"] = "fake-openrouter-key"
    os.environ["GOOGLE_API_KEY"] = "fake-google-key"
    # database/vector_db.py intentionally skips Pinecone only when this env var is absent.
    # An empty string still triggers Pinecone(api_key='') and fails at import time.
    os.environ.pop("PINECONE_API_KEY", None)
    os.environ["TYPESENSE_HOST"] = "localhost"
    os.environ["TYPESENSE_HOST_PORT"] = "8108"
    os.environ["TYPESENSE_API_KEY"] = "fake-typesense-key"
    os.environ["BUCKET_SPEECH_PROFILES"] = "speech-profiles"
    os.environ["BUCKET_POSTPROCESSING"] = "postprocessing"
    os.environ["BUCKET_PRIVATE_CLOUD_SYNC"] = "omi-private-cloud-sync"
    os.environ["BUCKET_TEMPORAL_SYNC_LOCAL"] = "sync-temporal"
    os.environ["BUCKET_MEMORIES_RECORDINGS"] = "memories-recordings"
    os.environ["BUCKET_APP_THUMBNAILS"] = "app-thumbnails"
    os.environ["BUCKET_CHAT_FILES"] = "chat-files"
    os.environ["BUCKET_DESKTOP_UPDATES"] = "desktop-updates"
    # Disable Stripe validation so startup doesn't fail.
    os.environ["STRIPE_SECRET_KEY"] = ""
    os.environ["ADMIN_KEY"] = ""
    for proxy_var in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
    ):
        os.environ.pop(proxy_var, None)


def _disabled_load_dotenv(*args, **kwargs):
    """Prevent backend/main.py from rehydrating real local secrets from .env."""
    return False


_set_e2e_env()
dotenv.load_dotenv = _disabled_load_dotenv


# ─── Network guard ──────────────────────────────────────────────────────

_ALLOWED_NETWORK_HOSTS = {"127.0.0.1", "::1", "localhost", "0.0.0.0"}
_original_socket_connect = socket.socket.connect
_original_socket_connect_ex = socket.socket.connect_ex
_original_socket_sendto = socket.socket.sendto
_original_create_connection = socket.create_connection
_original_getaddrinfo = socket.getaddrinfo


def _host_from_address(address):
    if isinstance(address, tuple) and address:
        return address[0]
    return None


def _assert_local_address(address):
    host = _host_from_address(address)
    if host is None or host in _ALLOWED_NETWORK_HOSTS:
        return
    raise AssertionError(f"Hermetic e2e blocked outbound network connection to {host!r}")


def _guarded_socket_connect(self, address):
    _assert_local_address(address)
    return _original_socket_connect(self, address)


def _guarded_socket_connect_ex(self, address):
    _assert_local_address(address)
    return _original_socket_connect_ex(self, address)


def _guarded_socket_sendto(self, data, *args):
    if len(args) == 1:
        address = args[0]
    elif len(args) == 2:
        address = args[1]
    else:
        raise TypeError("sendto expected address or flags,address")
    _assert_local_address(address)
    return _original_socket_sendto(self, data, *args)


def _guarded_create_connection(address, timeout=None, source_address=None, *args, **kwargs):
    _assert_local_address(address)
    return _original_create_connection(address, timeout=timeout, source_address=source_address, *args, **kwargs)


def _guarded_getaddrinfo(host, port, *args, **kwargs):
    if host is not None and host not in _ALLOWED_NETWORK_HOSTS:
        raise AssertionError(f"Hermetic e2e blocked DNS lookup for {host!r}")
    return _original_getaddrinfo(host, port, *args, **kwargs)


socket.socket.connect = _guarded_socket_connect
socket.socket.connect_ex = _guarded_socket_connect_ex
socket.socket.sendto = _guarded_socket_sendto
socket.create_connection = _guarded_create_connection
socket.getaddrinfo = _guarded_getaddrinfo


# ─── Fake service initialization ───────────────────────────────────────


@pytest.fixture(scope="session")
def fake_firestore():
    """Session-scoped MockFirestore — initialized once, shared across all tests."""
    from fakes.firestore import setup_fake_firestore, teardown_fake_firestore

    store = setup_fake_firestore()
    yield store
    teardown_fake_firestore()


@pytest.fixture(scope="session")
def fake_redis():
    """Session-scoped FakeRedis — initialized once."""
    from fakes.redis import setup_fake_redis, teardown_fake_redis

    r = setup_fake_redis()
    yield r
    teardown_fake_redis()


@pytest.fixture(scope="session")
def fake_storage():
    """Session-scoped temp-dir storage fake."""
    from fakes.storage import setup_fake_storage, teardown_fake_storage

    s = setup_fake_storage()
    yield s
    teardown_fake_storage()


# ─── Backend app factory (cached per-session) ───────────────────────────

_app_cache = None


def _create_backend_app(fake_firestore_instance, fake_redis_instance, fake_storage_instance):
    """
    Create the real FastAPI app with patched dependencies.

    This is called once per session and cached. Returns the raw app object,
    not a TestClient (TestClient is created per-test for isolation).
    """
    global _app_cache
    if _app_cache is not None:
        return _app_cache

    from fakes.firestore import patch_google_firestore
    from fakes.redis import patch_redis_client
    from fakes.storage import patch_google_storage

    # Patch must happen before database/storage modules are imported
    patch_google_firestore()
    patch_redis_client()
    patch_google_storage()

    # Initialize Firebase Admin SDK with fake credentials
    import firebase_admin

    try:
        firebase_admin.get_app()
    except ValueError:
        try:
            firebase_admin.initialize_app(
                firebase_admin.credentials.Certificate(
                    {
                        "type": "service_account",
                        "project_id": "test-e2e-project",
                        "private_key_id": "fake",
                        "private_key": "fake",
                        "client_email": "fake@test-e2e-project.iam.gserviceaccount.com",
                        "client_id": "123",
                    }
                )
            )
        except Exception:
            pass  # May fail in test env; ok for LOCAL_DEVELOPMENT mode

    # Import the real FastAPI app (triggers all backend module imports)
    import main as backend_main

    # Some backend modules bind ``db``/``r`` with ``from database._client import db``
    # or ``from database.redis_db import r`` at import time. If an import raced ahead
    # of the constructor monkeypatches above, relink those already-bound module
    # globals to the hermetic fakes so the e2e harness fails closed instead of
    # reaching Firestore/Redis on localhost or the public internet.
    import database._client as db_client
    import database.redis_db as redis_db

    old_db = db_client.db
    old_r = redis_db.r
    db_client.db = fake_firestore_instance
    redis_db.r = fake_redis_instance
    for module in list(sys.modules.values()):
        if module is None:
            continue
        if getattr(module, "db", None) is old_db:
            setattr(module, "db", fake_firestore_instance)
        if getattr(module, "r", None) is old_r:
            setattr(module, "r", fake_redis_instance)

    _app_cache = backend_main.app
    return _app_cache


# ─── Backend TestClient — function scoped for test isolation ─────────────


@pytest.fixture()
def client(fake_firestore, fake_redis, fake_storage):
    """
    Build a FastAPI TestClient wrapping the REAL omi backend.

    This is the core fixture — it patches Firestore/Redis at the network
    boundary, sets env vars, then imports and wraps the actual app.
    All router logic, auth, encryption, middleware runs for real.
    """
    app = _create_backend_app(fake_firestore, fake_redis, fake_storage)

    from fastapi.testclient import TestClient
    import logging

    logging.disable(logging.CRITICAL)
    tc = TestClient(app)
    yield tc
    logging.disable(logging.NOTSET)


# ─── Auth helpers ───────────────────────────────────────────────────────

DEV_UID = "123"
DEV_AUTH_HEADERS = {"Authori" + "zation": "Bearer dev-token"}


@pytest.fixture(autouse=True)
def isolate_e2e_state(fake_firestore, fake_redis, fake_storage):
    """Clear mutable fake service state before and after each test."""
    from fakes.firestore import clear_user_data
    from fakes.storage import clear_fake_storage

    def clear_state():
        clear_user_data(DEV_UID)
        fake_redis.flushall()
        clear_fake_storage()
        try:
            import utils.http_client as http_client

            http_client._webhook_circuit_breakers.clear()
        except Exception:
            pass
        try:
            import database.webhook_health as webhook_health

            webhook_health.r = fake_redis
            webhook_health._dev_failure_script = None
            webhook_health._record_failure_script = None
            webhook_health._record_success_script = None
        except Exception:
            pass
        try:
            import database.redis_db as redis_db

            redis_db.r = fake_redis
        except Exception:
            pass

    clear_state()
    yield
    clear_state()


@pytest.fixture()
def auth_headers():
    """Return dev-token auth headers for each test."""
    return dict(DEV_AUTH_HEADERS)


# ─── Test data fixtures ────────────────────────────────────────────────


@pytest.fixture()
def test_uid():
    """Return the fixed dev-test UID."""
    return DEV_UID


@pytest.fixture()
def conversation_fixture():
    """Load conversation fixture data from JSON."""
    fixture_path = E2E_DIR / "fixtures" / "conversations.json"
    with open(fixture_path) as f:
        return json.load(f)


@pytest.fixture()
def memory_fixture():
    """Load memory fixture data from JSON."""
    fixture_path = E2E_DIR / "fixtures" / "memories.json"
    with open(fixture_path) as f:
        return json.load(f)


@pytest.fixture()
def action_item_fixture():
    """Load action item fixture data from JSON."""
    fixture_path = E2E_DIR / "fixtures" / "action_items.json"
    with open(fixture_path) as f:
        return json.load(f)


# ─── Utility fixtures ──────────────────────────────────────────────────


@pytest.fixture()
def fresh_uid():
    """Generate a unique UID per test for isolation."""
    import uuid

    return str(uuid.uuid4())


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture()
def sample_conversation_data(fresh_uid):
    """Return dict suitable for creating a conversation via API."""
    return {
        "id": f"conv-{fresh_uid[:8]}",
        "created_at": _now_iso(),
        "started_at": _now_iso(),
        "finished_at": _now_iso(),
        "source": "omi",
        "language": "en",
        "structured": {
            "title": "Test Conversation",
            "overview": "A test conversation created by e2e harness",
            "emoji": "🧠",
            "category": "other",
            "action_items": [],
            "events": [],
        },
        "transcript_segments": [
            {
                "id": "seg-test-1",
                "text": "Hello, this is test transcript segment one.",
                "speaker": "SPEAKER_00",
                "is_user": True,
                "start": 0.0,
                "end": 2.5,
            },
            {
                "id": "seg-test-2",
                "text": "And this is segment two from the other speaker.",
                "speaker": "SPEAKER_01",
                "is_user": False,
                "start": 2.6,
                "end": 5.0,
            },
        ],
        "discarded": False,
        "status": "completed",
        "is_locked": False,
    }


@pytest.fixture()
def sample_memory_data():
    """Return dict suitable for creating a memory via POST /v3/memories."""
    return {
        "content": "Test memory content from e2e harness",
        "category": "interesting",
        "visibility": "public",
        "tags": ["test", "e2e"],
    }


@pytest.fixture()
def sample_action_item_data():
    """Return dict suitable for creating an action item via POST /v1/action-items."""
    return {
        "description": "Complete the e2e harness setup",
        "completed": False,
    }
