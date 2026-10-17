"""Bounded PCM custody at the live admission boundary, before provider replay.

A one-second tail is flushed on disconnect, cancellation and ordinary failures.
A hard process kill can lose that uncommitted second; only published seconds are
reported to clients. No capture bytes or encryption work block the event loop.
"""

import asyncio
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
import time
import logging
import wave

from google.cloud import firestore

from database._client import get_firestore_client
from database.legal_holds import external_write_fence
from utils.executors import db_executor, storage_executor, run_blocking
from utils.sync import cap_hold

logger = logging.getLogger(__name__)

# Per UID / UTC month, across concurrent sockets and all channels. Reservations
# are conservative on upload failures. No audio is silently dropped at capacity.
MAX_MONTHLY_BYTES = 96 * 1024**3
MAX_MONTHLY_CHUNKS = 3_000_000
CHUNK_SECONDS = 1
MAX_PENDING_SECONDS = 60


def reserve(uid: str, size: int, *, month: str | None = None, recovery: bool = False) -> None:
    month = month or datetime.now(timezone.utc).strftime('%Y-%m')
    client = get_firestore_client()
    ref = client.collection('users').document(uid).collection('stt_cap_live_storage').document(month)

    @firestore.transactional
    def commit(tx):
        snap = ref.get(transaction=tx)
        row = snap.to_dict() if snap.exists else {}
        used, count = row.get('bytes', 0) + size, row.get('chunks', 0) + 1
        source_bytes = row.get('source_bytes', 0) + (0 if recovery else size)
        source_chunks = row.get('source_chunks', 0) + (0 if recovery else 1)
        if (
            used > 2 * MAX_MONTHLY_BYTES
            or count > 2 * MAX_MONTHLY_CHUNKS
            or source_bytes > MAX_MONTHLY_BYTES
            or source_chunks > MAX_MONTHLY_CHUNKS
        ):
            raise RuntimeError('live held audio storage capacity reached')
        tx.set(ref, {'bytes': used, 'chunks': count, 'source_bytes': source_bytes, 'source_chunks': source_chunks})

    with external_write_fence(uid):
        commit(client.transaction())


def write_wav(path, data, rate):
    with wave.open(path, 'wb') as output:
        output.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        output.writeframes(data)


