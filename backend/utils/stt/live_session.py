"""Managed live-leg construction, VAD ownership and provider epoch timelines."""

from __future__ import annotations

import os
from typing import Any, Awaitable, Callable

from utils.observability.fallback import record_fallback
from utils.observability.transcription import record_live_stt_audio_seconds
from utils.stt import streaming as st
from utils.stt.live_failure import PendingLiveFailover
from utils.stt.live_rollout import window_allocation, window_language_supported
from utils.stt.socket import STTSocket
from utils.stt.vad_gate import VADStreamingGate


class LiveChainSession:
    def __init__(self, receiver: Any) -> None:
        self.receiver = receiver
        self.audio_seconds = 0.0
        self.last_end = 0.0
        self.generation = 0
        self.speech_ms = 0
        self.total_speech_ms = 0

    def consume_speech_ms_delta(self) -> int:
        delta, self.speech_ms = self.speech_ms, 0
        return delta

    def get_metrics(self) -> dict[str, Any]:
        return {'mode': 'active', 'speech_ms_total': self.total_speech_ms}

    def to_json_log(self) -> dict[str, Any]:
        return {'event': 'managed_live_vad_metrics', **self.get_metrics()}

    async def connect(self, sample_rate: int) -> STTSocket:
        host = self.receiver.host
        language = host.stt_language
        uid = host.request.uid
        models = [m.strip() for m in st.stt_service_models]
        keywords: list[str] = host.vocabulary[:100] if host.vocabulary else []
        dg_model = st.deepgram_fallback_model(language)
        window_eligible = (
            window_allocation(uid)
            and window_language_supported(host.language, language)
            and bool(os.getenv('HOSTED_PARAKEET_API_URL'))
        )
        rnnt_eligible = st.parakeet_is_configured_fallback(language)
        parakeet_models = ([host.stt_model] if host.stt_service == st.STTService.parakeet else []) + models
        parakeet_token = next(
            (
                token
                for token in parakeet_models
                if (token == 'parakeet-window' and window_eligible) or (token == 'parakeet' and rnnt_eligible)
            ),
            None,
        )
        window = parakeet_token == 'parakeet-window'
        parakeet_allowed = parakeet_token is not None
        if any(token in models for token in ('parakeet', 'parakeet-window')) and not parakeet_allowed:
            record_fallback(
                component='stt_selection',
                from_mode='parakeet',
                to_mode=host.stt_service.value,
                reason=(
                    'capability_mismatch'
                    if not (
                        window_language_supported(host.language, language)
                        if 'parakeet-window' in models
                        else st.parakeet_supports_language(st.STTServingSurface.STREAMING, language)
                    )
                    else 'allocation_rejected'
                ),
                outcome='degraded',
            )
        generation = self.generation + 1
        offset = self.audio_seconds

        async def build(service: st.STTService) -> STTSocket:
            is_window = service == st.STTService.parakeet and window
            try:
                gate = VADStreamingGate(sample_rate=sample_rate, channels=1, mode='active')
                if is_window:
                    # No four-second silence tail: each early-flushed window must
                    # contain speech, with only a short boundary hangover.
                    gate._hangover_ms = 300  # type: ignore[reportPrivateUsage]  # TDT has a speech-only admission contract
            except Exception:
                if is_window:
                    raise st.ParakeetConnectionError('config_incomplete')
                gate = None
                record_fallback(
                    component='vad', from_mode='gated', to_mode='direct', reason='config_incomplete', outcome='degraded'
                )
            passthrough = service == st.STTService.modulate

            def callback(segments: list[dict[str, Any]]) -> None:
                if generation != self.generation:
                    return
                if gate is not None and not passthrough:
                    gate.remap_segments(segments)
                segments.sort(key=lambda item: item['start'])
                for segment in segments:
                    start = max(self.last_end, offset + max(0.0, float(segment['start'])))
                    end = max(start, offset + max(0.0, float(segment['end'])))
                    segment['start'], segment['end'] = start, end
                    self.last_end = end
                leg.note_selection_transcript(segments)
                self.receiver._enqueue_stt_segments(segments, provider=service.value)

            raw = None
            try:
                if is_window:
                    from utils.stt.parakeet_window import connect_window

                    raw = connect_window(callback, sample_rate)
                elif service == st.STTService.parakeet:
                    raw = await st.process_audio_parakeet(callback, language, sample_rate, 1, keywords=keywords)
                elif service == st.STTService.soniox:
                    raw = await st.process_audio_soniox(callback, sample_rate, language)
                elif service == st.STTService.modulate:
                    raw = await st.process_audio_modulate(callback, sample_rate, language)
                else:
                    raw = await st.process_audio_dg(
                        callback,
                        language,
                        sample_rate,
                        1,
                        model=dg_model or host.stt_model,
                        keywords=keywords,
                        is_active=lambda: host.state.active,
                    )
                if raw is None:
                    raise RuntimeError('Provider returned no socket')
                leg = LiveLegSocket(raw, gate, self, service, sample_rate, is_window, passthrough)
                return leg
            except BaseException:
                if raw is not None:
                    raw.finish()
                raise

        callbacks: dict[st.STTService, Callable[[], Awaitable[STTSocket]] | None] = {
            st.STTService.parakeet: (lambda: build(st.STTService.parakeet)) if parakeet_allowed else None,
            st.STTService.soniox: (
                (lambda: build(st.STTService.soniox)) if 'soniox' in models and os.getenv('SONIOX_API_KEY') else None
            ),
            st.STTService.modulate: (
                (lambda: build(st.STTService.modulate))
                if st.modulate_is_configured_fallback(language) and os.getenv('MODULATE_API_KEY')
                else None
            ),
            st.STTService.deepgram: (lambda: build(st.STTService.deepgram)) if dg_model else None,
        }
        primary = callbacks.get(host.stt_service)
        if primary is None:

            async def unavailable() -> STTSocket:
                raise st.ParakeetConnectionError('config_incomplete')

            primary = unavailable
        socket, actual = await st.connect_stt_socket_with_fallback(
            primary_service=host.stt_service,
            connect_primary=primary,
            connect_parakeet=callbacks[st.STTService.parakeet],
            connect_soniox=callbacks[st.STTService.soniox],
            connect_modulate=callbacks[st.STTService.modulate],
            connect_deepgram=callbacks[st.STTService.deepgram],
            failed=self.receiver._stt_failed_providers,
            use_config=True,
        )
        host.stt_service = actual
        host.stt_model = {
            st.STTService.parakeet: 'parakeet-window' if window else 'parakeet',
            st.STTService.soniox: 'soniox',
            st.STTService.modulate: 'velma-2',
            st.STTService.deepgram: dg_model,
        }[actual]
        self.generation = generation
        self.receiver.vad_gate = self
        return socket


