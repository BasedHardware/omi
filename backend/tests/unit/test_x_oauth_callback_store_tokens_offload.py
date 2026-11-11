"""GET /v1/x/oauth/callback must not run _store_tokens on the event loop.

_store_tokens does two sequential Firestore writes (set_integration,
_register_user). The handler is async and the comment right above the call
says the redirect must be instant, so the write has to go through
run_blocking(db_executor, ...) like every other store in this module,
not run inline on the loop.
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from routers import x_connector as x_mod  # noqa: E402


async def test_oauth_callback_offloads_store_tokens(monkeypatch):
    offloaded_calls = []

    async def fake_run_blocking(executor, func, *args, **kwargs):
        offloaded_calls.append((executor, func))
        return func(*args, **kwargs)

    monkeypatch.setattr(x_mod, 'run_blocking', fake_run_blocking)
    monkeypatch.setattr(x_mod.x_connector, 'consume_oauth_state', lambda state: {'uid': 'u1', 'verifier': 'v'})

    async def fake_exchange_code(code, verifier):
        return {'access_token': 'tok'}

    async def fake_fetch_me(token):
        return {'username': 'nik', 'id': '123'}

    store_calls = []

    def fake_store_tokens(uid, token_resp, handle=None, x_user_id=None):
        store_calls.append((uid, handle, x_user_id))

    monkeypatch.setattr(x_mod.x_connector, 'exchange_code', fake_exchange_code)
    monkeypatch.setattr(x_mod.x_connector, 'fetch_me', fake_fetch_me)
    monkeypatch.setattr(x_mod.x_connector, '_store_tokens', fake_store_tokens)
    monkeypatch.setattr(x_mod, 'start_background_task', lambda coro, name=None: coro.close())

    response = await x_mod.x_oauth_callback(request=None, code='c', state='s', error=None)

    assert response.status_code == 200
    assert store_calls == [('u1', 'nik', '123')]
    # The store must go through the db executor, not a direct call on the loop.
    assert len(offloaded_calls) == 1
    assert offloaded_calls[0][1] is x_mod.x_connector._store_tokens
