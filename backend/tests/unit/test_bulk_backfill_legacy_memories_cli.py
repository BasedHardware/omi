from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from database import document_store
from tests.store_fakes import FakeDocumentStore
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


class _RecordingStore(FakeDocumentStore):
    """Neutral store fake that records path-level reads/writes for the CLI assertions."""

    def __init__(self):
        super().__init__()
        self.reads: list[str] = []
        self.writes: list[tuple] = []

    def get(self, path, **kwargs):
        self.reads.append(path)
        return super().get(path, **kwargs)

    def set(self, path, data, *, merge=False):
        self.writes.append((path, data, merge))
        return super().set(path, data, merge=merge)


def test_dry_run_cli_uses_offline_fake_and_emits_redacted_json(script, monkeypatch, capsys):
    store = _RecordingStore()
    secret_content = "the user's raw secret memory"
    # The CLI resolves its store via get_document_store(); read_global_pause reads through the
    # document_store facade. Route both to one recording fake so the dry-run access is observable.
    monkeypatch.setattr(script, "get_document_store", lambda: store)
    monkeypatch.setattr(document_store, "_store", lambda: store)
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
    assert store.writes == []
    assert store.reads == ["memory_control/legacy_canonical_backfill_pause"]


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