class LiveLegSocket(STTSocket):
    manages_vad = True

    def __init__(
        self,
        raw: STTSocket,
        gate: VADStreamingGate | None,
        session: LiveChainSession,
        service: st.STTService,
        sample_rate: int,
        window: bool,
        passthrough: bool,
    ) -> None:
        self.raw, self.gate, self.session = raw, gate, session
        self.service, self.sample_rate, self.window, self.passthrough = service, sample_rate, window, passthrough
        self._dead = False
        self._seconds = 0.0
        self._pending_selection: PendingLiveFailover | None = None

    @property
    def is_connection_dead(self) -> bool:
        dead = self._dead or self.raw.is_connection_dead
        if dead and self._pending_selection is not None:
            self._pending_selection.note_failure(self.typed_death_reason)
        return dead

    @property
    def death_reason(self) -> str | None:
        return 'vad_failed' if self._dead else self.raw.death_reason

    @property
    def typed_death_reason(self) -> str | None:
        return getattr(self.raw, 'typed_death_reason', None)

    def set_selection_outcome(self, pending: PendingLiveFailover) -> None:
        self._pending_selection = pending

    def note_selection_transcript(self, segments: list[dict[str, Any]]) -> None:
        if self._pending_selection is not None:
            self._pending_selection.note_transcript(segments)

    @property
    def defers_selection_success(self) -> bool:
        return self.window

    def set_health_callbacks(self, on_success: Callable[[], None], on_close: Callable[[], None]) -> None:
        from utils.stt.parakeet_window import WindowedParakeetSocket

        if isinstance(self.raw, WindowedParakeetSocket):
            self.raw.set_health_callbacks(on_success, on_close)

    def send(self, data: bytes) -> bool:
        if self.is_connection_dead:
            return False
        try:
            # Synthetic wall clock follows the received audio, unaffected by POST
            # delays or websocket burst delivery. Positive epoch avoids VAD's zero sentinel.
            output = self.gate.process_audio(data, 1.0 + self._seconds) if self.gate is not None else None
        except Exception:
            self._dead = True
            self.raw.finish()
            record_fallback(
                component='vad', from_mode='gated', to_mode='none', reason='connection_lost', outcome='exhausted'
            )
            return False
        audio = data if output is None or self.passthrough else output.audio_to_send
        if self.window and output is not None and output.is_speech:
            from utils.stt.parakeet_window import WindowedParakeetSocket

            if isinstance(self.raw, WindowedParakeetSocket):
                self.raw.mark_speech()
        try:
            if audio and self.raw.send(audio) is not True:
                self.finish()
                self._dead = True
                return False
            if output is not None and output.should_finalize:
                self.raw.finalize()
        except Exception:
            self._dead = True
            self.finish()
            return False
        duration = len(data) / (self.sample_rate * 2)
        self._seconds += duration
        self.session.audio_seconds += duration
        speech_ms = self.gate.consume_speech_ms_delta() if self.gate is not None else 0
        self.session.speech_ms += speech_ms
        self.session.total_speech_ms += speech_ms
        if speech_ms:
            record_live_stt_audio_seconds(
                provider=self.service.value,
                platform=self.session.receiver._telemetry_platform(),
                seconds=speech_ms / 1000,
            )
        return True

    def finalize(self) -> None:
        self.raw.finalize()

    def finish(self) -> None:
        if self.is_connection_dead and self._pending_selection is not None:
            self._pending_selection.note_failure(self.typed_death_reason)
        self.raw.finish()

    async def drain_and_close(self) -> None:
        try:
            await st.drain_stt_socket(self.raw)
        finally:
            self.finish()
