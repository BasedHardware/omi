"""Regression tests for apps, persona, and speech-profile lifecycle and lock guards.

Covers:
1. `create_app`, `create_persona`, `update_persona`, and `update_app`:
   - sanitize `file.filename` basename and remove `_temp/apps/<filename>` in `finally:`
   - roll back newly uploaded GCS logos when `AppCreate` validation fails in `create_app` / `create_persona`
   - validate `AppUpdate` and reject negative `price` BEFORE deleting the existing GCS logo or uploading a new logo in `update_app`
2. `update_app` paid-app partial updates:
   - preserve stored `is_paid`, `price`, and `payment_plan` when omitted in partial PATCH payloads passed to `upsert_app_payment_link`
3. `delete_app` and `delete_persona`:
   - delete stored GCS logo (`https://storage.googleapis.com/...`), invalidate popular apps cache when `is_popular` is True, and invalidate per-app / approved-apps caches on `delete_persona`
4. `approve_app` and `reject_app`:
   - return 404 before mutating Firestore or sending notifications when the app does not exist, and invalidate popular apps cache when `is_popular` is True
5. `update_app_review` and `generate_persona_desc`:
   - `update_app_review` falls back gracefully when a legacy review record omits `rated_at`
   - `generate_persona_desc` filters out locked memories (`is_locked=True`) before calling the LLM
6. `speech_profile.upload_profile` and `get_extra_speech_profile_samples`:
   - `upload_profile` sanitizes `file.filename` and removes `_temp/{uid}/{safe_filename}` in `finally:` on both success and error paths
   - `get_extra_speech_profile_samples` normalizes `person_id='null'` to `None`
"""

import asyncio
import importlib.abc
import importlib.machinery
import importlib.util
import json
import os
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")
os.environ.setdefault("PINECONE_API_KEY", "test-pinecone-key-not-real")


def _install_python_multipart_stub():
    if "python_multipart" in sys.modules:
        return False
    if importlib.util.find_spec("python_multipart") is not None:
        return False
    mod = types.ModuleType("python_multipart")
    mod.__version__ = "0.0.20"
    sys.modules["python_multipart"] = mod
    return True


_remove_multipart_stub = _install_python_multipart_stub()

# Scoped stub finder for heavy / native packages during router imports
_STUB = (
    "av",
    "opuslib",
    "scipy",
    "deepgram",
    "pydub",
    "utils.stt.speaker_embedding",
    "utils.stt.streaming",
)


def _is_stubbed(name: str) -> bool:
    return any(name == p or name.startswith(p + ".") for p in _STUB)


class _AutoMock(types.ModuleType):
    __path__ = []

    def __getattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        m = MagicMock()
        setattr(self, name, m)
        return m


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path=None, target=None):
        return importlib.machinery.ModuleSpec(name, self, is_package=True) if _is_stubbed(name) else None

    def create_module(self, spec):
        return _AutoMock(spec.name)

    def exec_module(self, module):
        pass


_f = _Finder()
_saved = {n: m for n, m in sys.modules.items() if _is_stubbed(n)}
_had_sp_router = "routers.speech_profile" in sys.modules
for _n in list(sys.modules):
    if _is_stubbed(_n):
        sys.modules.pop(_n, None)
sys.meta_path.insert(0, _f)
try:
    import routers
    import routers.apps as apps_router
    import utils.apps as apps_utils
    from routers import speech_profile as sp_router
finally:
    sys.meta_path.remove(_f)
    for _n in list(sys.modules):
        if _is_stubbed(_n) and _n not in _saved:
            sys.modules.pop(_n, None)
    sys.modules.update(_saved)
    if not _had_sp_router:
        sys.modules.pop("routers.speech_profile", None)
        sys.modules["routers"].__dict__.pop("speech_profile", None)
    if _remove_multipart_stub:
        sys.modules.pop("python_multipart", None)


class _SyncUpload:
    def __init__(self, filename: str = "logo.png", content: bytes = b"png-bytes"):
        self.filename = filename
        self.file = MagicMock()
        self.file.read.return_value = content


class _AsyncUpload:
    def __init__(self, filename: str = "avatar.png", content: bytes = b"png-bytes"):
        self.filename = filename
        self._content = content

    async def read(self):
        return self._content


