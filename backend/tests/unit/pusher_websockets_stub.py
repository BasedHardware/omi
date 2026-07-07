import sys
import types
from unittest.mock import AsyncMock


def install_websockets_stub():
    if 'websockets' not in sys.modules:
        websockets_stub = types.ModuleType('websockets')
        websockets_stub.__path__ = []
        sys.modules['websockets'] = websockets_stub

    websockets_stub = sys.modules['websockets']
    if not hasattr(websockets_stub, 'connect'):
        websockets_stub.connect = AsyncMock()

    if 'websockets.exceptions' not in sys.modules:
        websockets_exceptions_stub = types.ModuleType('websockets.exceptions')
        websockets_exceptions_stub.ConnectionClosed = type('ConnectionClosed', (Exception,), {})
        sys.modules['websockets.exceptions'] = websockets_exceptions_stub

    websockets_stub.exceptions = sys.modules['websockets.exceptions']
