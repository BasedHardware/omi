"""Bounded per-owner/conversation/hour capture packs, before lossy processing."""

import asyncio
import hashlib
import uuid

from config.audio_archive import admitted
from utils.executors import run_blocking, storage_executor
from utils.other.raw_audio import CapturePack
from utils.other.storage import archive_capture_bytes
from utils.observability.fallback import record_fallback


class LiveAudioArchive:
    def __init__(self, host):
        self.host = host
        self.packs: dict[int, CapturePack] = {}
        self.failed = False
        self.inflight: set[asyncio.Task] = set()
        self.capture_session_id = uuid.uuid4().hex
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
    ) -> None:
        request = self.host.request
        # Consent is read before admission: with LIVE default-on, a host that
        # does not carry the consent attribute (older hosts, test doubles)
        # must never crash the receive loop on its way to a no-op archive.
        if (
            self.failed
            or not getattr(self.host, 'private_cloud_sync_enabled', False)
            or not self._admitted(request.uid, 'LIVE')
        ):
            return
        pack = self.packs.get(channel)
        if pack is not None and pack.boundary(conversation_id, timestamp, len(raw)):
            self.flush(channel)
            pack = None
        if pack is None:
            pack = CapturePack(request.codec, request.sample_rate, 1)
            self.packs[channel] = pack
        pack.append(raw, conversation_id, timestamp, samples, decoded)
        # Queue bounded commits ahead of pusher's batched upload without
        # stalling capture/STT clocks. Uncommitted data never retires PCM.
        if (
            self._admitted(request.uid, 'STOP_PCM')
            and self._admitted(request.uid, 'READ')
            and pack.start is not None
            and pack.end is not None
            and pack.end - pack.start >= 60 - 0.0001
        ):
            self.flush(channel)

    def _disable(self, reason: str):
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

    def flush(self, channel: int):
        pack = self.packs.pop(channel, None)
        if pack is None or not pack.data:
            return
        if len(self.inflight) >= 4:
            self._disable('capacity_exhausted')
            return
        task = self.host.spawn(self._commit(pack, channel), name='raw_capture_commit')
        self.inflight.add(task)
        task.add_done_callback(self.inflight.discard)

    async def _commit(self, pack: CapturePack, channel: int):
        try:
            await self._write(pack, channel)
        except Exception:
            self._disable('upload_failed')

    async def _write(self, pack: CapturePack, channel: int):
        request = self.host.request
        context = request.client_device_context
        raw, metadata = await run_blocking(storage_executor, pack.encoded)
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
        await run_blocking(
            storage_executor,
            archive_capture_bytes,
            request.uid,
            raw,
            'raw-live',
            f'{owner}/{hour}/{channel}/{pack.start:.6f}',
            metadata,
        )

    async def close(self):
        for channel in list(self.packs):
            self.flush(channel)
        if self.inflight:
            _, pending = await asyncio.wait(tuple(self.inflight), timeout=15)
            if pending:
                self._disable('timeout')
                for task in pending:
                    task.cancel()
