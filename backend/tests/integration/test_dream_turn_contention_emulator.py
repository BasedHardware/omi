"""Concurrent minute-shard holds/receipts against an owned, loopback-only emulator."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier
from uuid import uuid4

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from config.dream_agent import Caps
from database import dream_turns
from utils.llm.shaped_agent import Turn

pytestmark = pytest.mark.integration


def test_twenty_concurrent_turns_preserve_minute_and_spend_ledgers(monkeypatch):
    assert os.environ.get('FIRESTORE_EMULATOR_HOST', '').startswith(('127.0.0.1:', 'localhost:'))
    monkeypatch.setattr(dream_turns, 'enabled', lambda: True)
    database = firestore.Client(
        project='demo-dream-contention',
        database='synthetic-' + uuid4().hex,
        credentials=AnonymousCredentials(),
    )
    now = datetime.now(timezone.utc)
    run = 'synthetic-' + uuid4().hex
    barrier = Barrier(20)
    owners = [run + '-' + str(index) for index in range(20)]
    for owner in owners:
        dream_turns.dream_store.state_ref(database, owner).set(
            {'lease': {'run_id': run, 'day': now.date().isoformat(), 'budget_charge_usd': 0.0}}
        )

    def turn(owner):
        barrier.wait(timeout=10)
        dream_turns.reserve(owner, run, 40000, Caps(), now=now, firestore_client=database)
        usage = Turn(tokens=100, prompt_tokens=80, completion_tokens=20, cached_tokens=0)
        usage.cost_status, usage.cost_micro_usd = 'priced', 100
        dream_turns.settle(owner, run, usage, firestore_client=database)

    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = [pool.submit(turn, owner) for owner in owners]
        for future in futures:
            future.result(timeout=60)
    for owner in owners:
        state = dream_turns.dream_store.state_ref(database, owner)
        lease = state.get().to_dict()['lease']
        assert lease['minute_hold'] is None and len(lease['turn_receipts']) == 1
        assert lease['budget_charge_usd'] == pytest.approx(0.0001)
        assert state.collection('spend').document(now.date().isoformat()).get().to_dict()['observed_usd'] == (
            pytest.approx(0.0001)
        )
    # 80 input + 20 output at 5x, for each of twenty turns.
    rows = [dream_turns.headroom_ref(database, shard).get().to_dict() or {} for shard in range(64)]
    assert all(row.get('tokens', 0) >= 0 for row in rows)
    assert sum(row.get('tokens', 0) for row in rows) == 20 * 180
