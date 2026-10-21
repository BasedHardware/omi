"""Bounded PCM custody at the live admission boundary, before provider replay.

Pending PCM is bounded to 15 seconds (60 with the fragment kill switch off) and supervised cleanup flushes socket tails.
A hard process kill can lose that pending PCM; only published seconds are
reported to clients. No capture bytes or encryption work block the event loop.
"""

import asyncio
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
import time
import logging
import hashlib
import json
from typing import Any
import os
from utils.sync.cap_hold_lifecycle import ACTIVE as _ACTIVE, observe_publication

from google.cloud import firestore

from database._client import get_firestore_client, run_transactional
from database.legal_holds import external_write_fence
from utils.executors import db_executor, storage_executor, run_blocking
from utils.observability.held_content import record_capture
from utils.sync import cap_hold, live_cap_manifest, live_cap_capacity, live_cap_codec, live_cap_staging, live_cap_upload
from utils.sync.live_cap_publication import Publication

logger = logging.getLogger(__name__)

# Legacy v3 PCM reservations remain readable/recoverable. New Opus source
# reservations use live_cap_capacity; failures never silently discard audio.
MAX_MONTHLY_BYTES = 96 * 1024**3
MAX_MONTHLY_CHUNKS = 3_000_000
CHUNK_SECONDS = 60
MAX_PENDING_SECONDS = 15


def fragments_enabled() -> bool:
    return os.getenv('CAP_HOLD_LIVE_FRAGMENT_ENABLED', 'true').lower() == 'true'


def _upload_audio(
    uid: str,
    data: bytes,
    rate: int,
    start: float,
    group: Publication | None,
    source: Publication,
    metadata: dict,
    duration: float,
) -> dict:
    """One executor leaf owns scratch until the actual upload has completed.

    Cancelling the async waiter cannot run a finally that unlinks a file still
    used by this thread. A queued cancelled call never creates any scratch.
    """
    with cap_hold.recovery_directory(uid) as directory:
        path = str(Path(directory) / f'{start:.6f}.opus')
        live_cap_codec.encode(
            path, data, rate, **({'max_bytes': live_cap_staging.MAX_FRAGMENT_BYTES} if group is not None else {})
        )
        return cap_hold.upload_held_audio(
            uid,
            path,
            source.identity,
            metadata,
            immutable=True,
            live_size_limit=(
                live_cap_staging.MAX_FRAGMENT_BYTES if group is not None else live_cap_codec.MAX_OBJECT_BYTES
            ),
            rpc_timeout=live_cap_upload.UPLOAD_SOCKET_SECONDS,
        )


async def _publish_audio(
    uid: str,
    data: bytes,
    rate: int,
    start: float,
    group: Publication | None,
    source: Publication,
    metadata: dict,
    duration: float,
) -> None:
    await live_cap_upload.prepare(
        source, lambda: _upload_audio(uid, data, rate, start, group, source, metadata, duration)
    )
    # Only the coordinator can advance to commit. A late upload cannot do so.
    if group is None:
        await run_blocking(storage_executor, live_cap_manifest.publish, uid, '', source, metadata, duration)
    else:
        await run_blocking(storage_executor, live_cap_staging.append, uid, '', group, source, metadata, duration)


def reserve(
    uid: str, size: int, *, month: str | None = None, recovery: bool = False, reservation_id: str | None = None
) -> None:
    month = month or datetime.now(timezone.utc).strftime('%Y-%m')
    client = get_firestore_client()
    ref = client.collection('users').document(uid).collection('stt_cap_live_storage').document(month)

    receipt = ref.collection('reservations').document(reservation_id) if reservation_id else None

    @firestore.transactional
    def commit(tx: Any) -> None:
        if receipt is not None and receipt.get(transaction=tx).exists:
            return
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
        if receipt is not None:
            tx.create(receipt, {'bytes': size})

    with external_write_fence(uid):
        run_transactional(client, commit, transient=True)


