"""Sync state has exactly one explicit, known runtime stage."""

from unittest.mock import MagicMock

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from database import sync_dead_letters, sync_jobs, sync_ledger
from utils.sync import backfill, stage as sync_stage


@pytest.mark.parametrize('value', [None, 'unexpected'], ids=['missing', 'unknown'])
def test_ambiguous_stage_retries_and_cannot_address_sync_state(monkeypatch, caplog, value):
    if value is None:
        monkeypatch.delenv('OMI_ENV_STAGE', raising=False)
    else:
        monkeypatch.setenv('OMI_ENV_STAGE', value)
    client = MagicMock()

    for operation in (
        lambda: sync_jobs._key('sync_job:job'),
        lambda: backfill._key('sync_backfill:inflight:user'),
        lambda: sync_ledger._ledger_ref(client, 'user', 'content'),
        lambda: sync_dead_letters._doc_ref(client, 'job'),
        sync_stage.production_stage,
        sync_stage.nonproduction_stage,
    ):
        with pytest.raises(sync_stage.InvalidSyncStage):
            operation()
    assert client.mock_calls == []
    assert 'event=sync_runtime_stage outcome=invalid_config' in caplog.text

    app = FastAPI(dependencies=[Depends(sync_stage.require_http_stage)])

    @app.post('/sync-probe')
    def probe():
        raise AssertionError('ambiguous stage reached the handler')

    response = TestClient(app).post('/sync-probe')
    assert response.status_code == 503


@pytest.mark.parametrize('value', ['prod', 'dev', 'local', 'offline'])
def test_known_stages_choose_only_their_own_names(monkeypatch, value):
    monkeypatch.setenv('OMI_ENV_STAGE', value)
    expected_key = 'sync_job:job' if value == 'prod' else f'{value}:sync_job:job'
    expected_collection = 'sync_content_ledger' if value == 'prod' else f'sync_content_ledger_{value}'
    assert sync_stage.current_stage() == value
    assert sync_jobs._key('sync_job:job') == expected_key
    assert backfill._key('sync_job:job') == expected_key
    client = MagicMock()
    sync_ledger._ledger_ref(client, 'user', 'content')
    assert client.collection('users').document('user').collection.call_args.args == (expected_collection,)
    sync_dead_letters._doc_ref(client, 'job')
    expected_dead_letters = 'sync_dead_letters' if value == 'prod' else f'sync_dead_letters_{value}'
    assert client.collection.call_args.args == (expected_dead_letters,)
    assert sync_stage.nonproduction_stage() is (value != 'prod')
    assert sync_stage.production_stage() is (value == 'prod')
    assert sync_stage.require_http_stage() is None
