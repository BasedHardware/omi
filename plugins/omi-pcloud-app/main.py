"""Authenticated setup and durable admission for the standalone pCloud service."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from html import escape
from contextlib import asynccontextmanager
from urllib.parse import urlencode

import requests
from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import ValidationError

from omi_plugin_sdk.models import Conversation
from pcloud_client import PCloudClient
from presentation import setup_html, summary_markdown, transcript_markdown
from security import signing_key, verify, verify_delivery
from store import configured_store
from worker import run_next_job

COOKIE = 'omi_pcloud_session'
REGIONS = {1: 'api.pcloud.com', 2: 'eapi.pcloud.com'}
_store = None


def get_store():
    global _store
    if _store is None:
        _store = configured_store()
    return _store


@asynccontextmanager
async def lifespan(app):
    signing_key()
    get_store().check_ready()
    for name in ('PCLOUD_CLIENT_ID', 'PCLOUD_CLIENT_SECRET', 'PCLOUD_REDIRECT_URI'):
        if not os.getenv(name):
            raise RuntimeError(f'Missing {name}')
    stop = asyncio.Event()

    async def loop():
        while not stop.is_set():
            try:
                worked = await asyncio.to_thread(run_next_job, get_store())
            except Exception as error:
                logging.getLogger(__name__).error('Backup worker store step failed: %s', type(error).__name__)
                worked = False
            if not worked:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=2)
                except asyncio.TimeoutError:
                    pass

    task = asyncio.create_task(loop(), name='pcloud-backup-worker')
    app.state.worker_task = task
    try:
        yield
    finally:
        stop.set()
        await task


app = FastAPI(title='Omi pCloud Backup', version='2.0.0', lifespan=lifespan)


@app.middleware('http')
async def privacy_headers(request, call_next):
    response = await call_next(request)
    response.headers.update(
        {
            'Cache-Control': 'no-store',
            'Referrer-Policy': 'no-referrer',
            'X-Content-Type-Options': 'nosniff',
            'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; form-action 'self' https://my.pcloud.com; frame-ancestors 'none'; base-uri 'none'",
        }
    )
    return response


def session(request: Request, csrf: str | None = None) -> dict:
    sid = request.cookies.get(COOKIE, '')
    data = get_store().get('session', hashlib.sha256(sid.encode()).hexdigest()) if sid else None
    if not data:
        raise HTTPException(status_code=401, detail='Open pCloud settings from your signed-in Omi app.')
    if csrf is not None and not hmac.compare_digest(csrf.encode(), data['csrf'].encode()):
        raise HTTPException(status_code=403, detail='This form expired. Reload settings and try again.')
    return data


def page(request: Request, notice: str = '', status_code: int = 200):
    principal = session(request)
    store = get_store()
    if not notice:
        flash_id = hashlib.sha256(request.cookies[COOKIE].encode()).hexdigest()
        notice = (store.get('flash', flash_id, consume=True) or {}).get('message', '')
    return HTMLResponse(
        setup_html(
            store.settings(principal['uid']),
            store.get('connection', principal['uid']),
            store.jobs(principal['uid']),
            principal['csrf'],
            notice,
        ),
        status_code=status_code,
    )


def success_page(request: Request, message: str):
    principal = session(request)
    flash_id = hashlib.sha256(request.cookies[COOKIE].encode()).hexdigest()
    get_store().put('flash', flash_id, principal['uid'], {'message': message}, ttl=60)
    return RedirectResponse('/setup/pcloud', status_code=303)


@app.exception_handler(HTTPException)
def actionable_error(request: Request, error: HTTPException):
    if 'text/html' in request.headers.get('accept', ''):
        return HTMLResponse(
            f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>pCloud connection · Omi</title><main style="max-width:600px;margin:48px auto;padding:20px;font:16px/1.6 system-ui"><h1>pCloud connection needs attention</h1><p>{escape(str(error.detail))}</p><p>Your saved connection and existing remote backups have not been changed by this rejected request.</p></main></html>',
            status_code=error.status_code,
        )
    return JSONResponse({'detail': error.detail}, status_code=error.status_code)


@app.get('/health')
def health():
    get_store().check_ready()
    signing_key()
    task = getattr(app.state, 'worker_task', None)
    if task is not None and task.done():
        raise HTTPException(status_code=503, detail='The backup worker is not running')
    return {'status': 'ok', 'provider': 'pcloud'}


@app.get('/setup/pcloud')
def setup(request: Request, uid: str | None = None, omi_token: str | None = None):
    if omi_token:
        claims = verify(omi_token, 'setup')
        if uid != claims['sub'] or not get_store().consume_nonce(
            claims['jti'], uid, max(1, claims['exp'] - int(time.time()))
        ):
            raise HTTPException(status_code=401, detail='Open a fresh setup link from Omi.')
        sid = secrets.token_urlsafe(32)
        get_store().put(
            'session',
            hashlib.sha256(sid.encode()).hexdigest(),
            uid,
            {'uid': uid, 'csrf': secrets.token_urlsafe(32)},
            ttl=3600,
        )
        response = RedirectResponse('/setup/pcloud', status_code=303)
        response.set_cookie(COOKIE, sid, max_age=3600, secure=True, httponly=True, samesite='lax')
        return response
    principal = session(request)
    if uid is not None and uid != principal['uid']:
        raise HTTPException(status_code=403, detail='This account does not match your Omi session.')
    return page(request)


@app.get('/setup-completed')
def setup_completed(uid: str, omi_token: str):
    claims = verify(omi_token, 'status')
    if claims['sub'] != uid:
        raise HTTPException(status_code=401, detail='Account mismatch')
    connection = get_store().get('connection', uid)
    settings = get_store().settings(uid)
    return {
        'is_setup_completed': bool(connection and connection['status'] == 'active' and settings['consent_version'] == 1)
    }


@app.post('/settings')
def save_settings(
    request: Request,
    csrf: str = Form(...),
    folder_name: str = Form(...),
    save_summary: str | None = Form(None),
    save_transcript: str | None = Form(None),
    save_audio: str | None = Form(None),
):
    principal = session(request, csrf)
    parts = folder_name.strip('/ ').split('/')
    if len(folder_name) > 200 or len(parts) > 5 or any(not p.strip() or p.strip() in ('.', '..') for p in parts):
        return page(
            request, 'Choose a folder up to 200 characters, with at most five levels and no . or .. components.', 422
        )
    store = get_store()
    with store.account_lock(principal['uid']):
        store.put(
            'settings',
            principal['uid'],
            principal['uid'],
            {
                'folder_name': '/'.join(PCloudClient.sanitize_path(p) for p in parts),
                'save_summary': save_summary is not None,
                'save_transcript': save_transcript is not None,
                'save_audio': save_audio is not None,
                'consent_version': 1,
            },
            ttl=10 * 365 * 86400,
        )
    return success_page(request, 'Backup preferences saved. Changes apply to unfinished files as well as new backups.')


def authorization_epoch(store, uid: str, *, rotate: bool = False) -> str:
    """Per-account authorization generation; callers hold the account lock.

    Each OAuth attempt is stamped with it. Disconnect rotates it, so every attempt
    started before the Disconnect is retired, whether or not a connection exists.
    """
    record = None if rotate else store.get('authorization', uid)
    if not record:
        record = {'epoch': secrets.token_urlsafe(16)}
        store.put('authorization', uid, uid, record, ttl=10 * 365 * 86400)
    return record['epoch']


RETIRED_ATTEMPT = 'You disconnected pCloud after this connection started, so it was not completed. Connect again to continue.'


@app.post('/auth/pcloud')
def connect(request: Request, csrf: str = Form(...)):
    principal = session(request, csrf)
    store = get_store()
    with store.account_lock(principal['uid']):
        if store.get('connection', principal['uid']):
            return page(request, 'Disconnect your current pCloud account before connecting another.', 409)
        state = secrets.token_urlsafe(32)
        store.put(
            'oauth',
            state,
            principal['uid'],
            {
                'uid': principal['uid'],
                'session_csrf': principal['csrf'],
                'epoch': authorization_epoch(store, principal['uid']),
            },
            ttl=900,
        )
    return RedirectResponse(
        'https://my.pcloud.com/oauth2/authorize?'
        + urlencode(
            {
                'client_id': os.environ['PCLOUD_CLIENT_ID'],
                'response_type': 'code',
                'redirect_uri': os.environ['PCLOUD_REDIRECT_URI'],
                'state': state,
            }
        ),
        status_code=303,
    )


@app.get('/auth/pcloud/callback')
def callback(
    request: Request,
    state: str = Query('', max_length=128),
    code: str = Query('', max_length=4096),
    locationid: int = 0,
    hostname: str = '',
    error: str = '',
):
    principal = session(request)
    store = get_store()
    data = store.get('oauth', state, consume=True)
    if not data or data['uid'] != principal['uid'] or not hmac.compare_digest(data['session_csrf'], principal['csrf']):
        return page(request, 'The connection request expired or belongs to another session. Start again.', 400)
    if error or not code:
        return page(request, 'pCloud authorization was not completed. Your existing backups were not changed.', 400)
    if locationid not in REGIONS or hostname != REGIONS[locationid]:
        return page(request, 'pCloud returned an unsupported data-center address. Restart the connection.', 400)
    with store.account_lock(principal['uid']):
        if data.get('epoch') != authorization_epoch(store, principal['uid']):
            return page(request, RETIRED_ATTEMPT, 409)
    try:
        response = requests.post(
            f'https://{REGIONS[locationid]}/oauth2_token',
            data={
                'client_id': os.environ['PCLOUD_CLIENT_ID'],
                'client_secret': os.environ['PCLOUD_CLIENT_SECRET'],
                'code': code,
            },
            timeout=(5, 20),
            allow_redirects=False,
        )
        response.raise_for_status()
        if response.status_code != 200:
            raise ValueError('Unexpected token exchange response')
        payload = response.json()
        if (
            payload.get('result') != 0
            or not isinstance(payload.get('access_token'), str)
            or not payload['access_token']
        ):
            raise ValueError('Invalid token response')
        client = PCloudClient(payload['access_token'], locationid)
        profile, profile_error = client.get_user_info()
        connection = {
            'access_token': payload['access_token'],
            'location_id': locationid,
            'userid': payload.get('uid'),
            'email': (profile or {}).get('email', ''),
            'generation': secrets.token_urlsafe(24),
            'status': 'revoke_pending' if profile_error else 'active',
        }
        with store.account_lock(principal['uid']):
            # Disconnect may have run while the code was being exchanged. The token
            # just issued belongs to a retired attempt: revoke it, never store it.
            if data.get('epoch') != authorization_epoch(store, principal['uid']):
                revoked, _ = client.logout()
                if revoked:
                    return page(request, RETIRED_ATTEMPT, 409)
                return page(
                    request,
                    RETIRED_ATTEMPT + ' pCloud has not confirmed revocation of the access it just issued; '
                    'remove this app in your pCloud account settings.',
                    409,
                )
            if store.get('connection', principal['uid']):
                client.logout()
                return page(request, 'Another connection finished first. Disconnect it before changing accounts.', 409)
            store.put('connection', principal['uid'], principal['uid'], connection, ttl=10 * 365 * 86400)
        if profile_error:
            return page(
                request, 'pCloud account verification failed. Backups are stopped; retry access revocation below.', 502
            )
        return success_page(request, 'pCloud connected. Review and save your backup preferences to finish setup.')
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return page(
            request,
            'Could not finish connecting to pCloud. Try connecting again; no backup was reported as complete.',
            502,
        )


@app.post('/disconnect')
def disconnect(request: Request, csrf: str = Form(...)):
    principal = session(request, csrf)
    store = get_store()
    with store.account_lock(principal['uid']):
        authorization_epoch(store, principal['uid'], rotate=True)
        connection = store.get('connection', principal['uid'])
        store.cancel_jobs(principal['uid'])
        if connection:
            connection['status'] = 'revoke_pending'
            store.put('connection', principal['uid'], principal['uid'], connection, ttl=10 * 365 * 86400)
            ok, _ = PCloudClient(connection['access_token'], connection['location_id']).logout()
            if not ok:
                return page(
                    request,
                    'Backups stopped, but pCloud has not confirmed access revocation. Retry below, or remove this app in your pCloud account.',
                    502,
                )
            store.delete('connection', principal['uid'])
    return success_page(request, 'Disconnected and revoked pCloud access. Existing remote files were not deleted.')


@app.post('/audio')
def reject_unscoped_audio():
    raise HTTPException(
        status_code=410,
        detail='UID-only audio buffering is not supported. Backups read canonical saved audio by conversation ID.',
    )


@app.post('/conversation')
async def conversation_created(request: Request, uid: str):
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > 4 * 1024 * 1024:
            raise HTTPException(status_code=413, detail='Conversation delivery is too large')
        raw.extend(chunk)
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError('Expected object')
        verify_delivery(request, payload, uid)
        conversation = Conversation.model_validate(payload)
    except (ValueError, ValidationError):
        raise HTTPException(status_code=422, detail='Invalid conversation delivery')
    if not conversation.id:
        raise HTTPException(status_code=422, detail='A stable conversation ID is required')
    return await asyncio.to_thread(admit, uid, conversation, payload.get('_omi_backup_audio_token'))


def admit(uid: str, conversation: Conversation, audio_token: str | None):
    store = get_store()
    with store.account_lock(uid):
        connection = store.get('connection', uid)
        if not connection or connection['status'] != 'active':
            raise HTTPException(status_code=409, detail='Connect pCloud before exporting this conversation')
        if conversation.discarded:
            return JSONResponse({'status': 'skipped', 'message': 'Discarded conversation was not exported'})
        settings = store.settings(uid)
        files = {}
        if settings['save_summary']:
            files['summary.md'] = summary_markdown(conversation)
        if settings['save_transcript']:
            files['transcript.md'] = transcript_markdown(conversation)
        audio_enabled = settings['save_audio']
        claims = verify(audio_token or '', 'audio')
        if claims['sub'] != uid or claims.get('conversation_id') != conversation.id:
            raise HTTPException(status_code=401, detail='Backup authorization belongs to another conversation')
        if not files and not audio_enabled:
            return JSONResponse({'status': 'paused', 'message': 'No backup items enabled'})
        key = hashlib.sha256(f'{uid}\0{conversation.id}'.encode()).hexdigest()
        job = {
            'conversation_id': conversation.id,
            'title': conversation.structured.title,
            'path': f'/{settings["folder_name"]}/{key}',
            'files': files,
            'audio_token': audio_token if audio_enabled else None,
            'authorization_token': audio_token,
            'generation': connection['generation'],
        }
        try:
            identity = store.enqueue(uid, conversation.id, job)
        except OverflowError:
            raise HTTPException(
                status_code=429, detail='Too many unfinished backups. Review failed backups in settings.'
            )
        state = store.job_state(uid, identity)
        queued = state in ('pending', 'running')
        return JSONResponse(
            {
                'status': 'accepted' if queued else state,
                'backup_id': identity,
                'message': (
                    'Queued for backup; check pCloud settings for progress.'
                    if queued
                    else 'This conversation already has a backup record. Check its status in pCloud settings.'
                ),
            },
            status_code=202 if queued else 200,
        )


@app.post('/backups/{identity}/retry')
def retry_backup(identity: str, request: Request, csrf: str = Form(...)):
    principal = session(request, csrf)
    store = get_store()
    with store.account_lock(principal['uid']):
        if not store.retry(principal['uid'], identity):
            return page(request, 'This backup cannot be retried. It may be complete, expired, or canceled.', 409)
    return success_page(request, 'Backup queued for retry. Previously completed files will not be uploaded again.')
