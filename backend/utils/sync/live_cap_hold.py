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
from utils.sync.cap_hold_lifecycle import ACTIVE as _ACTIVE, SHUTDOWN_DELIVERY_SECONDS

from google.cloud import firestore

from database._client import get_firestore_client, run_transactional, is_retryable_firestore_transaction_error
from database.legal_holds import external_write_fence
from utils.executors import db_executor, storage_executor, run_blocking
from utils.observability.held_content import record_capture, record_staging_retry, PCM_CUSTODY_SECONDS
from utils.sync import cap_hold, live_cap_manifest, live_cap_capacity, live_cap_codec
from utils.sync import live_cap_staging, live_cap_upload, live_cap_journal
from utils.sync.live_cap_publication import Publication
from utils.sync.live_cap_tail import TailGrace
from utils.sync.live_cap_capture import OrderedCapture

logger = logging.getLogger(__name__)

# Legacy v3 PCM reservations remain readable/recoverable. New Opus source
# reservations use live_cap_capacity; failures never silently discard audio.
MAX_MONTHLY_BYTES = 96 * 1024**3
MAX_MONTHLY_CHUNKS = 3_000_000
CHUNK_SECONDS = 60
MAX_PENDING_SECONDS = 15
MAX_POD_PENDING_SECONDS = 600
WARNING_INTERVAL_SECONDS = 60.0


class StagingDeferred(RuntimeError):
    """Both staging stores are temporarily unavailable; this sink owns PCM."""


def pod_pending_seconds() -> float:
    seconds = sum(hold.buffered_seconds() for hold in list(_ACTIVE))
    try:
        PCM_CUSTODY_SECONDS.set(seconds)
    except Exception:
        logger.warning('event=held_content_metric outcome=dropped')
    return seconds


def fragments_enabled() -> bool:
    return os.getenv('CAP_HOLD_LIVE_FRAGMENT_ENABLED', 'true').lower() == 'true'


