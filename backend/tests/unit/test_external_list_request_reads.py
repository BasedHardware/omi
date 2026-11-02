"""Request histogram uses the SDK ledger amounts across executor context copies."""

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from database.firestore_document_probe import _record
from utils.executors import db_executor, run_blocking
from utils.observability.external_lists import EXTERNAL_LIST_READS, ExternalListMetricsMiddleware

PATH = '/v1/dev/user/action-items'


def sample(name):
    EXTERNAL_LIST_READS.labels(route=PATH)
    return next(
        value.value
        for metric in EXTERNAL_LIST_READS.collect()
        for value in metric.samples
        if value.name == name and value.labels.get('route') == PATH
    )


def record(amount=1):
    _record(('users', 'synthetic-owner', 'action_items'), True, amount, kind='query')


@pytest.mark.parametrize('status', [200, 403, 429, 500])
def test_histogram_counts_reads_once_including_failures_and_excludes_background(status):
    app = FastAPI()
    app.add_middleware(ExternalListMetricsMiddleware)

    @app.get(PATH)
    async def endpoint(background_tasks: BackgroundTasks):
        record(2)  # includes billable missing-document, floor and aggregation amounts
        await run_blocking(db_executor, record, 5)
        if status != 200:
            raise HTTPException(status)
        background_tasks.add_task(record, 1000)
        return []

    before_sum = sample('omi_external_list_firestore_reads_per_request_sum')
    before_count = sample('omi_external_list_firestore_reads_per_request_count')
    assert TestClient(app).get(PATH).status_code == status
    assert sample('omi_external_list_firestore_reads_per_request_sum') - before_sum == 7
    assert sample('omi_external_list_firestore_reads_per_request_count') - before_count == 1
    assert EXTERNAL_LIST_READS._labelnames == ('route',)
    # The copied background holder was revoked at the final response body.
    record(99)
    assert sample('omi_external_list_firestore_reads_per_request_sum') - before_sum == 7


def test_zero_reads_and_opt_out(monkeypatch):
    app = FastAPI()
    app.add_middleware(ExternalListMetricsMiddleware)

    @app.get(PATH)
    def endpoint():
        return []

    before = sample('omi_external_list_firestore_reads_per_request_count')
    TestClient(app).get(PATH)
    assert sample('omi_external_list_firestore_reads_per_request_count') == before + 1
    monkeypatch.setenv('OMI_EXTERNAL_LIST_METRICS_ENABLED', 'false')
    TestClient(app).get(PATH)
    assert sample('omi_external_list_firestore_reads_per_request_count') == before + 1
