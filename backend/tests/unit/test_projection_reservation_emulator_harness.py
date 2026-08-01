"""Wiring contract for the projection Firestore-emulator contention harness."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2].parent


def test_projection_reservation_emulator_harness_uses_the_real_transaction_boundary():
    harness_path = REPO_ROOT / 'backend' / 'scripts' / 'projection_reservation_emulator_test.py'
    package = json.loads((REPO_ROOT / 'package.json').read_text())
    harness = harness_path.read_text()

    assert package['scripts']['test:projection-reservation:emulator'] == (
        'firebase emulators:exec --only firestore --project demo-projections '
        '"backend/.venv/bin/python backend/scripts/projection_reservation_emulator_test.py"'
    )
    assert 'FIRESTORE_EMULATOR_HOST' in harness
    assert 'reserve_projection_generation' in harness
    assert 'finalize_projection_generation' in harness
    assert 'ThreadPoolExecutor' in harness
    assert 'expected exactly one reservation owner under contention' in harness
    assert 'a losing attempt finalized the winning reservation' in harness
    assert 'PASS: Firestore emulator allowed one projection reservation owner and fenced losing finalization' in harness
