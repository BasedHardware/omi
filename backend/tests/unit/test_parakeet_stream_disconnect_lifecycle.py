"""Regression: a clean Parakeet /v3/stream client hang-up is a lifecycle event.

Prod signature (Loop S, 2026-09, ~42/30m on the parakeet container)::

    ERROR:main:v3/stream error: Cannot call "receive" once a disconnect
    message has been received.

Root cause: ``main.stream_transcribe`` dispatched on message content only
(``bytes`` / ``text``). Starlette delivers a client hang-up as a normal
``websocket.disconnect`` message, so the dispatch dropped it, the loop
re-armed ``receive()``, and Starlette answered with the generic
``RuntimeError('Cannot call "receive" once a disconnect message has been
received.')`` — every clean client disconnect was logged as a server fault.

The fix classifies the in-band disconnect message before the content
dispatch and breaks to the normal finalization path (flush → cleanup →
lease release), mirroring every other backend websocket receive loop
(`routers/listen/receiver.py`, `routers/chat.py`,
`routers/omni_relay.py`, and this repo's own stack-harness stub
`testing/listen_pusher_stack/parakeet_stub.py`).

RED on parent commit: tests asserting "no v3/stream server-fault log after
a client disconnect" fail on the unfixed handler (it logs the RuntimeError),
and the labeled static tripwire fails because the source has no disconnect
classification. The remaining tests are green-on-both lifecycle-contract
controls: they pin the admission, relay, idle, finalize, fault-separation,
and teardown-ordering behavior the fix must preserve.
"""

import asyncio
import logging
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

os.environ.setdefault("PARAKEET_MODEL", "nvidia/parakeet-tdt-0.6b-v3")
os.environ.setdefault("PARAKEET_DEVICE", "cpu")
os.environ.setdefault("PARAKEET_TORCH_COMPILE", "false")
os.environ.setdefault("PARAKEET_CUDA_GRAPHS", "false")
os.environ.setdefault("PARAKEET_INFERENCE_MODE", "nemo")

PARAKEET_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../parakeet"))
MAIN_SOURCE_PATH = os.path.join(PARAKEET_DIR, "main.py")


@pytest.fixture(scope="module", autouse=True)
def _parakeet_modules():
    """Load the parakeet subservice modules fresh against faked torch/nemo.

    Same sanctioned isolation as ``tests/unit/test_parakeet_endpoints.py``:
    torch and nemo are not installed in the test environment, the parakeet
    modules import them at top level, so fakes are installed via
    ``stub_modules`` and each module is exec'd fresh inside the block. The
    fixture evicts everything on teardown so nothing leaks to later files.
    """
    os.environ["PARAKEET_STREAM_MODEL"] = ""
    if str(PARAKEET_DIR) not in sys.path:
        sys.path.insert(0, PARAKEET_DIR)

    torch_fake = AutoMockModule("torch")
    torch_fake.cuda.is_available.return_value = False
    torch_fake.cuda.memory_allocated.return_value = 0
    _torch_props = MagicMock()
    _torch_props.total_memory = 16 * 1024**3
    torch_fake.cuda.get_device_properties.return_value = _torch_props
    torch_fake.cuda.empty_cache = MagicMock()
    torch_fake.cuda.mem_get_info.return_value = (10 * 1024**3, 16 * 1024**3)
    torch_fake.inference_mode = lambda: (lambda fn: fn)
    torch_fake.compile = lambda m: m
    torch_fake.backends.cudnn = MagicMock()

    nemo_asr_fake = AutoMockModule("nemo.collections.asr")
    nemo_fake = AutoMockModule("nemo")
    nemo_fake.collections.asr = nemo_asr_fake
    nemo_collections_fake = AutoMockModule("nemo.collections")
    nemo_collections_fake.asr = nemo_asr_fake

    fakes = {
        "torch": torch_fake,
        "nemo": nemo_fake,
        "nemo.collections": nemo_collections_fake,
        "nemo.collections.asr": nemo_asr_fake,
    }
    with stub_modules(fakes):
        gpu_worker = load_module_fresh("gpu_worker", os.path.join(PARAKEET_DIR, "gpu_worker.py"))
        batch_engine = load_module_fresh("batch_engine", os.path.join(PARAKEET_DIR, "batch_engine.py"))
        load_module_fresh("speaker_math", os.path.join(PARAKEET_DIR, "speaker_math.py"))
        load_module_fresh("transcribe", os.path.join(PARAKEET_DIR, "transcribe.py"))
        load_module_fresh("stream_handler", os.path.join(PARAKEET_DIR, "stream_handler.py"))
        load_module_fresh("main", MAIN_SOURCE_PATH)

        g = sys.modules[__name__]
        g.GPUWorker = gpu_worker.GPUWorker
        g.AudioDurationExceededError = gpu_worker.AudioDurationExceededError
        g.BatchEngine = batch_engine.BatchEngine
        g.QueueFullError = batch_engine.QueueFullError
        g.main_module = sys.modules["main"]
        yield


