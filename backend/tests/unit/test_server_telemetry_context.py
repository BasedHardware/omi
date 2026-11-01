"""Exercise request metadata through the real HTTP middleware with a local ASGI app."""

from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from utils.byok import BYOKMiddleware
from utils import product_telemetry


def test_http_context_reaches_sync_and_async_handlers_and_does_not_leak():
    app = FastAPI()
    app.add_middleware(BYOKMiddleware)
    capture = Mock()
    product_telemetry.set_product_telemetry_client_for_tests(capture)

    @app.get('/async')
    async def asynchronous():
        product_telemetry.emit_product_event(uid='u', event='Example', properties={})
        return {'ok': True}

    @app.get('/sync')
    def synchronous():
        product_telemetry.emit_product_event(uid='u', event='Example', properties={})
        return {'ok': True}

    try:
        with TestClient(app) as client:
            assert client.get('/async', headers={'X-App-Platform': 'ios', 'X-Build-Channel': 'testflight'}).json() == {
                'ok': True
            }
            assert (
                client.get('/sync', headers={'X-App-Platform': 'web', 'X-Build-Channel': 'stable'}).status_code == 200
            )
            assert client.get('/async').status_code == 200
        props = [call.kwargs['properties'] for call in capture.capture.call_args_list]
        assert [(p['source_platform'], p.get('build_channel')) for p in props] == [
            ('ios', 'testflight'),
            ('web', 'stable'),
            ('unknown', None),
        ]
    finally:
        product_telemetry.set_product_telemetry_client_for_tests(None)
