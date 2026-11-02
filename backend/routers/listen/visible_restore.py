"""Optional paid preview for batch-owned mobile captures; custody stays independent."""

import asyncio
import time
from typing import Any

from config.server_batch import visible_restore_selected as admitted

from routers.listen.demand_routing import LiveDemandRouting
from utils.metrics import OMI_LISTEN_VISIBLE_RESTORE_STREAMS_TOTAL, OMI_LISTEN_VISIBLE_RESTORE_SECONDS_TOTAL
from utils.observability.demand_cohort import current_visible_restore
from utils.stt.socket import release_live_stt_socket
from utils.stt.replay_delivery import abort_replay_socket
from utils.stt.provider_stream_end import begin_stream_close

VISIBLE_DWELL_SECONDS = 15.0


class VisibleRestore:
    def __init__(self, receiver: Any):
        self.receiver = receiver
        # Reuse strict client-state validation and sibling presence publication.
        # Sibling visibility, unknown presence and server consumers cannot admit
        # this preview: only this socket's stable visible report spends money.
        self.presence = LiveDemandRouting(receiver, eligible=False)
        self.failed = False
        self.socket: Any = None
        self.opened_at: float | None = None
        self.generation = 0
        self.captured_samples = 0
        self.buffer_start_sample = 0
        self.retired: list[Any] = []
        self._close_lock = asyncio.Lock()

    def observe(self, payload):
        self.presence.observe(payload)
        if self.presence.policy.state != 'visible':
            self.close()
            self.failed = False

    def visible(self) -> bool:
        policy = self.presence.policy
        return bool(
            admitted(self.receiver.host)
            and policy.state == 'visible'
            and time.monotonic() - policy.changed_at >= VISIBLE_DWELL_SECONDS
            and self.receiver.host.state.active
        )

    def close(self):
        socket, self.socket = self.socket, None
        self.generation += 1
        if self.opened_at is not None:
            OMI_LISTEN_VISIBLE_RESTORE_SECONDS_TOTAL.inc(max(0, time.monotonic() - self.opened_at))
            self.opened_at = None
        if socket is not None:
            self.retired.append(socket)
            try:
                begin_stream_close(socket)
                socket.finish()
            except Exception:
                pass  # Preview cleanup cannot interrupt original-audio custody.
            finally:
                release_live_stt_socket(socket)
                if self.receiver.stt_socket is socket:
                    self.receiver.stt_socket = None

    async def drain(self):
        async with self._close_lock:
            while self.retired:
                await abort_replay_socket(self.retired.pop(), timeout=2)

    def fail(self):
        if not self.failed:
            self.failed = True
            OMI_LISTEN_VISIBLE_RESTORE_STREAMS_TOTAL.labels(outcome='failed').inc()
        self.close()

    async def open(self) -> bool:
        from utils.stt.streaming import STTService
        from routers.listen.receiver import live_stt_socket_is_dead, process_audio_modulate

        if not self.visible() or self.failed:
            return False
        await self.drain()
        if self.socket is not None:
            if not live_stt_socket_is_dead(self.socket):
                return True
            self.fail()
            return False
        receiver = self.receiver
        admission = getattr(receiver, 'cap_admission', None)
        if admission is not None:
            await admission.refresh(force=False)
            if not admission.allowed(STTService.modulate):
                return False
        receiver.host.stt_service = STTService.modulate
        receiver.host.stt_model = 'velma-2'
        _, callback, epoch = receiver._build_stt_callbacks()
        if epoch is not None:
            # Fresh visible intervals must keep the original capture clock,
            # rather than placing each reopened provider's words at time zero.
            epoch.replay_origin_sample = receiver._stt_buffer_start_sample
        generation = self.generation
        offset = self.buffer_start_sample / receiver.host.request.sample_rate if epoch is None else 0

        def preview(segments):
            if generation == self.generation and self.visible() and not self.failed:
                if offset:
                    segments = [
                        {**segment, 'start': segment.get('start', 0) + offset, 'end': segment.get('end', 0) + offset}
                        for segment in segments
                    ]
                callback(segments)

        token = current_visible_restore.set(True)
        try:
            raw = await asyncio.wait_for(
                process_audio_modulate(preview, receiver.host.request.sample_rate, receiver.host.stt_language),
                timeout=10,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            self.fail()
            return False
        finally:
            current_visible_restore.reset(token)
        # A visibility/kill-switch change while the dial was in flight wins.
        if generation != self.generation or not self.visible():
            await abort_replay_socket(raw, timeout=2)
            return False
        self.socket = receiver._wrap_legacy_stt_socket(raw, epoch)
        receiver.stt_socket = self.socket
        receiver._record_selected_epoch(epoch, self.socket)
        self.opened_at = time.monotonic()
        OMI_LISTEN_VISIBLE_RESTORE_STREAMS_TOTAL.labels(outcome='opened').inc()
        return True

    async def flush(self, buffer: bytearray) -> None:
        from utils.stt.streaming import STTService

        receiver = self.receiver
        self.buffer_start_sample = self.captured_samples
        self.captured_samples += len(buffer) // 2
        try:
            if not self.visible():
                self.close()
                return
            if not buffer or not await receiver._open_deferred_stream():
                return
            admission = getattr(receiver, 'cap_admission', None)
            if admission is not None and not admission.packet_allowed(
                buffer, STTService.modulate, receiver.host.request.sample_rate
            ):
                self.close()
                return
            start = receiver._stt_buffer_start_sample
            accepted = (
                self.socket.send(bytes(buffer), start_sample=start)
                if start is not None
                else self.socket.send(bytes(buffer))
            )
            if accepted is False:
                self.fail()
        except asyncio.CancelledError:
            raise
        except Exception:
            self.fail()
        finally:
            buffer.clear()
            receiver._stt_buffer_start_sample = None

    async def run(self):
        from routers.listen.receiver import live_stt_socket_is_dead

        try:
            while self.receiver.host.state.active:
                if self.socket is not None:
                    if live_stt_socket_is_dead(self.socket):
                        self.fail()
                    elif not self.visible():
                        self.close()
                    elif self.opened_at is not None:
                        now = time.monotonic()
                        OMI_LISTEN_VISIBLE_RESTORE_SECONDS_TOTAL.inc(max(0, now - self.opened_at))
                        self.opened_at = now
                await self.drain()
                if await self.receiver.host.wait(1):
                    return
        finally:
            self.close()
            await self.drain()


def attach_visible_restore(receiver: Any) -> None:
    if not admitted(receiver.host) or getattr(receiver, 'visible_restore', None) is not None:
        return
    restore = receiver.visible_restore = VisibleRestore(receiver)
    receiver.live_demand = restore.presence
    receiver.ensure_live_demand_routing()
    receiver.host.task_supervisor.create_lifetime_task(restore.run(), name='visible_restore')
