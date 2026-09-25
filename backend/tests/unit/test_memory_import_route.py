import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import pytest  # noqa: E402

from database.memory_imports import MemoryImportIngestResult  # noqa: E402
from models.memory_imports import (  # noqa: E402
    MemoryImportBatchItem,
    MemoryImportBatchRequest,
    MemoryImportBatchResponse,
)
from routers import memories as mem_mod  # noqa: E402


class _Capture:
    def __init__(self):
        self.observations = []
        self.persisted = False

    def observe(self, lane, payload):
        self.observations.append((lane, payload))

    def persist(self):
        self.persisted = True


class _CaptureFactory:
    capture = _Capture()

    @classmethod
    def from_environ(cls, **_kwargs):
        cls.capture = _Capture()
        return cls.capture


@pytest.mark.asyncio
async def test_memory_import_route_returns_the_ingest_response(monkeypatch):
    request = MemoryImportBatchRequest(
        source_type='local_files',
        import_run_id='run-local-files-1',
        items=[MemoryImportBatchItem(title='Local profile', snippet='267 files indexed')],
    )
    expected = MemoryImportBatchResponse(
        run_id='run-local-files-1',
        artifacts_received=1,
        artifacts_created=1,
        artifacts_deduped=0,
    )

    async def fake_run_blocking(_executor, function, uid, received_request, *, db_client):
        assert function is mem_mod.ingest_memory_import_batch
        assert uid == 'uid-1'
        assert received_request is request
        assert db_client is fake_db
        return MemoryImportIngestResult(response=expected)

    fake_db = object()
    monkeypatch.setattr(mem_mod.db_client_module, 'db', fake_db)
    monkeypatch.setattr(mem_mod, 'run_blocking', fake_run_blocking)
    monkeypatch.setattr(mem_mod, 'SurfaceParityCapture', _CaptureFactory)

    response = await mem_mod.create_memory_import_batch(request=request, uid='uid-1')

    assert response == expected
    assert _CaptureFactory.capture.persisted
    assert _CaptureFactory.capture.observations[-1] == (
        'inbound',
        {'type': 'memory_import_result', **expected.model_dump(mode='json')},
    )
