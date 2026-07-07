"""Unit tests for the whole-roster first-sync backfill."""

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")
os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# person_backfill imports database.conversations, whose transitive chain constructs real
# Firestore/GCS clients at import time. Install the shared unit-test stubs first.
from tests.unit.memory_import_isolation import (  # noqa: E402
    ensure_utils_memory_packages_importable,
    install_canonical_write_runtime_stubs,
    install_database_client_stub,
    install_ws_i_heavy_import_stubs,
)

ensure_utils_memory_packages_importable(str(BACKEND_DIR))
install_database_client_stub()
install_canonical_write_runtime_stubs()
install_ws_i_heavy_import_stubs()

import utils.memory.person_backfill as bf  # noqa: E402


def _conv(pid, n_segs):
    return {"id": f"c_{pid}", "person_ids": [pid], "transcript_segments": [{"text": "hi", "person_id": pid}] * n_segs}


def test_backfill_person_skips_thin_history():
    with patch.object(bf.conversations_db, "get_conversations_by_person_id", return_value=[_conv("p1", 2)]), patch.object(
        bf, "enrich_persons_from_conversation"
    ) as enrich, patch.object(bf, "generate_person_profile") as prof:
        r = bf.backfill_person("u", "p1")
    assert r["facts_written"] == 0 and r["profile_updated"] is False
    enrich.assert_not_called()  # below _MIN_SEGMENTS
    prof.assert_not_called()


def test_backfill_person_enriches_and_profiles():
    with patch.object(
        bf.conversations_db, "get_conversations_by_person_id", return_value=[_conv("p1", 10)]
    ), patch.object(bf, "Conversation", side_effect=lambda **kw: kw), patch.object(
        bf, "enrich_persons_from_conversation", return_value={"p1": 3}
    ) as enrich, patch.object(
        bf, "generate_person_profile", return_value=True
    ) as prof:
        r = bf.backfill_person("u", "p1")
    assert r["facts_written"] == 3 and r["profile_updated"] is True
    enrich.assert_called_once()
    prof.assert_called_once()


def test_backfill_people_iterates_roster_and_counts():
    people = [{"id": "p1"}, {"id": "p2"}, {"id": None}]
    with patch.object(bf.users_db, "get_people", return_value=people), patch.object(
        bf, "backfill_person", side_effect=lambda uid, pid, **k: {"person_id": pid, "facts_written": 2, "profile_updated": True, "conversations": 1}
    ) as bp:
        s = bf.backfill_people("u")
    assert s["people_seen"] == 2  # None id skipped
    assert s["people_enriched"] == 2 and s["facts_written"] == 4 and s["profiles_updated"] == 2
    assert bp.call_count == 2


def test_backfill_people_respects_max_people():
    people = [{"id": f"p{i}"} for i in range(10)]
    with patch.object(bf.users_db, "get_people", return_value=people), patch.object(
        bf, "backfill_person", side_effect=lambda uid, pid, **k: {"person_id": pid, "facts_written": 1, "profile_updated": True, "conversations": 1}
    ):
        s = bf.backfill_people("u", max_people=3)
    assert s["people_enriched"] == 3


def test_first_sync_runs_once():
    r = MagicMock()
    r.set.return_value = True  # first caller claims the flag
    with patch.object(bf.redis_db, "r", r), patch.object(bf, "backfill_people", return_value={"people_enriched": 5}) as run:
        out = bf.maybe_backfill_on_first_sync("u", "en")
    assert out == {"people_enriched": 5}
    run.assert_called_once()
    r.set.assert_called_once_with("person_backfill:v1:u", "1", nx=True)


def test_first_sync_skips_when_already_claimed():
    r = MagicMock()
    r.set.return_value = None  # someone already claimed it (nx failed)
    with patch.object(bf.redis_db, "r", r), patch.object(bf, "backfill_people") as run:
        out = bf.maybe_backfill_on_first_sync("u", "en")
    assert out == {}
    run.assert_not_called()