def _stored_app(**overrides) -> dict:
    base = {
        "id": "app-1",
        "uid": "owner-1",
        "name": "Test App",
        "category": "productivity",
        "author": "Owner",
        "description": "Original description",
        "image": "https://storage.googleapis.com/bucket/old-logo.png",
        "capabilities": ["chat"],
        "approved": True,
        "private": False,
        "is_popular": False,
        "is_paid": False,
        "price": 0.0,
        "payment_plan": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 1. Temp file cleanup, filename sanitization, and validation ordering
# ---------------------------------------------------------------------------


def test_create_app_sanitizes_filename_and_cleans_up_temp_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    uploaded_paths = []

    def _fake_upload(file_path, app_id):
        uploaded_paths.append(file_path)
        assert os.path.exists(file_path)
        return "https://storage.googleapis.com/bucket/new-logo.png"

    monkeypatch.setattr(apps_router, "upload_app_logo", _fake_upload)
    monkeypatch.setattr(apps_router, "add_app_to_db", lambda data: None)
    monkeypatch.setattr(apps_router, "upsert_app_payment_link", lambda *a, **k: None)

    payload = {
        "name": "My App",
        "category": "productivity",
        "author": "Dev",
        "email": "dev@example.com",
        "description": "App desc",
        "capabilities": ["chat"],
    }
    res = apps_router.create_app(
        app_data=json.dumps(payload),
        file=_SyncUpload(filename="../../nested/evil.png"),
        uid="owner-1",
    )

    assert res["status"] == "ok"
    assert uploaded_paths == ["_temp/apps/evil.png"]
    assert not os.path.exists("_temp/apps/evil.png")


def test_create_app_validation_failure_deletes_uploaded_gcs_logo_and_temp_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    deleted_logos = []

    monkeypatch.setattr(
        apps_router,
        "upload_app_logo",
        lambda file_path, app_id: "https://storage.googleapis.com/bucket/orphan-logo.png",
    )
    monkeypatch.setattr(apps_router, "delete_app_logo", lambda url: deleted_logos.append(url))
    monkeypatch.setattr(apps_router, "get_user_from_uid", lambda uid: {"display_name": "Dev", "email": "d@e.com"})

    # Missing required 'category', 'description', 'capabilities' -> AppCreate.model_validate raises ValidationError
    with pytest.raises(HTTPException) as exc_info:
        apps_router.create_app(
            app_data=json.dumps({"name": "Incomplete App"}),
            file=_SyncUpload(filename="logo.png"),
            uid="owner-1",
        )

    assert exc_info.value.status_code == 422
    assert deleted_logos == ["https://storage.googleapis.com/bucket/orphan-logo.png"]
    assert not os.path.exists("_temp/apps/logo.png")


def test_update_app_validation_failure_does_not_delete_existing_logo_or_upload_new_one(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    deleted_logos = []
    uploaded_logos = []

    monkeypatch.setattr(apps_router, "get_available_app_by_id", lambda app_id, uid: _stored_app())
    monkeypatch.setattr(apps_router, "delete_app_logo", lambda url: deleted_logos.append(url))
    monkeypatch.setattr(apps_router, "upload_app_logo", lambda path, app_id: uploaded_logos.append(path))

    with pytest.raises(HTTPException) as exc_info:
        apps_router.update_app(
            "app-1",
            app_data=json.dumps({"external_integration": "invalid-non-dict"}),
            file=_SyncUpload(filename="new.png"),
            uid="owner-1",
        )

    assert exc_info.value.status_code == 422
    assert deleted_logos == []
    assert uploaded_logos == []


def test_update_app_rejects_negative_price_before_mutating_logo_or_db(monkeypatch):
    deleted_logos = []
    db_writes = []
    monkeypatch.setattr(apps_router, "get_available_app_by_id", lambda app_id, uid: _stored_app())
    monkeypatch.setattr(apps_router, "delete_app_logo", lambda url: deleted_logos.append(url))
    monkeypatch.setattr(apps_router, "update_app_in_db", lambda data: db_writes.append(data))

    with pytest.raises(HTTPException) as exc_info:
        apps_router.update_app(
            "app-1",
            app_data=json.dumps({"price": -5.0}),
            file=_SyncUpload(filename="new.png"),
            uid="owner-1",
        )

    assert exc_info.value.status_code == 422
    assert "negative" in exc_info.value.detail
    assert deleted_logos == []
    assert db_writes == []


def test_create_and_update_persona_clean_up_temp_files(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    async def _run_blocking(executor, fn, *args):
        return fn(*args)

    async def _gen_prompt(uid, data):
        return "persona-prompt"

    monkeypatch.setattr(apps_router, "run_blocking", _run_blocking)
    monkeypatch.setattr(apps_router, "get_user_from_uid", lambda uid: {"display_name": "Ada", "email": "ada@e.com"})
    monkeypatch.setattr(apps_router, "increment_username", lambda u: u)
    monkeypatch.setattr(apps_router, "save_username", lambda u, uid: None)
    monkeypatch.setattr(apps_router, "generate_persona_prompt", _gen_prompt)
    monkeypatch.setattr(apps_router, "generate_persona_desc", lambda uid, name: "desc")
    monkeypatch.setattr(apps_router, "upload_app_logo", lambda path, pid: "https://storage.googleapis.com/b/p.png")
    monkeypatch.setattr(apps_router, "add_app_to_db", lambda data: None)
    monkeypatch.setattr(apps_router, "update_app_in_db", lambda data: None)
    monkeypatch.setattr(apps_router, "delete_app_logo", lambda url: None)
    monkeypatch.setattr(apps_router, "invalidate_approved_apps_cache", lambda: None)
    monkeypatch.setattr(apps_router, "delete_app_cache_by_id", lambda pid: None)
    monkeypatch.setattr(
        apps_router,
        "get_available_app_by_id",
        lambda pid, uid: _stored_app(id=pid, uid=uid, category="personality-emulation", capabilities=["persona"]),
    )

    res_create = asyncio.run(
        apps_router.create_persona(
            persona_data=json.dumps({"name": "Ada", "username": "ada"}),
            file=_AsyncUpload(filename="../ traversal /avatar.png"),
            uid="owner-1",
        )
    )
    assert res_create["status"] == "ok"
    assert not os.path.exists("_temp/apps/avatar.png")

    res_update = asyncio.run(
        apps_router.update_persona(
            "persona-1",
            persona_data=json.dumps({"name": "Ada"}),
            file=_AsyncUpload(filename="../ traversal /updated.png"),
            uid="owner-1",
        )
    )
    assert res_update["status"] == "ok"
    assert not os.path.exists("_temp/apps/updated.png")


# ---------------------------------------------------------------------------
# 2. Paid-app partial update preserves stored pricing fields
# ---------------------------------------------------------------------------


def test_update_app_partial_patch_preserves_stored_paid_pricing_fields(monkeypatch):
    stored = _stored_app(is_paid=True, price=9.99, payment_plan="monthly_recurring")
    payment_calls = []

    monkeypatch.setattr(apps_router, "get_available_app_by_id", lambda app_id, uid: dict(stored))
    monkeypatch.setattr(apps_router, "update_app_in_db", lambda data: None)
    monkeypatch.setattr(apps_router, "upsert_app_payment_link", lambda *a, **k: payment_calls.append((a, k)))
    monkeypatch.setattr(apps_router, "invalidate_approved_apps_cache", lambda: None)
    monkeypatch.setattr(apps_router, "delete_app_cache_by_id", lambda app_id: None)

    # Partial update changing only the price on an already-paid app
    apps_router.update_app("app-1", app_data=json.dumps({"price": 14.99}), file=None, uid="owner-1")

    assert len(payment_calls) == 1
    args, kwargs = payment_calls[0]
    assert args == ("app-1", True, 14.99, "monthly_recurring", "owner-1")
    assert kwargs == {"previous_price": 9.99}


# ---------------------------------------------------------------------------
# 3. delete_app and delete_persona logo + cache cleanup
# ---------------------------------------------------------------------------


def test_delete_app_removes_gcs_logo_and_invalidates_popular_cache(monkeypatch):
    stored = _stored_app(
        image="https://storage.googleapis.com/bucket/app-logo.png",
        approved=True,
        is_popular=True,
    )
    events = []

    monkeypatch.setattr(apps_router, "get_available_app_by_id", lambda app_id, uid: stored)
    monkeypatch.setattr(apps_router, "delete_app_logo", lambda url: events.append(("delete_logo", url)))
    monkeypatch.setattr(apps_router, "delete_app_from_db", lambda app_id: events.append(("delete_db", app_id)))
    monkeypatch.setattr(apps_router, "invalidate_approved_apps_cache", lambda: events.append(("inv_approved",)))
    monkeypatch.setattr(apps_router, "invalidate_popular_apps_cache", lambda: events.append(("inv_popular",)))
    monkeypatch.setattr(apps_router, "delete_app_cache_by_id", lambda app_id: events.append(("del_cache", app_id)))

    res = apps_router.delete_app("app-1", uid="owner-1")

    assert res == {"status": "ok"}
    assert ("delete_logo", "https://storage.googleapis.com/bucket/app-logo.png") in events
    assert ("delete_db", "app-1") in events
    assert ("inv_approved",) in events
    assert ("inv_popular",) in events
    assert ("del_cache", "app-1") in events


def test_delete_persona_removes_gcs_logo_and_invalidates_caches(monkeypatch):
    monkeypatch.setenv("ADMIN_KEY", "secret-admin")
    persona_doc = {
        "id": "persona-1",
        "image": "https://storage.googleapis.com/bucket/persona.png",
        "approved": True,
    }
    events = []

    monkeypatch.setattr(apps_router, "get_persona_by_id_db", lambda pid: persona_doc)
    monkeypatch.setattr(apps_router, "delete_app_logo", lambda url: events.append(("delete_logo", url)))
    monkeypatch.setattr(apps_router, "delete_persona_db", lambda pid: events.append(("delete_db", pid)))
    monkeypatch.setattr(apps_router, "invalidate_approved_apps_cache", lambda: events.append(("inv_approved",)))
    monkeypatch.setattr(apps_router, "delete_app_cache_by_id", lambda pid: events.append(("del_cache", pid)))

    res = apps_router.delete_persona("persona-1", secret_key="secret-admin")

    assert res == {"status": "ok"}
    assert events == [
        ("delete_logo", "https://storage.googleapis.com/bucket/persona.png"),
        ("delete_db", "persona-1"),
        ("inv_approved",),
        ("del_cache", "persona-1"),
    ]


# ---------------------------------------------------------------------------
# 4. approve_app and reject_app missing-app 404 guard & popular cache invalidation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("endpoint_fn", [apps_router.approve_app, apps_router.reject_app])
def test_approve_or_reject_missing_app_returns_404_before_mutating_db(monkeypatch, endpoint_fn):
    monkeypatch.setenv("ADMIN_KEY", "secret-admin")
    status_changes = []
    notifications = []

    monkeypatch.setattr(apps_router, "get_available_app_by_id", lambda app_id, uid: None)
    monkeypatch.setattr(
        apps_router, "change_app_approval_status", lambda app_id, approved: status_changes.append((app_id, approved))
    )
    monkeypatch.setattr(apps_router, "send_notification", lambda *a, **k: notifications.append(a))

    with pytest.raises(HTTPException) as exc_info:
        endpoint_fn("missing-app", uid="owner-1", secret_key="secret-admin")

    assert exc_info.value.status_code == 404
    assert status_changes == []
    assert notifications == []


def test_approve_and_reject_popular_app_invalidates_popular_cache(monkeypatch):
    monkeypatch.setenv("ADMIN_KEY", "secret-admin")
    popular_invalidations = []

    monkeypatch.setattr(
        apps_router, "get_available_app_by_id", lambda app_id, uid: _stored_app(is_popular=True, name="PopApp")
    )
    monkeypatch.setattr(apps_router, "change_app_approval_status", lambda app_id, approved: None)
    monkeypatch.setattr(apps_router, "invalidate_approved_apps_cache", lambda: None)
    monkeypatch.setattr(
        apps_router, "invalidate_popular_apps_cache", lambda: popular_invalidations.append("invalidated")
    )
    monkeypatch.setattr(apps_router, "delete_app_cache_by_id", lambda app_id: None)
    monkeypatch.setattr(apps_router, "send_notification", lambda *a, **k: None)

    assert apps_router.approve_app("app-1", uid="owner-1", secret_key="secret-admin") == {"status": "ok"}
    assert apps_router.reject_app("app-1", uid="owner-1", secret_key="secret-admin") == {"status": "ok"}
    assert len(popular_invalidations) == 2


# ---------------------------------------------------------------------------
# 5. update_app_review legacy rated_at fallback & generate_persona_desc lock filter
# ---------------------------------------------------------------------------


def test_update_app_review_handles_legacy_review_without_rated_at(monkeypatch):
    saved = {}
    monkeypatch.setattr(apps_router, "get_available_app_by_id", lambda app_id, uid: _stored_app(uid="dev-1"))
    monkeypatch.setattr(
        apps_router,
        "get_specific_user_review",
        lambda app_id, uid: {"score": 3, "review": "old", "uid": uid},
    )
    monkeypatch.setattr(apps_router, "set_app_review", lambda app_id, uid, data: saved.update(data))
    monkeypatch.setattr(apps_router, "send_new_app_review_notification", lambda **k: None)

    res = apps_router.update_app_review(
        "app-1",
        apps_router.ReviewAppRequest(score=5, review="great"),
        uid="reviewer-1",
    )

    assert res == {"status": "ok"}
    assert saved["score"] == 5
    assert saved["rated_at"] == saved["updated_at"]


def test_generate_persona_desc_excludes_locked_memories(monkeypatch):
    unlocked_mem = SimpleNamespace(is_locked=False, dict=lambda: {"id": "m1", "content": "Public bio fact"})
    locked_mem = SimpleNamespace(is_locked=True, dict=lambda: {"id": "m2", "content": "Private locked secret"})

    fake_service = MagicMock()
    fake_service.read.return_value = [unlocked_mem, locked_mem]
    captured = {}

    def _fake_gen_desc(memories, persona_name):
        captured["memories"] = memories
        captured["persona_name"] = persona_name
        return "Generated description"

    monkeypatch.setattr(apps_utils, "MemoryService", lambda db_client=None: fake_service)
    monkeypatch.setattr(apps_utils, "generate_persona_description", _fake_gen_desc)

    result = apps_utils.generate_persona_desc("user-1", "Ada")

    assert result == "Generated description"
    assert captured["memories"] == [{"id": "m1", "content": "Public bio fact"}]


# ---------------------------------------------------------------------------
# 6. speech_profile upload_profile temp cleanup & expand person_id='null' guard
# ---------------------------------------------------------------------------


def test_speech_profile_upload_cleans_up_temp_file_on_success_and_error(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    fake_file = _SyncUpload(filename="../../traversal/voice.wav", content=b"wav-bytes")

    # Case 1: invalid WAV raises 400 and cleans up temp file
    with patch.object(sp_router.AudioSegment, "from_wav", side_effect=ValueError("bad wav")):
        with pytest.raises(HTTPException) as exc_info:
            sp_router.upload_profile(fake_file, uid="u-speech")
    assert exc_info.value.status_code == 400
    assert not os.path.exists("_temp/u-speech/voice.wav")

    # Case 2: valid WAV succeeds and cleans up temp file
    fake_aseg = MagicMock(frame_rate=16000, duration_seconds=10)
    fake_embedding = MagicMock()
    fake_embedding.flatten.return_value.tolist.return_value = [0.1, 0.2]

    with patch.object(sp_router.AudioSegment, "from_wav", return_value=fake_aseg), patch.object(
        sp_router, "apply_vad_for_speech_profile"
    ), patch.object(sp_router, "av") as mock_av, patch.object(
        sp_router, "extract_embedding", return_value=fake_embedding
    ), patch.object(
        sp_router, "set_user_speaker_embedding"
    ), patch.object(
        sp_router, "upload_profile_audio", return_value="https://storage.googleapis.com/b/profile.wav"
    ), patch.object(
        sp_router, "set_speech_profile_duration"
    ):
        mock_av.open.return_value.__enter__.return_value.duration = None
        res = sp_router.upload_profile(fake_file, uid="u-speech")

    assert res == {"url": "https://storage.googleapis.com/b/profile.wav"}
    assert not os.path.exists("_temp/u-speech/voice.wav")


def test_get_extra_speech_profile_samples_normalizes_literal_null_person_id(monkeypatch):
    person_calls = []
    user_calls = []

    monkeypatch.setattr(
        sp_router, "get_user_person_speech_samples", lambda uid, pid: person_calls.append((uid, pid)) or ["person.wav"]
    )
    monkeypatch.setattr(
        sp_router, "get_additional_profile_recordings", lambda uid: user_calls.append(uid) or ["user.wav"]
    )

    res = sp_router.get_extra_speech_profile_samples(person_id="null", uid="u-1")

    assert res == ["user.wav"]
    assert person_calls == []
    assert user_calls == ["u-1"]
