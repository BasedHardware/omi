"""In-memory CAS seam; the real dedicated retry state machine remains in use."""

from copy import deepcopy
from threading import RLock
from types import SimpleNamespace

import pytest

from database.batch_final_pass_retry import COUNTER_SHARDS, FinalPassRetries, terminal_plan
from utils.conversations import final_pass_retry as retry


@pytest.fixture
def retry_state(monkeypatch):
    class Rows(FinalPassRetries):
        def __init__(self):
            self.rows = {}
            self.counters = {}
            self.lock = RLock()

        def _mutate(self, key, operation):
            with self.lock:
                new, result = operation(deepcopy(self.rows.get(key)))
                if new is not None:
                    self.rows[key] = deepcopy(new)
                return result

        def take_terminal(self, key, token):
            # Production's pure two-document plan under the same atomic seam.
            with self.lock:
                shard = str(int(key[:2], 16) % COUNTER_SHARDS)
                plan = terminal_plan(self.rows.get(key), self.counters.get(shard, {}), token)
                if plan is None:
                    return False
                self.rows[key], self.counters[shard] = deepcopy(plan)
                return True

        def terminal_counts(self):
            with self.lock:
                return deepcopy(self.counters)

        def due(self, *, now, limit=100):
            return [
                SimpleNamespace(id=key, to_dict=lambda row=row: deepcopy(row))
                for key, row in list(self.rows.items())
                if row.get('repair_after', float('inf')) <= now
            ][:limit]

    store, wakes, clock = Rows(), [], [1000.0]
    from tests.unit import test_batch_final_pass
    from utils.observability import speaker_retry_terminal as metrics

    monkeypatch.setattr(test_batch_final_pass, '_retry_counter_snapshot', store.terminal_counts)
    monkeypatch.setattr(metrics, 'TERMINALS', metrics.RetryTerminals())
    monkeypatch.setattr(retry, '_store', lambda: store)
    monkeypatch.setattr(retry, '_now', lambda: clock[0])
    monkeypatch.setattr(retry, '_exists', lambda *args: False)
    monkeypatch.setattr(retry, '_binding', lambda: {'queue': 'synthetic-queue'})
    monkeypatch.setattr(retry, '_wake', lambda key, row: wakes.append((key, deepcopy(row))))
    return SimpleNamespace(store=store, rows=store.rows, wakes=wakes, clock=clock)
