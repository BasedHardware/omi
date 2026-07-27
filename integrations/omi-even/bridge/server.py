"""The omi <-> Even Realities bridge.

Serves three consumers from one process, because all three need the same Firebase
session and it should live in exactly one place:

1. **Even's built-in assistant** (`POST /`) -- the Even phone app's "Add Agent"
   feature posts OpenAI chat-completions here after doing speech-to-text on the
   glasses. This is what makes Even AI answer out of Omi's memory.
2. **The `omi` Hub plugin** (`WS /app`) -- the app on the glasses. JSON text frames
   are control; binary frames are microphone PCM.
3. **Operators** (`GET /health`) -- status without exposing credentials.

Run it:

    OMI_EVEN_TOKEN=<shared secret> .venv/bin/uvicorn server:app --host 0.0.0.0 --port 8788
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from capture import CaptureSession
from display import DEFAULT_LIMIT as DISPLAY_LIMIT
from display import fit_for_glasses, openai_chat_completion, paginate
from omi_auth import AuthError, OmiAuth
from omi_client import OmiClient

logging.basicConfig(
    level=os.getenv('OMI_EVEN_LOG_LEVEL', 'INFO'),
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)
log = logging.getLogger('omi-even')

OMI_API_BASE = os.getenv('OMI_API_BASE', 'https://api.omi.me')

# Shared secret the Even app sends as `Authorization: Bearer ...`. Generated at
# startup when unset so the bridge is never accidentally left open.
EVEN_TOKEN = os.getenv('OMI_EVEN_TOKEN') or secrets.token_urlsafe(24)

# A measured Omi answer takes ~9s. Even's client timeout is undocumented, so we
# cap our own wait and return whatever partial answer exists rather than nothing.
AGENT_DEADLINE_S = float(os.getenv('OMI_EVEN_DEADLINE', '20'))

_CONTRACT_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'add-agent-capture.log')

# Larger than any answer Omi produces; used to strip markup without truncating.
_UNLIMITED = 1_000_000

auth = OmiAuth()
omi = OmiClient(auth, OMI_API_BASE)


@asynccontextmanager
async def _lifespan(_: FastAPI):
    log.info('bridge starting; Even token: %s', EVEN_TOKEN)
    if not os.getenv('OMI_EVEN_TOKEN'):
        log.warning('OMI_EVEN_TOKEN was unset -- generated one for this run only')
    push_task = asyncio.create_task(_push_loop(), name='omi-even-push')
    try:
        yield
    finally:
        push_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await push_task


app = FastAPI(title='omi-even-bridge', lifespan=_lifespan)


# --------------------------------------------------------------------- health


@app.get('/health')
async def health() -> dict:
    status: dict = {
        'ok': True,
        'omi_api': OMI_API_BASE,
        'deadline_s': AGENT_DEADLINE_S,
        'app_clients': len(_clients),
    }
    try:
        # Before describe(): this is what actually loads the session, so reporting
        # auth state first would show "not loaded" on an otherwise healthy bridge.
        status['quota'] = await omi.usage_quota()
    except Exception as exc:  # noqa: BLE001 - health must never 500
        status['ok'] = False
        status['quota_error'] = f'{type(exc).__name__}: {exc}'
    status['auth'] = auth.describe()
    return status


# ------------------------------------------------------- Even AI agent endpoint


def _extract_question(payload: dict) -> str:
    """Pull the user's question out of an OpenAI chat-completions body.

    Tolerant on purpose: the Add Agent contract is undocumented, so accept both a
    plain string `content` and the newer list-of-parts shape, and fall back to any
    last message if no explicit user role is present.
    """
    messages = payload.get('messages')
    if not isinstance(messages, list) or not messages:
        return ''

    def content_of(message: object) -> str:
        if not isinstance(message, dict):
            return ''
        content = message.get('content')
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = [p.get('text', '') for p in content if isinstance(p, dict) and p.get('type') == 'text']
            return ' '.join(part for part in parts if part).strip()
        return ''

    for message in reversed(messages):
        if isinstance(message, dict) and message.get('role') == 'user':
            text = content_of(message)
            if text:
                return text
    return content_of(messages[-1])


def _authorized(request: Request) -> bool:
    header = request.headers.get('authorization') or ''
    parts = header.split(' ', 1)
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        return False
    # Constant-time compare: this is a shared secret over the open internet.
    return secrets.compare_digest(parts[1].strip(), EVEN_TOKEN)


def _display_is_full(raw: str) -> bool:
    """True once the accumulated answer already overflows one screen.

    Omi writes for a phone: measured answers ran 929-1511 characters where the
    glasses show ~380, and waiting for that tail cost about 3 seconds per
    question the user never saw. Stripping only ever shrinks text, so a raw
    length below the limit cannot possibly fill the screen -- that cheap check
    guards the expensive one, which runs at most a handful of times per answer.
    """
    if len(raw) < DISPLAY_LIMIT:
        return False
    # Fit with an effectively unlimited budget so this measures the *stripped*
    # length. Fitting at DISPLAY_LIMIT would truncate to at most DISPLAY_LIMIT --
    # and usually a few characters below it, having landed on a word boundary --
    # so comparing that against DISPLAY_LIMIT is a test that almost never passes.
    return len(fit_for_glasses(raw, limit=_UNLIMITED)) >= DISPLAY_LIMIT


async def _answer_for_glasses(question: str) -> str:
    """Ask Omi and reduce the answer to something the G2 can actually show."""
    result = await omi.chat(question, deadline_s=AGENT_DEADLINE_S, enough=_display_is_full)

    if result.error:
        log.warning('chat error: %s', result.error)
        return fit_for_glasses(f'Omi could not answer: {result.error}')

    if not result.text.strip():
        return 'Omi had no answer for that.'

    fitted = fit_for_glasses(result.text, limit=DISPLAY_LIMIT)
    if result.truncated:
        log.info('answer truncated at the %.0fs deadline', AGENT_DEADLINE_S)
    log.info('answered in %.1fs (%d chars -> %d shown)', result.elapsed_s, len(result.text), len(fitted))
    return fitted


def _record_contract(request: Request, raw: bytes) -> None:
    """Append the raw request to a log, since Even publishes no spec for this.

    The first real request from the glasses is the only authoritative description
    of the contract, so it is captured verbatim rather than inferred. The bearer
    token is redacted -- everything else is kept, including header order and case.
    """
    try:
        headers = [
            [k, '<redacted>' if k.lower() == 'authorization' else v] for k, v in request.headers.items()
        ]
        entry = {
            'received_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
            'method': request.method,
            'path': request.url.path,
            'query': str(request.url.query),
            'client': request.client.host if request.client else None,
            'headers': headers,
            'body': raw.decode('utf-8', errors='replace')[:4000],
        }
        with open(_CONTRACT_LOG, 'a', encoding='utf-8') as fh:
            fh.write(json.dumps(entry, indent=2) + '\n---\n')
    except Exception as exc:  # noqa: BLE001 - logging must never break a request
        log.debug('contract capture failed: %s', exc)


async def _handle_agent(request: Request) -> JSONResponse:
    raw = await request.body()
    _record_contract(request, raw)

    if not _authorized(request):
        # Logged above, so a token mismatch is still diagnosable from the capture.
        log.warning('rejected unauthorized agent request from %s', request.client)
        return JSONResponse({'error': {'message': 'Unauthorized'}}, status_code=401)

    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({'error': {'message': 'Body must be JSON'}}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({'error': {'message': 'Body must be a JSON object'}}, status_code=400)

    question = _extract_question(payload)
    if not question:
        return JSONResponse({'error': {'message': 'No user message found'}}, status_code=400)

    log.info('agent question: %.120s', question)
    try:
        answer = await _answer_for_glasses(question)
    except AuthError as exc:
        log.error('auth failure: %s', exc)
        return JSONResponse({'error': {'message': str(exc)}}, status_code=503)
    except Exception as exc:  # noqa: BLE001 - never hand the glasses a 500
        log.exception('agent request failed')
        answer = fit_for_glasses(f'Bridge error: {type(exc).__name__}')

    return JSONResponse(openai_chat_completion(answer, model=payload.get('model') or 'omi'))


# The exact path Even posts to is not documented; the known implementation uses the
# root. Register the conventional OpenAI paths too so a firmware change that starts
# appending /v1/chat/completions does not silently break.
@app.post('/')
async def agent_root(request: Request) -> JSONResponse:
    return await _handle_agent(request)


@app.post('/v1/chat/completions')
async def agent_openai(request: Request) -> JSONResponse:
    return await _handle_agent(request)


@app.post('/chat/completions')
async def agent_openai_short(request: Request) -> JSONResponse:
    return await _handle_agent(request)


# ------------------------------------------------------ glasses plugin socket

_clients: set[WebSocket] = set()


async def _send(socket: WebSocket, payload: dict) -> None:
    with contextlib.suppress(Exception):
        await socket.send_text(json.dumps(payload))


async def broadcast(payload: dict) -> None:
    """Push to every connected glasses app (proactive surfacing)."""
    for socket in list(_clients):
        await _send(socket, payload)


async def _stream_chat_to(socket: WebSocket, text: str) -> None:
    """Stream an answer to the glasses, coalescing deltas.

    Every frame costs a BLE round trip, so tokens are batched into readable
    chunks instead of forwarded one at a time.
    """
    buffer: list[str] = []
    pending = 0
    full: list[str] = []
    error: str | None = None

    async for event in omi.chat_stream(text):
        if event.kind == 'data':
            buffer.append(event.text)
            full.append(event.text)
            pending += len(event.text)
            if pending >= 60:
                await _send(socket, {'type': 'chat_delta', 'text': ''.join(buffer)})
                buffer.clear()
                pending = 0
        elif event.kind == 'think':
            await _send(socket, {'type': 'chat_status', 'text': event.text[:60]})
        elif event.kind == 'error':
            error = event.text
            break
        elif event.kind == 'done':
            if event.text:
                full = [event.text]
            break

    if error:
        await _send(socket, {'type': 'chat_done', 'text': fit_for_glasses(f'Error: {error}'), 'error': True})
        return

    answer = ''.join(full).strip()
    fitted = fit_for_glasses(answer, limit=1800)  # textContainerUpgrade caps at 2000
    await _send(
        socket,
        {'type': 'chat_done', 'text': fitted, 'pages': paginate(fitted), 'error': False},
    )


@dataclass
class _AppSession:
    """Per-connection state for one glasses app.

    Binary frames mean two different things depending on mode: between
    `ask_start` and `ask_stop` they are a question being dictated, otherwise
    they are continuous capture headed for `/v4/listen`. Keeping the mode here
    rather than globally means two connected apps can't confuse each other.
    """

    capture: CaptureSession
    ask_active: bool = False
    ask_buffer: bytearray = field(default_factory=bytearray)


# 30s of PCM16 at 16kHz. The app caps recording well below this; the bound
# exists so a client that never sends `ask_stop` cannot grow memory forever.
MAX_ASK_BYTES = 16000 * 2 * 30


async def _handle_ask_stop(socket: WebSocket, session: _AppSession) -> None:
    """Transcribe the dictated question, echo it back, then answer it."""
    pcm = bytes(session.ask_buffer)
    session.ask_buffer.clear()
    session.ask_active = False

    seconds = len(pcm) / (16000 * 2)
    if seconds < 0.4:
        # Too short to be speech -- almost always a double-tap cancel or a
        # mis-tap. Answering "" would send an empty question to Omi.
        await _send(socket, {'type': 'ask_error', 'text': "Didn't catch that. Tap to retry."})
        return

    try:
        transcript = (await omi.transcribe_pcm(pcm)).strip()
    except Exception as exc:  # noqa: BLE001 - report, never kill the socket
        log.warning('transcription failed: %s', exc)
        await _send(socket, {'type': 'ask_error', 'text': 'Could not transcribe that.'})
        return

    log.info('ask: %.1fs of audio -> %r', seconds, transcript[:120])
    if not transcript:
        await _send(socket, {'type': 'ask_error', 'text': "Didn't catch that. Tap to retry."})
        return

    # Echo the transcript first so a misheard question is visible before the
    # answer arrives, rather than leaving the user guessing what was asked.
    await _send(socket, {'type': 'transcribed', 'text': fit_for_glasses(transcript, limit=200)})
    await _stream_chat_to(socket, transcript)


async def _handle_app_message(socket: WebSocket, payload: dict, session: _AppSession) -> None:
    kind = payload.get('type')

    if kind == 'ask_start':
        session.ask_active = True
        session.ask_buffer.clear()
        await _send(socket, {'type': 'ask_listening'})
        return

    if kind == 'ask_stop':
        if not session.ask_active and not session.ask_buffer:
            return  # idempotent: a cancel after an auto-stop is not an error
        await _handle_ask_stop(socket, session)
        return

    if kind == 'chat':
        question = (payload.get('text') or '').strip()
        if not question:
            await _send(socket, {'type': 'chat_done', 'text': 'Nothing to ask.', 'error': True})
            return
        await _stream_chat_to(socket, question)

    elif kind == 'memories':
        rows = await omi.memories(int(payload.get('limit') or 20))
        items = [{'content': fit_for_glasses(r.get('content', ''), limit=200)} for r in rows]
        await _send(socket, {'type': 'memories', 'items': items})

    elif kind == 'action_items':
        rows = await omi.action_items(int(payload.get('limit') or 20))
        items = [
            {
                'description': fit_for_glasses(r.get('description', ''), limit=120),
                'completed': bool(r.get('completed')),
            }
            for r in rows
        ]
        await _send(socket, {'type': 'action_items', 'items': items})

    elif kind == 'today':
        rows = await omi.daily_summaries(1)
        if rows:
            raw = rows[0].get('summary') or rows[0].get('overview') or ''
            text = fit_for_glasses(str(raw), limit=1800)
        else:
            text = 'No summary for today yet.'
        await _send(socket, {'type': 'today', 'text': text, 'pages': paginate(text)})

    elif kind == 'capture':
        if payload.get('enabled'):
            await session.capture.start()
            await _send(socket, {'type': 'capture', 'active': True})
        else:
            stats = await session.capture.stop(finalize=True)
            await _send(
                socket,
                {
                    'type': 'capture',
                    'active': False,
                    'seconds': round(stats.audio_seconds, 1),
                    'conversation_id': stats.conversation_id,
                },
            )

    elif kind == 'transcribe':
        # One-shot push-to-talk: the app buffered PCM and wants text back.
        pcm = bytes.fromhex(payload.get('pcm_hex', ''))
        transcript = await omi.transcribe_pcm(pcm) if pcm else ''
        await _send(socket, {'type': 'transcribed', 'text': transcript})

    elif kind == 'ping':
        await _send(socket, {'type': 'pong'})

    else:
        log.debug('unknown app message type: %s', kind)


@app.websocket('/app')
async def app_socket(socket: WebSocket) -> None:
    await socket.accept()
    _clients.add(socket)
    log.info('glasses app connected (%d total)', len(_clients))

    async def on_segments(segments: list[dict]) -> None:
        text = ' '.join(s.get('text', '') for s in segments if s.get('text')).strip()
        if text:
            await _send(socket, {'type': 'transcript', 'text': fit_for_glasses(text, limit=300)})

    session = _AppSession(capture=CaptureSession(auth, OMI_API_BASE, on_segments=on_segments))

    try:
        await _send(socket, {'type': 'hello', 'omi_api': OMI_API_BASE})
        while True:
            message = await socket.receive()
            if message.get('type') == 'websocket.disconnect':
                break

            if (data := message.get('bytes')) is not None:
                # Binary frames are microphone PCM straight from the glasses, and
                # mean different things depending on mode.
                if session.ask_active:
                    if len(session.ask_buffer) < MAX_ASK_BYTES:
                        session.ask_buffer.extend(data)
                    else:
                        # Stop accumulating rather than grow without bound; the
                        # question is already far longer than anyone speaks.
                        log.warning('ask buffer hit %d bytes; ignoring further audio', MAX_ASK_BYTES)
                else:
                    session.capture.feed(data)
                continue

            raw = message.get('text')
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue

            try:
                await _handle_app_message(socket, payload, session)
            except Exception as exc:  # noqa: BLE001 - one bad request must not kill the socket
                log.exception('app message failed')
                await _send(socket, {'type': 'error', 'text': f'{type(exc).__name__}: {exc}'})

    except WebSocketDisconnect:
        pass
    finally:
        _clients.discard(socket)
        with contextlib.suppress(Exception):
            await session.capture.stop(finalize=True)
        log.info('glasses app disconnected (%d left)', len(_clients))


# --------------------------------------------------------------- push polling


def _created_at(row: dict) -> str:
    """Sortable creation timestamp. Missing values sort oldest."""
    return str(row.get('created_at') or '')


async def _push_loop() -> None:
    """Surface newly created action items to any connected glasses app.

    Only reaches the glasses while the app is running -- the Hub host keeps a
    backgrounded plugin alive in a headless WebView, but a closed app receives
    nothing. There is no OS-level notification path in the SDK.

    `GET /v1/action-items` does **not** return newest-first: a freshly created task
    was observed at index 20 of 100, so polling a small window silently watched only
    the oldest tasks and could never fire. We therefore pull a generous window and
    sort by `created_at` ourselves rather than trusting server order.
    """
    interval = float(os.getenv('OMI_EVEN_PUSH_INTERVAL', '120'))
    window = int(os.getenv('OMI_EVEN_PUSH_WINDOW', '100'))
    seen: set[str] = set()
    first_pass = True

    while True:
        try:
            await asyncio.sleep(interval)
            if not _clients:
                continue

            rows = await omi.action_items(window)
            rows.sort(key=_created_at, reverse=True)

            if first_pass:
                # Seed, or every pre-existing task would push at once on startup.
                seen = {r['id'] for r in rows if r.get('id')}
                first_pass = False
                continue

            # Newest first, so the most recent task is announced first.
            for row in rows:
                item_id = row.get('id')
                if not item_id or item_id in seen:
                    continue
                seen.add(item_id)
                if row.get('completed'):
                    continue
                await broadcast(
                    {
                        'type': 'push',
                        'text': fit_for_glasses(f"New task: {row.get('description', '')}", limit=200),
                    }
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - a poll failure must not end the loop
            log.warning('push poll failed: %s', exc)
