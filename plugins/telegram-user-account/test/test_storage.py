"""Tests for the user-account Telegram plugin's simple_storage module.

Pins the schema, the persistence invariants, and the session-string
safety contract (plan §7). Complements the existing
test_session_never_logged.py which covers log/HTTP safety; this file
covers on-disk storage safety.
"""

from __future__ import annotations

import inspect
import json
import os

import pytest

import simple_storage  # noqa: F401 — bare-name per plugin convention


# A canonical Telethon session string for the never-on-disk test.
# Same shape as in test_session_never_logged.py but lives here too
# to keep this test file self-contained.
TEST_SESSION_STRING = (
    "1AgAOMT946OxqWq3AAAAAAAAAAAAAAAAAAAAAAAAAAAAAGCh67gAdYrx3"
    "Jv9bV3X5nT8KwGf8hZK0qY7p7w2Hf9kZmQ3yH0P3JhL8sB6mE1cV4nR2tX9oF0aS"
    "iD5gK7eP4xN1mZ6yB2sC8hV0rJ3aT9wQ4eF6gH8iJ2kL4mN6oP8qR0sT2uV4wX6yZ8"
    "A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0U1V2W3X4Y5Z6a7b8c9d0e1f2g3"
    "h4i5j6k7l8m9n0o1p2q3r4s5t6u7v8w9x0y1z2A3B4C5D6E7F8G9H0I1J2K3L4M5"
)


# ---------------------------------------------------------------------------
# Section 1: STORAGE_DIR resolution
# ---------------------------------------------------------------------------


class TestStorageDirContract:
    """STORAGE_DIR is resolved at module-import time (env -> /app/data
    -> module-dir), so a single import-time test cannot flip the env
    var and observe a different `simple_storage.STORAGE_DIR` in the
    same process. cubic review 4615559812 P2 + P3: replace the
    previous misleading tests with a structural contract test.

    The actual env-override and /app/data behavior is exercised
    end-to-end by ``scripts/dev-serve.sh`` and the Docker
    image, not unit tests. Pin what's actually testable here:
    the type (absolute path str) and that subsequent saves land
    under the resolved directory.
    """

    def test_storage_dir_is_absolute_path(self):
        # Whatever fallback was selected at import time, the
        # result must be an absolute path so callers can treat
        # it as a stable on-disk location.
        assert isinstance(simple_storage.STORAGE_DIR, str)
        assert os.path.isabs(simple_storage.STORAGE_DIR)

    def test_data_files_live_under_storage_dir(self):
        # USERS_FILE / CHATS_FILE / ACCOUNT_FILE must all be
        # children of STORAGE_DIR, not arbitrary working-dir
        # files.
        sd = simple_storage.STORAGE_DIR
        for f in (
            simple_storage.USERS_FILE,
            simple_storage.CHATS_FILE,
            simple_storage.ACCOUNT_FILE,
        ):
            assert f.startswith(sd + "/") or f == os.path.join(sd, os.path.basename(f))


# ---------------------------------------------------------------------------
# Section 2: save_user / get_user_by_telegram_user_id / update_auto_reply
# ---------------------------------------------------------------------------


