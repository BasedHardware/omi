"""Synthetic route gate; run in /app with python -m scripts.qualify_parakeet_route.

Uses the served backend clients, never application/user endpoints or credentials.
Stdout is JSONL; admission refusals are receipts and block qualification (exit 1).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import logging
import math
import os
from pathlib import Path
import time
from typing import Any, Callable
from urllib.parse import urlsplit
import wave

import httpx

SAMPLE_RATE = 16000
CORPUS = Path(__file__).with_name('fixtures') / 'parakeet_route_synthetic.wav'
REFUSALS = {'capacity_full', 'allocation_rejected', 'queue_timeout'}


class QualificationFailure(ValueError):
    """Fixed, safe diagnostic for a failed protocol assertion."""

    def __init__(self, reason: str, diagnostics: dict[str, Any] | None = None):
        super().__init__(reason)
        self.diagnostics = diagnostics or {}


def load_corpus() -> tuple[bytes, bytes]:
    wav = CORPUS.read_bytes()
    if len(wav) > 200_000:
        raise QualificationFailure('synthetic corpus exceeds 200 KB')
    with wave.open(io.BytesIO(wav)) as audio:
        if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) != (SAMPLE_RATE, 1, 2):
            raise QualificationFailure('corpus must be mono PCM16 at 16 kHz')
        pcm = audio.readframes(audio.getnframes())
    return wav, pcm


def load_clients() -> tuple[Any, Any, Any]:
    # Dockerfile COPY backend/ . + WORKDIR /app: top-level utils and scripts,
    # not backend.utils. Keep --help free of backend initialization/imports.
    from utils.stt import pre_recorded, streaming
    from utils.stt.parakeet_window import WindowedParakeetSocket

    return streaming, WindowedParakeetSocket, pre_recorded


def refusal_reason(error: BaseException) -> str | None:
    seen: set[int] = set()
    while id(error) not in seen:
        seen.add(id(error))
        reason = getattr(error, 'reason', None)
        if reason in REFUSALS:
            return reason
        if isinstance(error, httpx.HTTPStatusError):
            response = error.response
            reason = response.headers.get('X-Omi-STT-Error')
            if response.status_code == 429:
                return 'rate_limited'
            if response.status_code == 503 and reason in REFUSALS:
                return reason
        cause = error.__cause__ or error.__context__
        if cause is None:
            break
        error = cause
    return None


def require_response(response: httpx.Response, endpoint: str) -> None:
    response.raise_for_status()
    if response.status_code != 200 or response.request.url.path.rstrip('/').split('/')[-2:] != [endpoint, 'transcribe']:
        raise QualificationFailure('expected exact endpoint and HTTP 200; no legacy fallback')


async def window_check(window_client: Any, base: str, pcm: bytes) -> dict[str, Any]:
    socket = window_client(lambda _: None, base, SAMPLE_RATE, lambda: None)
    # Use the real live-window WAV, AGC, admission semaphore and budget headers.
    # No pump/VAD model, speaker lookup or fallback provider is started.
    response = await socket._post_window(pcm)
    require_response(response, 'v1')
    payload = response.json()
    segments = payload.get('segments', [])
    text = payload.get('text') or ' '.join(segment.get('text', '') for segment in segments)
    if not text.strip():
        raise QualificationFailure('empty window transcript for speech')
    return {'http_status': 200, 'text': text}


class CheckedHttpx:
    """Observe the existing sync client's responses without changing its payload.

    This proxy is scoped to pre_recorded.httpx in this standalone process; it
    never replaces the shared httpx module or changes served backend source.
    """

    def Client(self, **kwargs: Any) -> httpx.Client:
        return httpx.Client(event_hooks={'response': [lambda response: require_response(response, 'v2')]}, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(httpx, name)


async def prerecorded_check(client: Any, wav: bytes, timeout: float) -> dict[str, Any]:
    def transcribe() -> dict[str, Any]:
        original_httpx = client.httpx
        client.httpx = CheckedHttpx()
        try:
            # One attempt, with the real served payload/normalizer. Response
            # observation forbids v2->v1 fallback before it can hide a bad route.
            with client.verification_stt_deadline(time.monotonic() + timeout):
                words = client.parakeet_prerecorded_from_bytes(wav, diarize=True, attempts=1)
        finally:
            client.httpx = original_httpx
        text = ' '.join(word['text'] for word in words)
        if not text.strip():
            raise QualificationFailure('empty prerecorded transcript for speech')
        return {'http_status': 200, 'text': text}

    return await asyncio.to_thread(transcribe)


# Pinned websockets 12 ConnectionClosedOK: 1000, 1001, or an empty frame (1005).
CLEAN_CLOSE_CODES = {1000, 1001, 1005}


def task_state(task: asyncio.Task[Any] | None) -> dict[str, Any]:
    if task is None:
        return {'state': 'missing'}
    if not task.done():
        return {'state': 'pending'}
    if task.cancelled():
        return {'state': 'cancelled'}
    error = task.exception()
    return {'state': 'error', 'exception_type': type(error).__name__} if error else {'state': 'completed'}


def close_diagnostics(socket: Any) -> dict[str, Any]:
    ws = socket._ws
    return {
        'close_code': getattr(ws, 'close_code', None),
        'close_reason': getattr(ws, 'close_reason', None),
        'sender_task': task_state(socket._sender_task),
        'receiver_task': task_state(socket._receiver_task),
    }


async def stream_check(streaming: Any, base: str, pcm: bytes, idle_seconds: float = 0) -> dict[str, Any]:
    segments: list[dict[str, Any]] = []
    first_text = asyncio.Event()
    sent_bytes = 0
    finalize_sent = False
    invalid_reason: str | None = None
    first_text_at: float | None = None
    started = time.monotonic()
    spans: list[dict[str, float | None]] = []
    overlap_count = 0
    past_sent_count = 0

    def receive(batch: list[dict[str, Any]]) -> None:
        nonlocal invalid_reason, first_text_at, overlap_count, past_sent_count
        for segment in batch:
            start = end = None
            try:
                start, end = float(segment['start']), float(segment['end'])
                if not (math.isfinite(start) and math.isfinite(end) and 0 <= start <= end):
                    invalid_reason = invalid_reason or 'bad start/end: expected finite 0 <= start <= end'
                else:
                    if spans and spans[-1]['end'] is not None and start < spans[-1]['end']:
                        overlap_count += 1
                    if end > sent_bytes / (SAMPLE_RATE * 2):
                        past_sent_count += 1
                if not isinstance(segment.get('text'), str) or not segment['text'].strip():
                    invalid_reason = invalid_reason or 'empty text segment'
                elif not sent_bytes:
                    invalid_reason = invalid_reason or 'text before PCM was sent'
                else:
                    if first_text_at is None:
                        first_text_at = time.monotonic() - started
                    first_text.set()
            except (KeyError, TypeError, ValueError):
                invalid_reason = invalid_reason or 'bad start/end: missing or nonnumeric timestamp'
            spans.append(
                {
                    'start': start if start is not None and math.isfinite(start) else None,
                    'end': end if end is not None and math.isfinite(end) else None,
                }
            )
            segments.append(segment)

    # main.py sends StreamSession.feed()/flush() segments unchanged. The RNNT
    # decoder yields cumulative hypotheses; _new_streaming_text_since_last_emit
    # removes their shared text, not their time span. Revisions can reuse spans.
    # _build_segments uses utterance bounds, not word alignment; a zero speech
    # start also falls through to stream_offset_s in _transcribe_utterance.
    # Partial decoder input is right-padded. Neither the served receive loop nor
    # TranscriptSegment.combine_segments imposes a bytes-sent right edge or
    # disjointness: chronological overlaps merge, late arrivals remain separate.
    # Validate each span, preserve wire order, never invent a word-time bound.
    url = base.replace('https://', 'wss://', 1).replace('http://', 'ws://', 1).rstrip('/') + '/v3/stream'
    socket = streaming.ParakeetWebSocketSocket(receive, url, SAMPLE_RATE)
    try:
        # Existing start() validates ready, after websockets validates status 101.
        # The pinned websockets 12 client exposes response_headers, not status.
        await socket.start()
        ws = socket._ws
        original_send = ws.send

        async def observe_send(data: Any) -> None:
            nonlocal finalize_sent
            await original_send(data)
            if data == 'finalize':
                finalize_sent = True

        # Observe successful wire writes; queuing drain alone isn't proof that
        # finalize was sent. Keep the served client's payload/control flow.
        ws.send = observe_send
        if not ws.open or ws.response_headers.get('Upgrade', '').lower() != 'websocket':
            raise QualificationFailure('WebSocket upgrade was not confirmed')
        await asyncio.sleep(idle_seconds)
        if socket.is_connection_dead or not ws.open:
            raise QualificationFailure('connection dead while idle')
        chunk_bytes = SAMPLE_RATE * 2 // 10
        for offset in range(0, len(pcm), chunk_bytes):
            chunk = pcm[offset : offset + chunk_bytes]
            if not socket.send(chunk):
                raise QualificationFailure('connection dead or PCM send rejected')
            sent_bytes += len(chunk)
            await asyncio.sleep(len(chunk) / (SAMPLE_RATE * 2))
        # Require bidirectional delivery before sending finalize, not only text
        # returned from a buffered upload at close. Corpus includes trailing quiet.
        try:
            await asyncio.wait_for(first_text.wait(), timeout=15)
        except TimeoutError as error:
            raise QualificationFailure(
                invalid_reason or ('connection dead' if socket.is_connection_dead else 'empty text before finalize')
            ) from error
        if invalid_reason or socket.is_connection_dead:
            raise QualificationFailure(invalid_reason or 'connection dead before finalize')
        await socket.drain_and_close()  # Existing client sends literal "finalize".
        if invalid_reason or socket.is_connection_dead:
            raise QualificationFailure(invalid_reason or 'connection dead during finalize')
        states = {
            name: task_state(task)['state']
            for name, task in (('sender', socket._sender_task), ('receiver', socket._receiver_task))
        }
        for name, state in states.items():
            if state in {'missing', 'pending', 'error'}:
                raise QualificationFailure(f'stream finalization left {name} task {state}')
        if ws.close_code == 1006:
            # Lead-ratified legacy parity: main.py flushes then returns without
            # a close frame. This exception requires actual finalize delivery,
            # validated speech before it, and both tasks completed normally.
            if not finalize_sent or first_text_at is None or any(state != 'completed' for state in states.values()):
                raise QualificationFailure('1006 without sent finalize, prior speech and completed tasks')
            close_kind = 'server_dropped_after_finalize'
        elif ws.close_code in CLEAN_CLOSE_CODES:
            close_kind = 'normal'
        else:
            raise QualificationFailure('stream finished with abnormal or missing close code')
        return {
            'http_status': 101,
            'finalize_sent': finalize_sent,
            'close_kind': close_kind,
            'sample_rate': SAMPLE_RATE,
            'ready': True,
            'pcm_bytes': sent_bytes,
            'segments': len(segments),
            'segment_spans': spans[:5],
            'is_connection_dead': socket.is_connection_dead,
            'overlap_against_previous_end': overlap_count,
            'end_past_bytes_sent': past_sent_count,
            'first_text_ms': round((first_text_at or 0) * 1000, 2),
            **close_diagnostics(socket),
            'idle_seconds': idle_seconds,
            'text': ' '.join(str(segment['text']) for segment in segments),
        }
    except BaseException as error:
        diagnostics = {
            'finalize_sent': finalize_sent,
            'segment_spans': spans[:5],
            'is_connection_dead': socket.is_connection_dead,
            'overlap_against_previous_end': overlap_count,
            'end_past_bytes_sent': past_sent_count,
            **close_diagnostics(socket),
        }
        if isinstance(error, asyncio.CancelledError):
            raise QualificationFailure('stream timeout before qualification completed', diagnostics) from error
        setattr(error, 'diagnostics', diagnostics)
        raise
    finally:
        # Bound cleanup even if the check timed out or admission was refused.
        socket._closed = True
        tasks = [task for task in (socket._sender_task, socket._receiver_task) if task is not None]
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if socket._ws is not None:
            await socket._ws.close()


async def receipt(check: str, action: Callable[[], Any], timeout: float, common: dict[str, Any]) -> bool:
    started = time.monotonic()
    result: dict[str, Any] = {}
    try:
        async with asyncio.timeout(timeout):
            result = await action()
        result['outcome'] = 'pass'
    except Exception as error:
        reason = refusal_reason(error)
        result = {
            'outcome': 'refused' if reason else 'fail',
            'reason': reason or (str(error) if isinstance(error, QualificationFailure) else type(error).__name__),
            **getattr(error, 'diagnostics', {}),
        }
    text = result.pop('text', '')
    print(
        json.dumps(
            {
                **common,
                'check': check,
                'latency_ms': round((time.monotonic() - started) * 1000, 2),
                'first_words': ' '.join(text.split()[:12]),
                **result,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return result['outcome'] == 'pass'


async def qualify(args: argparse.Namespace) -> int:
    os.environ['HOSTED_PARAKEET_API_URL'] = args.base
    os.environ['PARAKEET_USE_V2'] = '1'
    streaming, window_client, prerecorded = load_clients()
    wav, pcm = load_corpus()
    common = {'base': args.base, 'corpus_sha256': hashlib.sha256(wav).hexdigest(), 'concurrency': args.concurrency}
    checks = [await receipt('v1_window', lambda: window_check(window_client, args.base, pcm), args.timeout, common)]
    checks.append(
        await receipt('v2_prerecorded', lambda: prerecorded_check(prerecorded, wav, args.timeout), args.timeout, common)
    )
    checks.extend(
        await asyncio.gather(
            *(
                receipt(f'v3_stream_{index}', lambda: stream_check(streaming, args.base, pcm), args.timeout, common)
                for index in range(args.concurrency)
            )
        )
    )
    # Run after parallel streams release admission leases: one idle connection,
    # then a fresh reconnect that must deliver speech again, not just handshake.
    checks.append(
        await receipt(
            'v3_idle', lambda: stream_check(streaming, args.base, pcm, args.idle_seconds), args.timeout, common
        )
    )
    checks.append(await receipt('v3_reconnect', lambda: stream_check(streaming, args.base, pcm), args.timeout, common))
    from utils.http_client import close_all_clients

    await close_all_clients()
    return 0 if all(checks) else 1


def arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True)
    parser.add_argument('--corpus', choices=['synthetic'], default='synthetic')
    parser.add_argument('--concurrency', type=int, choices=range(1, 9), default=4)
    parser.add_argument('--timeout', type=float, default=120, help='Per-check deadline in seconds (maximum 120).')
    parser.add_argument(
        '--idle-seconds',
        type=float,
        default=35,
        help='Quiet wall-clock interval; default crosses server receive timeout.',
    )
    args = parser.parse_args(argv)
    url = urlsplit(args.base)
    if (
        url.scheme not in ('http', 'https')
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
    ):
        parser.error('--base must be an HTTP(S) service URL without credentials/query/fragment')
    if url.hostname.lower() == 'api.omi.me':
        parser.error('application/user endpoint is forbidden')
    if not math.isfinite(args.timeout) or not 10 <= args.timeout <= 120:
        parser.error('--timeout must be between 10 and 120 seconds')
    if not math.isfinite(args.idle_seconds) or not 0 <= args.idle_seconds < args.timeout - 10:
        parser.error('--idle-seconds must leave at least 10 seconds in the check deadline')
    return args


def main() -> int:
    args = arguments()
    logging.basicConfig(level=logging.ERROR)  # Client diagnostics go to stderr.
    try:
        return asyncio.run(qualify(args))
    except Exception as error:
        print(
            json.dumps(
                {
                    'check': 'setup',
                    'outcome': 'fail',
                    'latency_ms': 0,
                    'first_words': '',
                    'reason': type(error).__name__,
                }
            ),
            flush=True,
        )
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