class LiveHeldAudio:
    """Only unique, denied capture PCM enters this sink; replay has no append path."""

    def __init__(self, host):
        self.host = host
        self.pending = deque()
        self.pending_bytes = 0
        self.seconds = 0.0
        self.paused = False
        self.last_notice = None
        self.buffers = {}
        self._lock = asyncio.Lock()
        self._last_flush = time.monotonic()

    def append(self, data, rate, timestamp, conversation_id, channel=0):
        if not data:
            return
        buffered = self.pending_bytes + sum(len(item[0]) for item in self.buffers.values())
        if buffered + len(data) > MAX_PENDING_SECONDS * rate * 2:
            raise RuntimeError('live held audio packet exceeds custody bound')
        if len(data) % 2:
            raise ValueError('held PCM must contain whole PCM16 samples')
        self.paused = True
        key = (channel, rate, conversation_id)
        # Flush a channel at ownership/rate changes, never merge separate owners.
        for old in list(self.buffers):
            if old[0] == channel and old != key:
                self._queue(old)
        if key in self.buffers:
            existing, start = self.buffers[key]
            expected = start + len(existing) / (2 * rate)
            if abs(timestamp - expected) > 0.1:
                self._queue(key)  # Preserve real clock gaps, never concatenate them.
        if key not in self.buffers:
            self.buffers[key] = [bytearray(), timestamp]
        buffer, start = self.buffers[key]
        buffer.extend(data)
        while len(buffer) >= rate * 2 * CHUNK_SECONDS:
            size = rate * 2 * CHUNK_SECONDS
            self.pending.append((bytes(buffer[:size]), rate, start, conversation_id, channel))
            self.pending_bytes += size
            del buffer[:size]
            start += CHUNK_SECONDS
        self.buffers[key][1] = start
        if self.pending_bytes > MAX_PENDING_SECONDS * rate * 2:
            raise RuntimeError('live held audio persistence backpressure')

    def _queue(self, key):
        buffer, start = self.buffers.pop(key)
        if buffer:
            channel, rate, owner = key
            self.pending.append((bytes(buffer), rate, start, owner, channel))
            self.pending_bytes += len(buffer)

    async def flush(self, *, force=False):
        async with self._lock:
            if force or time.monotonic() - self._last_flush >= CHUNK_SECONDS:
                for key in list(self.buffers):
                    self._queue(key)
            while self.pending:
                data, rate, start, owner, channel = self.pending[0]
                # Header + authenticated chunk framing; quota reserves before
                # any upload. Frozen recovery pieces are bounded by this source.
                size = len(data) + 44
                size += 32 * ((size + cap_hold.AUDIO_CHUNK_BYTES - 1) // cap_hold.AUDIO_CHUNK_BYTES)
                month = datetime.fromtimestamp(start, timezone.utc).strftime('%Y-%m')
                await run_blocking(db_executor, reserve, self.host.request.uid, size, month=month)
                directory = await run_blocking(storage_executor, cap_hold.recovery_directory, self.host.request.uid)
                try:
                    path = str(Path(directory.name) / f'{start:.6f}.wav')
                    await run_blocking(storage_executor, write_wav, path, data, rate)
                    context = getattr(self.host, 'client_device_context', None)
                    await cap_hold._hold_capture(
                        self.host.request.uid,
                        path,
                        {
                            'origin': 'live',
                            'live_storage_month': month,
                            'timestamp': start,
                            'source': getattr(self.host.request.source, 'value', self.host.request.source) or 'omi',
                            'target_conversation_id': owner,
                            'recording_session_id': str(self.host.session_id),
                            'client_device_id': getattr(context, 'device_id', None),
                            'channel': channel,
                            'file_name': Path(path).name,
                            # Preserve short live chunks: ordinary sync VAD drops
                            # sub-second pieces. This PCM is already decoded and
                            # has no WAL coverage or lineage planning to replay.
                            'full_capture': False,
                        },
                        getattr(getattr(self.host.state, 'stt_cap_admission', None), 'reason', 'allowance_unavailable'),
                        {},
                    )
                finally:
                    await run_blocking(storage_executor, directory.cleanup)
                self.seconds += len(data) / (2 * rate)
                self.pending.popleft()
                self.pending_bytes -= len(data)
            self._last_flush = time.monotonic()

    async def notice(self, *, paused=None):
        if paused is not None:
            self.paused = paused
        state = (self.paused, int(self.seconds))
        if state == self.last_notice or (not self.paused and not self.seconds):
            return
        from models.message_event import SttCapLiveHeldEvent
        from utils.sync.held_audio_summary import next_utc_month_start

        try:
            await self.host.request.websocket.send_json(
                SttCapLiveHeldEvent(
                    session_id=str(self.host.session_id),
                    held_seconds=state[1],
                    paused=state[0],
                    reset_at=next_utc_month_start(),
                ).to_json()
            )
        except Exception as error:
            logger.info('event=stt_cap_live_held outcome=notify_deferred exception_type=%s', type(error).__name__)
            return  # The durable counter remains available; retry on the next packet.
        self.last_notice = state

    def observe(self, receiver, data, rate, start, admitted):
        # The adapter reports capture coordinates, before replay can repeat them.
        # Keep a bounded union, preserving holes (e.g. VAD-dropped silence).
        end = start + len(data) // 2
        spans = receiver._cap_decided_spans
        cursor = start
        if not admitted:
            for left, right in [*spans, (end, end)]:
                if right <= cursor:
                    continue
                if left > cursor:
                    stop = min(left, end)
                    if stop > cursor:
                        timeline = getattr(receiver, 'capture_timeline', None)
                        cuts = {cursor, stop}
                        for left_owner, right_owner, _ in receiver.host.state.conversation_sample_ranges or []:
                            if cursor < left_owner < stop:
                                cuts.add(left_owner)
                            if cursor < right_owner < stop:
                                cuts.add(right_owner)
                        boundaries = sorted(cuts)
                        for first, last in zip(boundaries, boundaries[1:]):
                            timestamp = (
                                timeline.wall(first) if timeline is not None else time.time() - (end - first) / rate
                            )
                            self.append(
                                data[(first - start) * 2 : (last - start) * 2],
                                rate,
                                timestamp,
                                receiver._owner_for_sample(first),
                            )
                cursor = max(cursor, right)
                if cursor >= end:
                    break
        spans.append((start, end))
        spans.sort()
        merged = []
        for left, right in spans:
            if merged and left <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(right, merged[-1][1]))
            else:
                merged.append((left, right))
        # Older replay than the retention horizon has already had an ownership
        # decision. Collapse evicted spans to a prefix rather than retaining PCM.
        if len(merged) > 512:
            merged = [(0, merged[-512][1]), *merged[-511:]]
        receiver._cap_decided_spans = merged

    async def run_updates(self, receiver):
        while not receiver._cap_hold_stop.is_set():
            try:
                await asyncio.wait_for(receiver._cap_hold_stop.wait(), timeout=1)
            except asyncio.TimeoutError:
                pass
            if receiver._cap_hold_stop.is_set():
                return
            await receiver._emit_stt_cap_live_held()
            if self.paused and not receiver.cap_admission.funded_paused and not receiver.cap_paused:
                await self.flush(force=True)
                await self.notice(paused=False)

    async def close(self):
        await self.flush(force=True)
        await self.notice()
