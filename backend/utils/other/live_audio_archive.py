"""Bounded per-owner/conversation/hour capture packs, before lossy processing."""

import asyncio
import hashlib
import uuid

from config.audio_archive import admitted
from config.audio_outbox import enabled as audio_outbox_enabled
from models.message_event import AudioCustodyEvent
from utils.executors import run_blocking, storage_executor
from utils.other.raw_audio import CapturePack
from utils.other.storage import archive_capture_bytes
from utils.other.audio_outbox import commit_capture
from utils.other.audio_outbox_metrics import BACKPRESSURE, record_failure, record_would_drop
from utils.observability.fallback import record_fallback


class LiveAudioArchive:
    def __init__(self, host):
        self.host = host
        self.packs: dict[int, CapturePack] = {}
        self.failed = False
        self.inflight: set[asyncio.Task] = set()
        self.capture_session_id = uuid.uuid4().hex
        self.durable = audio_outbox_enabled()
        self.lock = asyncio.Lock()
        self.uncommitted: dict[int, tuple[CapturePack, int]] = {}
        self.running: set[int] = set()
        self.frames: dict[int, list[dict]] = {}
        self.sequence: dict[int, int] = {}
        # Session-stable admission: this per-packet path must not re-query the
        # TTL cache. An expiry window would schedule a refresh but miss until
        # it completes, silently dropping archive packets once per TTL. Listen
        # warms membership at connection start, so the first append snapshots
        # the resolved decision for the connection lifetime.
        self._admitted_snapshot: dict[str, bool] = {}

    def _admitted(self, uid: str, phase: str) -> bool:
        if phase not in self._admitted_snapshot:
            self._admitted_snapshot[phase] = admitted(uid, phase)
        return self._admitted_snapshot[phase]

    async def append(
        self,
        raw: bytes,
        conversation_id,
        timestamp: float,
        samples: int,
        channel: int = 0,
        decoded: bytes | None = None,
        source_frame: dict | None = None,
    ) -> None:
        async with self.lock:
            await self._append(raw, conversation_id, timestamp, samples, channel, decoded, source_frame)

    async def _append(self, raw, conversation_id, timestamp, samples, channel, decoded, source_frame):
        request = self.host.request
        # Consent is read before admission: with LIVE default-on, a host that
        # does not carry the consent attribute (older hosts, test doubles)
        # must never crash the receive loop on its way to a no-op archive.
        if (
            (self.failed and not self.durable)
            or not getattr(self.host, 'private_cloud_sync_enabled', False)
            or (not self.durable and not self._admitted(request.uid, 'LIVE'))
        ):
            return
        if self.durable and (self.failed or any(key not in self.running for key in self.uncommitted)):
            await self._retry_pending()
        pack = self.packs.get(channel)
        if pack is not None and (
            pack.boundary(conversation_id, timestamp, len(raw))
            or (self.durable and len(self.frames.get(id(pack), [])) >= 4096)
        ):
            await self.flush(channel)
            pack = None
        if pack is None:
            pack = CapturePack(request.codec, request.sample_rate, 1)
            self.packs[channel] = pack
        previous_end = pack.end
        offset = len(pack.data)
        pack.append(raw, conversation_id, timestamp, samples, decoded)
        if self.durable:
            sequence = self.sequence.get(channel, 0)
            self.sequence[channel] = sequence + 1
            self.frames.setdefault(id(pack), []).append(
                {
                    'sequence': sequence,
                    'byte_offset': offset,
                    'bytes': len(pack.data) - offset,
                    'start': timestamp,
                    'samples': samples,
                    'gap_before': previous_end is not None and abs(timestamp - previous_end) > 0.002,
                    'sha256': hashlib.sha256(raw).hexdigest(),
                    'source': source_frame,
                }
            )
        # Queue bounded commits ahead of pusher's batched upload without
        # stalling capture/STT clocks. Uncommitted data never retires PCM.
        if (
            (self.durable or (self._admitted(request.uid, 'STOP_PCM') and self._admitted(request.uid, 'READ')))
            and pack.start is not None
            and pack.end is not None
            and pack.end - pack.start >= 60 - 0.0001
        ):
            await self.flush(channel)

    def _disable(self, reason: str):
        if self.durable:
            self.failed = True
            record_would_drop('raw_pack')
            record_failure('raw_commit')
            return
        if not self.failed:
            self.failed = True
            self.packs.clear()
            record_fallback(
                component='pusher',
                from_mode='raw_audio',
                to_mode='private_cloud_sync',
                reason=reason,
                outcome='degraded',
            )

    async def flush(self, channel: int):
        pack = self.packs.get(channel)
        if pack is None or not pack.data:
            return
        if len(self.inflight) >= 4:
            if not self.durable:
                self.packs.pop(channel, None)
                self._disable('capacity_exhausted')
                return
            BACKPRESSURE.labels(stage='raw_capacity').inc()
            record_would_drop('raw_capacity')
            done, _ = await asyncio.wait(tuple(self.inflight), return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()  # Refusal propagates before removing the active pack.
        self.packs.pop(channel, None)
        if self.durable:
            self.uncommitted[id(pack)] = (pack, channel)
        self._start(pack, channel)

    def _start(self, pack, channel):
        self.running.add(id(pack))
        commit = self._commit(pack, channel)
        try:
            task = self.host.spawn(commit, name='raw_capture_commit')
        except BaseException:
            commit.close()
            self.running.discard(id(pack))
            self._disable('enqueue_failed')
            raise
        self.inflight.add(task)

        def finished(task):
            self.inflight.discard(task)
            self.running.discard(id(pack))
            if task.cancelled():
                self.failed = True
            else:
                task.exception()  # Kept in uncommitted and retried at the next barrier.

        task.add_done_callback(finished)

    async def _retry_pending(self):
        for key, (pack, channel) in list(self.uncommitted.items()):
            # Another pack can commit while an earlier retry awaits storage.
            if key in self.uncommitted and key not in self.running:
                # Retry one at a time, retaining the original bytes/identity.
                await self._commit(pack, channel)
        if self.inflight:
            done, _ = await asyncio.wait(tuple(self.inflight))
            for task in done:
                task.result()
        self.failed = False

    async def _commit(self, pack: CapturePack, channel: int):
        try:
            await self._write(pack, channel)
            self.uncommitted.pop(id(pack), None)
            self.frames.pop(id(pack), None)
        except Exception:
            self._disable('upload_failed')
            if self.durable:
                raise
        finally:
            self.running.discard(id(pack))

    async def _write(self, pack: CapturePack, channel: int):
        request = self.host.request
        context = request.client_device_context
        raw, metadata = await run_blocking(storage_executor, pack.encoded, preserve_pcm=self.durable)
        headers = getattr(request.websocket, 'headers', {})
        metadata.update(
            firmware=headers.get('x-omi-firmware-version'),
            frame_size='variable' if request.codec == 'opus' else 'sample-aligned',
            capture_sha256=hashlib.sha256(bytes(pack.data)).hexdigest(),
            app_version=getattr(context, 'app_version', None),
            device_model=headers.get('x-omi-device-model') or request.source,
            consent_state='private_cloud_sync_enabled',
            consent_version=headers.get('x-omi-audio-consent-version', 'unknown'),
            consent_scope='cloud_audio_storage',
            training_consent_state='unknown',
            channel_index=channel,
            capture_session_id=self.capture_session_id,
            clock_source='server_projected',
            gap_domain='server_projected_sample_clock',
            source_layout='multi-channel' if getattr(self.host, 'is_multi_channel', False) else 'mono',
        )
        # Unknown linkage is explicit rather than inventing a conversation.
        # These packs remain training captures, but cannot qualify playback.
        owner = pack.conversation_id or 'unlinked'
        if pack.start is None:
            raise ValueError('capture has no start clock')
        hour = int(pack.start // 3600)
        if self.durable:
            frames = self.frames.get(id(pack), [])
            first = frames[0]['sequence'] if frames else 0
            receipt = await run_blocking(
                storage_executor,
                commit_capture,
                request.uid,
                raw,
                f'{owner}/{hour}/{channel}/{self.capture_session_id}/{first}',
                metadata,
                frames,
            )
            # A failed/disconnected delivery leaves the producer unacknowledged;
            # receipt loss is safe because the immutable media remains indexed.
            query = getattr(request.websocket, 'query_params', {})
            if query.get('audio_custody') == '1' and hasattr(self.host, 'send_event'):
                self.host.send_event(
                    AudioCustodyEvent(
                        event_type='audio_custody',
                        receipt=receipt.to_dict(),
                        capture_root=self.capture_session_id,
                        channel=str(channel),
                        frames=frames,
                    )
                )
            return
        await run_blocking(
            storage_executor,
            archive_capture_bytes,
            request.uid,
            raw,
            'raw-live',
            f'{owner}/{hour}/{channel}/{pack.start:.6f}',
            metadata,
        )

    async def ensure_durable(self):
        """Barrier before transcript commit/ACK; also commits silence-only tails."""
        async with self.lock:
            if self.durable and (self.failed or any(key not in self.running for key in self.uncommitted)):
                await self._retry_pending()
            for channel in list(self.packs):
                await self.flush(channel)
            if self.inflight:
                done, pending = await asyncio.wait(tuple(self.inflight), timeout=15)
                if self.durable:
                    for task in done:
                        task.result()
                    if pending:
                        record_would_drop('raw_timeout')
                        raise TimeoutError('audio custody not committed; producer remains unacknowledged')
                elif pending:
                    self._disable('timeout')
                    for task in pending:
                        task.cancel()
            if self.durable and self.uncommitted:
                raise RuntimeError('audio custody still pending; producer remains unacknowledged')

    async def close(self):
        await self.ensure_durable()
