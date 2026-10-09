from abc import ABC, abstractmethod
import threading
from typing import Any
from typing import Optional

from utils.metrics import OMI_LIVE_STT_OPEN_STREAMS
from utils.stt.stream_close import bounded_stream_close_provider

_LIVE_SOCKET_LEASES: dict[int, str] = {}
_LIVE_SOCKET_LEASES_LOCK = threading.Lock()


def record_live_stt_socket_open(provider: str) -> None:
    OMI_LIVE_STT_OPEN_STREAMS.labels(provider=bounded_stream_close_provider(provider)).inc()


def record_live_stt_socket_closed(provider: str) -> None:
    OMI_LIVE_STT_OPEN_STREAMS.labels(provider=bounded_stream_close_provider(provider)).dec()


def track_live_stt_socket(socket: Any, provider: str) -> Any:
    if socket is None or getattr(socket, 'manages_vad', False):
        return socket
    with _LIVE_SOCKET_LEASES_LOCK:
        key = id(socket)
        if key not in _LIVE_SOCKET_LEASES:
            _LIVE_SOCKET_LEASES[key] = bounded_stream_close_provider(provider)
            record_live_stt_socket_open(provider)
    return socket


def release_live_stt_socket(socket: Any) -> None:
    with _LIVE_SOCKET_LEASES_LOCK:
        provider = _LIVE_SOCKET_LEASES.pop(id(socket), None)
        if provider is not None:
            record_live_stt_socket_closed(provider)


class STTSocket(ABC):
    @abstractmethod
    def send(self, data: bytes) -> bool:
        """Return whether this socket durably accepted the audio bytes."""
        ...

    @abstractmethod
    def finish(self) -> None: ...

    @abstractmethod
    def finalize(self) -> None: ...

    @property
    @abstractmethod
    def is_connection_dead(self) -> bool: ...

    @property
    @abstractmethod
    def death_reason(self) -> Optional[str]: ...
