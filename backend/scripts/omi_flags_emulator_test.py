#!/usr/bin/env python3
"""Real-Firestore check of the Omi flag store write/read path (run under the emulator).

    firebase emulators:exec --only firestore --project demo-omi-flags \\
      "backend/.venv/bin/python backend/scripts/omi_flags_emulator_test.py"
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import omi_flags as store  # noqa: E402
from utils import omi_flags  # noqa: E402


def main() -> int:
    assert os.getenv('FIRESTORE_EMULATOR_HOST'), 'run under the Firestore emulator'
    os.environ['OMI_FLAGS_FIRESTORE_PROJECT'] = 'demo-omi-flags'
    client = store.flags_client()
    rule = {'active': True, 'rollout_percentage': 100.0, 'surfaces': ['macos'], 'allow_uids': [], 'deny_uids': []}
    assert store.write_rule(client, 'screen_task_jev_gate', rule, actor='emulator', reason='seed') == 1
    assert (
        store.write_rule(client, 'screen_task_jev_gate', {**rule, 'active': False}, actor='emulator', reason='kill')
        == 2
    )
    version, docs = store.read_all(client)
    assert version == 2 and docs['screen_task_jev_gate']['active'] is False, (version, docs)
    history = store.read_audit(client, 'screen_task_jev_gate')
    assert [row['reason'] for row in history] == ['kill', 'seed'], history
    assert history[0]['before']['active'] is True and history[0]['after']['active'] is False
    assert omi_flags.resolve_surface('uid-1', 'macos')[1]['screen_task_jev_gate'].enabled is False
    assert store.write_rule(client, 'screen_task_jev_gate', None, actor='emulator', reason='hand back') == 3
    assert 'screen_task_jev_gate' not in store.read_all(client)[1]
    print('omi flags emulator check: OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