def _make_session(feed_segments=None, flush_segments=None):
    session = MagicMock()
    session.feed = AsyncMock(return_value=list(feed_segments or []))
    session.flush = AsyncMock(return_value=list(flush_segments or []))
    session.cleanup = MagicMock()
    return session


def _make_app(
    gpu_ready=True,
    nim_mode=False,
    fatal_cuda_reason=None,
    admission="ok",
    session=None,
):
    """Fresh app with the stream path wired to fakes.

    ``admission``: 'ok' admits with a tracked lease, 'none' leaves the
    controller unset (infrastructure outage), otherwise a SimpleNamespace
    returned by ``try_acquire`` (e.g. lease=None, reason='allocation_rejected').
    """
    mod = sys.modules[__name__].main_module
    mod.start_time = 0.0

    if nim_mode:
        mod.gpu_worker = None
        mod.batch_engine = None
    else:
        mock_gpu = MagicMock(spec=GPUWorker)
        mock_gpu.is_ready = gpu_ready
        mock_gpu.fatal_cuda_reason = fatal_cuda_reason
        mock_engine = MagicMock(spec=BatchEngine)
        mock_engine._pending = []
        mod.gpu_worker = mock_gpu
        mod.batch_engine = mock_engine

    lease = MagicMock()
    if admission == "ok":
        controller = MagicMock()
        controller.try_acquire.return_value = SimpleNamespace(lease=lease, reason="admitted")
    elif admission == "none":
        controller = None
        lease = None
    else:
        controller = MagicMock()
        controller.try_acquire.return_value = admission
        lease = admission.lease

    mod.stream_admission = controller

    if session is None:
        session = _make_session()
    return mod, session, lease


def _v3_error_records(caplog):
    return [r for r in caplog.records if "v3/stream error" in r.getMessage()]


def _counter_value(counter, *labels):
    child = counter._metrics.get(labels)  # type: ignore[reportAttributeAccessIssue]  # prometheus introspection
    if child is None:
        return 0.0
    return child._value.get()  # type: ignore[reportAttributeAccessIssue]  # prometheus introspection


class TestAdmissionArms:
    def test_not_ready_gpu_rejects_with_1013_and_error_metric(self):
        mod, _, _ = _make_app(gpu_ready=False)
        before = _counter_value(mod.REQUESTS_TOTAL, "v3_stream", "error")

        client = TestClient(mod.app, raise_server_exceptions=False)
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/v3/stream") as websocket:
                websocket.receive_json()

        assert exc_info.value.code == 1013
        assert _counter_value(mod.REQUESTS_TOTAL, "v3_stream", "error") == before + 1

    def test_allocation_rejected_reason_surfaces_as_1013_close_and_metric(self):
        mod, _, _ = _make_app(admission=SimpleNamespace(lease=None, reason="allocation_rejected"))
        before = _counter_value(mod.REQUESTS_TOTAL, "v3_stream", "allocation_rejected")

        client = TestClient(mod.app, raise_server_exceptions=False)
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/v3/stream") as websocket:
                websocket.receive_json()

        assert exc_info.value.code == 1013
        assert _counter_value(mod.REQUESTS_TOTAL, "v3_stream", "allocation_rejected") == before + 1

    def test_admission_unavailable_closes_1011_and_logs_infra_fault(self, caplog):
        mod, _, _ = _make_app(admission="none")

        client = TestClient(mod.app, raise_server_exceptions=False)
        with caplog.at_level(logging.ERROR):
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/v3/stream") as websocket:
                    websocket.receive_json()

        assert exc_info.value.code == 1011
        infra_faults = [r for r in caplog.records if "v3/stream admission unavailable" in r.getMessage()]
        assert len(infra_faults) == 1

    def test_nim_mode_streams_without_gpu_worker(self):
        mod, session, _ = _make_app(nim_mode=True)
        session.feed = AsyncMock(return_value=[{"text": "nim segment", "start": 0.0, "end": 0.1}])

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session):
            with client.websocket_connect("/v3/stream") as websocket:
                assert websocket.receive_json() == {"type": "ready"}
                websocket.send_bytes(b"\x00\x00")
                assert websocket.receive_json()["text"] == "nim segment"
                websocket.close(code=1001)

        session.feed.assert_called_once_with(b"\x00\x00")

    def test_admission_rejection_does_not_increment_active_streams(self):
        mod, _, _ = _make_app(admission=SimpleNamespace(lease=None, reason="capacity_full"))
        baseline = mod.ACTIVE_STREAMS._value.get()  # type: ignore[reportAttributeAccessIssue]  # prometheus introspection

        client = TestClient(mod.app, raise_server_exceptions=False)
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/v3/stream") as websocket:
                websocket.receive_json()

        assert mod.ACTIVE_STREAMS._value.get() == baseline  # type: ignore[reportAttributeAccessIssue]  # prometheus introspection


