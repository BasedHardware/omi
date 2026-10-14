"""Bounded per-owner/conversation/hour capture packs, before lossy processing."""

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
        self.capture_session_id = uuid.uuid4().hex

    async def append(
        self,
        raw: bytes,
        conversation_id,
        timestamp: float,
        samples: int,
        channel: int = 0,
        decoded: bytes | None = None,
    ):
        request = self.host.request
        if self.failed or not admitted(request.uid, 'LIVE') or not self.host.private_cloud_sync_enabled:
            return
        pack = self.packs.get(channel)
        if pack is not None and pack.boundary(conversation_id, timestamp, len(raw)):
            await self.flush(channel)
            pack = None
        if pack is None:
            pack = CapturePack(request.codec, request.sample_rate, 1)
            self.packs[channel] = pack
        pack.append(raw, conversation_id, timestamp, samples, decoded)
        # Commit a bounded part before pusher receives its 60-second PCM flush.
        # Volatile hour buffers are never authority for PCM retirement.
        if (
            admitted(request.uid, 'STOP_PCM')
            and admitted(request.uid, 'READ')
            and pack.start is not None
            and pack.end is not None
            and pack.end - pack.start >= 60 - 0.0001
        ):
            await self.flush(channel)

    async def flush(self, channel: int):
        try:
            await self._flush(channel)
        except Exception:
            # Keep today's PCM path on every archive failure. Disabling this
            # session's optional writer also bounds memory during a GCS outage.
            self.failed = True
            self.packs.clear()
            record_fallback(
                component='pusher',
                from_mode='raw_audio',
                to_mode='private_cloud_sync',
                reason='upload_failed',
                outcome='degraded',
            )

    async def _flush(self, channel: int):
        pack = self.packs.get(channel)
        if pack is None or not pack.data:
            return
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
        self.packs.pop(channel, None)

    async def close(self):
        for channel in list(self.packs):
            await self.flush(channel)
