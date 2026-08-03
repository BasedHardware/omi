from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from utils.memory.legacy_backfill_bulk_support import LegacyBackfillInventoryReport

BACKEND_DIR = Path(__file__).resolve().parents[2]
SCRIPT = BACKEND_DIR / "scripts" / "bulk_backfill_legacy_memories.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("bulk_backfill_legacy_memories", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return _load_script()


class _Snapshot:
    exists = False

    def to_dict(self):
        return None


class _Document:
    def __init__(self, db, path):
        self._db = db
        self._path = path

    def get(self):
        self._db.reads.append(self._path)
        return _Snapshot()

    def set(self, payload, merge=False):
        self._db.writes.append((self._path, payload, merge))


class _Db:
    def __init__(self):
        self.reads = []
        self.writes = []

    def document(self, path):
        return _Document(self, path)


def test_dry_run_cli_uses_offline_fake_and_emits_redacted_json(script, monkeypatch, capsys):
    db = _Db()
    secret_content = "the user's raw secret memory"
    monkeypatch.setattr(script, "_load_firestore_client", lambda **_: db)
    monkeypatch.setattr(
        script,
        "inventory_legacy_user",
        lambda uid, **_: LegacyBackfillInventoryReport(
            uid=uid,
            source_count=3,
            bucket_counts={"manual_required_promotion": 2, "hold_sensitive": 1},
            admitted_candidate_count=2,
            content_character_count=len(secret_content),
            estimated_tokens=8,
            admitted_candidate_estimated_tokens=6,
        ),
    )

    exit_code = script.main(
        [
            "--uid",
            "uid-a",
            "--firestore-project",
            "offline-test-project",
            "--max-users-per-run",
            "1",
        ]
    )

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert exit_code == 0
    assert payload["dry_run"] is True
    assert payload["users"][0]["actions"] == [
        "would_enroll_write_only",
        "would_stage_all_for_admission",
    ]
    assert secret_content not in output
    assert db.writes == []
    assert db.reads == ["memory_control/legacy_canonical_backfill_pause"]


def test_apply_cli_requires_both_bulk_confirmations(script, capsys):
    try:
        script.main(
            [
                "--uid",
                "uid-a",
                "--firestore-project",
                "offline-test-project",
                "--apply",
            ]
        )
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("unsafe apply flags unexpectedly accepted")

    assert "--confirm-apply must be exactly" in capsys.readouterr().err