class TestReadyHandshake:
    def test_ready_frame_is_first_message_after_admission(self):
        mod, session, _ = _make_app()

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session):
            with client.websocket_connect("/v3/stream") as websocket:
                assert websocket.receive_json() == {"type": "ready"}
                websocket.close(code=1001)

    def test_stream_session_receives_query_parameters(self):
        mod, session, _ = _make_app()

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session) as stream_session:
            with client.websocket_connect("/v3/stream?sample_rate=8000&vad_threshold=0.5&hangover_s=0.3") as websocket:
                assert websocket.receive_json() == {"type": "ready"}
                websocket.close(code=1001)

        _, kwargs = stream_session.call_args
        assert kwargs["sample_rate"] == 8000
        assert kwargs["vad_threshold"] == 0.5
        assert kwargs["hangover_s"] == 0.3

    def test_query_defaults_construct_minimal_session(self):
        mod, session, _ = _make_app()

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session) as stream_session:
            with client.websocket_connect("/v3/stream") as websocket:
                assert websocket.receive_json() == {"type": "ready"}
                websocket.close(code=1001)

        _, kwargs = stream_session.call_args
        assert kwargs["sample_rate"] == 16000
        assert kwargs["vad_threshold"] is None
        assert kwargs["hangover_s"] is None

    def test_full_happy_session_emits_no_error_logs(self, caplog):
        mod, session, _ = _make_app()
        session.feed = AsyncMock(return_value=[{"text": "hello", "start": 0.0, "end": 0.2}])

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session):
            with caplog.at_level(logging.ERROR):
                with client.websocket_connect("/v3/stream") as websocket:
                    assert websocket.receive_json() == {"type": "ready"}
                    websocket.send_bytes(b"\x00\x00")
                    websocket.send_text("finalize")
                    assert websocket.receive_json()["text"] == "hello"

        assert _v3_error_records(caplog) == []


