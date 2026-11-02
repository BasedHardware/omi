"""Closed projection error provenance and peer-departure classification."""

from typing import Any, cast
from grpc import StatusCode
from fastapi.websockets import WebSocketDisconnect
from starlette.websockets import WebSocketState


def raising_frame(exc: BaseException) -> str:
    """Innermost raising frame name, for RCA attribution of projection failures.

    Only the code object's name is ever returned — the exception message and
    args can carry user-identifying object paths and must not reach logs.
    """
    frame_name = 'unknown'
    tb = exc.__traceback__
    while tb is not None:
        frame_name = tb.tb_frame.f_code.co_name
        tb = tb.tb_next
    return frame_name


def grpc_code(exc: BaseException) -> str:
    """Only the SDK's closed gRPC status enum; never message/metadata/reason text."""
    code = cast(object, getattr(exc, 'grpc_status_code', None))
    if isinstance(code, StatusCode):
        return code.name
    return 'UNKNOWN'


def ack_peer_departed(exc: Exception, websocket: Any) -> bool:
    if isinstance(exc, (WebSocketDisconnect, OSError)):
        return True
    return isinstance(exc, RuntimeError) and (
        getattr(websocket, 'application_state', None) == WebSocketState.DISCONNECTED
        or getattr(websocket, 'client_state', None) == WebSocketState.DISCONNECTED
        or str(exc) == 'Cannot call "send" once a close message has been sent.'
    )


def peer_connected(websocket: Any) -> bool:
    return websocket.client_state == WebSocketState.CONNECTED