def _encode_audio(uid: str, data: bytes, rate: int, fragmented: bool) -> bytes:
    with cap_hold.recovery_directory(uid) as directory:
        path = str(Path(directory) / 'source.opus')
        live_cap_codec.encode(
            path, data, rate, **({'max_bytes': live_cap_staging.MAX_FRAGMENT_BYTES} if fragmented else {})
        )
        return Path(path).read_bytes()


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
        Path(path).write_bytes(data)
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
) -> bool:
    encoded = await run_blocking(storage_executor, _encode_audio, uid, data, rate, group is not None)
    try:
        await live_cap_upload.prepare(
            source, lambda: _upload_audio(uid, encoded, rate, start, group, source, metadata, duration)
        )
        # Only the coordinator can commit; an upload worker cannot publish late.
        if group is None:
            await run_blocking(storage_executor, live_cap_manifest.publish, uid, '', source, metadata, duration)
        else:
            await run_blocking(storage_executor, live_cap_staging.append, uid, '', group, source, metadata, duration)
    except live_cap_staging.SourceSealed:
        raise
    except Exception as publication_error:
        # The source identity never changes. Late uploads cannot commit, and
        # the journal is retired only by the same fragment-claim sealer.
        try:
            await run_blocking(
                storage_executor,
                live_cap_journal.defer,
                uid,
                encoded,
                source,
                metadata,
                duration,
                standalone=group is None,
            )
        except Exception as error:
            if live_cap_upload.transient(error) or await run_blocking(
                db_executor, is_retryable_firestore_transaction_error, error
            ):
                raise StagingDeferred('live staging retains process custody') from error
            raise publication_error from error
        return False
    return True


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
        self._tails = TailGrace()
        self._capture = OrderedCapture()
        self._lock = asyncio.Lock()
        self._warning_times: dict[str, float] = {}

    def _warn_deferred(self, outcome: str, error: BaseException) -> None:
        if outcome not in {'staging_retained', 'update_deferred', 'publication_failed'}:
            raise ValueError('unknown live custody warning')
        now = time.monotonic()
        previous = self._warning_times.get(outcome)
        if previous is not None and now - previous < WARNING_INTERVAL_SECONDS:
            return
        self._warning_times[outcome] = now
        logger.warning(
            'event=stt_cap_live_held outcome=%s exception_type=%s pcm_seconds=%.3f',
            outcome,
            type(error).__name__,
            self.buffered_seconds(),
        )

    def _observe_flush(self, task: asyncio.Task) -> None:
        if not task.cancelled() and (error := task.exception()) is not None:
            # Observe failures even when the socket waiter was cancelled,
            # without duplicating an ERROR every updater tick. The non-final
            # flush boundary separately counts each volatile retention attempt.
            outcome = 'staging_retained' if isinstance(error, StagingDeferred) else 'publication_failed'
            self._warn_deferred(outcome, error)

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
        if pod_pending_seconds() + len(data) / (2 * rate) > MAX_POD_PENDING_SECONDS + 1e-9:
            raise RuntimeError('live held audio pod custody bound reached')
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
            if abs(timestamp - expected) > 0.1 or datetime.fromtimestamp(start, timezone.utc).strftime(
                '%Y-%m'
            ) != datetime.fromtimestamp(timestamp, timezone.utc).strftime('%Y-%m'):
                self._queue(key)  # Preserve real clock gaps, never concatenate them.
        if key not in self.buffers:
            self.buffers[key] = [bytearray(), timestamp]
        self._tails.appended(key)
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
            self._tails.opened[key] = time.monotonic()
        self.buffers[key][1] = start
        if self.buffered_seconds() > self.bound + 1e-9:
            raise RuntimeError('live held audio persistence backpressure')
        pod_pending_seconds()

    def buffered_seconds(self) -> float:
        return (
            self._capture.seconds
            + sum(len(item[0]) / (2 * item[1]) for item in self.pending)
            + sum(len(value[0]) / (2 * key[1]) for key, value in self.buffers.items())
        )

    async def _packet_parts(self, data: bytes, rate: int):
        # The caller retains the ingress packet while each complete minute is
        # published. Custody itself never accepts a straddle tail above 60s.
        if rate <= 0 or len(data) % 2:
            raise ValueError('held PCM requires whole samples and a positive rate')
        while data:
            available = min(self.bound - self.buffered_seconds(), MAX_POD_PENDING_SECONDS - pod_pending_seconds())
            frames = int(available * rate + 1e-6)
            if frames <= 0:
                # Force a durable handoff before accepting any bytes past the
                # session or pod bound. No oldest-chunk eviction is allowed.
                sink = self if self.buffered_seconds() else max(list(_ACTIVE), key=lambda h: h.buffered_seconds())
                await sink.flush(force=True, seal=False, final=True)
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
        self._tails.queued(key)
        if buffer:
            channel, rate, owner = key
            self.pending.append((bytes(buffer), rate, start, owner, channel))
            self.pending_bytes += len(buffer)

    async def flush(self, *, force: bool = False, seal: bool = True, final: bool = False) -> None:
        # Callers include host-owned updater/receive tasks. Their cancellation
        # must not release the lock or delete a source beneath an executor upload.
        custody = asyncio.create_task(self._flush(force=force, seal=seal, final=final), name='stt_cap_live_publish')
        self._custody = custody
        custody.add_done_callback(self._observe_flush)
        try:
            await asyncio.shield(custody)
        except StagingDeferred as error:
            if final:
                raise  # At close/bound, no more volatile custody is safe.
            record_staging_retry('retained')
            self._warn_deferred('staging_retained', error)
        except asyncio.CancelledError:
            # Keep ownership until the executor has stopped using the scratch
            # file. Shutdown also awaits active sinks before closing clients.
            # The sink retains the task and the lock; its own coroutine keeps
            # scratch/PCM alive. Socket and lifespan close await the same lock.
            raise
        except Exception as error:
            if final or not (
                live_cap_upload.transient(error)
                or await run_blocking(db_executor, is_retryable_firestore_transaction_error, error)
            ):
                raise
            # Reservation/summary faults also leave every unretired sample in
            # this sink. A full bound or close must still prove durable custody.
            logger.warning('event=stt_cap_live_held outcome=flush_deferred exception_type=%s', type(error).__name__)

    async def _seal_group(self) -> None:
        if self._group is None:
            return
        try:
            await run_blocking(storage_executor, live_cap_staging.seal, self.host.request.uid, self._group.identity)
        except Exception as error:
            if not self._group_parts:
                raise
            # Every part already has a durable staging receipt. No compose or
            # follow-up read failure can revoke that custody; redrive owns seal.
            logger.warning('event=stt_cap_live_held outcome=seal_deferred exception_type=%s', type(error).__name__)
        self.seconds += self._group_seconds
        self._group = None
        self._group_key = None
        self._group_seconds = 0.0
        self._group_parts = 0

    async def _reserve_capacity(self, month: str) -> None:
        if self.capacity is not None and self.capacity.month != month:
            await run_blocking(db_executor, live_cap_capacity.release, self.capacity)
            self.capacity = None
        if self.capacity is None or self.capacity.used == live_cap_capacity.BLOCK_GROUPS:
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

    async def _flush(self, *, force: bool = False, seal: bool = True, final: bool = False) -> None:
        async with self._lock:
            for span in self._capture.take(self.bound, force=force or final):
                key = (0, span.rate, span.owner)
                if key in self.buffers:
                    self._queue(key)  # Distinct capture runs keep their holes.
                self.append(bytes(span.data), span.rate, span.timestamp, span.owner)
                if key in self.buffers:
                    self._tails.opened[key] = min(self._tails.opened[key], span.opened)
            seal_tail = self._tails.expired()
            for key in list(self.buffers):
                seconds = len(self.buffers[key][0]) / (2 * key[1])
                if self._tails.ready(key, seconds, self.bound, force=force, final=final):
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
                        published = await _publish_audio(
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
                        published = await _publish_audio(
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
                    if published:
                        if self._group_parts == 0:
                            capacity.consume()
                        self._group_parts += 1
                        self._group_seconds += duration
                        self._group_end = start + duration
                    else:
                        capacity.consume()
                        if self._group_parts == 0:
                            self._group = None
                    self._capacity_uncertain = False
                else:
                    published = await _publish_audio(
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
                if not self.fragmented and published:
                    self.seconds += duration
                self.pending.popleft()
                self.pending_bytes -= len(data)
                pod_pending_seconds()
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
            if self.fragmented and seal and (force or final or seal_tail) and not self.buffers:
                await self._seal_group()

    async def seal(self, channel: int | None = None) -> None:
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
                            part = data[(first - start) * 2 : (last - start) * 2]
                            if self.buffered_seconds() + len(part) / (2 * rate) > self.bound + 1e-9:
                                raise RuntimeError('live held audio packet exceeds custody bound')
                            if pod_pending_seconds() + len(part) / (2 * rate) > MAX_POD_PENDING_SECONDS + 1e-9:
                                raise RuntimeError('live held audio pod custody bound reached')
                            self.paused = True
                            owner = receiver._owner_for_sample(first)
                            if self.fragmented:
                                self._capture.add(first, part, rate, timestamp, owner)
                            else:
                                self.append(part, rate, timestamp, owner)
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
        pod_pending_seconds()

    async def run_updates(self, receiver: Any) -> None:
        while not receiver._cap_hold_stop.is_set():
            try:
                await asyncio.wait_for(receiver._cap_hold_stop.wait(), timeout=1)
            except asyncio.TimeoutError:
                pass
            if receiver._cap_hold_stop.is_set():
                return
            try:
                pod_pending_seconds()
                await receiver._emit_stt_cap_live_held()
                if self.paused and not receiver.cap_admission.funded_paused and not receiver.cap_paused:
                    await self.flush(force=True)
                    await self.notice(paused=False)
            except Exception as error:
                # Updater errors cannot escape to the WS lifetime supervisor.
                # PCM stays in this sink; receive/close retry the same identity.
                self._warn_deferred('update_deferred', error)

    async def finish_updates(self, updates: asyncio.Task | None, stop: asyncio.Event) -> None:
        try:
            async with asyncio.timeout(SHUTDOWN_DELIVERY_SECONDS):
                await self._finish_updates(updates, stop)
        except TimeoutError:
            if self.buffered_seconds():
                raise
            _ACTIVE.discard(self)

    async def _finish_updates(self, updates: asyncio.Task | None, stop: asyncio.Event) -> None:
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
            async with asyncio.timeout(SHUTDOWN_DELIVERY_SECONDS):
                await self._close()
        except TimeoutError:
            if self.buffered_seconds():
                raise
            # A slow refund/seal/notice cannot revoke already durable custody.
            _ACTIVE.discard(self)

    async def _close(self) -> None:
        try:
            await self.flush(force=True, final=True)
            if self.capacity is not None and not self._capacity_uncertain:
                try:
                    await run_blocking(db_executor, live_cap_capacity.release, self.capacity)
                    self.capacity = None
                except Exception as error:
                    # Audio already has durable custody. A failed quota refund
                    # cannot justify an internal-error close or erase that data.
                    logger.warning(
                        'event=stt_cap_live_held outcome=refund_deferred exception_type=%s', type(error).__name__
                    )
            await self.notice()
            _ACTIVE.discard(self)
        finally:
            if self.pending_bytes > 0:
                record_capture('lost')