class TestAudioRelay:
    def test_single_audio_feed_relays_segment_shape_unchanged(self):
        mod, session, _ = _make_app()
        segment = {
            "id": "seg-1",
            "speaker": "SPEAKER_00",
            "start": 0.0,
            "end": 0.5,
            "text": "relay me",
            "is_user": False,
            "person_id": None,
        }
        session.feed = AsyncMock(return_value=[segment])

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session):
            with client.websocket_connect("/v3/stream") as websocket:
                assert websocket.receive_json() == {"type": "ready"}
                websocket.send_bytes(b"\x01\x02")
                assert websocket.receive_json() == segment
                websocket.close(code=1001)

        session.feed.assert_called_once_with(b"\x01\x02")

    def test_two_audio_feeds_relay_segments_in_order(self):
        mod, session, _ = _make_app()
        feeds = [
            [{"text": "first", "start": 0.0, "end": 0.1}],
            [{"text": "second", "start": 0.1, "end": 0.2}],
        ]
        session.feed = AsyncMock(side_effect=[feeds[0], feeds[1]])

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session):
            with client.websocket_connect("/v3/stream") as websocket:
                assert websocket.receive_json() == {"type": "ready"}
                websocket.send_bytes(b"\x01")
                websocket.send_bytes(b"\x02")
                assert websocket.receive_json()["text"] == "first"
                assert websocket.receive_json()["text"] == "second"
                websocket.close(code=1001)

        assert session.feed.await_count == 2

    def test_feed_returning_no_segments_keeps_loop_serving(self):
        mod, session, _ = _make_app()
        session.feed = AsyncMock(side_effect=[[], [{"text": "after empty", "start": 0.0, "end": 0.1}]])

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session):
            with client.websocket_connect("/v3/stream") as websocket:
                assert websocket.receive_json() == {"type": "ready"}
                websocket.send_bytes(b"\x01")
                websocket.send_bytes(b"\x02")
                assert websocket.receive_json()["text"] == "after empty"
                websocket.close(code=1001)

        assert session.feed.await_count == 2

    def test_two_concurrent_streams_are_both_served(self):
        mod, _, _ = _make_app()
        first = _make_session(feed_segments=[{"text": "one", "start": 0.0, "end": 0.1}])
        second = _make_session(feed_segments=[{"text": "two", "start": 0.0, "end": 0.1}])

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", side_effect=[first, second]):
            with client.websocket_connect("/v3/stream") as ws_one:
                with client.websocket_connect("/v3/stream") as ws_two:
                    assert ws_one.receive_json() == {"type": "ready"}
                    assert ws_two.receive_json() == {"type": "ready"}
                    ws_one.send_bytes(b"\x01")
                    ws_two.send_bytes(b"\x02")
                    assert ws_one.receive_json()["text"] == "one"
                    assert ws_two.receive_json()["text"] == "two"
                    ws_one.close(code=1001)
                    ws_two.close(code=1001)

        first.feed.assert_awaited_once_with(b"\x01")
        second.feed.assert_awaited_once_with(b"\x02")


class TestReceiveIdleTimeouts:
    def test_session_survives_receive_idle_timeouts(self, caplog):
        mod, session, _ = _make_app()

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "_WS_RECEIVE_TIMEOUT", 0.05), patch.object(mod, "StreamSession", return_value=session):
            with caplog.at_level(logging.ERROR):
                with client.websocket_connect("/v3/stream") as websocket:
                    assert websocket.receive_json() == {"type": "ready"}
                    websocket.send_text("ping-not-audio")
                    websocket.send_text("finalize")

        assert _v3_error_records(caplog) == []

    def test_audio_still_served_after_idle_timeouts(self):
        mod, session, _ = _make_app()
        session.feed = AsyncMock(return_value=[{"text": "post idle", "start": 0.0, "end": 0.1}])

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "_WS_RECEIVE_TIMEOUT", 0.05), patch.object(mod, "StreamSession", return_value=session):
            with client.websocket_connect("/v3/stream") as websocket:
                assert websocket.receive_json() == {"type": "ready"}
                websocket.send_text("ping-not-audio")
                websocket.send_bytes(b"\x01")
                assert websocket.receive_json()["text"] == "post idle"
                websocket.close(code=1001)

        session.feed.assert_awaited_once_with(b"\x01")

    def test_disconnect_after_idle_timeouts_is_clean(self, caplog):
        mod, session, _ = _make_app()

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "_WS_RECEIVE_TIMEOUT", 0.05), patch.object(mod, "StreamSession", return_value=session):
            with caplog.at_level(logging.ERROR):
                with client.websocket_connect("/v3/stream") as websocket:
                    assert websocket.receive_json() == {"type": "ready"}
                    websocket.send_text("ping-not-audio")
                    websocket.close(code=1001)

        assert _v3_error_records(caplog) == []


