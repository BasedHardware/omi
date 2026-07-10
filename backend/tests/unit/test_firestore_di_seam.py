import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
ENCRYPTION_SECRET = "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv"
os.environ.setdefault("ENCRYPTION_SECRET", ENCRYPTION_SECRET)
sys.path.insert(0, str(BACKEND_DIR / "testing" / "e2e"))

import database._client as client_module  # noqa: E402
import database.helpers as helpers  # noqa: E402
import database.memories as memories_db  # noqa: E402
from fakes.firestore import setup_fake_firestore, teardown_fake_firestore  # noqa: E402

pytestmark = pytest.mark.slow


def _subprocess_env() -> dict:
    env = os.environ.copy()
    for key in (
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_CLOUD_PROJECT",
        "GCLOUD_PROJECT",
        "SERVICE_ACCOUNT_JSON",
    ):
        env.pop(key, None)
    env["ENCRYPTION_SECRET"] = ENCRYPTION_SECRET
    env["PYTHONPATH"] = str(BACKEND_DIR)
    return env


@pytest.mark.parametrize("module_name", ["database._client", "database.memories"])
def test_database_modules_import_without_constructing_firestore_client(module_name):
    code = f"""
from google.cloud import firestore

def fail_client(*args, **kwargs):
    raise RuntimeError("firestore.Client constructed during import")

firestore.Client = fail_client
__import__({module_name!r})
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND_DIR,
        env=_subprocess_env(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_service_account_json_is_not_written_at_import(tmp_path):
    env = _subprocess_env()
    env["SERVICE_ACCOUNT_JSON"] = '{"client_email": "unused@example.com"}'
    code = """
from pathlib import Path
from google.cloud import firestore

def fail_client(*args, **kwargs):
    raise RuntimeError("firestore.Client constructed during import")

firestore.Client = fail_client
import database._client
assert not Path("google-credentials.json").exists()
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_get_firestore_client_builds_lazily_and_caches(monkeypatch):
    fake_client = SimpleNamespace(collection=MagicMock(return_value="users-ref"))
    build_client = MagicMock(return_value=fake_client)
    monkeypatch.setattr(client_module, "_firestore_client", None)
    monkeypatch.setattr(client_module, "_build_firestore_client", build_client)

    assert client_module.get_firestore_client() is fake_client
    assert client_module.get_firestore_client() is fake_client
    assert client_module.db.collection("users") == "users-ref"

    build_client.assert_called_once_with()


@pytest.fixture
def fake_firestore():
    store = setup_fake_firestore()
    try:
        yield store
    finally:
        teardown_fake_firestore()


def test_create_memory_uses_injected_firestore_for_data_protection(monkeypatch, fake_firestore):
    uid = "uid-injected-memory"
    fake_firestore.collection("users").document(uid).set({"data_protection_level": "standard"})

    monkeypatch.setattr(helpers.redis_db, "get_user_data_protection_level", MagicMock(return_value="enhanced"))
    monkeypatch.setattr(
        helpers.redis_db,
        "set_user_data_protection_level",
        MagicMock(side_effect=AssertionError("wrote global Redis data protection cache")),
    )
    monkeypatch.setattr(
        memories_db, "get_firestore_client", MagicMock(side_effect=AssertionError("used global client"))
    )
    monkeypatch.setattr(
        helpers.users_db,
        "get_user_profile",
        MagicMock(side_effect=AssertionError("used global user profile lookup")),
    )

    memory = {
        "id": "mem-1",
        "content": "Injected Firestore writes should stay plaintext at standard protection.",
        "created_at": "2026-06-30T00:00:00+00:00",
    }

    returned = memories_db.create_memory(uid, memory, firestore_client=fake_firestore)

    saved = fake_firestore.collection("users").document(uid).collection("memories").document("mem-1").get().to_dict()
    assert returned is memory
    assert memory["data_protection_level"] == "standard"
    assert saved["data_protection_level"] == "standard"
    assert saved["content"] == memory["content"]