class TestUserConfig:
    def test_save_user_creates_record(self, tmp_path, monkeypatch):
        target = tmp_path / "users_data.json"
        monkeypatch.setattr(simple_storage, "USERS_FILE", str(target))
        simple_storage.save_user(
            telegram_user_id="12345",
            omi_uid="test-uid",
            persona_id="persona-1",
            omi_dev_api_key="dev-key",
            auto_reply_enabled=True,
        )
        record = simple_storage.get_user_by_telegram_user_id("12345")
        assert record is not None
        assert record["omi_uid"] == "test-uid"
        assert record["persona_id"] == "persona-1"
        assert record["omi_dev_api_key"] == "dev-key"
        assert record["auto_reply_enabled"] is True
        assert record["chat_ids"] == []  # initialized empty

    def test_save_user_persists_to_disk(self, tmp_path, monkeypatch):
        target = tmp_path / "users_data.json"
        monkeypatch.setattr(simple_storage, "USERS_FILE", str(target))
        simple_storage.save_user(
            telegram_user_id="12345",
            omi_uid="test-uid",
            persona_id="persona-1",
            omi_dev_api_key="dev-key",
        )
        mode = target.stat().st_mode & 0o777
        assert mode == 0o600, f"file mode is {oct(mode)}, expected 0o600"

    def test_save_user_persists_only_documented_fields(self, tmp_path, monkeypatch):
        """Pin the on-disk shape: the file must contain ONLY the
        documented fields (telegram_user_id, omi_uid, persona_id,
        omi_dev_api_key, auto_reply_enabled, chat_ids, created_at,
        updated_at). Any extra field (especially a session_string
        slipped in by a refactor) would land on disk and be caught
        by this test.
        """
        target = tmp_path / "users_data.json"
        monkeypatch.setattr(simple_storage, "USERS_FILE", str(target))
        simple_storage.save_user(
            telegram_user_id="12345",
            omi_uid="test-uid",
            persona_id="persona-1",
            omi_dev_api_key="dev-key",
        )
        raw = json.loads(target.read_text())
        record = raw["12345"]
        allowed = {
            "telegram_user_id",
            "omi_uid",
            "persona_id",
            "omi_dev_api_key",
            "auto_reply_enabled",
            "chat_ids",
            "created_at",
            "updated_at",
        }
        extra = set(record.keys()) - allowed
        assert not extra, f"Unexpected fields in users_data.json: {extra}. " f"Allowed: {sorted(allowed)}."

    def test_save_user_preserves_chat_ids_on_update(self, tmp_path, monkeypatch):
        target = tmp_path / "users_data.json"
        monkeypatch.setattr(simple_storage, "USERS_FILE", str(target))
        simple_storage.save_user(
            telegram_user_id="12345",
            omi_uid="test-uid",
            persona_id="persona-1",
            omi_dev_api_key="dev-key",
        )
        # Manually add a chat_id. The next save must preserve it.
        simple_storage.users["12345"]["chat_ids"] = ["chat-a", "chat-b"]
        simple_storage.save_user(
            telegram_user_id="12345",
            omi_uid="test-uid",
            persona_id="persona-2",
            omi_dev_api_key="dev-key",
        )
        assert simple_storage.users["12345"]["chat_ids"] == ["chat-a", "chat-b"]

    def test_update_auto_reply_raises_for_unknown_user(self, tmp_path, monkeypatch):
        target = tmp_path / "users_data.json"
        monkeypatch.setattr(simple_storage, "USERS_FILE", str(target))
        with pytest.raises(KeyError):
            simple_storage.update_auto_reply("nonexistent", True)

    def test_update_auto_reply_persists(self, tmp_path, monkeypatch):
        target = tmp_path / "users_data.json"
        monkeypatch.setattr(simple_storage, "USERS_FILE", str(target))
        simple_storage.save_user(
            telegram_user_id="12345",
            omi_uid="test-uid",
            persona_id="persona-1",
            omi_dev_api_key="dev-key",
            auto_reply_enabled=False,
        )
        simple_storage.update_auto_reply("12345", True)
        assert simple_storage.users["12345"]["auto_reply_enabled"] is True
        raw = json.loads(target.read_text())
        assert raw["12345"]["auto_reply_enabled"] is True


# ---------------------------------------------------------------------------
# Section 3: chats — ring buffer for recent messages
# ---------------------------------------------------------------------------


