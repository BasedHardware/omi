import asyncio
import signal
import time
import os
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from prometheus_client import CollectorRegistry

from diarizer.batch_pipeline_runtime import (
    RuntimeState,
    SynchronizedWorker,
    health_server,
    supervise,
    run_process,
    main,
)
from utils.batch_pipeline.errors import FatalGpuError
from utils.batch_pipeline.stage_timings import StageTimings

def test_runtime_state_healthy():
    state = RuntimeState()
    assert state.healthy() is True

def test_runtime_state_unhealthy():
    state = RuntimeState()
    state.ticked_at = time.monotonic() - 61
    assert state.healthy() is False

def test_synchronized_worker_process_batch_success():
    worker_mock = MagicMock()
    worker_mock.process_batch.return_value = "batch_result"

    sync_mock = MagicMock()

    sync_worker = SynchronizedWorker(worker=worker_mock, synchronize=sync_mock)

    items = []
    result = sync_worker.process_batch(items)

    assert result == "batch_result"
    worker_mock.process_batch.assert_called_once_with(items)
    sync_mock.assert_called_once()

def test_synchronized_worker_unavailable_raises():
    worker_mock = MagicMock()
    sync_worker = SynchronizedWorker(worker=worker_mock)
    sync_worker._unavailable = True

    with pytest.raises(FatalGpuError, match="GPU chain unavailable"):
        sync_worker.process_batch([])

def test_synchronized_worker_fatal_error_quarantines():
    worker_mock = MagicMock()

    class FakeCudaError(Exception):
        pass

    worker_mock.process_batch.side_effect = FakeCudaError("CUDA error")

    fatal_callback = MagicMock()
    sync_worker = SynchronizedWorker(worker=worker_mock, on_fatal=fatal_callback)

    with patch('diarizer.batch_pipeline_runtime.is_fatal_cuda_error', return_value=True):
        with pytest.raises(FatalGpuError, match="fatal CUDA error"):
            sync_worker.process_batch([])

    assert sync_worker._unavailable is True
    fatal_callback.assert_called_once()

@pytest.mark.asyncio
async def test_supervise_happy_path():
    pump_mock = AsyncMock()
    state = RuntimeState()
    stop_event = asyncio.Event()

    async def side_effect(*args):
        # Allow pump to run briefly, then stop to avoid blocking test forever
        await asyncio.sleep(0.01)

    pump_mock.run.side_effect = side_effect

    await supervise(pump_mock, state, stop_event)

    pump_mock.run.assert_called_once_with(stop_event)
    assert state.ready is False

@pytest.mark.asyncio
async def test_supervise_fatal_state():
    pump_mock = AsyncMock()
    state = RuntimeState()
    state.fatal = True
    stop_event = asyncio.Event()

    async def side_effect(*args):
        await asyncio.sleep(0.01)

    pump_mock.run.side_effect = side_effect

    with pytest.raises(RuntimeError, match="GPU chain quarantined"):
        await supervise(pump_mock, state, stop_event)

def test_health_server_responses():
    state = RuntimeState()
    registry = CollectorRegistry()

    server = health_server(state, registry, port=0) # 0 lets OS pick random port

    try:
        # State: Unready
        assert state.ready is False

        # Test Handler directly since ThreadingHTTPServer is started in a daemon thread
        handler_class = server.RequestHandlerClass

        # Instead of full Handler init which does parsing, just instantiate bypass it
        handler = handler_class.__new__(handler_class)
        handler.server = server

        with patch.object(handler, 'send_response') as mock_send_response, \
             patch.object(handler, 'send_header') as mock_send_header, \
             patch.object(handler, 'end_headers') as mock_end_headers:

            class FakeWfile:
                def __init__(self):
                    self.content = b''
                def write(self, b):
                    self.content += b
            handler.wfile = FakeWfile()
            handler.wfile = FakeWfile()
            handler.path = '/health'

            # Act - healthy
            state.ticked_at = time.monotonic()
            handler.do_GET()

            # Assert
            mock_send_response.assert_called_with(200)
            assert handler.wfile.content == b'ok'

            # Act - not healthy (ticked long ago)
            mock_send_response.reset_mock()
            handler.wfile = FakeWfile()
            state.ticked_at = time.monotonic() - 70
            handler.do_GET()

            # Assert
            mock_send_response.assert_called_with(503)
            assert handler.wfile.content == b'unavailable'

            # Act - /ready endpoint when not ready
            mock_send_response.reset_mock()
            handler.wfile = FakeWfile()
            state.ticked_at = time.monotonic()
            handler.path = '/ready'
            handler.do_GET()

            # Assert
            mock_send_response.assert_called_with(503)
            assert handler.wfile.content == b'unavailable'

            # Act - /ready endpoint when ready
            state.ready = True
            mock_send_response.reset_mock()
            handler.wfile = FakeWfile()
            handler.do_GET()

            # Assert
            mock_send_response.assert_called_with(200)
            assert handler.wfile.content == b'ok'

            # Act - /ready endpoint when stopping
            state.stopping = True
            mock_send_response.reset_mock()
            handler.wfile = FakeWfile()
            handler.do_GET()

            # Assert
            mock_send_response.assert_called_with(503)

            # Act - Not found
            mock_send_response.reset_mock()
            handler.wfile = FakeWfile()
            handler.path = '/notfound'
            handler.do_GET()

            # Assert
            mock_send_response.assert_called_with(404)
            assert handler.wfile.content == b'not found'

            # Act - Metrics
            with patch('diarizer.batch_pipeline_runtime.generate_latest', return_value=b'metrics_data'):
                mock_send_response.reset_mock()
                handler.wfile = FakeWfile()
                handler.path = '/metrics'
                handler.do_GET()

                # Assert
                mock_send_response.assert_called_with(200)
                assert handler.wfile.content == b'metrics_data'
    finally:
        server.shutdown()
        server.server_close()

