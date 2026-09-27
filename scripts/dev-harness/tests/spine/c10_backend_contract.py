"""Protected real-router acceptance, collected by the existing backend E2E wrapper.

Not named test_*: lightweight dev-harness tests must not bootstrap the backend.
"""
import inspect
import json
from pathlib import Path

from dev_harness import client_compat as compat
from .pending import pending

ROOT = Path(__file__).resolve().parents[4]


def sender(client, auth_headers):
    def send(request):
        response = client.request(request.method, request.path, params=list(request.query),
                                  headers={**dict(request.headers), **auth_headers}, content=request.body)
        return compat.Response(response.status_code, dict(response.headers), response.content)
    return send


def active_cases():
    cases = compat.registered_cases(ROOT)
    if not cases:
        catalog = json.loads((ROOT / 'contracts/client-compat/catalog.json').read_text())
        policy = json.loads((ROOT / 'contracts/client-compat/support-policy.json').read_text())
        assert catalog['releases'], 'uncaptured clients are pending, not retired'
        minima = policy['minimum_build']
        receipt = policy['enforcement_receipt']
        assert receipt and receipt['minimum_build'] == minima
        assert receipt['rollout_url'].startswith('https://') and receipt['rejection_test']
        assert all(type(minima[p]) is int and minima[p] > row['build']
                   for row in catalog['releases'] for p in row['platforms'])
        # Explicitly out of scope after validated server retirement, not a replay pass.
    return cases


@pending("C10")
def test_released_decoders_read_real_router_responses(client, fake_firestore, auth_headers, test_uid, monkeypatch):
    cases = active_cases()
    if not cases:
        return
    compat.seed_backend(fake_firestore, test_uid)
    calls, decoded, sent, expected_decodes = [], [], [], []
    original_decode = compat.decode_released
    def observe_decode(root, decoder, response):
        decoded.append((decoder, response))
        return original_decode(root, decoder, response)
    monkeypatch.setattr(compat, 'decode_released', observe_decode)
    paths = {c.request.path for c in cases}
    for route in client.app.routes:
        if getattr(route, 'path', None) not in paths or not hasattr(route, 'dependant'):
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
    real_send = sender(client, auth_headers)
    def observe_send(request):
        index = len(sent)
        sent.append(request)
        assert request == cases[index].request
        response = real_send(request)
        assert response.status == cases[index].status
        expected_decodes.append((cases[index].decoder, response))
        return response
    result = compat.run_registered_replay(ROOT, send=observe_send)
    assert result.executed == len(cases) == len(sent)
    assert result.issues == ()
    assert decoded == expected_decodes, 'decode the exact current router bytes, not canned fixture bytes'
    assert {c.request.path for c in cases if 200 <= c.status < 300} <= set(calls)


@pending("C10")
def test_backend_break_is_not_hidden_by_canned_success(client, fake_firestore, auth_headers, test_uid):
    cases = active_cases()
    if not cases:
        return
    compat.seed_backend(fake_firestore, test_uid)
    real_send = sender(client, auth_headers)
    observed = []
    def corrupt(request):
        response = real_send(request)
        observed.append(request)
        # Every initial case promises a nonempty JSON semantic observation.
        return compat.Response(response.status, response.headers, b'')
    result = compat.run_registered_replay(ROOT, send=corrupt)
    assert observed == [c.request for c in cases]
    assert result.executed == len(cases)
    expected = sorted((c.release, c.platform, c.id) for c in cases)
    assert sorted((i.release, i.platform, i.case) for i in result.issues) == expected
    assert all(i.pointer for i in result.issues)