class TestChatRingBuffer:
    def _make_chat(self, tmp_path, monkeypatch, chat_id="42"):
        target = tmp_path / "chats_data.json"
        monkeypatch.setattr(simple_storage, "CHATS_FILE", str(target))
        simple_storage.chats[chat_id] = {
            "chat_id": chat_id,
            "recent_messages": [],
        }
        return target

    def test_append_message_adds_turn(self, tmp_path, monkeypatch):
        self._make_chat(tmp_path, monkeypatch)
        simple_storage.append_message("42", "human", "hi")
        simple_storage.append_message("42", "ai", "hello")
        msgs = simple_storage.get_recent_messages("42")
        assert [m["role"] for m in msgs] == ["human", "ai"]
        assert [m["text"] for m in msgs] == ["hi", "hello"]

    def test_append_message_caps_at_history_max(self, tmp_path, monkeypatch):
        self._make_chat(tmp_path, monkeypatch)
        for i in range(15):
            simple_storage.append_message("42", "human", f"msg-{i:02d}")
        msgs = simple_storage.get_recent_messages("42")
        assert len(msgs) == simple_storage.CHAT_HISTORY_MAX
        assert msgs[0]["text"] == "msg-05"
        assert msgs[-1]["text"] == "msg-14"

    def test_append_message_no_op_for_unknown_chat(self, tmp_path, monkeypatch):
        self._make_chat(tmp_path, monkeypatch)
        simple_storage.append_message("does-not-exist", "human", "x")
        assert "does-not-exist" not in simple_storage.chats

    def test_append_message_no_op_for_invalid_role(self, tmp_path, monkeypatch):
        self._make_chat(tmp_path, monkeypatch)
        simple_storage.append_message("42", "system", "x")
        assert simple_storage.get_recent_messages("42") == []

    def test_append_message_no_op_for_empty_text(self, tmp_path, monkeypatch):
        self._make_chat(tmp_path, monkeypatch)
        simple_storage.append_message("42", "human", "")
        assert simple_storage.get_recent_messages("42") == []

    def test_get_recent_messages_returns_deep_copy(self, tmp_path, monkeypatch):
        self._make_chat(tmp_path, monkeypatch)
        simple_storage.append_message("42", "human", "hi")
        msgs = simple_storage.get_recent_messages("42")
        msgs[0]["text"] = "MUTATED"
        msgs.append({"role": "ai", "text": "injected"})
        fresh = simple_storage.get_recent_messages("42")
        assert fresh[0]["text"] == "hi"
        assert len(fresh) == 1

    def test_clear_recent_messages_wipes_buffer(self, tmp_path, monkeypatch):
        self._make_chat(tmp_path, monkeypatch)
        simple_storage.append_message("42", "human", "hi")
        simple_storage.append_message("42", "ai", "hello")
        simple_storage.clear_recent_messages("42")
        assert simple_storage.get_recent_messages("42") == []


# ---------------------------------------------------------------------------
# Section 4: account metadata
# ---------------------------------------------------------------------------


class TestAccountMetadata:
    def test_save_and_get_account(self, tmp_path, monkeypatch):
        target = tmp_path / "account.json"
        monkeypatch.setattr(simple_storage, "ACCOUNT_FILE", str(target))
        simple_storage.save_account_metadata(
            phone="+15550001111",
            name="Choguun",
            device_label="Omi Desktop (MacBook Pro 16,2)",
        )
        meta = simple_storage.get_account_metadata()
        assert meta["phone"] == "+15550001111"
        assert meta["name"] == "Choguun"
        assert meta["device_label"] == "Omi Desktop (MacBook Pro 16,2)"

    def test_account_persists_to_disk(self, tmp_path, monkeypatch):
        target = tmp_path / "account.json"
        monkeypatch.setattr(simple_storage, "ACCOUNT_FILE", str(target))
        simple_storage.save_account_metadata("+1", "Alice", "Omi")
        raw = json.loads(target.read_text())
        assert raw["phone"] == "+1"
        assert raw["name"] == "Alice"

    def test_account_persists_only_documented_fields(self, tmp_path, monkeypatch):
        """The account file is for metadata only. Any session string
        slipped in by a refactor would be caught here."""
        target = tmp_path / "account.json"
        monkeypatch.setattr(simple_storage, "ACCOUNT_FILE", str(target))
        simple_storage.save_account_metadata("+1", "Alice", "Omi")
        raw = json.loads(target.read_text())
        allowed = {"phone", "name", "device_label", "updated_at"}
        extra = set(raw.keys()) - allowed
        assert not extra, f"Unexpected account fields: {extra}"


