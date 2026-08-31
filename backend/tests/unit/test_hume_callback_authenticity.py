"""The Hume prosody callback must prove it belongs to a job we submitted (BACKLOG L42).

`POST /v1/agents/hume/callback` is unauthenticated by necessity: Hume calls it and holds no user token.
Until this gate existed, the `job_id` in the BODY was the only thing tying a payload to a conversation,
so anyone who learned a job id could POST arbitrary prosody predictions and have them stored as a user's
measured emotions. Learning one does not require guessing — the id travels through Hume's dashboard, our
logs, and the callback itself.

The proof travels in the callback URL, because that is the one part of the exchange we control. What is
signed is NOT the job id: Hume chooses that and only returns it in the response to our submission, so at
the moment we ask there is nothing of ours to sign. What we choose, one line earlier, is the Task row's
id — signing that binds the callback to one specific submission, and the handler then refuses a body
whose job id resolves to a different task.

**Legacy principal.** A job already in flight when this deploys was submitted with the old, tokenless
callback URL, and its callback is now refused. That is a deliberate trade: Hume's batch prosody jobs
finish in minutes, the lost artefact is an emotion measurement rather than a user's content, and the
alternative — accepting unsigned callbacks during a grace period — is the hole itself, kept open on a
timer. On this deployment's default posture the window is empty anyway: `OMI_VENDOR_EGRESS=deny` means
no job is ever in flight. `test_a_tokenless_callback_from_a_job_in_flight_is_refused` states it.
"""

from __future__ import annotations

import os

# The handler tests below import utils.conversations.process_conversation, which builds clients at import
# time. Same preamble the other tests of that module use (test_merge_deleted_source_race.py).
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')
os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')

import time

import pytest

from utils.other.hume_callback_token import (
    DEFAULT_TTL_SECONDS,
    HumeCallbackTokenError,
    mint,
    task_id_from_token,
)

SECRET = b'0123456789abcdef0123456789abcdef'


def test_a_minted_token_names_the_task_it_was_minted_for():
    assert task_id_from_token(mint('task-1', secret=SECRET), secret=SECRET) == 'task-1'


def test_a_tampered_signature_is_refused():
    token = mint('task-1', secret=SECRET)

    with pytest.raises(HumeCallbackTokenError, match='invalid_hume_callback_signature'):
        task_id_from_token(token[:-1] + ('x' if token[-1] != 'x' else 'y'), secret=SECRET)


def test_a_token_re_pointed_at_another_task_is_refused():
    """The attack the signature exists for: keep a valid token, swap the task it names."""
    _task_id, expiry, signature = mint('task-1', secret=SECRET).split('.')

    with pytest.raises(HumeCallbackTokenError, match='invalid_hume_callback_signature'):
        task_id_from_token(f'task-2.{expiry}.{signature}', secret=SECRET)


def test_a_token_with_a_pushed_out_expiry_is_refused():
    """The expiry is inside the signed value, not beside it."""
    task_id, expiry, signature = mint('task-1', secret=SECRET).split('.')

    with pytest.raises(HumeCallbackTokenError, match='invalid_hume_callback_signature'):
        task_id_from_token(f'{task_id}.{int(expiry) + 86400}.{signature}', secret=SECRET)


def test_an_expired_token_is_refused_even_though_it_is_genuine():
    now = int(time.time())
    token = mint('task-1', ttl_seconds=60, now=now, secret=SECRET)

    assert task_id_from_token(token, now=now + 59, secret=SECRET) == 'task-1'
    with pytest.raises(HumeCallbackTokenError, match='expired_hume_callback_token'):
        task_id_from_token(token, now=now + 61, secret=SECRET)


def test_a_token_from_the_referral_surface_cannot_be_replayed_here():
    """Domain separation. Both helpers are HMAC-SHA256 over the same ENCRYPTION_SECRET, so without a
    distinct prefix a code minted for one surface would verify on the other."""
    from utils.referrals import create_referral_code

    with pytest.raises(HumeCallbackTokenError):
        task_id_from_token(create_referral_code('user-1', secret=SECRET), secret=SECRET)


def test_a_task_id_containing_the_separator_is_refused_at_minting():
    """'.' is the field separator: an id carrying one would let a crafted id shift the boundaries."""
    with pytest.raises(HumeCallbackTokenError, match='invalid_task_id'):
        mint('task.1', secret=SECRET)


