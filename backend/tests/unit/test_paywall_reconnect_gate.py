"""Listen admission retains the disabled trial answer on every client source."""

import pytest
from routers.listen.contracts import ListenRequest
from routers.listen.runtime import ListenSessionRuntime


class FakeWebSocket:
    def __init__(self):
        self.headers = {}
        self.events = []
        self.closed = []

    async def send_json(self, event):
        self.events.append(event)

    async def close(self, *, code, reason):
        self.closed.append((code, reason))


def _runtime(uid='test-user', source='desktop'):
    websocket = FakeWebSocket()
    return ListenSessionRuntime(ListenRequest(websocket=websocket, uid=uid, source=source)), websocket


class TestAdmissionPhase:
    """Exercise admission through the extracted runtime instead of source ordering."""

    @pytest.fixture(autouse=True)
    def _fresh_reconnect_budget(self):
        # _admit() consumes a process-global reconnect token (burst 3) keyed by
        # 'test-user'; without this the second admission test in a session is
        # shed with close 1011 before it reaches the sample-rate validation.
        from utils.listen_reconnect_budget import listen_reconnect_budget

        listen_reconnect_budget._buckets.clear()
        yield
        listen_reconnect_budget._buckets.clear()

    @pytest.mark.asyncio
    @pytest.mark.parametrize('source', ['desktop', 'macos', 'windows', 'ios', 'omi'])
    async def test_no_account_age_gate_before_session_start(self, monkeypatch, source):
        runtime, websocket = _runtime(source=source)

        async def no_trial_lookup(*args, **kwargs):
            pytest.fail('admission must not read trial state')

        monkeypatch.setattr('routers.listen.runtime.run_blocking', no_trial_lookup)
        assert await runtime._admit() is True
        assert websocket.events == []
        assert websocket.closed == []

    @pytest.mark.asyncio
    async def test_bad_uid_and_audio_format_are_rejected_without_starting_session(self, monkeypatch):
        missing_uid, missing_uid_socket = _runtime(uid='')
        assert await missing_uid._admit() is False
        assert missing_uid_socket.closed == [(1008, 'Bad uid')]

        invalid_audio, invalid_audio_socket = _runtime()
        monkeypatch.setattr('routers.listen.runtime.validate_audio_format', lambda *_args: 'bad_audio')
        assert await invalid_audio._admit() is False
        assert invalid_audio_socket.closed == [(1003, 'bad_audio')]
        assert invalid_audio.task_supervisor._session_started is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize('codec', ['pcm8', 'pcm16', 'aac'])
    @pytest.mark.parametrize('sample_rate', [30_000_000, 0, -16000])
    async def test_out_of_range_sample_rate_closes_before_bootstrap(self, monkeypatch, codec, sample_rate):
        # sample_rate=30000000 used to reach AudioRingBuffer at bootstrap and allocate ~3.6 GB.
        async def not_paywalled(_executor, function, *args):
            return False

        monkeypatch.setattr('routers.listen.runtime.run_blocking', not_paywalled)
        websocket = FakeWebSocket()
        runtime = ListenSessionRuntime(
            ListenRequest(websocket=websocket, uid='test-user', source='desktop', codec=codec, sample_rate=sample_rate)
        )
        assert await runtime._admit() is False
        assert len(websocket.closed) == 1
        code, reason = websocket.closed[0]
        assert code == 1003
        assert str(sample_rate) in reason
        assert runtime.task_supervisor._session_started is False
