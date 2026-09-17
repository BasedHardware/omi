"""Protected real-router acceptance, collected by the existing backend E2E wrapper.

Not named test_*: lightweight dev-harness tests must not bootstrap the backend.
"""
import inspect
from pathlib import Path

from dev_harness import client_compat as compat
from .pending import pending

ROOT = Path(__file__).resolve().parents[4]
PATHS = {'/v1/conversations', '/v3/memories', '/v2/messages', '/v1/action-items'}


def sender(client, auth_headers):
    def send(request):
        response = client.request(request.method, request.path, params=list(request.query),
                                  headers={**dict(request.headers), **auth_headers}, content=request.body)
        return compat.Response(response.status_code, dict(response.headers), response.content)
    return send


@pending("C10")
def test_released_decoders_read_real_router_responses(client, fake_firestore, auth_headers, test_uid, monkeypatch):
    compat.seed_backend(fake_firestore, test_uid)
    calls, decoded = [], []
    original_decode = compat.decode_released
    def observe_decode(root, decoder, response):
        decoded.append((decoder, response.body))
        return original_decode(root, decoder, response)
    monkeypatch.setattr(compat, 'decode_released', observe_decode)
    for route in client.app.routes:
        if getattr(route, 'path', None) not in PATHS or 'GET' not in getattr(route, 'methods', set()):
            continue
        original = route.dependant.call
        assert 'routers.' in original.__module__, 'must execute the current backend router, not a fixture server'
        def wrap(fn, path):
            async def record(**kwargs):
                calls.append(path)
                result = fn(**kwargs)
                return await result if inspect.isawaitable(result) else result
            return record
        monkeypatch.setattr(route.dependant, 'call', wrap(original, route.path))
    cases = compat.registered_cases(ROOT)
    result = compat.run_registered_replay(ROOT, send=sender(client, auth_headers))
    assert len(cases) >= 8
    assert result.executed == len(cases) == len(calls)
    assert set(calls) == PATHS
    assert result.issues == ()
    assert len(decoded) == len(cases)
    assert all(body for _, body in decoded)


@pending("C10")
def test_backend_break_is_not_hidden_by_canned_success(client, fake_firestore, auth_headers, test_uid):
    compat.seed_backend(fake_firestore, test_uid)
    real_send = sender(client, auth_headers)
    observed = []
    def corrupt(request):
        response = real_send(request)
        observed.append(request.path)
        if request.path == '/v1/conversations':
            return compat.Response(200, response.headers, b'[{"id":null}]')
        return response
    cases = compat.registered_cases(ROOT)
    result = compat.run_registered_replay(ROOT, send=corrupt)
    assert result.executed == len(cases) == len(observed)
    expected = sorted((c.release, c.platform, c.id) for c in cases if c.request.path == '/v1/conversations')
    assert expected
    assert sorted((i.release, i.platform, i.case) for i in result.issues) == expected
    assert all(i.pointer for i in result.issues)