class LiveHeldAudio:
    """Only unique, denied capture PCM enters this sink; replay has no append path."""

    def __init__(self, host: Any) -> None:
        self.host = host
        _ACTIVE.add(self)
        self.fragmented = fragments_enabled()
        self.bound = MAX_PENDING_SECONDS if self.fragmented else CHUNK_SECONDS
        self._group = None
        self._group_key = None
        self._group_seconds = 0.0
        self._group_end = 0.0
        self._group_parts = 0
        self._capacity_uncertain = False
        self.pending = deque()
        self.pending_bytes = 0
        self.seconds = 0.0
        self.paused = False
        self.last_notice = None
        self.buffers = {}
        self.capacity: live_cap_capacity.Capacity | None = None
        self.capacity_identity: str | None = None
        self._summary_ready = False
        self._charged: set[str] = set()
        self._publications: dict[str, Publication] = {}
        self._buffer_opened = {}
        self._lock = asyncio.Lock()

    def append(self, data: bytes, rate: int, timestamp: float, conversation_id: str | None, channel: int = 0) -> None:
        # Reserve against the capture month, including packets straddling reset.
        from calendar import timegm
        from math import ceil

        if len(data) % 2 or rate <= 0:
            raise ValueError('held PCM requires whole samples and a positive rate')
        while data:
            moment = datetime.fromtimestamp(timestamp, timezone.utc)
            year, month = (moment.year + 1, 1) if moment.month == 12 else (moment.year, moment.month + 1)
            boundary = timegm((year, month, 1, 0, 0, 0))
            frames = min(len(data) // 2, max(1, ceil((boundary - timestamp) * rate)))
            size = frames * 2
            self._append(data[:size], rate, timestamp, conversation_id, channel)
            data = data[size:]
            timestamp += frames / rate
            if data:
                self._queue((channel, rate, conversation_id))

    def _append(self, data: bytes, rate: int, timestamp: float, conversation_id: str | None, channel: int) -> None:
        if not data:
            return
        if self.buffered_seconds() + len(data) / (2 * rate) > self.bound + 1e-9:
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
            if (
                abs(timestamp - expected) > 0.1
                or datetime.fromtimestamp(start, timezone.utc).month
                != datetime.fromtimestamp(timestamp, timezone.utc).month
            ):
                self._queue(key)  # Preserve real clock gaps, never concatenate them.
        if key not in self.buffers:
            self.buffers[key] = [bytearray(), timestamp]
            self._buffer_opened[key] = time.monotonic()
        buffer, start = self.buffers[key]
        buffer.extend(data)
        emitted = False
        while len(buffer) >= rate * 2 * self.bound:
            size = rate * 2 * self.bound
            self.pending.append((bytes(buffer[:size]), rate, start, conversation_id, channel))
            self.pending_bytes += size
            del buffer[:size]
            start += self.bound
            emitted = True
        if emitted:
            self._buffer_opened[key] = time.monotonic()
        self.buffers[key][1] = start
        if self.buffered_seconds() > self.bound + 1e-9:
            raise RuntimeError('live held audio persistence backpressure')

    def buffered_seconds(self) -> float:
        return sum(len(item[0]) / (2 * item[1]) for item in self.pending) + sum(
            len(value[0]) / (2 * key[1]) for key, value in self.buffers.items()
        )

    async def _packet_parts(self, data: bytes, rate: int):
        # The caller retains the ingress packet while each complete minute is
        # published. Custody itself never accepts a straddle tail above 60s.
        if rate <= 0 or len(data) % 2:
            raise ValueError('held PCM requires whole samples and a positive rate')
        while data:
            frames = int((self.bound - self.buffered_seconds()) * rate + 1e-6)
            if frames <= 0:
                await self.flush(force=True, seal=False)
                continue
            size = min(len(data), frames * 2)
            yield data[:size]
            data = data[size:]

    async def append_async(
        self, data: bytes, rate: int, timestamp: float, conversation_id: str | None, channel: int = 0
    ) -> None:
        async for part in self._packet_parts(data, rate):
            self.append(part, rate, timestamp, conversation_id, channel)
            timestamp += len(part) / (2 * rate)

    async def observe_async(self, receiver: Any, data: bytes, rate: int, start: int, admitted: bool) -> None:
        async for part in self._packet_parts(data, rate):
            self.observe(receiver, part, rate, start, admitted)
            start += len(part) // 2

    def _queue(self, key: tuple[int, int, str | None]) -> None:
        buffer, start = self.buffers.pop(key)
        self._buffer_opened.pop(key, None)
        if buffer:
            channel, rate, owner = key
            self.pending.append((bytes(buffer), rate, start, owner, channel))
            self.pending_bytes += len(buffer)

    async def flush(self, *, force: bool = False, seal: bool = True) -> None:
        # Callers include host-owned updater/receive tasks. Their cancellation
        # must not release the lock or delete a source beneath an executor upload.
        custody = asyncio.create_task(self._flush(force=force, seal=seal), name='stt_cap_live_publish')
        self._custody = custody
        custody.add_done_callback(observe_publication)
        try:
            await asyncio.shield(custody)
        except asyncio.CancelledError:
            # Keep ownership until the executor has stopped using the scratch
            # file. Shutdown also awaits active sinks before closing clients.
            # The sink retains the task and the lock; its own coroutine keeps
            # scratch/PCM alive. Socket and lifespan close await the same lock.
            raise

    async def _seal_group(self) -> None:
        if self._group is None:
            return
        await run_blocking(storage_executor, live_cap_staging.seal, self.host.request.uid, self._group.identity)
        self.seconds += self._group_seconds
        self._group = None
        self._group_key = None
        self._group_seconds = 0.0
        self._group_parts = 0

    async def _reserve_capacity(self, month: str) -> None:
        if self.capacity is not None and self.capacity.month != month:
            await run_blocking(db_executor, live_cap_capacity.release, self.capacity)
            self.capacity = None
        if self.capacity is None or (self.capacity.used == live_cap_capacity.BLOCK_GROUPS and self._group is None):
            from uuid import uuid4

            # Preserve the acquisition key across an ambiguous transaction reply.
            self.capacity_identity = self.capacity_identity or uuid4().hex
            self.capacity = await run_blocking(
                db_executor,
                live_cap_capacity.acquire,
                self.host.request.uid,
                month,
                self.capacity_identity,
            )
            self.capacity_identity = None

    async def _flush(self, *, force: bool = False, seal: bool = True) -> None:
        async with self._lock:
            for key in list(self.buffers):
                if force or time.monotonic() - self._buffer_opened[key] >= self.bound:
                    self._queue(key)
            if self.fragmented and self._group_parts == live_cap_staging.MAX_FRAGMENTS:
                await self._seal_group()
            while self.pending:
                data, rate, start, owner, channel = self.pending[0]
                month = datetime.fromtimestamp(start, timezone.utc).strftime('%Y-%m')
                context = getattr(self.host, 'client_device_context', None)
                metadata = {
                    'origin': 'live',
                    'live_storage_month': month,
                    'timestamp': start,
                    'source': getattr(self.host.request.source, 'value', self.host.request.source) or 'omi',
                    'target_conversation_id': owner,
                    'recording_session_id': str(self.host.session_id),
                    'client_device_id': getattr(context, 'client_device_id', None),
                    'channel': channel,
                    'file_name': f'{start:.6f}.wav',
                    'full_capture': True,
                    'audio_codec': 'ogg_opus',
                    'sample_rate': rate,
                    'source_frames': len(data) // 2,
                    'live_custody_version': 4,
                }
                # Logical capture key retains one opaque Publication across
                # retries, independent of encoder randomness.
                identity = hashlib.sha256(data + json.dumps(metadata, sort_keys=True).encode()).hexdigest()
                duration = len(data) / (rate * 2)
                key = (channel, rate, owner, month)
                if (
                    self.fragmented
                    and self._group is not None
                    and (key != self._group_key or (self._group_parts > 0 and abs(start - self._group_end) > 0.1))
                ):
                    await self._seal_group()
                if not self._summary_ready:
                    await run_blocking(db_executor, cap_hold.ensure_summary, self.host.request.uid)
                    self._summary_ready = True
                source = self._publications.setdefault(identity, Publication(self.host.request.uid))
                retry = identity in self._charged
                # Reconcile an ambiguous block rollover even when this
                # fragment already owns a retry marker.
                await self._reserve_capacity(month)
                if not retry:
                    # Capacity is reserved before IO, consumed only once a
                    # durable receipt is known. An uncertain attempt cannot
                    # refund this slot on close until it is reconciled.
                    self._capacity_uncertain = True
                    self._charged.add(identity)
                capacity = self.capacity
                if capacity is None:
                    raise RuntimeError('live held audio lacks reserved capacity')
                if self.fragmented:
                    if self._group is None:
                        self._group = Publication(self.host.request.uid)
                        self._group_key = key
                    try:
                        await _publish_audio(
                            self.host.request.uid,
                            data,
                            rate,
                            start,
                            self._group,
                            source,
                            metadata,
                            duration,
                        )
                    except live_cap_staging.SourceSealed:
                        # The periodic sweeper may have sealed an idle writer.
                        # Only never-committed fragments roll into a fresh group;
                        # duplicate IDs (even purged) were reconciled above.
                        await self._seal_group()
                        await self._reserve_capacity(month)
                        capacity = self.capacity
                        if capacity is None:
                            raise RuntimeError('live held audio lacks reserved capacity')
                        self._group = Publication(self.host.request.uid)
                        self._group_key = key
                        await _publish_audio(
                            self.host.request.uid,
                            data,
                            rate,
                            start,
                            self._group,
                            source,
                            metadata,
                            duration,
                        )
                    # Reserve one minute slot for the group's peak footprint.
                    if self._group_parts == 0:
                        capacity.consume()
                    self._capacity_uncertain = False
                    self._group_parts += 1
                    self._group_seconds += duration
                    self._group_end = start + duration
                else:
                    await _publish_audio(
                        self.host.request.uid,
                        data,
                        rate,
                        start,
                        None,
                        source,
                        metadata,
                        duration,
                    )
                    capacity.consume()
                    self._capacity_uncertain = False
                # No await between durable publication and retiring bytes.
                if not self.fragmented:
                    self.seconds += duration
                self.pending.popleft()
                self.pending_bytes -= len(data)
                self._charged.discard(identity)
                self._publications.pop(identity, None)
                if self.fragmented and (
                    self._group_parts == live_cap_staging.MAX_FRAGMENTS or self._group_seconds >= CHUNK_SECONDS
                ):
                    await self._seal_group()
                cap_hold.record_audio(
                    'live',
                    'held',
                    'unknown',
                    duration,
                    getattr(getattr(self.host.state, 'stt_cap_admission', None), 'reason', '')
                    == 'plan_allowance_exhausted',
                )
            if self.fragmented and force and seal:
                await self._seal_group()

    async def seal(self, channel: int | None = None) -> None:
        # Source groups are immutable and born sealed in their publication tx.
        # Preserve the explicit flush barrier used by resume and close callers.
        await self.flush(force=True)

    async def notice(self, *, paused: bool | None = None) -> None:
        if paused is False:
            await self.seal()
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

    def observe(self, receiver: Any, data: bytes, rate: int, start: int, admitted: bool) -> None:
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

    async def run_updates(self, receiver: Any) -> None:
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

    async def finish_updates(self, updates: asyncio.Task | None, stop: asyncio.Event) -> None:
        stop.set()
        if updates is not None:
            try:
                await updates
            except asyncio.CancelledError:
                pass
            except Exception as error:
                logger.warning('event=stt_cap_live_held outcome=update_failed exception_type=%s', type(error).__name__)
        await self.close()

    async def close(self) -> None:
        try:
            await self.flush(force=True)
            await self.seal()
            if self.capacity is not None and not self._capacity_uncertain:
                await run_blocking(db_executor, live_cap_capacity.release, self.capacity)
                self.capacity = None
            await self.notice()
            _ACTIVE.discard(self)
        finally:
            if self.pending_bytes > 0:
                record_capture('lost')