def test_a_deployment_without_a_signing_secret_refuses_to_mint(monkeypatch):
    """Loud rather than unsigned: falling back to an open callback is the hole this closes."""
    monkeypatch.delenv('ENCRYPTION_SECRET', raising=False)

    with pytest.raises(HumeCallbackTokenError, match='missing_hume_callback_signing_secret'):
        mint('task-1')


def test_the_default_lifetime_outlives_a_slow_batch_job():
    """Hume's prosody jobs finish in minutes; a queue on their side is not ours to predict. A token that
    outlives its usefulness is far less harmful than one that expires under a slow job and silently drops
    a user's result."""
    assert DEFAULT_TTL_SECONDS >= 60 * 60


# --- the URL the client hands Hume ------------------------------------------------------------------


def _client(callback_url):
    from utils.other.hume import HumeClient

    return HumeClient(api_key='k', callback_url=callback_url)


def test_the_token_is_carried_on_the_callback_url():
    url = _client('https://api.example.test/v1/agents/hume/callback')._callback_url_for('tok-1')

    assert url == 'https://api.example.test/v1/agents/hume/callback?t=tok-1'


def test_an_existing_query_string_is_preserved():
    url = _client('https://api.example.test/cb?env=prod')._callback_url_for('tok-1')

    assert url == 'https://api.example.test/cb?env=prod&t=tok-1'


def test_a_token_is_url_encoded():
    """The token is base64url plus dots, but the encoding is not optional: an unescaped value would let a
    crafted token inject further query parameters."""
    url = _client('https://api.example.test/cb')._callback_url_for('a&b=c')

    assert url == 'https://api.example.test/cb?t=a%26b%3Dc'


# --- the route -------------------------------------------------------------------------------------


@pytest.fixture
def route(monkeypatch):
    """`routers/agents.py` with its one heavy import stubbed, plus a spy on the handler.

    Only `process_user_expression_measurement_callback` is replaced: everything the gate does — reading
    the query parameter, verifying, refusing — is the real code.
    """
    import importlib
    import sys
    import types

    from testing.import_isolation import stub_modules

    calls: list[tuple] = []
    stub = types.ModuleType('utils.conversations.process_conversation')
    stub.process_user_expression_measurement_callback = lambda *args: calls.append(args)

    monkeypatch.setenv('ENCRYPTION_SECRET', SECRET.decode())
    with stub_modules({'utils.conversations.process_conversation': stub, 'routers.agents': None}):
        agents = importlib.import_module('routers.agents')
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(agents.router)
        yield {'client': TestClient(app), 'calls': calls}
        sys.modules.pop('routers.agents', None)


BODY = {'job_id': 'hume-job-1', 'status': 'COMPLETED', 'predictions': []}


def _post(route, query=''):
    return route['client'].post(f'/v1/agents/hume/callback{query}', json=BODY)


def test_a_tokenless_callback_from_a_job_in_flight_is_refused(route):
    """THE LEGACY PRINCIPAL, and the deliberate cost of this gate.

    A job submitted before this deployed carries the old tokenless callback URL, and its result is now
    dropped. The trade is stated rather than softened: Hume's batch prosody jobs finish in minutes, what
    is lost is an emotion measurement and not a user's content, and the alternative — accepting unsigned
    callbacks for a grace period — is the hole itself on a timer. On this deployment's default posture
    (`OMI_VENDOR_EGRESS=deny`) no job is ever in flight, so the window is empty.
    """
    response = _post(route)

    assert response.status_code == 401
    assert route['calls'] == [], 'an unauthenticated payload must not reach the handler'


def test_a_forged_token_is_refused(route):
    response = _post(route, '?t=task-1.9999999999.not-a-real-signature')

    assert response.status_code == 401
    assert route['calls'] == []


def test_an_expired_token_is_refused(route):
    response = _post(route, f'?t={mint("task-1", ttl_seconds=-1, secret=SECRET)}')

    assert response.status_code == 401
    assert route['calls'] == []


def test_the_refusal_says_nothing_about_which_check_failed(route):
    """Absent, forged and expired must be indistinguishable to a caller who is not supposed to be here."""
    bodies = {
        _post(route).json()['detail'],
        _post(route, '?t=task-1.9999999999.nope').json()['detail'],
        _post(route, f'?t={mint("task-1", ttl_seconds=-1, secret=SECRET)}').json()['detail'],
    }

    assert bodies == {'Unauthorized'}


