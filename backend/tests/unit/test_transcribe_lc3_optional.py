import pytest

from routers.listen import receiver
from routers.listen.contracts import ListenRequest
from routers.listen.runtime import ListenSessionRuntime


def test_lc3_optional_dependency_fails_with_its_import_cause(monkeypatch):
    missing_dependency = ModuleNotFoundError("No module named 'lc3'")
    monkeypatch.setattr(receiver, 'lc3', None)
    monkeypatch.setattr(receiver, 'lc3_import_error', missing_dependency)

    with pytest.raises(RuntimeError, match='LC3 streaming requires lc3py') as error:
        receiver._get_lc3()

    assert error.value.__cause__ is missing_dependency


class _WebSocket:
    headers = {}

    def __init__(self):
        self.close_calls: list[tuple[int, str]] = []

    async def close(self, *, code: int, reason: str) -> None:
        self.close_calls.append((code, reason))


class _FailingDecoder:
    def initialize_decoders(self) -> None:
        raise RuntimeError('LC3 dependency is unavailable')


@pytest.mark.asyncio
async def test_lc3_codec_closes_cleanly_when_decoder_initialization_fails(monkeypatch):
    websocket = _WebSocket()
    runtime = ListenSessionRuntime(ListenRequest(websocket=websocket, uid='uid', codec='lc3'))
    runtime.receiver = _FailingDecoder()

    async def allow_session() -> bool:
        return True

    monkeypatch.setattr(runtime, '_admit', allow_session)
    monkeypatch.setattr(runtime, '_bootstrap', allow_session)

    await runtime.run()

    assert websocket.close_calls == [(runtime.state.close_code, 'LC3 codec is not available')]