class TestClientDisconnectLifecycle:
    """The prod incident: in-band websocket.disconnect must end the loop."""

    def test_client_disconnect_after_ready_logs_no_server_fault(self, caplog):
        mod, session, _ = _make_app()

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session):
            with caplog.at_level(logging.ERROR):
                with client.websocket_connect("/v3/stream") as websocket:
                    assert websocket.receive_json() == {"type": "ready"}
                    websocket.close(code=1001)

        assert _v3_error_records(caplog) == []

    def test_client_disconnect_never_touches_the_audio_session(self):
        mod, session, _ = _make_app()

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session):
            with client.websocket_connect("/v3/stream") as websocket:
                assert websocket.receive_json() == {"type": "ready"}
                websocket.close(code=1001)

        session.feed.assert_not_called()

    def test_client_disconnect_releases_admission_lease(self):
        mod, _, lease = _make_app()

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=_make_session()):
            with client.websocket_connect("/v3/stream") as websocket:
                assert websocket.receive_json() == {"type": "ready"}
                websocket.close(code=1001)

        lease.release.assert_called_once_with()

    def test_client_disconnect_runs_session_cleanup(self):
        mod, session, _ = _make_app()

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session):
            with client.websocket_connect("/v3/stream") as websocket:
                assert websocket.receive_json() == {"type": "ready"}
                websocket.close(code=1001)

        session.cleanup.assert_called_once_with()

    def test_client_disconnect_still_attempts_final_flush(self):
        mod, session, _ = _make_app()

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session):
            with client.websocket_connect("/v3/stream") as websocket:
                assert websocket.receive_json() == {"type": "ready"}
                websocket.close(code=1001)

        session.flush.assert_awaited_once_with()

    def test_client_disconnect_after_served_audio_logs_no_server_fault(self, caplog):
        mod, session, _ = _make_app()
        session.feed = AsyncMock(return_value=[{"text": "gone soon", "start": 0.0, "end": 0.1}])

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session):
            with caplog.at_level(logging.ERROR):
                with client.websocket_connect("/v3/stream") as websocket:
                    assert websocket.receive_json() == {"type": "ready"}
                    websocket.send_bytes(b"\x01\x02")
                    assert websocket.receive_json()["text"] == "gone soon"
                    websocket.close(code=1001)

        assert _v3_error_records(caplog) == []

    def test_disconnect_after_audio_feeds_exactly_once(self):
        mod, session, _ = _make_app()
        session.feed = AsyncMock(return_value=[{"text": "seg", "start": 0.0, "end": 0.1}])

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session):
            with client.websocket_connect("/v3/stream") as websocket:
                assert websocket.receive_json() == {"type": "ready"}
                websocket.send_bytes(b"\x01")
                websocket.close(code=1001)

        assert session.feed.await_count == 1

    @pytest.mark.parametrize("code", [1000, 1001])
    def test_disconnect_codes_1000_and_1001_are_both_lifecycle(self, code, caplog):
        mod, session, _ = _make_app()

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session):
            with caplog.at_level(logging.ERROR):
                with client.websocket_connect("/v3/stream") as websocket:
                    assert websocket.receive_json() == {"type": "ready"}
                    websocket.close(code=code)

        assert _v3_error_records(caplog) == []

    def test_flush_failure_during_disconnect_still_cleans_session(self, caplog):
        mod, session, _ = _make_app()
        session.flush = AsyncMock(side_effect=RuntimeError("flush exploded"))

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session):
            with caplog.at_level(logging.ERROR):
                with client.websocket_connect("/v3/stream") as websocket:
                    assert websocket.receive_json() == {"type": "ready"}
                    websocket.close(code=1001)

        session.cleanup.assert_called_once_with()
        assert _v3_error_records(caplog) == []

    def test_flush_failure_during_disconnect_still_releases_lease(self):
        mod, session, lease = _make_app()
        session.flush = AsyncMock(side_effect=RuntimeError("flush exploded"))

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session):
            with client.websocket_connect("/v3/stream") as websocket:
                assert websocket.receive_json() == {"type": "ready"}
                websocket.close(code=1001)

        lease.release.assert_called_once_with()

    def test_final_flush_runs_before_lease_release_on_disconnect(self):
        mod, session, lease = _make_app()
        order = []
        session.flush = AsyncMock(side_effect=lambda: order.append("flush") or [])
        lease.release.side_effect = lambda: order.append("release")
        session.cleanup.side_effect = lambda: order.append("cleanup")

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session):
            with client.websocket_connect("/v3/stream") as websocket:
                assert websocket.receive_json() == {"type": "ready"}
                websocket.close(code=1001)

        assert order == ["flush", "cleanup", "release"]

    def test_session_cleanup_runs_before_lease_release_on_disconnect(self):
        mod, session, lease = _make_app()
        order = []
        lease.release.side_effect = lambda: order.append("release")
        session.cleanup.side_effect = lambda: order.append("cleanup")

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session):
            with client.websocket_connect("/v3/stream") as websocket:
                assert websocket.receive_json() == {"type": "ready"}
                websocket.close(code=1001)

        assert order == ["cleanup", "release"]

    def test_flush_runs_before_cleanup_on_disconnect(self):
        mod, session, _ = _make_app()
        order = []
        session.flush = AsyncMock(side_effect=lambda: order.append("flush") or [])
        session.cleanup.side_effect = lambda: order.append("cleanup")

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session):
            with client.websocket_connect("/v3/stream") as websocket:
                assert websocket.receive_json() == {"type": "ready"}
                websocket.close(code=1001)

        assert order == ["flush", "cleanup"]

    def test_bytes_finalize_then_disconnect_stays_clean(self, caplog):
        mod, session, _ = _make_app()

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session):
            with caplog.at_level(logging.ERROR):
                with client.websocket_connect("/v3/stream") as websocket:
                    assert websocket.receive_json() == {"type": "ready"}
                    websocket.send_bytes(b"\x01")
                    websocket.send_text("finalize")
                    websocket.close(code=1001)

        assert _v3_error_records(caplog) == []

    def test_feed_failure_with_buffered_disconnect_still_closes_1011(self):
        mod, session, _ = _make_app()
        session.feed = AsyncMock(side_effect=RuntimeError("decode exploded"))

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session):
            with client.websocket_connect("/v3/stream") as websocket:
                assert websocket.receive_json() == {"type": "ready"}
                websocket.send_bytes(b"\x01")
                websocket.close(code=1001)
                with pytest.raises(WebSocketDisconnect) as exc_info:
                    websocket.receive_json()

        assert exc_info.value.code == 1011
        assert exc_info.value.reason == "stream_initialization_failed"

    def test_second_session_after_disconnect_is_admitted_fresh(self):
        mod, _, _ = _make_app()
        first = _make_session()
        second = _make_session(feed_segments=[{"text": "again", "start": 0.0, "end": 0.1}])

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", side_effect=[first, second]):
            with client.websocket_connect("/v3/stream") as websocket:
                assert websocket.receive_json() == {"type": "ready"}
                websocket.close(code=1001)
            with client.websocket_connect("/v3/stream") as websocket:
                assert websocket.receive_json() == {"type": "ready"}
                websocket.send_bytes(b"\x01")
                assert websocket.receive_json()["text"] == "again"
                websocket.close(code=1001)

        second.feed.assert_awaited_once_with(b"\x01")


