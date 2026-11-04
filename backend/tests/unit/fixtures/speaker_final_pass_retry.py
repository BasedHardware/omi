"""In-memory CAS seam; the real dedicated retry state machine remains in use."""

from copy import deepcopy
from threading import RLock
from types import SimpleNamespace

import pytest

from database.batch_final_pass_retry import FinalPassRetries
from utils.conversations import final_pass_retry as retry


@pytest.fixture
def retry_state(monkeypatch):
    class Rows(FinalPassRetries):
        def __init__(self):
            self.rows = {}
            self.lock = RLock()

        def _mutate(self, key, operation):
            with self.lock:
                new, result = operation(deepcopy(self.rows.get(key)))
                if new is not None:
                    self.rows[key] = deepcopy(new)
                return result

        def due(self, *, now, limit=100):
            return [
                SimpleNamespace(id=key, to_dict=lambda row=row: deepcopy(row))
                for key, row in list(self.rows.items())
                if row.get('repair_after', float('inf')) <= now
            ][:limit]

    store, wakes, clock = Rows(), [], [1000.0]
    monkeypatch.setattr(retry, '_store', lambda: store)
    monkeypatch.setattr(retry, '_now', lambda: clock[0])
    monkeypatch.setattr(retry, '_exists', lambda *args: False)
    monkeypatch.setattr(retry, '_binding', lambda: {'queue': 'synthetic-queue'})
    monkeypatch.setattr(retry, '_wake', lambda key, row: wakes.append((key, deepcopy(row))))
    return SimpleNamespace(store=store, rows=store.rows, wakes=wakes, clock=clock)
