"""Verify the enrichment dispatcher accepts Go's summary repair outbox row."""

import json
from pathlib import Path
from unittest.mock import Mock

from utils import cloud_tasks
from utils.enrichment import outbox


def test_canonical_dispatcher_accepts_go_summary_repair_wake(monkeypatch):
    path = (
        Path(__file__).resolve().parents[3]
        / 'backend-go/internal/adapters/finalizationdocs/testdata/summary_repair_wake.json'
    )
    row = json.loads(path.read_text(encoding='utf-8'))
    enqueue = Mock()
    monkeypatch.setattr(cloud_tasks, 'enqueue_named_task', enqueue)

    outbox.wake_row(row)

    dispatch = row['dispatch']
    key = row['document_id']
    enqueue.assert_called_once_with(
        dispatch['queue'],
        dispatch['handler'],
        f'sr-{key}-bound-repair-3',
        {'kind': 'sync_reprocess', 'key': key, 'task_token': 'bound'},
        audience=dispatch['audience'],
        invoker_sa=dispatch['invoker_sa'],
        schedule_at=2000,
    )