class TestFinalizePath:
    def test_finalize_flushes_pending_segments_to_client(self):
        mod, session, _ = _make_app()
        session.flush = AsyncMock(
            return_value=[
                {"text": "tail one", "start": 0.0, "end": 0.1},
                {"text": "tail two", "start": 0.1, "end": 0.2},
            ]
        )

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session):
            with client.websocket_connect("/v3/stream") as websocket:
                assert websocket.receive_json() == {"type": "ready"}
                websocket.send_text("finalize")
                assert websocket.receive_json()["text"] == "tail one"
                assert websocket.receive_json()["text"] == "tail two"

        session.flush.assert_awaited_once_with()

    def test_finalize_empty_flush_sends_nothing_and_stays_clean(self, caplog):
        mod, session, _ = _make_app()

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session):
            with caplog.at_level(logging.ERROR):
                with client.websocket_connect("/v3/stream") as websocket:
                    assert websocket.receive_json() == {"type": "ready"}
                    websocket.send_text("finalize")

        assert _v3_error_records(caplog) == []

    def test_finalize_releases_lease_and_cleans_session(self):
        mod, session, lease = _make_app()

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session):
            with client.websocket_connect("/v3/stream") as websocket:
                assert websocket.receive_json() == {"type": "ready"}
                websocket.send_text("finalize")

        lease.release.assert_called_once_with()
        session.cleanup.assert_called_once_with()

    def test_finalize_logs_no_server_fault(self, caplog):
        mod, session, _ = _make_app()

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session):
            with caplog.at_level(logging.ERROR):
                with client.websocket_connect("/v3/stream") as websocket:
                    assert websocket.receive_json() == {"type": "ready"}
                    websocket.send_text("finalize")

        assert _v3_error_records(caplog) == []

    def test_finalize_with_leading_whitespace_is_not_terminal(self):
        mod, session, _ = _make_app()

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session):
            with client.websocket_connect("/v3/stream") as websocket:
                assert websocket.receive_json() == {"type": "ready"}
                websocket.send_text(" finalize")
                websocket.send_bytes(b"\x01")
                websocket.send_text("finalize")

        session.feed.assert_awaited_once_with(b"\x01")


