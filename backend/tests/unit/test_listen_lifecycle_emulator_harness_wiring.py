"""Wiring contract for the #9687 Firestore-emulator contention harness."""

from __future__ import annotations

import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2].parent


def test_listen_lifecycle_emulator_harness_exercises_real_content_and_cleanup_primitives() -> None:
    harness_path = _REPO_ROOT / 'backend' / 'scripts' / 'listen_lifecycle_emulator_test.py'
    package = json.loads((_REPO_ROOT / 'package.json').read_text())
    harness = harness_path.read_text()

    assert package['scripts']['test:listen-lifecycle:emulator'] == (
        'firebase emulators:exec --only firestore --project demo-listen '
        '"backend/.venv/bin/python backend/scripts/listen_lifecycle_emulator_test.py"'
    )
    assert 'FIRESTORE_EMULATOR_HOST' in harness
    assert 'ENCRYPTION_SECRET' in harness
    assert 'update_conversation_segments' in harness
    assert 'store_conversation_photos' in harness
    assert 'tombstone_and_delete_empty_conversation' in harness
    assert 'request_finalization' in harness
    assert 'retry_fenced_live_content_once' in harness
    assert 'Cleanup-first ordering must move late buffered content to a fresh generation' in harness
    assert 'late content write did not block behind the cleanup parent lock' in harness
    assert 'first-segment started_at did not commit atomically with content' in harness
    assert (
        'PASS: Firestore emulator fenced cleanup races and preserved listen content through fresh-generation replay'
        in harness
    )