def test_a_valid_token_reaches_the_handler_carrying_the_task_it_names(route):
    response = _post(route, f'?t={mint("task-42", secret=SECRET)}')

    assert response.status_code == 200
    assert len(route['calls']) == 1
    provider, job_id, _callback, expected_task_id = route['calls'][0]
    assert job_id == 'hume-job-1'
    assert expected_task_id == 'task-42', 'the handler must be told WHICH task the token authorises'


# --- the handler: a valid token authorises ONE task ------------------------------------------------


def _drive_handler(monkeypatch, *, task_id, expected_task_id):
    """Run the real handler against a stubbed task row; report whether it wrote."""
    from datetime import datetime

    from models.task import Task, TaskAction, TaskActionProvider, TaskStatus
    from utils.conversations import process_conversation as pc
    from utils.other.hume import HumeJobCallbackModel

    stored = Task(
        id=task_id,
        action=TaskAction.HUME_MERSURE_USER_EXPRESSION,
        user_uid='user-1',
        memory_id='conv-1',
        status=TaskStatus.PROCESSING,
        request_id='hume-job-1',
        created_at=datetime(2026, 8, 22, 12, 0),
    )
    writes: list = []
    monkeypatch.setattr(pc.tasks_db, 'get_task_by_action_request', lambda _action, _rid: stored.dict())
    monkeypatch.setattr(pc.tasks_db, 'update', lambda *args, **kwargs: writes.append(args))
    monkeypatch.setattr(pc.conversations_db, 'get_conversation', lambda _uid, _cid: None)

    callback = HumeJobCallbackModel.from_dict('prosody', {'job_id': 'hume-job-1', 'status': 'COMPLETED'})
    pc.process_user_expression_measurement_callback(TaskActionProvider.HUME, 'hume-job-1', callback, expected_task_id)
    return writes


def test_a_valid_token_cannot_steer_another_users_job(monkeypatch):
    """The attack the task check exists for, and the reason the signature alone is not enough.

    A user has a genuine token for their OWN submission. Nothing stops them putting somebody else's job
    id in the body — the id is not a secret. The token proves the callback is ours; this proves it is
    THIS submission's.
    """
    writes = _drive_handler(monkeypatch, task_id='task-belonging-to-someone-else', expected_task_id='task-mine')

    assert writes == [], 'a callback authorised for one task wrote to another'


def test_the_task_the_token_names_is_processed(monkeypatch):
    """The legitimate path, so the check above is not passing by refusing everything."""
    writes = _drive_handler(monkeypatch, task_id='task-mine', expected_task_id='task-mine')

    assert writes, 'the authorised callback was refused too'


def test_a_signing_failure_skips_the_measurement_instead_of_failing_the_conversation(monkeypatch):
    """The only caller of the submission wraps it in `except Exception` and marks the whole
    conversation's postprocessing FAILED. Letting a signing error escape would trade a working
    conversation for an optional emotion reading, so it is skipped and logged instead. Unreachable while
    ENCRYPTION_SECRET is mandatory at boot — which is why it must not be load-bearing."""
    from models.conversation import Conversation
    from utils.conversations import process_conversation as pc
    from utils.other.hume_callback_token import HumeCallbackTokenError

    submitted: list = []
    monkeypatch.setattr(pc, 'vendor_egress_denied', lambda *a, **kw: False, raising=False)
    monkeypatch.setattr(pc.tasks_db, 'create', lambda *_a, **_kw: None)
    monkeypatch.setattr(pc.tasks_db, 'update', lambda *_a, **_kw: submitted.append('update'))
    monkeypatch.setattr(
        pc,
        'get_hume',
        lambda: type(
            'C', (), {'request_user_expression_mersurement': lambda *a, **k: submitted.append('sent') or {}}
        )(),
    )
    import utils.other.hume_callback_token as token_module

    def _refuse(_task_id):
        raise HumeCallbackTokenError('missing_hume_callback_signing_secret')

    monkeypatch.setattr(token_module, 'mint', _refuse)

    conversation = Conversation.construct(id='conv-1', language='en')
    pc.process_user_emotion('user-1', 'en', conversation, ['https://example.test/audio.wav'])

    assert submitted == [], 'a signing failure must not submit, and must not raise'