class TestTextProtocol:
    def test_unrecognized_text_frame_does_not_end_session(self):
        mod, session, _ = _make_app()
        session.feed = AsyncMock(return_value=[{"text": "still up", "start": 0.0, "end": 0.1}])

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session):
            with client.websocket_connect("/v3/stream") as websocket:
                assert websocket.receive_json() == {"type": "ready"}
                websocket.send_text("ping-not-audio")
                websocket.send_bytes(b"\x01")
                assert websocket.receive_json()["text"] == "still up"
                websocket.close(code=1001)

        session.feed.assert_awaited_once_with(b"\x01")

    def test_untyped_message_frame_falls_through_and_keeps_loop(self, caplog):
        mod, session, _ = _make_app()

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session):
            with caplog.at_level(logging.ERROR):
                with client.websocket_connect("/v3/stream") as websocket:
                    assert websocket.receive_json() == {"type": "ready"}
                    websocket.send({"type": "websocket.receive"})
                    websocket.send_text("finalize")

        assert _v3_error_records(caplog) == []


class TestGenuineFaultSeparation:
    """Server faults keep their 1011 + ERROR path; client hang-ups do not."""

    def test_session_feed_failure_closes_1011_stream_initialization_failed(self):
        mod, session, _ = _make_app()
        session.feed = AsyncMock(side_effect=RuntimeError("decode exploded"))

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session):
            with client.websocket_connect("/v3/stream") as websocket:
                assert websocket.receive_json() == {"type": "ready"}
                websocket.send_bytes(b"\x01")
                with pytest.raises(WebSocketDisconnect) as exc_info:
                    websocket.receive_json()

        assert exc_info.value.code == 1011
        assert exc_info.value.reason == "stream_initialization_failed"

    def test_session_feed_failure_logs_v3_stream_error(self, caplog):
        mod, session, _ = _make_app()
        session.feed = AsyncMock(side_effect=RuntimeError("decode exploded"))

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session):
            with caplog.at_level(logging.ERROR):
                with client.websocket_connect("/v3/stream") as websocket:
                    assert websocket.receive_json() == {"type": "ready"}
                    websocket.send_bytes(b"\x01")
                    with pytest.raises(WebSocketDisconnect):
                        websocket.receive_json()

        faults = _v3_error_records(caplog)
        assert len(faults) == 1
        assert "decode exploded" in faults[0].getMessage()

    def test_session_feed_failure_releases_lease_and_cleans_session(self):
        mod, session, lease = _make_app()
        session.feed = AsyncMock(side_effect=RuntimeError("decode exploded"))

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session):
            with client.websocket_connect("/v3/stream") as websocket:
                assert websocket.receive_json() == {"type": "ready"}
                websocket.send_bytes(b"\x01")
                with pytest.raises(WebSocketDisconnect):
                    websocket.receive_json()

        lease.release.assert_called_once_with()
        session.cleanup.assert_called_once_with()


class TestSessionTeardownMetrics:
    def test_active_streams_gauge_returns_to_baseline_after_disconnect(self):
        mod, session, _ = _make_app()
        baseline = mod.ACTIVE_STREAMS._value.get()  # type: ignore[reportAttributeAccessIssue]  # prometheus introspection

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session):
            with client.websocket_connect("/v3/stream") as websocket:
                assert websocket.receive_json() == {"type": "ready"}
                websocket.close(code=1001)

        assert mod.ACTIVE_STREAMS._value.get() == baseline  # type: ignore[reportAttributeAccessIssue]  # prometheus introspection

    def test_stream_duration_observed_after_session_teardown(self):
        mod, session, _ = _make_app()
        before = mod.STREAM_DURATION._sum.get()  # type: ignore[reportAttributeAccessIssue]  # prometheus introspection

        client = TestClient(mod.app, raise_server_exceptions=False)
        with patch.object(mod, "StreamSession", return_value=session):
            with client.websocket_connect("/v3/stream") as websocket:
                assert websocket.receive_json() == {"type": "ready"}
                websocket.close(code=1001)

        assert mod.STREAM_DURATION._sum.get() > before  # type: ignore[reportAttributeAccessIssue]  # prometheus introspection


class TestDisconnectClassificationTripwire:
    def test_static_tripwire_disconnect_classified_in_stream_handler(self):
        # Labeled static tripwire (not behavioral coverage): guards the
        # in-band disconnect classification against regression-by-refactor.
        # The behavioral contract lives in TestClientDisconnectLifecycle.
        with open(MAIN_SOURCE_PATH, "r", encoding="utf-8") as source_file:
            handler_source = source_file.read()
        assert 'websocket.disconnect' in handler_source
        assert handler_source.count('websocket.disconnect') >= 1