@patch('diarizer.batch_pipeline_runtime.provider_config')
@patch('diarizer.batch_pipeline_runtime.load_worker')
@patch('diarizer.batch_pipeline_runtime.Pump')
@pytest.mark.asyncio
async def test_run_process_success(pump_mock, load_worker_mock, config_mock):
    config = MagicMock()
    config.pool_kind = 'dedicated_batch'
    config.batch_size = 1
    config.max_unit_seconds = 10
    config_mock.return_value = config

    worker = MagicMock()
    load_worker_mock.return_value = worker

    pump_instance = AsyncMock()
    # supervise uses pump.run
    pump_instance.run.side_effect = lambda event: event.set()
    pump_mock.return_value = pump_instance

    store = MagicMock()
    artifacts = MagicMock()
    registry = CollectorRegistry()
    state = RuntimeState()

    # We must patch asyncio.get_running_loop().add_signal_handler
    # since signals can only be caught in main thread
    with patch('asyncio.get_running_loop') as mock_loop:
        loop_instance = MagicMock()
        mock_loop.return_value = loop_instance

        # We need to mock os.environ because the code creates QueueMetrics with it
        with patch.dict(os.environ, {'BATCH_PIPELINE_WORKER_RELEASE': 'test', 'POD_NAMESPACE': 'test'}):
            with patch('utils.batch_pipeline.compute_client.shadow_from_env') as shadow_mock:
                shadow_mock.return_value.shadow_recover.return_value = None

                await run_process(store, artifacts, registry, state)

    load_worker_mock.assert_called_once()
    pump_instance.run.assert_called_once()
    assert state.stopping is False  # Stopping is only set on signal

@patch('diarizer.batch_pipeline_runtime.provider_config')
@pytest.mark.asyncio
async def test_run_process_invalid_pool(config_mock):
    config = MagicMock()
    config.pool_kind = 'other_pool'
    config_mock.return_value = config

    store = MagicMock()
    artifacts = MagicMock()
    registry = CollectorRegistry()
    state = RuntimeState()

    with pytest.raises(ValueError, match="requires the dedicated batch GPU pool"):
        await run_process(store, artifacts, registry, state)

@patch('diarizer.batch_pipeline_runtime.os.getenv')
def test_main_disabled(getenv_mock):
    getenv_mock.return_value = 'false'

    with patch('diarizer.batch_pipeline_runtime.logger.info') as logger_mock:
        main()

    logger_mock.assert_called_with('event=batch_worker outcome=disabled')

@patch('diarizer.batch_pipeline_runtime.os.environ', {'BATCH_PIPELINE_WORKER_ENABLED': 'true', 'BATCH_PIPELINE_NAMESPACE': 'test', 'FIRESTORE_EMULATOR_HOST': 'localhost:8080', 'BUCKET_BATCH_PIPELINE': 'bucket'})
@patch('diarizer.batch_pipeline_runtime.os.getenv')
@patch('diarizer.batch_pipeline_runtime.configure_rollout_runtime')
@patch('diarizer.batch_pipeline_runtime.create_storage_client')
@patch('diarizer.batch_pipeline_runtime.create_artifact_store')
@patch('diarizer.batch_pipeline_runtime.health_server')
@patch('diarizer.batch_pipeline_runtime.run_process')
@patch('diarizer.batch_pipeline_runtime.asyncio.run')
@patch('diarizer.batch_pipeline_runtime.shutdown_executors')
@patch('diarizer.batch_pipeline_runtime.FirestoreStore')
@patch('diarizer.batch_pipeline_runtime.shadow_from_env')
def test_main_enabled(shadow_mock, store_mock, shutdown_mock, run_mock, run_process_mock, server_mock, artifact_mock, storage_mock, rollout_mock, getenv_mock):
    # run_mock doesn't actually run the coroutine, we need to mock run_process too
    # to avoid the 'coroutine was never awaited' warning when run_process() is called but its result is passed to the mock
    getenv_mock.side_effect = lambda k, d=None: {'BATCH_PIPELINE_WORKER_ENABLED': 'true', 'FIRESTORE_EMULATOR_HOST': 'localhost:8080', 'PORT': '8080', 'ENCRYPTION_SECRET': ''}.get(k, d)

    server_instance = MagicMock()
    server_mock.return_value = server_instance

    main()

    rollout_mock.assert_called_once()
    run_mock.assert_called_once()
    server_instance.shutdown.assert_called_once()
    server_instance.server_close.assert_called_once()
    shutdown_mock.assert_called_once()