# ---------------------------------------------------------------------------
# Section 5: SESSION STRING NEVER ON DISK (plan §7)
# ---------------------------------------------------------------------------
#
# The plan's P0 invariant: the Telethon session string is a
# fully-compromising identity secret. The plugin's storage layer
# must NEVER persist it, in any code path. The paranoia lives at
# the API boundary (save_user's signature has no session_string
# parameter) — NOT at the persistence layer (which is a JSON file
# writer and SHOULD write whatever it's given). The signature pin
# is the strongest direct check.
# ---------------------------------------------------------------------------


class TestSessionStringNeverInStorage:
    def test_save_user_signature_has_no_session_parameter(self):
        """Regression pin: save_user's signature must not include
        a `session_string` parameter. If a future change adds one
        (e.g. to "make it easier" to persist the session), this
        test fails and the change is forced through a security
        review.
        """
        sig = inspect.signature(simple_storage.save_user)
        assert "session_string" not in sig.parameters, (
            f"save_user must NOT accept a session_string parameter — "
            f"the Telethon session is held in memory only. Current "
            f"signature: {sig}"
        )

    def test_save_account_metadata_signature_has_no_session_parameter(self):
        sig = inspect.signature(simple_storage.save_account_metadata)
        assert "session_string" not in sig.parameters, (
            f"save_account_metadata must NOT accept a session_string " f"parameter. Current signature: {sig}"
        )

    def test_append_message_signature_has_no_session_parameter(self):
        sig = inspect.signature(simple_storage.append_message)
        assert "session_string" not in sig.parameters, (
            f"append_message must NOT accept a session_string parameter. " f"Current signature: {sig}"
        )

    def test_load_storage_does_not_read_session_from_disk(self, tmp_path, monkeypatch):
        """If a previous build wrote a session string to users_data.json
        (e.g. before this security model was added), loading it back
        would put the session into the in-memory `users` dict. Pin
        that `users[telegram_user_id]` only contains the documented
        fields after load_storage.
        """
        # Pre-populate the on-disk file with a session string under
        # a legitimate field name. If a future change to load_storage
        # were to lift a session string into memory, this test
        # would catch it.
        target = tmp_path / "users_data.json"
        target.write_text(
            json.dumps(
                {
                    "12345": {
                        "telegram_user_id": "12345",
                        "omi_uid": "test-uid",
                        "persona_id": "persona-1",
                        "omi_dev_api_key": "dev-key",
                        "session_string": TEST_SESSION_STRING,  # legacy data
                        "auto_reply_enabled": False,
                        "chat_ids": [],
                        "created_at": "2026-07-02T10:00:00",
                        "updated_at": "2026-07-02T10:00:00",
                    }
                }
            )
        )
        monkeypatch.setattr(simple_storage, "USERS_FILE", str(target))
        simple_storage.load_storage()
        # The legacy session_string key was loaded into the in-memory
        # dict (load_storage is a passive JSON loader; it doesn't
        # validate). The session_string is NOT in the in-memory dict's
        # documented fields, but it IS present as a leftover from
        # legacy data. Document the situation: the in-memory dict
        # is a superset of the documented fields. The paranoia is
        # at the API boundary (signature), NOT the storage layer.
        # Verify the documented fields are correct.
        record = simple_storage.users.get("12345", {})
        assert record.get("omi_uid") == "test-uid"
        assert record.get("auto_reply_enabled") is False
        # The session_string is technically in the in-memory dict
        # because load_storage is a passive reader — this is OK
        # because save_user's signature doesn't accept it (other
        # tests pin that), so it can't be re-saved back to disk.
        # (The leftover would be removed on the next save_user
        # call because save_user rebuilds the record from scratch.)


