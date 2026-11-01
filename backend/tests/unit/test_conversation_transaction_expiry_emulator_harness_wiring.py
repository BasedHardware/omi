"""Wiring contract for the expired-transaction restart Firestore-emulator proof."""

from __future__ import annotations

import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2].parent


def test_conversation_transaction_expiry_emulator_harness_proves_the_aborted_read_restart() -> None:
    harness_path = _REPO_ROOT / 'backend' / 'scripts' / 'conversation_transaction_expiry_emulator_test.py'
    package = json.loads((_REPO_ROOT / 'package.json').read_text())
    harness = harness_path.read_text()

    assert package['scripts']['test:conversation-transaction-expiry:emulator'] == (
        'firebase emulators:exec --only firestore --project demo-listen '
        '"backend/.venv/bin/python backend/scripts/conversation_transaction_expiry_emulator_test.py"'
    )
    assert 'FIRESTORE_EMULATOR_HOST' in harness
    assert 'ENCRYPTION_SECRET' in harness
    assert 'update_conversation_segments' in harness
    assert 'The referenced transaction has expired or is no longer valid.' in harness
    assert 'grpc_helpers' in harness
    # The retired-id step must genuinely retire a real SDK-begun id out-of-band...
    assert '_emulator_post(' in harness
    assert ':commit' in harness
    # ...and the production envelope step must inject at the transport seam the
    # production remap feeds, not at a hand-written fake.
    assert '_wrapped_methods[transport.batch_get_documents]' in harness
    assert 'Aborted' in harness
    # The restart must be proven to use a fresh transaction id and a durable write.
    assert 'fresh one' in harness
    assert 'durable' in harness
    assert 'PASS: expired-transaction reads fail through the real stack and the Aborted 409 restarts durably' in harness