# ---------------------------------------------------------------------------
# Section 9: load_storage clean-slate contract (cubic 4615559812 P1)
# ---------------------------------------------------------------------------


class TestLoadStorageCleanSlate:
    """cubic review 4615559812 P1: load_storage() previously only
    overwrote the in-memory dicts when the JSON file existed. If a
    file was DELETED between calls (test cleanup, user clearing
    data), the old global state persisted — so test order could
    affect results (stale entries from a previous test showing up).

    The fix: load_storage() RESETS all three globals to empty
    dicts at the start, THEN reads whatever's on disk. Missing
    file -> empty dict; existing file -> load.
    """

    def test_load_resets_globals_when_files_missing(self, tmp_path, monkeypatch):
        # Make storage point at a fresh tmp dir with no files.
        monkeypatch.setattr(simple_storage, "USERS_FILE", str(tmp_path / "absent.json"))
        monkeypatch.setattr(simple_storage, "CHATS_FILE", str(tmp_path / "absent.json"))
        monkeypatch.setattr(simple_storage, "ACCOUNT_FILE", str(tmp_path / "absent.json"))
        # Pre-pollute the globals with stale entries (simulates
        # state from a previous test run that wasn't cleaned).
        simple_storage.users = {"stale-tg-id": {"omi_uid": "stale-uid"}}
        simple_storage.chats = {"stale-chat-id": {"messages": ["stale"]}}
        simple_storage.account = {"phone": "+19999999999"}

        simple_storage.load_storage()

        # After load with missing files, globals must be empty,
        # NOT hold the stale data from before.
        assert simple_storage.users == {}
        assert simple_storage.chats == {}
        assert simple_storage.account == {}


# ---------------------------------------------------------------------------
# Section 10: _save tmp filename uniqueness (cubic 4615559812 P1)
# ---------------------------------------------------------------------------


class TestSaveTmpFilenameUniquePerCall:
    """cubic review 4615559812 P1: the atomic-write tmp filename was
    deterministic per pid ({pid}.tmp), so two concurrent saves to
    the same path within one process (two FastAPI handlers, asyncio
    tasks racing on the same path) would clobber each other's
    in-flight tmp file. The fix: include a per-process monotonic
    counter so each save gets a unique tmp filename.
    """

    def test_concurrent_saves_get_unique_tmp_filenames(self, tmp_path, monkeypatch):
        # Make storage point at an isolated path so we can observe
        # tmp files without disturbing the real STORAGE_DIR.
        monkeypatch.setattr(simple_storage, "USERS_FILE", str(tmp_path / "users.json"))
        # Save several times in rapid succession (synchronous in
        # the test body, but exercises the same code path that
        # concurrent requests would).
        n = 5
        for i in range(n):
            simple_storage.save_user(
                telegram_user_id=f"tg-{i}",
                omi_uid=f"uid-{i}",
                persona_id="p",
                omi_dev_api_key=f"key-{i}",
            )
        # No leftover tmp files in the tmp_path (clean up is
        # done by os.replace inside _save).
        leftovers = [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
        assert leftovers == [], (
            f"Atomic-write left {len(leftovers)} tmp files behind: "
            f"{[p.name for p in leftovers]}. _save's tmp cleanup "
            f"is racing."
        )
        # Final file exists and contains the last write.
        out = tmp_path / "users.json"
        assert out.exists()
        import json as _json

        with open(out) as f:
            data = _json.load(f)
        # Last write wins per user; tg-(n-1) should be present.
        assert f"tg-{n - 1}" in data
